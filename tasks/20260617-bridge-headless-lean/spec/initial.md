# toss-browser-bridge Chrome 렌더링 리소스 절감 (headless + lean) 스펙

## 개요

toss-browser-bridge daemon이 띄우는 Chrome은 토스 화면을 DOM으로 스크레이프하지 않는다. 데이터는 페이지 안에서 `fetch(url, {credentials:"include"})`로 토스 cert API를 직접 호출해 가져오고(`src/toss_browser_bridge/daemon.py:822` `page.evaluate(...)` → `:864` `fetch`), 브라우저는 ① 로그인 세션 보관(persistent profile), ② 토스 JS 요청 서명용 `App-Version` 추출 호스트(`daemon.py:834~852`) 역할만 한다. 즉 GPU 컴포지터·이미지 디코드·1440x960 창 전체가 순수 오버헤드다.

현재 `start_browser()`는 `launch_persistent_context`를 `headless=False`, `viewport`, `--window-size` 하드코딩으로 호출해 env로 바꿀 수 없다(`daemon.py:434~440`). 이 스펙은 기존 `_env_flag` + `TOSS_BRIDGE_ENABLE_FINAL_SUBMIT` 패턴을 재사용해 두 개의 opt-in env 토글(`TOSS_BRIDGE_HEADLESS`, `TOSS_BRIDGE_LEAN`)을 추가하고, 토글 미설정 시 현행 동작과 100% 동일(회귀 없음)하게 만든다.

## 목적

- Chrome 렌더링 리소스(RSS 메모리, GPU/컴포지터, 이미지 디코드) 절감.
- 데이터 취득 경로(in-page fetch)는 그대로 두어 기능 회귀 0.
- 설정은 코드 변경 없이 env 토글로. 기본값은 현행 headed 동작 유지(하위호환).

### 성공 기준

- 토글 미설정 시 launch 인자가 현행과 바이트 단위로 동일(회귀 테스트).
- `TOSS_BRIDGE_HEADLESS=on`에서 daemon 기동 → `account-summary` / `positions` / `quote` / `completed` 조회가 headed와 동일하게 성공(실측 acceptance, 추측 금지).
- `TOSS_BRIDGE_LEAN=on`에서 이미지 비활성화·GPU 비활성화에도 동일 조회 성공.
- headless+lean 전/후 Chrome RSS 메모리 비교 수치를 acceptance에 포함.

### 대상 사용자

- bridge 운영자(financier-v2 등 소비자). 백그라운드 데이터 조회 daemon을 상시 띄워두는 환경에서 메모리·전력 절감이 필요한 사람.

## 범위

### In Scope

- `start_browser()` launch 인자를 env 토글 기반으로 빌드(`headless`, lean args 셋).
- 토글 파싱 헬퍼(`_env_flag` 재사용) + lean args 빌더 함수 + 단위테스트.
- 기본값(현행 headed + 최소 flag) 하위호환 보장.
- headless/lean 조회경로 실측 검증 + RSS 측정 + 문서화.

### Out of Scope

- headless에서 세션 만료 시 자동 headed 재로그인 fallback(코드 자동 전환). → 열린 질문.
- 주문(place) 경로를 headless로 기본 전환(조회 검증 후 확대 — 이번엔 검증/문서까지만, 기본 전환은 보류).
- viewport/window-size를 env로 외부화(현재 needs 없음).
- 봇 탐지 회피용 stealth 플러그인·fingerprint 위장.
- financier-v2 측 CLAUDE.md 최소버전·env 반영(소비자 레포 작업 — 영향 분석에만 언급).

## 설계

### API / 인터페이스 (env 토글)

기존 패턴(`daemon.py:386` `_env_flag`, `:60` `FINAL_SUBMIT_ENABLE_ENV`)을 그대로 따른다. `_env_flag`는 `{"1","true","yes","on"}`를 truthy로 보고 그 외(미설정·오타·`off`·`0`)는 전부 false로 떨어진다 → 잘못된 env 값은 안전하게 "비활성"으로 처리됨.

| env 변수 | 기본값 | 의미 | 비고 |
|----------|--------|------|------|
| `TOSS_BRIDGE_HEADLESS` | off(미설정) | on이면 `headless=True`(Playwright 신형 headless) | 기본 off = 현행 headed, 하위호환 |
| `TOSS_BRIDGE_LEAN` | off(미설정) | on이면 경량 Chrome args 셋 추가 | 데이터 경로가 fetch라 이미지 OFF 안전, 권장 on |

