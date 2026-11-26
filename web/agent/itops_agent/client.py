"""Enrollment and the outbound WebSocket loop."""
import asyncio
import contextlib
import json
import logging
import random
import socket
import ssl
import urllib.error
import urllib.request
from urllib.parse import urlsplit

from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed, InvalidStatus

from . import VERSION
from .bundle import Bundle
from .executor import Executor, os_info
from .paths import bundle_dir
from .state import State

log = logging.getLogger(__name__)

LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


class EnrollError(Exception):
    pass


def check_server_url(url: str, allow_insecure: bool = False) -> str:
    url = url.strip().rstrip("/")
    parts = urlsplit(url)
    if parts.scheme not in ("https", "http") or not parts.hostname:
        raise ValueError("server URL must look like https://prov.example.com")
    if parts.scheme == "http" and parts.hostname not in LOCAL_HOSTS and not allow_insecure:
        raise ValueError("plain http is only allowed for localhost testing; use https")
    return url


def ws_url(server_url: str) -> str:
    parts = urlsplit(server_url)
    scheme = "wss" if parts.scheme == "https" else "ws"
    return f"{scheme}://{parts.netloc}{parts.path}/api/agent/ws"


def enroll(server_url: str, code: str) -> State:
    body = json.dumps(
        {
            "code": code,
            "hostname": socket.gethostname(),
            "agent_version": VERSION,
            "os_info": os_info(),
        }
    ).encode()
    req = urllib.request.Request(
        server_url + "/api/agent/enroll",
        data=body,
        headers={"Content-Type": "application/json", "User-Agent": f"itops-agent/{VERSION}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30, context=ssl.create_default_context()) as r:
            data = json.loads(r.read())
    except urllib.error.HTTPError as e:
        detail = ""
        with contextlib.suppress(Exception):
            detail = json.loads(e.read()).get("detail", "")
        raise EnrollError(f"server said {e.code}: {detail or e.reason}") from None
    except urllib.error.URLError as e:
        raise EnrollError(f"cannot reach server: {e.reason}") from None
    state = State(server_url=server_url, machine_id=data["machine_id"], token=data["token"])
    state.save()
    return state


def actions_prefix(root) -> str:
    return "actions" if (root / "actions").is_dir() else "web/actions"


class Agent:
    def __init__(self, state: State, bundle: Bundle | None = None) -> None:
        self.state = state
        root = bundle_dir()
        self.bundle = bundle or Bundle(root)
        self.ws = None
        self.heartbeat = 30
        self.executor = Executor(self.bundle, self._send, actions_prefix(root))
        self._send_lock = asyncio.Lock()
        self._stop = asyncio.Event()

    async def _send(self, msg: dict) -> None:
        ws = self.ws
        if ws is None:
            return  # disconnected: output is lost, job_done is reported via reconnect hello
        async with self._send_lock:
            await ws.send(json.dumps(msg))

    def stop(self) -> None:
        self._stop.set()

    async def run_forever(self) -> None:
        backoff = 1.0
        while not self._stop.is_set():
            delay = None
            try:
                await self._session()
                backoff = 1.0  # clean session: reconnect quickly
            except InvalidStatus as e:
                code = e.response.status_code
                if code in (401, 403):
                    log.error("server rejected this agent (HTTP %s): revoked or bad token", code)
                    delay = 600.0  # don't hammer the server; retry rarely
                else:
                    log.warning("server returned HTTP %s", code)
            except (OSError, ConnectionClosed, TimeoutError) as e:
                log.warning("connection problem: %s", e)
            except Exception:
                log.exception("unexpected error in agent loop")
            if self._stop.is_set():
                break
            if delay is None:
                delay = backoff * random.uniform(0.7, 1.3)  # jitter: fleets don't reconnect in lockstep
                backoff = min(backoff * 2, 60.0)
            log.info("reconnecting in %.0fs", delay)
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._stop.wait(), delay)
        await self.executor.shutdown()

    async def _session(self) -> None:
        url = ws_url(self.state.server_url)
        log.info("connecting to %s", url)
        async with connect(
            url,
            additional_headers={"Authorization": f"Bearer {self.state.token}"},
            user_agent_header=f"itops-agent/{VERSION}",
            open_timeout=20,
            ping_interval=20,
            ping_timeout=20,
            max_size=8 * 1024 * 1024,
        ) as ws:
            self.ws = ws
            try:
                await ws.send(
                    json.dumps(
                        {
                            "type": "hello",
                            "agent_version": VERSION,
                            "hostname": socket.gethostname(),
                            "os_info": os_info(),
                            "running_jobs": self.executor.running_ids(),
                        }
                    )
                )
                beat = asyncio.create_task(self._heartbeat())
                try:
                    async for raw in ws:
                        await self._handle(json.loads(raw))
                        if self._stop.is_set():
                            break
                finally:
                    beat.cancel()
            finally:
                self.ws = None

    async def _heartbeat(self) -> None:
        while True:
            await asyncio.sleep(self.heartbeat)
            with contextlib.suppress(Exception):
                await self._send({"type": "heartbeat"})

    async def _handle(self, msg: dict) -> None:
        kind = msg.get("type")
        if kind == "welcome":
            self.heartbeat = max(5, int(msg.get("heartbeat_seconds", 30)))
            log.info("connected as machine %s", msg.get("machine_id"))
        elif kind == "job":
            log.info("job %s: %s", msg.get("job_id"), msg.get("action"))
            self.executor.start(msg)
        elif kind == "cancel":
            log.info("cancel %s", msg.get("job_id"))
            await self.executor.cancel(str(msg.get("job_id", "")))
