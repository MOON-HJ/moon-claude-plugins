import { execFile } from 'node:child_process';
import fs from 'node:fs';
import http from 'node:http';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { promisify } from 'node:util';

const run = promisify(execFile);
// 이 서버를 띄운 세션의 Orca 신원(ORCA_AGENT_SESSION_ID 등)을 물려받으면 orca 가 그 세션을 보낸 사람으로 적어 회신이 그 세션으로 새고,
// 그 세션 없이 다시 띄우면 orchestration send 가 no_active_sender_terminal 로 실패한다(Orca 1.4.271). 신원을 빼고 --from 으로 대시보드를 보낸 사람으로 적는다.
const ORCA_IDENTITY = new Set(['ORCA_AGENT_SESSION_ID', 'ORCA_AGENT_SESSION_SPAWN_TOKEN', 'ORCA_STRUCTURED_SESSION', 'ORCA_TERMINAL_HANDLE', 'ORCA_PANE_KEY']);
const ORCA_ENV = Object.fromEntries(Object.entries(process.env).filter(([k]) => !ORCA_IDENTITY.has(k)));
const ORCA_SENDER = 'ticket-dashboard';
const orca = (args, opts = {}) => run('orca', args, { ...opts, env: ORCA_ENV });

const DIR = path.dirname(fileURLToPath(import.meta.url));
// 통합 대시보드는 티켓 대시보드 폴더들과 같은 부모 폴더(~/orca/dashboards)에 둔다.
const ROOT = path.dirname(DIR);
const PORT = Number(process.env.PORT ?? 4000);
const POLL_MS = 3000;
const ORIGINS = new Set([`http://127.0.0.1:${PORT}`, `http://localhost:${PORT}`]);

// 오케스트레이션 세션: 이 폴더에서 도는 Claude 세션과 채팅한다(CLAUDE.md 세션 협업 규칙의 전용 폴더).
const ORCH_CWD = process.env.ORCH_CWD ?? path.join(os.homedir(), 'orca', 'orchestrator');
const SESSIONS_DIR = path.join(os.homedir(), '.claude', 'sessions');
const PROJECTS_DIR = path.join(os.homedir(), '.claude', 'projects');
// 예전 SendMessage 중계로 보낸 메시지를 기록에서 알아보는 접두어
const DASH_PREFIX = '[대시보드]';
const DASHBOARD_SUBJECT = '사용자가 대시보드에서 보낸 메시지';

const clients = new Set();
let tickets = [];
// 링크 설명(/api/link)이 찾아볼 티켓 상태·Slack 캐시 폴더. poll 마다 바뀐다.
let linkSources = [];
let orchestrator = { online: false };
let lastPayload = '';

const discover = () => {
  const out = [];
  for (const name of fs.readdirSync(ROOT)) {
    const dir = path.join(ROOT, name);
    const file = path.join(dir, 'status.json');
    if (dir === DIR || !fs.existsSync(file)) continue;
    try {
      const s = JSON.parse(fs.readFileSync(file, 'utf8'));
      if (s.key && s.port) out.push({ key: s.key, title: s.title ?? s.key, port: s.port, dir, order: s.hubOrder ?? 999 });
    } catch {}
  }
  return out.sort((a, b) => a.order - b.order || a.key.localeCompare(b.key));
};

// 티켓 대시보드도 이 프로세스 안에서 돈다. 코드(ticket/)는 한 벌이고, 티켓 폴더마다 모듈을 따로 불러 상태를 나눈다.
// 화면은 티켓마다 자기 포트로 연다. 한 출처에 SSE 가 몰리면 브라우저의 출처당 동시 연결 6개 제한에 걸리기 때문.
const TICKET_MODULE = pathToFileURL(path.join(DIR, 'ticket', 'server.mjs'));
const loaded = new Map();

const loadTicket = (t) => {
  let entry = loaded.get(t.dir);
  if (entry) return entry;
  const u = new URL(TICKET_MODULE);
  u.searchParams.set('dir', t.dir);
  entry = { mod: null, error: null, listening: false, starting: false };
  entry.ready = import(u.href).then((mod) => { entry.mod = mod; }).catch((e) => { entry.error = `불러오기 실패: ${e.message}`; });
  loaded.set(t.dir, entry);
  return entry;
};

