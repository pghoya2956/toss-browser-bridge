# Toss Browser Bridge

토스증권 웹에 로그인된 **전용 Chrome 프로필**을 브리지가 직접 소유하고, 브라우저 컨텍스트 안에서 read-only 조회를 수행하는 로컬 daemon/CLI 프로젝트다.

공식 토스증권 API 프로젝트가 아니다. browser-attached companion 성격의 **비공식 read-only 도구**다.

## 현재 지원 명령

- `health`
- `open-login`
- `account-summary`
- `positions`
- `completed-orders`
- `quote`
- `order-preview`
- `fx-preview`
- `place-order` (guarded preflight only, final submit blocked)
- `verify-order` (journal-backed recovery over current verify signals)
- `reconnect`
- `shutdown`
- `diagnostics`

## quickstart

```bash
uv run --project . toss-bridge health
uv run --project . toss-bridge open-login
uv run --project . toss-bridge account-summary
uv run --project . toss-bridge order-preview --market us --side buy --symbol AAPL --order-type market --quantity 1
uv run --project . toss-bridge fx-preview --side buy --amount-krw 100000
uv run --project . toss-bridge place-order --preview-receipt-file /tmp/order-preview.json --preview-fingerprint sha256:... --confirm --confirm-text "BUY 3 AAPL LIMIT 201.50 US"
uv run --project . --extra dev pytest
TOSS_BRIDGE_LIVE_E2E=1 uv run --project . --extra dev pytest tests/test_live_e2e.py -q
sh scripts/scrub-check.sh
```

런타임 상태는 기본적으로 아래 경로를 사용한다.

- `~/Library/Application Support/toss-browser-bridge/chrome-profile`
- `~/Library/Application Support/toss-browser-bridge/token`
- `~/Library/Application Support/toss-browser-bridge/daemon.pid`
- `~/Library/Application Support/toss-browser-bridge/daemon.log`
- `~/Library/Application Support/toss-browser-bridge/mutation-journal.jsonl`

`TOSS_BRIDGE_HOME` 환경변수로 override 가능하다.
기본 listen 포트는 `42194`이며, `TOSS_BRIDGE_PORT`로 override 가능하다.

기존 `financier-v2` 내장 bridge와 같은 머신에서 함께 돌릴 때는 포트를 분리해야 한다.

## 예시 출력

- logged out capability matrix: [examples/health-attached-but-logged-out.json](examples/health-attached-but-logged-out.json)
- preview layer guide: [docs/preview-layer.md](docs/preview-layer.md)
- supervised submit guide: [docs/guarded-submit-supervised-validation.md](docs/guarded-submit-supervised-validation.md)

## 현재 범위

- browser-attached read + preview
- zero-money guarded submit preflight
- browser-attached only
- Toss Securities web dependency

## 운영 원칙

- daemon과 전용 Chrome 프로필은 세션 동안 한 번만 올려 두고 유지한다.
- discovery, preview, submit, verify는 이미 붙어 있는 daemon/browser 컨텍스트를 기준으로 진행한다.
- stale daemon을 정리해야 할 명확한 이유가 없는 한, 검증 중 daemon을 반복 재기동하지 않는다.
- final submit unlock은 기본값이 아니며, pytest 경로에서는 환경변수로 요청해도 차단된다.

## 현재 비범위

- 실제 주문 create / verify / 정정 / 취소 / 환전
- 공식 API 안정성 보장
- 헤드리스 세션 재생

## known limitations

- 토스증권 웹 구조나 내부 endpoint가 바뀌면 깨질 수 있다.
- 전용 Chrome 프로필에 직접 로그인해야 한다.
- `health`가 `attached_but_logged_out`일 때는 브라우저 연결만 성공한 상태다.
- `place-order`는 fresh preview 재검증, `prepare` preflight, duplicate-prevention까지만 수행하고, 최종 submit은 아직 막아 둔다.
- `verify-order`는 mutation journal과 현재 read signal을 조합해 `verified_failed` / `verified_success` / `unknown`을 판정한다. final create 이후 supervised submit만 아직 미구현이다.
