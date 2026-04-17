# Phase 4: Supervised Live Validation and Docs 실행 로그

> Append-only. 수정/삭제 금지.

| 항목 | 값 |
|------|-----|
| 시작 | 2026-04-17 15:58 KST |
| Phase 계획 | [phase4-supervised-live-validation-and-docs.md](../phase/phase4-supervised-live-validation-and-docs.md) |

---

### P4-01: automated submit 금지 guard를 runtime에 고정 [●]

**배경**: 실제 submit path가 나중에 열리더라도 pytest 경로에서 실주문이 발생하면 안 된다.

**결정 이유**: 문서 규칙만으로는 부족하다. final submit unlock 요청이 들어와도 test runtime에서 자동 차단되고, diagnostics에 이유가 남아야 한다.

**실행**: `src/toss_browser_bridge/daemon.py`에 final submit env guard를 추가했다. 기본값은 `disabled_by_default`, pytest 내부에서 unlock 요청이 들어오면 `blocked_in_pytest`, 명시적 수동 unlock 조건에서만 `enabled_by_env`가 되도록 정리했다.

**결과**: automated test 경로에서 future final submit unlock이 기본적으로 닫히게 됐다.

---

### P4-02: supervised smoke와 manual checklist를 별도 문서로 분리 [●]

**배경**: live discovery smoke와 실주문 validation은 목적과 위험도가 다르다.

**결정 이유**: 실제 돈이 움직이지 않는 smoke 순서와, future final submit용 supervised checklist를 한 문서에 명확히 나눠 두는 편이 운영 실수를 줄인다.

**실행**: [docs/guarded-submit-supervised-validation.md](../../../docs/guarded-submit-supervised-validation.md)를 추가해 자동화 금지 경계, zero-money smoke 절차, supervised 소액 limit order checklist, 절대 금지 조건을 정리했다.

**결과**: 실주문 검증이 테스트와 분리된 운영 체크리스트로 남게 됐다.

---

### P4-03: 후속 final submit task 입력 자료를 남김 [●]

**배경**: 현재 task는 safety groundwork까지 끝났지만, final `create` semantics는 아직 후속 구현이 필요하다.

**결정 이유**: 다음 task가 시작할 때 다시 discovery 맥락을 복구하느라 시간을 쓰지 않도록 남은 입력을 handoff 형태로 남겨 두는 편이 효율적이다.

**실행**: [references/final-submit-handoff.md](../references/final-submit-handoff.md)에 이미 닫힌 위험, 아직 남은 broker ack 관찰 포인트, next task에서 바로 확인할 질문을 정리했다.

**결과**: 현재 task는 preflight/verify/ops guard를 마감하고, final create 전용 후속 task로 자연스럽게 넘길 수 있게 됐다.
