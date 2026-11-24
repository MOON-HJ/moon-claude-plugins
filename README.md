# moon-claude-plugins

개인 작업용 Claude Code 플러그인 마켓플레이스.

## 설치

```
/plugin marketplace add MOON-HJ/moon-claude-plugins
/plugin install ticket-dashboard@moon-plugins
/plugin install tc-report@moon-plugins
```

## 플러그인

| 이름 | 설명 |
|---|---|
| ticket-dashboard | 티켓 하나의 진행 상황(리드 세션 → 작업 세션 → 결과물)을 실시간으로 보고 조작하는 로컬 대시보드. 여러 티켓을 묶는 통합 대시보드 포함 |
| tc-report | 테스트케이스 시트·시나리오 문서와 E2E 실행 결과(Playwright·Maestro)를 캡처·영상이 붙은 QA 리포트로 발행. `e2e-runner` 에이전트 포함 |

Jira 링크를 쓰려면 `init.mjs --jira-base https://<도메인>.atlassian.net/browse/` 로 주소를 지정한다.
