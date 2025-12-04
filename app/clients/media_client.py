import httpx
import os
from typing import List, Optional, Dict

class MediaServiceClient:
    
    def __init__(self):
        self.base_url = os.environ.get('MEDIA_SERVICE_URL', 'http://localhost:5002')
        self.timeout = 300.0
    
    async def _make_request(self, method: str, endpoint: str, **kwargs):
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                url = f"{self.base_url}{endpoint}"
                response = await client.request(method, url, **kwargs)
                response.raise_for_status()
                return response.json()
            except httpx.HTTPError as e:
                print(f"Error calling media service: {e}")
                return None

    async def upload_thumbnail(self, file_content: bytes, filename: str, content_type: str, user_id: str) -> Optional[str]:
        try:
            files = {'file': (filename, file_content, content_type)}
            data = {'user_id': user_id}
            
            result = await self._make_request(
                'POST',
                '/api/upload/thumbnail',
                files=files,
                data=data
            )
            return result.get('url') if result else None
        except Exception as e:
            print(f"Error uploading thumbnail: {e}")
            return None
    
    async def upload_video(self, file_content: bytes, filename: str, content_type: str, user_id: str) -> Optional[str]:
        try:
            files = {'file': (filename, file_content, content_type)}
            data = {'user_id': user_id}
            
            result = await self._make_request(
                'POST',
                '/api/upload/video',
                files=files,
                data=data
            )
            return result.get('url') if result else None
        except Exception as e:
            print(f"Error uploading video: {e}")
            return None
    
    async def upload_document(self, file_content: bytes, filename: str, content_type: str, user_id: str) -> Optional[str]:
        try:
            files = {'file': (filename, file_content, content_type)}
            data = {'user_id': user_id}
            
            result = await self._make_request(
                'POST',
                '/api/upload/document',
                files=files,
                data=data
            )
            return result.get('url') if result else None
        except Exception as e:
            print(f"Error uploading document: {e}")
            return None

    async def delete_file(self, url_or_key: str) -> bool:
        if not url_or_key: 
            return False
        try:
            result = await self._make_request(
                'DELETE',
                '/api/delete',
                json={'url_or_key': url_or_key}
            )
            return result.get('success', False) if result else False
        except Exception as e:
            print(f"Error deleting file: {e}")
            return False
    
    async def delete_files_batch(self, urls: List[str]) -> Dict:
        if not urls:
            return {"deleted": [], "failed": []}
        try:
            result = await self._make_request(
                'DELETE',
                '/api/delete/batch',
                json={'urls': urls}
            )
            return {
                "deleted": result.get('deleted', []) if result else [],
                "failed": result.get('failed', []) if result else urls
            }
        except Exception as e:
            print(f"Error deleting files: {e}")
            return {"deleted": [], "failed": urls}