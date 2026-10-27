import asyncio
import logging
import os
import sqlite3
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel

from internal.auth import current_member_id
from internal.chat import ChatStore, InvalidMessage, RateLimited, NamingUnavailable

logger = logging.getLogger(__name__)
chat_router = APIRouter(prefix='/api/chat')


@asynccontextmanager
async def chat_lifespan(app):
    path = Path(os.environ.get('CHAT_DB_PATH') or Path(__file__).resolve().parent.parent / 'data' / 'chat.sqlite3')
    app.state.chat = ChatStore(path)

    async def clean_periodically():
        while True:
            if path.exists():
                try:
                    await asyncio.to_thread(app.state.chat.cleanup)
                except (OSError, sqlite3.Error, RuntimeError):
                    logger.exception('Chat cleanup failed')
            await asyncio.sleep(60)

    task = asyncio.create_task(clean_periodically())
    try:
        yield
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


def identity(request: Request, visitor: UUID) -> tuple[str, str]:
    member = current_member_id(request)
    return ('member', member) if member else ('browser', str(visitor))


def metadata(request: Request) -> tuple[str, str]:
    return (request.client.host if request.client else '', request.headers.get('user-agent', ''))


class ChatMessage(BaseModel):
    visitor_id: UUID
    text: str


@chat_router.get('')
def get_chat(request: Request, x_visitor_id: UUID = Header()):
    try:
        return request.app.state.chat.read(identity(request, x_visitor_id), *metadata(request))
    except NamingUnavailable:
        raise HTTPException(503, '暱稱暫時無法產生，請稍後再試')
    except (OSError, sqlite3.Error, RuntimeError):
        logger.exception('Chat read failed')
        raise HTTPException(503, '聊天室暫時無法使用')


@chat_router.post('', status_code=201)
def post_chat(request: Request, message: ChatMessage):
    origin = request.headers.get('origin', '')
    parsed = urlsplit(origin)
    if parsed.scheme not in ('http', 'https') or parsed.netloc.lower() != request.headers.get('host', '').lower():
        raise HTTPException(403, '無效的請求來源')
    try:
        return request.app.state.chat.send(identity(request, message.visitor_id), message.text, *metadata(request))
    except NamingUnavailable:
        raise HTTPException(503, '暱稱暫時無法產生，請稍後再試')
    except InvalidMessage:
        raise HTTPException(400, '請輸入 1 至 1000 字的訊息')
    except RateLimited:
        raise HTTPException(429, '請稍等一下再發送')
    except (OSError, sqlite3.Error, RuntimeError):
        logger.exception('Chat send failed')
        raise HTTPException(503, '聊天室暫時無法使用')
