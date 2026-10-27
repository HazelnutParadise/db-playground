import os
from urllib.parse import urlsplit

from authlib.integrations.starlette_client import OAuth
from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware
from fastapi.responses import HTMLResponse

from internal.api import api_router
from internal.auth import auth_router
from internal.chat_api import chat_router, chat_lifespan
from internal.private_chat_api import private_router

app = FastAPI(docs_url=None, redoc_url=None, lifespan=chat_lifespan)
app.state.logto = None
app.state.logto_redirect_uri = ''

settings = {name: os.environ.get(name, '').strip() for name in (
    'LOGTO_APP_ID', 'LOGTO_APP_SECRET', 'LOGTO_SESSION_SECRET', 'LOGTO_REDIRECT_URI'
)}
if any(settings.values()):
    if not all(settings.values()) or len(settings['LOGTO_SESSION_SECRET']) < 32:
        raise RuntimeError('Logto 設定不完整，或工作階段密鑰長度不足 32 字元')
    redirect = urlsplit(settings['LOGTO_REDIRECT_URI'])
    if (redirect.scheme not in ('http', 'https') or not redirect.netloc or redirect.path != '/auth/callback'
            or redirect.query or redirect.fragment or redirect.username or redirect.password
            or (redirect.scheme == 'http' and redirect.hostname not in ('localhost', '127.0.0.1', '::1'))):
        raise RuntimeError('LOGTO_REDIRECT_URI 必須是有效的 HTTPS 回呼網址，或本機測試網址')
    oauth = OAuth()
    app.state.logto = oauth.register(
        name='logto',
        client_id=settings['LOGTO_APP_ID'],
        client_secret=settings['LOGTO_APP_SECRET'],
        server_metadata_url='https://auth.hazelnut-paradise.com/oidc/.well-known/openid-configuration',
        client_kwargs={'scope': 'openid profile', 'code_challenge_method': 'S256'},
    )
    app.state.logto_redirect_uri = settings['LOGTO_REDIRECT_URI']
    app.add_middleware(SessionMiddleware, secret_key=settings['LOGTO_SESSION_SECRET'],
                       same_site='lax', https_only=redirect.scheme == 'https', max_age=43200)

app.include_router(api_router)
app.include_router(auth_router)
app.include_router(chat_router)
app.include_router(private_router)


@app.get('/')
def index() -> HTMLResponse:
    with open('../frontend/index.html', 'r') as f:
        html_content: str = f.read()
    return HTMLResponse(html_content)


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)
