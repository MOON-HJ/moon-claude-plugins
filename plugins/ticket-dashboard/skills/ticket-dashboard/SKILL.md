---
name: ticket-dashboard
description: 티켓 하나의 진행 상황을 실시간으로 보고 조작하는 로컬 대시보드를 띄우고 운영한다. React Flow 세로 흐름(리드 세션 → 작업 세션 → 결과물)에 GitHub PR·배포 태그, 진행 현황 문서 변경 기록·마크다운 diff, Claude 세션 상태(작업 중 흐름 애니메이션)를 실시간 반영하고, 할 일마다 변경안 → 검토(diff) → 적용 흐름으로 작업 세션을 띄우며, 세션 채팅·@/# 이동·⌘O 프롬프트·자동 세션 회수를 지원한다. 여러 티켓 대시보드를 사이드바 탭(⌥1~9)으로 묶은 통합 대시보드(전체 현황)도 띄운다. 「대시보드 만들어줘」 「진행 대시보드 띄워줘」 「실시간으로 어디까지 됐는지 보고 싶어」 「리액트 플로우로 진행 현황 보여줘(계속 갱신되게)」 「<티켓> 대시보드 서버 구성」 「대시보드 템플릿 업데이트」 「통합 대시보드」 「여러 티켓 대시보드 한 화면에」 「/ticket-dashboard <티켓>」 등에 사용. 매니저 세션으로 티켓을 진행 중일 때 특히 쓴다. 한 번 보고 끝나는 그림은 orca-chat-visuals, 지표·데이터 대시보드는 Artifact 대시보드.
---

# Ticket Dashboard — 티켓 진행 실시간 대시보드

티켓 하나를 맡은 리드 세션이 자기 작업과 작업 세션들을 한 화면에서 보고, 사용자가 그 화면에서 다음 일을 고르고 승인하게 한다. 원형은 `~/orca/dashboards/<키 소문자>` 에 만든 티켓 대시보드.

## 상수

| 항목 | 값 |
|---|---|
| 티켓 코드 | `assets/template/`(server.mjs·index.html, 의존성 없음 — Node·gh·orca CLI만). 통합 대시보드 설치 때 `hub/ticket/` 에 한 벌 복사 |
| 티켓 데이터 | `~/orca/dashboards/<키 소문자>/`(status.json·실행 기록만, 코드 없음) |
| 포트 | 4000 + 티켓 번호 % 1000 (PROJ-383 → 4383), 127.0.0.1 전용 |
| 서버 | 통합 대시보드(`assets/hub/` → `~/orca/dashboards/hub/`) 프로세스 하나. 허브는 포트 4000, 같은 부모 폴더의 티켓 폴더를 3초마다 찾아 각 티켓을 자기 포트에서 띄움 |
| 작업 모델 형식 | `references/status-schema.md`, 실제 예시 `references/example-status.json` |
| 기능·API·운영 | `references/operations.md` |

## 1. 입력 정리

리드 세션의 맥락(진행 현황 문서, Jira, PR)에서 먼저 채우고, 모르는 것만 묻는다.

- 티켓 키·제목, Jira 링크 앞부분
- 리드 워크트리 경로와 리드 세션 이름(`~/.claude/sessions/*.json` 의 `cwd` 가 리드 워크트리인 항목의 `name`)
- 진행 현황 문서 경로(변경 기록 표가 있는 md)
- 기본 GitHub 레포, 레포별 워커 워크트리

## 2. 설치

```bash
node "${CLAUDE_SKILL_DIR}/scripts/init.mjs" \
  --key <키> --title "<키> <제목>" --repo <owner/repo> \
  --lead-cwd "<리드 워크트리>" --lead-name <리드 세션 이름> \
  --progress-doc "<진행 현황 md>"
```

- 폴더가 없으면 만들고 `status.json` 뼈대를 쓴다. 있으면 그대로 둔다. 통합 대시보드가 3초 안에 찾아 띄운다(따로 실행하지 않음)
- 출력의 `portBusy` 가 true 이고 다른 프로그램이 그 포트를 쓰면 `status.json` 의 `port` 를 바꾸고 통합 대시보드를 재시작한다
- 코드(template·hub) 업데이트는 `init.mjs --hub` 후 `~/orca/dashboards/hub` 에서 `./stop.sh && ./start.sh`. 모든 티켓이 함께 다시 뜬다

## 3. 작업 모델링 (status.json)

`references/status-schema.md` 를 읽고 진행 현황 문서를 근거로 채운다. 화면이 쓸모 있으려면 모델이 실제 일을 그대로 반영해야 하므로, 완료 여부는 문서·PR 상태로 확인되는 것만 `done` 으로 둔다.

