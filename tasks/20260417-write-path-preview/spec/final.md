# Write Path Preview-First Mutation Architecture 스펙

## 개요

`toss-browser-bridge`의 다음 단계로 `order-preview`와 `fx-preview`를 먼저 도입해, 실제 submit 이전의 검증, 위험 노출, 후속 write path 확장을 위한 기반을 만든다.

## 목적

현재 bridge는 browser-attached read-only daemon/CLI로 동작하며, `health`, `account-summary`, `positions`, `completed-orders`, `quote`만 지원한다. 현재 코드베이스와 [docs/write-path-opinion.md](../../../docs/write-path-opinion.md)의 공통 결론은, write path를 read path의 단순 확장으로 다루면 안 되고 `preview → explicit confirm → submit → post-submit verify` 구조를 강제해야 한다는 점이다.

이 스펙의 목적은 다음과 같다.

- 실제 돈이 움직이지 않는 범위에서 write path의 복잡도를 먼저 surface화한다.
- `order-preview`, `fx-preview`의 command contract와 daemon 내부 구조를 정의한다.
- mutation readiness를 read readiness와 분리해 capability matrix에서 표현한다.
- 이후 `place-order`, `fx-exchange`, `cancel-order`를 별도 phase로 진행할 수 있도록 preview-first 기반을 마련한다.

성공 기준은 다음과 같다.

- CLI와 daemon에 `order-preview`, `fx-preview` 계약이 명확히 정의된다.
- preview 결과가 단순 echo가 아니라 입력 검증, 브로커 상태 조회, 예상 submit payload, 위험 경고를 포함한다.
- health payload가 preview readiness와 submit readiness를 분리해 표현한다.
- preview 구현만으로도 후속 submit phase가 재설계 없이 이어질 수 있을 만큼 데이터 모델과 상태 전이가 정리된다.
- [보완] preview domain error가 `runtime_error`와 분리되고, capability와 request-time failure가 일관된 규칙으로 반환된다.

## 범위

### In Scope

- `order-preview` 명령 계약 정의
- `fx-preview` 명령 계약 정의
- preview 요청 입력 검증 규칙 정리
- preview 단계에서 필요한 사전 조회 항목 정의
- preview 응답 데이터 모델 정의
- preview fingerprint / idempotency seed 설계 초안
- capability matrix 확장과 readiness 판정 기준 정의
- daemon/CLI/bridge_lib 기준의 구현 분할 계획 수립
- 테스트 전략 수립

### Out of Scope

- `place-order` 실제 주문 제출
- `fx-exchange` 실제 환전 제출
- `cancel-order` 실제 취소 제출
- UI automation 기반 최종 confirm 구현
- 실제 submit endpoint reverse engineering 완료
- 이벤트 로그 저장소의 최종 영속화 방식 확정
- `financier-v2` 반영 작업
- [보완] preview phase에서 디스크 영속 preview cache 도입

## 요구사항

### 사용자

- 토스증권 웹에 로그인된 전용 Chrome 프로필을 사용하는 로컬 사용자
- CLI를 통해 브라우저 부착형 bridge를 호출하는 사용자
- 실제 주문 실행 전에 입력 유효성, 주문 가능 여부, 예상 결과, 위험 경고를 확인하려는 사용자

### 기능 요구사항

- `order-preview`는 시장, 종목, 수량, 주문 방향, 주문 유형, 지정가 여부를 받아 preview를 생성해야 한다.
- `fx-preview`는 환전 방향과 단일 금액 입력을 받아 preview를 생성해야 한다.
- preview는 로그인 여부만 보지 않고 계좌 조회, 주문 가능 금액, 시세, 시장 상태 등 관련 의존성이 준비되었는지 확인해야 한다.
- preview는 후속 submit에서 payload 동일성 검증에 사용할 수 있는 fingerprint를 반환해야 한다.
- preview는 예상 submit payload를 그대로 실행하지 않더라도, 어떤 입력이 실제 submit에 반영될지 사람이 검토할 수 있을 정도로 명시해야 한다.
- preview 실패는 `invalid_request`, `logged_out`, `capability_not_ready`, `preview_failed` 등으로 분리되어야 한다.
- [보완] `order_type`은 필수다. `market` 기본값을 두지 않는다.
- [보완] `blocking_issues`가 있어도 preview 계산이 끝났다면 응답은 `ok: true`일 수 있다. 이때 submit 가능 여부는 `data.preview_state`로 표현한다.
- [보완] sell preview는 health capability가 true여도 요청 시점에 positions 재확인을 수행해야 한다.

