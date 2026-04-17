# Task Plan: guarded-order-submit

## Goal
실제 주식 주문 submit을 preview-first 안전장치와 verify/recovery 경계 안에서 구현할 수 있도록 Phase별 실행 계획을 고정한다.

## Spec
[Initial](spec/initial.md) | [Review](spec/review-log.md) | [Final](spec/final.md)

## Master Progress

| Phase | Goal | Plan | Notes | Status |
|-------|------|------|-------|--------|
| 0 | Safety Contract and Journal | [plan](phase/phase0-safety-contract-and-journal.md) | [execution](execution/phase0-execution-notes.md) | ● |
| 1 | Submit Path Discovery | [plan](phase/phase1-submit-path-discovery.md) | [execution](execution/phase1-execution-notes.md) | ◐ |
| 2 | Guarded Place-Order | [plan](phase/phase2-guarded-place-order.md) | [execution](execution/phase2-execution-notes.md) | ● |
| 3 | Verify and Recovery | [plan](phase/phase3-verify-and-recovery.md) | [execution](execution/phase3-execution-notes.md) | ● |
| 4 | Supervised Live Validation and Docs | [plan](phase/phase4-supervised-live-validation-and-docs.md) | [execution](execution/phase4-execution-notes.md) | ● |

---

## Phase 0: Safety Contract and Journal

**Goal**: submit contract, preview receipt, confirm phrase, mutation journal 경계를 코드 구현 가능한 수준으로 먼저 고정한다.

### Checklist
- [x] P0-01: `place-order` / `verify-order` CLI 및 daemon command contract 확정
- [x] P0-02: preview receipt schema와 confirm phrase canonicalization 규칙 확정
- [x] P0-03: submit state 및 error taxonomy 구현 기준 확정
- [x] P0-04: mutation journal 최소 schema와 scrub 규칙 확정
- [x] P0-05: `order_submit_ready` / `post_submit_verify_ready` semantics 확정

---

## Phase 1: Submit Path Discovery

**Goal**: 실제 submit path가 fetch 가능한지, UI fallback이 필요한지 실측으로 확인한다.

### Checklist
- [x] P1-01: 국내/미국 limit order submit path 후보 수집
- [x] P1-02: submit request payload와 필수 header/context 조건 확인
- [x] P1-03: broker ack / reject / user cancel / timeout 시그널 분류
- [ ] P1-04: verify signal 조합과 bounded wait 관찰
- [x] P1-05: fetch path 유지 조건과 UI fallback 전환 기준 문서화

---

## Phase 2: Guarded Place-Order

**Goal**: limit order 기준 `place-order`를 preview receipt, confirm phrase, request-time recheck와 함께 구현한다.

### Checklist
- [x] P2-01: `cli.py`에 `place-order` 추가
- [x] P2-02: `daemon.py execute()`에 `place_order` wiring 추가
- [x] P2-03: preview receipt validation, confirm phrase 검증, single in-flight gate 구현
- [x] P2-04: request-time recheck와 duplicate-prevention 구현
- [x] P2-05: `prepare` preflight 및 sanitized broker ack summary 구현
- [x] P2-06: mutation journal append 구현

---

## Phase 3: Verify and Recovery

**Goal**: `verify-order`와 post-submit verify aggregator를 구현해 `submitted`/`unknown` 상태를 복구 가능하게 만든다.

### Checklist
- [x] P3-01: `cli.py`에 `verify-order` 추가
- [x] P3-02: daemon `verify_order` wiring 추가
- [x] P3-03: `completed_orders` / `positions` / `account_summary` verify aggregator 구현
- [x] P3-04: bounded verify window와 `submitted`/`unknown` 분기 구현
- [x] P3-05: daemon restart 후 mutation journal 기반 recovery 구현

---

## Phase 4: Supervised Live Validation and Docs

**Goal**: 실제 돈이 움직이는 범위에 맞는 수동 supervised validation 절차와 문서를 마무리한다.

### Checklist
- [x] P4-01: automated test에서 실제 submit 금지 guard 추가
- [x] P4-02: live discovery smoke test와 수동 submit checklist 정리
- [x] P4-03: limit order 소액 supervised validation 수행 기준 정리
- [x] P4-04: README / docs에 submit safety 경계 반영
- [x] P4-05: FX submit / cancel-order 후속 task 입력 자료 정리

---

## Key Questions
1. 실제 주문 submit이 fetch 기반으로 가능한지, 아니면 마지막 단계에서 UI confirm이 강제되는지
2. 국내/미국 submit path가 동일한지, 시장별 분기가 필요한지
3. bounded verify window의 기본 시간값을 얼마로 둘지

## Decisions Made
- 첫 실제 write scope는 `place-order`만 다룬다: FX submit과 cancel-order를 동시에 열면 safety contract가 흐려진다.
- 초기 실제 submit은 limit order만 연다: market order는 가격 슬리피지와 ambiguity가 더 크다.
- discovery를 구현보다 먼저 둔다: 실제 돈이 움직이는 path는 추측 구현을 허용하면 안 된다.
- `verify-order`를 별도 Phase로 둔다: `unknown` recovery가 없는 submit은 운영상 미완료다.

## Errors Encountered

없음.

## Status
**Current**: Completed for current safety scope
**Updated**: 2026-04-17 16:03 KST
**Next**: final `create`를 여는 별도 follow-up task에서 supervised unlock과 broker ack semantics를 구현
