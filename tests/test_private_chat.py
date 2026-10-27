import tempfile
import time
import unittest
from pathlib import Path
from fastapi import FastAPI
from fastapi.testclient import TestClient
from internal.chat import ChatStore
from internal.private_chat_api import private_router

class PrivateChatTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        app = FastAPI()
        app.state.chat = ChatStore(Path(self.temp.name) / 'chat.sqlite3')
        app.include_router(private_router)
        self.owner = TestClient(app)
        self.guest = TestClient(app)
        self.other = TestClient(app)
        self.origin = {'Origin':'http://testserver'}

    def test_create_join_and_private_messages(self):
        response = self.owner.post('/api/private-channels', headers=self.origin, json={'name':'資料庫小組','nickname':'小貓'})
        self.assertEqual(response.status_code, 201)
        channel = response.json()
        self.assertTrue(channel['code'])
        channel_id = channel['id']
        self.assertEqual(self.other.get(f'/api/private-channels/{channel_id}/messages').status_code, 404)
        self.assertEqual(self.guest.post('/api/private-channels/join', headers=self.origin, json={'code':channel['code'],'nickname':'水豚'}).status_code, 200)
        sent = self.guest.post(f'/api/private-channels/{channel_id}/messages', headers=self.origin, json={'text':'你好','attachment':None})
        self.assertEqual(sent.status_code, 201)
        messages = self.owner.get(f'/api/private-channels/{channel_id}/messages').json()['messages']
        self.assertEqual(messages[0]['name'], '水豚')
        self.assertEqual(messages[0]['body'], '你好')
        self.assertEqual(self.other.get('/api/private-channels').json()['channels'], [])
        self.assertNotIn('code', self.guest.get('/api/private-channels').json()['channels'][0])
        self.assertEqual(self.owner.get('/api/private-channels').json()['channels'][0]['code'], channel['code'])

    def test_required_fields_bad_code_and_cross_origin(self):
        for payload in ({'name':'','nickname':'暱稱'}, {'name':'頻道','nickname':' '}):
            self.assertEqual(self.owner.post('/api/private-channels', headers=self.origin, json=payload).status_code, 400)
        self.assertEqual(self.guest.post('/api/private-channels/join', headers=self.origin, json={'code':'bad','nickname':'人'}).status_code, 404)
        self.assertEqual(self.owner.post('/api/private-channels', headers={'Origin':'https://evil.test'}, json={'name':'頻道','nickname':'人'}).status_code, 403)

    def test_guest_identity_not_client_selected(self):
        channel = self.owner.post('/api/private-channels', headers=self.origin, json={'name':'群組','nickname':'甲'}).json()
        self.assertEqual(self.other.get(f"/api/private-channels/{channel['id']}/messages", headers={'X-Visitor-ID':'anything'}).status_code, 404)

    def test_attachment_isolated_and_message_expiry(self):
        room = self.owner.post('/api/private-channels', headers=self.origin, json={'name':'一','nickname':'甲'}).json()
        other_room = self.other.post('/api/private-channels', headers=self.origin, json={'name':'二','nickname':'乙'}).json()
        attachment = {'type':'code','label':'Query SQL','content':'SELECT 1;'}
        sent = self.owner.post(f"/api/private-channels/{room['id']}/messages", headers=self.origin, json={'text':'程式','attachment':attachment})
        self.assertEqual(sent.status_code, 201)
        self.assertEqual(self.owner.get(f"/api/private-channels/{room['id']}/messages").json()['messages'][0]['attachment'], attachment)
        self.assertEqual(self.other.get(f"/api/private-channels/{other_room['id']}/messages").json()['messages'], [])
        self.assertEqual(self.other.get(f"/api/private-channels/{room['id']}/messages").status_code, 404)
        store = self.owner.app.state.chat
        with store._connect() as db:
            db.execute('UPDATE private_messages SET created_at=?', (time.time()-7*86400-1,))
        store.cleanup()
        self.assertEqual(self.owner.get(f"/api/private-channels/{room['id']}/messages").json()['messages'], [])
        self.assertEqual(len(self.owner.get('/api/private-channels').json()['channels']), 1)

    def test_code_attempts_are_rate_limited(self):
        for _ in range(10):
            result = self.guest.post('/api/private-channels/join', headers=self.origin, json={'code':'wrong','nickname':'甲'})
            self.assertEqual(result.status_code, 404)
        self.assertEqual(self.guest.post('/api/private-channels/join', headers=self.origin, json={'code':'wrong','nickname':'甲'}).status_code, 429)

    def test_duplicate_nickname_rejected(self):
        room = self.owner.post('/api/private-channels', headers=self.origin, json={'name':'群組','nickname':'小貓'}).json()
        response = self.guest.post('/api/private-channels/join', headers=self.origin, json={'code':room['code'],'nickname':'小貓'})
        self.assertEqual(response.status_code, 409)

    def test_multiple_channels_nickname_changes_and_leave_rejoin(self):
        first = self.owner.post('/api/private-channels', headers=self.origin, json={'name':'一','nickname':'甲'}).json()
        second = self.other.post('/api/private-channels', headers=self.origin, json={'name':'二','nickname':'乙'}).json()
        self.assertEqual(self.guest.post('/api/private-channels/join', headers=self.origin, json={'code':first['code'],'nickname':'小貓'}).status_code, 200)
        self.assertEqual(self.guest.post('/api/private-channels/join', headers=self.origin, json={'code':second['code'],'nickname':'水豚'}).status_code, 200)
        self.assertEqual(len(self.guest.get('/api/private-channels').json()['channels']), 2)
        changed = self.guest.patch(f"/api/private-channels/{first['id']}/nickname", headers=self.origin, json={'nickname':'狐狸'})
        self.assertEqual(changed.status_code, 200)
        self.assertEqual(self.guest.get(f"/api/private-channels/{first['id']}/messages").json()['name'], '狐狸')
        self.assertEqual(self.guest.get(f"/api/private-channels/{second['id']}/messages").json()['name'], '水豚')
        self.assertEqual(self.guest.delete(f"/api/private-channels/{first['id']}/membership", headers=self.origin).status_code, 204)
        self.assertEqual(self.guest.get(f"/api/private-channels/{first['id']}/messages").status_code, 404)
        self.assertEqual(len(self.guest.get('/api/private-channels').json()['channels']), 1)
        self.assertEqual(self.guest.post('/api/private-channels/join', headers=self.origin, json={'code':first['code'],'nickname':'再加入'}).status_code, 200)
        self.assertEqual(self.guest.get(f"/api/private-channels/{first['id']}/messages").json()['name'], '再加入')

    def test_leave_frees_nickname_and_cannot_change_others(self):
        room = self.owner.post('/api/private-channels', headers=self.origin, json={'name':'一','nickname':'甲'}).json()
        self.guest.post('/api/private-channels/join', headers=self.origin, json={'code':room['code'],'nickname':'乙'})
        self.assertEqual(self.guest.patch(f"/api/private-channels/{room['id']}/nickname", headers=self.origin, json={'nickname':'甲'}).status_code, 409)
        self.assertEqual(self.other.patch(f"/api/private-channels/{room['id']}/nickname", headers=self.origin, json={'nickname':'別人'}).status_code, 404)
        self.assertEqual(self.guest.delete(f"/api/private-channels/{room['id']}/membership", headers=self.origin).status_code, 204)
        self.assertEqual(self.other.post('/api/private-channels/join', headers=self.origin, json={'code':room['code'],'nickname':'乙'}).status_code, 200)

    def test_owner_can_leave_rejoin_and_recover_code(self):
        room = self.owner.post('/api/private-channels', headers=self.origin, json={'name':'一','nickname':'甲'}).json()
        self.assertEqual(self.owner.delete(f"/api/private-channels/{room['id']}/membership", headers=self.origin).status_code, 204)
        self.assertEqual(self.owner.get('/api/private-channels').json()['channels'], [])
        self.assertEqual(self.owner.post('/api/private-channels/join', headers=self.origin, json={'code':room['code'],'nickname':'甲新'}).status_code, 200)
        self.assertEqual(self.owner.get('/api/private-channels').json()['channels'][0]['code'], room['code'])

    def test_old_messages_keep_name_and_exit_does_not_delete_history(self):
        room = self.owner.post('/api/private-channels', headers=self.origin, json={'name':'一','nickname':'舊名'}).json()
        url = f"/api/private-channels/{room['id']}"
        self.owner.post(url+'/messages', headers=self.origin, json={'text':'舊訊息'})
        self.assertEqual(self.owner.patch(url+'/nickname', headers=self.origin, json={'nickname':'新名'}).status_code, 200)
        self.assertEqual(self.owner.get(url+'/messages').json()['messages'][0]['name'], '舊名')
        self.assertEqual(self.owner.delete(url+'/membership', headers=self.origin).status_code, 204)
        self.assertEqual(self.owner.post('/api/private-channels/join', headers=self.origin, json={'code':room['code'],'nickname':'回來'}).status_code, 200)
        self.assertEqual(self.owner.get(url+'/messages').json()['messages'][0]['body'], '舊訊息')

    def test_membership_operations_reject_cross_origin(self):
        room = self.owner.post('/api/private-channels', headers=self.origin, json={'name':'一','nickname':'甲'}).json()
        url = f"/api/private-channels/{room['id']}"
        self.assertEqual(self.owner.patch(url+'/nickname', headers={'Origin':'https://evil.test'}, json={'nickname':'乙'}).status_code, 403)
        self.assertEqual(self.owner.delete(url+'/membership', headers={'Origin':'https://evil.test'}).status_code, 403)
        self.assertEqual(self.owner.get(url+'/messages').json()['name'], '甲')
