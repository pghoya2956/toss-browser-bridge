# Phase 3: Verify and Recovery

## 목표

`verify-order`와 bounded verify window를 구현해 `submitted`/`unknown` 상태를 복구 가능하게 만든다.

## 범위

- CLI `verify-order`
- daemon `verify_order`
- bounded verify window
- `completed_orders` / `positions` / `account_summary` aggregator
- daemon restart 후 journal 기반 recovery

## 제외 범위

- cancel/replace 구현
- FX submit verify

## 체크리스트

- [x] P3-01: `cli.py`에 `verify-order` 추가
- [x] P3-02: daemon `verify_order` wiring 추가
- [x] P3-03: verify aggregator 구현
- [x] P3-04: bounded verify window와 `submitted`/`unknown` 분기 구현
- [x] P3-05: daemon restart 뒤 journal 기반 recovery 구현

## 검증 기준

- `place-order`가 verify window 안에 결론이 안 나면 무한 대기하지 않는다.
- `verify-order`가 `mutation_id` 기준으로 recovery를 시도할 수 있다.
- verify 결과가 `verified_success` / `verified_failed` / `unknown`으로 일관되게 정리된다.

## 리스크

- verify 신호가 늦게 도달하거나 부분적으로만 관측될 수 있다.
- recovery가 false positive를 낼 수 있다.

## 완화 방안

- 단일 신호가 아니라 다중 read signal을 조합한다.
- 확정 근거가 부족하면 보수적으로 `unknown`을 유지한다.

## 완료 조건

- P3-01~P3-05 완료
- verify/recovery 통합 테스트 통과
- supervised validation에 필요한 recovery 절차가 문서화됨
