from contextlib import contextmanager
import hashlib
import hmac
import os
import secrets
import sqlite3
import threading
import time
from pathlib import Path
from typing import Callable

from internal.chat_names import generate_name

RETENTION_SECONDS = 7 * 24 * 60 * 60
MAX_MESSAGE_LENGTH = 1000


class InvalidMessage(ValueError):
    pass


class RateLimited(ValueError):
    pass


class NamingUnavailable(Exception):
    pass


class ChatStore:
    def __init__(self, path: Path, clock: Callable[[], float] = time.time, name_generator: Callable[[], str | None] = generate_name):
        self.path = Path(path)
        self.clock = clock
        self.name_generator = name_generator
        self._lock = threading.RLock()
        self._last_post: dict[tuple[str, str], float] = {}
        self._name_attempts: dict[str, list[float]] = {}
        self._naming: set[bytes] = set()
        self._ready = False

    @contextmanager
    def _connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            pass
        else:
            os.close(fd)
        conn = sqlite3.connect(self.path, timeout=5)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA secure_delete = ON')
        if not self._ready:
            version = conn.execute('PRAGMA user_version').fetchone()[0]
            if version > 2:
                conn.close()
                raise RuntimeError('Unsupported chat database version')
            migration = Path(__file__).resolve().parent.parent / 'migrations' / '0001_chat.sql'
            if version < 1:
                conn.executescript(migration.read_text(encoding='utf-8'))
            if version < 2:
                conn.executescript((migration.parent / '0002_chat_names.sql').read_text(encoding='utf-8'))
            conn.execute('INSERT OR IGNORE INTO chat_settings(key, value) VALUES (?, ?)',
                         ('name_key', secrets.token_bytes(32)))
            conn.commit()
            self._ready = True
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def _name(self, identity: tuple[str, str], ip: str) -> str:
        with self._lock, self._connect() as conn:
            key = conn.execute("SELECT value FROM chat_settings WHERE key = 'name_key'").fetchone()[0]
            digest = hmac.new(key, ('%s:%s' % identity).encode(), hashlib.sha256).digest()
            row = conn.execute('SELECT name FROM chat_names WHERE identity_hash = ?', (digest,)).fetchone()
            if row:
                return row['name']
            now = time.monotonic()
            self._name_attempts = {key: [t for t in times if now - t < 60] for key, times in self._name_attempts.items() if any(now - t < 60 for t in times)}
            attempts = self._name_attempts.setdefault(ip, [])
            if digest in self._naming or len(attempts) >= 10:
                raise NamingUnavailable()
            attempts.append(now)
            self._naming.add(digest)
        try:
            return self._generate_and_reserve(digest)
        finally:
            with self._lock:
                self._naming.discard(digest)

    def _generate_and_reserve(self, digest: bytes) -> str:
        # Do not hold a database transaction or the chat lock while waiting for AI.
        for _ in range(3):
            name = self.name_generator()
            if not name:
                raise NamingUnavailable()
            with self._lock, self._connect() as conn:
                row = conn.execute('SELECT name FROM chat_names WHERE identity_hash = ?', (digest,)).fetchone()
                if row:
                    return row['name']
                if conn.execute('SELECT 1 FROM chat_messages WHERE name = ? COLLATE NOCASE LIMIT 1', (name,)).fetchone():
                    continue
                now = self.clock()
                conn.execute('INSERT OR IGNORE INTO chat_names(identity_hash, name, created_at, updated_at) VALUES (?, ?, ?, ?)', (digest, name, now, now))
                row = conn.execute('SELECT name FROM chat_names WHERE identity_hash = ?', (digest,)).fetchone()
                if row:
                    return row['name']
        raise NamingUnavailable()

    @staticmethod
    def _log(conn: sqlite3.Connection, method: str, status: int, name: str,
             ip: str, user_agent: str, now: float) -> None:
        conn.execute('INSERT INTO chat_request_log(method, path, status, actor, client_ip, user_agent, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)',
                     (method, '/api/chat', status, name, ip[:255], user_agent[:255], now))

    def read(self, identity: tuple[str, str], ip: str, user_agent: str) -> dict:
        now = self.clock()
        name = self._name(identity, ip)
        with self._lock, self._connect() as conn:
            rows = conn.execute('SELECT id, name, body, created_at FROM chat_messages WHERE deleted_at IS NULL AND created_at > ? ORDER BY id DESC LIMIT 100',
                                (now - RETENTION_SECONDS,)).fetchall()
            self._log(conn, 'GET', 200, name, ip, user_agent, now)
            return {'name': name, 'messages': [dict(row) for row in reversed(rows)]}

    def send(self, identity: tuple[str, str], text: str, ip: str, user_agent: str) -> dict:
        now = self.clock()
        text = text.strip()
        if not text or len(text) > MAX_MESSAGE_LENGTH:
            raise InvalidMessage()
        name = self._name(identity, ip)
        with self._lock, self._connect() as conn:
            self._last_post = {key: seen for key, seen in self._last_post.items() if now - seen < 2}
            if identity in self._last_post:
                self._log(conn, 'POST', 429, name, ip, user_agent, now)
                conn.commit()
                raise RateLimited()
            cursor = conn.execute('INSERT INTO chat_messages(name, body, created_at, updated_at) VALUES (?, ?, ?, ?)',
                                  (name, text, now, now))
            self._log(conn, 'POST', 201, name, ip, user_agent, now)
            self._last_post[identity] = now
            return {'id': cursor.lastrowid, 'name': name, 'body': text, 'created_at': now}

    def cleanup(self) -> None:
        now = self.clock()
        with self._lock, self._connect() as conn:
            cutoff = now - RETENTION_SECONDS
            conn.execute('DELETE FROM chat_messages WHERE created_at <= ?', (cutoff,))
            conn.execute('DELETE FROM chat_audit_log WHERE created_at <= ?', (cutoff,))
            conn.execute('DELETE FROM chat_request_log WHERE created_at <= ?', (cutoff,))
