# Phase 1: Order Preview

## 목표

`order-preview`를 실제 계좌/시세/주문 가능 금액 기반 preview 명령으로 구현한다.

## 범위

- `order-preview` CLI/daemon wiring
- order preview 사전 조회 endpoint 세트 정의
- preview builder, warnings, blocking_issues, preview_state 구현
- buy/sell request-time capability check 구현
- order preview 통합 테스트 작성

## 제외 범위

- 실제 order submit
- preview 결과 영속화
- UI confirm

## 체크리스트

- [ ] P1-01: `cli.py`에 `order-preview` 서브커맨드 추가
- [ ] P1-02: `daemon.py execute()`에 `order_preview` 추가
- [ ] P1-03: order preview endpoint 상수와 fetch flow 구현
- [ ] P1-04: `submit_candidate` / `derived` / `preview_state` builder 구현
- [ ] P1-05: sell preview의 positions 재확인 분기 구현
- [ ] P1-06: logged-out / invalid-request / partial dependency failure 테스트 추가

## 검증 기준

- logged-in 상태에서 preview JSON이 일관되게 반환된다.
- logged-out 상태에서 `logged_out` error가 나온다.
- sell preview는 positions 실패 시 `blocked` 또는 `capability_not_ready`로 떨어진다.

## 리스크

- Toss 웹 endpoint family 응답 구조 변경
- 종목 검색 성공 후 가격/메타데이터 family mismatch

## 완화 방안

- endpoint_matrix를 diagnostics에 모두 남긴다.
- request builder와 response builder를 분리해 응답 구조 변화 영향 범위를 줄인다.

## 완료 조건

- P1-01~P1-06 완료
- logged-in 로컬 E2E로 `order-preview` 실제 응답 검증
