import logging
import time
from urllib.parse import urlsplit

import httpx
from authlib.integrations.base_client.errors import OAuthError
from fastapi import APIRouter, Request
from joserfc.errors import JoseError
from fastapi.responses import JSONResponse, RedirectResponse

logger = logging.getLogger(__name__)
auth_router = APIRouter()


def current_member_id(request: Request) -> str | None:
    user = request.scope.get('session', {}).get('user')
    if not isinstance(user, dict):
        return None
    subject = user.get('sub')
    expires = user.get('expires_at')
    if not isinstance(subject, str) or not subject or not isinstance(expires, (int, float)) or expires <= time.time():
        return None
    return subject


@auth_router.get('/api/auth/me')
async def current_user(request: Request) -> JSONResponse:
    if request.app.state.logto is None:
        return JSONResponse({'configured': False, 'user': None}, headers={'Cache-Control': 'no-store'})
    user = request.session.get('user')
    if not isinstance(user, dict) or user.get('expires_at', 0) <= time.time():
        request.session.pop('user', None)
        user = None
    return JSONResponse({'configured': True, 'user': {'name': user['name']} if user else None}, headers={'Cache-Control': 'no-store'})


@auth_router.get('/auth/login')
async def login(request: Request):
    client = request.app.state.logto
    if client is None:
        return JSONResponse({'error': '登入尚未設定'}, status_code=503)
    try:
        return await client.authorize_redirect(request, request.app.state.logto_redirect_uri)
    except (httpx.HTTPError, OAuthError, ValueError):
        logger.warning('Logto authorization unavailable')
        return JSONResponse({'error': '登入服務暫時無法使用'}, status_code=503)


@auth_router.get('/auth/callback')
async def callback(request: Request):
    client = request.app.state.logto
    if client is None:
        return JSONResponse({'error': '登入尚未設定'}, status_code=503)
    try:
        token = await client.authorize_access_token(request)
        info = token.get('userinfo')
        if not isinstance(info, dict) or not isinstance(info.get('sub'), str) or not info['sub'] or not isinstance(info.get('exp'), (int, float)) or info['exp'] <= time.time():
            raise ValueError('Missing or expired user identity')
        name = info.get('name') or info.get('username') or '會員'
        if not isinstance(name, str):
            raise ValueError('Invalid display name')
        request.session.clear()
        request.session['user'] = {'name': name[:200], 'sub': info['sub'], 'expires_at': info['exp']}
        return RedirectResponse('/', status_code=303, headers={'Cache-Control': 'no-store'})
    except (OAuthError, JoseError, httpx.HTTPError, ValueError, KeyError):
        logger.warning('Logto sign-in could not be completed')
        return RedirectResponse('/?auth_error=1', status_code=303, headers={'Cache-Control': 'no-store'})


@auth_router.post('/auth/logout')
async def logout(request: Request):
    if request.app.state.logto is None:
        return JSONResponse({'error': '登入尚未設定'}, status_code=503)
    parts = urlsplit(request.app.state.logto_redirect_uri)
    expected_origin = f'{parts.scheme}://{parts.netloc}'
    if request.headers.get('origin') != expected_origin:
        return JSONResponse({'error': 'Invalid origin'}, status_code=403)
    request.session.clear()
    return RedirectResponse('/', status_code=303, headers={'Cache-Control': 'no-store'})