// 포트를 못 잡으면(예전 티켓 서버가 떠 있는 등) 다음 poll 에서 다시 시도한다.
const listenTicket = (entry) => {
  entry.starting = true;
  const srv = http.createServer((req, res) => entry.mod.handle(req, res));
  srv.once('error', (e) => {
    entry.starting = false;
    entry.error = e.code === 'EADDRINUSE' ? `포트 ${entry.mod.PORT} 를 다른 프로세스가 쓰는 중` : e.message;
  });
  srv.listen(entry.mod.PORT, '127.0.0.1', () => {
    entry.starting = false;
    entry.listening = true;
    entry.error = null;
    console.log(`${entry.mod.KEY} 대시보드 http://127.0.0.1:${entry.mod.PORT}`);
  });
};

const ticketState = async (t) => {
  const entry = loadTicket(t);
  await entry.ready;
  if (entry.mod && !entry.listening && !entry.starting) listenTicket(entry);
  if (!entry.listening) return { s: null, error: entry.error };
  try {
    return { s: entry.mod.buildState(), error: null };
  } catch (e) {
    return { s: null, error: e.message };
  }
};

// 티켓 상태에서 사이드바·전체 현황에 필요한 것만 추린다.
const summarize = (s) => {
  const items = s.streams.flatMap((x) => x.items.map((it) => ({ ...it, stream: x.title })));
  const outs = Object.values(s.outputs ?? {});
  const agents = s.agents?.list ?? [];
  const done = new Set(items.filter((it) => it.done).map((it) => it.id));
  const reviews = (s.dispatches ?? []).filter((d) => d.status === 'review' && !done.has(d.itemId));
  return {
    done: items.filter((it) => it.done).length,
    total: items.length,
    remaining: items.filter((it) => !it.done).map((it) => ({ no: it.no, text: it.text, stream: it.stream, who: it.who ?? null })),
    outsReady: outs.filter((o) => o.done).length,
    outsTotal: outs.length,
    reviews: reviews.map((d) => d.text),
    busy: agents.filter((a) => a.busy).map((a) => ({ key: a.key, name: a.name, step: a.step, stepAt: a.stepAt })),
    sessions: agents.length,
    streams: s.streams.map((x) => ({ title: x.title, done: x.items.filter((it) => it.done).length, total: x.items.length })),
    prs: Object.values(s.github?.prs ?? {}).map((p) => ({ repo: p.repo, number: p.number, state: p.state, isDraft: p.isDraft, reviewDecision: p.reviewDecision, url: p.url })),
    lastLog: s.vault?.rows?.[0] ?? null,
  };
};

const alive = (pid) => {
  try {
    process.kill(pid, 0);
    return true;
  } catch (e) {
    return e.code === 'EPERM';
  }
};

const transcripts = new Map();
const findTranscript = (sessionId) => {
  if (transcripts.has(sessionId)) return transcripts.get(sessionId);
  for (const dir of fs.readdirSync(PROJECTS_DIR)) {
    const file = path.join(PROJECTS_DIR, dir, `${sessionId}.jsonl`);
    if (fs.existsSync(file)) {
      transcripts.set(sessionId, file);
      return file;
    }
  }
  return null;
};

const tailLines = (file, bytes = 800_000) => {
  const fd = fs.openSync(file, 'r');
  try {
    const size = fs.fstatSync(fd).size;
    const start = Math.max(0, size - bytes);
    const buf = Buffer.alloc(size - start);
    fs.readSync(fd, buf, 0, buf.length, start);
    const lines = buf.toString('utf8').split('\n');
    if (start > 0) lines.shift();
    return lines;
  } finally {
    fs.closeSync(fd);
  }
};

const describeTool = (use) => {
  const input = use.input ?? {};
  if (input.description) return input.description;
  const base = (p) => (p ? path.basename(p) : '');
  if (['Read', 'Edit', 'Write'].includes(use.name)) return `${use.name} ${base(input.file_path)}`;
  return use.name.replace(/^mcp__claude_ai_/, '').replaceAll('__', ' ');
};

const readHubConfig = () => {
  try {
    return JSON.parse(fs.readFileSync(path.join(DIR, 'hub.json'), 'utf8'));
  } catch {
    return {};
  }
};

let orcaAgents = { at: 0, list: [] };
const orcaAgentList = async () => {
  if (Date.now() - orcaAgents.at < 5_000) return orcaAgents.list;
  const { stdout } = await orca(['agent', 'list', '--json'], { maxBuffer: 16 * 1024 * 1024 });
  orcaAgents = { at: Date.now(), list: JSON.parse(stdout).result?.agents ?? [] };
  return orcaAgents.list;
};

