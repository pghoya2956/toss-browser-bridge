import importlib

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
