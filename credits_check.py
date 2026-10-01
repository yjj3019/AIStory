#!/usr/bin/env python3
"""로컬 사진(portraits/, context-images/)의 실제 출처·저작자·라이선스를 Wikimedia Commons API 로 조회한다.

목적: CC BY / CC BY-SA 는 저작자·출처 링크·라이선스 링크·변경 여부(TASL)를 요구한다. 이 스크립트는
① 후보 File 페이지 ② 위키백과 인물 문서에 실린 이미지 ③ Commons 검색 결과
의 메타데이터를 가져와 로컬 이미지와 크기·종횡비로 대조하고, 표기 초안(credits_report.md)과 credits.v18.json 을 만든다.

    python credits_check.py                    # 전체
    python credits_check.py --only altman,dario
    python credits_check.py --confirm altman,shannon      # 눈으로 같은 사진임을 확인한 키를 확정

프록시: 사내망처럼 브라우저만 프록시(PAC)를 쓰는 환경이면 파이썬은 직접 못 나간다. 환경변수로 지정한다.
    set HTTPS_PROXY=http://프록시주소:포트     (PowerShell: $env:HTTPS_PROXY="http://...")

주의
- 이 스크립트는 '확정'을 하지 않는다. 원본 해상도까지 일치하면 거의 같은 파일이고, 종횡비만 맞으면 후보일 뿐이다.
  로컬 사진은 대개 너비 500px 로 줄인 썸네일이라 종횡비(오차 2% 이내)로 대조한다.
- Getty 표기가 EXIF 에 남은 사진(altman, dario)은 Commons 의 CC 원본과 같은 사진일 때만 쓴다.
"""
import argparse
import html
import json
import pathlib
import re
import struct
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

HERE = pathlib.Path(__file__).resolve().parent
UA = "AIStoryCreditsCheck/1.0 (personal content project)"
GAP = 1.2            # 요청 간격(초) — 속도 제한(429) 회피

# 키: (로컬 파일, 주제, 현재 크레딧이 주장하는 라이선스, 후보 File 제목 또는 None, 위키백과(en) 문서 제목)
ITEMS = {
    "mccarthy":  ("portraits/mccarthy.jpg", "John McCarthy", "CC BY 2.0", None, "John McCarthy (computer scientist)"),
    "minsky":    ("portraits/minsky.jpg", "Marvin Minsky", "CC BY-SA 2.0", None, "Marvin Minsky"),
    "shannon":   ("portraits/shannon.jpg", "Claude Shannon", "CC BY 2.0", "File:C.E. Shannon. Tekniska museet 43069.jpg", "Claude Shannon"),
    "hinton":    ("portraits/hinton.jpg", "Geoffrey Hinton", "CC BY-SA 4.0", None, "Geoffrey Hinton"),
    "lecun":     ("portraits/lecun.jpg", "Yann LeCun", "CC BY-SA 2.0", None, "Yann LeCun"),
    "bengio":    ("portraits/bengio.jpg", "Yoshua Bengio", "CC BY-SA 2.0", None, "Yoshua Bengio"),
    "sutskever": ("portraits/sutskever.jpg", "Ilya Sutskever", "CC BY-SA 4.0", "File:Ilya Sutskever and Sam Altman in TAU (cropped).jpg", "Ilya Sutskever"),
    "hassabis":  ("portraits/hassabis.jpg", "Demis Hassabis", "CC BY-SA 4.0", None, "Demis Hassabis"),
    "musk":      ("portraits/musk.jpg", "Elon Musk", "CC BY-SA 3.0", "File:Elon Musk Royal Society (crop2).jpg", "Elon Musk"),
    "altman":    ("portraits/altman.jpg", "Sam Altman", "CC BY 2.0", "File:Sam Altman TechCrunch SF 2019 Day 2 Oct 3 (cropped).jpg", "Sam Altman"),
    "dario":     ("portraits/dario.jpg", "Dario Amodei", "CC BY 2.0", None, "Dario Amodei"),
    "brockman":  ("portraits/brockman.jpg", "Greg Brockman", "CC BY 3.0", None, "Greg Brockman"),
    "murati":    ("portraits/murati.jpg", "Mira Murati", "CC BY 4.0", None, "Mira Murati"),
    "ctx_dartmouth": ("context-images/dartmouth.jpg", "Dartmouth College", "?", "File:Dartmouth College campus 2007-10-20 34, crop 1.jpg", "Dartmouth College"),
    "ctx_lisp":      ("context-images/vintage-computer.jpg", "MIT LISP machine", "?", "File:MIT lisp machine.jpg", "Lisp machine"),
}
DEFAULT_KEYS = list(ITEMS)          # 출처 불명이라 페이지에서 뺀 맥락 이미지 3장은 조회 대상이 아니다


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


