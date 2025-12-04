import os
import requests
import jwt

from jwt.algorithms import RSAAlgorithm
from typing import Optional, Dict, Any
from datetime import datetime
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security = HTTPBearer()

_JWKS_CACHE = {"keys": None, "fetched_at": None}

def _get_config(key: str, default=None):
    return os.getenv(key, default)

def _get_jwks_url() -> Optional[str]:
    jwks_url = _get_config('COGNITO_JWKS_URL') or _get_config('JWKS_URL')
    if jwks_url:
        return jwks_url
    
    pool_id = _get_config('COGNITO_USER_POOL_ID') or _get_config('COGNITO_POOL_ID')
    region = _get_config('COGNITO_REGION') or _get_config('AWS_REGION', 'ap-southeast-1')
    
    if pool_id and region:
        return f"https://cognito-idp.{region}.amazonaws.com/{pool_id}/.well-known/jwks.json"
    return None

def _get_issuer() -> Optional[str]:
    issuer = _get_config('JWT_ISSUER') or _get_config('COGNITO_ISSUER')
    if issuer:
        return issuer
    
    pool_id = _get_config('COGNITO_USER_POOL_ID') or _get_config('COGNITO_POOL_ID')
    region = _get_config('COGNITO_REGION') or _get_config('AWS_REGION', 'ap-southeast-1')
    
    if pool_id and region:
        return f"https://cognito-idp.{region}.amazonaws.com/{pool_id}"
    return None

def _fetch_jwks() -> Optional[list]:
    """Fetch JWKS từ Cognito"""
    url = _get_jwks_url()
    if not url:
        return None
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        return response.json().get('keys', [])
    except Exception as e:
        print(f"Failed to fetch JWKS: {e}")
        return None

def _get_jwks_keys() -> Optional[list]:
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
    keys = _get_jwks_keys()
    if not keys:
        return None
    
    for jwk in keys:
        if jwk.get('kid') == kid:
            try:
                return RSAAlgorithm.from_jwk(jwk)
            except Exception as e:
                print(f"Failed to convert JWK: {e}")
                return None
    return None

def _verify_token(token: str) -> Dict[str, Any]:
    try:
        header = jwt.get_unverified_header(token)
    except jwt.InvalidTokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f'Invalid token header: {str(e)}'
        )
    
    kid = header.get('kid')
    if not kid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Token missing kid in header'
        )
    
    public_key = _get_public_key(kid)
    if not public_key:
        _JWKS_CACHE['keys'] = None
        public_key = _get_public_key(kid)
        if not public_key:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail='Public key not found for kid'
            )
    
    try:
        unverified_payload = jwt.decode(token, options={'verify_signature': False})
    except Exception:
        unverified_payload = {}
    
    token_use = unverified_payload.get('token_use')
    
    decode_options = {
        'algorithms': ['RS256'],
        'leeway': int(_get_config('JWT_LEEWAY', '0'))
    }
    
    issuer = _get_issuer()
    if issuer:
        decode_options['issuer'] = issuer
    
    app_client_id = _get_config('COGNITO_APP_CLIENT_ID')
    
    if token_use == 'id':
        if app_client_id:
            decode_options['audience'] = app_client_id
        else:
            decode_options['options'] = {'verify_aud': False}
    else:
        decode_options['options'] = {'verify_aud': False}
    
    try:
        payload = jwt.decode(token, key=public_key, **decode_options)
    except jwt.exceptions.MissingRequiredClaimError as e:
        if 'aud' in str(e) and token_use == 'access':
            decode_options['options'] = {'verify_aud': False}
            payload = jwt.decode(token, key=public_key, **decode_options)
        else:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Token has expired')
    except jwt.InvalidAudienceError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Token audience mismatch')
    except jwt.InvalidIssuerError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Token issuer mismatch')
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f'Invalid token: {str(e)}')

    if token_use == 'access' and app_client_id:
        token_client_id = payload.get('client_id')
        if token_client_id and token_client_id != app_client_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Token client_id mismatch')

    return payload

def _build_user_object(token: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        'id_token': token,
        'userId': payload.get('sub'),
        'email': payload.get('email'),
        'username': payload.get('preferred_username') or payload.get('cognito:username') or payload.get('username'),
        'name': payload.get('name'),
        'groups': payload.get('cognito:groups', []),
    }

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No authentication token provided"
        )

    allow_insecure = str(_get_config('ALLOW_INSECURE_JWT', 'false')).lower() in ('true', '1', 'yes')
    jwks_url = _get_jwks_url()

    if not jwks_url and allow_insecure:
        try:
            payload = jwt.decode(token, options={'verify_signature': False})
            return _build_user_object(token, payload)
        except Exception as e:
             raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))
    
    if not jwks_url and not allow_insecure:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="JWT verification not configured"
        )

    payload = _verify_token(token)
    return _build_user_object(token, payload)