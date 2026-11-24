---
name: tc-report
description: 테스트케이스를 QA 리포트 아티팩트로 발행한다. 모드 A는 구글시트(URL·붙여넣기·CSV)를, 모드 B는 테스트 시나리오 문서(TEST_SCENARIOS.md)와 자동화 실행 결과(웹 Playwright E2E·모바일 앱 Maestro)를 입력으로 쓴다. 모드 B는 e2e-runner 서브에이전트로 실행·캡처·영상 수집을 맡기고 결과를 TC에 매핑한다. 시트를 report.json으로 정규화하고 번들된 build_report.py로 요약 카드·구분별 막대·필터·케이스 상세(스텝/기대결과/관찰/캡처)를 갖춘 HTML을 만들어 Artifact로 발행하거나 기존 아티팩트를 갱신한다. "TC 시트로 아티팩트 만들어줘", "테스트케이스 시트 리포트로 뽑아줘", "QA 결과 아티팩트로 정리해줘", "시트 넣으면 리포트", "/tc-report <시트 URL>", "테스트 시나리오 보고 e2e 돌리고 리포트", "앱까지 테스트해서 아티팩트로", "E2E 결과 영상 포함해서 정리" 등에 사용. 결과 컬럼이 없으면 미실행 체크리스트 모드로 발행한다.
argument-hint: "<구글시트 URL | CSV/TSV 경로·붙여넣기 | TEST_SCENARIOS.md 경로> [기존 아티팩트 URL]"
allowed-tools: ["Bash", "Read", "Write", "Edit", "Glob", "Grep", "ToolSearch", "Artifact", "Skill", "Agent", "AskUserQuestion", "mcp__claude_ai_Google_Drive__read_file_content", "mcp__claude_ai_Google_Drive__download_file_content", "mcp__claude_ai_Google_Drive__get_file_metadata", "mcp__claude_ai_Google_Drive__search_files"]
---

# TC Report — 테스트케이스 시트 → QA 리포트 아티팩트

테스트케이스 시트를 받아 **QA 리포트 디자인**(요약 카드·구분별 막대·필터 표·케이스 상세·라이트박스)의 HTML로 빌드해 아티팩트로 발행한다.
렌더링은 번들 스크립트가 결정적으로 처리하므로, 이 스킬의 일은 **입력을 report.json으로
정규화하는 것**이 전부다.

| 모드 | 입력 | 절차 |
|---|---|---|
| A. 시트 | 구글시트·CSV·붙여넣기 | 1~5절 |
| B. 시나리오 + 자동화 | `TEST_SCENARIOS.md` + Playwright/Maestro 실행 | **6절** → 3~5절 |

작업 파일(report.json, report.html, 캡처 변환본)은 전부 세션 scratchpad에 만든다.

## 1. 시트 입력 확보

우선순위대로 시도하고, 실패하면 다음으로 넘어간다.

1. **Google Drive MCP** (기본 — 비공개 시트는 이 경로만 됨):
   URL `https://docs.google.com/spreadsheets/d/{fileId}/edit...#gid={gid}`에서 fileId를 뽑아
   `mcp__claude_ai_Google_Drive__read_file_content`로 읽는다 (ToolSearch로 로드).
   여러 탭이 합쳐져 오거나 원하는 탭을 못 고르면 어느 탭인지 사용자에게 확인한다.
2. **export URL** (링크 공유가 열린 시트만):
   `curl -sL "https://docs.google.com/spreadsheets/d/{fileId}/export?format=csv&gid={gid}"` —
   응답이 HTML(로그인 페이지)이면 실패로 판정한다.
3. **붙여넣기/로컬 파일**: 사용자가 붙여넣은 TSV·표, 로컬 CSV/TSV 경로.
   XLSX는 `python3`+openpyxl이 없으면 사용자에게 CSV export를 요청한다.

원본(CSV/TSV)은 scratchpad에 저장해 두고 정규화 결과와 행 수를 대조한다.

## 2. report.json으로 정규화

컬럼명이 아니라 **의미로 매핑**한다.

| 시트 컬럼 (예) | JSON 필드 | 처리 |
|---|---|---|
| ID / 번호 | `id` | 없으면 TC-01, TC-02… 순차 생성 |
| Title / 케이스 / 시나리오 | `title` | `그룹_케이스명` 형태면 첫 `_` 기준 분리 → 앞은 `group` |
| 구분 / 유형 (정상·경계·예외) | `category` | 값 그대로. 없으면 필드 생략(강제 분류 금지) |
| Priority / 우선순위 | `priority` | P1~P4 그대로 |
| Preconditions / 사전조건 | `pre` | HTML 잔재 제거, 여러 줄은 `·`로 합침 |
| Steps / 단계 | `steps` (배열) | HTML 제거, 단계별로 쪼갬 |
| Expected Result / 기대결과 | `expected` (배열) | HTML 제거, 단계별로 쪼갬 |
| 결과 / 판정 | `status` | Pass·Fail·보류(Blocked)·N/A. **공란이면 생략**(→미실행) |
| 비고 / 사유 / 코멘트 | `note` | Fail·보류 사유. 상세에 빨간 줄로 표시 |

