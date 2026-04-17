# Preview Layer

## 개요

현재 `toss-browser-bridge`는 read surface와 함께 preview-first write scaffold를 제공한다.

지원 범위:

- `order-preview`
- `fx-preview`

아직 지원하지 않는 범위:

- 실제 주문 제출
- 실제 환전 제출
- 정정/취소 제출

## 명령 예시

```bash
uv run toss-bridge order-preview --market us --side buy --symbol AAPL --order-type market --quantity 1
uv run toss-bridge fx-preview --side buy --amount-krw 100000
uv run toss-bridge fx-preview --side sell --amount-usd 50
```

## 응답 계약

preview 응답은 다음 필드를 공통으로 가진다.

- `preview_id`: 프로세스 로컬 식별자
- `preview_fingerprint`: canonical JSON + SHA-256 기반 fingerprint
- `preview_state`: `preview_ready` 또는 `blocked`
- `warnings`: submit 전 사람이 봐야 하는 항목
- `blocking_issues`: submit 전에 해결돼야 하는 항목
- `submit_candidate`: 후속 submit phase에서 payload 동일성 검증에 쓸 핵심 필드
- `verification_plan`: submit 뒤 재조회 계획

`order-preview`는 guarded submit Phase 0부터 아래 필드도 함께 제공한다.

- `preview_receipt`: `place-order` contract에서 쓰는 canonical subset
- `confirm_phrase`: ASCII 고정 형식 확인 문구

domain error는 HTTP 200 JSON body로 반환된다.

- `invalid_request`
- `logged_out`
- `capability_not_ready`
- `preview_failed`

`runtime_error`는 예기치 않은 예외에만 남긴다.

## Capability 의미

`health.data.capabilities`는 read/write readiness를 분리해 보여준다.

- `order_preview_ready`: logged-in + account summary + quote 준비 완료
- `post_submit_verify_ready`: `completed_orders` + `positions` + `account_summary` verify path가 준비됐을 때만 true
- `order_submit_ready`: submit path discovery, verify path, journal writable, single in-flight gate를 모두 만족할 때만 true
- `fx_preview_ready`: logged-in + account summary + FX rate/buy/sell quote 준비 완료
- `fx_submit_ready`, `cancel_order_ready`: 아직 false 고정

현재 `place-order`는 단순 contract 확인을 넘어서 아래 preflight를 수행한다.

- `preview_receipt` / `preview_fingerprint` / `confirm_text` 검증
- fresh `order-preview` 재평가
- request-time preview fingerprint drift 차단
- `prepare` fetch preflight
- `preparedOrderInfo` 기반 trade type / order price type / quantity drift 차단
- mutation journal 기반 duplicate-prevention
- sanitized mutation journal append

미국 매수 preflight는 현재 실측 기준으로 `currencyMode=KRW` + auto-exchange prepare 경로를 사용한다. 이 경로에서는 `preparedOrderInfo.price` 의미가 auto-exchange 표현과 섞일 수 있어, hard-block 비교는 `tradeType` / `orderPriceType` / `quantity`에 우선 둔다.

최종 `create` path는 아직 열지 않았다. 따라서 guarded preflight를 통과해도 마지막에는 `capability_not_ready`로 멈춘다.

현재 `verify-order`는 mutation journal을 기준으로 아래 verify signal을 다시 조회한다.

- `completed_orders`
- `positions`
- `account_summary`

이 조합으로 matching order가 보이면 `verified_success`, submit이 애초에 차단된 mutation이면 `verified_failed`, 현재 verify window에서 확정 근거가 부족하면 `unknown`을 반환한다.

현재 verify window는 bounded poll로 동작한다. 즉, `verify-order`는 짧은 횟수 안에서만 재조회하고, 끝까지 확정 근거가 없으면 무한 대기 대신 `unknown`으로 멈춘다.

final submit unlock은 별도 안전장치로 묶는다.

- 기본값은 `disabled_by_default`
- `TOSS_BRIDGE_ENABLE_FINAL_SUBMIT=1`로만 unlock 요청 가능
- pytest 내부에서는 `TOSS_BRIDGE_ALLOW_TEST_FINAL_SUBMIT=1`이 없으면 `blocked_in_pytest`

현재 daemon은 `submit path discovered`, `verify path discovered`, `final submit enabled`를 분리해 내부 상태로 들고 있다. 따라서 `post_submit_verify_ready`는 true가 될 수 있지만, `order_submit_ready`는 final `create` safety 경계가 닫혀 있는 동안 계속 false다.

## 검증

기본 자동 검증:

```bash
uv run --extra dev pytest
uv run python -m py_compile src/toss_browser_bridge/*.py
sh scripts/scrub-check.sh
```

실제 로그인 세션 기반 검증:

```bash
TOSS_BRIDGE_LIVE_E2E=1 uv run --extra dev pytest tests/test_live_e2e.py -q
```

이 live test는 이미 떠 있는 daemon/browser 세션을 그대로 사용한다. 코드 변경으로 stale daemon이 생겼을 때만 예외적으로 한 번 재기동해서 새 구현을 검증한다.
