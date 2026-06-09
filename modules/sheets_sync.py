"""Google Sheets sync — appends provisioning data rows via service account."""
import base64
import json
import os
from datetime import datetime
from modules.paths import get_base_dir

CONFIG_PATH = os.path.join(get_base_dir(), "config", "sheets_config.json")

_K = bytes([0x4D,0x79,0x49,0x54,0x44,0x65,0x63,0x6B,0x50,0x72,0x6F,0x76,0x54,0x6F,0x6F,0x6C,
            0x53,0x65,0x63,0x72,0x65,0x74,0x4B,0x65,0x79,0x32,0x30,0x32,0x34,0x58,0x59,0x5A])
_D = b'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'

def _get_sa_info() -> dict:
    raw = base64.b64decode(_D)
    return json.loads(bytes([b ^ _K[i % len(_K)] for i, b in enumerate(raw)]))

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
    return bool(cfg.get("sheet_id"))


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

    try:
        scopes = ["https://spreadsheets.google.com/feeds",
                  "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(_get_sa_info(), scopes=scopes)
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
    if not cfg.get("sheet_id"):
        return False, "Google Sheets not configured (set Sheet ID in Config tab)."

    try:
        scopes = ["https://spreadsheets.google.com/feeds",
                  "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(_get_sa_info(), scopes=scopes)
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
