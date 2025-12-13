from flask import Blueprint, request, g, Response
from app.middleware.auth import authenticate_jwt, instructor_required
from app.services.serie_service import (
    create_serie,
    get_all_series,
    get_serie_by_id,
    update_serie,
    delete_serie,
    subscribe_serie,
    unsubscribe_serie,
    search_series_by_title,
    get_series_subscribed_by_user,
    get_all_series_by_user,
    send_series_notification
)
import json
from app.utils.json_encoder import JSONEncoder
from app.utils.cache import (
    cached_public,
    cached_with_user,
    invalidate_series_cache,
    invalidate_user_cache,
)

bp = Blueprint("series", __name__, url_prefix="/api/v1/series")


def _success_response(data, message=None, status=200):
    return Response(
        json.dumps(data, cls=JSONEncoder),
        mimetype="application/json",
        status=status
    )


def _error_response(message, status=500):
    return Response(
        json.dumps({"success": False, "message": message}),
        mimetype="application/json",
        status=status
    )


@bp.route("", methods=["POST"])
@authenticate_jwt
# @instructor_required
def create_serie_route():
    """Create a new series"""
    try:
        data = request.form.to_dict() if request.form else request.get_json() or {}
        file = request.files.get("serie_thumbnail") if request.files else None
        
        user_id = g.user_sub
        id_token = request.headers.get('Authorization', '').replace('Bearer ', '')
        
        result = create_serie(data, user_id, id_token, file)
        
        # Invalidate cache
        # invalidate_series_cache()
        # invalidate_user_cache(user_id)  # User's created series changed
        
        return _success_response(result, "Series created successfully", 201)
    
    except Exception as e:
        return _error_response(str(e))


@bp.route("/", methods=["GET"])
@authenticate_jwt
# @cached_public(timeout=300)  # Cache 5 phút, public (ETag included)
def list_series():
    """List all series with optional pagination"""
    try:
        query_params = request.args.to_dict()
        result = get_all_series(query_params)
        return _success_response(result)
    
    except Exception as e:
        return _error_response(str(e))


@bp.route("/subscriptions", methods=["GET"])
@authenticate_jwt
# @cached_with_user(timeout=120)  # Cache 2 phút, per user (ETag included)
def get_user_subscribed_series():
    """Get series subscribed by current user"""
    try:
        user_id = g.user_sub
        result = get_series_subscribed_by_user(user_id)
        return _success_response(result)
    
    except Exception as e:
        return _error_response(str(e))


@bp.route("/me", methods=["GET"])
@authenticate_jwt
# @cached_with_user(timeout=120)  # Cache 2 phút, per user (ETag included)
def get_user_created_series():
    """Get series created by current user"""
    try:
        user_id = g.user_sub
        result = get_all_series_by_user(user_id)
        return _success_response(result)
    
    except Exception as e:
        return _error_response(str(e))


@bp.route("/search", methods=["GET"])
# @cached_public(timeout=60)  # Cache 1 phút (ETag included)
def search_series():
    """Search series by keyword"""
    try:
        keyword = request.args.get("keyword")
        
        if not keyword:
            return _error_response("Thiếu từ khóa tìm kiếm", 400)
        
        result = search_series_by_title(keyword)
        return _success_response(result)
    
    except Exception as e:
        return _error_response(str(e))


@bp.route("/<serie_id>", methods=["GET"])
# @cached_public(timeout=300)  # Cache 5 phút (ETag included)
def get_serie_detail(serie_id):
    """Get series details by ID"""
    try:
        serie = get_serie_by_id(serie_id)
        
        if not serie:
            return _error_response("Serie not found", 404)
        
        return _success_response(serie)
    
    except Exception as e:
        return _error_response(str(e))


@bp.route("/<serie_id>", methods=["PATCH"])
@authenticate_jwt
# @instructor_required
def update_serie_route(serie_id):
    """Update series information"""
    try:
        data = request.form.to_dict() if request.form else request.get_json() or {}
        file = request.files.get("serie_thumbnail") if request.files else None
        
        user_id = g.user_sub
        id_token = request.headers.get('Authorization', '').replace('Bearer ', '')
        
        updated = update_serie(serie_id, data, user_id, id_token, file)
        
        if not updated:
            return _error_response("Serie not found", 404)
        
        # Invalidate cache
        # invalidate_series_cache(serie_id)
        
        return _success_response(updated, "Series updated successfully")
    
    except Exception as e:
        return _error_response(str(e))


@bp.route("/<serie_id>/subscribe", methods=["POST"])
@authenticate_jwt
def subscribe_to_serie(serie_id):
    """Subscribe current user to a series"""
    try:
        user_id = g.user_sub
        user_email = g.user_email
        
        if not user_id or not user_email:
            return _error_response("Thiếu thông tin người dùng", 400)
        
        result = subscribe_serie(serie_id, user_id, user_email)
        
        # Invalidate caches
        # invalidate_series_cache(serie_id)
        # invalidate_user_cache(user_id)  # User's subscribed list changed
        
        return _success_response(result)
    
    except ValueError as e:
        return _error_response(str(e), 404)
    except Exception as e:
        return _error_response(str(e))


@bp.route("/<serie_id>/unsubscribe", methods=["POST"])
@authenticate_jwt
def unsubscribe_from_serie(serie_id):
    """Unsubscribe current user from a series"""
    try:
        user_id = g.user_sub
        user_email = g.user_email
        
        if not user_id or not user_email:
            return _error_response("Thiếu thông tin người dùng", 400)
        
        result = unsubscribe_serie(serie_id, user_id, user_email)
        
        # Invalidate caches
        # invalidate_series_cache(serie_id)
        # invalidate_user_cache(user_id)  # User's subscribed list changed
        
        return _success_response(result)
    
    except ValueError as e:
        return _error_response(str(e), 404)
    except Exception as e:
        return _error_response(str(e))


@bp.route("/<serie_id>", methods=["DELETE"])
@authenticate_jwt
def delete_serie_route(serie_id):
    """Delete a series"""
    try:
        user_id = g.user_sub
        result = delete_serie(serie_id)
        
        if not result.get("success"):
            return _error_response(result.get("warning"), 400)
        
        # Invalidate caches
        # invalidate_series_cache(serie_id)
        # invalidate_user_cache(user_id)  # User's created series changed
        
        return _success_response(None, "Serie deleted successfully")
    
    except ValueError as e:
        return _error_response(str(e), 404)
    except Exception as e:
        return _error_response(str(e))
    

@bp.route("/<serie_id>/notify", methods=["POST"])
@authenticate_jwt
def send_notification_route(serie_id):
    try:
        data = request.get_json() or {}
        title = data.get("title")
        message = data.get("message")

        if not title or not message:
            return _error_response("Tiêu đề và nội dung thông báo là bắt buộc", 400)

        result = send_series_notification(serie_id, title, message)
        
        return _success_response(result, "Thông báo đã được gửi thành công")

    except ValueError as e:
        return _error_response(str(e), 404)
    except Exception as e:
        print(f"Notification Error: {str(e)}")
        return _error_response(str(e), 500)