HTML 잔재 정리: `<ol><li>`·`<ul><li>`·`<div style>`·`<span>`·`&nbsp;`·`id="isPasted"` 제거,
중복 접두 번호(`1. 1.`) 정리.

**report.json 스키마** (스크립트 docstring에도 있음):

```json
{
  "meta": {
    "eyebrow": "PROJ-92 · QA-270",
    "title": "결제 화면 개편 QA 리포트",
    "sub": "한두 문장 요약. <b>·<code> 허용(신뢰 HTML — 직접 작성한 안전한 마크업만)",
    "facts": [["대상", "..."], ["기준", "워크시트 80건 · 2026-09-09"]],
    "generatedAt": "2026-09-15 14:00 KST",
    "footer": "생략 가능 — 기본값: title · 생성 generatedAt"
  },
  "findings": [{
    "severity": "critical|high|medium|note|resolved",
    "tag": "결함", "meta": "TC-74 · 저장 경로",
    "title": "한 줄 요약", "body": "신뢰 HTML", "impact": "신뢰 HTML(생략 가능)"
  }],
  "cases": [{
    "id": "TC-01", "group": "생략 가능", "title": "케이스명",
    "category": "정상", "priority": "P1", "status": "Pass",
    "pre": "사전조건", "steps": ["…"], "expected": ["…"],
    "note": "Fail 사유(생략 가능)", "verifiedAt": "생략 가능",
    "obs": [{"kind": "ok|ng|err", "text": "관찰"}],
    "shots": [{"src": "파일명 또는 data URI", "cap": "캡션"}],
    "videos": [{"src": "videos/tc-01.webm", "cap": "캡션"}]
  }],
  "notes": [{"title": "환경 특이사항", "body": "신뢰 HTML"}]
}
```

- `findings`는 시트의 Fail/보류 행과 비고에서 뽑는다. 결함이 없으면 빈 배열(섹션 자체가 생략됨).
- 결과 컬럼이 아예 없는 시트 = **체크리스트 모드**: status 전부 생략 → 미실행으로 집계된다.
  이때 `sub`에 "실행 전 체크리스트" 성격을 명시한다.
- 정규화 후 **행 수가 시트와 일치하는지 검증**하고, 버린 행(빈 행·머리글 반복)은 사용자에게 보고한다.

## 3. 빌드

```bash
python3 "${CLAUDE_SKILL_DIR}/assets/build_report.py" \
  <scratchpad>/report.json <scratchpad>/report.html [--shots-dir <캡처 디렉토리>]
```

- 스크립트가 판정 집계를 출력한다 — **시트와 다르면 정규화를 의심**하고 되돌아간다.
- 캡처를 임베드할 때: PNG가 크면 `cwebp -q 80`으로 변환해서 넣는다. 15MB 초과 시
  스크립트가 exit 2로 경고한다(아티팩트 한도 16MB).
- 영상(`videos[]`)은 임베드하지 않는다. HTML은 상대 경로만 가리키므로 HTML을 `<pub>/` 에 빌드하고
  영상을 `<pub>/videos/`에 둔다. 썸네일을 누르면 라이트박스에서 크게 재생된다.

## 4. 아티팩트 발행

1. `artifact-design` 스킬을 먼저 로드한다 (Artifact 도구 계약 — 템플릿이 디자인을 이미
   담고 있어도 로드는 생략하지 않는다).
2. 발행:
   - **새 리포트**: `Artifact(file_path=report.html)` + favicon `🧪` + `description` 한 문장.
     `<title>`은 build 스크립트가 meta.title로 넣는다 — 짧은 고유명사구로 짓는다
     (예: "결제 화면 개편 QA 리포트").
   - **기존 리포트 갱신**: 사용자가 아티팩트 URL을 줬거나 "같은 링크 유지"를 원하면
     `url` 파라미터로 갱신한다. favicon은 기존 것을 유지한다.
3. 같은 세션에서 재빌드하면 같은 file_path로 다시 발행하면 된다(같은 URL 유지).
4. **영상이 있으면** `root=<pub>`, `files={"videos/<이름>": {"from": "videos/<이름>", "contentType": "video/webm|video/mp4"}}`로
   함께 올린다(파일 하나 15MB·한 번에 64MB 한도). 갱신 때는 새로 바뀐 영상만 넘기면 나머지는 유지된다.

