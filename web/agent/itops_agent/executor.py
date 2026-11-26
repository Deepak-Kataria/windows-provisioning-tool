"""Runs allowlisted actions.

The agent loads the same web/actions/*.json files as the server (from its signed bundle),
validates params again, and maps them to a fixed script + named arguments. No shell is ever
used and no string from the server is ever executed as code.

"agent" block in an action file:
  {"type": "builtin", "name": "ping"}
  {"type": "powershell",
   "script": "get_system_info.ps1",          # file in scripts/
   "args": {"NewName": "new_name"},          # -NewName <params.new_name>; bool -> switch
   "env": {"ITOPS_PASSWORD": "password"},    # secrets go via env, never the command line
   "output": "text" | "json" | "kv",         # json: stdout is the result; kv: KEY:value lines
   "stream": true}                           # send stdout lines live to the server
"""
import asyncio
import contextlib
import json
import logging
import os
import platform
import socket
import subprocess
import time
from collections.abc import Awaitable, Callable
from typing import Any

from jsonschema import Draft202012Validator

from . import VERSION
from .bundle import Bundle, BundleError

log = logging.getLogger(__name__)

Send = Callable[[dict[str, Any]], Awaitable[None]]
MAX_RESULT_BYTES = 4 * 1024 * 1024


class ActionSpec:
    def __init__(self, raw: dict[str, Any], rel: str) -> None:
        self.id: str = raw["id"]
        self.rel = rel
        schema = dict(raw.get("params", {}))
        schema.setdefault("type", "object")
        schema.setdefault("additionalProperties", False)
        self.validator = Draft202012Validator(schema)
        self.agent: dict[str, Any] = raw.get("agent", {})
        self.timeout = int(raw.get("timeout_seconds", 300))


def load_actions(bundle: Bundle, prefix: str) -> dict[str, ActionSpec]:
    out: dict[str, ActionSpec] = {}
    for rel in bundle.listed(prefix):
        if not rel.endswith(".json"):
            continue
        path = bundle.check(rel)
        spec = ActionSpec(json.loads(path.read_text(encoding="utf-8")), rel)
        out[spec.id] = spec
    return out


class OutputSink:
    """Batches output lines so a chatty script does not send one message per line."""

    def __init__(self, send: Send, job_id: str) -> None:
        self.send = send
        self.job_id = job_id
        self.buf: list[dict[str, str]] = []
        self.last = time.monotonic()

    async def line(self, data: str, stream: str = "stdout") -> None:
        self.buf.append({"stream": stream, "data": data})
        if len(self.buf) >= 100 or time.monotonic() - self.last > 0.3:
            await self.flush()

    async def flush(self) -> None:
        if self.buf:
            batch, self.buf = self.buf, []
            await self.send({"type": "job_output", "job_id": self.job_id, "lines": batch})
        self.last = time.monotonic()


class Cancelled(Exception):
    pass