### 비기능 요구사항

- 기존 browser-attached 모델을 유지한다.
- preview는 브라우저 컨텍스트 안에서 fetch 기반으로 수행한다.
- `browser_attached = true`를 preview readiness와 동일시하지 않는다.
- submit readiness와 preview readiness는 별도 capability로 노출한다.
- 결과 JSON은 기존 daemon 응답 형식과 일관성을 유지한다.
- [보완] preview phase에서는 기존 `TOSS_BRIDGE_HOME` 하위 token/pid/log 외 새 런타임 파일을 만들지 않는다.
- [보완] raw `accountNo`, bearer token, XSRF, App-Version, 브라우저 식별 헤더는 preview 결과, diagnostics, future cache에 저장하지 않는다.

### [보완] 응답 및 오류 계약

- `/bridge/query`의 malformed JSON, `kind` 누락 같은 envelope 오류만 HTTP 400으로 반환한다.
- preview domain error는 기존 read path와 동일하게 JSON body 중심으로 반환하며, HTTP status는 200을 유지한다.
- `invalid_request`, `logged_out`, `capability_not_ready`, `preview_failed`는 모두 preview domain error다.
- `runtime_error`는 예기치 않은 예외에만 남긴다.
- preview path에서 의존 endpoint 결과는 성공/실패와 관계없이 가능한 범위에서 `diagnostics.endpoint_matrix`에 남긴다.

## 코드베이스 맥락

### 현재 구조

- [src/toss_browser_bridge/daemon.py](../../../src/toss_browser_bridge/daemon.py)
  - daemon의 query dispatch, browser attach, in-page fetch, health/account/positions/quote 구현이 있다.
  - `validate_order_preview_params`, `validate_fx_preview_params`가 이미 존재하지만 execute path에 연결되지는 않았다.
  - `MUTATION_CAPABILITIES`에 preview/submit placeholder가 있으며 health payload에서는 현재 모두 `false`다.
- [src/toss_browser_bridge/cli.py](../../../src/toss_browser_bridge/cli.py)
  - 현재 read-only 명령만 서브커맨드로 expose한다.
  - daemon 기동과 `/bridge/query` 호출 계약의 기준점이다.
- [src/toss_browser_bridge/bridge_lib.py](../../../src/toss_browser_bridge/bridge_lib.py)
  - runtime path, port, HTTP request helper, KST timestamp를 제공한다.
  - preview 자체보다는 공통 transport와 런타임 경계의 재사용 지점이다.
- [docs/write-path-opinion.md](../../../docs/write-path-opinion.md)
  - preview-first, hybrid write path, idempotency, post-submit verify 원칙이 정리돼 있다.

### 재사용 가능한 현재 자산

- browser attach와 in-page fetch 실행기 `_fetch_many`
- read path 공통 에러 응답 형식 `_error_response`
- KST 기준 `checked_at`/diagnostics 패턴
- preview 입력 검증 helper 초안
- capability classifier와 health payload 구조

### 현재 갭

- `execute()`와 CLI에 preview 명령이 없다.
- preview에 필요한 사전 조회 endpoint 세트가 정의돼 있지 않다.
- preview fingerprint와 mutation event 상태 모델이 없다.
- preview failure taxonomy가 read path 수준으로만 정리돼 있다.
- submit phase와 연결될 contract가 아직 문서화되지 않았다.
- [보완] preview domain error를 generic 500에서 분리하는 handler 경로가 아직 없다.

## 설계

### 데이터 모델

#### Order Preview Request

```json
{
  "market": "us",
  "side": "buy",
  "symbol": "AAPL",
  "order_type": "limit",
  "quantity": 3,
  "limit_price": 201.5
}
```

제약:

