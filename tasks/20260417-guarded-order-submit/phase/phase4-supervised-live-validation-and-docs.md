# Phase 4: Supervised Live Validation and Docs

## 목표

실제 돈이 움직이는 범위에 맞는 수동 supervised validation 절차와 문서를 마무리한다.

## 범위

- automated test에서 실제 submit 금지 guard
- live discovery smoke 절차 정리
- 소액 limit order supervised validation checklist 정리
- README / docs safety 경계 갱신
- 후속 FX submit / cancel-order task 입력 자료 정리

## 제외 범위

- 반복 자동화된 실주문 테스트
- FX submit 구현
- cancel-order 구현

## 체크리스트

- [x] P4-01: automated submit 금지 guard 정리
- [x] P4-02: live discovery smoke 절차 문서화
- [x] P4-03: supervised 소액 limit order validation checklist 정리
- [x] P4-04: README / docs safety 경계 반영
- [x] P4-05: 후속 task 입력 자료 정리

## 검증 기준

- pytest 경로로 실제 주문이 발생하지 않는다.
- 실주문 검증은 사람이 읽고 따라갈 수 있는 checklist로 분리된다.
- 후속 task가 submit/cancel/FX 방향으로 이어질 수 있는 입력 자료가 남는다.

## 리스크

- 문서가 실제 구현 상태보다 낙관적으로 쓸릴 수 있다.
- supervised live validation 과정에서 실행 실수가 날 수 있다.

## 완화 방안

- 완료 기준, 금지사항, 절대 실행 금지 경로를 문서에 분리한다.
- 실제 live validation은 마지막에만 수행하고, 조건을 엄격히 제한한다.

## 완료 조건

- P4-01~P4-05 완료
- task_plan과 tasks/index 상태 갱신
