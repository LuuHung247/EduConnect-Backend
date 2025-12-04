import os

from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()

class MongoDB:
    client: AsyncIOMotorClient = None
    db_name: str = None

db = MongoDB()

async def get_database():
    return db.client[db.db_name]

def connect_to_mongo():
    uri = os.environ.get("MONGODB_URI", "mongodb://localhost:27017")
    name = os.environ.get("MONGODB_NAME", "paas_backend")
    
    if not uri or not name:
        raise RuntimeError("MongoDB URI or database name not configured")

    db.client = AsyncIOMotorClient(uri)
    db.db_name = name
    print(f"Connected to MongoDB: {name}")

def close_mongo_connection():
    if db.client:
        db.client.close()
        print("Closed MongoDB connection")