# Phase 0: Safety Contract and Journal 실행 로그

> Append-only. 수정/삭제 금지.

| 항목 | 값 |
|------|-----|
| 시작 | 2026-04-17 15:25 KST |
| Phase 계획 | [phase0-safety-contract-and-journal.md](../phase/phase0-safety-contract-and-journal.md) |

---

### P0-01: `place-order` / `verify-order` command contract를 CLI와 daemon에 고정 [●]

**배경**: 실제 submit path discovery 전에 외부 계약이 흔들리면 이후 Phase가 테스트 없이 뒤틀린다.

**결정 이유**: `place-order`는 `preview_receipt + preview_fingerprint + confirm + confirm_text`를 강제하고, `verify-order`는 `mutation_id`만 받는 최소 계약으로 고정하는 편이 후속 submit/verify 구현을 좁게 유지한다.

**실행**: `src/toss_browser_bridge/cli.py`와 `src/toss_browser_bridge/daemon.py`에 `place-order`, `verify-order` surface를 추가했다. 실제 path가 없으므로 현재는 의도적으로 `capability_not_ready`를 반환한다.

**결과**: submit phase에서 필요한 최소 인자와 에러 transport가 코드로 고정됐다.

---

### P0-02: preview receipt와 confirm phrase 규칙을 helper로 분리 [●]

**배경**: preview response 전체를 submit 입력으로 쓰면 후속 phase에서 필드 drift와 민감정보 경계가 모호해진다.

**결정 이유**: receipt를 canonical subset으로 줄이고 confirm phrase를 ASCII deterministic helper로 고정하면, CLI와 daemon이 같은 규칙을 재사용할 수 있다.

**실행**: `src/toss_browser_bridge/submit.py`를 추가해 `build_order_preview_receipt()`, `validate_order_preview_receipt()`, `build_order_confirm_phrase()`, `validate_place_order_params()`를 구현했다. `order-preview` 응답에 `preview_receipt`와 `confirm_phrase`도 추가했다.

**결과**: preview receipt와 confirm phrase가 테스트 가능한 순수 함수로 분리됐다.

---

### P0-03: submit state/error taxonomy와 transport를 분리 [●]

**배경**: guarded submit에서 입력 오류, submit 차단, capability 미준비를 모두 500으로 올리면 실제 돈이 움직이는 단계에서 원인 분리가 어렵다.

**결정 이유**: preview와 같은 방식으로 mutation domain error를 transport에서 분리하면, 후속 Phase에서도 HTTP 200 domain error를 유지한 채 상태 모델만 넓힐 수 있다.

**실행**: `MutationDomainError`와 `MutationValidationError`를 추가하고, `BridgeHandler`가 preview/mutation domain error를 공통 처리하도록 변경했다.

**결과**: `invalid_request`, `submit_blocked`, `capability_not_ready`, `logged_out` 등이 runtime error와 분리됐다.

---

### P0-04: mutation journal 최소 schema와 scrub 규칙을 구현 [●]

**배경**: recovery가 필요한 write path인데도 journal schema가 없으면 나중에 raw payload 저장 같은 위험한 지름길이 생긴다.

**결정 이유**: append-only JSONL과 allowlist 기반 scrub를 먼저 구현하면 이후 Phase는 이 경계 안에서만 움직이게 된다.

**실행**: `bridge_lib.py`에 `mutation-journal.jsonl` 경로를 추가하고, `submit.py`에 journal sanitize/append/writable helper를 구현했다. 허용 필드와 금지 필드를 테스트로 고정했다.

**결과**: mutation journal은 recovery 최소 필드만 저장하고 토큰/계좌번호/raw body는 버린다.

---

### P0-05: health readiness semantics를 submit safety 기준으로 확장 [●]

**배경**: preview readiness만으로 submit readiness를 열면 discovery와 recovery 미구현 상태에서 false positive가 생긴다.

**결정 이유**: `order_submit_ready`를 submit path discovery, verify path discovery, journal writable, single in-flight gate까지 포함한 보수적 계산으로 고정해야 한다.

**실행**: `classify_health_payload()`에 runtime mutation state를 주입하도록 바꾸고, `post_submit_verify_ready` capability를 추가했다.

**결과**: 현재 logged-in 상태에서도 `order_submit_ready=false`, `post_submit_verify_ready=false`가 유지되며, 왜 submit이 아직 닫혀 있는지 코드로 설명된다.

---

### P0-06: contract/journal/readiness 회귀 테스트 추가 [●]

**배경**: 실제 submit Phase에 들어가기 전에 safety contract이 깨지지 않도록 자동 테스트를 붙여야 한다.

**결정 이유**: order preview, daemon transport, health capability, submit contract, journal scrub를 각각 고정하면 이후 discovery/submit 변경 시 영향 범위를 좁힐 수 있다.

**실행**: `tests/test_order_preview.py`, `tests/test_health_capabilities.py`, `tests/test_daemon.py`, `tests/test_submit_contract.py`를 추가/확장했다.

**결과**: Phase 0 규칙이 `uv run --extra dev pytest`로 자동 검증된다.
