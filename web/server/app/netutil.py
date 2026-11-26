from starlette.requests import HTTPConnection

from .config import get_settings


def client_ip(conn: HTTPConnection) -> str:
    """Client IP. Behind Caddy, the last X-Forwarded-For entry is the one Caddy saw."""
    if get_settings().trust_proxy:
        xff = conn.headers.get("x-forwarded-for", "")
        if xff:
            return xff.split(",")[-1].strip()[:64]
    return (conn.client.host if conn.client else "")[:64]
