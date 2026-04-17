# 설치 가이드

## 원칙

`toss-browser-bridge`의 canonical interface는 설치된 CLI다.

- 실행 계약: `toss-bridge ...`
- daemon 실행 계약: `toss-bridge-daemon ...`
- 정식 경로에서는 repo checkout이나 `uv run --project ...`를 전제로 두지 않는다.

## 권장 설치 순서

### 릴리스 소비 경로

가장 재현성이 높은 경로는 wheel artifact 설치다.

```bash
uv build --wheel
uv tool install --force dist/toss_browser_bridge-<version>-py3-none-any.whl
toss-bridge --help
```

특징:

- 설치 시점의 artifact가 고정된다.
- 소비 프로젝트나 운영 문서에 버전/파일명을 명시하기 쉽다.
- repo working tree 변경이 자동 반영되지 않는다.

### 태그/커밋 기반 경로

artifact 저장소를 따로 두지 않을 때는 git source install을 쓴다.

```bash
uv tool install --force "git+ssh://git@github.com/OWNER/toss-browser-bridge.git@v<version>"
toss-bridge --help
```

특징:

- 태그나 커밋으로 source를 고정할 수 있다.
- install 대상은 working tree가 아니라 지정한 git revision이다.

### 단일 사용자 로컬 경로

같은 머신에서 직접 repo를 관리하면서 설치형 CLI만 쓰고 싶다면 local path install을 쓴다.

```bash
uv tool install --force /path/to/toss-browser-bridge
toss-bridge --help
```

특징:

- 설치는 간단하다.
- 재설치 시 현재 checkout 상태가 반영된다.
- 배포/재현성보다는 개인 운영에 맞다.

### bridge 개발 경로

bridge 자체를 계속 수정하는 동안에는 editable install이 가장 빠르다.

```bash
uv tool install --force --editable /path/to/toss-browser-bridge
toss-bridge --help
```

특징:

- 소스 변경이 재설치 없이 즉시 반영된다.
- 설치 후 실행은 checkout-free지만, 설치 자체는 source path에 묶인다.
- 소비 프로젝트의 정식 배포 경로로는 권장하지 않는다.

### 프로젝트별 설치 경로

소비 프로젝트의 전용 venv에 고정해서 쓰려면 프로젝트 의존성으로 추가한다.

```bash
uv add --editable /path/to/toss-browser-bridge
uv run toss-bridge --help
```

wheel artifact를 쓰는 경우에도 같은 방식으로 추가할 수 있다.

```bash
uv add /path/to/dist/toss_browser_bridge-<version>-py3-none-any.whl
uv run toss-bridge --help
```

특징:

- 프로젝트별로 버전을 분리할 수 있다.
- `uv run toss-bridge ...`로 프로젝트 환경 안에서 실행된다.
- 소비 프로젝트가 bridge repo를 직접 import해서는 안 된다.

## 설치 후 smoke

설치 직후 최소 확인 세트는 아래 순서로 본다.

```bash
toss-bridge --help
toss-bridge-daemon --help
toss-bridge health
```

`health` 확인 기준:

- daemon bootstrap이 실패하지 않아야 한다.
- 로그인 전이라면 `attached_but_logged_out`도 정상이다.
- 포트 충돌이 있으면 `TOSS_BRIDGE_PORT`를 분리한다.

## 업데이트 정책

### wheel 경로

버전이 바뀐 wheel로 다시 설치한다.

```bash
uv tool install --force dist/toss_browser_bridge-<version>-py3-none-any.whl
```

### git source 경로

같은 source track이면 upgrade를 쓸 수 있다.

```bash
uv tool upgrade toss-browser-bridge
```

새 태그나 다른 commit으로 바꿀 때는 install 명령을 다시 사용한다.

```bash
uv tool install --force "git+ssh://git@github.com/OWNER/toss-browser-bridge.git@v<version>"
```

### local path / editable 경로

source checkout을 바꾼 뒤 install 명령을 다시 실행하거나, editable이면 바로 반영된다.

```bash
uv tool install --force /path/to/toss-browser-bridge
```

## PATH 확인

`uv tool install` 뒤에 `toss-bridge`가 바로 안 보이면 tool bin 경로를 확인한다.

```bash
uv tool dir --bin
uv tool update-shell
```

## 실측한 smoke 범위

2026-04-17 KST 기준으로 아래 경로를 실측했다.

- `uv tool install --force /path/to/toss-browser-bridge`
- `uv tool install --force --editable /path/to/toss-browser-bridge`
- `uv build --wheel` 후 `uv tool install --force <wheel>`
- `uv tool install --force "git+file:///.../toss-browser-bridge"`
- 임시 프로젝트에서 `uv add --editable /path/to/toss-browser-bridge`

모든 경로에서 `toss-bridge --help` 또는 `uv run toss-bridge --help`까지 확인했다.