- `market`: `kr` 또는 `us`
- `side`: `buy` 또는 `sell`
- `order_type`: `market` 또는 `limit`
- `quantity`: 양의 정수
- `limit_price`: `limit`일 때만 허용
- [보완] `order_type`은 필수이며 생략 시 `invalid_request`
- [보완] 한국 종목 6자리 숫자는 내부적으로 `A` prefix product code로 정규화한다

#### FX Preview Request

```json
{
  "side": "buy",
  "amount_krw": 1500000
}
```

제약:

- `side`: `buy` 또는 `sell`
- `amount_krw`와 `amount_usd` 중 정확히 하나만 허용
- 금액은 양수
- [보완] preview phase에서는 KRW/USD만 다룬다

#### Preview Response

```json
{
  "ok": true,
  "kind": "order_preview",
  "source": "toss_browser_bridge",
  "checked_at": "2026-04-17T11:30:00+09:00",
  "capability": "order_preview_ready",
  "data": {
    "preview_id": "pvw_...",
    "preview_fingerprint": "sha256:...",
    "preview_state": "preview_ready",
    "account_id": "toss:****1234",
    "market": "us",
    "warnings": [],
    "blocking_issues": [],
    "inputs": {},
    "derived": {},
    "submit_candidate": {},
    "verification_plan": {}
  },
  "diagnostics": {
    "endpoint_matrix": [],
    "last_errors": []
  }
}
```

필수 필드:

- `preview_id`: 프로세스 로컬 preview 인스턴스 식별자
- `preview_fingerprint`: 후속 submit payload 동일성 검증용 해시
- `preview_state`: `preview_ready` 또는 `blocked`
- `inputs`: 정규화된 사용자 입력
- `derived`: 사전 조회 결과를 바탕으로 계산한 값
- `submit_candidate`: 지금 시점에서 예상되는 submit payload/핵심 파라미터
- `warnings`: 실행 가능하지만 주의가 필요한 항목
- `blocking_issues`: submit 전 해결되어야 하는 항목
- `verification_plan`: submit 이후 어떤 재조회로 검증할지에 대한 계획
- [보완] `account_id`는 항상 마스킹된 값만 반환한다

#### Mutation Event 상태 모델

preview phase에서는 실제 저장을 도입하지 않아도 되지만, 응답과 추후 확장을 위해 상태 모델은 미리 고정한다.

```text
draft_preview
→ preview_ready
→ blocked
→ submitted
→ verified_success
→ verified_failed
→ unknown
```

현재 phase에서 실제로 사용하는 상태는 `draft_preview`, `preview_ready`, `blocked`까지다.

### [보완] Fingerprint 규칙

- `preview_fingerprint`는 canonical JSON 직렬화 결과의 SHA-256 해시로 계산한다.
- 입력 집합은 다음으로 고정한다.
  - `kind`
  - 정규화된 `inputs`
  - 마스킹된 `account_id`
  - `submit_candidate`
  - submit 안전성에 직접 영향을 주는 최소 `derived` 필드
- 다음 필드는 fingerprint에서 제외한다.
  - `checked_at`
  - `warnings`
  - `blocking_issues`
  - `diagnostics`
  - endpoint 응답 전체 원문
- 이유:
  - 같은 정규화 입력과 같은 submit 후보는 같은 fingerprint를 가져야 한다.
  - 사람이 읽기 위한 보조 데이터나 시각 정보는 submit 동일성 판정에 포함되면 안 된다.

### [보완] Preview 보관 정책

- preview phase에서는 디스크 영속화를 도입하지 않는다.
- `preview_id`는 프로세스 로컬 디버깅 식별자일 뿐, future submit phase의 신뢰 키가 아니다.
- future submit phase가 preview와 연결할 때는 `preview_fingerprint`를 기준으로 한다.
- preview 결과를 메모리에 일시 유지하더라도 daemon 재기동 후 복구를 보장하지 않는다.

### API / 인터페이스

#### CLI

추가 대상:

- `toss-bridge order-preview --market us --side buy --symbol AAPL --order-type limit --quantity 3 --limit-price 201.5`
- `toss-bridge fx-preview --side buy --amount-krw 1500000`

CLI 원칙:

