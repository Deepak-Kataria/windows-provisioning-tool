"""Action registry.

Each web/actions/<name>.json defines one allowlisted action. The server and the agent load
the same files, and both validate params against the schema. The server never sends a raw
command, only {action id, params}.

File format:
{
  "id": "system.info",
  "title": "System info",
  "description": "...",
  "min_role": "viewer" | "technician" | "admin",
  "timeout_seconds": 120,
  "params": { JSON Schema for the params object },
  "secret_params": ["password"],      # never stored in DB or logs
  "agent": { how the agent runs it; ignored by the server }
}
"""
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

from .models import ROLES

REDACTED = "***"


class ActionError(ValueError):
    pass


@dataclass(frozen=True)
class Action:
    id: str
    title: str
    description: str
    min_role: str
    timeout_seconds: int
    params_schema: dict[str, Any]
    secret_params: tuple[str, ...] = field(default_factory=tuple)

    def validate(self, params: dict[str, Any]) -> None:
        errors = sorted(
            Draft202012Validator(self.params_schema).iter_errors(params), key=lambda e: e.path
        )
        if errors:
            e = errors[0]
            where = "/".join(str(p) for p in e.path) or "params"
            raise ActionError(f"{where}: {e.message}")

    def redact(self, params: dict[str, Any]) -> dict[str, Any]:
        return {k: (REDACTED if k in self.secret_params else v) for k, v in params.items()}

    def has_secrets(self, params: dict[str, Any]) -> bool:
        return any(k in params for k in self.secret_params)


def _parse(path: Path) -> Action:
    raw = json.loads(path.read_text(encoding="utf-8"))
    for key in ("id", "title", "min_role", "params"):
        if key not in raw:
            raise ActionError(f"{path.name}: missing '{key}'")
    if raw["min_role"] not in ROLES:
        raise ActionError(f"{path.name}: bad min_role {raw['min_role']!r}")
    schema = dict(raw["params"])
    schema.setdefault("type", "object")
    schema.setdefault("additionalProperties", False)  # unknown params are rejected
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as e:
        raise ActionError(f"{path.name}: invalid params schema: {e.message}") from None
    secrets = tuple(raw.get("secret_params", []))
    unknown = set(secrets) - set(schema.get("properties", {}))
    if unknown:
        raise ActionError(f"{path.name}: secret_params not in schema: {sorted(unknown)}")
    return Action(
        id=raw["id"],
        title=raw["title"],
        description=raw.get("description", ""),
        min_role=raw["min_role"],
        timeout_seconds=int(raw.get("timeout_seconds", 300)),
        params_schema=schema,
        secret_params=secrets,
    )


class Registry:
    def __init__(self, actions_dir: Path) -> None:
        self.actions: dict[str, Action] = {}
        for path in sorted(actions_dir.glob("*.json")):
            a = _parse(path)
            if a.id in self.actions:
                raise ActionError(f"duplicate action id {a.id!r}")
            self.actions[a.id] = a

    def get(self, action_id: str) -> Action:
        a = self.actions.get(action_id)
        if a is None:
            raise ActionError(f"unknown action {action_id!r}")
        return a

    def all(self) -> list[Action]:
        return list(self.actions.values())