// hub.json 의 orchestrator.orcaSessionId 가 있으면 Orca 목록의 그 행으로 켜짐·작업 중을 판정한다.
// Orca 채팅은 쉬는 동안 claude 프로세스가 내려가 세션 등록 파일이 사라지므로, 대화 기록은 orchestrator.sessionId 로 읽는다.
const findOrchestrator = async () => {
  const cfg = readHubConfig().orchestrator ?? {};
  if (cfg.orcaSessionId) {
    const row = (await orcaAgentList()).find((a) => a.orcaSessionId === cfg.orcaSessionId);
    if (!row) return null;
    const live = findSession(cfg);
    return {
      sessionId: cfg.sessionId ?? live?.sessionId ?? null, name: cfg.name ?? live?.name ?? row.title, cwd: cfg.cwd ?? live?.cwd ?? null,
      busy: row.state === 'working', orcaSessionId: cfg.orcaSessionId,
    };
  }
  const s = findSession(cfg);
  return s ? { sessionId: s.sessionId, name: s.name, cwd: s.cwd, busy: s.status === 'busy' } : null;
};

// 살아 있는 세션 등록 파일에서 sessionId → name → cwd 순으로 찾는다(없으면 ORCH_CWD 폴더).
const findSession = (cfg) => {
  const sessions = [];
  for (const f of fs.readdirSync(SESSIONS_DIR)) {
    if (!f.endsWith('.json')) continue;
    try {
      const s = JSON.parse(fs.readFileSync(path.join(SESSIONS_DIR, f), 'utf8'));
      if (alive(s.pid)) sessions.push(s);
    } catch {}
  }
  const byId = cfg.sessionId && sessions.find((s) => s.sessionId === cfg.sessionId);
  if (byId) return byId;
  const byName = cfg.name && sessions.filter((s) => s.name === cfg.name).sort((a, b) => (b.updatedAt ?? 0) - (a.updatedAt ?? 0))[0];
  if (byName) return byName;
  const cwd = cfg.cwd ?? ORCH_CWD;
  let best = null;
  for (const f of fs.readdirSync(SESSIONS_DIR)) {
    if (!f.endsWith('.json')) continue;
    try {
      const s = JSON.parse(fs.readFileSync(path.join(SESSIONS_DIR, f), 'utf8'));
      if (!(s.cwd === cwd || s.cwd?.startsWith(`${cwd}/`)) || !alive(s.pid)) continue;
      // 폴더 바로 아래 세션을 하위 폴더 세션보다, 같은 조건이면 최근 세션을 고른다.
      const rank = (x) => [x.cwd === cwd ? 1 : 0, x.updatedAt ?? 0];
      if (!best || rank(s)[0] > rank(best)[0] || (rank(s)[0] === rank(best)[0] && rank(s)[1] > rank(best)[1])) best = s;
    } catch {}
  }
  return best;
};

const PEER = /<cross-session-message[^>]*from-name="([^"]*)"[^>]*>\n?([\s\S]*?)\n?<\/cross-session-message>/g;
const SKIP_USER = /^<(system-reminder|command-|local-command|task-notification|user-prompt-submit-hook)/;

// Orca 세션 간 메시지 틀(From·Subject·Reply 줄)을 걷어 본문만 남긴다.
const unwrapMail = (text) => {
  const lines = text.split('\n');
  if (!/^─+ From: /.test(lines[0] ?? '')) return null;
  let i = 1;
  let subject = '';
  if (lines[i]?.startsWith('Subject: ')) subject = lines[i++].slice(9).trim();
  const body = [];
  for (; i < lines.length; i++) {
    if (lines[i].startsWith('[Reply: ') || /^─+$/.test(lines[i])) break;
    body.push(lines[i]);
  }
  return { subject, body: body.join('\n').trim() };
};

const textsOf = (content) =>
  typeof content === 'string' ? [content] : Array.isArray(content) ? content.filter((c) => c.type === 'text').map((c) => c.text) : [];