_last = [0.0]


def get(base: str, params: dict):
    """속도 제한을 지키며 GET. 429/5xx 는 지수 백오프로 재시도."""
    url = base + "?" + urllib.parse.urlencode({**params, "format": "json", "formatversion": "2"})
    for attempt in range(6):
        wait = GAP - (time.time() - _last[0])
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.time()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "identity"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and attempt < 5:
                ra = e.headers.get("Retry-After")
                time.sleep(float(ra) if ra and ra.isdigit() else 3 * (2 ** attempt))
                continue
            raise
    raise RuntimeError("재시도 초과")


COMMONS = "https://commons.wikimedia.org/w/api.php"
ENWIKI = "https://en.wikipedia.org/w/api.php"


def strip(v: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", v or "")).strip()


def imageinfo(titles: list[str]) -> list[dict]:
    out = []
    for i in range(0, len(titles), 40):
        chunk = titles[i:i + 40]
        d = get(COMMONS, {
            "action": "query", "titles": "|".join(chunk), "redirects": "1", "prop": "imageinfo",
            "iiprop": "url|size|extmetadata",
            "iiextmetadatafilter": "Artist|LicenseShortName|LicenseUrl|ImageDescription|DateTimeOriginal|Credit",
        })
        for pg in d.get("query", {}).get("pages", []):
            ii = (pg.get("imageinfo") or [None])[0]
            if not ii or not ii.get("width"):
                continue
            em = ii.get("extmetadata", {})
            g = lambda k: strip(em.get(k, {}).get("value", ""))
            out.append({
                "title": pg["title"], "page": ii.get("descriptionurl"), "width": ii["width"], "height": ii["height"],
                "author": g("Artist"), "license": g("LicenseShortName"), "license_url": g("LicenseUrl"),
                "date": g("DateTimeOriginal"), "credit": g("Credit"),
            })
    return out


def wiki_images(article: str) -> list[str]:
    """위키백과 문서에 실린 이미지(인포박스 포함)의 File 제목."""
    titles = []
    d = get(ENWIKI, {"action": "query", "titles": article, "prop": "images", "imlimit": "60", "redirects": "1"})
    for pg in d.get("query", {}).get("pages", []):
        for im in pg.get("images", []) or []:
            t = im["title"]
            if re.search(r"\.(jpe?g|png)$", t, re.I) and not re.search(r"(icon|logo|flag|symbol|commons-logo|wikiquote|edit-clear|question|stub|ambox)", t, re.I):
                titles.append(t)
    return titles


def category_files(name: str, limit: int = 200) -> list[str]:
    """Commons 'Category:이름' 의 파일 목록(하위 카테고리는 제외)."""
    try:
        d = get(COMMONS, {"action": "query", "list": "categorymembers", "cmtitle": "Category:" + name,
                          "cmtype": "file", "cmlimit": str(limit)})
        return [x["title"] for x in d.get("query", {}).get("categorymembers", []) if re.search(r"\.(jpe?g|png)$", x["title"], re.I)]
    except Exception:
        return []


def search(name: str, limit: int = 10) -> list[str]:
    d = get(COMMONS, {"action": "query", "list": "search", "srnamespace": "6", "srsearch": name, "srlimit": str(limit)})
    return [x["title"] for x in d.get("query", {}).get("search", [])]


def score(local, remote):
    """(분류, 설명, 정렬키). 원본 해상도가 같으면 거의 같은 파일, 종횡비가 2% 이내면 후보."""
    if not local:
        return ("?", "로컬 크기 불명", 9)
    lw, lh = local
    if (lw, lh) == (remote["width"], remote["height"]):
        return ("정확", f"해상도 일치 {lw}x{lh}", 0)
    lr, rr = lw / lh, remote["width"] / remote["height"]
    d = abs(lr - rr) / rr
    if d < 0.02:
        return ("후보", f"종횡비 일치(오차 {d * 100:.1f}%) · 로컬 {lw}x{lh} / 원본 {remote['width']}x{remote['height']}", 1 + d)
    return ("다름", f"종횡비 차이 {d * 100:.0f}% · 로컬 {lw}x{lh} / 원본 {remote['width']}x{remote['height']}", 5 + d)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", help="쉼표로 구분한 키만 조회")
    ap.add_argument("--confirm", help="눈으로 같은 사진임을 확인한 키(쉼표) — verified=true 로 기록")
    ap.add_argument("--pick", help="키=파일제목 (자동 선택 대신 이 File 로 확정 후보를 지정) 예: lecun='File:Yann LeCun - Mar 2018.jpg'")
    ap.add_argument("--root", default=str(HERE), help="portraits/, context-images/ 가 있는 폴더")
    a = ap.parse_args()
    root = pathlib.Path(a.root)
    keys = [k.strip() for k in a.only.split(",")] if a.only else DEFAULT_KEYS
    store_path = root / "credits.v18.json"
    store = json.loads(store_path.read_text(encoding="utf-8")) if store_path.exists() else {}
    for k in (a.confirm.split(",") if a.confirm else []):
        k = k.strip()
        if k not in store or not store[k].get("commons_title"):
            sys.exit(f"--confirm {k}: 조회 결과(commons_title)가 있어야 확정할 수 있다")
        store[k]["verified"] = True
    report = ["# 사진 출처 조회 리포트", "",
              "분류: **정확**=원본 해상도까지 일치(같은 파일일 가능성 매우 높음) · **후보**=종횡비 2% 이내 · 다름=종횡비 불일치(잘라 냈거나 다른 사진)", ""]
    failed = []
    if not a.confirm or a.only:
        for k in keys:
            f, who, claimed, cand, article = ITEMS[k]
            local = jpeg_size(root / f) if (root / f).exists() else None
            rec = store.get(k, {"verified": False})
            rec.update({"file": f, "subject": who, "claimed_license": claimed})
            report.append(f"## {k} — {who} (현재 크레딧 주장: {claimed}, 로컬 {local[0]}x{local[1] if local else '?'})" if local else f"## {k} — {who}")
            try:
                titles = ([cand] if cand else []) + wiki_images(article) + search(who) + category_files(who)
                seen, uniq = set(), []
                for t in titles:
                    if t not in seen:
                        seen.add(t)
                        uniq.append(t)
                infos = imageinfo(uniq[:200])
            except Exception as e:
                failed.append(k)
                report.append(f"- (조회 실패: {type(e).__name__}: {e})")
                store[k] = rec
                continue
            ranked = sorted(((score(local, i), i) for i in infos), key=lambda x: x[0][2])
            report.append("")
            report.append("| 분류 | File 페이지 | 저작자 | 라이선스 | 대조 |")
            report.append("|---|---|---|---|---|")
            for (cls, note, _), info in ranked[:6]:
                warn = " ⚠ 현재 크레딧과 다름" if claimed not in ("?", info["license"]) else ""
                report.append(f"| {cls} | [{info['title']}]({info['page']}) | {info['author'][:70]} | {info['license']}{warn} | {note} |")
            report.append("")
            best = None
            if a.pick and a.pick.startswith(k + "="):
                want = a.pick.split("=", 1)[1]
                best = next((i for _, i in ranked if i["title"] == want), None)
            if best is None:
                best = next((i for (cls, _, _), i in ranked if cls in ("정확", "후보")), None)
            if best:
                rec.update({"commons_title": best["title"], "commons_page": best["page"], "author": best["author"],
                            "license": best["license"], "license_url": best["license_url"], "date": best["date"],
                            "match": score(local, best)[0]})
            else:
                rec.pop("commons_title", None)
                report.append("- 종횡비가 맞는 후보 없음 → 출처 불명이면 사진 삭제(이니셜 대체)")
            store[k] = rec
    report += ["## 사람이 해야 할 일",
               "1. **분류가 정확**인 것은 거의 확정이다. **후보**는 File 페이지의 사진과 로컬 사진을 눈으로 비교한다.",
               "2. 같은 사진이면 `python credits_check.py --confirm 키,키` 로 확정한다(확정된 항목만 크레딧에 저작자·링크가 표기된다).",
               "3. 후보가 없거나 다른 사진이면 삭제한다(카드는 이니셜로 대체된다).",
               "4. altman/dario 처럼 EXIF 에 Getty 표기가 있는 사진은 Commons 의 CC 라이선스 원본과 같은 사진일 때만 사용한다."]
    (root / "credits_report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    store_path.write_text(json.dumps(store, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n".join(report))
    print(f"\n저장: {root / 'credits_report.md'} , {store_path}")
    if failed:
        print(f"\n[경고] 조회 실패: {', '.join(failed)} — 잠시 뒤 `--only {','.join(failed)}` 로 다시 실행하라.")


if __name__ == "__main__":
    main()
