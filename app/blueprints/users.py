from flask import Blueprint, request, jsonify, g
from app.services.user_service import (
    create_user,
    get_user_by_id,
    update_user,
)
from app.middleware.auth import authenticate_jwt

# API Version 1
bp = Blueprint("users", __name__, url_prefix="/api/v1/users")


def _success_response(data, message=None, status=200):
    """Helper: Create success response"""
    response = {"success": True, "data": data}
    if message:
        response["message"] = message
    return jsonify(response), status


def _error_response(message, status=500):
    """Helper: Create error response"""
    return jsonify({"success": False, "message": message}), status


@bp.route("/profile", methods=["POST"])
def create_profile():
    """Create user profile"""
    try:
        user_data = request.get_json() or {}
        user_id = user_data.get("userId")

        if not user_id:
            return _error_response("userId is required", 400)
        
        # Check if user already exists
        existing = get_user_by_id(user_id)
        if existing:
            return _error_response("User profile already exists", 409)
        
        result = create_user(user_data)
        return _success_response(result, "User profile created successfully", 201)
    
    except Exception as e:
        return _error_response(str(e))


@bp.route("/profile", methods=["GET"])
@authenticate_jwt
def get_current_profile():
    """Get current authenticated user's profile"""
    try:
        user_id = g.user.get("userId")
        user = get_user_by_id(user_id)
        
        # Auto-create profile if not exists
        if not user:
            user_data = {
                "userId": user_id,
                "name": g.user.get("name"),
                "email": g.user.get("email"),
                "username": g.user.get("username"),
            }
            user = create_user(user_data)
            return _success_response(user, "User profile created automatically", 201)
        
        return _success_response(user)
    
    except Exception as e:
        return _error_response(str(e))


@bp.route("/<user_id>", methods=["GET"])
@authenticate_jwt
def get_user(user_id):
    """Get user by ID"""
    try:
        user = get_user_by_id(user_id)
        
        if not user:
            return _error_response("User not found", 404)
        
        return _success_response(user)
    
    except Exception as e:
        return _error_response(str(e))


@bp.route("/<user_id>", methods=["PUT"])
@authenticate_jwt
def update_user_profile(user_id):
    """Update user profile"""
    try:
        data = request.get_json() or {}
        
        # Check if user exists
        existing = get_user_by_id(user_id)
        if not existing:
            return _error_response("User not found", 404)
        
        # Update user
        updated = update_user(user_id, data)
        return _success_response(updated, "User updated successfully")
    
    except Exception as e:
        return _error_response(str(e))