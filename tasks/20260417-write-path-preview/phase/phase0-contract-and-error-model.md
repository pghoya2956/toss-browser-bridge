# Phase 0: Contract and Error Model

## 목표

preview command의 외부 계약과 내부 error/readiness 규칙을 먼저 고정한다.

## 범위

- `order-preview` / `fx-preview` CLI 인자 스키마 확정
- preview domain error와 generic runtime error 분리
- health capability readiness semantics 구현
- preview fingerprint 입력 집합 및 canonicalization 규칙 구현

## 제외 범위

- 실제 order preview 계산 로직
- 실제 FX preview 계산 로직
- 문서 외 대규모 refactor

## 체크리스트

- [ ] P0-01: `cli.py`에 preview command 파라미터 스키마 반영
- [ ] P0-02: preview domain error 타입과 handler 분기 추가
- [ ] P0-03: `classify_health_payload()`에 preview readiness semantics 반영
- [ ] P0-04: fingerprint helper와 canonical payload 규칙 추가
- [ ] P0-05: contract/error/readiness 단위 테스트 추가

## 검증 기준

- 잘못된 preview 요청은 `runtime_error`가 아니라 domain error로 떨어진다.
- `health` capability가 스펙의 preview readiness 기준과 일치한다.
- 같은 정규화 입력은 같은 fingerprint를 생성한다.

## 리스크

- 기존 read path 에러 규칙을 건드리며 회귀가 생길 수 있다.
- capability semantics를 과하게 낙관적으로 열면 실제 command failure와 health 표시가 어긋난다.

## 완화 방안

- preview error 분기는 새 helper 경로로 분리하고 기존 read kind 로직은 유지한다.
- readiness 판정은 보수적으로 구현하고 request-time check를 추가한다.

## 완료 조건

- P0-01~P0-05 완료
- `pytest`, `py_compile`, `scrub-check.sh` 통과
