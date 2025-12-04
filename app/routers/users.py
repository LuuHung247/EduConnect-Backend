from fastapi import APIRouter, Depends, HTTPException, status

from app.schemas.user import UserCreate, UserUpdate, UserResponse
from app.services.user_service import user_service
from app.dependencies.auth import get_current_user


router = APIRouter(
    prefix="/api/v1/users", 
    tags=["Users"]
)


@router.post("/profile", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_profile(user_data: UserCreate):
    try:
        # Check if user exists
        existing = await user_service.get_user_by_id(user_data.userId)
        if existing:
            raise HTTPException(status_code=409, detail="User profile already exists")
        
        result = await user_service.create_user(user_data.model_dump())
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/profile", response_model=UserResponse)
async def get_current_profile(current_user: dict = Depends(get_current_user)):
    user_id = current_user.get("userId")
    try:
        user = await user_service.get_user_by_id(user_id)
        
        if not user:
            user_data = {
                "userId": user_id,
                "name": current_user.get("name", ""),
                "email": current_user.get("email", ""),
                "username": current_user.get("username", ""),
            }
            user = await user_service.create_user(user_data)
            
        return user
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(user_id: str, 
                   current_user: dict = Depends(get_current_user)):
    user = await user_service.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.put("/{user_id}", response_model=UserResponse)
async def update_user_profile(user_id: str, 
                              user_data: UserUpdate, 
                              current_user: dict = Depends(get_current_user)):
    if current_user.get("userId") != user_id:
        raise HTTPException(status_code=403, detail="Not authorized to update this profile")

    existing = await user_service.get_user_by_id(user_id)
    if not existing:
        raise HTTPException(status_code=404, detail="User not found")
    
    updated = await user_service.update_user(user_id, user_data.model_dump(exclude_unset=True))
    return updated