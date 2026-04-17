# 런타임 계약

## 지원 범위

현재 제품 계약은 아래 환경만 정식 지원한다.

- macOS desktop
- 로컬 Google Chrome 설치
- 토스증권 웹 로그인 가능 환경

아직 정식 지원하지 않는 범위:

- Linux
- Windows
- headless 세션 재생
- 공식 API 호환성 보장

## 런타임 디렉토리

기본 런타임 홈은 아래다.

```text
~/Library/Application Support/toss-browser-bridge
```

여기에 다음 파일과 디렉토리가 생긴다.

- `chrome-profile`
- `token`
- `daemon.pid`
- `daemon.log`
- `mutation-journal.jsonl`

프로젝트별로 런타임을 분리하려면 `TOSS_BRIDGE_HOME`을 쓴다.

```bash
export TOSS_BRIDGE_HOME="$HOME/Library/Application Support/financier-v2/toss-bridge"
toss-bridge health
```

## 포트 계약

기본 포트는 `42194`다.

같은 머신에서 다른 bridge instance와 분리하려면 `TOSS_BRIDGE_PORT`를 명시한다.

```bash
export TOSS_BRIDGE_PORT=42184
toss-bridge health
```

권장 규칙:

- 독립 bridge 기본값은 `42194`
- 소비 프로젝트 전용 bridge는 프로젝트 문서에서 별도 포트를 고정
- daemon 한 번 올린 뒤에는 같은 세션에서 같은 포트를 유지

## 로그인 계약

브리지는 전용 Chrome 프로필을 직접 소유한다.

첫 로그인 절차:

```bash
toss-bridge open-login
```

완료 기준:

- Chrome 창이 열리고 토스증권 계정 화면까지 진입
- 이후 `toss-bridge health`에서 `browser_attached` 또는 `attached_but_logged_out`가 반환

로그인 전 상태 해석:

- `attached_but_logged_out`: 브라우저 attach는 성공했고 웹 세션만 아직 준비되지 않음
- `browser_attached`: 웹 세션까지 준비됨

## 대표 장애와 복구

### `toss-bridge`가 PATH에 없음

```bash
uv tool dir --bin
uv tool update-shell
```

### 포트 충돌

증상:

- `port 42194 is already in use by another process`

복구:

```bash
export TOSS_BRIDGE_PORT=42184
toss-bridge health
```

또는 충돌한 다른 daemon을 정리한다.

### Chrome / Playwright prerequisite 미충족

증상:

- daemon이 기동되지 않음
- `bridge daemon did not start on 127.0.0.1:42194`

확인:

- macOS에 Google Chrome이 실제로 설치돼 있는지
- 설치형 CLI가 정상 설치됐는지
- `toss-bridge-daemon --help`가 실행되는지

복구:

```bash
toss-bridge-daemon --port 42194
```

daemon stderr를 직접 보면서 실패 지점을 확인한다.

### 로그인 안 됨

증상:

- `health`가 `attached_but_logged_out`
- `account-summary`, `positions`가 `logged_out`

복구:

```bash
toss-bridge open-login
toss-bridge health
```

## 소비 프로젝트 원칙

소비 프로젝트는 아래만 안다.

- `toss-bridge`
- `toss-bridge-daemon`
- `TOSS_BRIDGE_HOME`
- `TOSS_BRIDGE_PORT`

소비 프로젝트는 bridge repo path나 내부 Python 모듈 import를 정식 계약으로 사용하지 않는다.
