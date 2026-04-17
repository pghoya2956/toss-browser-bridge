# Phase 1: Order Preview 실행 로그

> Append-only. 수정/삭제 금지.

| 항목 | 값 |
|------|-----|
| 시작 | 2026-04-17 12:28 KST |
| Phase 계획 | [phase1-order-preview.md](../phase/phase1-order-preview.md) |

---

### P1-01: `order-preview` CLI surface를 실제 호출 경로에 연결 [●]

**배경**: preview contract이 문서와 테스트에만 있으면 사용자는 실제로 검증할 수 없다.

**결정 이유**: Phase 0에서 추가한 CLI 인자를 바로 daemon query kind까지 연결해야 live E2E가 가능하다.

**실행**: `cli.py` command map에 `order_preview`를 추가하고 파라미터 전달을 연결했다.

**결과**: `toss-bridge order-preview ...`가 daemon query로 실제 전달된다.

---

### P1-02: daemon execute wiring을 추가 [●]

**배경**: CLI surface만 열려 있으면 daemon은 여전히 `unsupported kind`를 반환한다.

**결정 이유**: `execute()`에 preview kind를 추가해 routing을 먼저 고정하면, 이후 builder/diagnostics 구현을 메서드 내부에서 독립적으로 확장할 수 있다.

**실행**: `TossBridgeRuntime.execute()`에 `order_preview`와 `fx_preview` 분기를 추가했다.

**결과**: preview path가 unsupported kind가 아니라 도메인 로직으로 진입한다.

---

### P1-03: order preview dependency flow를 기존 read path 위에 구축 [●]

**배경**: 같은 endpoint family를 다시 직접 구현하면 read path와 preview path가 쉽게 드리프트한다.

**선택지**:
- A) preview 전용 fetch 코드를 새로 작성
- B) 기존 `account_summary()`, `quote()`, `positions()`를 의존성으로 재사용 ← 선택

**결정 이유**: 현재 코드베이스에서 가장 큰 레버리지는 검증된 read fetch 경로를 재사용하고 diagnostics만 preview 수준으로 합치는 것이다.

**실행**: `order_preview()`가 `account_summary()`, `quote()`, sell 시 `positions()`를 호출하고, 각 응답의 diagnostics를 합쳐 preview context를 구성하도록 구현했다.

**결과**: preview endpoint 세트가 기존 read path와 같은 실측 기반으로 움직이게 됐다.

---

### P1-04: preview response builder를 구현 [●]

**배경**: preview는 단순 echo가 아니라 submit scaffold 역할을 해야 한다.

**결정 이유**: `inputs`, `derived`, `submit_candidate`, `verification_plan`, `preview_fingerprint`를 한 응답에 담아야 다음 submit phase에서 재설계 비용이 줄어든다.

**실행**: buy/sell 공통 builder를 `order_preview()`에 구현하고, buying power/position quantity/market mismatch/market status를 warning 또는 blocking issue로 분류했다.

**결과**: 실제 logged-in 세션에서 `preview_ready` 또는 `blocked` 상태를 갖는 preview JSON이 생성된다.

---

### P1-05: sell preview request-time positions 재확인 분기 [●]

**배경**: health 시점의 `positions_ready`만으로 sell 가능 여부를 보장할 수 없다.

**결정 이유**: sell preview는 요청 시점 positions 재조회 실패를 domain error로 돌리고, 수량 부족은 `blocked` preview로 남겨야 spec과 일치한다.

**실행**: sell branch에서 `positions()`를 반드시 다시 호출하고, dependency failure와 insufficient quantity를 분리 처리했다.

**결과**: sell preview가 readiness failure와 business blocking issue를 구분해 반환한다.

---

### P1-06: automated + live E2E 검증을 추가 [●]

**배경**: preview는 브라우저 부착형 도구라 unit test만으로는 완료라고 볼 수 없다.

**결정 이유**: 로그인 세션이 있을 때 바로 재실행 가능한 live pytest를 만들면 이후 회귀 검증 비용이 크게 줄어든다.

**실행**: `tests/test_order_preview.py`와 `tests/test_live_e2e.py`를 추가했다. live test는 시작 시 daemon을 재기동해 stale process가 새 코드를 가리지 못하게 만들었다.

**결과**: `TOSS_BRIDGE_LIVE_E2E=1 uv run --extra dev pytest tests/test_live_e2e.py -q`로 read path + order preview를 실제 세션에서 재현 가능해졌다.

**발견**: 처음 live E2E가 실패한 원인은 health semantics가 아니라 기존 daemon이 살아 있어 새 `order_preview` 코드를 읽지 못한 것이었다.
