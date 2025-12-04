from typing import Optional, Dict, Any, List
from bson import ObjectId
from app.utils.mongodb import get_database
from app.utils.sns import publish_to_topic
from app.clients.media_client import MediaServiceClient

class LessonService:
    
    def __init__(self):
        self._media_client = MediaServiceClient()

    async def _lessons_collection(self):
        db = await get_database()
        return db["lessons"]

    async def _series_collection(self):
        db = await get_database()
        return db["series"]
    
    async def get_lesson_by_id(self, series_id: str, lesson_id: str) -> Optional[Dict[str, Any]]:
        if not ObjectId.is_valid(lesson_id):
            return None
        collection = await self._lessons_collection()
        return await collection.find_one({
            "_id": ObjectId(lesson_id),
            "lesson_serie": series_id
        })
    
    async def get_all_lessons_by_serie(self, series_id: str) -> List[Dict[str, Any]]:
        collection = await self._lessons_collection()
        cursor = collection.find({"lesson_serie": series_id})
        return await cursor.to_list(length=None)
    
    async def create_lesson(self, data: Dict[str, Any], user_id: str, 
                            video_file: tuple = None, doc_files: List[tuple] = None) -> Dict[str, Any]:
        
        # Upload Video
        video_url = ""
        if video_file:
            content, filename, ctype = video_file
            video_url = await self._media_client.upload_video(content, filename, ctype, user_id)
            
        # Upload Docs
        doc_urls = []
        if doc_files:
            for d_file in doc_files:
                content, filename, ctype = d_file
                url = await self._media_client.upload_document(content, filename, ctype, user_id)
                if url:
                    doc_urls.append(url)
        
        data["lesson_video"] = video_url
        data["lesson_documents"] = doc_urls
        data["createdAt"] = None
        data["updatedAt"] = None
        
        lesson_col = await self._lessons_collection()
        series_col = await self._series_collection()
        
        result = await lesson_col.insert_one(data)
        lesson_id = result.inserted_id
        
        # Push to series
        await series_col.update_one(
            {"_id": ObjectId(data.get("lesson_serie"))},
            {"$push": {"serie_lessons": lesson_id}}
        )
        
        # SNS Notification
        serie = await series_col.find_one({"_id": ObjectId(data.get("lesson_serie"))})
        if serie and serie.get("serie_sns"):
            msg = f"Bài học mới '{data.get('lesson_title')}' đã được thêm vào series."
            publish_to_topic(serie.get("serie_sns"), "New Lesson Alert", msg)
            
        return {"_id": str(lesson_id), **data}
    
    async def update_lesson(self, series_id: str, lesson_id: str, data: Dict[str, Any], user_id: str = None,
                           video_file: tuple = None, doc_files: List[tuple] = None) -> Optional[Dict[str, Any]]:
        
        if not ObjectId.is_valid(lesson_id):
            return None
            
        lesson_col = await self._lessons_collection()
        current = await lesson_col.find_one({"_id": ObjectId(lesson_id), "lesson_serie": series_id})
        if not current:
            return None
            
        if video_file:
            content, filename, ctype = video_file
            if current.get("lesson_video"):
                await self._media_client.delete_file(current.get("lesson_video"))
            new_vid = await self._media_client.upload_video(content, filename, ctype, user_id)
            data["lesson_video"] = new_vid

        if doc_files:
            old_docs = current.get("lesson_documents", [])
            if old_docs:
                await self._media_client.delete_files_batch(old_docs)
            
            new_urls = []
            for d_file in doc_files:
                 content, filename, ctype = d_file
                 url = await self._media_client.upload_document(content, filename, ctype, user_id)
                 if url: new_urls.append(url)
            data["lesson_documents"] = new_urls
            
        data["updatedAt"] = None
        
        await lesson_col.update_one(
            {"_id": ObjectId(lesson_id)},
            {"$set": data}
        )
        return await lesson_col.find_one({"_id": ObjectId(lesson_id)})

    async def delete_lesson(self, series_id: str, lesson_id: str) -> bool:
        if not ObjectId.is_valid(lesson_id):
            return False
            
        lesson_col = await self._lessons_collection()
        series_col = await self._series_collection()
        
        lesson = await lesson_col.find_one({"_id": ObjectId(lesson_id), "lesson_serie": series_id})
        if not lesson:
            return False
            
        if lesson.get("lesson_video"):
            await self._media_client.delete_file(lesson.get("lesson_video"))
        if lesson.get("lesson_documents"):
            await self._media_client.delete_files_batch(lesson.get("lesson_documents"))
            
        result = await lesson_col.delete_one({"_id": ObjectId(lesson_id)})
        
        if result.deleted_count > 0:
            await series_col.update_one(
                {"_id": ObjectId(series_id)},
                {"$pull": {"serie_lessons": ObjectId(lesson_id)}}
            )
            return True
        return False
    
    async def delete_document_by_url(self, series_id: str, lesson_id: str, doc_url: str) -> bool:
        if not ObjectId.is_valid(lesson_id):
            return False
            
        lesson_col = await self._lessons_collection()
        lesson = await lesson_col.find_one({"_id": ObjectId(lesson_id), "lesson_serie": series_id})
        
        if not lesson:
             return False
             
        docs = lesson.get("lesson_documents", [])
        if doc_url not in docs:
             return False
             
        updated_docs = [d for d in docs if d != doc_url]
        await lesson_col.update_one(
            {"_id": ObjectId(lesson_id)},
            {"$set": {"lesson_documents": updated_docs}}
        )
        
        await self._media_client.delete_file(doc_url)
        return True

lesson_service = LessonService()