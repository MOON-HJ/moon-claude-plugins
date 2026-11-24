# Tidy Files — 다운로드·데스크톱 주기 정리

## 대상·상수

- **SCAN**: `~/Downloads`, `~/Desktop` (인자로 다른 폴더를 받으면 그것만)
- **ARCHIVE**: `~/Downloads/_archive/yyyy-MM/` (이동 가능 모드일 때)

## ⚠️ 환경·모드 (실행 전 모드 감지 필수)

- macOS는 터미널·앱마다 FDA(전체 디스크 접근 권한)를 따로 준다. 권한이 없으면 `ls ~/Downloads`부터 막힌다.
- **첫 단계에서 `ls ~/Downloads`를 실행해 모드 감지**: 성공 = 전체 모드(이동·삭제 가능) / 실패 = 제한 모드(보고서+복사만, 삭제는 목록 안내).
- 제한 모드로 돌아간 경우: 나열·메타데이터는 `mdfind`/`mdls`, 내용은 네이티브 Read/Write. FDA 재부여 안내: 시스템 설정 → 개인정보 보호 및 보안 → 전체 디스크 접근 권한 → 사용 중인 터미널/Claude 앱 켜기 → 앱 재시작.

## 워크플로

### 1. 스캔

**전체 모드 (기본)**: `ls`/`find` + `stat`으로 직접 스캔 — 누락 없음.

```
find ~/Downloads ~/Desktop -maxdepth 1 -type f ! -name ".*" -exec stat -f "%z%t%Sm%t%N" -t "%Y-%m-%d" {} \;
```

최근 사용일은 `mdls -name kMDItemLastUsedDate <파일>`로 보충.

**제한 모드 (폴백)**: mdfind 유형별 쿼리. ⚠️ 주의 — ① catch-all `kMDItemFSName == "*"`는 **0건을 반환하는 깨진 문법**이니 `kMDItemContentTypeTree == "public.item"`을 쓸 것 ② 유형별 쿼리는 오디오(m4a) 등을 놓치므로 반드시 폴더마다 public.item 쿼리로 전체 목록을 먼저 잡고 유형은 mdls로 판별.

```
mdfind -onlyin ~/Downloads 'kMDItemContentTypeTree == "public.item"'
mdfind -onlyin ~/Desktop  'kMDItemContentTypeTree == "public.item"'
```

각 파일에 `mdls -name kMDItemContentTypeTree -name kMDItemFSSize -name kMDItemFSContentChangeDate -name kMDItemLastUsedDate` — 유형·크기·수정일·최근 사용일 수집. 총 파일 수·용량을 먼저 보고. 폴더는 v1에서 제외(전체 모드는 `-type f`로, 제한 모드는 mdls의 public.folder로 걸러냄).

### 2. 분류 (보수적 — 모르면 안 건드린다)

| 버킷 | 판별 | 제안 액션 |
| --- | --- | --- |
| 녹음 전사 | 녹음 앱이 내보낸 전사 txt(`새로운 녹음 N.txt` 등, 화자·시각 줄 형식) | 회의록 정리 여부를 묻고, 아니면 아카이브 이동 |
| 설치파일 | .dmg/.pkg/설치용 .zip, 받은 지 7일↑ | 삭제 후보 |
| 스크린샷 | 파일명 `스크린샷`/`Screenshot`/`CleanShot` 접두 | 아카이브 이동 |
| 문서·이미지 | 내용·이름으로 프로젝트 연관 추정 | 대상 폴더 제안 (프로젝트 폴더·노트 저장소 등) |
| 장기 미사용 | 최근 사용 30일↑ | `_archive/yyyy-MM/` 이동 |
| **불명** | 판별 불가 | **액션 없음** — 목록만 보고 |

제외: 최근 3일 내 사용 파일(진행 중 작업일 가능성), 폴더는 v1에서 건드리지 않음.

### 3. [확인 게이트] 계획 승인

파일/크기/최근 사용/분류/제안 액션 표로 제시. **삭제는 파일명 단위 명시 승인** 필수.

### 4. 실행 (모드별)

- **전체 모드(FDA)**: `mv`로 이동. 삭제도 영구삭제 대신 `~/Downloads/_trash/`로 mv 해두고 "확인 후 비우세요" 안내(복구 가능성 확보).
- **제한 모드**: 이동 대상은 네이티브 Read→Write 복사 + **"원본 수동 삭제 목록"** 을 마지막에 한 번에 출력(Finder에서 일괄 선택·삭제하기 좋게). 삭제 후보는 목록만. ⚠️ 네이티브 Read→Write 복사는 **텍스트 파일만 가능** — 이미지·zip·dmg 등 바이너리는 복사 불가이므로 목록 안내로만 처리.

### 5. 보고

정리 N건 / 보류 M건 / 회수 용량 / 녹음 전사 처리 결과 / 다음 정리 시점 제안.

## 주기화

- 기본 리듬: **주 1회** (월요일 아침 권장) — "/tidy files" 호출.
- 완전 무인 자동화(launchd + `claude -p`)는 FDA 부여 후에만 의미 있음 — 사용자가 원할 때 별도 세팅.

## 가드레일

- **삭제는 절대 자동으로 하지 않는다.** 항상 파일명 명시 승인 후, 가능하면 _trash 경유.
- 불명 파일·최근 사용 파일은 건드리지 않는다.
- 파일 내용 열람은 분류에 필요한 최소(첫 몇 줄)만. 개인 파일 내용을 보고서에 옮기지 않는다.
