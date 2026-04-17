# Phase 3: Verify and Recovery 실행 로그

> Append-only. 수정/삭제 금지.

| 항목 | 값 |
|------|-----|
| 시작 | 2026-04-17 15:40 KST |
| Phase 계획 | [phase3-verify-and-recovery.md](../phase/phase3-verify-and-recovery.md) |

---

### P3-01: `verify-order`를 실제 recovery command로 전환 [●]

**배경**: Phase 0의 `verify-order`는 contract만 고정했고, 실제 mutation journal recovery는 아직 없었다.

**결정 이유**: final `create`를 열기 전에도 blocked mutation과 이후 submitted mutation을 같은 식별자(`mutation_id`)로 다시 조회할 수 있어야 safety leverage가 생긴다.

**실행**: `src/toss_browser_bridge/daemon.py`에서 `verify_order()`가 `mutation_id`로 최근 journal entry를 찾고, verify path readiness를 검사한 뒤 recovery를 실행하도록 바꿨다. `place-order`의 blocked 종료에도 `mutation_id`를 diagnostics로 실어 후속 verify 연결이 가능하게 했다.

**결과**: `place-order` 실패 응답에서 받은 `mutation_id`를 바로 `verify-order`에 넘길 수 있게 됐다.

---

### P3-02: verify aggregator를 read signal 위에 조합 [●]

**배경**: broker ack summary만으로는 실제 주문 반영 여부를 확정할 수 없다.

**결정 이유**: 현재 레포에서 이미 신뢰 가능한 read surface는 `completed_orders`, `positions`, `account_summary`이므로, 새로운 취약한 probe를 만들기보다 이 조합을 verify source로 재사용하는 편이 안전하다.

**실행**: `verify-order`는 mutation journal entry의 `market/symbol/side/quantity`를 기준으로 최근 `completed_orders`를 매칭하고, 동시에 `positions`, `account_summary` 스냅샷을 함께 수집한다. 매칭되면 `verified_success`, 확정 근거가 부족하면 `unknown`, submit 자체가 blocked/rejected/cancelled였으면 `verified_failed`를 반환한다.

**결과**: verify 결과가 `verified_success` / `verified_failed` / `unknown`으로 일관되게 정리된다.

---

### P3-03: daemon 재기동 뒤 journal recovery를 live로 재검증 [●]

**배경**: mutation journal recovery는 daemon 재시작 뒤에도 이어져야 의미가 있다.

**결정 이유**: 이 프로젝트 운영 원칙상 daemon은 한 번만 올려 두고 유지하지만, 코드 변경으로 stale daemon이 생기면 예외적으로 한 번 재기동할 수 있다. 그 순간에도 recovery가 이어지는지 실측해야 한다.

**실행**: 최신 `daemon.py` 반영을 위해 stale daemon을 한 번만 `shutdown` 후 재시작했고, `TOSS_BRIDGE_LIVE_E2E=1 uv run --extra dev pytest tests/test_live_e2e.py -q`로 `place-order -> mutation_id -> verify-order` 흐름을 다시 검증했다.

**결과**: 재기동 뒤에도 같은 profile/journal 기준으로 `verify-order`가 동작했고, 현재 blocked preflight mutation은 `verified_failed`로 수렴한다.

---

### P3-04: 아직 남은 범위를 분리 [◐]

**배경**: verify-order recovery는 열렸지만, spec이 말하는 bounded verify wait loop와 final `create` 뒤 supervised submit은 아직 없다.

**결정 이유**: 현재 구현 수준을 과장하면 `order_submit_ready`를 잘못 여는 사고로 이어진다.

**실행**: health semantics를 `post_submit_verify_ready`와 `order_submit_ready`로 계속 분리하고, `final_submit_enabled=false`가 없이는 `order_submit_ready`가 열리지 않도록 유지했다. task plan도 Phase 3 `◐`로 갱신했다.

**결과**: verify recovery는 usable 상태가 됐지만, 실제 돈이 움직이는 final submit은 여전히 닫혀 있다.

---

### P3-05: bounded verify window를 `verify-order` 내부에 고정 [●]

**배경**: verify aggregator만 한 번 호출하면, 주문 반영이 약간 늦는 케이스를 너무 쉽게 `unknown`으로 분류할 수 있다.

**결정 이유**: final `create`를 열기 전에도 verify semantics는 미리 안정적으로 고정할 수 있다. 무한 대기 없이 짧은 bounded poll을 두는 편이 spec 의도와 가장 가깝다.

**실행**: `src/toss_browser_bridge/daemon.py`에 bounded verify poll attempt/delay를 추가하고, `verify-order`가 `submitted`/`unknown` 계열 mutation에 대해 짧게 재조회한 뒤 마지막까지 미확정이면 `unknown`으로 종료하도록 조정했다. 관련 unit test와 live E2E도 갱신했다.

**결과**: verify-order는 즉시 실패/성공만 보는 one-shot이 아니라, 제한된 verify window 안에서 보수적으로 재확인하는 recovery command가 됐다.