// 사용자 입력·응답·도구 단계·세션 간 메시지(대시보드에서 보낸 것은 사용자 말풍선)를 시간순으로.
const readConversation = (sessionId) => {
  const file = findTranscript(sessionId);
  if (!file) return [];
  const out = [];
  const pushUserText = (text, at) => {
    const v = text.trim();
    if (!v) return;
    if (v.includes('<cross-session-message')) {
      for (const m of v.matchAll(PEER)) {
        const body = m[2].trim();
        if (body.startsWith(DASH_PREFIX)) out.push({ role: 'user', text: body.slice(DASH_PREFIX.length).trim(), at, via: 'dashboard' });
        else out.push({ role: 'mail', subject: m[1], text: body, at });
      }
      return;
    }
    if (SKIP_USER.test(v)) return;
    const mail = unwrapMail(v);
    if (mail?.subject === DASHBOARD_SUBJECT) out.push({ role: 'user', text: mail.body.slice(0, 4000), at, via: 'dashboard' });
    else if (mail) out.push({ role: 'mail', subject: mail.subject, text: mail.body.slice(0, 4000), at });
    else out.push({ role: 'user', text: v.slice(0, 4000), at });
  };
  for (const line of tailLines(file)) {
    let d;
    try {
      d = JSON.parse(line);
    } catch {
      continue;
    }
    // 작업 중에 들어온 메시지는 사용자 턴이 아니라 이 첨부로 남고, prompt 는 문자열이거나 블록 배열이다
    if (d.type === 'attachment' && d.attachment?.type === 'queued_command') {
      for (const text of textsOf(d.attachment.prompt)) pushUserText(text, d.timestamp);
      continue;
    }
    if (d.isMeta || d.isCompactSummary) continue;
    const content = d.message?.content;
    if (d.type === 'user') {
      for (const text of textsOf(content)) pushUserText(text, d.timestamp);
    } else if (d.type === 'assistant' && Array.isArray(content)) {
      for (const c of content) {
        if (c.type === 'text' && c.text.trim()) {
          const last = out.at(-1);
          if (last?.role === 'assistant') last.text = `${last.text}\n\n${c.text.trim()}`.slice(0, 8000);
          else out.push({ role: 'assistant', text: c.text.trim().slice(0, 8000), at: d.timestamp });
        } else if (c.type === 'tool_use') {
          out.push({ role: 'tool', text: describeTool(c), at: d.timestamp });
        }
      }
    }
  }
  return out.slice(-80);
};

const orchestratorStatus = async () => {
  const s = await findOrchestrator();
  const cfg = readHubConfig().orchestrator ?? {};
  if (!s) return { online: false, cwd: cfg.cwd ?? ORCH_CWD, name: cfg.name ?? null };
  const msgs = s.sessionId ? readConversation(s.sessionId) : [];
  const lastTool = [...msgs].reverse().find((m) => m.role === 'tool');
  return {
    online: true, cwd: ORCH_CWD, id: s.sessionId, name: s.name, busy: s.busy,
    step: lastTool?.text ?? null, stepAt: lastTool?.at ?? null, count: msgs.length,
  };
};

// 데몬으로 도는 이 서버에서 띄운 헤드리스 Claude 의 SendMessage 는 성공을 돌려줘도 받는 세션에 닿지 않는다
// (2026-11-20 재현). 티켓 대시보드처럼 Orca 채팅으로 보낸다.
const orcaChatOf = async (s) => {
  if (s.orcaSessionId) return s.orcaSessionId;
  // Orca 는 경로를 NFD 로, 세션 기록은 NFC 로 적어 한글 경로(내 드라이브 등)가 그대로는 일치하지 않는다
  const cwd = s.cwd.normalize('NFC');
  const hits = (await orcaAgentList()).filter((a) => a.title === s.name && a.worktreeId?.normalize('NFC').endsWith(`::${cwd}`));
  return hits.length === 1 ? hits[0].orcaSessionId : null;
};

const relay = async (s, text) => {
  const orcaId = await orcaChatOf(s);
  if (!orcaId) throw new Error(`이 세션(${s.name})의 Orca 채팅을 찾지 못함. hub.json 의 orchestrator.orcaSessionId 로 지정 가능`);
  const { stdout } = await orca([
    'orchestration', 'send', '--from', ORCA_SENDER, '--to', `orca_session_id:${orcaId}`, '--type', 'status',
    '--subject', DASHBOARD_SUBJECT, '--body', text, '--json',
  ]);
  const out = JSON.parse(stdout);
  if (!out.ok) throw new Error(out.error?.message ?? '전송 실패');
};

