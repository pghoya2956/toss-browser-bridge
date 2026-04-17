# Phase 2: FX Preview Discovery and Build 실행 로그

> Append-only. 수정/삭제 금지.

| 항목 | 값 |
|------|-----|
| 시작 | 2026-04-17 12:44 KST |
| Phase 계획 | [phase2-fx-preview.md](../phase/phase2-fx-preview.md) |

---

### P2-01: FX endpoint family를 실측으로 확정 [●]

**배경**: FX preview는 order preview와 달리 endpoint family가 문서상 확정되지 않았다.

**결정 이유**: 정적 JS grep만으로는 신뢰하기 어려워서, 공개 `환율` 페이지의 실제 네트워크 요청을 먼저 확인한 뒤 API 후보를 고정했다.

**실행**: 공개 `https://www.tossinvest.com/indices/exchange-rate` route를 열어 네트워크 요청을 확인했고, `wts-info-api`의 `/api/v1/product/exchange-rate`와 `wts-api`의 `/api/v1/exchange/current-quote/for-buy`, `/api/v1/exchange/current-quote/for-sell`를 후보로 확정했다. 이후 각 endpoint를 직접 호출해 응답 구조를 확인했다.

**결과**: FX preview에 필요한 공개 quote/rate endpoint family와 핵심 필드(`rateQuoteId`, `usdRate`, `favorablePercent`, `validTill`)를 실측 기준으로 확보했다.

---

### P2-02: health probe와 readiness semantics에 FX를 반영 [●]

**배경**: FX preview가 실제 구현됐는데 health가 계속 false를 반환하면 capability matrix가 의미를 잃는다.

**결정 이유**: `logged-in + account_summary_ready + fx rate/quote endpoints ready`를 base readiness로 두면 과대 노출 없이 preview 가능성을 표현할 수 있다.

**실행**: `health()` probe에 FX rate/buy/sell quote endpoint를 추가하고 `classify_health_payload()`에서 `fx_preview_ready`를 계산하도록 수정했다.

**결과**: logged-in 실측 기준으로 `fx_preview_ready=true`, logged-out fixture 기준으로는 false가 유지된다.

---

### P2-03: FX preview builder를 구현 [●]

**배경**: FX preview는 stub 상태였고, 현재 단계에서는 submit 없이도 실제 환전 조건을 보여줄 수 있어야 한다.

**결정 이유**: `account_summary()`를 source balance로 재사용하고, 공개 FX quote endpoints를 조합하면 보수적인 preview를 충분히 구성할 수 있다.

**실행**: `fx_preview()`에서 입력 검증 후 `account_summary()`와 FX rate/quote fetch를 수행하고, source/target currency, source amount, target amount, applied rate, spread, valid till, submit candidate를 계산하도록 구현했다.

**결과**: buy/sell 양방향 KRW/USD preview가 실제 JSON 응답으로 동작한다.

---

### P2-04: FX blocking/degrade 규칙을 분리 [●]

**배경**: FX는 endpoint failure와 잔액 부족을 같은 오류로 처리하면 submit 준비 상태를 판단하기 어렵다.

**결정 이유**: endpoint failure는 domain error, 잔액 부족은 `blocked` preview로 나누는 것이 submit phase와 연결하기 좋다.

**실행**: FX quote fetch 실패는 `capability_not_ready`, 응답 구조 이상은 `preview_failed`, source balance 부족은 `blocking_issues`로 반환하도록 구현했다.

**결과**: capability failure와 business blocking이 분리됐다.

---

### P2-05: automated + live E2E로 FX preview를 검증 [●]

**배경**: 공개 FX endpoints는 구조가 바뀔 수 있어 코드와 실측을 같이 잡아야 한다.

**결정 이유**: pure unit test만 두면 로그인 세션과 health readiness 연동이 빠질 수 있어, live E2E까지 같은 턴에 확인했다.

**실행**: `tests/test_fx_preview.py`, `tests/test_health_capabilities.py`, `tests/test_live_e2e.py`를 갱신하고 `TOSS_BRIDGE_LIVE_E2E=1 uv run --extra dev pytest tests/test_live_e2e.py -q`로 실제 세션 검증을 돌렸다.

**결과**: `fx-preview`가 logged-in 세션에서 실제 응답을 반환하고 `health.fx_preview_ready`와 일치함을 확인했다.
