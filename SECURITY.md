# Security

## Scope

이 프로젝트는 로컬 전용 read-only browser bridge를 목표로 한다.

다음 항목은 절대 issue/PR에 첨부하지 말 것:

- raw cookie
- raw storage-state
- bearer token
- raw response body
- 계좌번호 원문

## Reporting

민감정보가 이미 커밋되었거나 노출될 가능성이 있으면 공개 issue 대신 비공개 채널로 먼저 알려야 한다.

현재는 정식 security mailbox를 두지 않았으므로, 공개 issue에는 sanitized 재현 정보만 남기는 것을 원칙으로 한다.