const poll = async () => {
  const found = discover();
  const sources = [];
  tickets = await Promise.all(found.map(async (t) => {
    const { s, error } = await ticketState(t);
    if (s) sources.push({ s, previews: path.join(t.dir, 'previews') });
    return { key: t.key, title: s?.title ?? t.title, port: t.port, up: Boolean(s), error, summary: s ? summarize(s) : null };
  }));
  linkSources = sources;
  try {
    orchestrator = await orchestratorStatus();
  } catch (e) {
    orchestrator = { online: false, cwd: ORCH_CWD, error: e.message };
  }
  const payload = JSON.stringify({ tickets, orchestrator });
  if (payload === lastPayload) return;
  lastPayload = payload;
  for (const res of clients) res.write(`event: tickets\ndata: ${payload}\n\n`);
};

const gh = async (args) => {
  const { stdout } = await run('gh', args, { maxBuffer: 16 * 1024 * 1024 });
  return JSON.parse(stdout);
};

const kst = (iso) =>
  iso ? new Date(new Date(iso).getTime() + 9 * 3600_000).toISOString().slice(5, 16).replace('T', ' ') : '';

const REVIEW = { APPROVED: '승인됨', CHANGES_REQUESTED: '변경 요청', REVIEW_REQUIRED: '리뷰 대기' };
const PASS = new Set(['SUCCESS', 'NEUTRAL', 'SKIPPED']);
const FAIL = new Set(['FAILURE', 'ERROR', 'TIMED_OUT', 'CANCELLED', 'ACTION_REQUIRED', 'STARTUP_FAILURE']);

const checksOf = (rollup) => {
  const checks = rollup ?? [];
  const result = (c) => c.conclusion || c.state;
  return {
    total: checks.length,
    pass: checks.filter((c) => PASS.has(result(c))).length,
    failing: checks.filter((c) => FAIL.has(result(c))).map((c) => c.name ?? c.context),
  };
};

// 링크 호버 설명(GET /api/link). 티켓 대시보드 server.mjs 에 같은 코드가 있다.
// PR 은 폴링해 둔 상태를 먼저 쓰고, 없으면 gh 로 가져와 2분 캐시한다. gh 인자는 아래 정규식을 통과한 값만 쓴다.
const LINK_PR_MS = 2 * 60_000;
const linkPrs = new Map();
const GH_PR = /^\/([A-Za-z0-9][A-Za-z0-9-]{0,38})\/([A-Za-z0-9._-]{1,100})\/pull\/(\d{1,7})(?:\/|$)/;
const JIRA_BROWSE = /^\/browse\/([A-Z][A-Z0-9]{1,9}-\d{1,7})\/?$/;
const SLACK_MSG = /^\/archives\/([A-Z0-9]{6,15})\/p(\d{10})(\d{6})\/?$/;
const PR_BADGE = { MERGED: ['merged', '병합'], CLOSED: ['closed', '닫힘'] };

const clip = (s, n) => {
  const v = String(s ?? '').replace(/\s+/g, ' ').trim();
  return v.length > n ? `${v.slice(0, n - 1)}…` : v;
};

const readJson = (file) => {
  try {
    return JSON.parse(fs.readFileSync(file, 'utf8'));
  } catch {
    return null;
  }
};

const parseLink = (raw) => {
  if (!raw || raw.length > 2000) return null;
  let u;
  try {
    u = new URL(raw);
  } catch {
    return null;
  }
  if (u.protocol !== 'https:' && u.protocol !== 'http:') return null;
  let m;
  if (u.hostname === 'github.com' && (m = u.pathname.match(GH_PR))) return { kind: 'pr', repo: `${m[1]}/${m[2]}`, number: Number(m[3]) };
  if (u.hostname.endsWith('.atlassian.net') && (m = u.pathname.match(JIRA_BROWSE))) return { kind: 'jira', key: m[1] };
  if (u.hostname.endsWith('.slack.com') && (m = u.pathname.match(SLACK_MSG))) {
    const thread = u.searchParams.get('thread_ts') ?? '';
    return { kind: 'slack', channel: m[1], ts: `${m[2]}.${m[3]}`, thread: /^\d{10}\.\d{6}$/.test(thread) ? thread : null };
  }
  let p = u.pathname;
  try {
    p = decodeURIComponent(p);
  } catch {}
  return { kind: 'link', where: clip(`${u.host}${p === '/' ? '' : p}`, 100) };
};

