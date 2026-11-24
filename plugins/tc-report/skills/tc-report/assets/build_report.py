#!/usr/bin/env python3
"""테스트케이스 report.json → QA 리포트 HTML (Claude Code 아티팩트용).

사용:
    python3 build_report.py report.json report.html [--shots-dir DIR]

JSON 스키마는 스킬 SKILL.md를 따른다. 신뢰 경계:
- meta.sub, findings[].body, findings[].impact, notes[].body 는 **HTML 그대로 삽입**
  (<b>, <code> 등 제한적 마크업 허용 — 작성자가 안전하게 쓴다는 전제).
- 그 외 모든 필드는 이스케이프된다.

이미지: shots[].src 가 data: URI면 그대로, 파일 경로면 --shots-dir 기준으로 읽어
base64 임베드한다. 아티팩트 한도(16MB)를 넘으면 경고를 낸다.

영상: videos[].src 는 임베드하지 않고 상대 경로 그대로 둔다(예: "videos/tc-01.webm").
발행할 때 Artifact `files`로 같은 경로에 함께 올려야 재생된다. 썸네일을 누르면 라이트박스에서
크게 재생되고, 같은 케이스의 캡처와 좌우로 오간다.
"""
import argparse
import base64
import html
import json
import os
import sys

# ── 상태 정규화 ──────────────────────────────────────────────
# key: (라벨, 배지 class, 막대 seg class, 필터 토큰)
STATUS = {
    "pass":    ("Pass",  "p", "p", "Pass"),
    "fail":    ("Fail",  "f", "f", "Fail"),
    "hold":    ("보류",   "h", "h", "Hold"),
    "na":      ("N/A",   "n", "n", "NA"),
    "pending": ("미실행", "n", "n", "Pending"),
}
STATUS_ALIASES = {
    "pass": "pass", "passed": "pass", "성공": "pass", "통과": "pass", "ok": "pass", "o": "pass", "✅": "pass",
    "fail": "fail", "failed": "fail", "실패": "fail", "결함": "fail", "ng": "fail", "x": "fail", "❌": "fail",
    "보류": "hold", "blocked": "hold", "block": "hold", "hold": "hold", "재확인": "hold",
    "n/a": "na", "na": "na", "n-a": "na", "제외": "na", "해당없음": "na", "skip": "na", "skipped": "na",
    "": "pending", "미실행": "pending", "pending": "pending", "todo": "pending", "-": "pending",
}
MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".webp": "image/webp", ".gif": "image/gif"}


def norm_status(v):
    return STATUS_ALIASES.get(str(v or "").strip().lower(), "pending")


def esc(s):
    return html.escape(str(s), quote=True)


def as_list(v):
    if v is None:
        return []
    if isinstance(v, list):
        return [str(x) for x in v if str(x).strip()]
    return [str(v)] if str(v).strip() else []


def data_uri(src, shots_dir):
    if not src or str(src).startswith("data:"):
        return src
    path = src if os.path.isabs(src) else os.path.join(shots_dir or ".", src)
    if not os.path.isfile(path):
        print(f"  경고: 캡처 파일 없음 — {path}", file=sys.stderr)
        return None
    ext = os.path.splitext(path)[1].lower()
    mime = MIME.get(ext)
    if not mime:
        print(f"  경고: 지원하지 않는 이미지 형식 — {path}", file=sys.stderr)
        return None
    with open(path, "rb") as f:
        return f"data:{mime};base64,{base64.b64encode(f.read()).decode()}"


