from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
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
    
    @abstractmethod
    def delete_transcript(self, lesson_id: str, series_id: str) -> bool:
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
            "createdAt": datetime.now(timezone.utc),
            "updatedAt": datetime.now(timezone.utc)
        }
        
        result = lesson_col.insert_one(new_lesson)
        lesson_id = result.inserted_id
        
        from bson import ObjectId
        series_col.update_one(
            {"_id": ObjectId(data.get("lesson_serie"))},
            {"$push": {"serie_lessons": lesson_id}}
        )
        
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
        
        data["updatedAt"] = datetime.now(timezone.utc)
        
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

        updated_docs = [d for d in docs if d != doc_url]
        lesson_col.update_one(
            {"_id": ObjectId(lesson_id), "lesson_serie": series_id},
            {"$set": {"lesson_documents": updated_docs, "updatedAt": datetime.now(timezone.utc)}}
        )
        
        return True
    
    def delete_transcript(self, lesson_id: str, series_id: str) -> bool:
        from bson import ObjectId
        lesson_col = self._lessons_collection()
        
        lesson = lesson_col.find_one({
            "_id": ObjectId(lesson_id),
            "lesson_serie": series_id
        })
        
        if not lesson:
            raise ValueError("Lesson không tồn tại.")
        
        if not lesson.get("lesson_transcript"):
            raise ValueError("Transcript không tồn tại trong lesson.")
        
        lesson_col.update_one(
            {"_id": ObjectId(lesson_id), "lesson_serie": series_id},
            {"$set": {"lesson_transcript": "", "transcript_status": None, "updatedAt": datetime.now(timezone.utc)}}
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
    
    def _process_documents(self, files, user_id: str) -> List[str]:
        """Process document files only"""
        document_urls = []
        
        if not files:
            return document_urls
        
        docs = files.getlist("lesson_documents") if hasattr(files, 'getlist') else None
        if docs:
            document_urls = self._media_client.upload_documents_batch(docs, user_id)
        
        return document_urls
    
    def create_lesson(
        self,
        data: Dict[str, Any],
        user_id: str,
        id_token: str = None,
        files=None
    ) -> Dict[str, Any]:
        """
        Create lesson với flow:
        1. Upload documents (sync)
        2. Create lesson trong DB (để có lesson_id)
        3. Upload video qua Media Service (transcript chạy background ở đó)
        4. Update lesson với video URL
        5. Return response ngay
        """
        # Step 1: Upload documents
        document_urls = self._process_documents(files, user_id)
        
        # Prepare lesson data (chưa có video/transcript)
        data["lesson_video"] = ""
        data["lesson_transcript"] = ""
        data["transcript_status"] = "pending"
        data["lesson_documents"] = document_urls
        
        # Step 2: Create lesson để có lesson_id
        created_lesson = self._repository.create(data)
        lesson_id = created_lesson["_id"]
        series_id = data.get("lesson_serie")
        
        # Step 3: Upload video qua Media Service
        if files:
            video_list = files.getlist("lesson_video") if hasattr(files, 'getlist') else None
            if video_list and len(video_list) > 0:
                video_file = video_list[0]
                
                # Gọi Media Service với lesson_id, series_id
                # Media Service sẽ chạy background task và update DB sau
                video_result = self._media_client.upload_video(
                    file=video_file,
                    user_id=user_id,
                    lesson_id=lesson_id,
                    series_id=series_id,
                    create_transcript=True
                )
                
                # Step 4: Update lesson với video URL ngay
                if video_result and video_result.get("url"):
                    self._repository.update(lesson_id, series_id, {
                        "lesson_video": video_result["url"],
                        "transcript_status": video_result.get("transcript_status", "processing")
                    })
                    created_lesson["lesson_video"] = video_result["url"]
                    created_lesson["transcript_status"] = video_result.get("transcript_status", "processing")
        
        return created_lesson
    
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
        current = self._repository.find_by_id(lesson_id, series_id)
        if not current:
            return None
        
        # Handle video replacement
        if files:
            video_list = files.getlist("lesson_video") if hasattr(files, 'getlist') else None
            if video_list and len(video_list) > 0:
                video_file = video_list[0]
                
                # Delete old video & transcript
                old_video = current.get("lesson_video")
                if old_video:
                    self._media_client.delete_file(old_video)
                
                old_transcript = current.get("lesson_transcript")
                if old_transcript:
                    self._media_client.delete_file(old_transcript)
                
                # Upload new video
                video_result = self._media_client.upload_video(
                    file=video_file,
                    user_id=user_id,
                    lesson_id=lesson_id,
                    series_id=series_id,
                    create_transcript=True
                )
                
                if video_result and video_result.get("url"):
                    data["lesson_video"] = video_result["url"]
                    data["lesson_transcript"] = ""
                    data["transcript_status"] = video_result.get("transcript_status", "processing")
        
        # Handle documents replacement
        if files:
            doc_list = files.getlist("lesson_documents") if hasattr(files, 'getlist') else None
            if doc_list and len(doc_list) > 0:
                # Delete old documents
                old_docs = current.get("lesson_documents", [])
                if old_docs:
                    self._media_client.delete_files_batch(old_docs)
                
                # Upload new documents
                new_doc_urls = self._media_client.upload_documents_batch(doc_list, user_id)
                if new_doc_urls:
                    data["lesson_documents"] = new_doc_urls
        
        return self._repository.update(lesson_id, series_id, data)
    
    def delete_lesson(self, series_id: str, lesson_id: str) -> bool:
        lesson = self._repository.find_by_id(lesson_id, series_id)
        
        result = self._repository.delete(lesson_id, series_id)
        
        if result and lesson:
            if lesson.get("lesson_video"):
                self._media_client.delete_file(lesson.get("lesson_video"))
            
            if lesson.get("lesson_transcript"):
                self._media_client.delete_file(lesson.get("lesson_transcript"))
            
            docs = lesson.get("lesson_documents")
            if docs:
                if isinstance(docs, list):
                    self._media_client.delete_files_batch(docs)
                else:
                    self._media_client.delete_file(docs)
        
        return result
    
    def delete_document_by_url(self, series_id: str, lesson_id: str, doc_url: str) -> bool:
        result = self._repository.delete_document(lesson_id, series_id, doc_url)
        
        if result:
            self._media_client.delete_file(doc_url)
        
        return result
    
    def delete_transcript(self, series_id: str, lesson_id: str) -> bool:
        lesson = self._repository.find_by_id(lesson_id, series_id)
        if not lesson:
            raise ValueError("Lesson không tồn tại.")
        
        transcript_url = lesson.get("lesson_transcript")
        
        result = self._repository.delete_transcript(lesson_id, series_id)
        
        if result and transcript_url:
            self._media_client.delete_file(transcript_url)
        
        return result


# Public API
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

def delete_transcript(series_id, lesson_id):
    return _service.delete_transcript(series_id, lesson_id)