const prInfo = (t, sources, allowFetch) => {
  const url = `https://github.com/${t.repo}/pull/${t.number}`.toLowerCase();
  const polled = sources.flatMap(({ s }) => Object.values(s.github?.prs ?? {})).find((p) => p.url?.toLowerCase() === url);
  if (polled) return polled;
  const hit = linkPrs.get(url);
  if (hit && Date.now() - hit.at < LINK_PR_MS) return hit.data;
  if (!allowFetch) return null;
  const data = gh([
    'pr', 'view', String(t.number), '--repo', t.repo, '--json',
    'title,state,isDraft,reviewDecision,author,baseRefName,headRefName,statusCheckRollup,mergedAt,updatedAt',
  ]).then((pr) => ({
    title: pr.title, state: pr.state, isDraft: pr.isDraft, reviewDecision: pr.reviewDecision, author: pr.author?.login,
    base: pr.baseRefName, headRef: pr.headRefName, mergedAt: pr.mergedAt, updatedAt: pr.updatedAt, checks: checksOf(pr.statusCheckRollup),
  }));
  data.catch(() => linkPrs.delete(url));
  linkPrs.set(url, { at: Date.now(), data });
  return data;
};

const describePr = (t, p) => {
  const [state, stateLabel] = PR_BADGE[p.state] ?? (p.isDraft ? ['draft', '초안'] : ['open', '열림']);
  const { pass, total, failing } = p.checks ?? { pass: 0, total: 0, failing: [] };
  return {
    kind: 'pr', label: `PR · ${t.repo.split('/')[1]} #${t.number}`, title: p.title, state, stateLabel,
    lines: [
      `대상 브랜치 ${p.base}${p.headRef ? ` ← ${p.headRef}` : ''}`,
      `작성 ${p.author ?? '—'} · ${p.state === 'MERGED' ? `병합 ${kst(p.mergedAt)}` : `갱신 ${kst(p.updatedAt)}`}`,
      [REVIEW[p.reviewDecision] ?? '리뷰 결정 없음', total ? `체크 ${pass}/${total}` : '체크 없음', failing.length ? `실패 ${failing.slice(0, 3).join(', ')}` : '']
        .filter(Boolean).join(' · '),
    ],
  };
};

const jiraLines = (s, key) => {
  const re = new RegExp(`(?<![A-Z0-9-])${key}(?!\\d)`);
  const lines = [];
  if (s.key === key) lines.push(`대시보드 「${s.title}」`);
  for (const x of s.streams) {
    if (x.ticket === key) lines.push(`작업 세션 「${x.title}」 ${x.items.filter((it) => it.done).length}/${x.items.length} 완료`);
    for (const it of x.items) if (re.test(it.text)) lines.push(`#${it.no} ${clip(it.text, 100)}${it.done ? ' · 완료' : ''}`);
  }
  for (const o of Object.values(s.outputs ?? {})) {
    if (re.test(`${o.name} ${o.desc ?? ''}`)) lines.push(`결과물 ${o.name}${o.desc ? ` — ${o.desc}` : ''}`);
  }
  const row = (s.vault?.rows ?? []).find((r) => re.test(r.content));
  if (row) lines.push(`기록 #${row.n} ${clip(row.content, 100)}`);
  return lines;
};

// sources: [{ s: 대시보드 상태(/api/state 형태), previews: Slack 캐시 폴더 }]
const describeLink = async (t, sources, allowFetch) => {
  if (t.kind === 'pr') {
    const p = await prInfo(t, sources, allowFetch);
    return p ? describePr(t, p) : { kind: 'pr', label: `PR · ${t.repo.split('/')[1]} #${t.number}`, title: null, lines: [] };
  }
  if (t.kind === 'jira') {
    const lines = sources.flatMap(({ s }) => jiraLines(s, t.key).map((l) => (sources.length > 1 ? `${s.key} · ${l}` : l)));
    return { kind: 'jira', label: 'Jira', title: t.key, lines: lines.length > 5 ? [...lines.slice(0, 4), `외 ${lines.length - 4}건`] : lines };
  }
  if (t.kind === 'slack') {
    const tss = [t.thread, t.ts].filter(Boolean);
    const ref = sources.flatMap(({ s }) => s.streams.flatMap((x) => x.items)).flatMap((it) => it.refs ?? [])
      .find((r) => r.type === 'slack' && r.channel === t.channel && tss.includes(r.ts));
    const cache = sources.flatMap(({ previews }) => tss.map((ts) => readJson(path.join(previews, `slack-${t.channel}-${ts}.json`)))).find(Boolean);
    const first = cache?.messages?.[0];
    return {
      kind: 'slack', label: `Slack · ${t.channel}`, title: ref?.title ?? null,
      lines: first
        ? [`${first.author} · ${first.time}`, clip(first.text, 160), `메시지 ${cache.messages.length}개 · ${kst(cache.fetchedAt)} 가져옴`]
        : ['가져온 프리뷰 없음(할 일 「프리뷰」에서 가져옴)'],
    };
  }
  return { kind: 'link', label: '링크', title: null, lines: [t.where] };
};

