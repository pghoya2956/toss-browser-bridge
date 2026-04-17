# Phase 3: Preview Quality and Handoff

## 목표

preview layer의 품질 기준과 후속 submit task 연결 지점을 마무리한다.

## 범위

- fingerprint 안정성 테스트
- privacy scrub 규칙 적용
- preview 관련 문서 업데이트
- submit/cancel 후속 task로 넘길 입력 자료 정리

## 제외 범위

- 실제 submit/cancel 구현
- release/tag 생성

## 체크리스트

- [ ] P3-01: fingerprint 안정성 및 canonicalization 테스트 추가
- [ ] P3-02: preview diagnostics scrub 규칙 적용
- [ ] P3-03: logged-in / logged-out 통합 검증 기록 정리
- [ ] P3-04: README 또는 docs에 preview layer 사용법 반영
- [ ] P3-05: submit/cancel 후속 task 입력 자료 정리

## 검증 기준

- scrub-check가 preview 관련 문서/예시까지 포함해 통과한다.
- preview 구현 경계와 후속 submit 경계가 문서로 분리된다.
- 후속 task가 `spec/final.md`와 Phase 산출물만 읽고 이어질 수 있다.

## 리스크

- preview 구현 후 문서/테스트가 실제 동작을 따라오지 못할 수 있다.
- submit phase 설계 전 임시 필드가 공개 인터페이스로 굳어질 수 있다.

## 완화 방안

- 공개 인터페이스와 internal-only 필드를 문서에 구분한다.
- closeout 전에 README/docs/task_plan을 함께 정리한다.

## 완료 조건

- P3-01~P3-05 완료
- task_plan과 tasks/index 상태 갱신