# ── 정적 CSS/JS (QA 리포트 디자인) ──────
CSS = """
:root {
  --ground:#F3F5F7; --surface:#FFFFFF; --surface-2:#FAFBFC; --line:#DFE4EA; --line-soft:#EAEEF2;
  --ink:#161B22; --ink-2:#3D4753; --muted:#6E7885;
  --accent:#8A5A00; --accent-fill:#FFC93D; --accent-soft:#FFF6DF;
  --ok:#1C6B4F; --ok-soft:#E4F2EB; --ng:#A32B21; --ng-soft:#FBE9E7; --na:#5E6874; --na-soft:#ECEFF2;
  --sh:0 1px 2px rgba(22,27,34,.05), 0 8px 24px -16px rgba(22,27,34,.18);
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --ground:#0E1216; --surface:#161B21; --surface-2:#1B2128; --line:#2A323B; --line-soft:#222932;
    --ink:#E8EDF3; --ink-2:#BCC5D0; --muted:#8B96A3;
    --accent:#FFC93D; --accent-fill:#8A6A16; --accent-soft:#2A2210;
    --ok:#69C79E; --ok-soft:#12291F; --ng:#F0938A; --ng-soft:#2B1614; --na:#9AA5B1; --na-soft:#1F262E;
    --sh:0 1px 2px rgba(0,0,0,.4), 0 10px 28px -18px rgba(0,0,0,.8);
  }
}
:root[data-theme="dark"] {
  --ground:#0E1216; --surface:#161B21; --surface-2:#1B2128; --line:#2A323B; --line-soft:#222932;
  --ink:#E8EDF3; --ink-2:#BCC5D0; --muted:#8B96A3;
  --accent:#FFC93D; --accent-fill:#8A6A16; --accent-soft:#2A2210;
  --ok:#69C79E; --ok-soft:#12291F; --ng:#F0938A; --ng-soft:#2B1614; --na:#9AA5B1; --na-soft:#1F262E;
  --sh:0 1px 2px rgba(0,0,0,.4), 0 10px 28px -18px rgba(0,0,0,.8);
}
* { box-sizing:border-box; }
body {
  margin:0; background:var(--ground); color:var(--ink);
  font-family:"IBM Plex Sans KR","Apple SD Gothic Neo",system-ui,sans-serif;
  font-size:15px; line-height:1.7; -webkit-font-smoothing:antialiased;
}
.wrap { max-width:1080px; margin:0 auto; padding:40px 24px 96px; }
h1,h2,h3,h4,h5 { font-family:"Gothic A1","Apple SD Gothic Neo",system-ui,sans-serif; text-wrap:balance; margin:0; }
code { font-family:"IBM Plex Mono",ui-monospace,monospace; font-size:.88em;
  background:var(--surface-2); border:1px solid var(--line-soft); border-radius:4px; padding:1px 5px; }
a { color:var(--accent); }
:focus-visible { outline:2px solid var(--accent); outline-offset:2px; border-radius:4px; }
header.top { border-bottom:2px solid var(--ink); padding-bottom:20px; margin-bottom:32px; }
.eyebrow { font-family:"IBM Plex Mono",monospace; font-size:12px; letter-spacing:.14em;
  text-transform:uppercase; color:var(--accent); font-weight:600; }
header.top h1 { font-size:clamp(28px,4.2vw,42px); font-weight:800; letter-spacing:-.02em; margin:8px 0 12px; }
.sub { color:var(--ink-2); max-width:62ch; margin:0; }
dl.facts { display:grid; grid-template-columns:repeat(auto-fit,minmax(190px,1fr)); gap:2px 24px;
  margin:22px 0 0; font-size:13.5px; }
dl.facts div { display:flex; gap:8px; padding:5px 0; border-top:1px solid var(--line-soft); }
dl.facts dt { color:var(--muted); min-width:64px; flex:none; }
dl.facts dd { margin:0; color:var(--ink-2); word-break:break-all; }
.progress { background:var(--surface); border:1px solid var(--line); border-radius:12px;
  padding:16px 20px; box-shadow:var(--sh); margin-bottom:20px; }
.progress .phead { display:flex; align-items:baseline; gap:12px; margin-bottom:8px; }
.progress .phead > span:first-child { font-size:13px; font-weight:700; letter-spacing:.04em; color:var(--muted); }
.progress .phead b { font-family:"Gothic A1",sans-serif; font-size:26px; font-weight:800;
  font-variant-numeric:tabular-nums; }
.progress .pnum { font-family:"IBM Plex Mono",monospace; font-size:13px; color:var(--muted);
  margin-left:auto; font-variant-numeric:tabular-nums; }
.progress .track { height:12px; margin:0; }
.summary { display:grid; grid-template-columns:minmax(0,1fr) minmax(0,1.15fr); gap:20px; margin-bottom:44px; }
@media (max-width:760px) { .summary { grid-template-columns:1fr; } }
.scores { display:grid; grid-template-columns:repeat(3,1fr); gap:12px; }
.score { background:var(--surface); border:1px solid var(--line); border-radius:12px; padding:16px 14px;
  box-shadow:var(--sh); }
.score b { display:block; font-family:"Gothic A1",sans-serif; font-size:34px; font-weight:800;
  line-height:1.1; font-variant-numeric:tabular-nums; }
.score span { font-size:12.5px; color:var(--muted); }
.score.p b { color:var(--ok); } .score.f b { color:var(--ng); } .score.n b { color:var(--na); }
.bars { background:var(--surface); border:1px solid var(--line); border-radius:12px; padding:18px 20px;
  box-shadow:var(--sh); display:grid; gap:14px; align-content:start; }
.bars h2 { font-size:13px; font-weight:700; letter-spacing:.04em; color:var(--muted); margin-bottom:2px; }
.bar .barhead { display:flex; justify-content:space-between; font-size:13px; font-weight:600; }
.barnum { font-family:"IBM Plex Mono",monospace; color:var(--muted); }
.track { display:flex; height:8px; border-radius:99px; overflow:hidden; background:var(--line-soft); margin:5px 0 3px; }
.seg.p { background:var(--ok); } .seg.f { background:var(--ng); }
.seg.h { background:var(--accent-fill); } .seg.n { background:var(--na); }
.barlegend { font-size:11.5px; color:var(--muted); font-variant-numeric:tabular-nums; }
section { margin-bottom:52px; }
.shead { display:flex; align-items:baseline; gap:12px; margin-bottom:18px;
  border-bottom:1px solid var(--line); padding-bottom:10px; }
.shead h2 { font-size:21px; font-weight:800; letter-spacing:-.01em; }
.shead .count { font-family:"IBM Plex Mono",monospace; font-size:13px; color:var(--muted); }
.findings { display:grid; gap:14px; }
.finding { background:var(--surface); border:1px solid var(--line); border-left:4px solid var(--na);
  border-radius:10px; padding:18px 20px; box-shadow:var(--sh); }
.finding.sev-critical { border-left-color:var(--ng); }
.finding.sev-high { border-left-color:var(--accent-fill); }
.finding.sev-medium { border-left-color:var(--line); }
.finding.sev-note { border-left-color:var(--line-soft); }
.finding.sev-resolved { border-left-color:var(--ok); opacity:.72; }
.sev-resolved .sev { background:var(--ok-soft); color:var(--ok); }
.finding header { display:flex; align-items:center; gap:10px; margin-bottom:8px; flex-wrap:wrap; }
.sev { font-size:11px; font-weight:700; letter-spacing:.06em; padding:2px 8px; border-radius:99px;
  background:var(--na-soft); color:var(--na); }
.sev-critical .sev { background:var(--ng-soft); color:var(--ng); }
.sev-high .sev { background:var(--accent-soft); color:var(--accent); }
.fmeta { font-size:12px; color:var(--muted); }
.finding h3 { font-size:17px; font-weight:700; line-height:1.5; margin-bottom:8px; }
.fbody { margin:0 0 10px; color:var(--ink-2); font-size:14.5px; }
.fimpact { margin:0; font-size:13.5px; color:var(--ink-2);
  background:var(--surface-2); border-radius:8px; padding:9px 12px; }
.fimpact span { font-weight:700; color:var(--ink); margin-right:8px; }
.filters { display:flex; gap:8px; flex-wrap:wrap; margin-bottom:14px; }
.filters button { font:inherit; font-size:13px; padding:5px 13px; border-radius:99px;
  border:1px solid var(--line); background:var(--surface); color:var(--ink-2); cursor:pointer; }
.filters button[aria-pressed="true"] { background:var(--ink); color:var(--ground); border-color:var(--ink); }
.tablebox { overflow-x:auto; border:1px solid var(--line); border-radius:12px; background:var(--surface);
  box-shadow:var(--sh); }
table.cases { width:100%; border-collapse:collapse; min-width:680px; }
table.cases th { text-align:left; font-size:12px; letter-spacing:.04em; color:var(--muted);
  font-weight:600; padding:10px 14px; border-bottom:1px solid var(--line); background:var(--surface-2); }
table.cases td { padding:10px 14px; border-bottom:1px solid var(--line-soft); vertical-align:top; font-size:14px; }
tr.row:last-of-type td { border-bottom:none; }
tr.grp td { background:var(--surface-2); font-family:"Gothic A1",sans-serif; font-weight:700;
  font-size:13px; color:var(--ink-2); border-bottom:1px solid var(--line); }
td.id { font-family:"IBM Plex Mono",monospace; font-size:12.5px; color:var(--muted); white-space:nowrap; }
td.title { width:52%; }
td.meta { white-space:nowrap; }
.tag { font-size:11px; padding:1px 7px; border-radius:99px; border:1px solid var(--line); color:var(--ink-2); }
.tag.t-e { background:var(--accent-soft); border-color:transparent; color:var(--accent); }
.pri { font-family:"IBM Plex Mono",monospace; font-size:11.5px; color:var(--muted); }
.badge { font-size:12px; font-weight:600; padding:2px 10px; border-radius:99px; white-space:nowrap; }
.badge.p { background:var(--ok-soft); color:var(--ok); }
.badge.f { background:var(--ng-soft); color:var(--ng); }
.badge.h { background:var(--accent-soft); color:var(--accent); }
.badge.n { background:var(--na-soft); color:var(--na); }
.toggle { font:inherit; font-size:12.5px; padding:3px 10px; border-radius:6px; cursor:pointer;
  border:1px solid var(--line); background:var(--surface-2); color:var(--ink-2); white-space:nowrap; }
.toggle[aria-expanded="true"] { background:var(--ink); color:var(--ground); border-color:var(--ink); }
tr.detail td { background:var(--surface-2); padding:16px 18px 20px; }
.note { margin:0 0 10px; font-size:13.5px; color:var(--ng); }
.specgrid { display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:12px; margin:0 0 14px; }
.specgrid > div { background:var(--surface); border:1px solid var(--line-soft); border-radius:8px; padding:10px 14px; }
.specgrid h5 { font-size:11.5px; letter-spacing:.06em; color:var(--muted); margin-bottom:4px; }
.specgrid p, .specgrid ol, .specgrid ul { margin:0; font-size:13.5px; color:var(--ink-2); padding-left:0; }
.specgrid ol { padding-left:18px; } .specgrid ul { list-style:none; }
.specgrid li { margin:2px 0; }
ul.obslist { list-style:none; margin:0 0 14px; padding:0; display:grid; gap:4px; }
li.obs { font-size:13.5px; color:var(--ink-2); padding-left:20px; position:relative; word-break:break-word; }
li.obs::before { content:"·"; position:absolute; left:6px; color:var(--muted); }
li.obs.ok::before { content:"✓"; color:var(--ok); font-size:12px; }
li.obs.ng::before { content:"✕"; color:var(--ng); font-size:12px; }
li.obs.err::before { content:"!"; color:var(--ng); font-weight:700; }
.shots { display:grid; grid-template-columns:repeat(auto-fill,minmax(230px,1fr)); gap:12px; }
.shots figure { margin:0; border:1px solid var(--line); border-radius:8px; overflow:hidden; background:var(--surface); }
.shots img { display:block; width:100%; height:auto; }
.shots video { display:block; width:100%; height:auto; aspect-ratio:16/10; object-fit:cover; object-position:top left; background:var(--surface-2); }
.shots .vid .zoom { position:relative; }
.shots .play { position:absolute; left:50%; top:50%; transform:translate(-50%,-50%); width:44px; height:44px;
  border-radius:50%; display:grid; place-items:center; font-size:16px; padding-left:3px;
  background:rgba(8,11,14,.72); color:#fff; pointer-events:none; }
.shots .vid figcaption b { color:var(--accent); font-weight:600; margin-right:2px; }
.shots .zoom { display:block; width:100%; padding:0; border:0; background:none; cursor:zoom-in; }
.shots .zoom:focus-visible { outline:2px solid var(--accent); outline-offset:2px; }
.shots figcaption { font-size:11.5px; color:var(--muted); padding:6px 8px; border-top:1px solid var(--line-soft); }
.thumbcell { width:180px; padding:6px 8px; }
.rowthumb { width:172px; height:108px; object-fit:cover; object-position:top left; border-radius:6px;
  border:1px solid var(--line); display:block; background:var(--surface-2); }
.nothumb { color:var(--muted); opacity:.5; }
@media (max-width:720px) { .thumbcell { width:96px; } .rowthumb { width:88px; height:56px; } }
.vstamp { margin:0 0 12px; padding:7px 12px; background:var(--surface); border:1px solid var(--line-soft);
  border-radius:8px; font-size:13px; color:var(--muted); display:inline-flex; align-items:center; gap:6px; }
.vstamp b { color:var(--ink); font-variant-numeric:tabular-nums; font-weight:600; }
.lightbox { position:fixed; inset:0; z-index:1000; display:grid; place-items:center;
  padding:clamp(16px,4vw,56px); background:rgba(8,11,14,.86);
  -webkit-backdrop-filter:blur(2px); backdrop-filter:blur(2px); }
.lightbox[hidden] { display:none; }
.lb-figure { margin:0; display:flex; flex-direction:column; align-items:center; gap:10px;
  max-width:100%; max-height:100%; overflow:auto; overscroll-behavior:contain; }
.lb-figure img { display:block; max-width:min(1600px,94vw); max-height:84vh; width:auto; height:auto;
  object-fit:contain; border-radius:10px; background:#fff;
  box-shadow:0 24px 64px -24px rgba(0,0,0,.7); }
.lb-figure img.tall { max-height:none; }
.lb-figure video { display:block; max-width:min(1600px,94vw); max-height:84vh; width:min(1280px,94vw); height:auto; background:#000; border-radius:6px; }
.lb-figure img[hidden], .lb-figure video[hidden] { display:none; }
.lb-figure figcaption { font-size:13px; color:#E8EDF3; text-align:center; max-width:min(1600px,94vw); }
.lb-figure .lb-count { display:block; margin-top:2px; font-size:11.5px; color:#8B96A3; font-variant-numeric:tabular-nums; }
.lightbox button { position:absolute; display:grid; place-items:center; border:1px solid rgba(232,237,243,.22);
  background:rgba(22,27,34,.72); color:#E8EDF3; border-radius:999px; cursor:pointer;
  font-family:inherit; line-height:1; }
.lightbox button:hover { background:rgba(22,27,34,.95); border-color:rgba(232,237,243,.45); }
.lightbox button:focus-visible { outline:2px solid var(--accent-fill); outline-offset:2px; }
.lb-close { top:16px; right:16px; width:40px; height:40px; font-size:18px; }
.lb-nav { top:50%; transform:translateY(-50%); width:44px; height:64px; font-size:26px; }
.lb-prev { left:12px; } .lb-next { right:12px; }
.lb-nav[hidden] { display:none; }
@media (max-width:640px) { .lb-nav { width:36px; height:52px; font-size:20px; } .lb-figure img { max-height:72vh; } }
.notes { display:grid; gap:2px; }
.note-item { padding:14px 0; border-top:1px solid var(--line); }
.note-item h4 { font-size:14.5px; font-weight:700; margin-bottom:5px; }
.note-item p { margin:0; font-size:14px; color:var(--ink-2); }
footer { margin-top:56px; padding-top:18px; border-top:1px solid var(--line);
  font-size:12.5px; color:var(--muted); }
@media (prefers-reduced-motion:reduce) { * { transition:none !important; animation:none !important; } }
"""

