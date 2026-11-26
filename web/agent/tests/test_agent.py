import asyncio
import json
import sys
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
import bundle_tool  # noqa: E402

from itops_agent.bundle import Bundle, BundleError  # noqa: E402
from itops_agent.client import check_server_url, ws_url  # noqa: E402
from itops_agent.executor import Executor, parse_kv  # noqa: E402
from itops_agent.state import State  # noqa: E402

PING = {
    "id": "agent.ping",
    "title": "Ping",
    "min_role": "technician",
    "timeout_seconds": 5,
    "params": {"properties": {"message": {"type": "string"}}},
    "agent": {"type": "builtin", "name": "ping"},
}


def make_bundle(tmp_path: Path, actions=(PING,), scripts=None):
    root = tmp_path / "bundle"
    (root / "actions").mkdir(parents=True)
    (root / "scripts").mkdir()
    for a in actions:
        (root / "actions" / f"{a['id']}.json").write_text(json.dumps(a))
    for name, body in (scripts or {}).items():
        (root / "scripts" / name).write_text(body)
    key = Ed25519PrivateKey.generate()
    bundle_tool.sign_dir(root, key)
    pub = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw).hex()
    return root, pub


# ------------------------------------------------------------------ bundle signing

def test_signed_bundle_verifies(tmp_path):
    root, pub = make_bundle(tmp_path)
    b = Bundle(root, pub)
    assert b.check("actions/agent.ping.json").is_file()


def test_tampered_file_rejected(tmp_path):
    root, pub = make_bundle(tmp_path)
    b = Bundle(root, pub)
    (root / "actions" / "agent.ping.json").write_text("{}")
    with pytest.raises(BundleError, match="modified"):
        b.check("actions/agent.ping.json")


def test_unlisted_file_rejected(tmp_path):
    root, pub = make_bundle(tmp_path)
    b = Bundle(root, pub)
    (root / "scripts" / "evil.ps1").write_text("rm -r C:\\")
    with pytest.raises(BundleError, match="not in signed bundle"):
        b.check("scripts/evil.ps1")


def test_tampered_manifest_rejected(tmp_path):
    root, pub = make_bundle(tmp_path)
    m = json.loads((root / "bundle.manifest.json").read_text())
    m["files"]["scripts/evil.ps1"] = "00"
    (root / "bundle.manifest.json").write_text(json.dumps(m))
    with pytest.raises(BundleError, match="signature"):
        Bundle(root, pub)


def test_wrong_key_rejected(tmp_path):
    root, _ = make_bundle(tmp_path)
    other = Ed25519PrivateKey.generate().public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    ).hex()
    with pytest.raises(BundleError):
        Bundle(root, other)


def test_path_escape_rejected(tmp_path):
    root, pub = make_bundle(tmp_path)
    with pytest.raises(BundleError):
        Bundle(root, pub).check("../outside.ps1")


def test_unsigned_needs_dev_flag(tmp_path, monkeypatch):
    monkeypatch.delenv("ITOPS_AGENT_DEV", raising=False)
    with pytest.raises(BundleError, match="dev mode"):
        Bundle(tmp_path, "")


# ------------------------------------------------------------------ executor

def run_job(executor: Executor, msg: dict) -> list[dict]:
    async def go():
        executor.start(msg)
        while executor.tasks:
            await asyncio.sleep(0.01)

    asyncio.run(go())
    return sent


sent: list[dict] = []


async def _capture(msg):
    sent.append(msg)


@pytest.fixture
def executor(tmp_path):
    sent.clear()
    root, pub = make_bundle(tmp_path)
    return Executor(Bundle(root, pub), _capture, "actions")


def test_ping(executor):
    msgs = run_job(executor, {"job_id": "j1", "action": "agent.ping", "params": {"message": "hi"}})
    kinds = [m["type"] for m in msgs]
    assert kinds == ["job_started", "job_output", "job_done"]
    assert msgs[-1]["status"] == "succeeded" and msgs[-1]["result"]["echo"] == "hi"


def test_unknown_action_fails_without_running(executor):
    msgs = run_job(executor, {"job_id": "j1", "action": "shell.exec", "params": {"cmd": "whoami"}})
    assert msgs == [msgs[0]] and msgs[0]["status"] == "failed"


def test_agent_revalidates_params(executor):
    msgs = run_job(executor, {"job_id": "j1", "action": "agent.ping", "params": {"cmd": "x"}})
    assert msgs[-1]["status"] == "failed" and "invalid params" in msgs[-1]["error"]


