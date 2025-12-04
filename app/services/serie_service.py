from typing import Optional, Dict, Any, List
from bson import ObjectId

from app.utils.mongodb import get_database
from app.utils.sns import create_topic, delete_topic, subscribe_to_serie, unsubscribe_from_topic
from app.clients.media_client import MediaServiceClient

class SerieService:
    
    def __init__(self):
        self._media_client = MediaServiceClient()

    async def _series_collection(self):
        db = await get_database()
        return db["series"]
    
    async def _users_collection(self):
        db = await get_database()
        return db["users"]
    
    async def get_all_series(self, query: Optional[Dict] = None) -> List[Dict[str, Any]]:
        collection = await self._series_collection()
        q = dict(query) if query else {}
        cursor = collection.find(q)
        return await cursor.to_list(length=None)
    
    async def get_serie_by_id(self, serie_id: str) -> Optional[Dict[str, Any]]:
        if not ObjectId.is_valid(serie_id):
            return None
        collection = await self._series_collection()
        return await collection.find_one({"_id": ObjectId(serie_id)})
    
    async def create_serie(self, data: Dict, 
                           user_id: str, 
                           file_content: bytes = None, 
                           filename: str = None, 
                           content_type: str = None) -> Dict[str, Any]:
        thumbnail_url = ""
        if file_content:
            thumbnail_url = await self._media_client.upload_thumbnail(file_content, filename, content_type, user_id)
        
        data["serie_thumbnail"] = thumbnail_url
        data["serie_user"] = user_id
        
        is_publish_val = data.get("isPublish", False)
        if isinstance(is_publish_val, str):
            is_publish_val = is_publish_val.lower() == "true"
        
        new_serie = {
            **data,
            "isPublish": bool(is_publish_val),
            "serie_lessons": [],
            "createdAt": None,
            "updatedAt": None,
            "serie_subcribe_num": 0,
        }
        
        collection = await self._series_collection()
        result = await collection.insert_one(new_serie)
        inserted_id = str(result.inserted_id)
        
        topic_arn = create_topic(f"serie_{inserted_id}")
        await collection.update_one(
            {"_id": result.inserted_id},
            {"$set": {"serie_sns": topic_arn}}
        )
        
        return {"_id": inserted_id, **new_serie, "serie_sns": topic_arn}

    async def update_serie(self, serie_id: str, data: Dict, user_id: str = None, file_content: bytes = None, filename: str = None, content_type: str = None) -> Optional[Dict[str, Any]]:
        if not ObjectId.is_valid(serie_id):
            return None
        
        collection = await self._series_collection()
        
        if file_content:
            current = await collection.find_one({"_id": ObjectId(serie_id)})
            if current and current.get("serie_thumbnail"):
                await self._media_client.delete_file(current.get("serie_thumbnail"))
            
            new_url = await self._media_client.upload_thumbnail(file_content, filename, content_type, user_id)
            data["serie_thumbnail"] = new_url
        
        if "isPublish" in data and isinstance(data["isPublish"], str):
             data["isPublish"] = data["isPublish"].lower() == "true"

        data["updatedAt"] = None
        
        res = await collection.update_one(
            {"_id": ObjectId(serie_id)},
            {"$set": data}
        )
        
        if res.matched_count == 0:
            return None
        
        return await collection.find_one({"_id": ObjectId(serie_id)})

    async def delete_serie(self, serie_id: str) -> Dict[str, Any]:
        if not ObjectId.is_valid(serie_id):
            return {"success": False, "message": "Invalid ID"}
            
        serie_col = await self._series_collection()
        user_col = await self._users_collection()
        
        serie = await serie_col.find_one({"_id": ObjectId(serie_id)})
        if not serie:
             return {"success": False, "warning": "Serie not found"}
        
        if serie.get("serie_lessons") and len(serie.get("serie_lessons")) > 0:
            return {"success": False, "warning": "Không thể xóa serie khi vẫn còn bài học."}
        
        await user_col.update_many(
            {"serie_subcribe": serie_id},
            {"$pull": {"serie_subcribe": serie_id}, "$set": {"updatedAt": None}}
        )
        
        if serie.get("serie_sns"):
            delete_topic(serie.get("serie_sns"))
            
        if serie.get("serie_thumbnail"):
            await self._media_client.delete_file(serie.get("serie_thumbnail"))
            
        result = await serie_col.delete_one({"_id": ObjectId(serie_id)})
        return {"success": result.deleted_count > 0}

    async def subscribe_serie(self, serie_id: str, user_id: str, user_email: str) -> Dict[str, Any]:
        if not ObjectId.is_valid(serie_id):
             raise ValueError("Invalid Serie ID")
             
        serie_col = await self._series_collection()
        user_col = await self._users_collection()
        
        serie = await serie_col.find_one({"_id": ObjectId(serie_id)})
        if not serie:
             raise ValueError("Serie not found")
             
        user = await user_col.find_one({"_id": user_id})
        if not user:
             raise ValueError("User not found")
             
        if user.get("serie_subcribe") and serie_id in user.get("serie_subcribe"):
            return {"message": "Already subscribed", "alreadySubscribed": True}
            
        await user_col.update_one(
            {"_id": user_id},
            {"$addToSet": {"serie_subcribe": serie_id}}
        )
        await serie_col.update_one(
            {"_id": ObjectId(serie_id)},
            {"$inc": {"serie_subcribe_num": 1}}
        )
        
        # SNS Subscribe
        if serie.get("serie_sns"):
            subscribe_to_serie(serie.get("serie_sns"), user_email)
            
        return {"message": "Subscribed"}

    async def unsubscribe_serie(self, serie_id: str, user_id: str, user_email: str) -> Dict[str, Any]:
        if not ObjectId.is_valid(serie_id):
             raise ValueError("Invalid Serie ID")
             
        serie_col = await self._series_collection()
        user_col = await self._users_collection()
        
        serie = await serie_col.find_one({"_id": ObjectId(serie_id)})
        if not serie:
             raise ValueError("Serie not found")
             
        # SNS Unsubscribe
        if serie.get("serie_sns"):
            unsubscribe_from_topic(serie.get("serie_sns"), user_email)
            
        await user_col.update_one(
            {"_id": user_id},
            {"$pull": {"serie_subcribe": serie_id}}
        )
        await serie_col.update_one(
            {"_id": ObjectId(serie_id)},
            {"$inc": {"serie_subcribe_num": -1}}
        )
        return {"message": "Unsubscribed"}
    
    async def search_series_by_title(self, keyword: str) -> List[Dict[str, Any]]:
        collection = await self._series_collection()
        cursor = collection.find({
            "serie_title": {"$regex": keyword, "$options": "i"},
            "isPublish": True
        })
        return await cursor.to_list(length=None)
    
    async def get_series_subscribed_by_user(self, user_id: str) -> List[Dict[str, Any]]:
        user_col = await self._users_collection()
        serie_col = await self._series_collection()
        
        user = await user_col.find_one({"_id": user_id})
        if not user or not user.get("serie_subcribe"):
            return []
            
        # Convert IDs
        obj_ids = []
        for sid in user.get("serie_subcribe"):
            if ObjectId.is_valid(sid):
                obj_ids.append(ObjectId(sid))
                
        if not obj_ids:
            return []
            
        cursor = serie_col.find({"_id": {"$in": obj_ids}})
        return await cursor.to_list(length=None)
    
    async def get_all_series_by_user(self, user_id: str) -> List[Dict[str, Any]]:
        collection = await self._series_collection()
        cursor = collection.find({"serie_user": user_id})
        return await cursor.to_list(length=None)

serie_service = SerieService()