- 기존과 동일하게 daemon을 자동 기동한다.
- validation error도 JSON으로 일관되게 출력한다.
- submit 관련 옵션(`--confirm` 등)은 이 phase에서 추가하지 않는다.
- [보완] `order-preview`는 `--order-type`을 필수 플래그로 노출한다.
- [보완] `fx-preview`는 `--amount-krw`와 `--amount-usd`를 동시에 받을 수 없다.

#### Daemon Query Kind

- `order_preview`
- `fx_preview`

`execute()`에 위 kind를 추가하고, 기존 read path와 동일하게 `/bridge/query`를 통해 호출한다.

#### Readiness Contract

`health.data.capabilities`에서 아래 semantics를 유지한다.

- `order_preview_ready`: `logged-in + account_summary_ready + quote_ready`
- `fx_preview_ready`: [추정] FX rate endpoint family가 확인되기 전까지는 보수적으로 false 유지 또는 request-time capability check만 수행
- `order_submit_ready`: submit 단계까지 안전하게 진행 가능한 것은 아님. 후속 phase에서만 의미 부여
- `fx_submit_ready`: 동일
- `cancel_order_ready`: 동일

추가 후보:

- `post_submit_verify_ready`

이 키는 submit phase 설계가 확정될 때 도입 여부를 다시 결정한다. preview phase에서는 문서 수준 후보로만 유지한다.

보완 규칙:

- `positions_ready`는 order preview base readiness의 필수 전제는 아니다.
- 다만 sell preview는 요청 시점에 positions 재조회를 시도하고, 실패 시 `capability_not_ready` 또는 `preview_state=blocked`로 처리한다.
- capability는 health 시점의 base readiness만 나타내며, 특정 요청 파라미터까지 완전하게 보장하지는 않는다.

### 컴포넌트 구조

```mermaid
flowchart TD
    CLI[cli.py] --> INVOKE[/bridge/query]
    INVOKE --> DAEMON[TossBridgeRuntime.execute]
    DAEMON --> VALIDATE[preview input validation]
    VALIDATE --> PREFETCH[account or quote or market prefetch]
    PREFETCH --> BUILD[preview builder]
    BUILD --> RESULT[preview response]
    RESULT --> FUTURE[future submit phase]
```

#### 내부 구성 제안

- `daemon.py` 안에서 시작해도 되지만, preview 로직이 길어지면 별도 helper 모듈로 분리하는 것이 낫다.
- [보완] 구현 중 로직이 커지면 `src/toss_browser_bridge/preview.py` 또는 유사 helper 모듈로 이동한다.
- 초기 구현은 다음 순서가 현실적이다.
  - `daemon.py`에 command wiring 추가
  - preview request builder / response builder helper 추가
  - endpoint request templates를 명시적 상수로 분리
- `bridge_lib.py`는 transport와 runtime 유틸만 유지하고 mutation 도메인 로직은 넣지 않는다.
- [보완] preview phase에서는 현재 runtime lock 기반 직렬 실행을 유지한다.

### Preview 계산 원칙

#### Order Preview

- 입력 정규화
- 로그인 상태 확인
- 계좌 요약과 주문 가능 금액 조회
- 종목/시장 메타데이터와 최신 가격 조회
- 주문 유형에 따라 예상 주문 금액 계산
- 주문 가능 금액 대비 부족 여부 계산
- 시장 상태 또는 거래 제한 플래그를 warnings/blocking_issues로 분류
- 후속 submit에 필요한 핵심 필드만 추려 `submit_candidate` 구성

#### FX Preview

- 입력 정규화
- 로그인 상태 확인
- 환전 가능 잔액과 대상 통화 잔액 조회
- 현재 환율 및 수수료성 정보 확보 가능 여부 확인
- 입력 금액 기준 예상 수취 금액 계산
- 최소/최대 가능 금액, 잔액 부족, 시장 비가동 상태를 warnings/blocking_issues로 분류
- 후속 submit에서 동일성 검증 가능한 `submit_candidate` 구성

### Error Taxonomy

- `invalid_request`
  - 파라미터 누락, 형식 오류, 상호 배타 위반
- `logged_out`
  - 브라우저 attach는 됐지만 로그인되지 않음
