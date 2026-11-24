# 대시보드 기능과 운영

## 화면 구성

- 위: React Flow 세로 흐름 「리드 세션 → 작업 세션 → 결과물」. 확대·이동 없이 고정, 창 크기에 맞춰 다시 맞춤
  - 작업 중인 경로(리드 → 작업 세션 → 해당 결과물)에만 파란 점이 흐르고 카드가 빛남
  - 대기 결과물은 주황 카드·주황 점선
  - 작업 세션 카드: 진행 막대, 결과물로 이어지지 않는 남은 일(주황 ○), 붙어 있는 세션 줄(`@키`)
- 아래 3열: 할 일(남은 일 → 「완료」 구분선 → 최근 완료, 이전 완료는 접힘) | 사이클(status.json cycles 가 있을 때) + 문서 변경 + GitHub | 진행 기록
- 사이클 운영(`flow: "pipeline"` 티켓): 요청 하나를 Plan → Build → Verify 로 한 바퀴 돌 때마다 리드가 `cycles` 에 한 항목을 남긴다. 검증에서 막히면 `result: "fail"` 로 닫고 다음 사이클을 연다. 할 일은 단계가 넘어갈 때 다음 단계 작업 세션으로 옮긴다
- 헤더: 작업·결과물·에이전트 수, 「검토 대기 N」, 「다음 진행 ▶ #N …」, 「⌘/ 이동」, 「⌘O @세션」, 실시간 연결 표시
- 호버 툴팁(티켓·통합 공통, 300ms): 외부 링크는 `GET /api/link` 설명(PR 제목·상태·대상 브랜치·작성자·리뷰·체크, Slack 첫 메시지, Jira 키가 나오는 할 일·결과물·기록, 그 밖은 링크 텍스트·도메인·경로), 상태 태그·배지는 `data-hint` 문구(뜻 + 판정 근거). 링크 텍스트가 쓸모없으면 `data-label` 로 대신함

## 데이터 출처

