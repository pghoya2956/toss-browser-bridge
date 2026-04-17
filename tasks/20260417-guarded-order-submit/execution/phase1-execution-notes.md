# Phase 1: Submit Path Discovery 실행 로그

> Append-only. 수정/삭제 금지.

| 항목 | 값 |
|------|-----|
| 시작 | 2026-04-17 14:38 KST |
| Phase 계획 | [phase1-submit-path-discovery.md](../phase/phase1-submit-path-discovery.md) |

---

### 운영 원칙: daemon/browser 컨텍스트 유지 [●]

**배경**: 같은 전용 Chrome 프로필을 daemon과 일회성 Playwright가 번갈아 소유하면 세션 안정성과 사용자 경험이 흔들린다.

**결정 이유**: 이 프로젝트의 기조를 browser-attached companion으로 유지하려면, 세션 동안 daemon과 전용 프로필을 한 번만 올려 두고 같은 컨텍스트를 진실의 원천으로 써야 한다.

**실행**: 이후 discovery와 검증은 이미 붙어 있는 daemon/browser 컨텍스트를 기준으로 진행하고, stale daemon 정리 같은 명확한 이유가 없는 한 반복 재기동하지 않는 원칙으로 고정했다.

**결과**: submit phase 설계와 live validation 절차가 모두 “daemon one-shot attach 후 유지” 모델을 전제로 하게 됐다.

---

### P1-01: 미국 limit order submit path를 실측으로 확인 [●]

**배경**: 실제 돈이 움직이는 submit path는 추측 구현을 허용하면 안 된다.

**결정 이유**: 로그인된 전용 Chrome 프로필에서 실주문을 막는 endpoint abort를 걸고 클릭 단계를 나눠 관찰하면, 주문을 내지 않고도 prepare/create 분리를 안전하게 볼 수 있다.

**실행**: NVDA 주문 페이지(`https://www.tossinvest.com/stocks/US19990122001/order`)에서 `quantity=1`로 설정 후 `구매하기`를 한 번 눌렀다. 첫 클릭 직후 `POST /api/v2/wts/trading/order/prepare`만 호출되고, 확인 다이얼로그가 열리는 것을 확인했다.

**결과**: 미국 limit order는 `prepare → confirm modal → create` 2단계 fetch path를 가진다.

---

### P1-02: 최종 submit endpoint와 필수 context를 확인 [●]

**배경**: `create`가 어떤 context에 의존하는지 모르면 Phase 2에서 재현 가능한 guarded submit을 만들 수 없다.

**결정 이유**: `create` endpoint를 Playwright route에서 abort해 두고 최종 `구매` 버튼만 누르면, 실주문 없이 request shape를 관찰할 수 있다.

**실행**: 최종 `구매` 버튼 클릭 시 `POST /api/v2/wts/trading/order/create`가 발생하는 것을 확인했다. `prepare`는 `withOrderKey=true`로 요청되고 응답에 `orderKey`가 포함됐다. `create`는 `X-ORDER-KEY` 헤더를 요구했다. 공통 헤더는 `App-Version`, `Browser-Tab-Id`, `X-XSRF-TOKEN`, `X-Tossinvest-Account`였다.

**결과**: limit order submit의 최소 필수 context는 브라우저 세션, account header, xsrf, browser tab id, app version, prepare에서 얻은 order key다.

---

### P1-03: confirm 단계와 simple-trade 설정의 상호작용을 확인 [●]

**배경**: “한 번 클릭이 곧 실주문인지”가 불명확하면 automation safety 경계가 무너진다.

**결정 이유**: 설정 endpoint와 실제 클릭 결과를 같이 보면 UI confirm의 유무를 계정 설정과 연결해 해석할 수 있다.

**실행**: `GET /api/v1/trading/settings/toggle/find?categoryName=TRADE_WITHOUT_CONFIRM` 결과가 `turnedOn: false`임을 확인했다. 같은 세션에서 첫 클릭 후 확인 다이얼로그가 뜨는 것도 함께 관찰했다.

**결과**: 현재 계정 설정에서는 direct submit이 아니라 확인 다이얼로그를 거친다.

---

### P1-04: prepare 응답 shape와 broker pre-submit 판단 정보를 확인 [●]

**배경**: preview receipt만으로는 submit 직전 값이 바뀌었는지 충분히 알 수 없다.

**결정 이유**: prepare 응답에서 실제 주문 확인창에 쓰는 값과 safety signal을 확인하면 request-time recheck 기준을 더 좁힐 수 있다.

**실행**: `prepare` 응답에서 `orderKey`, `authRequired`, `buyingRedFlags`, `preparedOrderInfo`를 확인했다. `preparedOrderInfo`에는 `tradeType`, `orderPriceType`, `price`, `quantity`, `commission`, `tradeAmount`, `orderExpiredAt` 등이 들어 있었다. 실측 기준 `authRequired.required=false`, `authRequired.simpleTrade=true`였다.

**결과**: request-time recheck는 prepare 응답의 `preparedOrderInfo`와 preview receipt를 비교하는 방식으로 설계할 수 있다.

---

### P1-05: 국내/미국 endpoint family 공통성을 정적 분석으로 확인 [◐]

**배경**: 시장별로 submit endpoint가 갈리면 Phase 2 구현 범위를 다시 나눠야 한다.

**결정 이유**: live browser 소유권을 흔들지 않고도 번들 문자열을 뒤지면 endpoint family 공통성을 빠르게 판정할 수 있다.

