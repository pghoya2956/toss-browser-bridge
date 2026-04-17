# Task Plan: write-path-preview

## Goal
`order-preview`와 `fx-preview`를 preview-first mutation architecture에 맞게 구현할 수 있도록 Phase별 실행 계획을 고정한다.

## Spec
[Initial](spec/initial.md) | [Review](spec/review-log.md) | [Final](spec/final.md)

## Master Progress

| Phase | Goal | Plan | Notes | Status |
|-------|------|------|-------|--------|
| 0 | Contract and Error Model | [plan](phase/phase0-contract-and-error-model.md) | [notes](execution/phase0-execution-notes.md) | ● |
| 1 | Order Preview | [plan](phase/phase1-order-preview.md) | [notes](execution/phase1-execution-notes.md) | ● |
| 2 | FX Preview Discovery and Build | [plan](phase/phase2-fx-preview.md) | [notes](execution/phase2-execution-notes.md) | ● |
| 3 | Preview Quality and Handoff | [plan](phase/phase3-preview-quality-and-handoff.md) | [notes](execution/phase3-execution-notes.md) | ● |

---

## Phase 0: Contract and Error Model

**Goal**: preview command contract, domain error 규칙, readiness semantics를 코드 구현 가능한 수준으로 고정한다.

### Checklist
- [x] P0-01: CLI 명령 이름과 필수 인자 규칙 확정
- [x] P0-02: daemon preview error transport 규칙 구현
- [x] P0-03: `order_preview_ready` / `fx_preview_ready` 판정 기준 구현
- [x] P0-04: preview fingerprint 입력 집합 구현

---

## Phase 1: Order Preview

**Goal**: `order-preview`를 실제 동작하는 read-assisted preview 명령으로 구현한다.

### Checklist
- [x] P1-01: `cli.py`에 `order-preview` 서브커맨드 추가
- [x] P1-02: `daemon.py execute()`에 `order_preview` wiring 추가
- [x] P1-03: order preview 사전 조회 endpoint 세트와 builder 구현
- [x] P1-04: `submit_candidate`, `warnings`, `blocking_issues`, `preview_state` 구현
- [x] P1-05: logged-out, invalid-request, partial dependency failure 케이스 테스트 추가

---

## Phase 2: FX Preview Discovery and Build

**Goal**: FX endpoint family를 확인한 뒤 `fx-preview`를 보수적으로 구현한다.

### Checklist
- [x] P2-01: FX 환율/수수료/잔액 endpoint family 확인
- [x] P2-02: `cli.py`에 `fx-preview` 서브커맨드 추가
- [x] P2-03: `daemon.py execute()`에 `fx_preview` wiring 추가
- [x] P2-04: FX preview 계산 로직과 `fx_preview_ready` 구현
- [x] P2-05: endpoint 불확실성 및 capability degrade 테스트 추가

---

## Phase 3: Preview Quality and Handoff

**Goal**: preview layer를 안정화하고 후속 submit task로 넘길 scaffold를 마무리한다.

### Checklist
- [x] P3-01: preview fingerprint 안정성 테스트 추가
- [x] P3-02: privacy scrub 규칙을 preview diagnostics에 적용
- [x] P3-03: logged-in / logged-out 통합 검증 정리
- [x] P3-04: README 또는 docs에 preview layer 사용법 반영
- [x] P3-05: submit/cancel 후속 task 입력 자료 정리

---

## Key Questions
1. FX preview용 실제 환율/수수료 endpoint family가 무엇인가
2. future submit phase에서 `preview_id`를 사용할지 `preview_fingerprint`만 사용할지
3. `post_submit_verify_ready`를 health capability에 언제 노출할지

## Decisions Made
- Preview 구현은 Phase 0 → 3 순으로 진행한다: contract 미고정 상태에서 endpoint 구현으로 들어가면 되돌림 비용이 커진다.
- Order preview를 FX보다 먼저 구현한다: 현재 코드베이스와 검증 자산은 order path 쪽이 더 명확하다.
- FX는 discovery를 별도 체크리스트로 둔다: endpoint family 불확실성을 숨기지 않기 위해서다.
- execution 로그는 Phase 시작 전까지 만들지 않는다: append-only 원칙을 지키고, 빈 로그 파일을 남기지 않기 위해서다.

## Errors Encountered

### Phase 1 (2026-04-17)
- **stale daemon이 새 preview 코드를 가림**: live E2E 첫 실행에서 `order_preview_ready=false`, `unsupported kind: order_preview`가 나왔고, 원인은 기존 daemon 프로세스가 살아 있어 새 코드를 읽지 못한 것이었다. live test 시작 시 `shutdown`으로 daemon을 재기동하도록 고쳤다.
### Phase 2 (2026-04-17)
- **정적 JS grep만으로 FX endpoint가 바로 드러나지 않음**: bundle 문자열만으로는 신뢰할 수 있는 endpoint family를 얻지 못했다. 공개 `환율` 페이지 네트워크 요청 실측으로 `/api/v1/product/exchange-rate`, `/api/v1/exchange/current-quote/for-buy`, `/api/v1/exchange/current-quote/for-sell`를 확정했다.

## Status
**Current**: Completed
**Updated**: 2026-04-17 12:55 KST
**Next**: submit/cancel phase를 별도 task로 시작
