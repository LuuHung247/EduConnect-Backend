from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from app.utils.mongodb import get_db
from datetime import datetime, timezone

# 1. Interface Repository
class UserRepository(ABC):
    """Interface cho User Repository"""
    
    @abstractmethod
    def find_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        pass
    
    @abstractmethod
    def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        pass
    
    @abstractmethod
    def update(self, user_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        pass

# 2. Implementation: MongoDB
class MongoUserRepository(UserRepository):
    """MongoDB implementation"""
    
    def _users_collection(self):
        _, db = get_db()
        return db["users"]

    def find_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        collection = self._users_collection()
        return collection.find_one({"_id": user_id})
    
    def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        cognito_id = data.get("userId") 
        if not cognito_id:
            raise ValueError("userId is required")

        collection = self._users_collection()

        # Check existing
        existing = collection.find_one({"_id": cognito_id})
        if existing:
            return self.update(cognito_id, data)
        
        # Create new
        payload = {
            "_id": cognito_id,
            "email": data.get("email"),
            "name": data.get("name"),
            "username": data.get("username", data.get("email").split('@')[0]),
            "gender": data.get("gender", ""),
            "birthdate": data.get("birthdate", ""),
            
            # Các trường mặc định
            "role": "student",
            "avatar": "",
            "bio": "",
            "cognito_sub": cognito_id,
            
            "serie_subscribe": [],
            "createdAt": datetime.now(timezone.utc),
            "updatedAt": datetime.now(timezone.utc),
            "lastLogin": datetime.now(timezone.utc)
        }
        collection.insert_one(payload)
        return payload
    
    def update(self, user_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        collection = self._users_collection()
        
        # Sanitize data
        update_data = {k: v for k, v in data.items() if k not in ("_id", "userId", "createdAt")}
        update_data["updatedAt"] = datetime.now(timezone.utc)

        return collection.find_one_and_update(
            {"_id": user_id},
            {"$set": update_data},
            return_document=True,
            upsert=True
        )


# 3. Service đơn giản
class UserService:
    """Service quản lý user"""
    
    def __init__(self, repository: Optional[UserRepository] = None):
        self._repository = repository or MongoUserRepository()
    
    def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        return self._repository.find_by_id(user_id)
    
    def get_user_by_cognito_id(self, cognito_id: str) -> Optional[Dict[str, Any]]:
        return self._repository.find_by_id(cognito_id)
    
    def create_user(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return self._repository.create(data)
    
    def update_user(self, user_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return self._repository.update(user_id, data)
    
    def update_user_by_cognito_id(self, cognito_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        return self._repository.update(cognito_id, data)
    
    @staticmethod
    def sync_cognito_user(user_data):
        try:
            _, db = get_db()
            users_collection = db["users"]
            
            cognito_sub = user_data.get('cognito_sub')
            email = user_data.get('email')
            
            if not cognito_sub or not email:
                return None, "Missing required user info"

            existing_user = None

            if not existing_user:
                existing_user = users_collection.find_one({"email": email})

            now = datetime.now(timezone.utc)

            if not existing_user:
                existing_user = users_collection.find_one({"email": email})

            now = datetime.now(timezone.utc)
            
            update_data = {
                "email": email,
                "cognito_sub": cognito_sub,
                "lastLogin": now,
                "updatedAt": now
            }
            
            fields_to_sync = ['name', 'gender', 'birthdate', 'avatar']
            for field in fields_to_sync:
                if user_data.get(field):
                    update_data[field] = user_data.get(field)

            if existing_user:
                # Cập nhật user hiện có
                users_collection.update_one(
                    {"_id": existing_user["_id"]},
                    {"$set": update_data}
                )
                return str(existing_user["_id"]), None
            else:
                # Tạo user mới
                new_user_data = {
                    "_id": cognito_sub,
                    **update_data,
                    "role": "student",
                    "bio": "",
                    "serie_subscribe": [],
                    "createdAt": now
                }
                if "name" not in new_user_data: 
                    new_user_data["name"] = email.split('@')[0]

                users_collection.insert_one(new_user_data)
                return cognito_sub, None
        
        except Exception as e:
            print(f"User Sync Error: {str(e)}")
            return None, str(e)


# Public API - giữ backward compatibility
_service = UserService()

def create_user(data: dict) -> dict:
    return _service.create_user(data)

def get_user_by_id(user_id: str) -> dict:
    return _service.get_user_by_id(user_id)

def get_user_by_cognito_id(cognito_id: str) -> dict:
    return _service.get_user_by_cognito_id(cognito_id)

def update_user(user_id: str, data: dict) -> dict:
    return _service.update_user(user_id, data)

def update_user_by_cognito_id(cognito_id: str, data: dict):
    return _service.update_user_by_cognito_id(cognito_id, data)

