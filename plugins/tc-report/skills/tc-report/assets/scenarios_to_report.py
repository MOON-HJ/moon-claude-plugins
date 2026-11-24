#!/usr/bin/env python3
"""TEST_SCENARIOS.md + 자동화 결과 + 판단(overrides) → report.json.

사용:
    python3 scenarios_to_report.py --scenarios TEST_SCENARIOS.md \
        --results e2e-results.json [--results more.json] \
        --media media-map.json --overrides overrides.json -o report.json

입력
- scenarios: 테스트 시나리오 마크다운 문서. `### N. 그룹` 아래의
  `| TC ID | 케이스 | 사전조건 | 단계 | 기대 결과 | P | 결과 |` 표를 읽는다(7열 미만 행 = 추적표, 무시).
  단계는 ` → `로 쪼갠다.
- results: Playwright JSON 리포터 결과. 테스트 제목에 든 `TC-NN`을 그 테스트의 결과로 판정한다
  (한 테스트가 여러 TC를 묶으면 전부 같은 결과).
- media: collect_media.py 가 만든 media-map.json. TC별 영상·캡처를 붙인다.
- overrides: 사람이 판단한 것 — 아래 스키마. 자동 결과보다 우선한다.

overrides.json
{
  "meta": {...report.meta...},          # 문자열 안의 {auto} {tests} {passed} {verified} {duration} 치환
  "findings": [...], "notes": [...],    # report.json 그대로
  "scopeRules": [                       # 자동 결과도 개별 지정도 없는 TC에 적용(위에서부터 첫 일치)
    {"groups": ["5.", "9."], "status": "N/A", "note": "범위 밖 사유"},
    {"ids": ["TC-63"], "status": "N/A", "note": "..."}
  ],
  "cases": {
    "TC-07": {
      "status": "보류",                  # 자동 판정을 덮는다(생략하면 자동 판정 유지)
      "note": "...",
      "obs": ["추가 관찰(문자열은 ok)", {"kind": "ng", "text": "..."}],
      "shots": [{"src": "app-x-02.webp", "cap": "..."}],   # 있으면 media-map 캡처 대신 쓴다
      "videos": [{"src": "videos/app-x.mp4", "cap": "..."}],# 있으면 media-map 영상 대신 쓴다
      "verifiedAt": "2026-10-01 19:22 KST",
      "autoObs": false                   # 자동화 관찰 줄을 빼고 싶을 때
    }
  }
}
"""
import argparse
import datetime
import json
import re

KST = datetime.timezone(datetime.timedelta(hours=9))
TC_RE = re.compile(r"TC-\d+")


def parse_scenarios(path):
    cases, group = [], ""
    for line in open(path, encoding="utf-8").read().splitlines():
        m = re.match(r"^### (\d+)\. (.+)$", line)
        if m:
            group = f"{m.group(1)}. {re.sub(r' [(（].*[)）]$', '', m.group(2))}"
            continue
        if not line.startswith("| TC-"):
            continue
        cols = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cols) < 7:
            continue
        tcid, title, pre, steps, expected, prio = cols[:6]
        cases.append({
            "id": tcid, "group": group, "title": title, "priority": prio,
            "pre": {"—": "", "〃": "위와 같음"}.get(pre, pre),
            "steps": [s.strip() for s in steps.split(" → ") if s.strip()],
            "expected": [expected] if expected else [],
        })
    return cases


def walk_specs(suite):
    for spec in suite.get("specs", []):
        yield spec
    for child in suite.get("suites", []):
        yield from walk_specs(child)


