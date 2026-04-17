# Submit Path Discovery

## 개요

guarded submit Phase 1에서 확인한 limit order submit path와 verify 후보를 정리한다.

## 미국 limit order 실측

- 주문 페이지: `https://www.tossinvest.com/stocks/US19990122001/order`
- 첫 클릭:
  - UI: `구매하기`
  - 요청: `POST /api/v2/wts/trading/order/prepare`
  - 결과: 확인 다이얼로그 표시
- 최종 클릭:
  - UI: 확인 다이얼로그의 `구매`
  - 요청: `POST /api/v2/wts/trading/order/create`
  - 안전 확인: discovery에서는 route abort로 실제 submit 차단

결론:

- 미국 limit order는 `prepare → confirm modal → create` 2단계 fetch path다.
- 현재 계정 설정에서 direct submit은 꺼져 있다.

## 확인된 설정

- `GET /api/v1/trading/settings/toggle/find?categoryName=TRADE_WITHOUT_CONFIRM`
  - 실측 결과: `turnedOn=false`
- `prepare` 응답
  - `orderKey` 포함
  - `authRequired.required=false`
  - `authRequired.simpleTrade=true`
  - `preparedOrderInfo` 포함

## submit payload / header shape

실측 기준 `prepare` 요청:

- endpoint: `POST /api/v2/wts/trading/order/prepare`
- 필수 헤더 이름:
  - `App-Version`
  - `Browser-Tab-Id`
  - `X-XSRF-TOKEN`
  - `X-Tossinvest-Account`
- 주요 payload 필드:
  - `stockCode`
  - `tradeType`
  - `market`
  - `currencyMode`
  - `price`
  - `quantity`
  - `orderPriceType`
  - `withOrderKey`
  - `allowAutoExchange`
  - `marginTrading`
  - `isReservationOrder`
  - `orderAmount`
  - `openPriceSinglePriceYn`
  - `max`

실측 기준 `create` 요청:

- endpoint: `POST /api/v2/wts/trading/order/create`
- 추가 헤더:
  - `X-ORDER-KEY`
- 주요 payload 필드:
  - `stockCode`
  - `tradeType`
  - `market`
  - `currencyMode`
  - `price`
  - `quantity`
  - `orderPriceType`
  - `allowAutoExchange`
  - `marginTrading`
  - `isReservationOrder`
  - `orderAmount`
  - `openPriceSinglePriceYn`
  - `max`

구현 시사점:

- daemon은 request-time recheck 이후 `prepare`를 먼저 호출해야 한다.
- `prepare` 응답의 `orderKey` 없이는 `create`를 호출하지 않는다.
- `X-ORDER-KEY`는 디스크에 저장하지 않고 프로세스 메모리에서만 다룬다.

## prepare 응답에서 재검증에 쓸 값

`preparedOrderInfo`에서 확인한 필드:

- `tradeType`
- `orderPriceType`
- `price`
- `quantity`
- `commission`
- `tradeAmount`
- `orderExpiredAt`
- `displayPrice`
- `displayQuantity`
- `displayTradeAmount`
- `displayCommission`

구현 시사점:

- preview receipt와 `preparedOrderInfo`를 비교해 price/quantity/order type drift를 막는다.
- `tradeAmount`, `commission`, `orderExpiredAt`은 final confirm 직전 경고/차단 판단에 쓸 수 있다.

## 번들에서 확인한 order schema 상수

정적 분석 기준 주요 optional payload 필드:

- `agreedOver100Million`
- `agreedBuyingRedFlag`
- `confirmed`
- `upperLimit`
- `lowerLimit`
- `exchangePrice`
- `transferDollarAmount`
- `hasConfirmedExchangeNotice`

구현 시사점:

- Phase 2 첫 버전은 실측에 나온 최소 필드만 다루고, 나머지는 `prepare` 응답이 요구할 때만 제한적으로 연다.
- `confirmed`, `upperLimit`, `lowerLimit`는 prepare/create helper 시그니처에 자리는 남겨 두되 기본값은 넣지 않는다.

## bundle 상태 enum

정적 분석 기준 주문 상태 라벨:

