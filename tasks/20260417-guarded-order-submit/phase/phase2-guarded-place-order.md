# Phase 2: Guarded Place-Order

## 목표

`place-order`를 preview receipt, confirm phrase, request-time recheck, duplicate-prevention, mutation journal과 함께 구현한다.

## 범위

- CLI `place-order`
- daemon `place_order`
- preview receipt validation
- confirm phrase generation/verification
- request-time recheck
- single in-flight mutation gate
- duplicate-prevention
- submit path 구현
- sanitized broker ack summary
- mutation journal append

## 제외 범위

- `verify-order`
- daemon restart recovery
- 실제 supervised live submit

## 체크리스트

- [x] P2-01: `cli.py`에 `place-order` 추가
- [x] P2-02: `daemon.py execute()`에 `place_order` 추가
- [x] P2-03: preview receipt validation과 confirm phrase 검증 구현
- [x] P2-04: request-time recheck 구현
- [x] P2-05: single in-flight gate와 duplicate-prevention 구현
- [x] P2-06: `prepare` preflight 및 sanitized broker ack summary 구현
- [x] P2-07: mutation journal append 구현

## 검증 기준

- preview receipt mismatch는 hard-block 된다.
- confirm phrase가 틀리면 submit에 진입하지 않는다.
- duplicate-prevention이 같은 receipt/fingerprint 재사용을 막는다.
- request-time recheck가 fresh preview drift를 hard-block 한다.
- `prepare` preflight가 실제 세션에서 200으로 응답하고, 최종 `create` 전에는 `capability_not_ready`로 멈춘다.

## 리스크

- submit path 구현 중 실제 주문이 발생할 수 있다.
- journal이 민감정보를 저장할 위험이 있다.

## 완화 방안

- dry-run 불가능 시 구현 우선순위는 guard rails부터 두고 submit path는 가장 마지막에 연결한다.
- journal sanitization 테스트를 먼저 둔다.

## 완료 조건

- P2-01~P2-07 완료
- daemon/CLI submit contract 테스트 통과
- 실제 돈이 움직이지 않는 수준의 guarded flow smoke test 완료
