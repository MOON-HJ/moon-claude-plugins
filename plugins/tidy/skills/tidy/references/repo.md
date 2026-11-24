# Tidy Repo — 브랜치·stash 주기 정리

로컬에 쌓인 브랜치와 stash 중 이미 역할이 끝난 것을 골라내 정리한다. 판정 근거는 로컬 git 상태와 GitHub PR 상태고, 이슈 트래커(Jira 등)가 연결돼 있으면 티켓 상태를 함께 본다. 삭제는 전부 백업 태그를 건 뒤에 한다.

## 대상·상수

- **REPOS**: 하드코딩하지 않는다. 인자로 repo 경로·이름을 받으면 그것만 본다. 없으면 `~/.claude/tidy-repo-roots.txt`(한 줄에 루트 하나)가 정한 루트 아래에서 3단계까지 훑어 찾고, 그 파일도 없으면 현재 디렉토리를 루트로 쓴다. `node_modules`·`vendor`·`.venv`는 건너뛴다.
  ```bash
  find <루트> -maxdepth 3 \( -name node_modules -o -name vendor -o -name .venv \) -prune -o -name .git -print
  ```
- **GitHub**: `gh` CLI에 로그인된 계정 그대로 쓴다. 로그인이 안 돼 있으면 PR 판정을 건너뛰고 그 사실을 보고에 적는다.
- **이슈 트래커**(선택): Jira 등 조회 도구가 연결돼 있을 때만 티켓 상태를 본다. 없으면 PR 상태만으로 판정하고 근거가 약한 항목은 "확인 필요"로 내린다.
- **보호 브랜치** (절대 삭제 후보에 넣지 않는다):
  - 공통: `main`, `master`, `develop`, `stage`, `release/*`, 현재 체크아웃 브랜치
  - repo별: 장기 공유 브랜치(예: 테스트 서버 배포용)가 있으면 사용자가 알려 준 이름을 추가한다. ahead/behind 양쪽으로 크게 갈라진 upstream 있는 브랜치는 후보에 넣기 전에 묻는다
- **백업 태그**: `stash-bak-yyyyMMdd-<인덱스>`, `branch-bak-yyyyMMdd-<브랜치명 슬러그>`

## 워크플로

### 1. 스캔 (repo마다, 읽기 전용)

```bash
git -C <repo> fetch --prune          # gone 판정의 전제 — 반드시 먼저
git -C <repo> branch -vv
git -C <repo> stash list --date=format:'%Y-%m-%d' --pretty=format:'%gd|%cd|%s'
```

네트워크가 막히면 `fetch --prune`을 건너뛰되 **"gone 판정은 직전 prune 기준"이라고 보고에 명시**한다. 지어내지 않는다.

### 2. 브랜치 분류

| 버킷 | 판정 | 근거 |
| --- | --- | --- |
| 삭제 후보 | `gh pr list --head <브랜치> --state merged`에 결과 있음 | 머지 확정 — 가장 강한 신호 |
| 삭제 후보 | `git branch --merged origin/main`에 포함 | 일반 머지 repo에서만 유효 |
| 삭제 후보 | `branch -vv`가 `: gone]` 표시 | 리모트에서 사라짐. **머지 증명은 아님** — 동료가 지웠거나 미머지 삭제일 수 있으니 PR 상태를 함께 확인 |
| 확인 필요 | PR이 OPEN인데 제목에 `[DO NOT MERGE]`·`프리뷰` 등이 있고 티켓은 완료 | 영영 머지되지 않을 브랜치다 |
| 확인 필요 | upstream 없는 로컬 전용 + 마지막 커밋 30일 경과 | 실험용으로 만들고 잊은 브랜치일 가능성 |
| 보존 | 보호 브랜치, 현재 체크아웃, PR OPEN(정상 진행 중) | — |

**⚠️ squash-merge repo에서는 `--merged`와 ancestor 테스트가 통하지 않는다.** squash 머지하는 repo는 머지된 작업도 커밋 해시가 달라 `git merge-base --is-ancestor`가 항상 거짓이 된다. 이런 repo는 **PR 상태(와 티켓 상태)로만** 판정한다.

이슈 트래커가 있으면 브랜치명에서 티켓 키를 뽑아(`feat/ABC-414` → `ABC-414`) 한 번에 조회한다(Jira면 JQL `key in (...)`).

### 3. stash 분류

각 stash에 대해:

```bash
git log -1 --format='%cd %s' --date=short 'stash@{N}'   # 날짜·메시지
git stash show --name-only 'stash@{N}'                   # 파일 목록
git rev-parse -q --verify 'stash@{N}^3'                  # untracked 페이로드 유무
git rev-parse 'stash@{N}^{tree}'                         # 트리 해시 (중복 판정)
```

