from abc import ABC, abstractmethod
from uuid import uuid4
from typing import Optional, Dict, Any, List
from app.utils.mongodb import get_db
from app.utils.s3 import  upload_to_s3, delete_from_s3
from app.utils.sns import publish_to_topic


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
            
            # Delete video
            if lesson.get("lesson_video"):
                delete_from_s3(lesson.get("lesson_video"))
            
            # Delete documents
            if isinstance(lesson.get("lesson_documents"), list):
                for doc in lesson.get("lesson_documents"):
                    delete_from_s3(doc)
            elif lesson.get("lesson_documents"):
                delete_from_s3(lesson.get("lesson_documents"))
        
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

        # Delete file from S3
        delete_from_s3(doc_url)

        # Update lesson
        updated_docs = [d for d in docs if d != doc_url]
        lesson_col.update_one(
            {"_id": ObjectId(lesson_id), "lesson_serie": series_id},
            {"$set": {"lesson_documents": updated_docs, "updatedAt": None}}
        )
        
        return True


# 3. Service
class LessonService:
    """Service quản lý lesson"""
    
    def __init__(self, repository: Optional[LessonRepository] = None):
        self._repository = repository or MongoLessonRepository()
    
    def _process_files(self, files, user_id: str, id_token: str) -> tuple[str, List[str]]:
        """Process video and document files"""
        video_url = ""
        document_urls = []
        
        if not files:
            return video_url, document_urls
        
        # Process video
        video = files.get("lesson_video") if hasattr(files, 'get') else None
        if video:
            vf = video[0] if isinstance(video, (list, tuple)) else video
            buffer = vf.read()
            filename = getattr(vf, 'filename', 'video')
            mimetype = getattr(vf, 'mimetype', None)
            video_url = upload_to_s3(
                buffer, f"{uuid4()}_{filename}",
                mimetype, f"files/user-{user_id}/videos"
            )
        
        # Process documents
        docs = files.get("lesson_documents") if hasattr(files, 'get') else None
        if docs:
            doc_files = docs if isinstance(docs, (list, tuple)) else [docs]
            for doc in doc_files:
                buf = doc.read()
                filename = getattr(doc, 'filename', 'doc')
                mimetype = getattr(doc, 'mimetype', None)
                doc_url = upload_to_s3(
                    buf, f"{uuid4()}_{filename}",
                    mimetype, f"files/user-{user_id}/docs"
                )
                document_urls.append(doc_url)
        
        return video_url, document_urls
    
    def create_lesson(
        self,
        data: Dict[str, Any],
        user_id: str,
        id_token: str = None,
        files=None
    ) -> Dict[str, Any]:
        video_url, document_urls = self._process_files(files, user_id, id_token)
        
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
        
        # Handle video replacement
        if files and files.get("lesson_video"):
            if current.get("lesson_video"):
                delete_from_s3(current.get("lesson_video"))
            
            vf = files.get("lesson_video")[0]
            buf = vf.read()
            filename = getattr(vf, 'filename', 'video')
            mimetype = getattr(vf, 'mimetype', None)
            data["lesson_video"] = upload_to_s3(
                buf, f"{uuid4()}_{filename}",
                mimetype, f"files/user-{user_id}/videos"
            )
        
        # Handle documents replacement
        if files and files.get("lesson_documents"):
            if current.get("lesson_documents"):
                for doc_url in current.get("lesson_documents"):
                    delete_from_s3(doc_url)

            doc_urls = []
            for df in files.get("lesson_documents"):
                buf = df.read()
                filename = getattr(df, 'filename', 'doc')
                mimetype = getattr(df, 'mimetype', None)
                doc_url = upload_to_s3(
                    buf, f"{uuid4()}_{filename}",
                    mimetype, f"files/user-{user_id}/docs"
                )
                doc_urls.append(doc_url)
            data["lesson_documents"] = doc_urls
        
        return self._repository.update(lesson_id, series_id, data)
    
    def delete_lesson(self, series_id: str, lesson_id: str) -> bool:
        return self._repository.delete(lesson_id, series_id)
    
    def delete_document_by_url(self, series_id: str, lesson_id: str, doc_url: str) -> bool:
        return self._repository.delete_document(lesson_id, series_id, doc_url)


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