- **작업 세션(streams)**: 레포·도메인 단위 5~7개(예: 앱, 디자인 시스템, 검증, 확인·문서, 테스트 환경, 곁가지). `worktree` 는 그 일을 할 폴더
- **할 일(items)**: 명사형 짧은 문장, `no` 는 1부터 고정 번호. 남은 일에는 `who`, 결과물을 만드는 일에는 `out`, PR·Slack 근거가 있으면 `refs`, GitHub 로 판정되는 일에는 `auto`
- **결과물(outputs)**: PR(`auto.pr`), 배포(`auto.release`), 리포트·문서·이미지·환경. 아직 안 나온 것은 대기(주황)로 보인다
- **감시 폴더(agents.watch)**: 리드 워크트리(`role: lead`, `name`)와 워커 워크트리(`stream` 지정)
- **단계 흐름(기본)**: `flow: "pipeline"` 과 `stages`(Initial=리드 → Plan → Build → Verify → Deploy, Verify 는 Plan 으로 루프)를 두고, 할 일마다 `stage` 를 단다. Plan → Build → Verify 한 바퀴마다 `cycles` 에 통과·실패를 남긴다(형식은 status-schema.md)

## 4. 실행·열기

```bash
curl -s 127.0.0.1:<port>/api/state | head -c 300   # 응답 확인
orca tab create --url http://127.0.0.1:<port>/ --json   # Orca 브라우저 탭으로 열기
```

재부팅하면 `~/orca/dashboards/hub/start.sh` 하나만 실행한다(티켓 폴더에는 start.sh 가 없다). 화면 확인은 사용자가 보고 있는 탭을 새로고침하지 말고 임시 탭을 열어 캡처한 뒤 닫는다(사용자가 그 탭에서 작업 중일 수 있다).

## 5. 통합 대시보드

티켓이 둘 이상이거나 사용자가 한 화면에서 여러 티켓을 보려 할 때 쓴다.

```bash
node "${CLAUDE_SKILL_DIR}/scripts/init.mjs" --hub   # 설치·업데이트
cd ~/orca/dashboards/hub && ./start.sh                          # http://127.0.0.1:4000/
```

- 사이드바: 전체 현황(⌥0)과 티켓 탭(⌥1~9). 탭마다 진행률·남은 일·검토 대기·작업 중 세션 수
- 전체 현황: 티켓별 진행률, 작업 세션별 막대, 검토 대기, 작업 중 세션, 남은 일, PR 상태, 마지막 기록
- 티켓 탭은 각 티켓 대시보드를 그대로 띄운다(한 번 연 탭은 상태 유지). 띄우지 못한 티켓은 카드에 이유를 보이고 3초마다 다시 시도
- 단축키: ⌥/⌘/Ctrl+숫자로 탭 이동, ⌥↑↓로 앞뒤. 티켓 화면 안에서 눌러도 동작
- 순서는 키 이름순. 바꾸려면 티켓 `status.json` 에 `hubOrder`(작을수록 위)
- 전체 현황 오른쪽 「오케스트레이션」 채팅: 최상위(오케스트레이터) 세션의 대화를 보고 메시지를 보낸다. 대상은 `~/orca/dashboards/hub/hub.json` 의 `orchestrator`. Orca 채팅이면 `orcaSessionId`(켜짐·작업 중 판정, 전송)와 `sessionId`(대화 기록)를 함께 적는다. 없으면 `sessionId` → `name` → `cwd` 순으로 살아 있는 세션을 찾음(없으면 `~/orca/orchestrator`)

## 6. 리드 운영 규칙

대시보드는 리드가 남기는 기록을 그대로 보여 주므로, 기록이 어긋나면 화면도 어긋난다.

- **단계마다 기록**: 진행 현황 문서 변경 기록에 한 행씩. 형식 `| N | YYYY-MM-DD HH:MM | 변경·결정 | 내용 | 링크 또는 채팅 |` — 끝 열이 빠지면 패널에 안 나온다. 여러 세션이 같은 문서에 쓰므로 번호는 쓰기 직전 최댓값 + 1
- **할 일 상태**: 끝난 일은 `curl -s -XPOST -H 'content-type: application/json' -d '{"done":true}' 127.0.0.1:<port>/api/items/<id>`. 새 할 일은 `status.json` 에 `no` = 최댓값 + 1 로 추가
- **지금 하는 일 알리기**(선택): `POST /api/agents/focus {name, stream, item, doing}` — 요청 키워드로 자동 추정되지만 틀릴 때 쓴다
- **대시보드 채팅 메시지**: 제목이 「사용자가 대시보드에서 보낸 메시지」인 세션 간 메시지는 사용자 요청으로 처리한다. 다만 커밋·push·외부 전송 승인은 직접 채팅이나 「변경 검토 → 적용」으로 받는다(보낸 사람이 리드로 찍혀 승인 근거가 되지 못함)
- **변경안을 리드가 직접 만들 때**: `drafts/<id>/` 에 plan.md·바뀔 내용·manifest.json 을 쓰고 `dispatches.json` 에 검토 대기 기록을 추가한다(형식은 operations.md). 사용자는 「변경 검토」에서 diff 를 보고 적용한다
- **세션 정리**: 대시보드가 띄운 세션은 자동 회수된다. 테스트 대기처럼 계속 필요한 세션은 채팅 팝업 「이 세션 유지」. 리드가 직접 회수할 때는 대기 상태·작업 완료를 확인하고 Claude 프로세스만 종료한다(대화 기록은 남음)

## 7. 보고

설치·변경을 마치면 URL, 포트, 작업 세션·할 일·결과물 수, 확인한 것과 확인 못 한 것을 짧게 보고한다. 기능 상세는 `references/operations.md` 를 근거로 답한다.