JS = """
(function () {
  document.querySelectorAll('.toggle').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var row = document.getElementById(btn.getAttribute('aria-controls'));
      var open = btn.getAttribute('aria-expanded') === 'true';
      btn.setAttribute('aria-expanded', String(!open));
      row.hidden = open;
      btn.textContent = open ? '상세' : '접기';
    });
  });
  var buttons = Array.prototype.slice.call(document.querySelectorAll('.filters button'));
  buttons.forEach(function (b) {
    b.addEventListener('click', function () {
      buttons.forEach(function (x) { x.setAttribute('aria-pressed', String(x === b)); });
      var f = b.dataset.f;
      document.querySelectorAll('tr.grp').forEach(function (g) {
        g.style.display = f === 'all' ? '' : 'none';
      });
      document.querySelectorAll('tr.row').forEach(function (r) {
        var show = f === 'all' || r.dataset.status === f || r.dataset.pri === f;
        r.style.display = show ? '' : 'none';
        var d = document.getElementById('d-' + r.querySelector('.id').textContent.trim());
        if (d && !show) {
          d.hidden = true;
          var t = r.querySelector('.toggle');
          if (t) { t.setAttribute('aria-expanded', 'false'); t.textContent = '상세'; }
        }
        if (d) d.style.display = show ? '' : 'none';
      });
    });
  });

  var box = document.getElementById('lightbox');
  if (!box) return;
  var lbFig = box.querySelector('.lb-figure');
  var lbImg = document.getElementById('lb-img');
  var lbVid = document.getElementById('lb-video');
  var lbCap = document.getElementById('lb-cap');
  var closeBtn = box.querySelector('.lb-close');
  var prevBtn = box.querySelector('.lb-prev');
  var nextBtn = box.querySelector('.lb-next');
  var group = [], index = 0, opener = null;

  function markTall() {
    var tall = lbImg.naturalWidth > 0 && lbImg.naturalHeight / lbImg.naturalWidth > 1.5;
    lbImg.classList.toggle('tall', tall);
  }
  function render() {
    var fig = group[index];
    if (!fig) return;
    var img = fig.querySelector('img');
    var vid = fig.querySelector('video');
    var capEl = fig.querySelector('figcaption');
    lbVid.pause();
    if (vid) {
      lbImg.hidden = true;
      lbImg.removeAttribute('src');
      lbVid.hidden = false;
      lbVid.src = vid.getAttribute('src').split('#')[0];
      var p = lbVid.play();
      if (p && p.catch) p.catch(function () {});
    } else {
      lbVid.hidden = true;
      lbVid.removeAttribute('src');
      lbImg.hidden = false;
      lbImg.classList.remove('tall');
      lbImg.src = img.src;
      lbImg.alt = img.alt;
      lbImg.decode ? lbImg.decode().then(markTall).catch(markTall) : markTall();
    }
    var many = group.length > 1;
    lbCap.innerHTML = '';
    lbCap.appendChild(document.createTextNode(capEl ? capEl.textContent : (img ? img.alt : '')));
    if (many) {
      var n = document.createElement('span');
      n.className = 'lb-count';
      n.textContent = (index + 1) + ' / ' + group.length;
      lbCap.appendChild(n);
    }
    prevBtn.hidden = !many;
    nextBtn.hidden = !many;
  }
  function open(fig) {
    var shots = fig.closest('.shots');
    group = shots ? Array.prototype.slice.call(shots.querySelectorAll('figure')) : [fig];
    index = Math.max(0, group.indexOf(fig));
    opener = fig.querySelector('.zoom');
    render();
    box.hidden = false;
    document.body.style.overflow = 'hidden';
    closeBtn.focus();
  }
  function close() {
    box.hidden = true;
    lbImg.removeAttribute('src');
    lbVid.pause();
    lbVid.removeAttribute('src');
    document.body.style.overflow = '';
    if (opener) opener.focus();
    opener = null;
  }
  function step(delta) {
    if (group.length < 2) return;
    index = (index + delta + group.length) % group.length;
    render();
  }
  document.querySelectorAll('.shots .zoom').forEach(function (btn) {
    btn.addEventListener('click', function () { open(btn.closest('figure')); });
  });
  closeBtn.addEventListener('click', close);
  prevBtn.addEventListener('click', function () { step(-1); });
  nextBtn.addEventListener('click', function () { step(1); });
  box.addEventListener('click', function (e) {
    if (e.target === box || e.target === lbFig) close();
  });
  document.addEventListener('keydown', function (e) {
    if (box.hidden) return;
    if (e.key === 'Escape') { e.preventDefault(); close(); }
    else if (e.key === 'ArrowLeft') { e.preventDefault(); step(-1); }
    else if (e.key === 'ArrowRight') { e.preventDefault(); step(1); }
  });
})();
"""


