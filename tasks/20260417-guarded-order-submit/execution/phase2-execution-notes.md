# Phase 2: Guarded Place-Order 실행 로그

> Append-only. 수정/삭제 금지.

| 항목 | 값 |
|------|-----|
| 시작 | 2026-04-17 15:00 KST |
| Phase 계획 | [phase2-guarded-place-order.md](../phase/phase2-guarded-place-order.md) |

---

### P2-01: zero-money guarded preflight로 범위를 고정 [●]

**배경**: 실제 `create`를 열기 전에 submit guard rail을 코드로 먼저 고정하지 않으면, 이후 구현이 verify 미구현 상태에서 과도하게 열릴 수 있다.

**결정 이유**: 현재 남은 불확실성은 `create` 응답 shape와 bounded verify window다. 이 둘이 없는 상태에서도 fresh preview 재검증, duplicate-prevention, journal append는 안전하게 구현할 수 있다.

**실행**: `place-order`를 final submit 대신 zero-money preflight 단계까지만 확장하는 방향으로 고정했다. 최종 `create`와 verify는 여전히 닫아 둔다.

**결과**: 실제 돈이 움직이지 않는 범위에서 submit 직전 safety contract를 더 강하게 검증할 수 있게 됐다.

---

### P2-02: request-time preview recheck를 `place-order`에 반영 [●]

**배경**: preview를 본 뒤 submit까지 시간이 지나면 잔고나 보유수량이 바뀔 수 있다.

**결정 이유**: 기존 `order-preview`를 같은 daemon 컨텍스트에서 다시 평가하면, 별도 submit helper를 만들기 전에 drift를 가장 단순하고 보수적으로 차단할 수 있다.

**실행**: `place-order`에서 `preview_receipt.inputs`를 기반으로 fresh `order-preview`를 다시 호출하고, `preview_state`가 `preview_ready`가 아니면 hard-block 하도록 구현했다. fresh `preview_fingerprint`가 receipt와 다를 때도 즉시 차단한다.

**결과**: submit 직전 drift가 있으면 `submit_blocked`로 멈추고, mutation journal에도 sanitized 사유가 남는다.

---

### P2-03: mutation journal 기반 duplicate-prevention 추가 [●]

**배경**: 같은 preview receipt를 네트워크 실패나 사용자 재시도로 반복 호출하면 실제 submit phase에서 중복 주문 위험이 생긴다.

**결정 이유**: verify/recovery가 아직 없으므로, 현재 단계에서는 같은 `preview_fingerprint` 재사용을 보수적으로 전면 차단하는 편이 안전하다.

**실행**: mutation journal의 최근 항목을 역순으로 훑어 같은 `preview_fingerprint`가 이미 존재하면 `place-order`를 `submit_blocked`로 종료하도록 구현했다.

**결과**: 동일 receipt 재사용이 막혔고, live E2E도 항상 fresh fingerprint를 쓰도록 조정했다.

---

### P2-04: daemon 유지 원칙에 맞게 live E2E 조정 [●]

**배경**: 기존 live test는 시작 시 daemon을 내렸다 올리는 흐름이라 운영 원칙과 어긋났다.

**결정 이유**: 실사용 흐름과 동일한 조건에서 검증해야 stale daemon 문제와 일반 운영 흐름을 분리해서 다룰 수 있다.

**실행**: `tests/test_live_e2e.py`를 수정해 이미 떠 있는 daemon을 그대로 사용하도록 바꿨다. read → limit `order-preview` → `place-order` guarded block → `fx-preview`를 검증한다. 코드 변경으로 stale daemon이 확인된 경우에만 예외적으로 한 번 재기동해 새 구현을 확인했다.

**결과**: live E2E가 현재 프로젝트 운영 원칙과 일치하게 됐고, 실제 세션에서 guarded preflight가 작동함을 확인했다.

---

### P2-05: 현재 남은 구현 범위를 분리 [◐]

**배경**: `place-order` guard rail은 강화됐지만, 아직 `prepare` fetch와 `preparedOrderInfo` 비교는 미구현이다.

**결정 이유**: 이 구간을 별도 남은 작업으로 명확히 분리해야, Phase 2 완료 조건과 Phase 3 verify 범위가 섞이지 않는다.

