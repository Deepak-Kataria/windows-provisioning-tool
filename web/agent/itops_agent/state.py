"""Enrollment state (server URL, machine id, token). The token is DPAPI-encrypted on Windows."""
import base64
import ctypes
import json
import os
from dataclasses import asdict, dataclass

from .paths import state_dir

STATE_FILE = "state.json"


class _Blob(ctypes.Structure):
    _fields_ = [("cbData", ctypes.c_uint32), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _dpapi(data: bytes, protect: bool) -> bytes:
    """Windows DPAPI, machine scope: only this PC can decrypt it."""
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    buf = ctypes.create_string_buffer(data, len(data))
    blob_in = _Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    blob_out = _Blob()
    CRYPTPROTECT_LOCAL_MACHINE = 0x4
    CRYPTPROTECT_UI_FORBIDDEN = 0x1
    flags = CRYPTPROTECT_LOCAL_MACHINE | CRYPTPROTECT_UI_FORBIDDEN
    fn = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    ok = fn(ctypes.byref(blob_in), None, None, None, None, flags, ctypes.byref(blob_out))
    if not ok:
        raise OSError("DPAPI call failed")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        kernel32.LocalFree(blob_out.pbData)


def _seal(token: str) -> str:
    if os.name == "nt":
        return "dpapi:" + base64.b64encode(_dpapi(token.encode(), True)).decode()
    return "plain:" + token


def _unseal(value: str) -> str:
    kind, _, data = value.partition(":")
    if kind == "dpapi":
        return _dpapi(base64.b64decode(data), False).decode()
    if kind == "plain":
        return data
    raise ValueError("unknown token format")


@dataclass
class State:
    server_url: str
    machine_id: str
    token: str

    def save(self) -> None:
        d = state_dir()
        d.mkdir(parents=True, exist_ok=True)
        raw = asdict(self)
        raw["token"] = _seal(self.token)
        tmp = d / (STATE_FILE + ".tmp")
        tmp.write_text(json.dumps(raw, indent=2), encoding="utf-8")
        os.replace(tmp, d / STATE_FILE)

    @classmethod
    def load(cls) -> "State | None":
        p = state_dir() / STATE_FILE
        if not p.exists():
            return None
        raw = json.loads(p.read_text(encoding="utf-8"))
        raw["token"] = _unseal(raw["token"])
        return cls(**raw)

    @staticmethod
    def clear() -> None:
        p = state_dir() / STATE_FILE
        if p.exists():
            p.unlink()
