import json
import os
import bcrypt

CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "credentials.json")

_DEFAULT_CREDENTIALS = {
    "users": [
        {
            "username": "admin",
            "password_hash": "$2b$12$placeholder_change_on_first_run",
            "role": "admin",
            "display_name": "Administrator"
        }
    ]
}


def _ensure_credentials_file():
    if not os.path.exists(CONFIG_PATH):
        os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
        with open(CONFIG_PATH, "w") as f:
            json.dump(_DEFAULT_CREDENTIALS, f, indent=4)


def load_credentials():
    _ensure_credentials_file()
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)


def save_credentials(data):
    with open(CONFIG_PATH, "w") as f:
        json.dump(data, f, indent=4)


def is_first_run(username: str) -> bool:
    """Returns True if the user still has the default placeholder password."""
    data = load_credentials()
    for user in data["users"]:
        if user["username"] == username:
            return user["password_hash"] == "$2b$12$placeholder_change_on_first_run"
    return False


def authenticate(username: str, password: str):
    """Returns (success: bool, role: str, display_name: str)"""
    data = load_credentials()
    for user in data["users"]:
        if user["username"] == username:
            stored_hash = user["password_hash"].encode("utf-8")
            # Handle first-run placeholder
            if stored_hash == b"$2b$12$placeholder_change_on_first_run":
                if password == "admin":
                    return True, user["role"], user["display_name"]
            elif bcrypt.checkpw(password.encode("utf-8"), stored_hash):
                return True, user["role"], user["display_name"]
    return False, None, None


def add_user(username: str, password: str, role: str, display_name: str):
    data = load_credentials()
    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    data["users"].append({
        "username": username,
        "password_hash": hashed,
        "role": role,
        "display_name": display_name
    })
    save_credentials(data)


def change_password(username: str, new_password: str):
    data = load_credentials()
    for user in data["users"]:
        if user["username"] == username:
            user["password_hash"] = bcrypt.hashpw(
                new_password.encode("utf-8"), bcrypt.gensalt()
            ).decode("utf-8")
    save_credentials(data)


def list_users():
    data = load_credentials()
    return [{"username": u["username"], "role": u["role"], "display_name": u["display_name"]}
            for u in data["users"]]


def delete_user(username: str):
    data = load_credentials()
    data["users"] = [u for u in data["users"] if u["username"] != username]
    save_credentials(data)
