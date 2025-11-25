from abc import ABC, abstractmethod
from uuid import uuid4
from typing import Optional, Dict, Any, List
from app.utils.mongodb import get_db
from app.utils.s3 import upload_to_s3, delete_from_s3
from app.utils.sns import create_topic, delete_topic, subscribe_to_serie, unsubscribe_from_topic


# 1. Interface Repository
class SerieRepository(ABC):
    """Interface cho Serie Repository"""
    
    @abstractmethod
    def find_by_id(self, serie_id: str) -> Optional[Dict[str, Any]]:
        pass
    
    @abstractmethod
    def find_all(self, query: Optional[Dict] = None) -> List[Dict[str, Any]]:
        pass
    
    @abstractmethod
    def find_by_user(self, user_id: str) -> List[Dict[str, Any]]:
        pass
    
    @abstractmethod
    def search_by_title(self, keyword: str) -> List[Dict[str, Any]]:
        pass
    
    @abstractmethod
    def find_subscribed_by_user(self, user_id: str) -> List[Dict[str, Any]]:
        pass
    
    @abstractmethod
    def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        pass
    
    @abstractmethod
    def update(self, serie_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        pass
    
    @abstractmethod
    def delete(self, serie_id: str) -> bool:
        pass
    
    @abstractmethod
    def subscribe_user(self, serie_id: str, user_id: str) -> Dict[str, Any]:
        pass
    
    @abstractmethod
    def unsubscribe_user(self, serie_id: str, user_id: str) -> Dict[str, Any]:
        pass


# 2. Implementation: MongoDB
class MongoSerieRepository(SerieRepository):
    """MongoDB implementation"""
    
    
    def _series_collection(self):
        _, db = get_db()
        return db["series"]

    def _users_collection(self):
        _, db = get_db()
        return db["users"]

    def find_by_id(self, serie_id: str) -> Optional[Dict[str, Any]]:
        from bson import ObjectId
        if not ObjectId.is_valid(serie_id):
            return None
        return self._series_collection().find_one({"_id": ObjectId(serie_id)})
    
    def find_all(self, query: Optional[Dict] = None) -> List[Dict[str, Any]]:
        q = dict(query) if query else {}
        return list(self._series_collection().find(q))
    
    def find_by_user(self, user_id: str) -> List[Dict[str, Any]]:
        return list(self._series_collection().find({"serie_user": user_id}))
    
    def search_by_title(self, keyword: str) -> List[Dict[str, Any]]:
        serie_col = self._series_collection()
        try:
            return list(serie_col.find({
                "$text": {"$search": keyword},
                "isPublish": True
            }))
        except Exception:
            return list(serie_col.find({
                "serie_title": {"$regex": keyword, "$options": "i"},
                "isPublish": True
            }))
    
    def find_subscribed_by_user(self, user_id: str) -> List[Dict[str, Any]]:
        user_col = self._users_collection()
        serie_col = self._series_collection()
        
        user = user_col.find_one({"_id": user_id}, {"serie_subcribe": 1})
        if not user or not user.get("serie_subcribe"):
            return []
        
        from bson import ObjectId
        obj_ids = []
        for sid in user.get("serie_subcribe"):
            try:
                obj_ids.append(ObjectId(sid))
            except Exception:
                pass
        
        return list(serie_col.find({"_id": {"$in": obj_ids}}))
    
    def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        serie_col = self._series_collection()
        
        # Convert isPublish thành boolean
        is_publish_val = data.get("isPublish", False)
        if isinstance(is_publish_val, str):
            is_publish_val = is_publish_val.lower() == "true"
        else:
            is_publish_val = bool(is_publish_val)
        
        new_serie = {
            **data,
            "isPublish": is_publish_val,
            "serie_lessons": data.get("serie_lessons", []),
            "createdAt": None,
            "updatedAt": None,
            "serie_subcribe_num": 0,
        }
        
        result = serie_col.insert_one(new_serie)
        inserted_id = str(result.inserted_id)
        
        # Create SNS topic
        topic_arn = create_topic(f"serie_{inserted_id}")
        serie_col.update_one(
            {"_id": result.inserted_id},
            {"$set": {"serie_sns": topic_arn}}
        )
        
        return {"_id": inserted_id, **new_serie, "serie_sns": topic_arn}

    
    def update(self, serie_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        from bson import ObjectId
        serie_col = self._series_collection()
        
        # Coerce isPublish string
        if isinstance(data.get("isPublish"), str):
            data["isPublish"] = data["isPublish"].lower() == "true"
        
        data["updatedAt"] = None
        
        res = serie_col.update_one(
            {"_id": ObjectId(serie_id)},
            {"$set": data}
        )
        
        if res.matched_count == 0:
            return None
        
        return serie_col.find_one({"_id": ObjectId(serie_id)})
    
    def delete(self, serie_id: str) -> bool:
        from bson import ObjectId
        serie_col = self._series_collection()
        user_col = self._users_collection()
        
        serie = serie_col.find_one({"_id": ObjectId(serie_id)})
        if not serie:
            raise ValueError("Serie không tồn tại.")
        
        if serie.get("serie_lessons") and len(serie.get("serie_lessons")) > 0:
            return False
        
        # Remove from users' subscriptions
        user_col.update_many(
            {"serie_subcribe": serie_id},
            {"$pull": {"serie_subcribe": serie_id}, "$set": {"updatedAt": None}}
        )
        
        # Delete SNS topic
        if serie.get("serie_sns"):
            delete_topic(serie.get("serie_sns"))
        
        result = serie_col.delete_one({"_id": ObjectId(serie_id)})
        
        # Delete thumbnail
        if result.deleted_count > 0 and serie.get("serie_thumbnail"):
            delete_from_s3(serie.get("serie_thumbnail"))
        
        return result.deleted_count > 0
    
    def subscribe_user(self, serie_id: str, user_id: str) -> Dict[str, Any]:
        from bson import ObjectId
        serie_col = self._series_collection()
        user_col = self._users_collection()
        
        serie = serie_col.find_one({"_id": ObjectId(serie_id)})
        if not serie or not serie.get("serie_sns"):
            raise ValueError("Serie not found")
        
        user = user_col.find_one({"_id": user_id})
        if not user:
            raise ValueError("User not found")
        
        if user.get("serie_subcribe") and serie_id in user.get("serie_subcribe"):
            return {"message": "Bạn đã đăng ký series này rồi.", "alreadySubscribed": True}
        
        user_col.update_one(
            {"_id": user_id},
            {"$addToSet": {"serie_subcribe": serie_id}, "$set": {"updatedAt": None}}
        )
        
        serie_col.update_one(
            {"_id": ObjectId(serie_id)},
            {"$inc": {"serie_subcribe_num": 1}, "$set": {"updatedAt": None}}
        )
        
        return {"message": "Subscribed"}
    
    def unsubscribe_user(self, serie_id: str, user_id: str) -> Dict[str, Any]:
        from bson import ObjectId
        serie_col = self._series_collection()
        user_col = self._users_collection()
        
        serie = serie_col.find_one({"_id": ObjectId(serie_id)})
        if not serie or not serie.get("serie_sns"):
            raise ValueError("Serie not found")
        
        user = user_col.find_one({"_id": user_id})
        if not user:
            raise ValueError("User not found")
        
        if not user.get("serie_subcribe") or serie_id not in user.get("serie_subcribe"):
            return {"message": "Bạn chưa đăng ký serie này.", "user": user}
        
        user_col.update_one(
            {"_id": user_id},
            {"$pull": {"serie_subcribe": serie_id}, "$set": {"updatedAt": None}}
        )
        
        serie_col.update_one(
            {"_id": ObjectId(serie_id)},
            {"$inc": {"serie_subcribe_num": -1}, "$set": {"updatedAt": None}}
        )
        
        return {"message": "Bạn đã hủy đăng ký thành công.", "user": None}


# 3. Service
class SerieService:
    """Service quản lý serie"""
    
    def __init__(self, repository: Optional[SerieRepository] = None):
        self._repository = repository or MongoSerieRepository()
    
    def create_serie(self, data: Dict, user_id: str, id_token: str = None, file=None) -> Dict[str, Any]:
        image_url = ""
        
        if file:
            unique_name = f"{uuid4()}_{getattr(file, 'filename', 'file')}"
            buffer = getattr(file, 'read', lambda: None)()
            mimetype = getattr(file, 'mimetype', None) or getattr(file, 'content_type', None)
            # image_url = upload_to_s3(
            #     buffer, unique_name, mimetype,
            #     f"files/user-{user_id}/thumbnail"
            # )
        
        data["serie_thumbnail"] = image_url
        data["serie_user"] = user_id
        
        return self._repository.create(data)
    
    def get_all_series(self, query: Optional[Dict] = None) -> List[Dict[str, Any]]:
        return self._repository.find_all(query)
    
    def get_serie_by_id(self, serie_id: str) -> Optional[Dict[str, Any]]:
        return self._repository.find_by_id(serie_id)
    
    def get_all_series_by_user(self, user_id: str) -> List[Dict[str, Any]]:
        return self._repository.find_by_user(user_id)
    
    def search_series_by_title(self, keyword: str) -> List[Dict[str, Any]]:
        return self._repository.search_by_title(keyword)
    
    def get_series_subscribed_by_user(self, user_id: str) -> List[Dict[str, Any]]:
        return self._repository.find_subscribed_by_user(user_id)
    
    def update_serie(self, serie_id: str, data: Dict, user_id: str = None, id_token: str = None, file=None) -> Optional[Dict[str, Any]]:
        if file:
            # Delete old thumbnail
            current = self._repository.find_by_id(serie_id)
            if current and current.get("serie_thumbnail"):
                delete_from_s3(current.get("serie_thumbnail"))

            # Upload new
            unique_name = f"{uuid4()}_{getattr(file, 'filename', 'file')}"
            buffer = getattr(file, 'read', lambda: None)()
            mimetype = getattr(file, 'mimetype', None) or getattr(file, 'content_type', None)
            new_url = upload_to_s3(
                buffer, unique_name, mimetype,
                f"files/user-{user_id}/thumbnail"
            )
            data["serie_thumbnail"] = new_url
        
        return self._repository.update(serie_id, data)
    
    def subscribe_serie(self, serie_id: str, user_id: str, user_email: str) -> Dict[str, Any]:
        result = self._repository.subscribe_user(serie_id, user_id)
        
        if not result.get("alreadySubscribed"):
            # Subscribe to SNS
            serie = self._repository.find_by_id(serie_id)
            if serie and serie.get("serie_sns"):
                subscribe_to_serie(serie.get("serie_sns"), user_email)
        
        return result
    
    def unsubscribe_serie(self, serie_id: str, user_id: str, user_email: str) -> Dict[str, Any]:
        serie = self._repository.find_by_id(serie_id)
        if serie and serie.get("serie_sns"):
            result = unsubscribe_from_topic(serie.get("serie_sns"), user_email)
            if result.get("pendingConfirmation"):
                return result
        
        return self._repository.unsubscribe_user(serie_id, user_id)
    
    def delete_serie(self, serie_id: str) -> Dict[str, Any]:
        result = self._repository.delete(serie_id)
        
        if result is False:
            return {
                "success": False,
                "warning": "Không thể xóa serie khi vẫn còn bài học trong serie này."
            }
        
        return {"success": result}


# Public API - backward compatibility
_service = SerieService()

def create_serie(data, user_id=None, id_token=None, file=None):
    return _service.create_serie(data, user_id, id_token, file)

def get_all_series(query=None):
    return _service.get_all_series(query)

def get_serie_by_id(serie_id):
    return _service.get_serie_by_id(serie_id)

def get_all_series_by_user(user_id):
    return _service.get_all_series_by_user(user_id)

def search_series_by_title(keyword):
    return _service.search_series_by_title(keyword)

def get_series_subscribed_by_user(user_id):
    return _service.get_series_subscribed_by_user(user_id)

def update_serie(serie_id, data, user_id=None, id_token=None, file=None):
    return _service.update_serie(serie_id, data, user_id, id_token, file)

def subscribe_serie(serie_id, user_id, user_email):
    return _service.subscribe_serie(serie_id, user_id, user_email)

def unsubscribe_serie(serie_id, user_id, user_email):
    return _service.unsubscribe_serie(serie_id, user_id, user_email)

def delete_serie(serie_id):
    return _service.delete_serie(serie_id)