| 출처 | 반영 |
|---|---|
| `status.json` | 1초 감시, 바뀌면 SSE 로 즉시 |
| GitHub(`gh`) | 1분 폴링. `auto.pr`·`auto.release`·PR 본문 스냅숏 |
| 진행 현황 문서 | 2초 감시. 변경 기록 표 행을 파싱해 최근 8건 |
| `docs.root` 마크다운 | 3초 확인, 스냅숏 대비 `git diff --no-index` 로 diff 기록(최근 50건). 기록마다 한 줄 요약(새로 붙은 진행 기록 #번호, 바뀐 ## 절 제목)을 남겨 「문서 변경」 패널에 항목당 한 줄(시각, 문서 이름, 요약)로 보이고, 누르면 diff |
| Claude 세션 | `~/.claude/sessions` 2초 스캔 + 대화 기록 끝부분(요청·현재 도구 단계) |
| Slack | 서버에 토큰이 없어 `claude -p`(읽기 도구 하나만 허용, `--permission-mode dontAsk`)로 가져와 10분 캐시 |

## 진행 현황 문서 변경 기록 행

대시보드가 이 형식만 읽는다. 끝 열(링크·「채팅」)이 빠지면 패널에 안 보인다.

```
| 152 | 2026-11-20 14:30 | 변경 | 내용 — 근거 | 링크 또는 채팅 |
```

- 여러 세션이 같은 문서에 쓰므로 번호는 쓰기 직전에 표의 최댓값 + 1 로 정하고, 최신 행 위에 넣는다
- 겹친 번호를 발견하면 시각 순서로 다시 매기고 보고한다

## 할 일 진행: 변경안 → 검토 → 적용

1. 「진행」(또는 ⌘O 대신 헤더 「다음 진행」) → 확인 팝업(추가 프롬프트 입력) → `orca agent launch --surface chat` 으로 작업 세션이 `streams[].worktree` 에서 열림
2. 작업 세션은 변경안만 `drafts/<id>/`(plan.md·바뀔 내용·manifest.json)에 쓰고 멈춤. manifest 가 생기면 「검토 대기」
3. 「변경 검토」 팝업: PR 본문·파일은 현재 대비 diff, 메시지는 미리보기, 기타 동작은 설명
4. 「이대로 적용」 두 번(⌘↵ 두 번) → 승인 목록만 반영하는 적용 세션이 새로 열림. 끝나면 `POST /api/items/<id>` 로 완료 처리
5. 「다시 만들기」(피드백 필수)·「변경안 폐기」 가능

리드가 직접 변경안을 만들 때는 `drafts/<id>/` 에 같은 형식으로 쓰고 `dispatches.json` 에 `{ id, mode: "draft", status: "review", itemId, stream, text, worktree, at, readyAt, sessionId: "lead" }` 를 추가한다.

### manifest.json

```json
{ "summary": "한 줄", "changes": [
  { "kind": "pr-body", "repo": "owner/repo", "number": 584, "after": "pr-body.md", "label": "PR #584 본문" },
  { "kind": "file", "path": "/절대/경로", "after": "파일이름", "label": "설명" },
  { "kind": "message", "target": "Slack 스레드 URL·받는 사람", "after": "message-1.md", "label": "설명" },
  { "kind": "note", "label": "그 밖의 동작", "text": "설명" } ] }
```

## 세션

- `@키`: 리드 `@lead`, 나머지 처음 본 순서로 `@s1…`(`session-keys.json`, 바뀌지 않음)
- 채팅 팝업: 리드 카드·세션 줄 클릭, ⌘/ → `@`, `?chat=<세션ID>`. 대화(사용자·응답·도구 단계) 2초 갱신, 입력창 자동 포커스, Enter·⌘↵ 보내기
- 보내기는 `orca orchestration send --from ticket-dashboard --to <받는 곳>`(제목 「사용자가 대시보드에서 보낸 메시지」). 화면에는 전달 틀을 걷은 본문만 보임. 서버를 띄운 세션의 Orca 신원(`ORCA_AGENT_SESSION_ID`·`ORCA_AGENT_SESSION_SPAWN_TOKEN`·`ORCA_STRUCTURED_SESSION`·`ORCA_TERMINAL_HANDLE`·`ORCA_PANE_KEY`)을 지운 환경으로 `orca`를 실행하고 보낸 사람은 `ticket-dashboard` 로 적어, 회신이 서버를 띄운 세션으로 새지 않게 함(신원 없이 `--from` 도 없으면 Orca 1.4.271 에서 `no_active_sender_terminal`, Orca 채팅 세션은 `--from` 으로 대신 지정 불가)
- 받는 곳: 대시보드가 띄운 세션은 실행 기록의 `orca_session_id`, 그 밖에는 같은 폴더에서 제목이 세션 이름과 같은 Orca 채팅. 없으면 그 폴더에 대시보드가 띄우지 않은 세션이 하나이고 채팅·Claude 터미널(`orca terminal list`의 `writable`)도 합쳐 하나일 때 그 채팅 ID나 터미널 핸들(`term_…`)
- 받는 곳을 못 찾는 세션은 읽기 전용
- 자동 회수: 대시보드가 띄운 세션만. 작업 중이 아니고 적용 세션은 할 일 완료 뒤 1분, 변경안 세션은 작성 끝 뒤 3분이면 Claude 프로세스 SIGTERM. 채팅 팝업 「이 세션 유지」로 제외. Orca 채팅 탭은 CLI 로 못 닫아 남음

## 단축키

| 키 | 동작 |
|---|---|
| ⌘/ (Ctrl+/) | 이동 창: `@` 세션 대화, `#` 할 일 팝업 |
| ⌘O (Ctrl+O) | 프롬프트 창: `@키 내용` → 해당 세션에 전송 |
| ⌘↵ | 열린 팝업의 주 동작(변경안 만들기·적용·완료 표시·보내기) |

Orca 앱이 ⌘ 조합을 먼저 가져가면 Ctrl 조합이나 헤더 버튼을 쓴다.

## API (127.0.0.1 전용, POST 는 `content-type: application/json` 필수·다른 출처 거부)

| 메서드·경로 | 용도 |
|---|---|
| `GET /api/state`, `GET /api/events`(SSE) | 전체 상태 |
| `POST /api/items/<id>` `{done}` | 할 일 완료·취소 |
| `POST /api/agents/focus` `{name, stream, item, doing}` | 리드가 지금 하는 일을 직접 알림(새 요청이 오면 자동 해제) |
| `POST /api/dispatch` `{itemId, extra, previous?}` | 변경안 작업 세션 실행 |
| `GET /api/dispatch/<id>/review`, `POST …/apply` `{extra}`, `POST …/cancel` | 검토·적용·폐기 |
| `GET /api/preview?item=<id>`, `POST /api/preview/refresh` | PR·Slack 프리뷰 |
| `GET /api/link?url=<링크>` | 링크 호버 설명. PR 은 폴링 상태 재사용, 없으면 `gh pr view`(URL 의 owner/repo/번호를 정규식 검증 후) 2분 캐시. 다른 출처·`sec-fetch-site` 가 same-origin 아니면 gh 호출 안 함 |
| `GET /api/docs/<id>` | 문서 diff |
| `GET /api/sessions/<id>/messages`, `POST …/send` `{text}`, `POST …/keep` `{keep}` | 세션 대화·전송·자동 회수 제외 |
| `POST /api/refresh` | GitHub·진행 기록 즉시 다시 확인 |

## 통합 대시보드(hub)

- 위치 `~/orca/dashboards/hub/`(server.mjs·index.html·start.sh·stop.sh, 티켓 코드 `ticket/`), 포트 4000(`PORT` 환경 변수로 변경)
- 서버는 이 프로세스 하나. 3초마다 형제 폴더의 `status.json`(key·port 있는 것)을 찾아, 처음 본 티켓은 `ticket/server.mjs?dir=<티켓 폴더>` 로 모듈을 따로 불러 그 티켓 포트에서 받는다. 상태는 모듈 안에서 바로 읽어 요약을 SSE 로 내보냄
- 티켓마다 포트를 따로 쓰는 이유: 화면이 한 출처에 몰리면 SSE 가 브라우저의 출처당 동시 연결 6개 제한에 걸린다
- 포트를 못 잡으면 카드에 이유를 보이고 3초마다 다시 시도. 티켓 key·port 를 바꾸거나 코드를 고치면 `./stop.sh && ./start.sh`(모든 티켓이 함께 다시 뜸)
- 한 티켓의 예외로 프로세스가 내려가지 않게 `uncaughtException`·`unhandledRejection` 은 기록만 남김
- API: `GET /api/tickets`, `GET /api/events`, `GET /api/link?url=(티켓 서버와 같은 링크 설명, 모든 티켓 상태·`previews/` 에서 찾음)
- 오케스트레이션 채팅: `hub.json` `{ "orchestrator": { "sessionId", "name", "cwd", "orcaSessionId" } }` 로 대상 세션 지정. `orcaSessionId` 가 있으면 `orca agent list` 의 그 행으로 켜짐·작업 중(`working`)을 판정(5초 캐시, 행이 없으면 꺼짐)하고, 대화는 `sessionId` 의 세션 기록에서 읽는다. Orca 채팅은 쉬는 동안 claude 프로세스가 내려가 세션 등록 파일이 없기 때문. `orcaSessionId` 가 없으면 살아 있는 세션 등록 파일에서 `sessionId` → `name` → `cwd` 순으로 찾음. 보내기는 `orca orchestration send`(제목 「사용자가 대시보드에서 보낸 메시지」)로 그 Orca 채팅에 전달. API `GET /api/orchestrator/messages`, `POST /api/orchestrator/send {text}`
- 티켓 화면은 iframe. 티켓 대시보드는 iframe 안에서 ⌥/⌘/Ctrl+숫자·⌥↑↓를 `postMessage({type:'hub-key'})` 로 부모에 넘기고, hub 는 티켓 출처에서 온 메시지만 받음

## 데이터 파일(대시보드 폴더)

`status.json`(작업 모델) · `dispatches.json`(실행 기록) · `session-keys.json` · `leads.json`(마지막으로 본 리드 세션, 쉬는 Orca 채팅 리드 표시용) · `doc-history.json` · `drafts/` · `previews/`(Slack 캐시) · `.snapshots/`(문서 기준본). 서버 기록은 `hub/server.log` 하나. 통합 전 티켓 서버 코드는 각 폴더 `.legacy/` 에 옮겨 둠

## 문제 해결

- 화면이 안 바뀜: `curl -s 127.0.0.1:<port>/api/state` 로 서버 확인, `~/orca/dashboards/hub/server.log` 끝 확인, hub 에서 `./stop.sh && ./start.sh`
- 진행 기록이 안 보임: 행 끝 `| … |` 열 누락 여부
- Slack 프리뷰 실패: `claude -p` 가 Slack 커넥터를 못 쓰는 상태. 프리뷰의 「다시 가져오기」 오류 문구 확인
- 헤드리스 Chrome 캡처는 SSE 때문에 멈춤 → Orca 임시 탭(`orca tab create` → `orca screenshot` → `orca tab close`)으로 확인
