from typing import Optional, Dict, Any

from app.utils.mongodb import get_database

class UserService:
    
    async def _users_collection(self):
        db = await get_database()
        return db["users"]

    async def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        collection = await self._users_collection()
        return await collection.find_one({"_id": user_id})
    
    async def create_user(self, data: Dict[str, Any]) -> Dict[str, Any]:
        cognito_id = data.get("userId") 
        if not cognito_id:
            raise ValueError("userId is required")

        collection = await self._users_collection()

        existing = await collection.find_one({"_id": cognito_id})
        if existing:
            return await self.update_user(cognito_id, data)
        
        payload = {
            "_id": cognito_id,
            **{k: v for k, v in data.items() if k != "userId"},
            "serie_subscribe": [],
            "createdAt": None,
            "updatedAt": None,
        }
        await collection.insert_one(payload)
        return payload
    
    async def update_user(self, user_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        collection = await self._users_collection()
        
        update_data = {k: v for k, v in data.items() if k not in ("_id", "userId", "createdAt")}
        update_data["updatedAt"] = None
        
        return await collection.find_one_and_update(
            {"_id": user_id},
            {"$set": update_data},
            return_document=True,
            upsert=True
        )

user_service = UserService()