from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from app.utils.mongodb import get_db


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
            **{k: v for k, v in data.items() if k != "userId"},
            "serie_subscribe": [],
            "createdAt": datetime.now(timezone.utc),
            "updatedAt": datetime.now(timezone.utc)
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

