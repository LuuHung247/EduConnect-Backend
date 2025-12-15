"""
Tracking Service Proxy Blueprint
Forwards all /api/v1/tracking/* requests to Tracking Service microservice
This allows Frontend to continue using the same Backend URL
"""
from flask import Blueprint, request, Response
import requests
import os

bp = Blueprint("tracking_proxy", __name__, url_prefix="/api/v1/tracking")

TRACKING_SERVICE_URL = os.environ.get('TRACKING_SERVICE_URL', 'http://localhost:8002')


@bp.route('/', defaults={'path': ''}, methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'])
@bp.route('/<path:path>', methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'])
def proxy_to_tracking_service(path):
    """
    Proxy all tracking requests to Tracking Service
    Preserves headers, body, query params, and HTTP method
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

        # Return response from Tracking Service
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
