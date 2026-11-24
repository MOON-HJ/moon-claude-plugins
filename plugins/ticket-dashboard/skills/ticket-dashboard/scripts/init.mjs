#!/usr/bin/env node
// 티켓 대시보드 데이터 폴더(status.json 뼈대)를 만든다. 서버는 통합 대시보드(hub) 프로세스 하나가 모든 티켓을 띄우므로
// 티켓 폴더에는 코드를 두지 않는다. status.json 이 있으면 건드리지 않는다.
// --hub 는 hub 코드와 티켓 코드(hub/ticket/)를 설치·업데이트한다.
//
// node init.mjs --key PROJ-383 --lead-cwd <리드 워크트리> --progress-doc <진행 현황 md>
//   [--title "PROJ-383 알림 기능"] [--repo owner/repo] [--port 4383] [--lead-name PROJ-383]
//   [--jira-base https://your-domain.atlassian.net/browse/] [--dir ~/orca/dashboards/proj-383]
import fs from 'node:fs';
import net from 'node:net';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const args = {};
const argv = process.argv.slice(2);
for (let i = 0; i < argv.length; i++) {
  if (!argv[i].startsWith('--')) continue;
  const next = argv[i + 1];
  args[argv[i].slice(2)] = next && !next.startsWith('--') ? argv[++i] : 'true';
}

const skillDir = path.join(path.dirname(fileURLToPath(import.meta.url)), '..');

// --hub: 통합 대시보드(티켓 대시보드들을 사이드바 탭으로 묶는 화면)를 ~/orca/dashboards/hub 에 설치·업데이트
if (args.hub) {
  const hubDir = path.resolve(args.dir ?? path.join(os.homedir(), 'orca', 'dashboards', 'hub'));
  fs.mkdirSync(hubDir, { recursive: true });
  for (const f of ['server.mjs', 'index.html', 'start.sh', 'stop.sh']) {
    fs.copyFileSync(path.join(skillDir, 'assets', 'hub', f), path.join(hubDir, f));
  }
  fs.chmodSync(path.join(hubDir, 'start.sh'), 0o755);
  fs.chmodSync(path.join(hubDir, 'stop.sh'), 0o755);
  fs.mkdirSync(path.join(hubDir, 'ticket'), { recursive: true });
  for (const f of ['server.mjs', 'index.html']) {
    fs.copyFileSync(path.join(skillDir, 'assets', 'template', f), path.join(hubDir, 'ticket', f));
  }
  console.log(JSON.stringify({ dir: hubDir, url: 'http://127.0.0.1:4000/', note: '티켓 대시보드는 같은 부모 폴더에서 자동으로 찾아 이 프로세스가 띄움. 코드를 바꿨으면 ./stop.sh && ./start.sh' }, null, 2));
  process.exit(0);
}

const need = ['key', 'lead-cwd', 'progress-doc'];
const missing = need.filter((k) => !args[k]);
if (missing.length) {
  console.error(`필수 인자 없음: ${missing.map((k) => `--${k}`).join(' ')}`);
  process.exit(1);
}

const key = args.key;
const num = Number((key.match(/(\d+)$/) ?? [])[1] ?? 0);
// 4000 은 통합 대시보드 포트라 피한다.
const port = Number(args.port ?? (num % 1000 === 0 ? 4999 : 4000 + (num % 1000)));
const dir = path.resolve(args.dir ?? path.join(os.homedir(), 'orca', 'dashboards', key.toLowerCase()));

const portBusy = (p) =>
  new Promise((resolve) => {
    const srv = net.createServer();
    srv.once('error', () => resolve(true));
    srv.once('listening', () => srv.close(() => resolve(false)));
    srv.listen(p, '127.0.0.1');
  });

fs.mkdirSync(dir, { recursive: true });

const statusFile = path.join(dir, 'status.json');
const created = !fs.existsSync(statusFile);
if (created) {
  const leadCwd = path.resolve(args['lead-cwd']);
  const status = {
    key,
    title: args.title ?? key,
    port,
    repo: args.repo ?? '',
    jiraBase: args['jira-base'] ?? 'https://your-domain.atlassian.net/browse/',
    updatedAt: new Date().toISOString(),
    streams: [],
    outputs: {},
    agents: {
      leadDoc: path.resolve(args['progress-doc']),
      watch: [{ cwd: leadCwd, label: '리드 세션', role: 'lead', ...(args['lead-name'] ? { name: args['lead-name'] } : {}) }],
    },
    docs: { root: leadCwd, progressDoc: path.resolve(args['progress-doc']) },
  };
  fs.writeFileSync(statusFile, `${JSON.stringify(status, null, 2)}\n`);
}

const finalPort = JSON.parse(fs.readFileSync(statusFile, 'utf8')).port ?? port;
const busy = await portBusy(finalPort);
console.log(JSON.stringify({
  dir,
  url: `http://127.0.0.1:${finalPort}/`,
  statusJson: created ? '새로 만듦(streams·outputs 비어 있음)' : '기존 파일 유지',
  portBusy: busy,
  note: created
    ? '통합 대시보드(~/orca/dashboards/hub)가 3초 안에 찾아 띄움. 포트를 다른 프로세스가 쓰면 status.json 의 port 를 바꾼 뒤 hub 재시작'
    : 'status.json 의 key·port 를 바꿨으면 hub 재시작(./stop.sh && ./start.sh)',
}, null, 2));
