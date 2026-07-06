"""A tiny in-memory store for reference/attempt graphs.

Deliberately trivial (a dict behind a lock) so the API has somewhere to keep
submitted graphs during a session. Swap for a real database by implementing the
same three methods.
"""

from __future__ import annotations

import threading
import uuid
from typing import Optional

from .models import ReactionGraph


class GraphStore:
    def __init__(self) -> None:
        self._graphs: dict[str, ReactionGraph] = {}
        self._lock = threading.Lock()

    def put(self, graph: ReactionGraph, graph_id: Optional[str] = None) -> str:
        gid = graph_id or graph.id or uuid.uuid4().hex[:12]
        graph.id = gid
        with self._lock:
            self._graphs[gid] = graph
        return gid

    def get(self, graph_id: str) -> Optional[ReactionGraph]:
        with self._lock:
            return self._graphs.get(graph_id)

    def all_ids(self) -> list[str]:
        with self._lock:
            return list(self._graphs)
