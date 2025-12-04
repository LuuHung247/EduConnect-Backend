from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List
from app.utils.mongodb import get_db
from app.utils.sns import publish_to_topic
from app.clients.media_client import MediaServiceClient


# 1. Interface Repository
class LessonRepository(ABC):
    """Interface cho Lesson Repository"""
    
    @abstractmethod
    def find_by_id(self, lesson_id: str, series_id: str) -> Optional[Dict[str, Any]]:
        pass
    
    @abstractmethod
    def find_by_serie(self, series_id: str) -> List[Dict[str, Any]]:
        pass
    
    @abstractmethod
    def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        pass
    
    @abstractmethod
    def update(self, lesson_id: str, series_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        pass
    
    @abstractmethod
    def delete(self, lesson_id: str, series_id: str) -> bool:
        pass
    
    @abstractmethod
    def delete_document(self, lesson_id: str, series_id: str, doc_url: str) -> bool:
        pass


# 2. Implementation: MongoDB
class MongoLessonRepository(LessonRepository):
    """MongoDB implementation"""
    
    def _lessons_collection(self):
        _, db = get_db()
        return db["lessons"]

    def _series_collection(self):
        _, db = get_db()
        return db["series"]
    
    def find_by_id(self, lesson_id: str, series_id: str) -> Optional[Dict[str, Any]]:
        from bson import ObjectId
        if not ObjectId.is_valid(lesson_id):
            return None
        return self._lessons_collection().find_one({
            "_id": ObjectId(lesson_id),
            "lesson_serie": series_id
        })
    
    def find_by_serie(self, series_id: str) -> List[Dict[str, Any]]:
        return list(self._lessons_collection().find({"lesson_serie": series_id}))
    
    def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        lesson_col = self._lessons_collection()
        series_col = self._series_collection()
        
        new_lesson = {
            **data,
            "createdAt": None,
            "updatedAt": None
        }
        
        result = lesson_col.insert_one(new_lesson)
        lesson_id = result.inserted_id
        
        # Push lesson id to series
        from bson import ObjectId
        series_col.update_one(
            {"_id": ObjectId(data.get("lesson_serie"))},
            {"$push": {"serie_lessons": lesson_id}}
        )
        
        # Get serie for SNS notification
        serie = series_col.find_one({"_id": ObjectId(data.get("lesson_serie"))})
        
        if serie and serie.get("serie_sns"):
            custom_message = (
                f"Bài học mới \"{new_lesson.get('lesson_title')}\" "
                f"đã được thêm vào series \"{serie.get('serie_title', '')}\". "
                f"Truy cập ngay để xem nội dung!"
            )
            publish_to_topic(
                serie.get("serie_sns"),
                f"New Lesson in \"{serie.get('serie_title')}\"",
                custom_message
            )
        
        return {"_id": str(lesson_id), **new_lesson}
    
    def update(self, lesson_id: str, series_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        from bson import ObjectId
        lesson_col = self._lessons_collection()
        
        data["updatedAt"] = None
        
        res = lesson_col.update_one(
            {"_id": ObjectId(lesson_id), "lesson_serie": series_id},
            {"$set": data}
        )
        
        if res.matched_count == 0:
            return None
        
        return lesson_col.find_one({"_id": ObjectId(lesson_id)})
    
    def delete(self, lesson_id: str, series_id: str) -> bool:
        from bson import ObjectId
        lesson_col = self._lessons_collection()
        series_col = self._series_collection()
        
        lesson = lesson_col.find_one({
            "_id": ObjectId(lesson_id),
            "lesson_serie": series_id
        })
        
        if not lesson:
            raise ValueError("Lesson không tồn tại.")
        
        result = lesson_col.delete_one({
            "_id": ObjectId(lesson_id),
            "lesson_serie": series_id
        })
        
        if result.deleted_count > 0:
            # Remove from series
            series_col.update_one(
                {"_id": ObjectId(series_id)},
                {"$pull": {"serie_lessons": ObjectId(lesson_id)}}
            )
        
        return result.deleted_count > 0
    
    def delete_document(self, lesson_id: str, series_id: str, doc_url: str) -> bool:
        from bson import ObjectId
        lesson_col = self._lessons_collection()
        
        lesson = lesson_col.find_one({
            "_id": ObjectId(lesson_id),
            "lesson_serie": series_id
        })
        
        if not lesson:
            raise ValueError("Lesson không tồn tại.")
        
        docs = lesson.get("lesson_documents", [])
        if doc_url not in docs:
            raise ValueError("Document URL không tồn tại trong lesson.")

        # Update lesson (remove document from list)
        updated_docs = [d for d in docs if d != doc_url]
        lesson_col.update_one(
            {"_id": ObjectId(lesson_id), "lesson_serie": series_id},
            {"$set": {"lesson_documents": updated_docs, "updatedAt": None}}
        )
        
        return True


# 3. Service
class LessonService:
    """Service quản lý lesson - Gọi Media Service qua HTTP"""
    
    def __init__(
        self, 
        repository: Optional[LessonRepository] = None,
        media_client: Optional[MediaServiceClient] = None
    ):
        self._repository = repository or MongoLessonRepository()
        self._media_client = media_client or MediaServiceClient()
    
    def _process_files(self, files, user_id: str) -> tuple[str, List[str]]:
        """Process video and document files using Media Service"""
        video_url = ""
        document_urls = []
        
        if not files:
            return video_url, document_urls
        
        # Process video
        video = files.get("lesson_video") if hasattr(files, 'get') else None
        if video:
            video_file = video[0] if isinstance(video, (list, tuple)) else video
            video_url = self._media_client.upload_video(video_file, user_id)
            if not video_url:
                print("Warning: Failed to upload video")
                video_url = ""
        
        # Process documents
        docs = files.get("lesson_documents") if hasattr(files, 'get') else None
        if docs:
            doc_files = docs if isinstance(docs, (list, tuple)) else [docs]
            document_urls = self._media_client.upload_documents_batch(doc_files, user_id)
        
        return video_url, document_urls
    
    def create_lesson(
        self,
        data: Dict[str, Any],
        user_id: str,
        id_token: str = None,
        files=None
    ) -> Dict[str, Any]:
        # Upload media files qua Media Service
        video_url, document_urls = self._process_files(files, user_id)
        
        data["lesson_video"] = video_url
        data["lesson_documents"] = document_urls
        
        return self._repository.create(data)
    
    def get_all_lessons_by_serie(self, series_id: str) -> List[Dict[str, Any]]:
        return self._repository.find_by_serie(series_id)
    
    def get_lesson_by_id(self, series_id: str, lesson_id: str) -> Optional[Dict[str, Any]]:
        return self._repository.find_by_id(lesson_id, series_id)
    
    def update_lesson(
        self,
        series_id: str,
        lesson_id: str,
        data: Dict[str, Any],
        user_id: str = None,
        id_token: str = None,
        files=None
    ) -> Optional[Dict[str, Any]]:
        # Get current lesson to handle file deletions
        current = self._repository.find_by_id(lesson_id, series_id)
        if not current:
            return None
        
        # Handle video replacement qua Media Service
        if files and files.get("lesson_video"):
            video_file = files.get("lesson_video")
            if isinstance(video_file, (list, tuple)):
                video_file = video_file[0]
            
            # Delete old video
            old_video = current.get("lesson_video")
            if old_video:
                self._media_client.delete_file(old_video)
            
            # Upload new video
            new_video_url = self._media_client.upload_video(video_file, user_id)
            if new_video_url:
                data["lesson_video"] = new_video_url
        
        # Handle documents replacement qua Media Service
        if files and files.get("lesson_documents"):
            doc_files = files.get("lesson_documents")
            
            # Delete old documents
            old_docs = current.get("lesson_documents", [])
            if old_docs:
                self._media_client.delete_files_batch(old_docs)
            
            # Upload new documents
            new_doc_urls = self._media_client.upload_documents_batch(doc_files, user_id)
            if new_doc_urls:
                data["lesson_documents"] = new_doc_urls
        
        return self._repository.update(lesson_id, series_id, data)
    
    def delete_lesson(self, series_id: str, lesson_id: str) -> bool:
        # Get lesson to delete media files
        lesson = self._repository.find_by_id(lesson_id, series_id)
        
        # Delete from repository first
        result = self._repository.delete(lesson_id, series_id)
        
        if result and lesson:
            # Delete video qua Media Service
            if lesson.get("lesson_video"):
                self._media_client.delete_file(lesson.get("lesson_video"))
            
            # Delete documents qua Media Service
            docs = lesson.get("lesson_documents")
            if docs:
                if isinstance(docs, list):
                    self._media_client.delete_files_batch(docs)
                else:
                    self._media_client.delete_file(docs)
        
        return result
    
    def delete_document_by_url(self, series_id: str, lesson_id: str, doc_url: str) -> bool:
        # First update the repository (remove from DB)
        result = self._repository.delete_document(lesson_id, series_id, doc_url)
        
        # Then delete from storage qua Media Service
        if result:
            self._media_client.delete_file(doc_url)
        
        return result


# Public API - backward compatibility
_service = LessonService()

def create_lesson(data, user_id=None, id_token=None, files=None):
    return _service.create_lesson(data, user_id, id_token, files)

def get_all_lessons_by_serie(series_id):
    return _service.get_all_lessons_by_serie(series_id)

def get_lesson_by_id(series_id, lesson_id):
    return _service.get_lesson_by_id(series_id, lesson_id)

def update_lesson(series_id, lesson_id, data, user_id=None, id_token=None, files=None):
    return _service.update_lesson(series_id, lesson_id, data, user_id, id_token, files)

def delete_lesson(series_id, lesson_id):
    return _service.delete_lesson(series_id, lesson_id)

def delete_document_by_url(series_id, lesson_id, doc_url):
    return _service.delete_document_by_url(series_id, lesson_id, doc_url)