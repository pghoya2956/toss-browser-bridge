# Final Submit Handoff

## 현재까지 닫힌 위험

- preview receipt 기반 동일성 검증
- canonical confirm phrase 강제
- request-time preview recheck
- duplicate-prevention
- `prepare` preflight
- mutation journal append
- `verify-order` recovery
- bounded verify window
- pytest 내부 final submit unlock 차단

## 아직 남은 구현 입력

- final `create` 성공 응답 shape
- final `create` reject 응답 shape
- UI confirm fallback이 필수인지 여부
- `submitted`와 `unknown`을 나누는 최종 broker ack 기준
- supervised live submit에서 verify convergence가 몇 초 안에 수렴하는지 실측값

## 다음 task에서 바로 확인할 것

- `TOSS_BRIDGE_ENABLE_FINAL_SUBMIT` unlock을 실제 submit worker 경로에 어떻게 연결할지
- `create` 이전 UI confirm 단계와 fetch 호출의 경계
- 국내/미국 limit order에서 공통 helper로 묶을 수 있는 필드와 분기 필드
- `verify-order`를 final submit 직후 inline wait와 후속 recovery 두 경로에서 어떻게 재사용할지

## 권장 성공 조건

- automated test 경로에서는 여전히 실주문이 절대 발생하지 않는다.
- final submit unlock은 supervised 세션에서만 명시적으로 켠다.
- `place-order` 성공은 broker ack 단독이 아니라 verify 결과까지 포함해 판단한다.
- ambiguous 결과는 `unknown`으로 남기고 auto retry는 하지 않는다.
