"""
HTTP Client for User Service
Follows the same pattern as media_client.py
"""
import requests
import os
from typing import Optional, Dict, List


class UserServiceClient:
    """Client to communicate with User Microservice"""

    def __init__(self):
        self.base_url = os.environ.get('USER_SERVICE_URL', 'http://localhost:5002')
        self.timeout = 30

    def _make_request(self, method: str, endpoint: str, **kwargs):
        """Make HTTP request with error handling"""
        try:
            url = f"{self.base_url}{endpoint}"

            # Always include Authorization header if present in kwargs
            headers = kwargs.pop('headers', {})

            response = requests.request(
                method,
                url,
                headers=headers,
                **kwargs
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error calling user service: {e}")
            raise Exception(f"User service error: {str(e)}")

    def verify_jwt(self, token: str) -> Optional[Dict]:
        """
        Verify JWT token and get user context

        Args:
            token: JWT token (without 'Bearer ' prefix)

        Returns:
            {
                "user_id": "...",
                "email": "...",
                "name": "...",
                "role": "..."
            }
        """
        try:
            result = self._make_request(
                'POST',
                '/api/v1/auth/verify',
                headers={'Authorization': f'Bearer {token}'},
                timeout=10
            )

            if result.get('success'):
                return result.get('data')
            return None
        except Exception as e:
            print(f"Error verifying JWT: {e}")
            return None

    def get_user(self, user_id: str, token: str) -> Optional[Dict]:
        """Get user profile by ID"""
        try:
            result = self._make_request(
                'GET',
                f'/api/v1/users/{user_id}',
                headers={'Authorization': f'Bearer {token}'},
                timeout=10
            )

            if result.get('success'):
                return result.get('data')
            return None
        except Exception as e:
            print(f"Error getting user: {e}")
            return None

    def get_subscriptions(self, user_id: str, token: str) -> List[str]:
        """Get user's subscribed serie IDs"""
        try:
            result = self._make_request(
                'GET',
                f'/api/v1/users/{user_id}/subscriptions',
                headers={'Authorization': f'Bearer {token}'},
                timeout=10
            )

            if result.get('success'):
                data = result.get('data', {})
                return data.get('subscriptions', [])
            return []
        except Exception as e:
            print(f"Error getting subscriptions: {e}")
            return []

    def add_subscription(self, user_id: str, serie_id: str, token: str) -> bool:
        """Add serie to user's subscriptions"""
        try:
            result = self._make_request(
                'POST',
                f'/api/v1/users/{user_id}/subscriptions',
                headers={'Authorization': f'Bearer {token}'},
                json={'serie_id': serie_id},
                timeout=10
            )

            return result.get('success', False)
        except Exception as e:
            print(f"Error adding subscription: {e}")
            return False

    def remove_subscription(self, user_id: str, serie_id: str, token: str) -> bool:
        """Remove serie from user's subscriptions"""
        try:
            result = self._make_request(
                'DELETE',
                f'/api/v1/users/{user_id}/subscriptions/{serie_id}',
                headers={'Authorization': f'Bearer {token}'},
                timeout=10
            )

            return result.get('success', False)
        except Exception as e:
            print(f"Error removing subscription: {e}")
            return False

    def get_subscribers(self, serie_id: str, token: str) -> List[str]:
        """Get all emails of users subscribed to a serie"""
        try:
            result = self._make_request(
                'GET',
                f'/api/v1/users/subscribers/{serie_id}',
                headers={'Authorization': f'Bearer {token}'},
                timeout=10
            )

            if result.get('success'):
                data = result.get('data', {})
                return data.get('emails', [])
            return []
        except Exception as e:
            print(f"Error getting subscribers: {e}")
            return []

    def remove_serie_from_all(self, serie_id: str, token: str) -> Dict:
        """Remove serie from ALL users' subscriptions"""
        try:
            result = self._make_request(
                'DELETE',
                f'/api/v1/users/subscriptions/serie/{serie_id}',
                headers={'Authorization': f'Bearer {token}'},
                timeout=30
            )

            if result.get('success'):
                return result.get('data', {})
            return {'modified_count': 0}
        except Exception as e:
            print(f"Error removing serie from all users: {e}")
            return {'modified_count': 0}

    def health_check(self) -> bool:
        """Check if user service is healthy"""
        try:
            response = requests.get(f"{self.base_url}/health", timeout=5)
            return response.status_code == 200
        except Exception:
            return False
