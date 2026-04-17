# Phase 2: FX Preview Discovery and Build

## 목표

FX endpoint family를 실측한 뒤 `fx-preview`를 보수적으로 구현한다.

## 범위

- FX 환율/수수료/잔액 endpoint discovery
- `fx-preview` CLI/daemon wiring
- FX preview 계산 로직과 readiness semantics 구현
- endpoint 불확실성 degrade 테스트 작성

## 제외 범위

- 실제 FX submit
- 장기 cache 또는 quote history 저장

## 체크리스트

- [ ] P2-01: FX 관련 endpoint family 조사 및 확정
- [ ] P2-02: `cli.py`에 `fx-preview` 서브커맨드 추가
- [ ] P2-03: `daemon.py execute()`에 `fx_preview` 추가
- [ ] P2-04: FX preview builder 및 `fx_preview_ready` 구현
- [ ] P2-05: endpoint 미확정/부분 실패 시 degrade 규칙 테스트 추가

## 검증 기준

- KRW/USD 단일 금액 입력 제약이 지켜진다.
- FX endpoint가 부족하면 health에서 과대 노출하지 않는다.
- 계산 실패와 capability failure가 분리된다.

## 리스크

- FX 관련 endpoint를 fetch 기반으로 안정적으로 확보하지 못할 수 있다.
- 수수료/환율 데이터 시점 차이로 preview 오차가 생길 수 있다.

## 완화 방안

- discovery 단계와 build 단계를 분리한다.
- 불확실한 값은 warning으로 노출하고 submit phase에서 재검증하도록 남긴다.

## 완료 조건

- P2-01~P2-05 완료
- logged-in 로컬 E2E로 `fx-preview` 실제 응답 또는 명시적 blocked 상태 검증
