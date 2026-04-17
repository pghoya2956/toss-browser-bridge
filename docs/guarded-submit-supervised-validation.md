# Guarded Submit Supervised Validation

## 목적

실제 돈이 움직일 수 있는 submit phase를 열기 전에, 자동화 경계와 사람이 따라야 하는 supervised 절차를 분리한다.

## 자동화 금지 경계

- pytest 경로에서는 final submit unlock을 허용하지 않는다.
- `TOSS_BRIDGE_ENABLE_FINAL_SUBMIT=1`만으로는 pytest 내부에서 final submit이 열리지 않는다.
- pytest 안에서 final submit unlock을 시도하면 runtime diagnostics에 `final_submit_guard_reason=blocked_in_pytest`가 남는다.
- live E2E는 read, preview, guarded preflight, verify recovery까지만 검증한다.

현재 기본 상태:

- `order_submit_ready=false`
- `post_submit_verify_ready=true`
- `final_submit_enabled=false`

## Live Discovery Smoke

실제 돈이 움직이지 않는 smoke 순서:

```bash
uv run --project . toss-bridge health
uv run --project . toss-bridge account-summary
uv run --project . toss-bridge positions
uv run --project . toss-bridge completed-orders --limit 3
uv run --project . toss-bridge quote --symbol AAPL
uv run --project . toss-bridge order-preview --market us --side buy --symbol AAPL --order-type limit --quantity 1 --limit-price 999.99
uv run --project . toss-bridge place-order --preview-receipt-file /tmp/order-preview.json --preview-fingerprint sha256:... --confirm --confirm-text "BUY 1 AAPL LIMIT 999.99 US"
uv run --project . toss-bridge verify-order --mutation-id mut_...
```

완료 기준:

- `health`에서 `post_submit_verify_ready=true`
- `place-order`가 `capability_not_ready`로 끝나고 `diagnostics.mutation_id`를 반환
- `verify-order`가 그 `mutation_id`를 받아 `verified_failed` 또는 `unknown`을 일관되게 반환

## Supervised 소액 Limit Order Checklist

실주문은 아직 기본 기능으로 열지 않는다. 아래 체크리스트는 final `create`를 여는 후속 task에서만 사용한다.

사전 조건:

- 전용 Chrome profile이 이미 로그인된 상태
- daemon/browser 세션은 이미 떠 있고, stale 코드 반영이 필요한 경우에만 한 번 재기동
- `health`에서 `order_preview_ready=true`, `post_submit_verify_ready=true`
- supervised 대상 주문은 소액 `limit order` 1건만 사용
- 주문 금액은 사용자가 사전에 정한 허용 손실 범위 안이어야 함

절대 진행 금지:

- `order_submit_ready=false`인 상태에서 final submit unlock을 임의로 우회
- market order
- 여러 주문을 연속으로 자동화
- 로그아웃 직후 세션 불안정 상태
- verify path가 흔들리는 날의 submit 검증

수동 진행 순서:

- fresh `order-preview` 생성
- preview receipt, confirm phrase, price, quantity, symbol을 사람 눈으로 재확인
- final submit unlock 의도와 대상 주문을 터미널에 명시적으로 남김
- 1건만 수동 실행
- 즉시 `verify-order --mutation-id ...` 수행
- `completed-orders`, `positions`, `account-summary`를 사람이 교차 확인
- 결과를 execution note에 append-only로 기록

수동 완료 기준:

- broker ack와 verify snapshot이 서로 모순되지 않음
- `verified_success` 또는 보수적 `unknown` 중 하나로 수렴
- duplicate-prevention이 동일 receipt 재사용을 막음

## 운영 메모

- final submit unlock은 기본값이 아니다.
- supervised validation은 테스트가 아니라 운영 리허설에 가깝다.
- ambiguous result는 성공으로 간주하지 않고 `unknown`으로 남긴다.