상수는 `FINAL_SUBMIT_ENABLE_ENV` 인근(`daemon.py:60~61`)에 나란히 추가한다.

```python
HEADLESS_ENV = "TOSS_BRIDGE_HEADLESS"
LEAN_ENV = "TOSS_BRIDGE_LEAN"
```

### 컴포넌트 구조 (launch 호출부 변경)

새 순수 함수 두 개를 module-level(테스트 용이)에 추가한다.

```python
# daemon.py — _env_flag(:386) 근처

LEAN_CHROME_ARGS = [
    "--disable-gpu",
    "--disable-software-rasterizer",
    "--blink-settings=imagesEnabled=false",  # fetch 경로라 안전
    "--disable-dev-shm-usage",
    "--disable-extensions",
    "--disable-background-networking",
    "--mute-audio",
    "--js-flags=--max-old-space-size=512",
]

def resolve_browser_launch_options() -> dict:
    """env 토글을 읽어 launch_persistent_context kwargs를 만든다.
    토글 미설정 시 현행과 동일한 인자를 반환(회귀 0)."""
    headless = _env_flag(HEADLESS_ENV)
    lean = _env_flag(LEAN_ENV)
    args = ["--window-size=1440,960"]          # 현행 baseline 유지
    if lean:
        args = args + LEAN_CHROME_ARGS         # 중복 제거 불필요(겹침 없음)
    return {
        "channel": "chrome",
        "headless": headless,
        "viewport": {"width": 1440, "height": 960},
        "args": args,
    }
```

`start_browser()`(`daemon.py:434~440`)는 다음으로 바뀐다:

```python
self._context = self._playwright.chromium.launch_persistent_context(
    str(PROFILE_DIR),
    **resolve_browser_launch_options(),
)
```

토글 둘 다 off일 때 `resolve_browser_launch_options()`는
`{channel:"chrome", headless:False, viewport:{1440,960}, args:["--window-size=1440,960"]}`
즉 현행 `:436~439`과 동일 → 회귀 0(회귀 단위테스트로 고정).

운용 모델(문서화 대상, 코드 자동화 아님): **headed 1회 로그인 → persistent profile(`bridge_lib.py:40` `PROFILE_DIR`)에 세션 잔존 → 이후 `TOSS_BRIDGE_HEADLESS=on`으로 daemon 재기동**. daemon은 `subprocess.Popen`으로 `python -m toss_browser_bridge.daemon run`을 띄우는 장수 프로세스(`cli.py:35~64`)이고, 브라우저는 첫 조회 시 `start_browser()`에서 lazy 기동된다. profile은 daemon 재기동·shutdown과 무관하게 디스크에 남으므로, headed에서 한 번 로그인하면 headless 재기동에서 쿠키를 재사용한다.

## 구현 계획

### Phase 0 — 토글 헬퍼 / args 빌더 + 단위테스트

- [ ] `HEADLESS_ENV`, `LEAN_ENV` 상수 추가(`daemon.py:60~61` 인근).
- [ ] `LEAN_CHROME_ARGS` 리스트 + `resolve_browser_launch_options()` 순수 함수 추가(`_env_flag` 인근).
- [ ] 단위테스트(`tests/` 신규 또는 `test_daemon.py` 확장, `monkeypatch.setenv` 패턴 — `test_submit_runtime.py:684` 참조):
  - 토글 미설정 → 반환 kwargs가 현행 4-튜플과 정확히 일치(회귀 고정).
  - `TOSS_BRIDGE_HEADLESS=on` → `headless=True`, args에 lean 없음.
  - `TOSS_BRIDGE_LEAN=on` → args에 `--blink-settings=imagesEnabled=false` 등 포함, `headless=False` 유지.
  - 둘 다 on → headless True + lean args.
  - 잘못된 값(`maybe`, ``, `0`, `OFF`) → false 처리(현행 동작).
- [ ] 검증: `uv run pytest tests/ -k "launch or headless or lean"` green. 기존 테스트 회귀 없음.

### Phase 1 — launch 적용 + 하위호환

- [ ] `start_browser()`(`daemon.py:434~440`)를 `**resolve_browser_launch_options()`로 교체.
- [ ] 토글 미설정 daemon 기동 → 현행과 동일하게 headed 창 뜨고 `account-summary`/`positions` 성공(스모크).
- [ ] 검증: 전체 `uv run pytest` green. 하위호환 회귀 0.

### Phase 2 — headless 조회경로 실측 + RSS 측정 + 문서

