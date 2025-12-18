"""
Tracking Blueprint - Handle user lesson tracking directly in backend
Replaces the tracking service microservice with built-in functionality
"""
from flask import Blueprint, request, jsonify
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict
from app.services.lesson_service import LessonService
from app.utils.mongodb import get_db
import logging

logger = logging.getLogger(__name__)

bp = Blueprint("tracking", __name__, url_prefix="/api/v1/tracking")

# Lazy init - will be initialized on first request
_db = None
_tracking_collection = None
_lesson_service = None
_indexes_created = False


def _get_tracking_collection():
    """Lazy init MongoDB connection"""
    global _db, _tracking_collection, _lesson_service, _indexes_created

    if _tracking_collection is None:
        _, _db = get_db()
        _tracking_collection = _db["current_lesson_tracking"]
        _lesson_service = LessonService()

        # Create indexes on first access
        if not _indexes_created:
            try:
                _tracking_collection.create_index("user_id", unique=True)
                logger.info("Tracking indexes created successfully")
                _indexes_created = True
            except Exception as e:
                logger.warning(f"Error creating tracking indexes: {e}")

    return _tracking_collection, _lesson_service


def _cleanup_stale_tabs(user_id: str, stale_minutes: int = 30) -> None:
    """Remove tabs that haven't been active for more than stale_minutes"""
    tracking_collection, _ = _get_tracking_collection()

    try:
        tracking = tracking_collection.find_one({"user_id": user_id})
        if not tracking:
            return

        now = datetime.now(timezone.utc)
        active_lessons = tracking.get("active_lessons", [])
        stale_threshold = now - timedelta(minutes=stale_minutes)

        fresh_lessons = []
        removed_count = 0

        for lesson in active_lessons:
            last_active = lesson.get("last_active")
            if last_active is None or last_active > stale_threshold:
                fresh_lessons.append(lesson)
            else:
                removed_count += 1

        if removed_count > 0:
            if len(fresh_lessons) == 0:
                tracking_collection.delete_one({"user_id": user_id})
                logger.info(f"Cleaned up all stale tabs for user {user_id}")
            else:
                most_recent = max(fresh_lessons, key=lambda x: x.get("last_active", datetime.min.replace(tzinfo=timezone.utc)))
                tracking_collection.update_one(
                    {"user_id": user_id},
                    {"$set": {
                        "active_lessons": fresh_lessons,
                        "current_lesson": most_recent,
                        "last_updated": now
                    }}
                )
    except Exception as e:
        logger.error(f"Error cleaning up stale tabs: {e}")


@bp.route('/lesson/enter', methods=['POST'])
def enter_lesson():
    """
    Add/update lesson for a browser tab when user enters a lesson page
    Request body: {user_id, lesson_id, serie_id, tab_id, lesson_title (optional)}
    """
    tracking_collection, _ = _get_tracking_collection()

    try:
        data = request.get_json()
        user_id = data.get('user_id')
        lesson_id = data.get('lesson_id')
        serie_id = data.get('serie_id')
        tab_id = data.get('tab_id')
        lesson_title = data.get('lesson_title')

        if not all([user_id, lesson_id, serie_id, tab_id]):
            return jsonify({"success": False, "message": "Missing required fields"}), 400

        # Cleanup stale tabs
        _cleanup_stale_tabs(user_id, stale_minutes=30)

        now = datetime.now(timezone.utc)
        new_lesson = {
            "lesson_id": lesson_id,
            "serie_id": serie_id,
            "lesson_title": lesson_title,
            "tab_id": tab_id,
            "last_active": now
        }

        tracking = tracking_collection.find_one({"user_id": user_id})

        if tracking:
            active_lessons = tracking.get("active_lessons", [])
            # Remove old entry for this tab
            active_lessons = [l for l in active_lessons if l.get("tab_id") != tab_id]
            active_lessons.append(new_lesson)

            tracking_collection.update_one(
                {"user_id": user_id},
                {"$set": {
                    "active_lessons": active_lessons,
                    "current_lesson": new_lesson,
                    "last_updated": now
                }}
            )
        else:
            tracking_collection.insert_one({
                "user_id": user_id,
                "active_lessons": [new_lesson],
                "current_lesson": new_lesson,
                "last_updated": now
            })

        logger.info(f"Set current lesson for user {user_id} tab {tab_id}: {lesson_id}")

        return jsonify({
            "success": True,
            "message": "Current lesson set successfully",
            "data": {
                "user_id": user_id,
                "lesson_id": lesson_id,
                "serie_id": serie_id,
                "lesson_title": lesson_title,
                "tab_id": tab_id
            }
        })

    except Exception as e:
        logger.error(f"Error entering lesson: {e}")
        return jsonify({"success": False, "message": str(e)}), 500


