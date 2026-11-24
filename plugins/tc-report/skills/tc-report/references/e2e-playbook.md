# E2E·앱 자동화 플레이북 (모드 B)

실제 프로젝트에서 부딪힌 것만 일반화해 적는다. 스펙을 새로 쓸 때 먼저 훑는다. 프로젝트 고유 규칙(테스트 README, 셀렉터 관례)이 있으면 그쪽이 우선한다.

## 1. 범위 판정 — 시나리오 TC를 셋으로 나눈다

| 분류 | 기준 | 처리 |
|---|---|---|
| 자동화 | 화면(웹·앱)이나 API 응답으로 기대 결과를 볼 수 있다 | 스펙 테스트 제목에 `TC-NN`을 넣는다(여러 개 묶어도 된다) |
| 보류 | 볼 수는 있는데 지금 조건(계정·데이터·서버 미배포)이 안 된다, 또는 기대 결과 일부를 화면이 안 보여 준다 | overrides `cases`에 사유를 적는다 |
| N/A | 서버 내부(쿼리 수·인덱스·배치)·다른 팀 영역이거나 설계 변경으로 사라진 동작 | overrides `scopeRules`(그룹 단위) 또는 `cases` |

- 시나리오 기대 결과가 **확정 디자인과 다르면** 디자인을 따르고 「확인 필요」 finding을 남긴다.
- 앱 판정 TC는 먼저 **서버 응답부터** 확인한다. 앱은 서버 값을 매핑만 하는 경우가 많아, 서버가 안 나갔으면 앱을 돌려도 「반영 안 됨」뿐이다. 그때는 기준선 녹화 + 보류로 남긴다.

## 2. 실서버 쓰기 — 매 실행 사용자 확인

공용 환경(개발·스테이징 포함)에 데이터를 만들거나 지우는 TC는 **실행마다** 사용자에게 묻는다(이전 승인은 다음 실행에 넘어가지 않는다). 허락받으면 격리 패턴을 지킨다.

1. 사전 점검 테스트에서 기존 데이터를 **스냅샷**(id 집합)으로 남긴다. 연관 도메인도 함께.
2. 테스트 날짜는 **먼 미래**(오늘+200일 등, 조회 창 안)로 잡고, 그 구간에 기존 데이터가 있으면 **시작하지 않는다**.
3. `test.afterAll`에서 스냅샷에 **없던 것만** 지운다. 테스트가 놓친 잔여물도 다시 목록을 떠서 지운다. 지운 결과를 `console.log('[cleanup] … → 204')`로 남긴다.
4. 실행 뒤 목록을 한 번 더 읽어 스냅샷과 같은지 확인한다(서브에이전트가 한다).
5. 쓰기 스펙은 `E2E_ALLOW_WRITE=on`일 때만 돌게 `test.skip(process.env.E2E_ALLOW_WRITE !== 'on')`로 막아 둔다.

## 3. Playwright 함정

- **전환 끄기 CSS를 주입하면 HeadlessUI Listbox·Transition이 닫힌 패널을 DOM에서 못 치운다.** 달력·셀렉트 셀렉터는 그 트리거 버튼의 컨테이너(`trigger.locator('..')`)로 좁힌다. 안 그러면 닫힌 패널의 항목이 눌린다.
- 달력 날짜는 `time[datetime="YYYY-MM-DD"]`처럼 의미 있는 속성으로 잡는다. 화면 문구·순서에 기대면 달이 바뀔 때 깨진다.
- **러너의 `browser.newContext()`는 프로젝트 `use`(storageState 포함)를 물려받는다.** 다른 계정으로 로그인하려면 `storageState: { cookies: [], origins: [] }`를 명시한다. `baseURL`은 `test.info().project.use.baseURL`.
- 모달 제목이 본문 testid 영역 **밖**에 있는 컴포넌트가 많다. 제목은 `getByRole('heading', { name: 제목 })`로 잡는다.
- 화면이 보내는 요청에서 API origin과 `authorization` 헤더를 잡아 `page.request`로 **우회 요청**(400·403·409 검증)과 정리를 한다.
- 녹화는 env로만 켠다: `test.use({ video: process.env.E2E_VIDEO === 'on' ? { mode: 'on', size } : 'off' })`. 직접 연 컨텍스트는 `recordVideo`를 주고 닫은 뒤 `test.info().attach('video', …)`.
- 리포트 캡처는 `page.screenshot({ path: 'test-results/tcNN.png' })` 규칙으로 저장하면 collect_media가 TC에 붙인다.
- dev 서버 포트와 Playwright 설정의 포트가 다르면 두 번째 dev 서버를 띄우다 실패한다. 이미 뜬 포트를 env로 넘긴다.

## 4. Maestro 함정

- 레포에 Maestro 래퍼 스크립트가 있으면 **결과를 메신저 등 외부로 보내는지** 먼저 확인한다. 보낸다면 `maestro --udid <UDID> test --flatten-debug-output --debug-output <dir> <flow>`를 직접 쓴다.
- 개발빌드는 Metro가 필요하다. 8081에 이미 떠 있으면 재사용한다(누가 어느 브랜치로 띄웠는지 리포트에 적는다).
- 앱을 켤 때 업데이트 안내·마케팅 동의·광고 팝업이 뜰 수 있다 → 닫기 버튼 문구를 `tapOn` optional 로 넣는다.
- 딥링크가 개발빌드에서 화면을 안 바꾸는 경우가 있다. 그때는 홈에서 실제 탭·검색 동선으로 들어간다.
- RN 접근성 트리는 텍스트를 묶어 한 요소로 낸다. 텍스트 매칭은 `".*문구.*"` 정규식으로 한다. 하단 플로팅 요소에 가린 testID는 visible로 안 잡힌다.
- 캡처는 `takeScreenshot`, 영상은 `startRecording`/`stopRecording` → `<debug>/takeScreenshot/*.png`, `<debug>/startRecording/*.mp4`. 원본 mp4는 1분만 넘어도 15MB를 넘는다 — collect_media가 avconvert로 줄인다(macOS).
- 실패하면 `<debug>/screen-hierarchy/step-*.json`의 마지막 파일에서 실제 화면의 text·resource-id를 본다.