- [ ] headed 1회 로그인으로 profile 세션 확보.
- [ ] `TOSS_BRIDGE_HEADLESS=on TOSS_BRIDGE_LEAN=on`으로 daemon 재기동 → `health`에서 `account_summary_ready`/`positions_ready`/`quote_ready`/`completed_orders_ready` true 실측(`daemon.py:340~353`).
- [ ] `account-summary` / `positions` / `quote` / `completed` 4종 실호출 성공 acceptance(추측 금지).
- [ ] Chrome RSS 메모리: headed vs headless vs headless+lean 3종 측정(`ps -o rss= -p <chrome pid>` 또는 동등) → 수치 기록.
- [ ] README/docs에 운용 모델(headed 1회 로그인 → headless 재기동 하이브리드) + env 토글 표 + 봇탐지 점진 확대(조회 검증 후 주문) 문서화.
- [ ] (선택) place 경로는 headless 실측 후 별도 판단 — 이번엔 기본 전환 안 함.

## 영향 분석

| 영역 | 변경 내용 | 위험도 | 완화 방안 |
|------|-----------|--------|-----------|
| launch 인자 (`daemon.py:434~440`) | 하드코딩 → `resolve_browser_launch_options()` | 낮음 | 토글 미설정 시 동일 인자 반환을 회귀 단위테스트로 고정 |
| 봇 탐지 | headless=new는 headed보다 fingerprint 차이 존재(navigator.webdriver 등). 토스가 차단 가능 | 중간 | 데이터는 로그인 쿠키 기반 fetch라 표면적은 작음. **조회 4종부터 실측 acceptance 후 주문 확대**. 차단 감지 시 headed로 즉시 롤백(env off) |
| 로그인 / 세션 갱신 인터랙션 | headless 단독은 최초 로그인·2FA·인증서 입력 UI 불가 | 중간 | headed 1회 로그인 → profile 잔존 → headless 재기동 하이브리드 문서화. 자동 fallback은 범위 밖(열린 질문) |
| 세션 만료 시 동작 | headless에서 `/signin` 리다이렉트(`is_logged_out` `daemon.py:380`) → 조회 실패하지만 자동 복구 불가 | 중간 | health가 `attached_but_logged_out` 반환(`daemon.py:360,363`). 운영자가 headed 재기동해 재로그인하도록 문서화 + 엣지 테스트 |
| 주문 fingerprint | lean의 이미지 OFF·GPU OFF가 토스 주문 prerequisite/create 요청서명(App-Version `:834~852`)에 영향? | 낮음 | App-Version은 main-* 청크를 fetch해 정규식 추출 — 렌더링/이미지 무관. lean에서도 동일 동작 검증 |
| 이미지 비활성화 | `--blink-settings=imagesEnabled=false` | 낮음 | 데이터 경로가 fetch(JSON)라 DOM 이미지 불필요. App-Version 추출은 script src fetch라 영향 없음 — Phase 2에서 실증 |
| `--disable-dev-shm-usage` / `--js-flags=max-old-space-size=512` | 메모리 압박 환경 안정화 + heap 상한 | 낮음 | 512MB heap이 다건 fetch에 충분한지 Phase 2 조회로 확인. 부족 징후 시 상향 |
| 소비자 (financier-v2) | bridge를 `TOSS_BRIDGE_PORT=42184` 격리 env로 사용 | 낮음(레포 밖) | 최소버전·신규 env 토글을 financier-v2 CLAUDE.md MCP 섹션에 반영하는 **후속 작업 필요**(이 레포 범위 밖, 여기 명시만) |
| Playwright 버전 | lock = 1.58.0(`uv.lock:80`), pyproject floor `>=1.53.0`(`pyproject.toml:12`) | 낮음 | 1.53+에서 신형 headless 기본. 1.60.0 가정은 lock과 불일치 — 1.58.0 기준으로 검증 |

## 테스트 계획

### 단위

- 토글 파싱: `TOSS_BRIDGE_HEADLESS`/`TOSS_BRIDGE_LEAN` 각각 `on/1/true/yes` truthy, `off/0/""/오타` falsy(`_env_flag` 위임).
- args 빌더: lean on 시 8개 lean flag 포함 + baseline `--window-size` 유지, lean off 시 baseline만.
- 기본값 회귀: 두 토글 미설정 → `{channel,headless:False,viewport,args:["--window-size=1440,960"]}` 정확 일치.
- `monkeypatch.setenv` 사용(`test_submit_runtime.py:684,694` 패턴 재사용).

### 통합