const json = (res, code, body) => {
  res.writeHead(code, { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store' });
  res.end(JSON.stringify(body));
};

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, 'http://localhost');
  if (req.method === 'GET' && url.pathname === '/') {
    res.writeHead(200, { 'content-type': 'text/html; charset=utf-8', 'cache-control': 'no-store' });
    res.end(fs.readFileSync(path.join(DIR, 'index.html')));
    return;
  }
  if (req.method === 'GET' && url.pathname === '/api/tickets') return json(res, 200, { tickets, orchestrator });
  if (req.method === 'GET' && url.pathname === '/api/link') {
    if (req.headers.origin && !ORIGINS.has(req.headers.origin)) return json(res, 403, { error: '허용되지 않은 출처' });
    const target = parseLink(url.searchParams.get('url'));
    if (!target) return json(res, 400, { error: 'http(s) 링크만 받음' });
    const sameSite = !req.headers['sec-fetch-site'] || req.headers['sec-fetch-site'] === 'same-origin';
    try {
      return json(res, 200, await describeLink(target, linkSources, sameSite));
    } catch (e) {
      return json(res, 502, { error: String(e.stderr || e.message || e).trim().slice(0, 200) });
    }
  }
  if (req.method === 'GET' && url.pathname === '/api/orchestrator/messages') {
    const s = await findOrchestrator();
    return json(res, 200, { orchestrator: await orchestratorStatus(), messages: s?.sessionId ? readConversation(s.sessionId) : [] });
  }
  if (req.method === 'GET' && url.pathname === '/api/events') {
    res.writeHead(200, { 'content-type': 'text/event-stream', 'cache-control': 'no-store', connection: 'keep-alive' });
    res.write(`event: tickets\ndata: ${JSON.stringify({ tickets, orchestrator })}\n\n`);
    clients.add(res);
    req.on('close', () => clients.delete(res));
    return;
  }
  if (req.method === 'POST' && url.pathname === '/api/orchestrator/send') {
    if (!(req.headers['content-type'] ?? '').startsWith('application/json')) return json(res, 415, { error: 'application/json 만 받음' });
    if (req.headers.origin && !ORIGINS.has(req.headers.origin)) return json(res, 403, { error: '허용되지 않은 출처' });
    let body = '';
    for await (const chunk of req) {
      body += chunk;
      if (body.length > 1e5) return json(res, 413, { error: '너무 김' });
    }
    const text = String(JSON.parse(body || '{}').text ?? '').trim();
    if (!text) return json(res, 400, { error: '빈 메시지' });
    const s = await findOrchestrator();
    if (!s) return json(res, 409, { error: `오케스트레이션 세션이 꺼져 있음(${ORCH_CWD})` });
    try {
      await relay(s, text);
      return json(res, 200, { ok: true });
    } catch (e) {
      return json(res, 502, { error: String(e.stderr || e.message || e).trim().slice(0, 300) });
    }
  }
  json(res, 404, { error: 'not found' });
});

// 티켓 모듈이 한 프로세스에 모여 있어, 한 티켓의 예외로 전체가 내려가지 않게 기록만 남긴다.
process.on('uncaughtException', (e) => console.error('[uncaught]', e));
process.on('unhandledRejection', (e) => console.error('[unhandled]', e));

setInterval(poll, POLL_MS);
setInterval(() => {
  for (const res of clients) res.write(': ping\n\n');
}, 25_000);
poll();
server.listen(PORT, '127.0.0.1', () => console.log(`통합 대시보드 http://127.0.0.1:${PORT}`));
