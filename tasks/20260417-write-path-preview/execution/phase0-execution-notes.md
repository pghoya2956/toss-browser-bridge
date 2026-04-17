# Phase 0: Contract and Error Model 실행 로그

> Append-only. 수정/삭제 금지.

| 항목 | 값 |
|------|-----|
| 시작 | 2026-04-17 12:20 KST |
| Phase 계획 | [phase0-contract-and-error-model.md](../phase/phase0-contract-and-error-model.md) |

---

### P0-01: preview command contract를 CLI에 반영 [●]

**배경**: preview layer는 Phase 1 구현 전에 외부 계약부터 고정해야 이후 error taxonomy와 live E2E를 안정적으로 얹을 수 있다.

**결정 이유**: `order-preview`와 `fx-preview`를 둘 다 CLI surface에 먼저 노출하면, 실제 구현 범위와 미구현 범위를 JSON 계약으로 분리해 다룰 수 있다.

**실행**: `cli.py`에 `order-preview`와 `fx-preview` 서브커맨드를 추가하고, `--order-type` 필수, FX 금액 필드 분리 등 spec-reviewed 인자 규칙을 반영했다.

**결과**: preview command name과 필수 인자 스키마가 CLI에서 고정됐다.

---

### P0-02: preview domain error transport를 분리 [●]

**배경**: preview path는 입력 오류나 readiness 실패를 `runtime_error` 500으로 올리면 안 된다.

**결정 이유**: `PreviewDomainError`를 별도 타입으로 두고 handler에서 HTTP 200 JSON body로 직렬화하면, read path transport를 깨지 않으면서 domain error만 분리할 수 있다.

**실행**: `src/toss_browser_bridge/preview.py`에 `PreviewDomainError`를 추가하고, `BridgeHandler.do_POST()`에서 preview domain error를 별도 분기 처리하도록 바꿨다.

**결과**: `invalid_request`, `logged_out`, `capability_not_ready` 같은 preview 오류가 더 이상 500으로 승격되지 않는다.

---

### P0-03: health readiness semantics를 preview 기준으로 반영 [●]

**배경**: `browser_attached`와 preview 가능 여부를 동일시하면 live E2E에서 false positive가 생긴다.

**결정 이유**: `order_preview_ready`를 `logged-in + account_summary_ready + quote_ready`로 계산하고, `fx_preview_ready`는 discovery 전까지 false로 유지하는 것이 spec과 일치한다.

**실행**: `classify_health_payload()`를 수정해 `order_preview_ready`를 계산하고, mutation capability placeholder들은 명시적으로 false 유지하도록 정리했다.

**결과**: health capability matrix가 preview base readiness를 드러내도록 바뀌었다.

---

### P0-04: canonical fingerprint helper를 추가 [●]

**배경**: preview 응답이 후속 submit phase의 신뢰 기준이 되려면 입력 순서와 무관한 안정적 fingerprint가 필요하다.

**결정 이유**: 순수 helper 모듈로 분리해 두면 order preview와 future FX/submit phase가 같은 canonicalization 규칙을 재사용할 수 있다.

**실행**: `preview.py`에 canonical JSON 직렬화, SHA-256 fingerprint 생성, preview_id 생성, preview_state 계산 helper를 추가했다.

**결과**: preview fingerprint 규칙이 코드와 테스트로 고정됐다.

---

### P0-05: contract/error/readiness 테스트를 추가 [●]

**배경**: preview contract은 Phase 1 builder보다 먼저 회귀 방지망이 필요하다.

**결정 이유**: validation, readiness, domain error, fingerprint를 각각 순수 테스트로 고정하면 order preview 로직 변경 시 원인 분리가 쉬워진다.

**실행**: `tests/test_preview_validation.py`, `tests/test_preview_contract.py`, `tests/test_health_capabilities.py`, `tests/test_daemon.py`를 확장했다.

**결과**: Phase 0 핵심 규칙이 자동 테스트로 보호된다.
