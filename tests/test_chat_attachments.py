import tempfile
import unittest
from pathlib import Path
from internal.chat import ChatStore, InvalidMessage

class ChatAttachmentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'chat.sqlite3'
        self.now = 1_800_000_000
        self.store = ChatStore(self.path, clock=lambda: self.now, name_generator=lambda: '索引海獺')

    def test_code_preserves_indentation_and_restarts(self):
        attachment = {'type': 'code', 'label': 'Query SQL', 'content': 'SELECT\n  1;'}
        self.store.send(('browser', 'one'), '看看程式', '', '', attachment=attachment)
        restored = ChatStore(self.path, clock=lambda: self.now).read(('browser', 'one'), '', '')
        self.assertEqual(restored['messages'][0]['attachment'], attachment)

    def test_table_roundtrip_and_seven_day_expiry(self):
        attachment = {'type': 'table', 'label': '執行結果', 'tables': [{'columns':['a', 'b'], 'rows':[['<b>', None], [42, True]]}]}
        self.store.send(('browser', 'one'), '看看結果', '', '', attachment=attachment)
        self.assertEqual(self.store.read(('browser', 'one'), '', '')['messages'][0]['attachment'], attachment)
        self.now += 7 * 24 * 60 * 60
        self.store.cleanup()
        self.assertEqual(self.store.read(('browser', 'one'), '', '')['messages'], [])

    def test_invalid_or_oversized_attachment_rejected_before_naming(self):
        store = ChatStore(self.path, name_generator=lambda: self.fail('must not invoke AI'))
        for attachment in ({'type':'html', 'content':'<script>'}, {'type':'code', 'label':'x', 'content':'x' * 40000}, {'type':'table', 'label':'x', 'tables':[{'columns':['a'], 'rows':[['x', 'y']]}]}):
            with self.subTest(attachment=attachment['type']):
                with self.assertRaises(InvalidMessage):
                    store.send(('browser', 'one'), 'x', '', '', attachment=attachment)
