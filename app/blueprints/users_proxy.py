"""
User Service Proxy Blueprint
Forwards all /api/v1/users/* requests to User Service microservice
This allows Frontend to continue using the same Backend URL
"""
from flask import Blueprint, request, Response
import requests
import os

bp = Blueprint("users_proxy", __name__, url_prefix="/api/v1/users")

USER_SERVICE_URL = os.environ.get('USER_SERVICE_URL', 'http://localhost:5002')


@bp.route('/', defaults={'path': ''}, methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'])
@bp.route('/<path:path>', methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'])
def proxy_to_user_service(path):
    """
    Proxy all user requests to User Service
    Preserves headers, body, query params, and HTTP method
    """
    # Build target URL
    if path:
        target_url = f"{USER_SERVICE_URL}/api/v1/users/{path}"
    else:
        target_url = f"{USER_SERVICE_URL}/api/v1/users/"

    # Preserve query parameters
    if request.query_string:
        target_url += f"?{request.query_string.decode('utf-8')}"

    # Forward headers (especially Authorization)
    headers = {}
    for key, value in request.headers:
        if key.lower() not in ['host', 'connection']:
            headers[key] = value

    # Get request body
    data = None
    if request.method in ['POST', 'PUT', 'PATCH']:
        data = request.get_data()

    try:
        # Forward request to User Service
        response = requests.request(
            method=request.method,
            url=target_url,
            headers=headers,
            data=data,
            allow_redirects=False,
            timeout=30
        )

        # Build response to return to client
        excluded_headers = ['content-encoding', 'content-length', 'transfer-encoding', 'connection']
        response_headers = [
            (name, value) for (name, value) in response.raw.headers.items()
            if name.lower() not in excluded_headers
        ]

        return Response(
            response.content,
            status=response.status_code,
            headers=response_headers
        )

    except requests.exceptions.ConnectionError:
        return {
            "success": False,
            "message": "User Service unavailable. Please try again later."
        }, 503
    except requests.exceptions.Timeout:
        return {
            "success": False,
            "message": "User Service timeout. Please try again."
        }, 504
    except Exception as e:
        print(f"Error proxying to User Service: {e}")
        return {
            "success": False,
            "message": f"Proxy error: {str(e)}"
        }, 500
