import time
import unittest
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import RedirectResponse

from internal.auth import auth_router


class AuthTests(unittest.TestCase):
    def setUp(self):
        self.app = FastAPI()
        self.app.add_middleware(SessionMiddleware, secret_key='x' * 40, https_only=False, same_site='lax')
        self.app.include_router(auth_router)
        self.app.state.logto = None
        self.app.state.logto_redirect_uri = 'http://testserver/auth/callback'
        self.client = TestClient(self.app)

    def test_unconfigured_auth_keeps_site_available(self):
        self.assertEqual(self.client.get('/api/auth/me').json(), {'configured': False, 'user': None})
        self.assertEqual(self.client.get('/auth/login').status_code, 503)

    def test_validated_login_logout_and_expiry(self):
        logto = self.app.state.logto = AsyncMock()
        logto.authorize_redirect.return_value = RedirectResponse('https://example.com/authorize', status_code=302)
        logto.authorize_access_token.return_value = {'userinfo': {'sub': 'user-1', 'name': 'Alice', 'exp': int(time.time()) + 3600}}
        self.assertEqual(self.client.get('/auth/login', follow_redirects=False).status_code, 302)
        self.assertEqual(self.client.get('/auth/callback?code=valid&state=valid', follow_redirects=False).status_code, 303)
        self.assertEqual(self.client.get('/api/auth/me').json()['user'], {'name': 'Alice'})
        self.assertEqual(self.client.post('/auth/logout', headers={'origin': 'http://testserver'}, follow_redirects=False).status_code, 303)
        self.assertIsNone(self.client.get('/api/auth/me').json()['user'])
        logto.authorize_access_token.return_value = {'userinfo': {'sub': 'user-1', 'exp': int(time.time()) - 1}}
        self.client.get('/auth/callback?code=expired&state=valid', follow_redirects=False)
        self.assertIsNone(self.client.get('/api/auth/me').json()['user'])

    def test_bad_callback_and_cross_origin_logout(self):
        logto = self.app.state.logto = AsyncMock()
        from authlib.integrations.base_client.errors import OAuthError
        logto.authorize_access_token.side_effect = OAuthError(error='mismatching_state')
        self.assertEqual(self.client.get('/auth/callback?code=x&state=bad', follow_redirects=False).status_code, 303)
        self.assertIsNone(self.client.get('/api/auth/me').json()['user'])
        self.assertEqual(self.client.post('/auth/logout', headers={'origin': 'https://evil.example'}, follow_redirects=False).status_code, 403)


class RealOidcValidationTests(unittest.TestCase):
    def test_pkce_state_nonce_and_signature(self):
        from urllib.parse import parse_qs, urlsplit
        from unittest.mock import patch
        from authlib.integrations.starlette_client import OAuth
        from joserfc import jwt
        from joserfc.jwk import RSAKey

        app = FastAPI()
        app.add_middleware(SessionMiddleware, secret_key='s' * 40, https_only=False)
        app.include_router(auth_router)
        oauth = OAuth()
        logto = oauth.register(name='test', client_id='app-id', client_secret='secret',
                               server_metadata_url='https://id.example/.well-known/openid-configuration',
                               client_kwargs={'scope': 'openid profile', 'code_challenge_method': 'S256'})
        app.state.logto = logto
        app.state.logto_redirect_uri = 'http://testserver/auth/callback'
        metadata = {'issuer': 'https://id.example', 'authorization_endpoint': 'https://id.example/authorize',
                    'token_endpoint': 'https://id.example/token', 'jwks_uri': 'https://id.example/jwks',
                    'id_token_signing_alg_values_supported': ['RS256']}
        key = RSAKey.generate_key(auto_kid=True)
        client = TestClient(app)
        with patch.object(logto, 'load_server_metadata', AsyncMock(return_value=metadata)), \
             patch.object(logto, 'fetch_jwk_set', AsyncMock(return_value={'keys': [key.as_dict()]})), \
             patch.object(logto, 'fetch_access_token', AsyncMock()) as fetch:
            response = client.get('/auth/login', follow_redirects=False)
            params = parse_qs(urlsplit(response.headers['location']).query)
            self.assertEqual(params['code_challenge_method'], ['S256'])
            self.assertIn('code_challenge', params)
            bad = client.get('/auth/callback?code=x&state=wrong', follow_redirects=False)
            self.assertIn('auth_error=1', bad.headers['location'])
            fetch.assert_not_awaited()
            response = client.get('/auth/login', follow_redirects=False)
            params = parse_qs(urlsplit(response.headers['location']).query)
            now = int(time.time())
            claims = {'iss': 'https://id.example', 'sub': 'one', 'aud': 'app-id', 'iat': now,
                      'exp': now + 3600, 'nonce': params['nonce'][0], 'name': 'Verified'}
            fetch.return_value = {'id_token': jwt.encode({'alg': 'RS256', 'kid': key.as_dict()['kid']}, claims, key)}
            result = client.get('/auth/callback', params={'code': 'x', 'state': params['state'][0]}, follow_redirects=False)
            self.assertEqual(result.headers['location'], '/')
            self.assertEqual(client.get('/api/auth/me').json()['user'], {'name': 'Verified'})
            replay = client.get('/auth/callback', params={'code': 'x', 'state': params['state'][0]}, follow_redirects=False)
            self.assertIn('auth_error=1', replay.headers['location'])
            self.assertEqual(client.get('/api/auth/me').json()['user'], {'name': 'Verified'})
            client.post('/auth/logout', headers={'origin': 'http://testserver'}, follow_redirects=False)
            for tampering in ('signature', 'nonce', 'issuer', 'audience'):
                response = client.get('/auth/login', follow_redirects=False)
                params = parse_qs(urlsplit(response.headers['location']).query)
                claims['nonce'] = params['nonce'][0]
                claims['iss'] = 'https://id.example'
                claims['aud'] = 'app-id'
                if tampering == 'nonce':
                    claims['nonce'] = 'wrong'
                elif tampering == 'issuer':
                    claims['iss'] = 'https://evil.example'
                elif tampering == 'audience':
                    claims['aud'] = 'different-app'
                signing_key = RSAKey.generate_key() if tampering == 'signature' else key
                fetch.return_value = {'id_token': jwt.encode({'alg': 'RS256', 'kid': key.as_dict()['kid']}, claims, signing_key)}
                rejected = client.get('/auth/callback', params={'code': 'x', 'state': params['state'][0]}, follow_redirects=False)
                self.assertIn('auth_error=1', rejected.headers['location'], tampering)
                self.assertIsNone(client.get('/api/auth/me').json()['user'], tampering)
