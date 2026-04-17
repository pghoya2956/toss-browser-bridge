# Write Path Opinion

## 요약

`toss-browser-bridge`에 쓰기 기능을 넣는 건 가능하다. 다만 `read-only bridge`에 명령 몇 개를 더 붙이는 정도로 생각하면 실패한다.

내 판단은 이렇다.

- write는 구현 가능
- 하지만 `직접 주문 실행`보다 `preview → explicit confirm → post-check verify`를 강제하는 구조가 먼저다
- 첫 write scope는 `place-order`보다 `order-preview`와 `fx-preview`가 맞다

즉, 다음 단계의 목표는 `바로 주문하는 CLI`가 아니라 **실수 비용이 큰 mutation을 안전하게 다루는 브라우저 부착형 실행기**다.

## 왜 read-only에서 멈췄는가

현재 read-only는 브라우저 컨텍스트 안에서 `fetch`를 수행하고, capability matrix로 readiness를 노출한다.

이 모델이 read에는 잘 맞는 이유:

- 읽기는 중복 실행돼도 금전 피해가 없다
- 실패해도 재조회하면 된다
- endpoint family별 skew를 진단으로 노출하면 충분하다

반대로 write는 다르다.

- 중복 실행 자체가 손실이 될 수 있다
- partial success가 생긴다
- 브라우저 UI 확인창, 시장 상태, 계좌 상태가 끼어든다
- 성공 여부를 응답 하나로 믿으면 안 된다

그래서 read path의 성공 패턴을 write path에 그대로 확장하면 안 된다.

## 권장 아키텍처

### 원칙

- browser-attached 유지
- daemon이 전용 Chrome 프로필을 소유
- mutation은 브라우저 컨텍스트 안에서만 수행
- 모든 mutation은 verify 단계가 끝나기 전까지 완료로 간주하지 않음

### 실행 모델

권장 흐름:

```text
input
→ preview
→ user confirm
→ submit
→ broker/web acknowledgement
→ post-submit requery
→ verified result
```

핵심은 `submit 응답`이 아니라 `post-submit requery`가 최종 진실이라는 점이다.

## 첫 구현 범위

### v0.2: preview layer

먼저 넣어야 할 것:

- `order-preview`
- `fx-preview`

여기서 해야 할 일:

- 입력 검증
- 주문 가능 금액 검증
- 시장/통화/계좌 상태 사전 점검
- 예상 payload 구성
- 위험 경고 노출

이 단계는 실제 돈을 움직이지 않으면서 write path의 복잡도를 대부분 드러낸다.

### v0.3: guarded submit

preview가 안정화된 뒤에만:

- `place-order`
- `fx-exchange`

조건:

- `--confirm` 없으면 실행 금지
- preview fingerprint와 submit payload가 일치해야 함
- submit 후 `completed-orders`, `account-summary`, `positions` 재조회로 검증

### v0.4: order management

그 다음:

- `cancel-order`
- 필요 시 `replace-order`

이건 open order 상태와 타이밍 이슈가 더 심하므로 마지막에 넣는 게 맞다.

## 구현 우선순위

### 우선순위 1

- preview command contract
- mutation capability matrix 설계
- idempotency key 설계

### 우선순위 2

- order submit POC
- fx submit POC
- submit 후 검증기

### 우선순위 3

- cancel-order
- richer diagnostics
- error taxonomy 정리

## capability matrix 확장안

현재 health는 read surface readiness를 보여준다.

write를 넣는다면 아래 capability를 추가하는 게 자연스럽다.

- `order_preview_ready`
- `order_submit_ready`
- `fx_preview_ready`
- `fx_submit_ready`
- `cancel_order_ready`
- `post_submit_verify_ready`

중요한 점:

`browser_attached = true`가 mutation readiness를 의미하면 안 된다.

예를 들어:

- quote는 가능
- positions는 가능
- submit은 불가

같은 상태를 분리해서 보여줄 수 있어야 한다.

## 가장 현실적인 구현 방식

write 구현 방식은 셋으로 나뉜다.

### UI automation

장점:

- 웹이 요구하는 모든 문맥을 그대로 탐

단점:

- DOM 변경에 취약
- 유지보수 비용 큼

### in-page mutation fetch

장점:

- read path와 구조가 유사
- 코드가 더 깔끔함

단점:

- 실제 submit endpoint의 인증/검증 요구사항이 더 빡셀 수 있음

### hybrid

추천 방식이다.

- preview는 fetch 기반
- 실제 마지막 제출은 브라우저 UI 또는 명시적 confirm을 요구
- 제출 후 검증은 다시 fetch 기반

내 판단:

첫 write는 **hybrid**가 가장 현실적이다.

## 반드시 필요한 안전장치

- 모든 mutation에 dry-run 또는 preview 선행
- `--confirm` 같은 explicit ack 필요
- preview fingerprint와 submit payload 일치 여부 확인
- 실행 전 계좌 상태 재조회
- 실행 후 계좌 상태 재조회
- 같은 요청 재실행 방지용 idempotency key
- 실패 시 `submitted / unknown / verified_failed / verified_success` 상태 구분

## 금지할 것

초기 버전에서 아래는 금지하는 게 맞다.

- market order 기본값
- all-in / max order 단축 명령
- preview 없이 submit
- submit 응답만 보고 성공 처리
- auto retry

write에서 자동 재시도는 특히 위험하다. 네트워크 타임아웃 직후 실제 주문이 들어갔는지 모르는 상태에서 retry하면 중복 주문이 된다.

## 추천 데이터 모델

write를 넣는다면 이벤트 로그를 별도 두는 게 좋다.

예:

```text
mutation_id
kind
requested_at
preview_payload_hash
submit_status
submit_ack
verification_status
verification_snapshot
```

중요한 건 "요청"과 "검증 완료"를 같은 사건으로 뭉개지 않는 것이다.

## 구체적인 다음 액션

가장 좋은 다음 작업은 이것이다.

- `docs/write-path-spec.md`를 별도 생성
- `order-preview`와 `fx-preview`만 feature-spec화
- `place-order`는 그 다음 phase로 분리

이유:

- preview에서 대부분의 위험이 먼저 드러난다
- submit까지 한 번에 가면 scope가 급격히 커진다
- 공개 OSS 기준으로도 preview는 설명하기 쉽고 리뷰받기 좋다

## 최종 의견

write는 충분히 구현 가능하다. 다만 `read-only의 연장선`으로 보면 안 된다.

이 프로젝트의 다음 성공은 `주문 실행 지원` 자체가 아니라, **실행 전/후 검증이 강제된 안전한 mutation framework**를 먼저 세우는 것이다.

한 줄로 요약하면:

**다음 단계는 `place-order`가 아니라 `preview-first mutation architecture`다.**
