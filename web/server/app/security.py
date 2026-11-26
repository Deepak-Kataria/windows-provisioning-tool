"""Passwords, TOTP, tokens, and encryption at rest."""
import base64
import hashlib
import hmac
import secrets
import time

import bcrypt
import pyotp
from cryptography.fernet import Fernet, InvalidToken

from .config import get_settings

PASSWORD_MIN = 12
PASSWORD_MAX_BYTES = 72  # bcrypt limit

# Used when the username does not exist, so the response time does not reveal that.
_DUMMY_HASH = bcrypt.hashpw(b"timing-equaliser", bcrypt.gensalt(12))


# ---------------------------------------------------------------- passwords

def password_problem(password: str) -> str | None:
    """Return a human message if the password is not acceptable, else None."""
    if len(password) < PASSWORD_MIN:
        return f"Password must be at least {PASSWORD_MIN} characters."
    if len(password.encode("utf-8")) > PASSWORD_MAX_BYTES:
        return f"Password must be at most {PASSWORD_MAX_BYTES} bytes."
    if password.lower() == password or password.upper() == password:
        return "Password must mix upper and lower case."
    if not any(c.isdigit() for c in password):
        return "Password must contain a digit."
    return None


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(12)).decode("ascii")


def verify_password(password: str, password_hash: str | None) -> bool:
    raw = password.encode("utf-8")
    if len(raw) > PASSWORD_MAX_BYTES:
        raw = raw[:PASSWORD_MAX_BYTES]
    if not password_hash:
        bcrypt.checkpw(raw, _DUMMY_HASH)
        return False
    try:
        return bcrypt.checkpw(raw, password_hash.encode("ascii"))
    except ValueError:
        return False


# ---------------------------------------------------------------- tokens

def new_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def hash_token(token: str) -> str:
    """Tokens are high-entropy, so a plain SHA-256 is enough (no slow hash needed)."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def tokens_equal(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O, 1/I


def new_enrollment_code() -> str:
    """Human-typeable one-time code, e.g. 7KQ2-MZ8D-R4TX-PW9B (~80 bits)."""
    chars = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(16))
    return "-".join(chars[i : i + 4] for i in range(0, 16, 4))


def normalise_enrollment_code(code: str) -> str:
    c = "".join(ch for ch in code.upper() if ch.isalnum())
    return "-".join(c[i : i + 4] for i in range(0, len(c), 4))


# ---------------------------------------------------------------- encryption at rest

def _fernet() -> Fernet:
    key = hashlib.sha256(("itops-fernet:" + get_settings().secret_key).encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt(value: str) -> str:
    return _fernet().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt(value: str) -> str | None:
    try:
        return _fernet().decrypt(value.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError):
        return None


# ---------------------------------------------------------------- TOTP

def new_totp_secret() -> str:
    return pyotp.random_base32()


def totp_uri(secret: str, username: str) -> str:
    s = get_settings()
    return pyotp.TOTP(secret).provisioning_uri(name=username, issuer_name=s.totp_issuer)


def qr_data_uri(text: str) -> str:
    """SVG QR code as a data: URI (no image library needed)."""
    import io

    import qrcode
    import qrcode.image.svg

    img = qrcode.make(text, image_factory=qrcode.image.svg.SvgPathImage, box_size=8, border=2)
    buf = io.BytesIO()
    img.save(buf)
    return "data:image/svg+xml;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def verify_totp(secret: str, code: str, last_step: int, now: float | None = None) -> int | None:
    """Check a 6-digit code (allowing one 30s step of clock drift).

    Returns the matched time step, or None. The caller stores the step and passes it as
    last_step next time, so a code can never be used twice.
    """
    code = "".join(ch for ch in code if ch.isdigit())
    if len(code) != 6:
        return None
    totp = pyotp.TOTP(secret)
    now = time.time() if now is None else now
    current = int(now // totp.interval)
    for step in (current - 1, current, current + 1):
        if step <= last_step:
            continue
        if hmac.compare_digest(totp.generate_otp(step), code):
            return step
    return None
