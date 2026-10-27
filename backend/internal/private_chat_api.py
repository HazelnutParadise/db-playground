import base64
import hashlib
import hmac
import json
import re
import secrets
import sqlite3
import time
import unicodedata
from urllib.parse import urlsplit

from cryptography.fernet import Fernet
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from internal.chat import RETENTION_SECONDS
from internal.chat_attachments import serialize_attachment

private_router = APIRouter(prefix='/api/private-channels')
_COOKIE = 'db_private_session'
_CODE_LIFETIME = 600
_GLOBAL_FAILURE_KEY = hashlib.sha256(b'private-code-global-failures').digest()


def origin_check(request):
    origin = urlsplit(request.headers.get('origin', ''))
    if origin.scheme not in ('http', 'https') or origin.netloc.lower() != request.headers.get('host', '').lower():
        raise HTTPException(403, '無效的請求來源')


def identity(request, response):
    token = request.cookies.get(_COOKIE, '')
    if not re.fullmatch(r'[A-Za-z0-9_-]{43}', token):
        token = secrets.token_urlsafe(32)
        response.set_cookie(_COOKIE, token, httponly=True, secure=request.url.scheme == 'https', samesite='lax', max_age=365 * 24 * 3600, path='/')
    return hashlib.sha256(token.encode()).digest()


def clean_label(value, limit):
    value = unicodedata.normalize('NFKC', value).strip()
    if not 1 <= len(value) <= limit or any(unicodedata.category(ch).startswith('C') for ch in value):
        raise HTTPException(400, '頻道名稱和暱稱不可空白或過長')
    return value


def crypto(conn):
    key = conn.execute("SELECT value FROM chat_settings WHERE key='name_key'").fetchone()[0]
    cipher_key = hmac.new(key, b'private-code-encryption', hashlib.sha256).digest()
    hash_key = hmac.new(key, b'private-code-lookup', hashlib.sha256).digest()
    return Fernet(base64.urlsafe_b64encode(cipher_key)), hash_key


def code_hash(key, code):
    return hmac.new(key, code.encode(), hashlib.sha256).digest()


def fresh_code(conn, key):
    for _ in range(50):
        code = f'{secrets.randbelow(1_000_000):06d}'
        if not conn.execute('SELECT 1 FROM private_channels WHERE code_hash=?', (code_hash(key, code),)).fetchone():
            return code
    raise HTTPException(503, '暫時無法產生配對碼，請稍後再試')


def check_member(conn, channel_id, person):
    member = conn.execute('SELECT m.nickname, c.name FROM private_members m JOIN private_channels c ON c.id=m.channel_id WHERE m.channel_id=? AND m.identity_hash=? AND m.deleted_at IS NULL AND c.deleted_at IS NULL', (channel_id, person)).fetchone()
    if not member:
        raise HTTPException(404, '找不到頻道')
    return member


def audit(conn, request, status, actor, now):
    conn.execute('INSERT INTO chat_request_log(method,path,status,actor,client_ip,user_agent,created_at) VALUES (?,?,?,?,?,?,?)', (request.method, '/api/private-channels', status, actor, (request.client.host if request.client else '')[:255], request.headers.get('user-agent','')[:255], now))


def limit_attempt(conn, request, person, now):
    ip = (request.client.host if request.client else '').encode()
    keys = (hashlib.sha256(b'ip:' + ip).digest(), hashlib.sha256(b'user:' + person).digest())
    conn.execute('DELETE FROM private_attempts WHERE created_at <= ?', (now-60,))
    if any(conn.execute('SELECT COUNT(*) FROM private_attempts WHERE identity_hash=?', (key,)).fetchone()[0] >= 10 for key in keys):
        audit(conn, request, 429, 'private', now)
        conn.commit()
        raise HTTPException(429, '嘗試次數過多，請稍後再試')
    conn.executemany('INSERT INTO private_attempts(identity_hash,created_at) VALUES (?,?)', [(key, now) for key in keys])


class CreateChannel(BaseModel):
    name: str
    nickname: str


class JoinChannel(BaseModel):
    code: str
    nickname: str


class NicknameChange(BaseModel):
    nickname: str


class PrivateMessage(BaseModel):
    text: str
    attachment: dict | None = None


