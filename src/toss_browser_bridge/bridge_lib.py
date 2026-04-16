from __future__ import annotations

import json
import os
import secrets
import socket
import stat
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
HOST = "127.0.0.1"
SOURCE = "toss_browser_bridge"
DEFAULT_PORT = 42194


def _default_port() -> int:
    raw = os.environ.get("TOSS_BRIDGE_PORT")
    if not raw:
        return DEFAULT_PORT
    return int(raw)


PORT = _default_port()


def _default_app_support_dir() -> Path:
    override = os.environ.get("TOSS_BRIDGE_HOME")
    if override:
        return Path(override).expanduser()
    return Path.home() / "Library" / "Application Support" / "toss-browser-bridge"


APP_SUPPORT_DIR = _default_app_support_dir()
PROFILE_DIR = APP_SUPPORT_DIR / "chrome-profile"
TOKEN_FILE = APP_SUPPORT_DIR / "token"
PID_FILE = APP_SUPPORT_DIR / "daemon.pid"
LOG_FILE = APP_SUPPORT_DIR / "daemon.log"


def now_kst() -> str:
    return datetime.now(KST).isoformat(timespec="seconds")


def ensure_runtime_dirs() -> None:
    APP_SUPPORT_DIR.mkdir(parents=True, exist_ok=True)
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)


def write_secure_text(path: Path, text: str) -> None:
    ensure_runtime_dirs()
    path.write_text(text, encoding="utf-8")
    os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)


def read_text_if_exists(path: Path) -> str | None:
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8").strip()


def rotate_token() -> str:
    token = secrets.token_urlsafe(32)
    write_secure_text(TOKEN_FILE, token)
    return token


def write_pid(pid: int) -> None:
    write_secure_text(PID_FILE, str(pid))


def clear_runtime_markers() -> None:
    for path in (PID_FILE, TOKEN_FILE):
        if path.exists():
            path.unlink()


def daemon_url(path: str) -> str:
    return f"http://{HOST}:{PORT}{path}"


def request_json(
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    token: str | None = None,
    timeout: float = 30.0,
) -> dict[str, Any]:
    data = None
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(
        daemon_url(path),
        data=data,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        detail: dict[str, Any]
        try:
            detail = json.loads(body)
        except json.JSONDecodeError:
            detail = {"ok": False, "error": {"code": "http_error", "message": body}}
        raise RuntimeError(
            f"bridge http {exc.code}: {detail.get('error', {}).get('message', body)}"
        ) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"bridge unavailable: {exc.reason}") from exc


def wait_for_port(host: str = HOST, port: int = PORT, timeout: float = 15.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.5)
            if sock.connect_ex((host, port)) == 0:
                return True
        time.sleep(0.25)
    return False


def masked_account_id(value: str | None) -> str:
    if not value:
        return "toss:primary"
    stripped = "".join(ch for ch in value if ch.isdigit())
    if len(stripped) < 4:
        return "toss:primary"
    return f"toss:{'*' * max(0, len(stripped) - 4)}{stripped[-4:]}"


def sanitize_endpoint_entry(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": entry.get("name"),
        "method": entry.get("method"),
        "path": entry.get("path"),
        "status_code": entry.get("status_code"),
        "ok": entry.get("ok"),
        "error": entry.get("error"),
    }