| 버킷 | 판정 |
| --- | --- |
| 삭제 후보 | 트리 해시가 다른 stash와 동일 (완전 중복) |
| 삭제 후보 | 추가된 줄의 대부분이 다른 stash·브랜치에 이미 존재 (포함관계 — 더 최신 쪽만 남긴다) |
| 삭제 후보 | 담긴 파일 경로가 `origin/main`·활성 브랜치 어디에도 없음 (구조 개편으로 폐기된 코드) |
| 삭제 후보 | 원 티켓이 완료 + 최종본이 커밋으로 남아 있음 |
| 삭제 후보 | `Autostash. Switch from ...` 자동 생성 잔여물, 1~2줄짜리 소품 |
| 확인 필요 | 어디에도 없는 고유 내용이 크고(수백 줄↑) 최근 것 |
| 보존 | 진행 중인 티켓 기반 |

포함관계·경로 소멸 판정은 stash가 10개를 넘으면 스크립트로 일괄 처리하는 편이 빠르다. 추가된 줄이 비교 대상 ref의 파일 내용에 들어 있는지 세는 방식이면 충분하다.

### 4. 제안 → 컨펌 → 실행

repo별로 세 버킷(**삭제 후보 / 확인 필요 / 보존**)을 표로 제시하고, 각 항목에 **한 줄 근거**를 붙인다. 근거 없는 삭제 제안은 하지 않는다.

승인받은 뒤에만 실행한다.

```bash
STAMP=$(date +%Y%m%d)

# stash — 백업 태그 후 내림차순 삭제
for i in $DROP; do git tag -f "stash-bak-$STAMP-$i" "stash@{$i}"; done
for i in $(echo $DROP | tr ' ' '\n' | sort -rn); do git stash drop "stash@{$i}"; done

# 브랜치 — 백업 태그 후 삭제
for b in $BRANCHES; do
  git tag -f "branch-bak-$STAMP-$(echo $b | tr '/' '-')" "$b"
  git branch -D "$b"
done
```

### 5. 보고

- repo별 정리 전후 개수, 삭제 목록, 남긴 것과 그 이유
- 복구 명령: `git stash apply stash-bak-<날짜>-<번호>` / `git switch -c <이름> branch-bak-<날짜>-<슬러그>`
- 태그 정리 명령: `git tag -d $(git tag -l 'stash-bak-<날짜>-*' 'branch-bak-<날짜>-*')` — 한 달쯤 뒤 권장. **두 패턴을 모두 넣어야** 브랜치 백업 태그가 남지 않는다
- 백업 태그는 로컬 전용이라 push에 영향 없음을 함께 안내

## 함정 (실측으로 확인된 것)

- **`git rev-parse <ref>:<경로>`는 경로가 없어도 인자를 그대로 stdout에 돌려준다.** 존재 확인은 반드시 `git cat-file -e <ref>:<경로>`의 종료 코드로 한다. rev-parse로 판정하면 "전부 존재함"이라는 정반대 결과가 나온다.
- **stash 삭제는 내림차순으로.** 하나 지울 때마다 뒤쪽 인덱스가 당겨진다.
- **`stash@{N}^3`을 확인한다.** `-u`로 만들었거나 GUI가 만든 stash는 untracked 파일을 세 번째 부모에 담는데, `git stash show`와 `git diff stash^ stash`에는 전혀 잡히지 않는다.
- **백업은 태그로, patch export로 하지 않는다.** `git stash show -p`는 `^3` 트리를 통째로 빠뜨리고 바이너리를 뭉갠다. 태그는 커밋 전체를 부모까지 붙잡아두고 gc 대상에서도 빠진다.
- **삭제한 stash·브랜치는 즉시 unreachable이 되어 gc 대상이다.** 백업 태그 없이 지우면 회수 창이 2주뿐이다.

## 가드레일

- **삭제는 전부 제안 → 컨펌 → 실행.** 백업 태그 생성까지가 무컨펌 허용 범위다.
- 보호 브랜치와 현재 체크아웃 브랜치는 후보 목록에 올리지도 않는다.
- 판정 근거가 하나뿐이면(예: `: gone]`만) "삭제 후보"가 아니라 "확인 필요"로 내린다.
- 조회에 실패한 소스는 실패했다고 적는다. 추정으로 채우지 않는다.
- `git push --delete`로 리모트 브랜치를 지우는 일은 이 스킬 범위 밖이다. 로컬만 정리한다.