- `예약`
- `체결대기`
- `체결완료`
- `부분체결`
- `취소`
- `실패`
- `주문거부`
- `수정`

정적 분석 기준 auth verifier enum:

- `REQUIRED`
- `NOT_REQUIRED`
- `AGAIN_REQUIRED`
- `DONE`
- `UNKNOWN`

구현 시사점:

- daemon 상태 모델 매핑 초안:
  - `체결대기` → `submitted`
  - `체결완료`, `부분체결` → `verified_success`
  - `취소` → `submit_cancelled`
  - `실패`, `주문거부` → `broker_rejected`
- `authRequired.verifier`가 `REQUIRED`/`AGAIN_REQUIRED`면 Phase 2 범위 밖으로 두고 `capability_not_ready` 또는 `submit_blocked`로 보수 처리한다.

## verify 후보 endpoint

정적 분석으로 확인한 verify 관련 endpoint family:

- `GET /api/v1/trading/orders/histories/all/pending`
- `GET /api/v2/trading/my-orders/markets/[market]/pending`
- `GET /api/v2/trading/my-orders/markets/[market]/order-details/[orderDate]/[orderNo]`
- `GET /api/v2/trading/my-orders/markets/[market]/preorder-details/[orderDate]/[orderNo]`
- `GET /api/v3/trading/orders/histories/compact/executed`
- `GET /api/v3/trading/order/[orderKorNo]/available-actions`

bridge에서 이미 가진 read signal:

- `completed_orders`
- `positions`
- `account_summary`

구현 시사점:

- Phase 2 첫 버전은 기존 read signal만으로 bounded verify를 구성한다.
- 추가 endpoint는 `verify-order` 정확도 보강이 필요할 때 Phase 3에서 도입한다.

## 국내/미국 공통성 판단

현재 결론:

- `prepare/create/create-direct/correct` endpoint family는 generic path를 공유한다.
- 시장 차이는 payload의 `market`, `stockCode`, `currencyMode`, `tradeType`, `orderPriceType`로 표현되는 쪽이다.
- 국내 live order page 실측은 아직 남아 있지만, 구현 시작 시점 기준으로는 공통 helper를 먼저 두고 시장별 파라미터만 분기하는 설계가 합리적이다.

## fetch 유지 조건과 UI fallback 기준

현재 판단:

- fetch transport 자체는 확인됐다.
  - `prepare`: fetch
  - `create`: fetch
- 하지만 “fetch가 가능하다”와 “UI confirm을 우회해도 된다”는 같은 뜻이 아니다.

보수적 운영 기준:

- 기본 경로:
  - `prepare`는 fetch로 수행
  - 최종 confirm은 UI modal을 유지
  - 최종 submit은 UI modal의 action button click으로 진행
- pure fetch `create`는 기본값으로 열지 않는다.

UI modal 유지 근거:

- 현재 계정 설정에서 `TRADE_WITHOUT_CONFIRM=false`
- 실제 사이트도 첫 클릭 뒤 확인 다이얼로그를 강제한다
- guarded submit task의 목적이 “실제 돈이 움직이는 path를 더 보수적으로 여는 것”이기 때문이다

pure fetch `create`를 검토할 수 있는 최소 조건:

- 사용자가 토스 웹에서 이미 no-confirm 성격의 설정을 명시적으로 켰음
- `prepare` 응답에서 `authRequired.required=false`
- `authRequired.verifier`가 추가 인증을 요구하지 않음
- live supervised validation에서 fetch create와 UI click 결과가 동일하게 관찰됨

UI fallback이 필요한 조건:

- `TRADE_WITHOUT_CONFIRM=false`
- `authRequired.required=true`
- `authRequired.verifier`가 `REQUIRED` 또는 `AGAIN_REQUIRED`
- confirm modal에 buying red flag, 환전 notice, high-risk notice 등 추가 확인 UI가 개입함
- create 응답 shape가 아직 미확인이라 unknown recovery를 안전하게 담보할 수 없음

## 아직 미확인

- `create` 성공 응답 body shape
- `create` reject 응답 body shape
- timeout/connection drop 시 브라우저가 남기는 ambiguity signal
- submit 직후 `completed_orders` / `positions` / `account_summary` 수렴 시간
