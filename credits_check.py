#!/usr/bin/env python3
"""로컬 사진(portraits/, context-images/)의 실제 출처·저작자·라이선스를 Wikimedia Commons API 로 조회한다.

목적: CC BY / CC BY-SA 는 저작자·출처 링크·라이선스 링크·변경 여부(TASL)를 요구한다. 지금 페이지 크레딧에는
라이선스 종류만 있다. 이 스크립트는 후보 File: 페이지의 메타데이터를 가져와 로컬 이미지와 대조하고,
표기 초안(credits_report.md)과 credits.v18.json 을 만든다.

    python credits_check.py                 # 네트워크가 되는 PC 에서 실행 (Commons API 필요)
    python credits_check.py --only altman   # 한 장만

주의
- 이 스크립트는 '확정'을 하지 않는다. 종횡비가 맞는 후보를 찾아 줄 뿐이며, 같은 사진인지는 사람이 File 페이지의
  이미지와 로컬 사진을 눈으로 비교해 `--confirm 키,키` 로 표시해야 한다(verified=true).
- 후보가 없는 이미지는 Commons 검색 결과 상위 몇 개를 보여 준다.
- Getty 등 상업 라이선스 표기가 EXIF 에 남은 사진(altman, dario)은 Commons 의 CC 원본(예: TechCrunch/Flickr)과
  같은 사진인지 반드시 확인한다.
"""
import argparse
import html
import json
import pathlib
import re
import struct
import sys
import urllib.parse
import urllib.request

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

HERE = pathlib.Path(__file__).resolve().parent
API = "https://commons.wikimedia.org/w/api.php"
UA = "AIStoryCreditsCheck/1.0 (personal content project)"

# (로컬 파일, 사람/주제, 현재 크레딧이 주장하는 라이선스, 조사에서 나온 후보 File 제목 또는 None)
ITEMS = {
    "mccarthy":  ("portraits/mccarthy.jpg", "John McCarthy", "CC BY 2.0", None),
    "minsky":    ("portraits/minsky.jpg", "Marvin Minsky", "CC BY-SA 2.0", None),   # KI 2006 학회 사진(배너 확인됨)
    "shannon":   ("portraits/shannon.jpg", "Claude Shannon", "CC BY 2.0", "File:C.E. Shannon. Tekniska museet 43069.jpg"),
    "hinton":    ("portraits/hinton.jpg", "Geoffrey Hinton", "CC BY-SA 4.0", None),  # 후보(낮은 확신): Geoffrey E. Hinton, 2024 Nobel Prize Laureate in Physics.jpg
    "lecun":     ("portraits/lecun.jpg", "Yann LeCun", "CC BY-SA 2.0", None),        # EXIF: JEREMY_BARANDE
    "bengio":    ("portraits/bengio.jpg", "Yoshua Bengio", "CC BY-SA 2.0", None),    # EXIF: jeremy_barande
    "sutskever": ("portraits/sutskever.jpg", "Ilya Sutskever", "CC BY-SA 4.0", "File:Ilya Sutskever and Sam Altman in TAU (cropped).jpg"),
    "hassabis":  ("portraits/hassabis.jpg", "Demis Hassabis", "CC BY-SA 4.0", None),
    "musk":      ("portraits/musk.jpg", "Elon Musk", "CC BY-SA 3.0", "File:Elon Musk Royal Society (crop2).jpg"),
    "altman":    ("portraits/altman.jpg", "Sam Altman", "CC BY 2.0", "File:Sam Altman TechCrunch SF 2019 Day 2 Oct 3 (cropped).jpg"),  # EXIF: Getty / Steve Jennings
    "dario":     ("portraits/dario.jpg", "Dario Amodei", "CC BY 2.0", None),         # EXIF: 2023 Getty Images — CC 원본 확인 필수
    "brockman":  ("portraits/brockman.jpg", "Greg Brockman", "CC BY 3.0", None),
    "murati":    ("portraits/murati.jpg", "Mira Murati", "CC BY 4.0", None),
    "ctx_dartmouth": ("context-images/dartmouth.jpg", "Dartmouth College", "?", "File:Dartmouth College campus 2007-10-20 34, crop 1.jpg"),
    "ctx_lisp":      ("context-images/vintage-computer.jpg", "MIT LISP machine", "?", "File:MIT lisp machine.jpg"),
    "ctx_gpu":       ("context-images/gpu-alexnet.jpg", "NVIDIA GPU board", "?", None),
    "ctx_openai":    ("context-images/openai-hq.jpg", "OpenAI 옛 본사(Pioneer Building)", "?", None),
    "ctx_chatgpt":   ("context-images/chatgpt-launch.jpg", "ChatGPT(스톡 사진으로 추정)", "?", None),
}


def jpeg_size(path: pathlib.Path):
    """PIL 없이 JPEG 크기를 읽는다."""
    with open(path, "rb") as f:
        data = f.read()
    i = 2
    while i < len(data) - 9:
        if data[i] != 0xFF:
            i += 1
            continue
        m = data[i + 1]
        if m in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
            h, w = struct.unpack(">HH", data[i + 5:i + 9])
            return w, h
        i += 2 + struct.unpack(">H", data[i + 2:i + 4])[0]
    return None


def get(params: dict):
    url = API + "?" + urllib.parse.urlencode({**params, "format": "json", "formatversion": "2"})
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.loads(r.read().decode("utf-8"))


