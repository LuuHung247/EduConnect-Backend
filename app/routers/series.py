import json

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Query
from typing import List, Optional
from app.schemas.serie import SerieResponse, SerieCreate, SerieUpdate
from app.services.serie_service import serie_service
from app.dependencies.auth import get_current_user


router = APIRouter(prefix="/api/v1/series", tags=["Series"])

@router.post("", response_model=SerieResponse, status_code=status.HTTP_201_CREATED)
async def create_serie_route(
    serie_title: str = Form(...),
    serie_description: str = Form(None),
    isPublish: bool = Form(False),
    serie_thumbnail: UploadFile = File(None),
    current_user: dict = Depends(get_current_user)
):
    user_id = current_user.get("userId")
    
    data = {
        "serie_title": serie_title,
        "serie_description": serie_description,
        "isPublish": isPublish
    }
    
    file_content = None
    filename = None
    content_type = None
    if serie_thumbnail:
        file_content = await serie_thumbnail.read()
        filename = serie_thumbnail.filename
        content_type = serie_thumbnail.content_type

    try:
        result = await serie_service.create_serie(data, user_id, file_content, filename, content_type)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("", response_model=List[SerieResponse])
async def list_series(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100)
):
    return await serie_service.get_all_series()


@router.get("/subscribed", response_model=List[SerieResponse])
async def get_user_subscribed_series(current_user: dict = Depends(get_current_user)):
    user_id = current_user.get("userId")
    return await serie_service.get_series_subscribed_by_user(user_id)


@router.get("/created", response_model=List[SerieResponse])
async def get_user_created_series(current_user: dict = Depends(get_current_user)):
    user_id = current_user.get("userId")
    return await serie_service.get_all_series_by_user(user_id)


@router.get("/search", response_model=List[SerieResponse])
async def search_series(keyword: str = Query(..., min_length=1)):
    return await serie_service.search_series_by_title(keyword)


@router.get("/{serie_id}", response_model=SerieResponse)
async def get_serie_detail(serie_id: str):
    serie = await serie_service.get_serie_by_id(serie_id)
    if not serie:
        raise HTTPException(status_code=404, detail="Serie not found")
    return serie


@router.patch("/{serie_id}", response_model=SerieResponse)
async def update_serie_route(
    serie_id: str,
    serie_title: Optional[str] = Form(None),
    serie_description: Optional[str] = Form(None),
    isPublish: Optional[bool] = Form(None),
    serie_thumbnail: UploadFile = File(None),
    current_user: dict = Depends(get_current_user)
):
    user_id = current_user.get("userId")
    
    data = {}
    if serie_title is not None: data["serie_title"] = serie_title
    if serie_description is not None: data["serie_description"] = serie_description
    if isPublish is not None: data["isPublish"] = isPublish

    file_content = None
    filename = None
    content_type = None
    if serie_thumbnail:
        file_content = await serie_thumbnail.read()
        filename = serie_thumbnail.filename
        content_type = serie_thumbnail.content_type

    updated = await serie_service.update_serie(serie_id, data, user_id, file_content, filename, content_type)
    if not updated:
        raise HTTPException(status_code=404, detail="Serie not found")
    return updated


@router.post("/{serie_id}/subscribe")
async def subscribe_to_serie(serie_id: str, 
                             current_user: dict = Depends(get_current_user)):
    user_id = current_user.get("userId")
    user_email = current_user.get("email")
    try:
        return await serie_service.subscribe_serie(serie_id, user_id, user_email)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{serie_id}/unsubscribe")
async def unsubscribe_from_serie(serie_id: str, 
                                 current_user: dict = Depends(get_current_user)):
    user_id = current_user.get("userId")
    user_email = current_user.get("email")
    try:
        return await serie_service.unsubscribe_serie(serie_id, user_id, user_email)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/{serie_id}")
async def delete_serie_route(serie_id: str, 
                             current_user: dict = Depends(get_current_user)):
    result = await serie_service.delete_serie(serie_id)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("warning", "Delete failed"))
    return {"message": "Serie deleted successfully"}