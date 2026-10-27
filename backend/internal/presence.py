from threading import Lock
from time import monotonic
from uuid import UUID


class PresenceTracker:
    def __init__(self, timeout: int = 90, capacity: int = 10000):
        self.timeout = timeout
        self.capacity = capacity
        self._visitors: dict[UUID, tuple[float, tuple[str, str]]] = {}
        self._lock = Lock()

    def record(self, visitor: UUID, member_id: str | None = None) -> int | None:
        now = monotonic()
        with self._lock:
            self._visitors = {key: seen for key, seen in self._visitors.items()
                              if now - seen[0] < self.timeout}
            if visitor not in self._visitors and len(self._visitors) >= self.capacity:
                return None
            identity = ('member', member_id) if member_id else ('browser', str(visitor))
            self._visitors[visitor] = (now, identity)
            return len({entry[1] for entry in self._visitors.values()})
