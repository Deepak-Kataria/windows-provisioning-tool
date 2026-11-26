"""Signed script bundle.

bundle.manifest.json lists sha256 of every action/script file; bundle.sig is an Ed25519
signature over the manifest bytes. The private key never lives on the web server, so even a
compromised server cannot make an agent run a script that was not signed by the builder.
"""
import hashlib
import json
import logging
import os
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from . import bundle_key

log = logging.getLogger(__name__)

MANIFEST = "bundle.manifest.json"
SIGNATURE = "bundle.sig"


class BundleError(Exception):
    pass


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


class Bundle:
    """Answers: may I use this file? (exists in the signed manifest with this exact hash)"""

    def __init__(self, root: Path, public_key_hex: str | None = None) -> None:
        self.root = root
        key_hex = bundle_key.PUBLIC_KEY_HEX if public_key_hex is None else public_key_hex
        self.dev = not key_hex
        self.files: dict[str, str] = {}
        if self.dev:
            if os.environ.get("ITOPS_AGENT_DEV") != "1" and not bundle_key.ALLOW_UNSIGNED:
                raise BundleError("agent has no bundle key; set ITOPS_AGENT_DEV=1 for dev mode")
            log.warning("DEV MODE: script bundle signature is NOT checked")
            return
        try:
            manifest = (root / MANIFEST).read_bytes()
            sig = (root / SIGNATURE).read_bytes()
        except FileNotFoundError as e:
            raise BundleError(f"bundle file missing: {e.filename}") from None
        try:
            Ed25519PublicKey.from_public_bytes(bytes.fromhex(key_hex)).verify(sig, manifest)
        except (InvalidSignature, ValueError):
            raise BundleError("bundle signature is invalid") from None
        self.files = json.loads(manifest)["files"]

    def check(self, rel: str) -> Path:
        """Return the absolute path of a bundle file after verifying its hash."""
        rel = rel.replace("\\", "/")
        path = (self.root / rel).resolve()
        if self.root.resolve() not in path.parents:
            raise BundleError(f"path escapes bundle: {rel}")
        if not path.is_file():
            raise BundleError(f"missing bundle file: {rel}")
        if self.dev:
            return path
        want = self.files.get(rel)
        if want is None:
            raise BundleError(f"file not in signed bundle: {rel}")
        if sha256_file(path) != want:
            raise BundleError(f"file was modified: {rel}")
        return path

    def listed(self, prefix: str) -> list[str]:
        if self.dev:
            base = self.root / prefix
            return sorted(
                p.relative_to(self.root).as_posix() for p in base.glob("*") if p.is_file()
            )
        return sorted(f for f in self.files if f.startswith(prefix.rstrip("/") + "/"))