def test_build_command_maps_args_and_hides_secrets(tmp_path):
    action = {
        "id": "pc.rename",
        "title": "Rename",
        "min_role": "technician",
        "params": {
            "properties": {
                "new_name": {"type": "string"},
                "restart": {"type": "boolean"},
                "password": {"type": "string"},
            }
        },
        "agent": {
            "type": "powershell",
            "script": "rename_computer.ps1",
            "args": {"NewName": "new_name", "Restart": "restart"},
            "env": {"ITOPS_PASSWORD": "password"},
        },
    }
    root, pub = make_bundle(tmp_path, [action], {"rename_computer.ps1": "param($NewName)"})
    ex = Executor(Bundle(root, pub), _capture, "actions")
    cmd, env = ex._build_command(
        ex.actions["pc.rename"], {"new_name": "PC-01; rm x", "restart": True, "password": "s3cret"}
    )
    i = cmd.index("-NewName")
    assert cmd[i + 1] == "PC-01; rm x"  # one argv element, no shell, so no injection
    assert "-Restart" in cmd
    assert "s3cret" not in " ".join(cmd)
    assert env["ITOPS_PASSWORD"] == "s3cret"


@pytest.mark.skipif(sys.platform != "win32", reason="needs powershell.exe")
def test_powershell_kv_script(tmp_path):
    action = {
        "id": "t.kv",
        "title": "kv",
        "min_role": "viewer",
        "timeout_seconds": 60,
        "params": {"properties": {"Name": {"type": "string"}}},
        "agent": {"type": "powershell", "script": "kv.ps1", "args": {"Name": "Name"}, "output": "kv"},
    }
    script = 'param([string]$Name)\nWrite-Output "HELLO:$Name"\nWrite-Output "COUNT:3"\nexit 0\n'
    root, pub = make_bundle(tmp_path, [action], {"kv.ps1": script})
    sent.clear()
    ex = Executor(Bundle(root, pub), _capture, "actions")
    msgs = run_job(ex, {"job_id": "j1", "action": "t.kv", "params": {"Name": "a b"}})
    done = msgs[-1]
    assert done["status"] == "succeeded", done
    assert done["result"] == {"hello": "a b", "count": "3"}


@pytest.mark.skipif(sys.platform != "win32", reason="needs powershell.exe")
def test_powershell_cancel_kills_process(tmp_path):
    action = {
        "id": "t.sleep",
        "title": "sleep",
        "min_role": "viewer",
        "timeout_seconds": 60,
        "params": {"properties": {}},
        "agent": {"type": "powershell", "script": "sleep.ps1"},
    }
    root, pub = make_bundle(tmp_path, [action], {"sleep.ps1": "Write-Output start\nStart-Sleep 30\n"})
    sent.clear()
    ex = Executor(Bundle(root, pub), _capture, "actions")

    async def go():
        ex.start({"job_id": "j1", "action": "t.sleep", "params": {}})
        for _ in range(200):
            if any(m["type"] == "job_output" for m in sent):
                break
            await asyncio.sleep(0.05)
        await ex.cancel("j1")
        while ex.tasks:
            await asyncio.sleep(0.05)

    asyncio.run(asyncio.wait_for(go(), 20))
    assert sent[-1]["status"] == "cancelled"


def test_parse_kv():
    assert parse_kv(["USER:bob", "noise", "MONITOR_1:DEL (SN: 1)", "lower:x"]) == {
        "user": "bob",
        "monitor_1": "DEL (SN: 1)",
    }


# ------------------------------------------------------------------ client + state

def test_server_url_rules():
    assert check_server_url("https://prov.example.com/") == "https://prov.example.com"
    assert check_server_url("http://127.0.0.1:8000") == "http://127.0.0.1:8000"
    with pytest.raises(ValueError):
        check_server_url("http://prov.example.com")
    assert ws_url("https://prov.example.com") == "wss://prov.example.com/api/agent/ws"


def test_state_roundtrip_token_not_plain_on_windows(tmp_path, monkeypatch):
    monkeypatch.setenv("ITOPS_AGENT_STATE", str(tmp_path))
    State("https://x", "m1", "super-secret-token").save()
    raw = (tmp_path / "state.json").read_text()
    if sys.platform == "win32":
        assert "super-secret-token" not in raw
    assert State.load().token == "super-secret-token"
