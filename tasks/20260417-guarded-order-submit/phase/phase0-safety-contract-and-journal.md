# Phase 0: Safety Contract and Journal

## 목표

실제 submit을 열기 전에 command contract, preview receipt, confirm phrase, mutation journal 경계를 먼저 고정한다.

## 범위

- `place-order` / `verify-order` command contract 확정
- preview receipt schema 확정
- confirm phrase canonicalization 규칙 확정
- submit state/error taxonomy 확정
- mutation journal 최소 schema 및 scrub 규칙 확정
- `order_submit_ready` / `post_submit_verify_ready` semantics 확정

## 제외 범위

- 실제 주문 submit path 구현
- 실제 verify aggregator 구현
- 수동 live submit 수행

## 체크리스트

- [ ] P0-01: `place-order` / `verify-order` command contract 확정
- [ ] P0-02: preview receipt schema 확정
- [ ] P0-03: confirm phrase canonicalization 규칙 확정
- [ ] P0-04: submit state/error taxonomy 확정
- [ ] P0-05: mutation journal 허용/금지 필드와 저장 형식 확정
- [ ] P0-06: `order_submit_ready` / `post_submit_verify_ready` semantics 확정

## 검증 기준

- fingerprint 단독 submit이 금지되고 preview receipt 기반 검증 경로가 명확하다.
- confirm phrase가 locale-independent하고 deterministic하다.
- mutation journal이 어떤 민감값도 저장하지 않는다는 규칙이 테스트 가능한 수준으로 정의된다.

## 리스크

- contract가 느슨하면 이후 submit path 구현이 위험한 기본값으로 굳어진다.
- journal 범위를 과하게 넓히면 보안 부담이 커진다.

## 완화 방안

- preview phase에서 이미 확정한 fingerprint 규칙을 그대로 재사용한다.
- journal은 recovery에 필요한 최소 필드만 허용하고 raw payload/headers는 금지한다.

## 완료 조건

- P0-01~P0-06 완료
- spec의 열린 질문 중 implementation-independent 부분이 해소됨
- contract 관련 단위 테스트 항목이 정의됨