def strip(v: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", v or "")).strip()


def imageinfo(titles: list[str]) -> list[dict]:
    d = get({
        "action": "query", "titles": "|".join(titles), "redirects": "1", "prop": "imageinfo",
        "iiprop": "url|size|extmetadata",
        "iiextmetadatafilter": "Artist|LicenseShortName|LicenseUrl|ImageDescription|DateTimeOriginal|Credit|Attribution|UsageTerms",
    })
    out = []
    for pg in d.get("query", {}).get("pages", []):
        ii = (pg.get("imageinfo") or [None])[0]
        if not ii:
            continue
        em = ii.get("extmetadata", {})
        g = lambda k: strip(em.get(k, {}).get("value", ""))
        out.append({
            "title": pg["title"], "page": ii.get("descriptionurl"), "width": ii["width"], "height": ii["height"],
            "author": g("Artist"), "license": g("LicenseShortName"), "license_url": g("LicenseUrl"),
            "date": g("DateTimeOriginal"), "description": g("ImageDescription")[:160], "credit": g("Credit"),
        })
    return out


def search(name: str, limit: int = 8) -> list[str]:
    d = get({"action": "query", "list": "search", "srnamespace": "6", "srsearch": name, "srlimit": str(limit)})
    return [x["title"] for x in d.get("query", {}).get("search", [])]


def ratio_note(local, remote) -> str:
    if not local:
        return "로컬 크기 불명"
    lr, rr = local[0] / local[1], remote["width"] / remote["height"]
    d = abs(lr - rr) / rr
    return ("종횡비 일치" if d < 0.02 else f"종횡비 차이 {d * 100:.0f}% (잘라 냈거나 다른 사진)") + f" · 로컬 {local[0]}x{local[1]} / 원본 {remote['width']}x{remote['height']}"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", help="쉼표로 구분한 키만 조회")
    ap.add_argument("--confirm", help="눈으로 같은 사진임을 확인한 키(쉼표) — credits.v18.json 에 verified=true 로 기록")
    ap.add_argument("--root", default=str(HERE), help="portraits/, context-images/ 가 있는 폴더")
    a = ap.parse_args()
    root = pathlib.Path(a.root)
    keys = [k.strip() for k in a.only.split(",")] if a.only else list(ITEMS)
    store_path = root / "credits.v18.json"
    store = json.loads(store_path.read_text(encoding="utf-8")) if store_path.exists() else {}
    for k in (a.confirm.split(",") if a.confirm else []):
        k = k.strip()
        if k not in store:
            sys.exit(f"--confirm {k}: 먼저 조회 결과가 있어야 한다(credits.v18.json 에 없음)")
        store[k]["verified"] = True
    lines = ["# 사진 출처 조회 리포트", "", "| 키 | 후보 File 페이지 | 저작자 | 라이선스 | 크기 대조 | 비고 |", "|---|---|---|---|---|---|"]
    net_ok = True
    for k in keys:
        f, who, claimed, cand = ITEMS[k]
        local = jpeg_size(root / f) if (root / f).exists() else None
        rec = store.get(k, {"file": f, "subject": who, "claimed_license": claimed, "verified": False})
        rec["file"], rec["subject"], rec["claimed_license"] = f, who, claimed
        try:
            titles = [cand] if cand else search(who)
            infos = imageinfo(titles) if titles else []
        except Exception as e:
            net_ok = False
            lines.append(f"| {k} | (조회 실패: {type(e).__name__}) | | | | 네트워크/API 확인 |")
            store[k] = rec
            continue
        if not infos:
            lines.append(f"| {k} | (후보 없음) | | | | Commons 검색 결과 없음 → 출처 불명이면 사진 교체/삭제 |")
        for n, info in enumerate(infos[:8]):
            rn = ratio_note(local, info)
            lines.append(f"| {k}{'' if n == 0 else ' (후보 ' + str(n + 1) + ')'} | [{info['title']}]({info['page']}) | {info['author'][:60]} | "
                         f"{info['license']} | {rn} | {'⚠ 현재 크레딧과 라이선스가 다름' if claimed not in ('?', info['license']) else ''} |")
        if infos:
            best = next((i for i in infos if "일치" in ratio_note(local, i)), infos[0])
            rec.update({"commons_title": best["title"], "commons_page": best["page"], "author": best["author"],
                        "license": best["license"], "license_url": best["license_url"], "date": best["date"]})
        store[k] = rec
    lines += ["", "## 사람이 해야 할 일",
              "1. 위 표의 File 페이지를 열어 **로컬 사진과 같은 사진인지 눈으로 확인**한다(종횡비 일치는 필요조건일 뿐이다).",
              "2. 같은 사진이면 `python credits_check.py --confirm altman,shannon` 처럼 표시한다.",
              "3. 후보가 없거나 출처 불명인 사진은 **교체하거나 삭제**한다(맥락 이미지 3장은 조사 결과 출처 불명·캡션 불일치 → 교체 권고).",
              "4. EXIF 에 Getty 표기가 있는 altman/dario 는 Commons 의 CC 라이선스 원본과 같은 사진일 때만 사용한다."]
    (root / "credits_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    store_path.write_text(json.dumps(store, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n".join(lines))
    print(f"\n저장: {root / 'credits_report.md'} , {store_path}")
    if not net_ok:
        print("\n[경고] 일부 조회가 네트워크 오류로 실패했다. Commons(commons.wikimedia.org) 접속 가능한 환경에서 다시 실행하라.")


if __name__ == "__main__":
    main()
