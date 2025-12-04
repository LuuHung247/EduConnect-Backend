from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Body
from typing import List, Optional

from app.schemas.lesson import LessonResponse
from app.services.lesson_service import lesson_service
from app.dependencies.auth import get_current_user

router = APIRouter(
    prefix="/api/v1/series/{series_id}/lessons",
    tags=["Lessons"]
)

@router.post("", response_model=LessonResponse, status_code=status.HTTP_201_CREATED)
async def create_lesson_route(
    series_id: str,
    lesson_title: str = Form(...),
    lesson_content: str = Form(None),
    lesson_video: UploadFile = File(None),
    lesson_documents: List[UploadFile] = File(None),
    current_user: dict = Depends(get_current_user)
):
    user_id = current_user.get("userId")
    
    data = {
        "lesson_title": lesson_title,
        "lesson_content": lesson_content,
        "lesson_serie": series_id
    }
    
    # Process Video
    video_tuple = None
    if lesson_video:
        content = await lesson_video.read()
        video_tuple = (content, lesson_video.filename, lesson_video.content_type)
        
    # Process Docs
    doc_tuples = []
    if lesson_documents:
        for doc in lesson_documents:
            content = await doc.read()
            doc_tuples.append((content, doc.filename, doc.content_type))

    try:
        return await lesson_service.create_lesson(data, user_id, video_tuple, doc_tuples)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("", response_model=List[LessonResponse])
async def list_lessons(series_id: str, 
                       current_user: dict = Depends(get_current_user)):
    return await lesson_service.get_all_lessons_by_serie(series_id)


@router.get("/{lesson_id}", response_model=LessonResponse)
async def get_lesson_detail(series_id: str, 
                            lesson_id: str, 
                            current_user: dict = Depends(get_current_user)):
    lesson = await lesson_service.get_lesson_by_id(series_id, lesson_id)
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")
    return lesson


@router.patch("/{lesson_id}", response_model=LessonResponse)
async def update_lesson_route(
    series_id: str,
    lesson_id: str,
    lesson_title: Optional[str] = Form(None),
    lesson_content: Optional[str] = Form(None),
    lesson_video: UploadFile = File(None),
    lesson_documents: List[UploadFile] = File(None),
    current_user: dict = Depends(get_current_user)
):
    user_id = current_user.get("userId")
    data = {}
    if lesson_title is not None: data["lesson_title"] = lesson_title
    if lesson_content is not None: data["lesson_content"] = lesson_content
    
    video_tuple = None
    if lesson_video:
        content = await lesson_video.read()
        video_tuple = (content, lesson_video.filename, lesson_video.content_type)
        
    doc_tuples = []
    if lesson_documents:
        for doc in lesson_documents:
            content = await doc.read()
            doc_tuples.append((content, doc.filename, doc.content_type))

    updated = await lesson_service.update_lesson(series_id, lesson_id, data, user_id, video_tuple, doc_tuples)
    if not updated:
        raise HTTPException(status_code=404, detail="Lesson not found")
    return updated


@router.delete("/{lesson_id}")
async def delete_lesson_route(series_id: str, 
                              lesson_id: str, 
                              current_user: dict = Depends(get_current_user)):
    result = await lesson_service.delete_lesson(series_id, lesson_id)
    if not result:
        raise HTTPException(status_code=404, detail="Lesson not found")
    return {"message": "Lesson deleted successfully"}


@router.delete("/{lesson_id}/documents")
async def delete_document_route(
    series_id: str, 
    lesson_id: str, 
    payload: dict = Body(...),
    current_user: dict = Depends(get_current_user)
):
    doc_url = payload.get("docUrl")
    if not doc_url:
        raise HTTPException(status_code=400, detail="docUrl is required")
        
    result = await lesson_service.delete_document_by_url(series_id, lesson_id, doc_url)
    if not result:
         raise HTTPException(status_code=404, detail="Lesson or document not found")
    return {"message": "Document deleted successfully"}