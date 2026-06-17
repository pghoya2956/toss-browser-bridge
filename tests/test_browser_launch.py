from __future__ import annotations

import pytest

from toss_browser_bridge.daemon import (
    LEAN_CHROME_ARGS,
    resolve_browser_launch_options,
)

# 토글 미설정 시 launch 인자가 현행(하드코딩)과 동일해야 한다는 회귀 기준.
# daemon.py start_browser()가 과거에 직접 넘기던 값과 바이트 단위로 일치.
BASELINE = {
    "channel": "chrome",
    "headless": False,
    "viewport": {"width": 1440, "height": 960},
    "args": ["--window-size=1440,960"],
}


@pytest.fixture(autouse=True)
def _clear_toggles(monkeypatch):
    monkeypatch.delenv("TOSS_BRIDGE_HEADLESS", raising=False)
    monkeypatch.delenv("TOSS_BRIDGE_LEAN", raising=False)


def test_no_toggles_matches_current_hardcoded_baseline() -> None:
    # 회귀 고정: 토글 미설정 → 기존 headed 동작과 정확히 동일.
    assert resolve_browser_launch_options() == BASELINE


def test_headless_toggle_flips_headless_only(monkeypatch) -> None:
    monkeypatch.setenv("TOSS_BRIDGE_HEADLESS", "on")
    opts = resolve_browser_launch_options()
    assert opts["headless"] is True
    # lean 미설정이므로 baseline args 그대로(경량 플래그 없음).
    assert opts["args"] == ["--window-size=1440,960"]


def test_lean_toggle_appends_args_keeps_headed(monkeypatch) -> None:
    monkeypatch.setenv("TOSS_BRIDGE_LEAN", "on")
    opts = resolve_browser_launch_options()
    assert opts["headless"] is False  # lean은 headless를 건드리지 않는다
    assert opts["args"][0] == "--window-size=1440,960"  # baseline 유지
    for flag in LEAN_CHROME_ARGS:
        assert flag in opts["args"]
    # 이미지 비활성화가 포함됐는지(데이터가 fetch라 안전한 핵심 절감 플래그).
    assert "--blink-settings=imagesEnabled=false" in opts["args"]


def test_both_toggles_combine(monkeypatch) -> None:
    monkeypatch.setenv("TOSS_BRIDGE_HEADLESS", "true")
    monkeypatch.setenv("TOSS_BRIDGE_LEAN", "1")
    opts = resolve_browser_launch_options()
    assert opts["headless"] is True
    assert opts["args"] == ["--window-size=1440,960"] + LEAN_CHROME_ARGS


@pytest.mark.parametrize("value", ["maybe", "", "0", "OFF", "no", "false"])
def test_invalid_or_falsy_values_keep_current_behavior(monkeypatch, value) -> None:
    # _env_flag 위임: 오타/빈값/off는 전부 false → 현행 headed 동작으로 안전하게 떨어진다.
    monkeypatch.setenv("TOSS_BRIDGE_HEADLESS", value)
    monkeypatch.setenv("TOSS_BRIDGE_LEAN", value)
    assert resolve_browser_launch_options() == BASELINE