class Executor:
    def __init__(self, bundle: Bundle, send: Send, actions_prefix: str) -> None:
        self.bundle = bundle
        self.send = send
        self.actions = load_actions(bundle, actions_prefix)
        self.tasks: dict[str, asyncio.Task] = {}
        self.procs: dict[str, asyncio.subprocess.Process] = {}
        self.cancelled: set[str] = set()
        log.info("loaded %d actions: %s", len(self.actions), ", ".join(sorted(self.actions)))

    def running_ids(self) -> list[str]:
        return list(self.tasks)

    # ------------------------------------------------------------ entry points

    def start(self, msg: dict[str, Any]) -> None:
        job_id = str(msg.get("job_id", ""))
        if not job_id or job_id in self.tasks:
            return
        task = asyncio.create_task(self._run(job_id, msg))
        self.tasks[job_id] = task
        task.add_done_callback(lambda _t: self.tasks.pop(job_id, None))

    async def cancel(self, job_id: str) -> None:
        if job_id not in self.tasks:
            return
        self.cancelled.add(job_id)
        proc = self.procs.get(job_id)
        if proc is not None:
            await _kill_tree(proc)
        else:
            self.tasks[job_id].cancel()

    async def shutdown(self) -> None:
        for job_id in list(self.tasks):
            await self.cancel(job_id)

    # ------------------------------------------------------------ job lifecycle

    async def _done(self, job_id: str, status: str, exit_code=None, result=None, error="") -> None:
        if result is not None and len(json.dumps(result)) > MAX_RESULT_BYTES:
            result, error = None, (error + " result too large, dropped").strip()
        with contextlib.suppress(Exception):
            await self.send(
                {
                    "type": "job_done",
                    "job_id": job_id,
                    "status": status,
                    "exit_code": exit_code,
                    "result": result,
                    "error": error,
                }
            )

    async def _run(self, job_id: str, msg: dict[str, Any]) -> None:
        action_id = msg.get("action")
        params = msg.get("params") or {}
        spec = self.actions.get(action_id)
        if spec is None:
            await self._done(job_id, "failed", error=f"agent does not know action {action_id!r}")
            return
        errors = list(spec.validator.iter_errors(params))
        if errors:
            await self._done(job_id, "failed", error=f"invalid params: {errors[0].message}")
            return
        timeout = min(int(msg.get("timeout_seconds") or spec.timeout), spec.timeout)
        sink = OutputSink(self.send, job_id)
        try:
            await self.send({"type": "job_started", "job_id": job_id})
            self.bundle.check(spec.rel)  # action file unchanged since start
            kind = spec.agent.get("type")
            if kind == "builtin":
                code, result = await asyncio.wait_for(self._builtin(spec, params, sink), timeout)
            elif kind == "powershell":
                code, result = await self._powershell(job_id, spec, params, sink, timeout)
            else:
                raise BundleError(f"unsupported action type {kind!r}")
            await sink.flush()
            if job_id in self.cancelled:
                await self._done(job_id, "cancelled", code, error="cancelled")
            else:
                await self._done(job_id, "succeeded" if code == 0 else "failed", code, result)
        except (asyncio.CancelledError, Cancelled):
            await sink.flush()
            await self._done(job_id, "cancelled", error="cancelled")
        except TimeoutError:
            await sink.flush()
            await self._done(job_id, "failed", error=f"timed out after {timeout}s")
        except BundleError as e:
            log.error("bundle check failed for %s: %s", action_id, e)
            await self._done(job_id, "failed", error=f"bundle check failed: {e}")
        except Exception as e:  # never let one job kill the agent
            log.exception("job %s crashed", job_id)
            await sink.flush()
            await self._done(job_id, "failed", error=f"{type(e).__name__}: {e}")
        finally:
            self.cancelled.discard(job_id)
            self.procs.pop(job_id, None)

    # ------------------------------------------------------------ builtins

    async def _builtin(self, spec: ActionSpec, params: dict[str, Any], sink: OutputSink):
        name = spec.agent.get("name")
        if name == "ping":
            msg = params.get("message", "")
            await sink.line(f"pong {msg}".strip())
            return 0, {"echo": msg, "hostname": socket.gethostname(), "agent_version": VERSION}
        raise BundleError(f"unknown builtin {name!r}")

    # ------------------------------------------------------------ powershell

    def _build_command(self, spec: ActionSpec, params: dict[str, Any]) -> tuple[list[str], dict]:
        a = spec.agent
        script = self.bundle.check(f"scripts/{a['script']}")
        cmd = [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
        ]
        for ps_name, key in a.get("args", {}).items():
            if key not in params:
                continue
            value = params[key]
            if isinstance(value, bool):
                if value:
                    cmd.append(f"-{ps_name}")
            elif isinstance(value, list):
                cmd += [f"-{ps_name}", ",".join(str(v) for v in value)]
            else:
                cmd += [f"-{ps_name}", str(value)]
        env = dict(os.environ)
        for env_name, key in a.get("env", {}).items():
            if key in params:
                env[env_name] = str(params[key])
        return cmd, env

    async def _powershell(self, job_id, spec, params, sink: OutputSink, timeout: int):
        cmd, env = self._build_command(spec, params)
        output = spec.agent.get("output", "text")
        want_json = output == "json"
        stream = spec.agent.get("stream", output == "text")
        kwargs: dict[str, Any] = {}
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
            **kwargs,
        )
        self.procs[job_id] = proc
        stdout_lines: list[str] = []

        async def pump(reader, name):
            while True:
                raw = await reader.readline()
                if not raw:
                    return
                line = _decode(raw).rstrip("\r\n")
                if name == "stdout":
                    stdout_lines.append(line)
                    if stream and line.strip():
                        await sink.line(line, "stdout")
                elif line.strip():
                    await sink.line(line, "stderr")

        try:
            await asyncio.wait_for(
                asyncio.gather(pump(proc.stdout, "stdout"), pump(proc.stderr, "stderr"), proc.wait()),
                timeout,
            )
        except TimeoutError:
            await _kill_tree(proc)
            raise
        if job_id in self.cancelled:
            raise Cancelled()
        result = None
        if want_json:
            text = "\n".join(stdout_lines).strip()
            try:
                result = json.loads(text) if text else None
                if result is not None and not isinstance(result, dict):
                    result = {"data": result}
            except json.JSONDecodeError:
                await sink.line("script did not return valid JSON", "system")
                for line in stdout_lines[-50:]:
                    await sink.line(line, "stdout")
                return (proc.returncode or 1), None
        elif output == "kv":
            result = parse_kv(stdout_lines)
        return proc.returncode, result


def parse_kv(lines: list[str]) -> dict[str, str]:
    """KEY:value lines (the format the desktop app's scripts print) -> {"key": "value"}."""
    out: dict[str, str] = {}
    for line in lines:
        key, sep, value = line.partition(":")
        key = key.strip()
        if sep and key and key.replace("_", "").isalnum() and key.upper() == key:
            out[key.lower()] = value.strip()
    return out


def _decode(raw: bytes) -> str:
    for enc in ("utf-8", "cp1252"):
        with contextlib.suppress(UnicodeDecodeError):
            return raw.decode(enc)
    return raw.decode("utf-8", errors="replace")


async def _kill_tree(proc: asyncio.subprocess.Process) -> None:
    if proc.returncode is not None:
        return
    if os.name == "nt":
        killer = await asyncio.create_subprocess_exec(
            "taskkill", "/T", "/F", "/PID", str(proc.pid),
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
        )
        await killer.wait()
    else:
        with contextlib.suppress(ProcessLookupError):
            proc.kill()


def os_info() -> dict[str, Any]:
    return {
        "system": platform.system(),
        "release": platform.release(),
        "version": platform.version(),
        "machine": platform.machine(),
    }
