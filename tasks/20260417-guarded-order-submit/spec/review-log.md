# 스펙 검토 로그

## 검토 대상

- 파일: [tasks/20260417-guarded-order-submit/spec/initial.md](/Users/heeho/para/Area/pghoya2956/toss-browser-bridge/tasks/20260417-guarded-order-submit/spec/initial.md)
- 검토일: 2026-04-17 KST

## 발견 사항

### 기술적 구현

| 항목 | 상태 | 발견 내용 | 보완 내용 |
|------|------|----------|----------|
| submit 입력 계약 | ◐ 모호 | `preview_fingerprint`는 해시일 뿐이라, daemon이 submit 시점에 무엇과 비교해야 하는지 불명확하다. fingerprint만으로는 preview 내용을 복원할 수 없다. | `final.md`에 [보완] `preview_receipt` 개념을 추가했다. 초기 submit은 `preview_fingerprint` 단독이 아니라, fingerprint + canonical preview subset을 담은 receipt 또는 동일 세션 내 preview registry reference를 요구하도록 정리했다. |
| 실제 주문 범위 | ◐ 모호 | 초안은 buy/sell 전부를 다루면서도 order type rollout 경계가 없다. 실제 돈이 움직이는 첫 submit phase에서 market order까지 바로 여는 것은 과도하다. | `final.md`에 [보완] 초기 실제 submit 범위를 `limit order`로만 제한하고, market order는 preview-only로 남기도록 조정했다. 시장 rollout도 단계적으로 열도록 보완했다. |
| verify 복구 경로 | ○ 누락 | `unknown` 상태를 정의했지만 이를 사용자가 어떻게 복구/확인할지 명령 계약이 없다. | `final.md`에 [보완] `verify-order` companion command를 In Scope에 추가하고, `place-order`와 분리된 recovery path를 명시했다. |
| 상태 기록 정책 | ○ 누락 | submit 이후 daemon이 재시작되거나 CLI가 종료되면 `unknown`/`submitted` 상태를 추적할 최소 저장 지점이 없다. | `final.md`에 [보완] submit phase에서는 sanitized append-only mutation journal을 최소 범위로 도입하도록 추가했다. raw token/accountNo는 금지하고 mutation metadata만 남기도록 정리했다. |
| readiness semantics | ◐ 모호 | `order_submit_ready`가 preview readiness와 어떻게 구분되는지 충분히 엄격하지 않다. verify path가 미준비여도 submit readiness가 true가 될 여지가 있다. | `final.md`에 [보완] `order_submit_ready`는 `order_preview_ready + submit path discovery + verify path 준비 + mutation journal writable`일 때만 true가 되도록 보수적으로 정의했다. |
| confirm UX | ◐ 모호 | `--confirm`과 `confirm-text`를 언급하지만 어떤 문자열을 누가 생성하는지, 대소문자/공백 규칙이 무엇인지 없다. | `final.md`에 [보완] daemon이 canonical confirm phrase를 생성하고, CLI는 그 문자열을 그대로 재입력받는 규칙으로 고정했다. |
| submit 오류 분류 | ◐ 모호 | `submit_failed` 하나로는 broker reject, user cancel, timeout unknown이 섞인다. | `final.md`에 [보완] `submit_cancelled`, `broker_rejected`, `submit_unknown`, `verification_failed`를 분리하고, `runtime_error`는 예외 상황으로만 남겼다. |
| 동시성 제어 | ○ 누락 | 같은 browser context에서 submit 두 건이 동시에 들어오면 confirm UI와 verify 신호가 뒤엉킬 수 있다. | `final.md`에 [보완] 초기 submit phase는 daemon당 단일 in-flight mutation만 허용하도록 명시했다. |

### 보안, 개인정보 보호

| 항목 | 상태 | 발견 내용 | 보완 내용 |
|------|------|----------|----------|
| submit 로그 민감도 | ◐ 모호 | preview phase에서는 민감정보 금지 규칙이 있지만, submit phase의 journal에는 어떤 필드가 허용되는지 없다. | `final.md`에 [보완] journal 허용 필드를 제한하고, raw request body, bearer token, XSRF, accountNo, browser headers는 금지하도록 추가했다. |
| 실제 주문 테스트 경계 | ○ 누락 | live E2E 계획이 있지만, pytest에서 실제 주문이 실행되지 않도록 하는 운영 경계가 없다. | `final.md`에 [보완] 자동 test에서는 실제 submit 금지, 실제 submit 검증은 수동 supervised checklist로만 수행하도록 분리했다. |

### 트레이드오프

| 항목 | 상태 | 발견 내용 | 보완 내용 |
|------|------|----------|----------|
| submit 방식 선택 | ◐ 모호 | hybrid 방향은 맞지만, 언제 fetch를 포기하고 UI fallback으로 전환할지 경계가 없다. | `final.md`에 [보완] discovery phase에서 fetch path를 우선 검증하되, confirm UI를 우회할 수 없거나 응답 의미가 모호하면 UI fallback으로 전환하는 기준을 추가했다. |
| verify 대기 시간 | ◐ 모호 | `place-order`가 verify를 얼마나 기다릴지 없으면 CLI가 과도하게 오래 멈추거나, 반대로 너무 빨리 `unknown`을 반환할 수 있다. | `final.md`에 [보완] `place-order`는 bounded verify window만 수행하고, 미확정 상태는 `submitted`/`unknown`으로 반환한 뒤 `verify-order`로 이어지도록 정리했다. |

### 엣지 케이스

| 항목 | 상태 | 발견 내용 | 보완 내용 |
|------|------|----------|----------|
| stale preview | ◐ 모호 | request-time 재검증 항목은 나와 있지만 mismatch가 어떤 수준에서 hard-block인지 없다. | `final.md`에 [보완] cash/quantity/product_code/order_type/limit_price mismatch는 hard-block으로, 일부 보조 필드 변화는 warning으로 두는 원칙을 추가했다. |
| user cancel | ○ 누락 | submit 도중 사용자가 confirm UI를 닫거나 취소하는 경우가 정의되지 않았다. | `final.md`에 [보완] `submit_cancelled`를 별도 상태/오류로 정의했다. |
| daemon restart 후 recovery | ○ 누락 | daemon 재기동 뒤에도 `unknown` 주문을 추적해야 하는지 명확하지 않다. | minimal journal을 통해 `verify-order --mutation-id` 복구 경로를 지원하도록 보완했다. |

## 열린 질문 (해결 불가)

- 실제 주문 submit이 최종적으로 fetch 기반으로 가능한지, 아니면 마지막 단계에서 UI confirm이 강제되는지: discovery 없이는 확정할 수 없다.
- 국내/미국 주문 submit endpoint family가 동일한지, 시장별로 완전히 분기되는지: 실측 전까지는 [추정]으로만 둘 수 있다.
- bounded verify window의 기본 시간값을 얼마로 둘지: 구현 전 smoke observation이 더 필요하다.

## 요약

- 발견된 모호함: 14건
- 보완된 항목: 14건
- 열린 질문: 3건
