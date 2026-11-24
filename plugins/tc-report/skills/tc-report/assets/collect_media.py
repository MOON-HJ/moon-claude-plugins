#!/usr/bin/env python3
"""자동화 실행 산출물(캡처·영상) → 발행용 미디어 + media-map.json.

사용:
    # Playwright — JSON 리포터 결과와 test-results 디렉토리
    python3 collect_media.py playwright --results e2e-results.json \
        --test-results <앱>/test-results --pub <pub> --shots <shots> --map media-map.json

    # Maestro — --debug-output 디렉토리(--flatten-debug-output 권장)
    python3 collect_media.py maestro --debug-dir <debug> --name app-detail \
        --tc TC-38,TC-49 --caption "앱 기준선 — 상세 화면" --pub <pub> --shots <shots> --map media-map.json

결과:
- 영상은 <pub>/videos/ 에 둔다(임베드하지 않는다 — 발행할 때 Artifact files로 올린다).
  Playwright webm은 그대로, Maestro mp4는 macOS avconvert로 H.264 960x540으로 줄인다
  (원본은 15MB를 쉽게 넘어 아티팩트 파일 한도에 걸린다).
- 캡처는 <shots>/ 에 webp로 줄여 둔다(긴 변 1200px). build_report.py --shots-dir 로 넘긴다.
- media-map.json 은 TC별 {"videos": [...], "shots": [...]} — 여러 번 실행하면 누적된다.

Playwright 캡처 매핑: 테스트가 attach 한 PNG, 또는 test-results/ 바로 아래의 `tcNN*.png`
파일(예: tc01.png, tc16-confirm.png)을 TC-NN에 붙인다. 테스트 제목에 TC-NN이 여러 개면
같은 영상을 그 TC 전부에 붙인다.
"""
import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys

TC_RE = re.compile(r"TC-\d+")


def load_map(path):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {}


def add(m, tc, kind, item):
    entry = m.setdefault(tc, {"videos": [], "shots": []})
    if item not in entry[kind]:
        entry[kind].append(item)


def to_webp(src, dst, max_width=1200):
    from PIL import Image  # 지연 import — 영상만 모을 때는 필요 없다

    im = Image.open(src)
    if im.width > max_width:
        im = im.resize((max_width, round(im.height * max_width / im.width)))
    im.save(dst, "WEBP", quality=75)


def walk_specs(suite):
    for spec in suite.get("specs", []):
        yield spec
    for child in suite.get("suites", []):
        yield from walk_specs(child)


def cmd_playwright(a):
    m = load_map(a.map)
    os.makedirs(os.path.join(a.pub, "videos"), exist_ok=True)
    os.makedirs(a.shots, exist_ok=True)
    with open(a.results, encoding="utf-8") as f:
        data = json.load(f)

    videos = 0
    for suite in data.get("suites", []):
        for spec in walk_specs(suite):
            tcs = TC_RE.findall(spec["title"])
            if not tcs:
                continue
            for t in spec.get("tests", []):
                result = (t.get("results") or [{}])[-1]
                atts = result.get("attachments", [])
                vids = [x["path"] for x in atts if x.get("contentType") == "video/webm" and x.get("path")]
                if vids:
                    # 컨텍스트를 직접 연 테스트(예: 다른 계정 로그인)는 직접 attach 한 영상과
                    # 아무것도 안 한 기본 페이지 영상(수 KB)이 함께 붙는다. 순서가 일정하지 않아 가장 큰 것을 쓴다
                    vids = [p for p in vids if os.path.exists(p)] or vids
                    pick = max(vids, key=lambda p: os.path.getsize(p) if os.path.exists(p) else -1)
                    name = f"{tcs[0].lower()}.webm"
                    shutil.copy(pick, os.path.join(a.pub, "videos", name))
                    for tc in tcs:
                        add(m, tc, "videos", {"src": f"videos/{name}", "cap": spec["title"]})
                    videos += 1
                for x in atts:
                    if x.get("contentType") == "image/png" and x.get("path") and x.get("name") != "screenshot":
                        name = f"{tcs[0].lower()}-{re.sub(r'[^a-z0-9]+', '-', x['name'].lower())}.webp"
                        to_webp(x["path"], os.path.join(a.shots, name))
                        add(m, tcs[0], "shots", {"src": name, "cap": x["name"]})

    shots = 0
    for png in sorted(glob.glob(os.path.join(a.test_results, "tc*.png"))):
        base = os.path.basename(png)[:-4]
        mt = re.match(r"tc(\d+)(.*)$", base)
        if not mt:
            continue
        tc = f"TC-{int(mt.group(1)):02d}"
        name = f"{base}.webp"
        to_webp(png, os.path.join(a.shots, name))
        add(m, tc, "shots", {"src": name, "cap": base})
        shots += 1

    with open(a.map, "w", encoding="utf-8") as f:
        json.dump(m, f, ensure_ascii=False, indent=1)
    print(f"playwright: 영상 {videos}개 · 캡처 {shots}장 → {a.map}")