## 5. 보고

최종 메시지에 넣을 것: 아티팩트 링크, 판정 집계(Pass/Fail/보류/N/A/미실행), 시트에서 버린
행이나 매핑이 애매했던 컬럼, (체크리스트 모드면) 결과 채운 뒤 재발행 가능하다는 안내.

## 주의

- 아티팩트는 조직 공유될 수 있다 — 시트에 실명·연락처 등 개인정보가 보이면 발행 전에 사용자에게
  확인받는다 (기본은 마스킹).
- `meta.sub`·`findings[].body`·`impact`·`notes[].body`는 이스케이프 없이 삽입된다.
  시트 셀 원문을 그대로 넣지 말고 직접 작성한 안전한 마크업만 쓴다. 케이스 필드는 전부
  이스케이프되므로 원문 그대로 둬도 된다.
- 판정 라벨 매핑은 스크립트가 관대하게 처리한다(성공/통과/O→Pass, 실패/X→Fail,
  Blocked/재확인→보류, 제외/해당없음→N/A, 공란→미실행). 시트에 그 외 라벨이 있으면
  임의 해석하지 말고 사용자에게 확인한다.
- 이 스킬은 테스트를 직접 실행하지 않는다. 실행·수집은 모드 B의 `e2e-runner` 서브에이전트가 한다.

## 6. 모드 B — 시나리오 + 자동화 결과

판단(범위·스펙·사유)은 메인 대화가, 반복 실행과 수집은 서브에이전트가, 매핑과 빌드는 스크립트가 맡는다.
스펙을 쓰기 전에 `references/e2e-playbook.md`를 먼저 읽는다(실제로 부딪힌 함정 모음).

1. **시나리오 확보**: 로컬 `TEST_SCENARIOS.md` 경로를 받는다. 아직 머지되지 않은 브랜치에 있으면
   `git -C <문서 레포> fetch origin <branch> && git show FETCH_HEAD:<path> > <scratchpad>/TEST_SCENARIOS.md`.
   표 형식은 `assets/scenarios_to_report.py` docstring을 따른다.
2. **범위 판정**(메인): TC를 자동화·보류·N/A로 나눈다(플레이북 1절). 앱 판정 TC는 서버 응답부터 본다.
3. **실서버 쓰기 게이트**: 쓰기 TC를 실서버로 돌릴지 **실행마다** `AskUserQuestion`으로 묻는다.
   허락받으면 플레이북 2절의 격리 패턴(스냅샷·먼 날짜·스냅샷 대비 정리)을 스펙에 넣는다. 거절이면 읽기 TC만.
4. **스펙 작성**(메인): 테스트 제목에 `TC-NN`을 넣고, 캡처는 `test-results/tcNN*.png`, 녹화는 `E2E_VIDEO=on`
   env로만 켠다. 앱은 scratchpad에 Maestro 플로우를 쓴다(레포 래퍼 스크립트가 외부로 결과를 보내면 쓰지 않는다).
5. **실행·수집**: `Agent(subagent_type="tc-report:e2e-runner")`에 넘긴다. 프롬프트에 넣을 것:
   모드(playwright|maestro), 수집 스크립트 경로(`${CLAUDE_SKILL_DIR}/assets/collect_media.py`의 절대 경로), 앱 디렉토리, 스펙·플로우 경로, 포트, scratchpad 출력 루트, 실서버 쓰기 승인 여부,
   (maestro면) 영상을 붙일 TC 목록과 이름. 반환: 통과 수·실패 요약·results JSON·media-map 경로·정리 로그.
   Playwright와 Maestro는 서로 독립이라 **병렬**로 띄워도 된다.
6. **overrides.json**(메인): 보류·N/A 사유, 추가 관찰, 캡처 캡션, meta(placeholder `{auto}` `{tests}` `{passed}` `{verified}` `{duration}`),
   findings, notes. 스키마는 `assets/scenarios_to_report.py` docstring.
7. **매핑·빌드**:
   ```bash
   A="${CLAUDE_SKILL_DIR}/assets"
   python3 $A/scenarios_to_report.py --scenarios <TEST_SCENARIOS.md> --results <e2e-results.json> \
     --media <media-map.json> --overrides <overrides.json> -o <pub>/../report.json
   python3 $A/build_report.py <report.json> <pub>/<이름>.html --shots-dir <shots>
   ```
   집계가 예상과 다르면 overrides를 의심한다. 그다음 4절 발행(영상 files 포함).
8. **보고**: 5절 + 실서버 정리 결과(지운 건수·실행 전후 목록 일치), 보류 사유 중 서버 미배포처럼 다시 돌려야 하는 것.