- `capability_not_ready`
  - preview 의존 endpoint가 실패하거나 세션 조건이 부족함
- `preview_failed`
  - endpoint 응답 구조 예기치 않음, 계산 실패, 데이터 불일치

preview는 `runtime_error`에 최대한 의존하지 않고 도메인 오류로 환원하는 것이 목표다.

## 구현 계획

### Phase A: Preview Contract 고정

- [ ] `order-preview`, `fx-preview` CLI/daemon command name과 파라미터 스키마 확정
- [ ] preview response 공통 envelope와 `data` 필드 구조 확정
- [ ] capability readiness semantics 문서화
- [ ] preview fingerprint 입력 집합 정의
- [ ] [보완] preview error transport 규칙 고정

검증 기준:

- 문서만 보고도 CLI와 daemon 인터페이스를 구현할 수 있어야 한다.

### Phase B: Order Preview 기반 구현

- [ ] `cli.py`에 `order-preview` 서브커맨드 추가
- [ ] `daemon.py execute()`에 `order_preview` 추가
- [ ] 기존 `validate_order_preview_params()`를 실제 호출 경로에 연결
- [ ] order preview용 사전 조회 endpoint 세트 정의
- [ ] `submit_candidate`, `warnings`, `blocking_issues`, `preview_state` 생성 로직 구현
- [ ] `order_preview_ready` readiness 판정 로직 구현
- [ ] [보완] preview domain error를 generic `runtime_error`에서 분리

검증 기준:

- valid request에서 예측 가능한 preview JSON이 반환된다.
- invalid request와 logged-out 상태가 일관된 error code로 반환된다.

### Phase C: FX Endpoint Discovery / Preview 구현

- [ ] FX preview용 실제 endpoint family를 discovery spike로 식별
- [ ] `cli.py`에 `fx-preview` 서브커맨드 추가
- [ ] `daemon.py execute()`에 `fx_preview` 추가
- [ ] 기존 `validate_fx_preview_params()`를 실제 호출 경로에 연결
- [ ] FX preview용 사전 조회 endpoint 세트 정의
- [ ] 예상 환전 결과, warnings, blocking_issues, `preview_state` 생성 로직 구현
- [ ] `fx_preview_ready` readiness 판정 로직 구현

검증 기준:

- KRW/USD 단일 금액 입력 규칙이 보장된다.
- 잔액 부족과 조회 실패가 구분된 오류 또는 blocking issue로 노출된다.
- endpoint family가 확인되지 않으면 `fx_preview_ready`를 true로 과대 노출하지 않는다.

### Phase D: Preview Quality / Verification Scaffold

- [ ] preview fingerprint 생성 규칙 구현
- [ ] verification plan 필드 구성
- [ ] daemon error response와 diagnostics를 preview path에도 맞춰 정리
- [ ] logged-in / logged-out fixture 기반 preview 테스트 추가
- [ ] 후속 submit phase가 재사용할 mutation state skeleton 정리
- [ ] [보완] privacy scrub rules를 preview 결과/diagnostics에도 적용

검증 기준:

- 같은 정규화 입력과 같은 파생 상태에서는 fingerprint가 안정적으로 재현된다.
- submit phase 설계 시 preview payload를 그대로 참조할 수 있다.

### Phase E: Submit/Cancellation 후속 Phase 정의

- [ ] `place-order`, `fx-exchange`, `cancel-order`를 별도 spec 또는 phase 문서로 분리
- [ ] `--confirm`, post-submit verify, idempotency persistence 요건을 후속 범위로 고정

검증 기준:

- 현재 스펙을 확장하지 않고도 후속 feature-spec 또는 phase-planning 문서로 자연스럽게 이어진다.

## 영향 분석

