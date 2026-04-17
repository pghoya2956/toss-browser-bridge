import importlib
from pathlib import Path

from toss_browser_bridge import bridge_lib
from toss_browser_bridge.bridge_lib import masked_account_id


def test_masked_account_id_masks_all_but_last_four() -> None:
    assert masked_account_id("18401036018") == "toss:*******6018"


def test_masked_account_id_handles_empty() -> None:
    assert masked_account_id(None) == "toss:primary"


def test_default_port_is_public_repo_port() -> None:
    assert bridge_lib.PORT == 42194


def test_env_port_override(monkeypatch) -> None:
    monkeypatch.setenv("TOSS_BRIDGE_PORT", "43111")
    reloaded = importlib.reload(bridge_lib)
    try:
        assert reloaded.PORT == 43111
    finally:
        monkeypatch.delenv("TOSS_BRIDGE_PORT", raising=False)
        importlib.reload(bridge_lib)


def test_env_home_override(monkeypatch, tmp_path) -> None:
    override = tmp_path / "bridge-home"
    monkeypatch.setenv("TOSS_BRIDGE_HOME", str(override))
    reloaded = importlib.reload(bridge_lib)
    try:
        assert reloaded.APP_SUPPORT_DIR == override
        assert reloaded.PROFILE_DIR == override / "chrome-profile"
        assert reloaded.TOKEN_FILE == override / "token"
    finally:
        monkeypatch.delenv("TOSS_BRIDGE_HOME", raising=False)
        importlib.reload(bridge_lib)


def test_default_home_uses_app_support_dir(monkeypatch) -> None:
    monkeypatch.delenv("TOSS_BRIDGE_HOME", raising=False)
    reloaded = importlib.reload(bridge_lib)
    try:
        assert reloaded.APP_SUPPORT_DIR == Path.home() / "Library" / "Application Support" / "toss-browser-bridge"
    finally:
        importlib.reload(bridge_lib)