@bp.route('/lesson/exit', methods=['POST'])
def exit_lesson():
    """
    Remove lesson from a specific browser tab when user exits/closes tab
    Request body: {user_id, tab_id}
    """
    tracking_collection, _ = _get_tracking_collection()

    try:
        data = request.get_json()
        user_id = data.get('user_id')
        tab_id = data.get('tab_id')

        if not all([user_id, tab_id]):
            return jsonify({"success": False, "message": "Missing required fields"}), 400

        tracking = tracking_collection.find_one({"user_id": user_id})

        if not tracking:
            return jsonify({"success": True, "message": "No tracking data found"})

        active_lessons = tracking.get("active_lessons", [])
        active_lessons = [l for l in active_lessons if l.get("tab_id") != tab_id]

        if len(active_lessons) == 0:
            tracking_collection.delete_one({"user_id": user_id})
            logger.info(f"Cleared all lessons for user {user_id}")
            return jsonify({"success": True, "message": "All lessons cleared"})
        else:
            most_recent = max(active_lessons, key=lambda x: x.get("last_active", datetime.min.replace(tzinfo=timezone.utc)))
            tracking_collection.update_one(
                {"user_id": user_id},
                {"$set": {
                    "active_lessons": active_lessons,
                    "current_lesson": most_recent,
                    "last_updated": datetime.now(timezone.utc)
                }}
            )
            logger.info(f"Cleared lesson for user {user_id} tab {tab_id}")
            return jsonify({"success": True, "message": f"Lesson cleared, {len(active_lessons)} tabs remaining"})

    except Exception as e:
        logger.error(f"Error exiting lesson: {e}")
        return jsonify({"success": False, "message": str(e)}), 500


@bp.route('/lesson/focus', methods=['POST'])
def update_lesson_focus():
    """
    Update which browser tab is currently focused
    Request body: {user_id, tab_id}
    """
    tracking_collection, _ = _get_tracking_collection()

    try:
        data = request.get_json()
        user_id = data.get('user_id')
        tab_id = data.get('tab_id')

        if not all([user_id, tab_id]):
            return jsonify({"success": False, "message": "Missing required fields"}), 400

        now = datetime.now(timezone.utc)
        tracking = tracking_collection.find_one({"user_id": user_id})

        if not tracking:
            return jsonify({"success": False, "message": "No tracking data found for user"}), 404

        active_lessons = tracking.get("active_lessons", [])
        focused_lesson = None

        for lesson in active_lessons:
            if lesson.get("tab_id") == tab_id:
                lesson["last_active"] = now
                focused_lesson = lesson
                break

        if not focused_lesson:
            return jsonify({"success": False, "message": "Tab not found in active lessons"}), 404

        tracking_collection.update_one(
            {"user_id": user_id},
            {"$set": {
                "active_lessons": active_lessons,
                "current_lesson": focused_lesson,
                "last_updated": now
            }}
        )

        logger.info(f"Updated focus for user {user_id} to tab {tab_id}")

        return jsonify({
            "success": True,
            "message": "Focus updated successfully",
            "data": focused_lesson
        })

    except Exception as e:
        logger.error(f"Error updating focus: {e}")
        return jsonify({"success": False, "message": str(e)}), 500


@bp.route('/user/<user_id>/current', methods=['GET'])
def get_current_lesson(user_id: str):
    """
    Get user's current lesson (focused tab) with full lesson details for AI chatbot
    Returns tracking info + enriched lesson data from MongoDB
    """
    tracking_collection, lesson_service = _get_tracking_collection()

    try:
        tracking = tracking_collection.find_one({"user_id": user_id})

        if not tracking or not tracking.get("current_lesson"):
            return jsonify({
                "user_id": user_id,
                "is_in_lesson": False,
                "active_lessons": [],
                "total_active_tabs": 0
            })

        current = tracking["current_lesson"]
        active_lessons = tracking.get("active_lessons", [])

        # Convert datetime objects to ISO strings
        active_lessons_serializable = []
        for lesson in active_lessons:
            lesson_copy = lesson.copy()
            if isinstance(lesson_copy.get("last_active"), datetime):
                lesson_copy["last_active"] = lesson_copy["last_active"].isoformat()
            active_lessons_serializable.append(lesson_copy)

        result = {
            "user_id": tracking["user_id"],
            "lesson_id": current.get("lesson_id"),
            "serie_id": current.get("serie_id"),
            "lesson_title": current.get("lesson_title"),
            "last_updated": tracking.get("last_updated"),
            "is_in_lesson": True,
            "active_lessons": active_lessons_serializable,
            "total_active_tabs": len(active_lessons)
        }

        # Fetch full lesson details from database for AI chatbot context
        lesson_id = current.get("lesson_id")
        serie_id = current.get("serie_id")

        if lesson_id and serie_id:
            # Use LessonService to get lesson details
            lesson_details = lesson_service.get_lesson_by_id(serie_id, lesson_id)
            if lesson_details:
                result["lesson_data"] = {
                    "lesson_title": lesson_details.get("lesson_title"),
                    "lesson_description": lesson_details.get("lesson_description"),
                    "lesson_serie": lesson_details.get("lesson_serie"),
                    "lesson_video": lesson_details.get("lesson_video"),
                    "lesson_transcript": lesson_details.get("lesson_transcript"),
                    "transcript_status": lesson_details.get("transcript_status"),
                    "lesson_documents": lesson_details.get("lesson_documents", []),
                    "createdAt": lesson_details.get("createdAt"),
                    "updatedAt": lesson_details.get("updatedAt"),
                    "lesson_summary": lesson_details.get("lesson_summary"),
                    "lesson_timeline": lesson_details.get("lesson_timeline")
                }
                logger.info(f"Enriched tracking response with lesson details for {lesson_id}")

        return jsonify(result)

    except Exception as e:
        logger.error(f"Error getting current lesson: {e}")
        return jsonify({"error": str(e)}), 500