def cmd_maestro(a):
    m = load_map(a.map)
    os.makedirs(os.path.join(a.pub, "videos"), exist_ok=True)
    os.makedirs(a.shots, exist_ok=True)
    tcs = [t.strip() for t in a.tc.split(",") if t.strip()]

    shots = []
    for png in sorted(glob.glob(os.path.join(a.debug_dir, "**", "takeScreenshot", "*.png"), recursive=True)):
        name = f"{a.name}-{os.path.basename(png)[:-4]}.webp"
        to_webp(png, os.path.join(a.shots, name), max_width=600)
        shots.append({"src": name, "cap": os.path.basename(png)[:-4]})

    mp4s = sorted(glob.glob(os.path.join(a.debug_dir, "**", "startRecording", "*.mp4"), recursive=True))
    video = None
    if mp4s:
        dst = os.path.join(a.pub, "videos", f"{a.name}.mp4")
        r = subprocess.run(["avconvert", "--source", mp4s[-1], "--preset", "Preset960x540",
                            "--output", dst, "--replace"], capture_output=True, text=True)
        if r.returncode != 0 or not os.path.exists(dst):
            sys.exit(f"avconvert 실패: {r.stdout[-300:]} {r.stderr[-300:]}")
        video = {"src": f"videos/{a.name}.mp4", "cap": a.caption or a.name}
        size_mb = os.path.getsize(dst) / 1_000_000
        if size_mb > 15:
            print(f"⚠️ 압축 뒤에도 {size_mb:.1f}MB — 아티팩트 파일 한도(15MB) 초과. 녹화 구간을 줄인다", file=sys.stderr)

    # 캡처는 TC별로 고를 수 있게 키 하나에 모아 두고, 영상만 지정 TC 전부에 붙인다
    m.setdefault(f"maestro:{a.name}", {"videos": [], "shots": []})["shots"] = shots
    for tc in tcs:
        if video:
            add(m, tc, "videos", video)
    with open(a.map, "w", encoding="utf-8") as f:
        json.dump(m, f, ensure_ascii=False, indent=1)
    print(f"maestro: 영상 {1 if video else 0}개 · 캡처 {len(shots)}장 (키 maestro:{a.name}) → {a.map}")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="mode", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--pub", required=True, help="발행 루트(영상은 pub/videos)")
    common.add_argument("--shots", required=True, help="캡처 webp 디렉토리(--shots-dir)")
    common.add_argument("--map", required=True, help="media-map.json 경로(누적)")

    pw = sub.add_parser("playwright", parents=[common])
    pw.add_argument("--results", required=True)
    pw.add_argument("--test-results", required=True)

    ma = sub.add_parser("maestro", parents=[common])
    ma.add_argument("--debug-dir", required=True)
    ma.add_argument("--name", required=True, help="영상 파일 이름(확장자 없이)")
    ma.add_argument("--tc", default="", help="영상을 붙일 TC 목록(쉼표)")
    ma.add_argument("--caption", default="")

    a = ap.parse_args()
    {"playwright": cmd_playwright, "maestro": cmd_maestro}[a.mode](a)


if __name__ == "__main__":
    main()
