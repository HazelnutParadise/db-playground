import time
import unittest
from uuid import UUID
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware
from internal.api import api_router
from internal.presence import PresenceTracker


class PresencePeopleTests(unittest.TestCase):
    def test_same_member_across_devices_and_identity_transitions(self):
        tracker = PresenceTracker()
        a = UUID('00000000-0000-4000-8000-000000000001')
        b = UUID('00000000-0000-4000-8000-000000000002')
        self.assertEqual(tracker.record(a), 1)
        self.assertEqual(tracker.record(a, 'member-1'), 1)
        self.assertEqual(tracker.record(b, 'member-1'), 1)
        self.assertEqual(tracker.record(a), 2)
        self.assertEqual(tracker.record(b, 'member-2'), 2)

    def test_expired_member_is_anonymous_and_no_session_is_supported(self):
        app = FastAPI()
        app.add_middleware(SessionMiddleware, secret_key='x' * 40)
        app.include_router(api_router)
        @app.get('/session/{state}')
        def session(request: __import__('fastapi').Request, state: str):
            request.session['user'] = {'sub': 'one', 'expires_at': time.time() + (100 if state == 'active' else -100)}
            return {}
        tracker = PresenceTracker()
        with patch('internal.api.presence', tracker), TestClient(app) as a, TestClient(app) as b:
            a.get('/session/active'); b.get('/session/active')
            x = {'visitor_id': '00000000-0000-4000-8000-000000000001'}
            y = {'visitor_id': '00000000-0000-4000-8000-000000000002'}
            self.assertEqual(a.post('/api/presence', json=x).json()['count'], 1)
            self.assertEqual(b.post('/api/presence', json=y).json()['count'], 1)
            a.get('/session/expired')
            self.assertEqual(a.post('/api/presence', json=x).json()['count'], 2)
        plain = FastAPI(); plain.include_router(api_router)
        with patch('internal.api.presence', PresenceTracker()), TestClient(plain) as client:
            self.assertEqual(client.post('/api/presence', json=x).json()['count'], 1)
