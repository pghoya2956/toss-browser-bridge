# Phase 3: Preview Quality and Handoff 실행 로그

> Append-only. 수정/삭제 금지.

| 항목 | 값 |
|------|-----|
| 시작 | 2026-04-17 12:52 KST |
| Phase 계획 | [phase3-preview-quality-and-handoff.md](../phase/phase3-preview-quality-and-handoff.md) |

---

### P3-01: fingerprint 안정성 테스트를 유지 자산으로 고정 [●]

**배경**: preview fingerprint는 submit phase와 직접 연결되기 때문에 지금 단계에서 회귀 테스트가 필수다.

**결정 이유**: 이미 추가한 canonicalization/fingerprint 테스트를 Phase 산출물에 명시적으로 연결해 두면 후속 작업자가 신뢰 기준을 바로 파악할 수 있다.

**실행**: `tests/test_preview_contract.py`를 Phase 3 검증 자산으로 명시하고 task 상태에 반영했다.

**결과**: fingerprint 안정성 기준이 문서와 테스트 양쪽에서 고정됐다.

---

### P3-02: preview diagnostics scrub 규칙을 테스트로 보강 [●]

**배경**: preview diagnostics는 endpoint matrix를 포함하므로 민감 필드가 새어 들어갈 가능성을 계속 경계해야 한다.

**결정 이유**: 현재 `sanitize_endpoint_entry()`가 name/method/path/status_code/ok/error만 남기므로, 이 경계를 테스트로 잡아두는 것이 가장 저비용이다.

**실행**: preview/health 테스트를 FX 포함 최신 shape로 갱신하고, diagnostics가 sanitized endpoint matrix만 유지하는 전제를 보존했다.

**결과**: preview diagnostics가 raw URL, 헤더, token, accountNo를 노출하지 않는 현재 경계가 유지된다.

---

### P3-03: logged-in 통합 검증 기록 정리 [●]

**배경**: 로컬 E2E를 돌렸더라도 task 산출물에 남기지 않으면 다음 작업자가 다시 같은 검증을 반복하게 된다.

**결정 이유**: read + order preview + FX preview까지 한 번에 검증된 사실을 execution/task_plan에 남겨두는 것이 handoff 비용을 줄인다.

**실행**: live pytest와 실측 CLI 결과를 기준으로 logged-in 검증 범위를 execution log와 task 상태에 반영했다.

**결과**: preview layer의 실사용 검증 범위가 task 산출물에 남았다.

---

### P3-04: preview usage 문서를 갱신 [●]

**배경**: 공개 surface가 늘었는데 README가 따라오지 않으면 사용자가 실제 가능 범위를 오해한다.

**결정 이유**: README와 별도 preview 문서를 함께 두면 quickstart와 deeper handoff를 분리할 수 있다.

**실행**: README를 preview-aware 상태로 업데이트하고 `docs/preview-layer.md`를 추가했다.

**결과**: order/fx preview 사용법, live E2E 실행 방법, capability 의미가 문서화됐다.

---

### P3-05: submit/cancel 후속 task 입력 자료 정리 [●]

**배경**: preview phase가 끝난 뒤 바로 submit/cancel spec으로 넘어갈 수 있어야 한다.

**결정 이유**: confirmed endpoint family, fingerprint contract, 남은 open question을 한 문서에 정리하면 후속 task가 현재 implementation을 다시 역추적하지 않아도 된다.

**실행**: `references/submit-handoff.md`를 추가해 확인된 FX/order preview 자산과 다음 write phase의 입력 자료를 정리했다.

**결과**: submit/cancel phase의 시작점이 별도 handoff 문서로 고정됐다.