**실행**: task plan의 Phase 2 상태를 `◐`로 올리고, 다음 구현 입력을 “`prepare` fetch + preparedOrderInfo drift 비교”로 고정했다.

**결과**: 다음 구현 포인트가 명확해졌고, 최종 `create`를 열기 전 필요한 zero-money leverage가 정리됐다.

---

### P2-06: `prepare` fetch preflight와 broker ack summary를 연결 [●]

**배경**: request-time preview recheck만으로는 실제 submit path와의 드리프트를 충분히 잡을 수 없다.

**결정 이유**: Phase 1에서 이미 `prepare`가 zero-money 단계라는 점을 확인했으므로, `create`를 열지 않고도 broker-side preflight를 안전하게 끼울 수 있다.

**실행**: `place-order`에서 account overview raw 응답으로 `accountNo`를 얻고, `prerequisite` / `TRADE_WITHOUT_CONFIRM` / `prepare`를 같은 daemon 컨텍스트에서 호출하도록 구현했다. `preparedOrderInfo`의 `tradeType`, `orderPriceType`, `quantity`를 receipt와 비교하고, 성공 시에는 sanitized `PREPARED` broker ack summary를 journal에 남긴 뒤 `capability_not_ready`로 종료한다.

**결과**: `place-order`는 이제 단순 contract 확인이 아니라 실제 broker preflight를 통과한 뒤 마지막 `create` 직전에서 멈추는 상태가 됐다.

---

### P2-07: 미국 매수 auto-exchange prepare 경로를 실측에 맞춤 [●]

**배경**: 첫 `prepare` 구현은 미국 매수에서 500을 반환했다.

**결정 이유**: discovery 실측에서 미국 주문 페이지 기본값이 `currencyMode=KRW`였고, `prepare` payload에서 optional field를 과하게 싣는 것이 오히려 실패 원인이 될 수 있었다.

**실행**: 미국 매수 preflight는 `currencyMode=KRW`, `allowAutoExchange=true`로 보내고, `orderAmount` 등 의미가 불확실한 optional field는 payload에서 제거했다. 이후 `prepare`는 200으로 응답했다.

**결과**: `prepare` 자체는 실제 세션에서 성공하게 됐고, 마지막 blocker는 verify 미구현만 남게 됐다.

---

### P2-08: auto-exchange price drift 의미 차이를 정리 [●]

**배경**: `prepare`는 성공했지만 미국 매수 auto-exchange 경로에서 `preparedOrderInfo.price`가 preview의 limit price와 다르게 나타났다.

**결정 이유**: 이 필드는 auto-exchange 표현과 섞여 의미가 달라질 수 있으므로, Phase 2에서는 hard-block 기준에서 일단 제외하고 나머지 핵심 필드에 집중하는 편이 맞다.

**실행**: auto-exchange가 켜진 미국 매수 preflight에서는 `tradeType`, `orderPriceType`, `quantity`만 drift hard-block 대상으로 유지하고, `price` 비교는 보수적으로 skip하도록 조정했다.

**결과**: zero-money preflight가 실세션에서 안정적으로 통과하고, `create` 직전의 guard rail 역할을 수행하게 됐다.

---

### P2-09: logged-in live E2E로 `prepare` preflight를 재검증 [●]

**배경**: unit test만으로는 실제 browser-attached 세션에서 `prepare`가 통과하는지 확인할 수 없다.

**결정 이유**: 이 프로젝트의 기준선은 로컬 실사용 세션에서 read / preview / guarded preflight가 모두 일관되게 동작하는 것이다.

**실행**: live E2E를 `read → limit order-preview → place-order preflight → fx-preview` 흐름으로 유지한 채 다시 돌렸다. daemon은 코드 변경 때만 한 번 재기동하고, 이후에는 같은 세션을 유지했다.

**결과**: `TOSS_BRIDGE_LIVE_E2E=1 uv run --extra dev pytest tests/test_live_e2e.py -q`가 통과했다. 현재 `place-order`는 실제 세션에서 `prepare` preflight 후 의도적으로 `capability_not_ready`로 멈춘다.
