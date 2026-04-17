# Submit Handoff

## 현재까지 확정된 자산

### Order Preview

- 입력 검증: `market`, `side`, `symbol`, `order_type`, `quantity`, `limit_price`
- 의존 read path:
  - `account_summary()`
  - `quote()`
  - sell 시 `positions()`
- fingerprint 기준:
  - `kind`
  - 정규화된 `inputs`
  - 마스킹된 `account_id`
  - `submit_candidate`
  - submit 안전성에 직접 영향을 주는 최소 `derived`

### FX Preview

- 입력 검증: `side`, `amount_krw` xor `amount_usd`
- 의존 read/public path:
  - `account_summary()`
  - `GET /api/v1/product/exchange-rate?buyCurrency=USD&sellCurrency=KRW`
  - `GET /api/v1/exchange/current-quote/for-buy`
  - `GET /api/v1/exchange/current-quote/for-sell`
- 실측 확인 필드:
  - `rateQuoteId`
  - `usdRate`
  - `displayUsdRate`
  - `favorablePercent`
  - `validFrom`
  - `validTill`
  - `round`

## Submit Phase에서 바로 이어받을 것

- `preview_fingerprint`를 submit payload 동일성 검증 기준으로 사용할지
- `preview_id`는 디버깅 식별자에만 남길지
- order/fx submit 전에 어떤 필드를 request-time으로 다시 확인할지
- post-submit verify 결과를 `verified_success`, `verified_failed`, `unknown` 중 어디로 내릴지

## 다음 구현 순서 제안

- `place-order`
  - preview fingerprint 일치 검사
  - explicit confirm 플래그
  - submit 후 `completed_orders`, `positions`, `account_summary` 재조회
- `fx-exchange`
  - preview fingerprint 일치 검사
  - `rateQuoteId` 유효기간 재확인
  - submit 후 `account_summary` 재조회
- `cancel-order`
  - open order 조회 경로 확정 후 별도 spec

## 남은 리스크

- FX submit endpoint family는 아직 실측하지 않았다.
- `order-preview`와 달리 FX는 공개 quote endpoint와 계좌 잔액 endpoint를 조합한 보수적 preview다.
- preview 단계의 `submit_candidate` 필드 집합은 submit phase에서 소폭 조정될 수 있지만, fingerprint 입력 집합은 가능한 유지해야 한다.
