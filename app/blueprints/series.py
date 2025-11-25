from flask import Blueprint, request, jsonify, g, Response
from app.middleware.auth import authenticate_jwt
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
)
import json
from app.utils.json_encoder import JSONEncoder
# API Version 1
bp = Blueprint("series", __name__, url_prefix="/api/v1/series")


def _success_response(data, message=None, status=200):
    payload = data
    
    return Response(
        json.dumps(payload, cls=JSONEncoder),
        mimetype="application/json",
        status=status
    )



def _error_response(message, status=500):
    """Helper: Create error response"""
    return Response(
        json.dumps({"success": False, "message": message}),
        mimetype="application/json",
        status=status
    )


@bp.route("", methods=["POST"])
@authenticate_jwt
def create_serie_route():
    """Create a new series"""
    try:
        data = request.form.to_dict() if request.form else request.get_json() or {}
        file = request.files.get("serie_thumbnail") if request.files else None
        
        user_id = g.user.get("userId")
        id_token = g.user.get("idToken")
        
        result = create_serie(data, user_id, id_token, file)
        return _success_response(result, "Series created successfully", 201)
    
    except Exception as e:
        return _error_response(str(e))


@bp.route("", methods=["GET"])
@authenticate_jwt
def list_series():
    """List all series with optional pagination"""
    try:
        query_params = request.args.to_dict()
        result = get_all_series(query_params)
        return _success_response(result)
    
    except Exception as e:
        return _error_response(str(e))


@bp.route("/subscribed", methods=["GET"])
@authenticate_jwt
def get_user_subscribed_series():
    """Get series subscribed by current user"""
    try:
        user_id = g.user.get("userId")
        result = get_series_subscribed_by_user(user_id)
        return _success_response(result)
    
    except Exception as e:
        return _error_response(str(e))


@bp.route("/created", methods=["GET"])
@authenticate_jwt
def get_user_created_series():
    """Get series created by current user"""
    try:
        user_id = g.user.get("userId")
        result = get_all_series_by_user(user_id)
        return _success_response(result)
    
    except Exception as e:
        return _error_response(str(e))


@bp.route("/search", methods=["GET"])
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
def update_serie_route(serie_id):
    """Update series information"""
    try:
        data = request.form.to_dict() if request.form else request.get_json() or {}
        file = request.files.get("serie_thumbnail") if request.files else None
        
        user_id = g.user.get("userId")
        id_token = g.user.get("idToken")
        
        updated = update_serie(serie_id, data, user_id, id_token, file)
        
        if not updated:
            return _error_response("Serie not found", 404)
        
        return _success_response(updated, "Series updated successfully")
    
    except Exception as e:
        return _error_response(str(e))


@bp.route("/<serie_id>/subscribe", methods=["POST"])
@authenticate_jwt
def subscribe_to_serie(serie_id):
    """Subscribe current user to a series"""
    try:
        user_id = g.user.get("userId")
        user_email = g.user.get("email")
        
        if not user_id or not user_email:
            return _error_response("Thiếu thông tin người dùng", 400)
        
        result = subscribe_serie(serie_id, user_id, user_email)
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
        user_id = g.user.get("userId")
        user_email = g.user.get("email")
        
        if not user_id or not user_email:
            return _error_response("Thiếu thông tin người dùng", 400)
        
        result = unsubscribe_serie(serie_id, user_id, user_email)
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
        result = delete_serie(serie_id)
        
        if not result.get("success"):
            return _error_response(result.get("warning"), 400)
        
        return _success_response(None, "Serie deleted successfully")
    
    except ValueError as e:
        return _error_response(str(e), 404)
    except Exception as e:
        return _error_response(str(e))