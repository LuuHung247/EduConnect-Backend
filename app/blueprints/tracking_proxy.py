"""
Tracking Service Proxy Blueprint
Forwards all /api/v1/tracking/* requests to Tracking Service microservice
Enriches /user/{user_id}/current response with lesson details
"""
from flask import Blueprint, request, Response, jsonify
import requests
import json
import os
import re
from app.services.lesson_service import LessonService

bp = Blueprint("tracking_proxy", __name__, url_prefix="/api/v1/tracking")

TRACKING_SERVICE_URL = os.environ.get('TRACKING_SERVICE_URL', 'http://localhost:8002')

# Initialize lesson service for fetching lesson details
lesson_service = LessonService()


@bp.route('/', defaults={'path': ''}, methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'])
@bp.route('/<path:path>', methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'])
def proxy_to_tracking_service(path):
    """
    Proxy all tracking requests to Tracking Service
    Special handling for GET /user/{user_id}/current - enriches with lesson details
    """
    # Build target URL
    if path:
        target_url = f"{TRACKING_SERVICE_URL}/api/tracking/{path}"
    else:
        target_url = f"{TRACKING_SERVICE_URL}/api/tracking/"

    # Preserve query parameters
    if request.query_string:
        target_url += f"?{request.query_string.decode('utf-8')}"

    # Forward headers (especially Authorization)
    headers = {}
    for key, value in request.headers:
        if key.lower() not in ['host', 'connection', 'content-length']:
            headers[key] = value

    # Get request body
    data = None
    if request.method in ['POST', 'PUT', 'PATCH']:
        data = request.get_data()

    try:
        # Forward request to Tracking Service
        response = requests.request(
            method=request.method,
            url=target_url,
            headers=headers,
            data=data,
            allow_redirects=False,
            timeout=30
        )

        # Check if this is GET /user/{user_id}/current endpoint
        # Pattern: user/{user_id}/current
        is_current_lesson_endpoint = (
            request.method == 'GET' and
            re.match(r'^user/[^/]+/current$', path)
        )

        if is_current_lesson_endpoint and response.status_code == 200:
            # Enrich response with lesson details
            try:
                tracking_data = response.json()

                # If user is in a lesson, fetch lesson details
                if tracking_data.get('is_in_lesson') and tracking_data.get('lesson_id'):
                    lesson_id = tracking_data['lesson_id']
                    serie_id = tracking_data.get('serie_id')

                    # Fetch lesson details from database
                    # NOTE: Method signature is get_lesson_by_id(series_id, lesson_id) - order matters!
                    lesson_details = lesson_service.get_lesson_by_id(serie_id, lesson_id)

                    if lesson_details:
                        # Add lesson_data to response
                        tracking_data['lesson_data'] = {
                            'lesson_title': lesson_details.get('lesson_title'),
                            'lesson_description': lesson_details.get('lesson_description'),
                            'lesson_serie': lesson_details.get('lesson_serie'),
                            'lesson_video': lesson_details.get('lesson_video'),
                            'lesson_transcript': lesson_details.get('lesson_transcript'),
                            'transcript_status': lesson_details.get('transcript_status'),
                            'lesson_documents': lesson_details.get('lesson_documents', []),
                            'createdAt': lesson_details.get('createdAt'),
                            'updatedAt': lesson_details.get('updatedAt'),
                            'lesson_summary': lesson_details.get('lesson_summary'),
                            'lesson_timeline': lesson_details.get('lesson_timeline')
                        }

                # Return enriched response
                return jsonify(tracking_data)

            except Exception as e:
                print(f"Error enriching tracking response with lesson data: {e}")
                # Fall through to return original response if enrichment fails

        # Return original response from Tracking Service
        return Response(
            response.content,
            status=response.status_code,
            headers=dict(response.headers)
        )

    except requests.exceptions.RequestException as e:
        print(f"Error proxying to Tracking Service: {e}")
        return Response(
            f'{{"error": "Tracking Service unavailable: {str(e)}"}}',
            status=503,
            content_type='application/json'
        )