def bar_html(label, rows):
    """rows: {statusKey: count} → 막대 하나."""
    total = sum(rows.values())
    if total == 0:
        return ""
    segs, legend = [], []
    for key in ("pass", "fail", "hold", "na", "pending"):
        c = rows.get(key, 0)
        if c == 0:
            continue
        _label, _badge, seg, _tok = STATUS[key]
        segs.append(f'<span class="seg {seg}" style="width:{c / total * 100:.1f}%"></span>')
        legend.append(f"{_label} {c}")
    return (
        f'<div class="bar"><div class="barhead"><span>{esc(label)}</span>'
        f'<span class="barnum">{total}</span></div>'
        f'<div class="track">{"".join(segs)}</div>'
        f'<div class="barlegend">{" · ".join(legend)}</div></div>'
    )


def build(data, shots_dir):
    meta = data.get("meta", {})
    cases = data.get("cases", [])
    findings = data.get("findings", [])
    notes = data.get("notes", [])

    # 케이스 정규화
    seen_ids = set()
    for i, c in enumerate(cases, 1):
        cid = str(c.get("id") or f"TC-{i:02d}").strip()
        while cid in seen_ids:
            cid += "'"
        seen_ids.add(cid)
        c["id"] = cid
        c["_status"] = norm_status(c.get("status"))
        c["_shots"] = []
        for s in c.get("shots") or []:
            if isinstance(s, str):
                s = {"src": s}
            uri = data_uri(s.get("src"), shots_dir)
            if uri:
                c["_shots"].append({"src": uri, "cap": s.get("cap") or ""})
        c["_videos"] = [{"src": v["src"], "cap": v.get("cap") or "실행 영상"}
                        for v in c.get("videos") or [] if v.get("src")]

    counts = {k: 0 for k in STATUS}
    for c in cases:
        counts[c["_status"]] += 1
    total = len(cases)
    has_shots = any(c["_shots"] for c in cases)
    has_pri = any(c.get("priority") for c in cases)
    has_cat = any(c.get("category") for c in cases)
    has_group = any(c.get("group") for c in cases)

    # ── 헤더 ──
    out = []
    title = meta.get("title") or "QA 리포트"
    out.append(f"<title>{esc(title)}</title>")
    out.append('<link rel="preconnect" href="https://fonts.googleapis.com">')
    out.append('<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>')
    out.append('<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Gothic+A1:wght@500;700;800&family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans+KR:wght@400;500;600&display=swap">')
    out.append(f"<style>{CSS}</style>")
    out.append('<div class="wrap">')
    out.append('<header class="top">')
    if meta.get("eyebrow"):
        out.append(f'<p class="eyebrow">{esc(meta["eyebrow"])}</p>')
    out.append(f"<h1>{esc(title)}</h1>")
    if meta.get("sub"):
        out.append(f'<p class="sub">{meta["sub"]}</p>')  # 신뢰 HTML
    facts = meta.get("facts") or []
    if facts:
        out.append('<dl class="facts">')
        for dt, dd in facts:
            out.append(f"<div><dt>{esc(dt)}</dt><dd>{esc(dd)}</dd></div>")
        out.append("</dl>")
    out.append("</header>")

    # ── 진행률 (미실행이 남아 있는 동안 표시) ──
    done = total - counts["pending"]
    if total and counts["pending"]:
        pct = done / total * 100
        segs = []
        for key in ("pass", "fail", "hold", "na"):
            c = counts[key]
            if c:
                segs.append(f'<span class="seg {STATUS[key][2]}" style="width:{c / total * 100:.1f}%"></span>')
        out.append(
            f'<div class="progress"><div class="phead"><span>진행률</span>'
            f"<b>{pct:.0f}%</b>"
            f'<span class="pnum">실행 {done} / {total}</span></div>'
            f'<div class="track">{"".join(segs)}</div></div>'
        )

    # ── 요약 ──
    rest = counts["hold"] + counts["na"] + counts["pending"]
    rest_parts = [f"{STATUS[k][0]} {counts[k]}" for k in ("hold", "na", "pending") if counts[k]]
    out.append('<div class="summary"><div class="scores">')
    out.append(f'<div class="score p"><b>{counts["pass"]}</b><span>Pass</span></div>')
    out.append(f'<div class="score f"><b>{counts["fail"]}</b><span>Fail (결함)</span></div>')
    out.append(f'<div class="score n"><b>{rest}</b><span>{esc(" · ".join(rest_parts)) or "보류 · N/A · 미실행"}</span></div>')
    out.append("</div>")

    out.append('<div class="bars">')
    group_field = "category" if has_cat else ("group" if has_group else None)
    if group_field:
        out.append(f'<h2>{"구분별" if group_field == "category" else "그룹별"}</h2>')
        order, buckets = [], {}
        for c in cases:
            g = c.get(group_field) or "기타"
            if g not in buckets:
                buckets[g] = {}
                order.append(g)
            buckets[g][c["_status"]] = buckets[g].get(c["_status"], 0) + 1
        for g in order:
            out.append(bar_html(g, buckets[g]))
    else:
        out.append("<h2>전체</h2>")
        out.append(bar_html("전체", {k: v for k, v in counts.items() if v}))
    if has_pri:
        out.append('<h2 style="margin-top:6px">우선순위별</h2>')
        order, buckets = [], {}
        for c in cases:
            p = c.get("priority") or "-"
            if p not in buckets:
                buckets[p] = {}
                order.append(p)
            buckets[p][c["_status"]] = buckets[p].get(c["_status"], 0) + 1
        for p in sorted(order):
            out.append(bar_html(p, buckets[p]))
    out.append("</div></div>")

    # ── 결함·참고 ──
    if findings:
        n_defects = sum(1 for f in findings if f.get("severity") in ("critical", "high", "medium"))
        out.append("<section>")
        out.append(f'<div class="shead"><h2>확인된 결함 · 참고</h2><span class="count">결함 {n_defects} · 항목 {len(findings)}건</span></div>')
        out.append('<div class="findings">')
        for f in findings:
            sev = f.get("severity") or "note"
            out.append(f'<article class="finding sev-{esc(sev)}"><header>'
                       f'<span class="sev">{esc(f.get("tag") or sev.upper())}</span>')
            if f.get("meta"):
                out.append(f'<span class="fmeta">{esc(f["meta"])}</span>')
            out.append(f"</header><h3>{esc(f.get('title') or '')}</h3>")
            if f.get("body"):
                out.append(f'<p class="fbody">{f["body"]}</p>')  # 신뢰 HTML
            if f.get("impact"):
                out.append(f'<p class="fimpact"><span>영향</span>{f["impact"]}</p>')  # 신뢰 HTML
            out.append("</article>")
        out.append("</div></section>")

    # ── 케이스 표 ──
    out.append("<section>")
    out.append(f'<div class="shead"><h2>전체 결과</h2><span class="count">{total}건 · 상세를 눌러 스텝과 근거를 봅니다</span></div>')
    out.append('<div class="filters"><button data-f="all" aria-pressed="true">전체 ' + str(total) + "</button>")
    for key in ("pass", "fail", "hold", "na", "pending"):
        if counts[key]:
            label, _b, _s, tok = STATUS[key]
            out.append(f'<button data-f="{tok}" aria-pressed="false">{label} {counts[key]}</button>')
    if has_pri:
        for p in sorted({c.get("priority") for c in cases if c.get("priority")}):
            out.append(f'<button data-f="{esc(p)}" aria-pressed="false">{esc(p)}</button>')
    out.append("</div>")

    ncols = 4 + (1 if has_shots else 0) + 1
    out.append('<div class="tablebox"><table class="cases"><thead><tr><th>ID</th>')
    if has_shots:
        out.append("<th>결과 사진</th>")
    out.append("<th>케이스</th><th>구분</th><th>결과</th><th></th></tr></thead><tbody>")

    last_group = None
    for c in cases:
        if has_group and c.get("group") != last_group:
            last_group = c.get("group")
            if last_group:
                out.append(f'<tr class="grp"><td colspan="{ncols}">{esc(last_group)}</td></tr>')
        skey = c["_status"]
        label, badge, _seg, tok = STATUS[skey]
        pri = c.get("priority") or ""
        cat = c.get("category") or ""
        tag_cls = "tag t-e" if cat == "예외" else "tag"
        has_detail = any([c.get("pre"), as_list(c.get("steps")), as_list(c.get("expected")),
                          c.get("obs"), c.get("note"), c["_shots"], c.get("verifiedAt")])
        out.append(f'<tr class="row" data-status="{tok}"' + (f' data-pri="{esc(pri)}"' if pri else "") + ">")
        out.append(f'<td class="id"><a id="{esc(c["id"])}"></a>{esc(c["id"])}</td>')
        if has_shots:
            if c["_shots"]:
                out.append(f'<td class="thumbcell"><img class="rowthumb" loading="lazy" src="{c["_shots"][0]["src"]}" alt="{esc(c["id"])} 결과"></td>')
            else:
                out.append('<td class="thumbcell"><span class="nothumb">—</span></td>')
        out.append(f'<td class="title">{esc(c.get("title") or "")}</td>')
        meta_bits = []
        if cat:
            meta_bits.append(f'<span class="{tag_cls}">{esc(cat)}</span>')
        if pri:
            meta_bits.append(f'<span class="pri">{esc(pri)}</span>')
        out.append(f'<td class="meta">{" ".join(meta_bits) or "—"}</td>')
        out.append(f'<td class="st"><span class="badge {badge}">{label}</span></td>')
        if has_detail:
            out.append(f'<td class="exp"><button class="toggle" aria-expanded="false" aria-controls="d-{esc(c["id"])}">상세</button></td>')
        else:
            out.append('<td class="exp"></td>')
        out.append("</tr>")

        if not has_detail:
            continue
        out.append(f'<tr class="detail" id="d-{esc(c["id"])}" hidden><td colspan="{ncols}">')
        if c.get("verifiedAt"):
            vlabel = esc(c.get("verifiedLabel") or "확인 시각")
            out.append(f'<p class="vstamp">🕒 {vlabel} <b>{esc(c["verifiedAt"])}</b></p>')
        if c.get("note"):
            out.append(f'<p class="note">{esc(c["note"])}</p>')
        spec = []
        if c.get("pre"):
            spec.append(f"<div><h5>사전조건</h5><p>{esc(c['pre'])}</p></div>")
        steps = as_list(c.get("steps"))
        if steps:
            spec.append("<div><h5>스텝</h5><ol>" + "".join(f"<li>{esc(s)}</li>" for s in steps) + "</ol></div>")
        expected = as_list(c.get("expected"))
        if expected:
            spec.append("<div><h5>기대 결과</h5><ul>" + "".join(f"<li>· {esc(e)}</li>" for e in expected) + "</ul></div>")
        if spec:
            out.append(f'<div class="specgrid">{"".join(spec)}</div>')
        obs = c.get("obs") or []
        if obs:
            out.append('<ul class="obslist">')
            for o in obs:
                if isinstance(o, str):
                    o = {"text": o}
                kind = o.get("kind") or ""
                kind = kind if kind in ("ok", "ng", "err") else ""
                out.append(f'<li class="obs {kind}">{esc(o.get("text") or "")}</li>')
            out.append("</ul>")
        if c["_shots"] or c["_videos"]:
            out.append('<div class="shots">')
            for v in c["_videos"]:
                cap = v["cap"]
                out.append(f'<figure class="vid"><button type="button" class="zoom" aria-label="{esc(cap)} — 크게 재생">'
                           f'<video muted playsinline preload="metadata" src="{esc(v["src"])}#t=0.5"></video>'
                           f'<span class="play" aria-hidden="true">▶</span></button>'
                           f"<figcaption><b>영상</b> {esc(cap)}</figcaption></figure>")
            for s in c["_shots"]:
                cap = s["cap"] or "캡처"
                out.append(f'<figure><button type="button" class="zoom" aria-label="{esc(cap)} — 크게 보기">'
                           f'<img loading="lazy" src="{s["src"]}" alt="{esc(cap)}"></button>'
                           f"<figcaption>{esc(cap)}</figcaption></figure>")
            out.append("</div>")
        out.append("</td></tr>")

    out.append("</tbody></table></div></section>")

    # ── 참고 ──
    if notes:
        out.append("<section>")
        out.append(f'<div class="shead"><h2>참고</h2><span class="count">{len(notes)}건</span></div>')
        out.append('<div class="notes">')
        for n in notes:
            out.append(f'<div class="note-item"><h4>{esc(n.get("title") or "")}</h4>'
                       f'<p>{n.get("body") or ""}</p></div>')  # body는 신뢰 HTML
        out.append("</div></section>")

    footer = meta.get("footer") or f"{title} · 생성 {meta.get('generatedAt', '')}".strip(" ·")
    out.append(f"<footer>{esc(footer)}</footer>")
    out.append("</div>")
    out.append("""<div class="lightbox" id="lightbox" hidden>
  <button type="button" class="lb-close" aria-label="닫기">×</button>
  <button type="button" class="lb-nav lb-prev" aria-label="이전" hidden>‹</button>
  <figure class="lb-figure"><img id="lb-img" alt=""><video id="lb-video" controls playsinline hidden></video><figcaption id="lb-cap"></figcaption></figure>
  <button type="button" class="lb-nav lb-next" aria-label="다음" hidden>›</button>
</div>""")
    out.append(f"<script>{JS}</script>")
    return "\n".join(out), counts, total


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input", help="report.json 경로")
    ap.add_argument("output", help="출력 HTML 경로")
    ap.add_argument("--shots-dir", default=None, help="캡처 파일 기준 디렉토리")
    args = ap.parse_args()

    with open(args.input, encoding="utf-8") as f:
        data = json.load(f)
    html_out, counts, total = build(data, args.shots_dir)
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(html_out)

    size = os.path.getsize(args.output)
    print(f"생성 완료: {args.output} ({size / 1024 / 1024:.2f}MB)")
    print("판정: " + " · ".join(f"{STATUS[k][0]} {counts[k]}" for k in STATUS if counts[k]) + f" / 총 {total}건")
    if size > 15 * 1024 * 1024:
        print("경고: 15MB 초과 — 아티팩트 한도(16MB)에 근접. 캡처를 cwebp -q 80으로 줄이거나 빼세요.", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