- headed(토글 off) daemon 기동 → `account-summary`/`positions` 성공(현행 회귀).
- headless on daemon 기동(profile에 세션 존재 전제) → `account-summary`/`positions`/`quote`/`completed` 4종 성공.
- headless+lean on → 위 4종 + 이미지 OFF 상태에서도 동일 성공 + RSS 절감 수치 확보.
- `health` capabilities(`daemon.py:340~353`)가 headed/headless에서 동일 true 셋.

### 엣지 케이스

- 세션 만료 상태에서 headless 기동 → `health` `session_state="attached_but_logged_out"`(`daemon.py:360`), 조회 실패가 명확히 surfaced되는지(자동 로그인 시도 안 함).
- 잘못된 env 값(`TOSS_BRIDGE_HEADLESS=maybe`) → false 처리, headed 동작.
- lean on에서 주문 preview(App-Version 추출 경로) 정상 — 이미지 OFF가 서명에 영향 없음 확인.
- 토글을 켠 채 profile 미로그인 첫 기동(headless) → 로그인 불가로 조회 실패, headed 재기동 안내 동작.

## 결정 사항

- 기본값은 현행 동작(headed + 최소 flag) 유지. headless·lean은 opt-in. (합의됨)
- `TOSS_BRIDGE_LEAN`은 데이터 경로가 fetch라 이미지 비활성화가 안전 → 기본 off지만 권장 on. (합의됨)
- headless 단독으로는 최초 로그인/세션갱신 불가(인증서/2FA는 headed 창 필요). 운용 모델 = "headed 1회 로그인 → 세션 profile 잔존 → headless 재기동" 하이브리드를 문서화. 코드 자동 fallback은 이번 범위 밖(열린 질문). (합의됨)
- 봇 탐지 리스크: 조회 경로(account-summary/positions/quote/completed)부터 headless 실측 검증 후 주문(place) 확대. 추측 금지, 실제 호출로 acceptance. (합의됨)
- acceptance에 headless/lean 전후 Chrome RSS 메모리 비교 수치 포함. (합의됨)

## 열린 질문

| ID | 질문 | 시도한 자체 답변 | 다음 단계 처리 권장 |
|----|------|-----------------|---------------------|
| OQ-1 | headless에서 세션 만료 감지 시 headed로 자동 fallback(임시 창 띄워 재로그인 유도)을 코드에 넣을까? | 현재는 범위 밖. health가 `attached_but_logged_out`로 명확히 표면화하므로 운영자 수동 재기동으로 충분. 자동화는 headed 창 spawn이 필요해 별도 설계 | 후속 phase. 이번 스펙은 문서화 안내까지만 |
| OQ-2 | 토스가 headless=new를 봇으로 차단할 가능성? | fetch는 로그인 쿠키 기반이라 표면적 작지만 실측 전엔 단정 불가 | Phase 2 조회 4종 실측이 사실상 이 질문의 acceptance. 차단 시 OQ-3로 |
| OQ-3 | 차단 시 stealth(navigator.webdriver 패치 등) 도입? | 이번 스펙 명시적 out of scope | 차단이 실측되면 별도 스펙 |
| OQ-4 | `--js-flags=--max-old-space-size=512` 512MB가 다건 fetch에 충분? | App-Version용 main 청크 fetch + JSON 파싱 정도라 충분 추정 | Phase 2 실측에서 OOM 징후 모니터, 부족 시 상향 |
| OQ-5 | place(주문) 경로 headless 기본 전환 시점? | 조회 검증 후 별도 판단 — 이번엔 검증/문서까지만 | 조회 acceptance 안정화 후 별 task |
| OQ-6 | financier-v2 CLAUDE.md MCP 섹션에 최소버전·신규 env 반영은 누가? | 소비자 레포 작업이라 이 레포 범위 밖 | 메인 세션이 financier-v2에서 별도 후속 |

## 보류

- Context의 "Playwright 1.60.0" 전제는 실측 lock과 불일치(`uv.lock:80` 1.58.0, `pyproject.toml:12` `>=1.53.0`). 신형 headless(`--headless=new` 계열)는 1.53+에서 기본 적용이라 결론(headless 탐지 감소)은 유지되나, 검증·문서의 버전 표기는 1.58.0 기준으로 한다.
- Context의 라인 번호(설치본 0.4.1 daemon.py:434~439, 839, 864, 831)는 레포 소스에서 재검증 완료 — launch 호출 `:434~440`, fetch `:864`, App-Version `:834~852`, in-page fetch evaluate `:822`로 일치(미세 오프셋 보정 반영).
