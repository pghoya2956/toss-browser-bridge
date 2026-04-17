# Phase 1: Submit Path Discovery

## 목표

실제 limit order submit path가 fetch 기반으로 가능한지, 언제 UI fallback이 필요한지 실측으로 확인한다.

## 범위

- 국내/미국 limit order submit path 후보 조사
- submit request payload 및 필수 header/context 관찰
- broker ack / reject / cancel / timeout 시그널 수집
- verify 신호 도달 시간 관찰
- fetch 유지 조건과 UI fallback 전환 기준 문서화

## 제외 범위

- 실제 주문을 반복 자동화하는 스크립트
- market order submit 조사
- cancel/replace 조사

## 체크리스트

- [ ] P1-01: 국내 limit order path 후보 조사
- [ ] P1-02: 미국 limit order path 후보 조사
- [ ] P1-03: submit payload와 필수 context 조건 확인
- [ ] P1-04: ack/reject/cancel/timeout 구분 시그널 수집
- [ ] P1-05: verify 관측 창과 fallback 기준 문서화

## 검증 기준

- fetch 기반 submit 가능 여부를 [확인] 또는 [추정]으로 구분할 수 있다.
- UI fallback이 필요한 조건이 구현 가능한 수준으로 정리된다.
- verify window와 후속 recovery 필요성이 실측 데이터로 뒷받침된다.

## 리스크

- 실제 submit path가 모호해 discovery 자체가 high risk일 수 있다.
- 잘못된 실험은 실제 주문으로 이어질 수 있다.

## 완화 방안

- 초기 discovery는 실제 submit 대신 network/context observation 위주로 진행한다.
- 실제 주문이 필요한 확인은 가장 마지막 supervised checklist로 밀어둔다.

## 완료 조건

- P1-01~P1-05 완료
- fetch path 유지 조건과 UI fallback 전환 기준이 문서화됨
- Phase 2 구현 범위가 limit order 기준으로 고정됨