def load_results(paths):
    auto, stats = {}, {"tests": 0, "passed": 0, "duration": 0.0, "start": None}
    for path in paths:
        data = json.load(open(path, encoding="utf-8"))
        st = data.get("stats", {})
        start = datetime.datetime.fromisoformat(st["startTime"].replace("Z", "+00:00")).astimezone(KST)
        stats["start"] = max(filter(None, [stats["start"], start]))
        stats["duration"] += st.get("duration", 0) / 1000
        for suite in data.get("suites", []):
            for spec in walk_specs(suite):
                for t in spec.get("tests", []):
                    r = (t.get("results") or [{}])[-1]
                    stats["tests"] += 1
                    stats["passed"] += r.get("status") == "passed"
                    for tc in TC_RE.findall(spec["title"]):
                        auto.setdefault(tc, []).append({
                            "title": spec["title"], "status": r.get("status"),
                            "sec": r.get("duration", 0) / 1000,
                            "err": ((r.get("error") or {}).get("message") or "")[:240],
                        })
    return auto, stats


def as_obs(items):
    out = []
    for o in items or []:
        out.append({"kind": "ok", "text": o} if isinstance(o, str) else o)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenarios", required=True)
    ap.add_argument("--results", action="append", default=[])
    ap.add_argument("--media")
    ap.add_argument("--overrides", required=True)
    ap.add_argument("-o", "--output", required=True)
    a = ap.parse_args()

    cases = parse_scenarios(a.scenarios)
    auto, stats = load_results(a.results) if a.results else ({}, {"tests": 0, "passed": 0, "duration": 0, "start": None})
    media = json.load(open(a.media, encoding="utf-8")) if a.media else {}
    ov = json.load(open(a.overrides, encoding="utf-8"))
    verified = stats["start"].strftime("%Y-%m-%d %H:%M KST") if stats["start"] else ""

    for c in cases:
        tc = c["id"]
        o = ov.get("cases", {}).get(tc, {})
        runs = auto.get(tc, [])
        if runs:
            ok = all(r["status"] == "passed" for r in runs)
            c["status"] = "Pass" if ok else "Fail"
            c["verifiedAt"] = verified
            if o.get("autoObs", True):
                c["obs"] = [{
                    "kind": "ok" if r["status"] == "passed" else "err",
                    "text": f"자동화: {r['title']} ({r['sec']:.1f}s)" + ("" if r["status"] == "passed" else f" — {r['err']}"),
                } for r in runs]
        elif not o.get("status"):
            for rule in ov.get("scopeRules", []):
                if tc in rule.get("ids", []) or any(c["group"].startswith(g) for g in rule.get("groups", [])):
                    c["status"], c["note"] = rule["status"], rule.get("note", "")
                    break
        for key in ("status", "note", "verifiedAt"):
            if o.get(key):
                c[key] = o[key]
        if o.get("obs"):
            c["obs"] = c.get("obs", []) + as_obs(o["obs"])
        mm = media.get(tc, {})
        shots = o.get("shots", mm.get("shots", []))
        videos = o.get("videos", mm.get("videos", []))
        if shots:
            c["shots"] = shots
        if videos:
            c["videos"] = videos

    counts = {}
    for c in cases:
        counts[c.get("status", "미실행")] = counts.get(c.get("status", "미실행"), 0) + 1
    fill = {
        "auto": len([c for c in cases if c["id"] in auto]),
        "tests": stats["tests"], "passed": stats["passed"],
        "verified": verified, "duration": f"{stats['duration']:.1f}",
    }

    def sub(v):
        if isinstance(v, str):
            for k, x in fill.items():
                v = v.replace("{" + k + "}", str(x))
            return v
        if isinstance(v, list):
            return [sub(x) for x in v]
        if isinstance(v, dict):
            return {k: sub(x) for k, x in v.items()}
        return v

    report = {
        "meta": sub(ov.get("meta", {})),
        "findings": ov.get("findings", []),
        "cases": cases,
        "notes": ov.get("notes", []),
    }
    report["meta"].setdefault("generatedAt", verified)
    with open(a.output, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    print(f"cases {len(cases)} · 자동화 TC {fill['auto']} · 테스트 {stats['passed']}/{stats['tests']} 통과 · {counts}")


if __name__ == "__main__":
    main()
