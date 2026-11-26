"""Build and sign the agent script bundle.

  python web/tools/bundle_tool.py keygen --out C:\keys\itops-bundle.key
      Creates the Ed25519 signing key. Keep it OFF the web server (USB / password manager).
      Prints the public key: paste it into web/agent/itops_agent/bundle_key.py.

  python web/tools/bundle_tool.py build --key C:\keys\itops-bundle.key --out web/agent/build/bundle
      Copies web/actions/*.json, scripts/*.ps1 and the app catalog into the bundle folder, writes
      bundle.manifest.json (sha256 of each file) and bundle.sig.
"""
import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

REPO = Path(__file__).resolve().parents[2]
# Config the agent reads (app catalog = which winget ids may be installed)
CONFIG_FILES = ["apps_common.json", "apps_teams.json"]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def public_hex(key: Ed25519PrivateKey) -> str:
    return key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    ).hex()


def load_key(path: Path) -> Ed25519PrivateKey:
    key = serialization.load_pem_private_key(path.read_bytes(), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        sys.exit("not an Ed25519 key")
    return key


def keygen(out: Path) -> None:
    if out.exists():
        sys.exit(f"{out} exists; refusing to overwrite a signing key")
    key = Ed25519PrivateKey.generate()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
        )
    )
    print(f"private key: {out}  (keep it secret, never commit it)")
    print(f"PUBLIC_KEY_HEX = \"{public_hex(key)}\"")


def sign_dir(root: Path, key: Ed25519PrivateKey) -> dict:
    files = {
        p.relative_to(root).as_posix(): sha256(p)
        for p in sorted(root.rglob("*"))
        if p.is_file() and p.name not in ("bundle.manifest.json", "bundle.sig")
    }
    manifest = json.dumps({"version": 1, "files": files}, indent=1, sort_keys=True).encode()
    (root / "bundle.manifest.json").write_bytes(manifest)
    (root / "bundle.sig").write_bytes(key.sign(manifest))
    return files


def build(key_path: Path | None, out: Path) -> None:
    key = load_key(key_path) if key_path else None
    if out.exists():
        shutil.rmtree(out)
    (out / "actions").mkdir(parents=True)
    (out / "scripts").mkdir()
    for p in sorted((REPO / "web" / "actions").glob("*.json")):
        json.loads(p.read_text(encoding="utf-8"))  # fail early on broken JSON
        shutil.copy2(p, out / "actions" / p.name)
    for p in sorted((REPO / "scripts").glob("*.ps1")):
        shutil.copy2(p, out / "scripts" / p.name)
    (out / "config").mkdir()
    for name in CONFIG_FILES:
        shutil.copy2(REPO / "config" / name, out / "config" / name)
    if key is None:
        print(f"UNSIGNED dev bundle in {out} (agent must be built with ALLOW_UNSIGNED)")
        return
    files = sign_dir(out, key)
    print(f"signed {len(files)} files into {out}")
    print(f"public key: {public_hex(key)}")


def main() -> None:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    k = sub.add_parser("keygen")
    k.add_argument("--out", type=Path, required=True)
    b = sub.add_parser("build")
    g = b.add_mutually_exclusive_group(required=True)
    g.add_argument("--key", type=Path)
    g.add_argument("--unsigned", action="store_true", help="dev only: no signature")
    b.add_argument("--out", type=Path, default=REPO / "web" / "agent" / "build" / "bundle")
    a = p.parse_args()
    if a.cmd == "keygen":
        keygen(a.out)
    else:
        build(None if a.unsigned else a.key, a.out)


if __name__ == "__main__":
    main()
