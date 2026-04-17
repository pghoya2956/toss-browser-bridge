# 스펙 검토 로그

## 검토 대상

- 파일: [tasks/20260417-write-path-preview/spec/initial.md](/Users/heeho/para/Area/pghoya2956/toss-browser-bridge/tasks/20260417-write-path-preview/spec/initial.md)
- 검토일: 2026-04-17 KST

## 발견 사항

### 기술적 구현

| 항목 | 상태 | 발견 내용 | 보완 내용 |
|------|------|----------|----------|
| order preview 입력 계약 | ◐ 모호 | 초안은 `order_type` 예시를 제시하지만 현재 코드 helper는 기본값을 `market`으로 둔다. 이는 `market order 기본값 금지` 원칙과 충돌한다. | `final.md`에서 `order_type`을 필수 필드로 고정하고, CLI도 `--order-type`을 명시적으로 요구하도록 보완했다. |
| preview 오류 계약 | ○ 누락 | 현재 daemon은 도메인 예외를 구분하지 않으면 `runtime_error` 500으로 떨어진다. 스펙에는 `invalid_request`를 어떻게 transport 레벨에 매핑할지 없었다. | `final.md`에 preview domain error는 기존 read path와 동일하게 JSON body 중심으로 반환하고, 잘못된 `/bridge/query` envelope만 400, 예기치 않은 예외만 500으로 남기도록 명시했다. |
| readiness semantics | ◐ 모호 | `order_preview_ready`와 `fx_preview_ready`의 기준이 추상적이라 health capability와 실제 command 동작이 어긋날 수 있다. | `final.md`에 `order_preview_ready`는 `logged-in + account_summary_ready + quote_ready`로 고정하고, sell preview는 요청 시점에 positions 재확인으로 보완하도록 명시했다. `fx_preview_ready`는 FX endpoint family 확인 전까지 보수적으로 취급하도록 정리했다. |
| fingerprint 정의 | ◐ 모호 | `preview_fingerprint`가 어떤 필드를 포함해야 하는지 없어서 구현마다 호환성이 깨질 수 있다. | `final.md`에 canonical JSON + SHA-256 규칙을 추가하고, `checked_at`, `warnings`, `diagnostics` 같은 휘발성 필드는 제외하도록 보완했다. |
| preview 결과 보관 범위 | ○ 누락 | `preview_id`와 fingerprint를 도입했지만 메모리 유지인지 런타임 홈 저장인지 정해져 있지 않았다. | `final.md`에 preview phase에서는 디스크 영속화를 금지하고, `preview_id`는 프로세스 로컬 디버깅 용도, submit phase 연계 키는 `preview_fingerprint`로 한정하도록 보완했다. |
| 모듈 경계 | ◐ 모호 | `daemon.py`가 이미 큰데 preview 로직까지 추가하면 유지보수성이 급격히 나빠질 수 있다. | `final.md`에 `preview.py` 계열 helper 분리 원칙을 추가하고, `bridge_lib.py`에는 도메인 로직을 두지 않도록 고정했다. |
| FX preview 선행 조건 | ◐ 모호 | FX endpoint family가 아직 확인되지 않았는데 구현 계획이 order preview와 동일한 확실도로 적혀 있었다. | `final.md`에 FX endpoint discovery spike를 별도 단계로 추가하고, 확인 전까지 `fx_preview_ready`를 과도하게 true로 노출하지 않도록 보완했다. |
| blocking issue 의미 | ◐ 모호 | `blocking_issues`가 있으면 preview가 실패인지, 성공이지만 submit 불가인지가 구분되지 않았다. | `final.md`에 `preview_state`를 추가해 `preview_ready`와 `blocked`를 구분하고, preview 계산 성공 자체와 submit 가능 여부를 분리했다. |

### 보안, 개인정보 보호

| 항목 | 상태 | 발견 내용 | 보완 내용 |
|------|------|----------|----------|
| 계좌/토큰 노출 방지 | ◐ 모호 | preview와 diagnostics에 어떤 민감값을 마스킹할지 구체 규칙이 없었다. | `final.md`에 raw `accountNo`, bearer token, XSRF, App-Version, 브라우저 식별 헤더는 응답과 캐시에 저장하지 않도록 추가했다. |
| 런타임 아티팩트 | ◐ 모호 | preview 결과를 `TOSS_BRIDGE_HOME`에 남기면 이후 submit phase와 섞이며 보안/정합성 문제가 생길 수 있다. | preview phase에서는 기존 token/pid/log 외 새 런타임 파일을 만들지 않도록 명시했다. |

### 트레이드오프

| 항목 | 상태 | 발견 내용 | 보완 내용 |
|------|------|----------|----------|
| order vs fx 동시 추진 | ◐ 모호 | 둘을 같은 확실도로 추진하면 FX endpoint 불확실성이 전체 일정의 병목이 된다. | `final.md`에서 order preview를 우선 구현 대상으로 고정하고, FX는 discovery 결과에 따라 이어붙이도록 phase를 조정했다. |
| health capability 보수성 | ◐ 모호 | capability를 낙관적으로 열면 실제 preview command 실패와 health 표시가 어긋난다. | capability는 보수적으로 계산하고, 불확실한 의존성은 요청 시점 `capability_not_ready`로 환원하도록 정리했다. |

### 엣지 케이스

| 항목 | 상태 | 발견 내용 | 보완 내용 |
|------|------|----------|----------|
| sell preview 의존성 | ○ 누락 | sell preview는 positions가 필수일 수 있는데 health 기준에 포함될지 불분명했다. | health는 base readiness만 표현하고, sell preview 실행 시 positions 재조회 실패를 `capability_not_ready` 또는 `blocked`로 처리하도록 보완했다. |
| stale preview | ○ 누락 | preview 시점과 submit 시점 사이의 가격/주문 가능 금액 변화가 반영될 위치가 없었다. | `verification_plan` 외에 `preview_state`, fingerprint 입력 집합, future submit 재조회 요구를 명시해 stale preview를 future submit phase에서 강제 검증하도록 연결했다. |
| 동시성 | ○ 누락 | browser context가 공유되는데 preview 다중 호출 정책이 적혀 있지 않았다. | 현재 runtime lock 기반 직렬 실행을 유지하는 것으로 정리하고, preview phase에서는 side effect가 없으므로 직렬화 비용을 허용한다고 명시했다. |

## 열린 질문 (해결 불가)

- FX preview용 실제 환율/수수료 endpoint family가 무엇인지: 현재 코드베이스와 문서만으로는 확인되지 않았다.
- future submit에서 `preview_id`를 입력받을지, `preview_fingerprint`만 사용할지: preview phase에서 확정할 수 없고 submit UX 설계가 필요하다.
- `post_submit_verify_ready`를 health에 언제 노출할지: submit spec 범위의 readiness 정의가 선행돼야 한다.

## 요약

- 발견된 모호함: 13건
- 보완된 항목: 13건
- 열린 질문: 3건