@private_router.get('')
def list_channels(request: Request, response: Response):
    person = identity(request, response)
    store = request.app.state.chat
    with store._lock, store._connect() as conn:
        cipher, _ = crypto(conn)
        rows = conn.execute('SELECT c.id,c.name,c.code_encrypted,c.code_expires_at,c.owner_hash,m.nickname FROM private_channels c JOIN private_members m ON c.id=m.channel_id WHERE m.identity_hash=? AND m.deleted_at IS NULL AND c.deleted_at IS NULL ORDER BY c.created_at', (person,)).fetchall()
        channels = []
        for row in rows:
            channel = {'id':row['id'], 'name':row['name'], 'nickname':row['nickname']}
            if hmac.compare_digest(row['owner_hash'], person):
                channel['code'] = cipher.decrypt(row['code_encrypted']).decode()
                channel['code_expires_at'] = row['code_expires_at']
            channels.append(channel)
        audit(conn, request, 200, 'private', time.time())
    response.headers['Cache-Control'] = 'no-store'
    return {'channels':channels}


@private_router.post('', status_code=201)
def create_channel(data: CreateChannel, request: Request, response: Response):
    origin_check(request)
    name = clean_label(data.name, 50)
    nickname = clean_label(data.nickname, 24)
    person = identity(request, response)
    now = time.time()
    channel_id = secrets.token_urlsafe(18)
    store = request.app.state.chat
    with store._lock, store._connect() as conn:
        limit_attempt(conn, request, person, now)
        cipher, key = crypto(conn)
        code = fresh_code(conn, key)
        expires = now + _CODE_LIFETIME
        conn.execute('INSERT INTO private_channels(id,name,code_hash,code_encrypted,owner_hash,created_at,updated_at,code_expires_at) VALUES (?,?,?,?,?,?,?,?)', (channel_id, name, code_hash(key,code), cipher.encrypt(code.encode()), person, now, now, expires))
        conn.execute('INSERT INTO private_members(channel_id,identity_hash,nickname,nickname_key,created_at,updated_at) VALUES (?,?,?,?,?,?)', (channel_id, person, nickname, nickname.casefold(), now, now))
        audit(conn, request, 201, 'private', now)
    response.headers['Cache-Control'] = 'no-store'
    return {'id':channel_id, 'name':name, 'nickname':nickname, 'code':code, 'code_expires_at':expires}


@private_router.post('/join')
def join_channel(data: JoinChannel, request: Request, response: Response):
    origin_check(request)
    nickname = clean_label(data.nickname, 24)
    code = data.code.strip().replace('-', '').upper()
    person = identity(request, response)
    now = time.time()
    store = request.app.state.chat
    with store._lock, store._connect() as conn:
        limit_attempt(conn, request, person, now)
        if conn.execute('SELECT COUNT(*) FROM private_attempts WHERE identity_hash=?', (_GLOBAL_FAILURE_KEY,)).fetchone()[0] >= 30:
            audit(conn, request, 429, 'private', now)
            conn.commit()
            raise HTTPException(429, '嘗試次數過多，請稍後再試')
        _, key = crypto(conn)
        row = conn.execute('SELECT id,name,owner_hash,code_expires_at FROM private_channels WHERE code_hash=? AND deleted_at IS NULL', (code_hash(key,code),)).fetchone()
        if not row or (row['code_expires_at'] is not None and row['code_expires_at'] <= now and not hmac.compare_digest(row['owner_hash'], person)):
            conn.execute('INSERT INTO private_attempts(identity_hash,created_at) VALUES (?,?)', (_GLOBAL_FAILURE_KEY, now))
            audit(conn, request, 404, 'private', now)
            conn.commit()
            raise HTTPException(404, '配對碼無效')
        old = conn.execute('SELECT nickname, deleted_at FROM private_members WHERE channel_id=? AND identity_hash=?', (row['id'],person)).fetchone()
        if old and old['deleted_at'] is None:
            nickname = old['nickname']
        else:
            try:
                if old:
                    conn.execute('UPDATE private_members SET nickname=?, nickname_key=?, deleted_at=NULL, updated_at=? WHERE channel_id=? AND identity_hash=?', (nickname, nickname.casefold(), now, row['id'], person))
                else:
                    conn.execute('INSERT INTO private_members(channel_id,identity_hash,nickname,nickname_key,created_at,updated_at) VALUES (?,?,?,?,?,?)', (row['id'], person, nickname, nickname.casefold(), now, now))
            except sqlite3.IntegrityError:
                audit(conn, request, 409, 'private', now)
                conn.commit()
                raise HTTPException(409, '這個暱稱已被使用')
        audit(conn, request, 200, 'private', now)
    response.headers['Cache-Control'] = 'no-store'
    return {'id':row['id'],'name':row['name'],'nickname':nickname}


