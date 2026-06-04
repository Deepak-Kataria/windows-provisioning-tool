"""Google Sheets sync — appends provisioning data rows via service account."""
import json
import os
from datetime import datetime
from modules.paths import get_base_dir

CONFIG_PATH = os.path.join(get_base_dir(), "config", "sheets_config.json")

HEADERS = [
    "Timestamp", "Computer Name", "Operator Username", "Operator Email",
    "System Model", "System Serial No.", "Processor", "RAM", "Disk Size",
    "Display / GPU", "Windows Version", "Last Windows Update", "Monitor Details",
]


def _extract_sheet_id(value: str) -> str:
    """Accept either a bare sheet ID or a full Google Sheets URL."""
    import re
    m = re.search(r'/spreadsheets/d/([a-zA-Z0-9_-]+)', value)
    return m.group(1) if m else value.strip()


def _load_config():
    try:
        with open(CONFIG_PATH) as f:
            cfg = json.load(f)
        if cfg.get("sheet_id"):
            cfg["sheet_id"] = _extract_sheet_id(cfg["sheet_id"])
        return cfg
    except Exception:
        return {}


def save_config(cfg: dict):
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=4)


def is_configured() -> bool:
    cfg = _load_config()
    return bool(cfg.get("sheet_id") and cfg.get("key_file"))


def test_connection() -> tuple[bool, str]:
    """Returns (success, message)."""
    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except ImportError:
        return False, "gspread not installed. Run: pip install gspread google-auth"

    cfg = _load_config()
    if not cfg.get("sheet_id"):
        return False, "Sheet ID not configured."
    if not cfg.get("key_file"):
        return False, "Service account key file not configured."
    if not os.path.exists(cfg["key_file"]):
        return False, f"Key file not found: {cfg['key_file']}"

    try:
        scopes = ["https://spreadsheets.google.com/feeds",
                  "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_file(cfg["key_file"], scopes=scopes)
        client = gspread.authorize(creds)
        sheet = client.open_by_key(cfg["sheet_id"])
        ws_name = cfg.get("worksheet_name") or "Sheet1"
        try:
            ws = sheet.worksheet(ws_name)
        except gspread.exceptions.WorksheetNotFound:
            ws = sheet.add_worksheet(title=ws_name, rows=1000, cols=len(HEADERS))
        _ = ws.title
        return True, f"Connected to '{sheet.title}' → worksheet '{ws.title}'"
    except Exception as e:
        return False, str(e)


def append_row(data: dict) -> tuple[bool, str]:
    """Append one provisioning row. data keys match _get_details_row() in tab_system."""
    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except ImportError:
        return False, "gspread not installed. Run: pip install gspread google-auth"

    cfg = _load_config()
    if not cfg.get("sheet_id") or not cfg.get("key_file"):
        return False, "Google Sheets not configured (set Sheet ID and key file in Config tab)."
    if not os.path.exists(cfg["key_file"]):
        return False, f"Key file not found: {cfg['key_file']}"

    try:
        scopes = ["https://spreadsheets.google.com/feeds",
                  "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_file(cfg["key_file"], scopes=scopes)
        client = gspread.authorize(creds)
        sheet = client.open_by_key(cfg["sheet_id"])
        ws_name = cfg.get("worksheet_name") or "Sheet1"
        try:
            ws = sheet.worksheet(ws_name)
        except gspread.exceptions.WorksheetNotFound:
            ws = sheet.add_worksheet(title=ws_name, rows=1000, cols=len(HEADERS))

        # Ensure header row exists
        existing = ws.row_values(1)
        if existing != HEADERS:
            ws.insert_row(HEADERS, 1)

        row = [
            datetime.now().strftime("%Y-%m-%d %H:%M"),
            data.get("computer_name", ""),
            data.get("operator", ""),
            data.get("email", ""),
            data.get("model", ""),
            data.get("serial", ""),
            data.get("processor", ""),
            data.get("ram", ""),
            data.get("disk", ""),
            data.get("display", ""),
            data.get("windows", ""),
            data.get("last_update", ""),
            data.get("monitors", ""),
        ]
        ws.append_row(row)
        return True, f"Row added to '{ws_name}'."
    except Exception as e:
        return False, str(e)
