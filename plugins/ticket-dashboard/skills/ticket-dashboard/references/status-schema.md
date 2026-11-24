# status.json 형식

대시보드가 보여 주는 작업 모델이다. 서버는 이 파일을 1초마다 다시 읽고, 바뀌면 열려 있는 화면에 바로 반영한다. 직접 고칠 때는 임시 파일에 쓰고 이름을 바꿔(원자적 쓰기) 서버가 반쯤 쓴 파일을 읽지 않게 한다. 실제 예시는 `example-status.json`(PROJ-383).

## 최상위

| 필드 | 뜻 |
|---|---|
| `key` | 티켓 키. 작업 세션 프롬프트 태그(`[키 대시보드 변경안 d-…]`)와 화면 제목에 쓰임. 바꾸면 서버 재시작 |
| `title` | 헤더 제목 |
| `port` | 서버 포트(기본 4000 + 티켓 번호 % 1000). 바꾸면 재시작 |
| `repo` | 기본 GitHub 레포(`owner/name`). `auto.pr`(다른 레포는 `auto.repo`)·배포 태그 확인에 씀 |
| `jiraBase` | Jira 링크 앞부분 |
| `streams` | 작업 세션(가로 열) 목록 |
| `flow` | 선택. `"pipeline"` 이면 작업 세션을 단계로 보고 리드 → 단계들을 한 줄로 왼쪽→오른쪽 화살표로 잇는다(작업 중인 단계로 가는 화살표가 움직임). 없으면 리드 아래 나란히 |
| `stages` | 선택(`flow: "pipeline"`). 단계 목록 `[{ id, title, lead?, loopTo?, loopLabel?, outs? }]`. 있으면 작업 세션(레포·작업 폴더)은 그대로 두고 할 일의 `stage` 로 단계 열을 그린다. 티켓 표준은 initial(lead) → plan → build → verify(loopTo plan) → deploy. 결과물은 `outs` 가 없으면 연결된 남은 할 일의 단계, 다 끝났거나 자동 판정이면 마지막 단계 |
| `cycles` | 선택. 사이클(Plan → Build → Verify 한 바퀴) 기록 배열. 있으면 「사이클」 패널이 보이고 루프 화살표 이름에 실패 횟수가 붙음. 항목: `n`(1부터), `item`(할 일 id), `at`, `plan`·`build`·`verify`(한 줄씩), `result`(`pass`·`fail`·`doing`) |
| `outputs` | 결과물 카드 사전(`id → 결과물`) |
| `agents.watch` | 감시할 작업 폴더. 리드는 `role: "lead"`, `name`(세션 이름)으로 구분. 폴더마다 리드는 하나: 이름 일치 → 마지막으로 본 리드 세션(`leads.json`) → 그 폴더에서 대시보드가 띄우지 않은 세션 중 먼저 시작한 세션 순(재개하면 derived 이름이 바뀌기 때문) |
| `agents.leadDoc` / `docs.progressDoc` | 진행 현황 문서 경로(변경 기록 패널·프롬프트 참고) |
| `docs.root` | 마크다운 변경 diff 를 추적할 폴더(raw·archive 제외) |

## streams[] — 작업 세션

```json
{ "id": "app", "title": "앱", "ticket": "APP-1021",
  "worktree": "/…/my-app/APP-1021-pr",
  "keywords": ["APP-1021", "#584", "PR 본문"],
  "outs": ["pr584", "body"],
  "items": [ … ] }
```

- `worktree`: 「진행」으로 띄우는 작업 세션이 열릴 폴더. 레포 작업이면 그 레포 워크트리, 문서·확인 작업이면 리드 워크트리
- `keywords`: 리드 세션 요청 문장에 이 말이 있으면 리드가 이 작업 세션을 하고 있다고 보고 흐름을 그린다
- `outs`: 이 작업 세션 아래에 매달 결과물 id 순서
- `lead`(선택, `flow: "pipeline"` 일 때): `true` 인 단계(보통 Initial)는 리드 노드가 맡는다. 따로 그리지 않고 남은 일을 리드 노드 안에 보임
- `loopTo`·`loopLabel`(선택, `flow: "pipeline"` 일 때): 이 단계에서 되돌아갈 단계 id 와 화살표 이름. 예: Verify 단계에 `"loopTo": "plan", "loopLabel": "검증 실패 → 다시 계획"` 이면 위쪽에 보라 점선 루프를 그림