**실행**: `pages/_app-*.js` 번들에서 `/api/v2/wts/trading/order/prepare`, `/api/v2/wts/trading/order/create`, `/api/v2/wts/trading/order/create/direct`를 찾았다. 함수 시그니처는 `stockCode`, `tradeType`, `market`, `orderPriceType`, `currencyMode` 같은 payload 필드로 시장을 구분하고, endpoint 자체는 generic path를 재사용한다.

**결과**: 국내/미국 limit order는 endpoint family를 공유할 가능성이 높다. 다만 국내 live order page 실측은 아직 남아 있다.

---

### P1-06: bundle 상수로 submit/reject/auth 분류 후보를 확보 [●]

**배경**: 실제 `create` 성공/실패 응답을 아직 열지 못한 상태에서, daemon 상태 모델을 전혀 근거 없이 짜면 나중에 다시 뜯어야 한다.

**결정 이유**: 번들 안의 order schema와 status enum을 먼저 확보해 두면 `broker_ack` summary와 verify status mapping을 더 좁게 설계할 수 있다.

**실행**: 번들에서 order payload schema 상수와 상태 enum을 확인했다. 주요 optional 필드는 `agreedBuyingRedFlag`, `confirmed`, `upperLimit`, `lowerLimit`, `exchangePrice`, `transferDollarAmount`, `hasConfirmedExchangeNotice`였다. 상태 enum은 `예약`, `체결대기`, `체결완료`, `부분체결`, `취소`, `실패`, `주문거부`, `수정`, auth verifier enum은 `REQUIRED`, `NOT_REQUIRED`, `AGAIN_REQUIRED`, `DONE`, `UNKNOWN`였다.

**결과**: daemon 상태 매핑 초안과 auth-required 보수 처리 기준을 세울 근거가 생겼다.

---

### P1-07: verify 후보 endpoint family를 정적 분석으로 확보 [●]

**배경**: Phase 3 verify aggregator를 기존 read signal만으로 끝낼지, order-detail endpoint를 추가할지 판단 근거가 필요하다.

**결정 이유**: 번들에서 verify 후보 endpoint를 먼저 정리해 두면, Phase 2는 최소 read signal만 쓰고 Phase 3에서 필요한 추가 endpoint를 선택적으로 도입할 수 있다.

**실행**: 번들에서 `GET /api/v1/trading/orders/histories/all/pending`, `GET /api/v2/trading/my-orders/markets/[market]/pending`, `GET /api/v2/trading/my-orders/markets/[market]/order-details/[orderDate]/[orderNo]`, `GET /api/v2/trading/my-orders/markets/[market]/preorder-details/[orderDate]/[orderNo]`, `GET /api/v3/trading/orders/histories/compact/executed`, `GET /api/v3/trading/order/[orderKorNo]/available-actions`를 확인했다. 상세 정리는 [submit-path-discovery.md](../references/submit-path-discovery.md)에 남겼다.

**결과**: verify path는 기존 `completed_orders` / `positions` / `account_summary` 조합으로 먼저 가고, 부족할 때만 order-detail endpoint를 Phase 3에서 추가하는 방향이 명확해졌다.

---

### P1-08: fetch 유지 조건과 UI fallback 기준을 문서화 [●]

**배경**: fetch `create`가 존재한다는 사실만으로 pure fetch submit을 기본 경로로 열면 위험하다.

**결정 이유**: 실제 사이트가 확인 다이얼로그를 띄우고, 현재 계정 설정도 `TRADE_WITHOUT_CONFIRM=false`이므로 guarded submit의 기본은 UI confirm 유지가 맞다.

**실행**: [submit-path-discovery.md](../references/submit-path-discovery.md)에 보수적 운영 기준을 정리했다. 기본 경로는 `prepare` fetch + UI modal confirm이고, pure fetch `create`는 no-confirm 설정 활성화, `authRequired.required=false`, verifier 추가 요구 없음, live supervised validation 동등성 확인까지 만족할 때만 검토 대상으로 남겼다.

**결과**: Phase 2 구현의 기본 방향이 “request-time recheck는 fetch, 마지막 confirm은 UI 유지”로 고정됐다.

---

### P1-09: daemon runtime에도 discovery 결과를 반영 [●]

**배경**: discovery가 문서에만 남아 있으면 health/diagnostics가 실제 진행 상태를 설명하지 못한다.

**결정 이유**: submit path는 파악됐지만 verify path가 미구현이라 닫혀 있다는 점을 runtime state에 반영하면, 이후 구현과 운영 판단이 더 명확해진다.

**실행**: daemon 기본 runtime state에서 `submit_path_discovered=true`, `verify_path_discovered=false`로 분리하고, `diagnostics.runtime`에 mutation runtime state를 노출했다. `place-order` 차단 메시지도 “discovery 미완료”가 아니라 “post-submit verify 미구현”으로 바꿨다.

**결과**: daemon이 현재 guarded submit 차단 이유를 스스로 설명하게 됐다.

---

### P1-10: 아직 남은 discovery 항목을 분리 [◐]

**배경**: create 응답과 verify window는 실제 submit을 막아둔 관찰만으로는 끝까지 확인되지 않는다.

**결정 이유**: 이미 확인된 fetch path와 아직 미확인인 ack/reject/timeout/verify signal을 분리해야 Phase 2와 Phase 3 경계가 흔들리지 않는다.

**실행**: 미확인 항목을 정리했다.

**결과**:

- `create` 성공 응답 shape와 broker reject 응답 shape는 아직 미확인
- `submit_cancelled`는 확인 다이얼로그에서 `취소`로 UI state는 확인 가능하지만, daemon response mapping은 아직 미구현
- `completed_orders` / `positions` / `account_summary`가 실제 submit 후 몇 초 내 수렴하는지는 supervised live validation 전까지 보류
