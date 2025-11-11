"""
Flask JWT Authentication for AWS Cognito
Supports both ID tokens and Access tokens
"""

from functools import wraps
from flask import request, g, jsonify, current_app
import os
import requests
import jwt
from jwt.algorithms import RSAAlgorithm
from typing import Optional, Dict, Any
from datetime import datetime


# Cache cho JWKS
_JWKS_CACHE = {"keys": None, "fetched_at": None}


def _get_config(key: str, default=None):
    """Get config from Flask app.config hoặc environment variables"""
    try:
        return current_app.config.get(key, os.getenv(key, default))
    except RuntimeError:
        return os.getenv(key, default)


def _get_jwks_url() -> Optional[str]:
    """Get JWKS URL from config hoặc construct từ pool ID + region"""
    jwks_url = _get_config('COGNITO_JWKS_URL') or _get_config('JWKS_URL')
    if jwks_url:
        return jwks_url
    
    pool_id = _get_config('COGNITO_USER_POOL_ID') or _get_config('COGNITO_POOL_ID')
    region = _get_config('COGNITO_REGION') or _get_config('AWS_REGION', 'ap-southeast-1')
    
    if pool_id and region:
        return f"https://cognito-idp.{region}.amazonaws.com/{pool_id}/.well-known/jwks.json"
    
    return None


def _get_issuer() -> Optional[str]:
    """Get expected issuer"""
    issuer = _get_config('JWT_ISSUER') or _get_config('COGNITO_ISSUER')
    if issuer:
        return issuer
    
    pool_id = _get_config('COGNITO_USER_POOL_ID') or _get_config('COGNITO_POOL_ID')
    region = _get_config('COGNITO_REGION') or _get_config('AWS_REGION', 'ap-southeast-1')
    
    if pool_id and region:
        return f"https://cognito-idp.{region}.amazonaws.com/{pool_id}"
    
    return None


def _fetch_jwks() -> Optional[list]:
    """Fetch JWKS from Cognito"""
    url = _get_jwks_url()
    if not url:
        return None
    
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        return response.json().get('keys', [])
    except Exception as e:
        try:
            current_app.logger.error(f"Failed to fetch JWKS: {e}")
        except RuntimeError:
            print(f"Failed to fetch JWKS: {e}")
        return None


def _get_jwks_keys() -> Optional[list]:
    """Get JWKS keys with caching"""
    cache_ttl = int(_get_config('JWKS_CACHE_TTL', '86400'))
    now = datetime.now()
    
    if (_JWKS_CACHE['keys'] is not None and 
        _JWKS_CACHE['fetched_at'] is not None and
        (now - _JWKS_CACHE['fetched_at']).total_seconds() < cache_ttl):
        return _JWKS_CACHE['keys']
    
    keys = _fetch_jwks()
    if keys is not None:
        _JWKS_CACHE['keys'] = keys
        _JWKS_CACHE['fetched_at'] = now
    
    return keys


def _get_public_key(kid: str) -> Optional[Any]:
    """Get public key for specific kid"""
    keys = _get_jwks_keys()
    if not keys:
        return None
    
    for jwk in keys:
        if jwk.get('kid') == kid:
            try:
                return RSAAlgorithm.from_jwk(jwk)
            except Exception as e:
                try:
                    current_app.logger.error(f"Failed to convert JWK: {e}")
                except RuntimeError:
                    print(f"Failed to convert JWK: {e}")
                return None
    
    return None


def _extract_token() -> Optional[str]:
    """Extract token from Authorization header"""
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return None
    return auth_header[7:]


def _verify_token(token: str) -> Dict[str, Any]:
    """Verify and decode JWT token"""
    # Get unverified header để extract kid
    try:
        header = jwt.get_unverified_header(token)
    except jwt.InvalidTokenError as e:
        raise jwt.InvalidTokenError(f'Invalid token header: {e}')
    
    kid = header.get('kid')
    if not kid:
        raise jwt.InvalidTokenError('Token missing kid in header')
    
    # Get public key
    public_key = _get_public_key(kid)
    if not public_key:
        # Retry after clearing cache
        _JWKS_CACHE['keys'] = None
        public_key = _get_public_key(kid)
        
        if not public_key:
            raise jwt.InvalidTokenError('Public key not found for kid')
    
    # Decode unverified để check token_use
    try:
        unverified_payload = jwt.decode(token, options={'verify_signature': False})
    except Exception:
        unverified_payload = {}
    
    token_use = unverified_payload.get('token_use')
    
    # Prepare decode options
    decode_options = {
        'algorithms': ['RS256'],
        'leeway': int(_get_config('JWT_LEEWAY', '0'))
    }
    
    # Issuer validation (always required)
    issuer = _get_issuer()
    if issuer:
        decode_options['issuer'] = issuer
    
    # Audience validation - chỉ cho ID token
    # Access token không có aud claim, chỉ có client_id
    app_client_id = _get_config('COGNITO_APP_CLIENT_ID')
    
    if token_use == 'id':
        # ID token MUST have audience
        if app_client_id:
            decode_options['audience'] = app_client_id
        else:
            decode_options['options'] = {'verify_aud': False}
    else:
        # Access token - skip audience verification
        decode_options['options'] = {'verify_aud': False}
    
    # Verify and decode
    try:
        payload = jwt.decode(token, key=public_key, **decode_options)
    except jwt.exceptions.MissingRequiredClaimError as e:
        # If missing aud for access token, that's okay
        if 'aud' in str(e) and token_use == 'access':
            decode_options['options'] = {'verify_aud': False}
            payload = jwt.decode(token, key=public_key, **decode_options)
        else:
            raise
    
    # Validate client_id for access tokens
    if token_use == 'access' and app_client_id:
        token_client_id = payload.get('client_id')
        if token_client_id and token_client_id != app_client_id:
            raise jwt.InvalidAudienceError('Token client_id mismatch')
    
    # Validate token_use claim
    if token_use and token_use not in ('id', 'access'):
        raise jwt.InvalidTokenError(f'Invalid token_use: {token_use}')
    
    return payload