| 영역 | 변경 내용 | 위험도 | 완화 방안 |
|------|----------|--------|----------|
| daemon query dispatch | preview kind 추가, readiness 판정 분기 추가 | 중간 | read path와 별도 helper로 분리하고 응답 envelope를 유지 |
| CLI surface | 새 서브커맨드와 인자 파싱 추가 | 낮음 | 기존 invoke 패턴 재사용, validation은 daemon 중심 유지 |
| browser fetch layer | preview용 사전 조회 endpoint 추가 | 높음 | endpoint template를 명시적 상수로 두고 diagnostics에 모두 노출 |
| capability matrix | preview/submit readiness semantics 구체화 | 중간 | `browser_attached`와 독립된 readiness 판정 규칙 문서화 |
| 테스트 픽스처 | logged-in/logged-out 및 preview fixture 확장 | 중간 | endpoint별 최소 fixture 세트를 분리 유지 |
| 후속 submit 설계 | preview contract가 submit phase의 기초가 됨 | 높음 | preview fingerprint, verification plan, submit_candidate를 초기부터 고정 |
| [보완] privacy boundary | preview 결과에 계좌/세션 정보가 추가될 수 있음 | 높음 | masked account id, sanitized diagnostics, 디스크 영속화 금지 |

## 테스트 계획

### 단위 테스트

- `validate_order_preview_params()` 정상/오류 케이스
- `validate_fx_preview_params()` 정상/오류 케이스
- preview fingerprint 생성 안정성
- warnings/blocking_issues 분류 함수
- readiness classifier에서 preview capability 판정
- [보완] `preview_state` 계산과 sell preview positions 의존성

### 통합 테스트

- daemon `order_preview` JSON 응답 형태 검증
- daemon `fx_preview` JSON 응답 형태 검증
- logged-out 상태에서 `logged_out` 오류 반환 검증
- preview 의존 endpoint 일부 실패 시 `capability_not_ready` 또는 `preview_failed` 반환 검증
- CLI 서브커맨드가 daemon 기동과 함께 정상 동작하는지 검증
- [보완] invalid request가 `runtime_error`가 아닌 domain error로 반환되는지 검증

### 엣지 케이스

- 시장가 주문에 `limit_price`가 들어온 경우
- 지정가 주문에 `limit_price`가 없는 경우
- KRW/USD 금액 필드가 동시에 들어온 경우
- 수량/금액이 문자열, 공백, 불리언, 소수 등 경계값인 경우
- 종목 검색 성공 후 가격 조회 실패하는 경우
- preview 시점과 submit 시점 사이에 가격 또는 주문 가능 금액이 변하는 경우
- 브라우저 attach는 살아 있으나 특정 endpoint family만 실패하는 readiness skew
- [보완] sell preview에서 positions 조회만 실패하는 경우

## 결정 사항

- preview-first mutation architecture를 우선한다: `docs/write-path-opinion.md`와 현재 코드베이스 방향이 모두 직접 submit보다 preview layer를 먼저 요구한다.
- browser-attached 모델을 유지한다: 현재 daemon의 핵심 자산이 `_fetch_many`와 전용 Chrome 프로필 attach이기 때문이다.
- preview는 fetch 기반으로 간다: 현재 read path와 재사용성이 가장 높고, submit phase에서 hybrid 전략으로 확장할 수 있다.
- submit/cancel은 별도 phase로 분리한다: 실제 금전 이동이 수반되는 단계는 `--confirm`, post-submit verify, idempotency persistence가 준비된 뒤에만 열어야 한다.
- preview response에 `submit_candidate`와 `verification_plan`을 포함한다: preview를 단순 검증 도구가 아니라 후속 submit scaffold로 사용하기 위해서다.
- preview fingerprint를 초기에 도입한다: 같은 preview를 submit 단계에서 동일성 검증에 재사용하기 위해서다.
- [보완] `order_type`은 명시 입력으로 고정한다: market order를 암묵 기본값으로 열지 않기 위해서다.
- [보완] preview phase에서는 디스크 영속화를 도입하지 않는다: 보안과 정합성 비용이 submit phase 설계 없이 커지기 때문이다.
- [보완][추정] `fx_preview_ready`는 endpoint family가 확인되기 전까지 보수적으로 운영한다: health가 실제 능력을 과대 표시하지 않기 위해서다.

## 열린 질문

- FX preview용 실제 환율/수수료 endpoint family가 무엇인지.
- future submit에서 `preview_id`를 입력받을지, `preview_fingerprint`만 사용할지.
- `post_submit_verify_ready`를 health capability에 언제 노출할지.