@private_router.get('/{channel_id}/messages')
def read_messages(channel_id: str, request: Request, response: Response):
    person = identity(request, response)
    now = time.time()
    store = request.app.state.chat
    with store._lock, store._connect() as conn:
        member = check_member(conn, channel_id, person)
        rows = conn.execute('SELECT id,name,body,created_at,attachment FROM private_messages WHERE channel_id=? AND created_at>? AND deleted_at IS NULL ORDER BY id DESC LIMIT 100', (channel_id,now-RETENTION_SECONDS)).fetchall()
        messages = [dict(row) for row in reversed(rows)]
        for message in messages:
            message['attachment'] = json.loads(message['attachment']) if message['attachment'] else None
        audit(conn, request, 200, 'private', now)
    response.headers['Cache-Control'] = 'no-store'
    return {'name':member['nickname'], 'messages':messages}


@private_router.post('/{channel_id}/messages', status_code=201)
def send_message(channel_id: str, data: PrivateMessage, request: Request, response: Response):
    origin_check(request)
    text = data.text.strip()
    try:
        attachment = serialize_attachment(data.attachment)
    except (ValueError, TypeError, OverflowError):
        raise HTTPException(400, '附件格式不正確或超過大小上限')
    if not text or len(text) > 1000:
        raise HTTPException(400, '訊息長度不正確')
    person = identity(request, response)
    now = time.time()
    store = request.app.state.chat
    with store._lock, store._connect() as conn:
        member = check_member(conn, channel_id, person)
        last = store._last_post.get(('private', person.hex()), 0)
        if now - last < 2:
            raise HTTPException(429, '請稍等一下再發送')
        cursor = conn.execute('INSERT INTO private_messages(channel_id,name,body,attachment,created_at,updated_at) VALUES (?,?,?,?,?,?)', (channel_id, member['nickname'], text, attachment, now, now))
        store._last_post[('private', person.hex())] = now
        audit(conn, request, 201, 'private', now)
    return {'id':cursor.lastrowid,'name':member['nickname'],'body':text,'created_at':now,'attachment':data.attachment}


@private_router.patch('/{channel_id}/nickname')
def change_nickname(channel_id: str, data: NicknameChange, request: Request, response: Response):
    origin_check(request)
    nickname = clean_label(data.nickname, 24)
    person = identity(request, response)
    now = time.time()
    store = request.app.state.chat
    with store._lock, store._connect() as conn:
        check_member(conn, channel_id, person)
        try:
            conn.execute('UPDATE private_members SET nickname=?, nickname_key=?, updated_at=? WHERE channel_id=? AND identity_hash=? AND deleted_at IS NULL', (nickname, nickname.casefold(), now, channel_id, person))
        except sqlite3.IntegrityError:
            audit(conn, request, 409, 'private', now)
            conn.commit()
            raise HTTPException(409, '這個暱稱已被使用')
        audit(conn, request, 200, 'private', now)
    response.headers['Cache-Control'] = 'no-store'
    return {'nickname': nickname}


@private_router.delete('/{channel_id}/membership', status_code=204)
def leave_channel(channel_id: str, request: Request, response: Response):
    origin_check(request)
    person = identity(request, response)
    now = time.time()
    store = request.app.state.chat
    with store._lock, store._connect() as conn:
        check_member(conn, channel_id, person)
        # Reserve a prefix rejected by clean_label so the old nickname becomes available.
        conn.execute("UPDATE private_members SET nickname_key=char(0) || id, deleted_at=?, updated_at=? WHERE channel_id=? AND identity_hash=? AND deleted_at IS NULL", (now, now, channel_id, person))
        audit(conn, request, 204, 'private', now)
    return Response(status_code=204, headers={'Cache-Control': 'no-store'})


@private_router.post('/{channel_id}/code')
def regenerate_code(channel_id: str, request: Request, response: Response):
    origin_check(request)
    person = identity(request, response)
    now = time.time()
    store = request.app.state.chat
    with store._lock, store._connect() as conn:
        check_member(conn, channel_id, person)
        row = conn.execute('SELECT owner_hash FROM private_channels WHERE id=? AND deleted_at IS NULL', (channel_id,)).fetchone()
        if not row or not hmac.compare_digest(row['owner_hash'], person):
            raise HTTPException(404, '找不到頻道')
        limit_attempt(conn, request, person, now)
        cipher, key = crypto(conn)
        code = fresh_code(conn, key)
        expires = now + _CODE_LIFETIME
        conn.execute('UPDATE private_channels SET code_hash=?, code_encrypted=?, code_expires_at=?, updated_at=? WHERE id=?', (code_hash(key,code), cipher.encrypt(code.encode()), expires, now, channel_id))
        audit(conn, request, 200, 'private', now)
    response.headers['Cache-Control'] = 'no-store'
    return {'code':code, 'code_expires_at':expires}
