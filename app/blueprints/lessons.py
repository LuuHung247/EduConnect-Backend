from flask import Blueprint, request, g, Response
from app.middleware.auth import authenticate_jwt
from app.services.lesson_service import (
    create_lesson,
    get_all_lessons_by_serie,
    get_lesson_by_id,
    update_lesson,
    delete_lesson,
    delete_document_by_url,
)
import json
from app.utils.json_encoder import JSONEncoder
from app.utils.cache import (
    cached_with_user,
    invalidate_lessons_cache,
)

bp = Blueprint("lessons", __name__, url_prefix="/api/v1/series/<series_id>/lessons")


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
def create_lesson_route(series_id):
    """Create a new lesson in a series"""
    try:
        data = dict(request.form) if request.form else (request.get_json() or {})
        data["lesson_serie"] = series_id
        
        files = request.files if request.files else None
        user_id = g.user.get("userId")
        id_token = g.user.get("idToken")
        
        lesson = create_lesson(data, user_id, id_token, files)
        
        # Invalidate cache
        invalidate_lessons_cache(series_id)
        
        return _success_response(lesson, "Lesson created successfully", 201)
    
    except Exception as e:
        return _error_response(str(e))


@bp.route("", methods=["GET"], strict_slashes=False)
@authenticate_jwt
@cached_with_user(timeout=300)  # Cache 5 phút, per user (ETag included)
def list_lessons(series_id):
    """List all lessons in a series"""
    try:
        lessons = get_all_lessons_by_serie(series_id)
        return _success_response(lessons)
    
    except Exception as e:
        return _error_response(str(e))


@bp.route("/<lesson_id>", methods=["GET"])
@authenticate_jwt
@cached_with_user(timeout=300)  # Cache 5 phút, per user (ETag included)
def get_lesson_detail(series_id, lesson_id):
    """Get lesson details by ID"""
    try:
        lesson = get_lesson_by_id(series_id, lesson_id)
        
        if not lesson:
            return _error_response("Lesson not found", 404)
        
        return _success_response(lesson)
    
    except Exception as e:
        return _error_response(str(e))


@bp.route("/<lesson_id>", methods=["PATCH"])
@authenticate_jwt
def update_lesson_route(series_id, lesson_id):
    """Update lesson information"""
    try:
        data = dict(request.form) if request.form else (request.get_json() or {})
        files = request.files if request.files else None
        
        user_id = g.user.get("userId")
        id_token = g.user.get("idToken")
        
        updated = update_lesson(series_id, lesson_id, data, user_id, id_token, files)
        
        if not updated:
            return _error_response("Lesson not found", 404)
        
        # Invalidate cache
        invalidate_lessons_cache(series_id, lesson_id)
        
        return _success_response(updated, "Lesson updated successfully")
    
    except Exception as e:
        return _error_response(str(e))


@bp.route("/<lesson_id>", methods=["DELETE"])
@authenticate_jwt
def delete_lesson_route(series_id, lesson_id):
    """Delete a lesson"""
    try:
        deleted = delete_lesson(series_id, lesson_id)
        
        if not deleted:
            return _error_response("Lesson not found", 404)
        
        # Invalidate cache
        invalidate_lessons_cache(series_id, lesson_id)
        
        return _success_response(None, "Lesson deleted successfully")
    
    except ValueError as e:
        return _error_response(str(e), 404)
    except Exception as e:
        return _error_response(str(e))


@bp.route("/<lesson_id>/documents", methods=["DELETE"])
@authenticate_jwt
def delete_document_route(series_id, lesson_id):
    """Delete a document from a lesson"""
    try:
        data = request.get_json() or {}
        doc_url = data.get("docUrl")
        
        if not doc_url:
            return _error_response("docUrl is required", 400)
        
        delete_document_by_url(series_id, lesson_id, doc_url)
        
        # Invalidate cache
        invalidate_lessons_cache(series_id, lesson_id)
        
        return _success_response(None, "Document deleted successfully")
    
    except ValueError as e:
        error_msg = str(e)
        if "Lesson không tồn tại" in error_msg:
            return _error_response("Lesson not found", 404)
        if "Document URL không tồn tại" in error_msg:
            return _error_response("Document not found in lesson", 400)
        return _error_response(error_msg, 400)
    
    except Exception as e:
        return _error_response(str(e))