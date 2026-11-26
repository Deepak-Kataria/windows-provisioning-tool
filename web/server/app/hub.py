"""In-memory hub for live agent connections and job output subscribers.

Single API worker for now. To run several workers, back this with Redis pub/sub:
each worker keeps its own sockets, and job/cancel messages are routed through Redis.
"""
import asyncio
import contextlib
from dataclasses import dataclass, field
from typing import Any

from fastapi import WebSocket


@dataclass
class AgentConn:
    machine_id: str
    ws: WebSocket
    last_seen_written: float = 0.0
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def send(self, msg: dict[str, Any]) -> None:
        async with self.lock:
            await self.ws.send_json(msg)


class Hub:
    def __init__(self) -> None:
        self.agents: dict[str, AgentConn] = {}
        self.subscribers: dict[str, set[asyncio.Queue]] = {}

    # ---------------------------------------------------------- agents

    async def register(self, conn: AgentConn) -> None:
        old = self.agents.get(conn.machine_id)
        self.agents[conn.machine_id] = conn
        if old is not None and old is not conn:
            with contextlib.suppress(Exception):
                await old.ws.close(code=4409, reason="replaced by newer connection")

    def unregister(self, conn: AgentConn) -> None:
        if self.agents.get(conn.machine_id) is conn:
            del self.agents[conn.machine_id]

    def is_online(self, machine_id: str) -> bool:
        return machine_id in self.agents

    def online_ids(self) -> set[str]:
        return set(self.agents)

    async def send(self, machine_id: str, msg: dict[str, Any]) -> bool:
        conn = self.agents.get(machine_id)
        if conn is None:
            return False
        try:
            await conn.send(msg)
            return True
        except Exception:
            self.unregister(conn)
            return False

    async def kick(self, machine_id: str, code: int = 4403, reason: str = "revoked") -> None:
        conn = self.agents.pop(machine_id, None)
        if conn is not None:
            with contextlib.suppress(Exception):
                await conn.ws.close(code=code, reason=reason)

    # ---------------------------------------------------------- job output fan-out

    def subscribe(self, job_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=1000)
        self.subscribers.setdefault(job_id, set()).add(q)
        return q

    def unsubscribe(self, job_id: str, q: asyncio.Queue) -> None:
        subs = self.subscribers.get(job_id)
        if subs is not None:
            subs.discard(q)
            if not subs:
                del self.subscribers[job_id]

    def publish(self, job_id: str, event: dict[str, Any]) -> None:
        for q in list(self.subscribers.get(job_id, ())):
            with contextlib.suppress(asyncio.QueueFull):  # slow viewer drops lines, never blocks
                q.put_nowait(event)


hub = Hub()
