# Toss Browser Bridge

토스증권 웹에 로그인된 **전용 Chrome 프로필**을 브리지가 직접 소유하고, 브라우저 컨텍스트 안에서 read-only 조회를 수행하는 로컬 daemon/CLI 프로젝트다.

공식 토스증권 API 프로젝트가 아니다. browser-attached companion 성격의 **비공식 read-only 도구**다.

## 현재 지원 명령

- `health`
- `open-login`
- `account-summary`
- `positions`
- `completed-orders`
- `quote`
- `reconnect`
- `shutdown`
- `diagnostics`

## quickstart

```bash
uv run --project . toss-bridge health
uv run --project . toss-bridge open-login
uv run --project . toss-bridge account-summary
uv run --project . --extra dev pytest
sh scripts/scrub-check.sh
```

런타임 상태는 기본적으로 아래 경로를 사용한다.

- `~/Library/Application Support/toss-browser-bridge/chrome-profile`
- `~/Library/Application Support/toss-browser-bridge/token`
- `~/Library/Application Support/toss-browser-bridge/daemon.pid`
- `~/Library/Application Support/toss-browser-bridge/daemon.log`

`TOSS_BRIDGE_HOME` 환경변수로 override 가능하다.
기본 listen 포트는 `42194`이며, `TOSS_BRIDGE_PORT`로 override 가능하다.

기존 `financier-v2` 내장 bridge와 같은 머신에서 함께 돌릴 때는 포트를 분리해야 한다.

## 예시 출력

- logged out capability matrix: [examples/health-attached-but-logged-out.json](examples/health-attached-but-logged-out.json)

## 현재 범위

- read-only only
- browser-attached only
- Toss Securities web dependency

## 현재 비범위

- 주문/정정/취소/환전
- 공식 API 안정성 보장
- 헤드리스 세션 재생

## known limitations

- 토스증권 웹 구조나 내부 endpoint가 바뀌면 깨질 수 있다.
- 전용 Chrome 프로필에 직접 로그인해야 한다.
- `health`가 `attached_but_logged_out`일 때는 브라우저 연결만 성공한 상태다.
