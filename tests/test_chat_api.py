import tempfile
import time
import unittest
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware

from internal.chat import ChatStore
from internal.chat_api import chat_router


class ChatApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        app = FastAPI()
        app.add_middleware(SessionMiddleware, secret_key='test-secret')
        app.state.chat = ChatStore(Path(self.temp.name) / 'chat.sqlite3', name_generator=lambda: '索引海獺')
        app.include_router(chat_router)
        @app.post('/test-login')
        def login(request: Request):
            request.session['user'] = {'sub': 'same-member', 'expires_at': time.time() + 60}
            return {}
        self.client = TestClient(app)
        self.visitor = str(uuid4())

    def test_anonymous_read_and_post(self):
        headers = {'X-Visitor-ID': self.visitor}
        before = self.client.get('/api/chat', headers=headers).json()
        result = self.client.post('/api/chat', headers={'Origin': 'http://testserver'}, json={'visitor_id': self.visitor, 'text': '<b>hello</b>'})
        self.assertEqual(result.status_code, 201)
        after = self.client.get('/api/chat', headers=headers).json()
        self.assertEqual(before['name'], result.json()['name'])
        self.assertEqual(after['messages'][0]['body'], '<b>hello</b>')
        self.assertEqual(self.client.post('/api/chat', headers={'Origin': 'http://evil.example'}, json={'visitor_id': self.visitor, 'text': 'bad'}).status_code, 403)
        self.assertEqual(self.client.get('/api/chat', headers={'X-Visitor-ID': 'invalid'}).status_code, 422)

    def test_member_name_is_the_same_across_devices(self):
        self.client.post('/test-login')
        first = self.client.get('/api/chat', headers={'X-Visitor-ID': self.visitor}).json()['name']
        second = self.client.get('/api/chat', headers={'X-Visitor-ID': str(uuid4())}).json()['name']
        self.assertEqual(first, second)
        self.assertNotIn('same-member', first)
