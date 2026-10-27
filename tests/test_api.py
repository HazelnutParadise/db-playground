import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from internal.presence import PresenceTracker
from main import app


class ApiTests(unittest.TestCase):
    def test_presence_counts_distinct_tabs_and_rejects_invalid_ids(self):
        with patch('internal.api.presence', PresenceTracker()), TestClient(app) as client:
            first = {'visitor_id': '00000000-0000-4000-8000-000000000001'}
            second = {'visitor_id': '00000000-0000-4000-8000-000000000002'}
            self.assertEqual(client.post('/api/presence', json=first).json(), {'count': 1})
            self.assertEqual(client.post('/api/presence', json=first).json(), {'count': 1})
            self.assertEqual(client.post('/api/presence', json=second).json(), {'count': 2})
            self.assertEqual(client.post('/api/presence', json={'visitor_id': 'invalid'}).status_code, 422)

    def test_database_list_includes_new_versions_and_preserves_existing(self):
        with TestClient(app) as client:
            versions = client.get('/api/databases').json()['databases']
        for version in ['26.10', '26.7', '9.7', '9.6', '9.5', '9.4', '9.3', '9.2', '9.1', '9.0', '5.5']:
            self.assertIn(version, versions['mysql'])
        for version in ['18', '17', '9.4']:
            self.assertIn(version, versions['postgres'])