## items[] — 할 일

```json
{ "id": "app-body", "no": 14, "text": "PR 본문 수정", "done": false,
  "who": "approve", "out": "body",
  "refs": [{ "type": "pr", "repo": "owner/repo", "number": 584 }],
  "auto": { "release": "v11.15.0" } }
```

| 필드 | 뜻 |
|---|---|
| `id` | 고정 id(작업세션-짧은말) |
| `no` | 고정 번호 `#N`. 처음 1부터, 새 할 일은 최댓값 + 1. 순서가 바뀌어도 다시 매기지 않음 |
| `text` | 명사형으로 짧게 |
| `done` / `doneAt` | 완료 여부·시각. 화면 팝업이나 `POST /api/items/<id>` 로 바꾸면 `doneAt` 이 붙음 |
| `who` | 남은 일 담당 태그: `approve`(승인 필요)·`ext`(외부 확인)·`me`(내 작업)·`plan`(예정) |
| `out` | 이 할 일이 만드는 결과물 id. 결과물에 `auto` 가 없으면 연결된 할 일이 모두 끝날 때 「나옴」 |
| `refs` | 프리뷰 대상. `pr`(repo·number), `slack`(channel·ts·title·url), `link`(title·url) |
| `stage` | `stages` 를 쓸 때 이 할 일의 단계 id. 없으면 완료·자동 판정은 마지막 단계, 남은 일은 build. 단계가 넘어가면 리드가 바꾼다 |
| `auto` | GitHub 로 자동 판정: `{ "pr": 625, "merged": true }`, `{ "pr": 4043, "repo": "owner/other-repo" }`, `{ "release": "v11.15.0" }`. 자동 판정 할 일은 화면에서 체크 불가 |

## outputs{} — 결과물

```json
"pr584": { "name": "PR #584", "desc": "리뷰 중", "url": "https://…/pull/584", "auto": { "pr": 584 } },
"e2e": { "name": "E2E 리포트 3건", "done": true, "links": [["앱 TC", "https://…"]] },
"vault": { "name": "진행 현황 문서", "done": true, "auto": { "vaultLog": true } }
```

- `auto.pr`: 상태·리뷰·체크 수를 1분마다 가져와 설명줄에 표시(`merged: true` 면 병합돼야 「나옴」). 기본 레포가 아닌 PR 은 `auto.repo`(`owner/name`)를 함께 적음
- `auto.release`: 해당 태그가 생기면 「나옴」(기본 레포 `repo` 의 태그만 확인)
- `auto.vaultLog`: 진행 현황 문서의 마지막 기록 번호·시각을 설명줄에 표시
- `done` 을 직접 둘 수도 있음(자동 판정·연결 할 일이 없을 때)

## agents.watch[]

```json
{ "cwd": "/…/notes/PROJ-383_manager", "label": "리드 세션", "role": "lead", "name": "PROJ-383" },
{ "cwd": "/…/my-app/APP-1021-pr", "label": "앱 워커", "stream": "app" }
```

`~/.claude/sessions/*.json` 에서 이 폴더(또는 그 아래)에 있는 살아 있는 세션만 화면에 나온다. 워커 폴더에 `stream` 을 주면 그 작업 세션 카드에 붙는다. Orca 채팅 리드는 쉬는 동안 등록 파일이 사라지므로, 한 번 본 리드 세션을 `leads.json` 에 남겨 두고 그 Orca 채팅이 목록에 있는 동안 대기 상태로 보여 준다.
