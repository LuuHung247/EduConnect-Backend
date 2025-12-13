from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List
from app.utils.mongodb import get_db
from app.utils.sns import create_topic, delete_topic, subscribe_to_serie, unsubscribe_from_topic
from app.clients.media_client import MediaServiceClient
from app.utils.ses import send_email
from datetime import datetime, timezone


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
            "createdAt": datetime.now(timezone.utc),
            "updatedAt": datetime.now(timezone.utc),
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
        
        data["updatedAt"] = datetime.now(timezone.utc)
        
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
            {"$pull": {"serie_subcribe": serie_id}, "$set": {"updatedAt": datetime.now(timezone.utc)}}
        )
        
        # Delete SNS topic
        if serie.get("serie_sns"):
            delete_topic(serie.get("serie_sns"))
        
        result = serie_col.delete_one({"_id": ObjectId(serie_id)})
        
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
            {"$addToSet": {"serie_subcribe": serie_id}, "$set": {"updatedAt": datetime.now(timezone.utc)}}
        )
        
        serie_col.update_one(
            {"_id": ObjectId(serie_id)},
            {"$inc": {"serie_subcribe_num": 1}, "$set": {"updatedAt": datetime.now(timezone.utc)}}
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
            {"$pull": {"serie_subcribe": serie_id}, "$set": {"updatedAt": datetime.now(timezone.utc)}}
        )
        
        serie_col.update_one(
            {"_id": ObjectId(serie_id)},
            {"$inc": {"serie_subcribe_num": -1}, "$set": {"updatedAt": datetime.now(timezone.utc)}}
        )
        
        return {"message": "Bạn đã hủy đăng ký thành công."}


# 3. Service
class SerieService:
    """Service quản lý serie - Gọi Media Service qua HTTP"""
    
    def __init__(
        self, 
        repository: Optional[SerieRepository] = None,
        media_client: Optional[MediaServiceClient] = None
    ):
        self._repository = repository or MongoSerieRepository()
        self._media_client = media_client or MediaServiceClient()
    
    def create_serie(self, data: Dict, user_id: str, id_token: str = None, file=None) -> Dict[str, Any]:
        # Upload thumbnail qua Media Service
        thumbnail_url = ""
        if file:
            thumbnail_url = self._media_client.upload_thumbnail(file, user_id)
        
        data["serie_thumbnail"] = thumbnail_url
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
    
    def update_serie(
        self, 
        serie_id: str, 
        data: Dict, 
        user_id: str = None, 
        id_token: str = None, 
        file=None
    ) -> Optional[Dict[str, Any]]:
        # Handle thumbnail replacement qua Media Service
        if file:
            current = self._repository.find_by_id(serie_id)
            
            # Delete old thumbnail
            if current and current.get("serie_thumbnail"):
                self._media_client.delete_file(current.get("serie_thumbnail"))
            
            # Upload new thumbnail
            new_url = self._media_client.upload_thumbnail(file, user_id)
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
        # Get serie to delete thumbnail
        serie = self._repository.find_by_id(serie_id)
        
        result = self._repository.delete(serie_id)
        
        if result is False:
            return {
                "success": False,
                "warning": "Không thể xóa serie khi vẫn còn bài học trong serie này."
            }
        
        # Delete thumbnail qua Media Service
        if result and serie and serie.get("serie_thumbnail"):
            self._media_client.delete_file(serie.get("serie_thumbnail"))
        
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

def send_series_notification(serie_id: str, title: str, message: str) -> dict:
    _, db = get_db()
    
    # 1. Lấy thông tin series
    serie = get_serie_by_id(serie_id)
    if not serie:
        raise ValueError("Khóa học không tồn tại")
    
    serie_title = serie.get("serie_title", "Khóa học")
    
    # 2. Tìm danh sách email của những người đã subscribe khóa học này
    subscribers = db.users.find(
        {"serie_subcribe": serie_id},
        {"email": 1, "_id": 0}
    )
    
    recipient_list = [sub.get("email") for sub in subscribers if sub.get("email")]
    
    if not recipient_list:
        return {
            "success": True,
            "message": "Không có học viên nào đăng ký khóa học này để gửi thông báo."
        }

    # 3. Chuẩn bị nội dung email
    email_subject = f"[{serie_title}] Thông báo mới: {title}"
    
    email_html = f"""
    <html>
    <body>
        <h2>Thông báo từ khóa học {serie_title}</h2>
        <p><strong>{title}</strong></p>
        <p style="white-space: pre-line;">{message}</p>
        <hr/>
        <p>Cảm ơn bạn đã học tập cùng EduConnect.</p>
    </body>
    </html>
    """

    # 4. Gọi SES để gửi
    try:
        message_ids = send_email(
            recipient_emails=recipient_list,
            subject=email_subject,
            body_text=message,
            body_html=email_html
        )
        
        return {
            "success": True,
            "recipient_count": len(recipient_list),
            "message_ids": message_ids
        }
    except Exception as e:
        print(f"Failed to send email: {str(e)}")
        raise Exception(f"Lỗi khi gửi email thông báo: {str(e)}")