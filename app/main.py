from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware

from app.utils.mongodb import connect_to_mongo, close_mongo_connection
from app.dependencies.auth import get_current_user
from app.routers import users, series, lessons

@asynccontextmanager
async def lifespan(app: FastAPI):
    connect_to_mongo()
    yield
    close_mongo_connection()

app = FastAPI(
    title="EduConnect Backend API",
    version="1.0.0",
    description="API Documentation for EduConnect Platform",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Better change in production phase
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(users.router)
app.include_router(series.router)
app.include_router(lessons.router)

# Health Check Route
@app.get("/health", tags=["System"])
async def health_check():
    return {"status": "ok", "framework": "FastAPI", "mode": "async"}

# Temporary MainPage Route
@app.get("/", tags=["System"])
async def root():
    return {"message": "Welcome to EduConnect API"}


@app.get("/api/me-test", tags=["System"])
async def read_users_me(current_user: dict = Depends(get_current_user)):
    return {"status": "authenticated", "user": current_user}