def _build_user_object(token: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Build user object from token payload"""
    return {
        'id_token': token,
        'user_id': payload.get('sub'),
        'email': payload.get('email'),
        'email_verified': payload.get('email_verified'),
        'username': payload.get('preferred_username') or payload.get('cognito:username') or payload.get('username'),
        'name': payload.get('name'),
        'given_name': payload.get('given_name'),
        'family_name': payload.get('family_name'),
        'gender': payload.get('gender'),
        'birthdate': payload.get('birthdate'),
        'phone_number': payload.get('phone_number'),
        'phone_number_verified': payload.get('phone_number_verified'),
        'groups': payload.get('cognito:groups', []),
        'token_use': payload.get('token_use'),
        'auth_time': payload.get('auth_time'),
        'exp': payload.get('exp'),
        'iat': payload.get('iat'),
        'client_id': payload.get('client_id'),
        'cognito': payload
    }


def authenticate_jwt(f):
    """
    Decorator để protect Flask routes với JWT authentication từ AWS Cognito
    Supports cả ID tokens và Access tokens
    
    Configuration (via app.config hoặc environment variables):
      - COGNITO_USER_POOL_ID: Required - Cognito User Pool ID
      - COGNITO_APP_CLIENT_ID: Required - Cognito App Client ID
      - COGNITO_REGION hoặc AWS_REGION: Region (default: ap-southeast-1)
      - COGNITO_JWKS_URL: Optional - Explicit JWKS URL
      - JWKS_CACHE_TTL: Optional - Cache TTL in seconds (default: 86400)
      - JWT_LEEWAY: Optional - Leeway for token expiration (default: 0)
      - ALLOW_INSECURE_JWT: Optional - Allow insecure mode for dev (default: false)
    
    Usage:
        from auth import authenticate_jwt
        
        @app.route('/api/protected')
        @authenticate_jwt
        def protected_route():
            return jsonify({
                'user_id': g.user['user_id'],
                'email': g.user['email']
            })
    
    Token types:
        - ID Token: Contains user profile info (email, name, etc.)
        - Access Token: Contains client_id, scope, but minimal user info
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        # Extract token
        token = _extract_token()
        if not token:
            return jsonify({
                'success': False,
                'error': 'unauthorized',
                'message': 'No authentication token provided'
            }), 401
        
        # Check JWKS configuration
        jwks_url = _get_jwks_url()
        allow_insecure = str(_get_config('ALLOW_INSECURE_JWT', 'false')).lower() in ('true', '1', 'yes')
        
        if not jwks_url:
            if not allow_insecure:
                return jsonify({
                    'success': False,
                    'error': 'configuration_error',
                    'message': 'JWT verification not configured. Set COGNITO_USER_POOL_ID and AWS_REGION'
                }), 500
            
            # Insecure mode for development only
            try:
                payload = jwt.decode(token, options={'verify_signature': False})
                g.user = _build_user_object(token, payload)
                try:
                    current_app.logger.warning('JWT verification in INSECURE mode - not for production!')
                except RuntimeError:
                    print('WARNING: JWT verification in INSECURE mode - not for production!')
            except jwt.InvalidTokenError as e:
                return jsonify({
                    'success': False,
                    'error': 'invalid_token',
                    'message': str(e)
                }), 401
        else:
            # Secure verification
            try:
                payload = _verify_token(token)
                g.user = _build_user_object(token, payload)
                
            except jwt.ExpiredSignatureError:
                return jsonify({
                    'success': False,
                    'error': 'token_expired',
                    'message': 'Token has expired'
                }), 403
                
            except jwt.InvalidAudienceError:
                return jsonify({
                    'success': False,
                    'error': 'invalid_audience',
                    'message': 'Token audience mismatch'
                }), 401
                
            except jwt.InvalidIssuerError:
                return jsonify({
                    'success': False,
                    'error': 'invalid_issuer',
                    'message': 'Token issuer mismatch'
                }), 401
                
            except jwt.InvalidTokenError as e:
                try:
                    current_app.logger.error(f"Token verification failed: {e}")
                except RuntimeError:
                    print(f"Token verification failed: {e}")
                return jsonify({
                    'success': False,
                    'error': 'invalid_token',
                    'message': 'Invalid authentication token'
                }), 403
        
        return f(*args, **kwargs)
    
    return decorated