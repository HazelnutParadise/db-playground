import tempfile
from contextlib import closing
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
import unittest
from pathlib import Path

from internal.chat import ChatStore, InvalidMessage, RateLimited, NamingUnavailable


class ChatStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.now = 1_800_000_000.0
        self.path = Path(self.temp.name) / 'chat.sqlite3'
        self.names = iter(['索引海獺', '查詢松鼠', '資料水豚', '表格鯨魚'])
        self.store = ChatStore(self.path, clock=lambda: self.now, name_generator=lambda: next(self.names))

    def test_anonymous_names_are_stable_and_private(self):
        a = ('member', 'private-subject')
        b = ('browser', 'browser-id')
        self.store.send(a, 'Hello', '127.0.0.1', 'test')
        self.now += 3
        self.store.send(b, 'World', '127.0.0.1', 'test')
        data = ChatStore(self.path, clock=lambda: self.now, name_generator=lambda: self.fail("name should already exist")).read(a, '127.0.0.1', 'test')
        self.assertEqual(len(data['messages']), 2)
        self.assertEqual(data['name'], data['messages'][0]['name'])
        self.assertNotEqual(data['messages'][0]['name'], data['messages'][1]['name'])
        self.assertNotIn('private-subject', str(data))

    def test_expires_on_schedule_and_is_not_readable(self):
        self.store.send(('browser', 'one'), 'old', '127.0.0.1', 'test')
        self.now += 7 * 24 * 60 * 60
        self.store.cleanup()
        self.assertEqual(self.store.read(('browser', 'one'), '127.0.0.1', 'test')['messages'], [])
        with closing(sqlite3.connect(self.path)) as connection:
            self.assertEqual(connection.execute('SELECT count(*) FROM chat_messages').fetchone()[0], 0)

    def test_invalid_and_rate_limited_messages(self):
        identity = ('browser', 'one')
        for text in ('', '  ', 'x' * 1001):
            with self.assertRaises(InvalidMessage):
                self.store.send(identity, text, '127.0.0.1', 'test')
        self.store.send(identity, 'valid', '127.0.0.1', 'test')
        with self.assertRaises(RateLimited):
            self.store.send(identity, 'too fast', '127.0.0.1', 'test')
        self.now += 2
        self.store.send(identity, 'allowed', '127.0.0.1', 'test')

    def test_names_are_unique_even_if_ai_repeats(self):
        names = iter(['索引海獺', '索引海獺', '查詢水豚'])
        store = ChatStore(self.path, clock=lambda: self.now, name_generator=lambda: next(names))
        first = store.read(('browser', 'one'), '', '')['name']
        second = store.read(('browser', 'two'), '', '')['name']
        self.assertEqual((first, second), ('索引海獺', '查詢水豚'))

    def test_no_fake_name_if_ai_unavailable(self):
        store = ChatStore(self.path, clock=lambda: self.now, name_generator=lambda: None)
        with self.assertRaises(NamingUnavailable):
            store.read(('browser', 'one'), '', '')

    def test_upgrade_v1_preserves_existing_messages_and_key(self):
        with closing(sqlite3.connect(self.path)) as db, db:
            migration = Path(__file__).resolve().parents[1] / 'backend/migrations/0001_chat.sql'
            db.executescript(migration.read_text())
            db.execute("INSERT INTO chat_settings VALUES ('name_key', ?)", (b'x' * 32,))
            db.execute("INSERT INTO chat_messages(name, body, created_at, updated_at) VALUES ('舊名稱', '舊訊息', ?, ?)", (self.now, self.now))
        data = self.store.read(('browser', 'one'), '', '')
        self.assertEqual(data['messages'][0]['body'], '舊訊息')
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0], 7)
            self.assertEqual(db.execute("SELECT value FROM chat_settings WHERE key = 'name_key'").fetchone()[0], b'x' * 32)

    def test_concurrent_stores_reserve_only_one_name_per_identity(self):
        barrier = threading.Barrier(2)
        def generate(name):
            barrier.wait(timeout=5)
            return name
        first = ChatStore(self.path, name_generator=lambda: generate('索引海獺'))
        second = ChatStore(self.path, name_generator=lambda: generate('查詢水豚'))
        # Initialize migrations before racing the two generators.
        with first._connect():
            pass
        with ThreadPoolExecutor(max_workers=2) as pool:
            jobs = [pool.submit(store.read, ('browser', 'same'), '', '') for store in (first, second)]
            results = [job.result(timeout=10)['name'] for job in jobs]
        self.assertEqual(results[0], results[1])
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM chat_names').fetchone()[0], 1)

    def test_invalid_message_does_not_call_ai(self):
        store = ChatStore(self.path, name_generator=lambda: self.fail('AI should not be called'))
        with self.assertRaises(InvalidMessage):
            store.send(('browser', 'one'), ' ', '', '')

    def test_retry_after_ai_failure(self):
        names = iter([None, '索引海獺'])
        store = ChatStore(self.path, name_generator=lambda: next(names))
        with self.assertRaises(NamingUnavailable):
            store.read(('browser', 'one'), '', '')
        self.assertEqual(store.read(('browser', 'one'), '', '')['name'], '索引海獺')
