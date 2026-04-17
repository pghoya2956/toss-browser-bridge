# 소비 프로젝트 통합 계약

## 목적

소비 프로젝트는 `toss-browser-bridge`를 다시 구현하지 않고, 설치된 CLI만 호출한다.

이 문서는 그 경계를 고정한다.

## 소비 프로젝트가 알아야 하는 것

- 실행 명령: `toss-bridge`
- daemon 명령: `toss-bridge-daemon`
- 런타임 분리 변수: `TOSS_BRIDGE_HOME`
- 포트 분리 변수: `TOSS_BRIDGE_PORT`
- JSON 응답 계약

## 소비 프로젝트가 하면 안 되는 것

- bridge repo path를 코드에 하드코딩
- `uv run --project /path/to/toss-browser-bridge ...` 재호출
- `toss_browser_bridge.*` Python 모듈 직접 import
- bridge token, pid, journal을 소비 프로젝트 tracked file로 vendor
- 브라우저 attach, preview, verify 로직을 소비 프로젝트 안에서 재구현

## thin wrapper 원칙

소비 프로젝트 wrapper의 역할은 아래까지만 허용한다.

- 환경변수 주입
- CLI subprocess 호출
- JSON 파싱
- 프로젝트 고유 응답 shape로 얇게 변환

wrapper가 하면 안 되는 것:

- bridge 내부 상태를 추측해서 보정
- bridge 실패를 침묵시키고 다른 숨은 경로로 우회
- bridge repo checkout이 있어야만 동작하도록 결합

## shell 예시

```bash
export TOSS_BRIDGE_HOME="$HOME/Library/Application Support/financier-v2/toss-bridge"
export TOSS_BRIDGE_PORT=42184
toss-bridge account-summary
```

## Python subprocess 예시

```python
from __future__ import annotations

import json
import os
import subprocess


def toss_bridge(kind: str) -> dict:
    env = os.environ.copy()
    env["TOSS_BRIDGE_HOME"] = os.path.expanduser(
        "~/Library/Application Support/financier-v2/toss-bridge"
    )
    env["TOSS_BRIDGE_PORT"] = "42184"
    completed = subprocess.run(
        ["toss-bridge", kind],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    return json.loads(completed.stdout)
```

핵심은 subprocess 경계를 유지하는 것이다. 소비 프로젝트는 bridge 내부 모듈을 import하지 않는다.

## `financier-v2` 같은 소비 프로젝트의 권장 형태

- read path는 기존 skill/MCP가 설치된 `toss-bridge`를 subprocess로 호출
- 프로젝트 문서에서 `TOSS_BRIDGE_HOME`, `TOSS_BRIDGE_PORT`를 고정
- CLI JSON을 프로젝트 응답으로 얇게 번역
- bridge 기능 추가는 bridge repo에서 먼저 구현
- 사용자 경험 개선은 소비 프로젝트 skill에서 처리

## skill follow-up handoff

후속 skill task는 bridge repo가 아니라 소비 프로젝트 쪽에서 만든다.

이유:

- 사용자 경험은 프로젝트 문맥에 의존한다.
- bridge는 데이터 plane과 daemon contract를 제공하는 쪽이 맞다.
- skill은 login 유도, 복구 안내, 포트/환경 주입, 프로젝트 고유 wording을 책임진다.

후속 skill task 입력:

- installed CLI만 사용
- repo path 금지
- `TOSS_BRIDGE_HOME`, `TOSS_BRIDGE_PORT`를 project-local로 고정
- 실패 시 `health`, `open-login`, `diagnostics` 순서로 복구 안내
