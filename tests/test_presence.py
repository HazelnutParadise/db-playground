import unittest
from unittest.mock import patch
from uuid import UUID

from internal.presence import PresenceTracker


class PresenceTrackerTests(unittest.TestCase):
    def test_refresh_and_expiry(self):
        tracker = PresenceTracker(timeout=90)
        first = UUID('00000000-0000-4000-8000-000000000001')
        second = UUID('00000000-0000-4000-8000-000000000002')
        with patch('internal.presence.monotonic', side_effect=[0, 20, 40, 100, 131]):
            self.assertEqual(tracker.record(first), 1)
            self.assertEqual(tracker.record(first), 1)
            self.assertEqual(tracker.record(second), 2)
            self.assertEqual(tracker.record(second), 2)
            self.assertEqual(tracker.record(second), 1)

    def test_capacity_rejects_new_visitors_but_allows_refresh(self):
        tracker = PresenceTracker(timeout=90, capacity=1)
        first = UUID('00000000-0000-4000-8000-000000000001')
        second = UUID('00000000-0000-4000-8000-000000000002')
        self.assertEqual(tracker.record(first), 1)
        self.assertIsNone(tracker.record(second))
        self.assertEqual(tracker.record(first), 1)
