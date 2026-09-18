#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pad_rescan_orig.py —— 任务1 辅助：留边版取不到原图的项，回港服重搜取原图。

只写 /tmp/padvs/orig/{i}.jpg（覆盖画布反推的近似结果），不动 covers/。
命中判定：先按 cover_sources.store 里记的港服条目名精确找，找不到再用商品名打分。
"""
import json, os, re, sys, threading
from concurrent.futures import ThreadPoolExecutor, as_completed

REPO = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, REPO)
import autocover as AC
import cover_policy as CP

OUT = "/tmp/padvs"
ORIG = os.path.join(OUT, "orig")
LOCK = threading.Lock()
RES = {}

state = json.load(open(os.path.join(OUT, "state.json"), encoding="utf-8"))
need = json.load(open(os.path.join(OUT, "need.json"), encoding="utf-8"))
src = CP.load_sources()
grid = json.load(open(os.path.join(REPO, "data/ps_grid.json"), encoding="utf-8"))
EN = {}
for r in (grid.get("rows") or [])[2:]:
    if r and len(r) > 3 and r[2] and str(r[2]).strip():
        EN[str(r[2]).strip()] = str(r[3] or "").strip()

LANG = re.compile(r"[(（][^)）]*[)）]\s*$")


def pick(item):
    i = item["i"]
    rep = item["rep"]
    store = (item.get("store") or "").strip()
    terms = []
    if store:
        terms.append(LANG.sub("", store).strip())
    base = AC.strip_seq(AC.strip_ed(rep))
    if base and base not in terms:
        terms.append(base)
    en = EN.get(rep, "")
    if en:
        terms.append(re.split(r"[/（(]", en)[0].strip())
    best = None
    for t in terms:
        if not t:
            continue
        try:
            cands = AC.store_search(t)
        except Exception:
            cands = []
        if not cands:
            continue
        hit = None
        if store:
            ns = AC.norm(LANG.sub("", store))
            for c in cands:
                if AC.norm(LANG.sub("", c.get("name") or "")) == ns:
                    hit = c
                    break
        if hit is None:
            try:
                hit, _s, _s2 = AC.best_of(rep, cands, en, strict=False)
            except Exception:
                hit = cands[0]
        if hit:
            best = (hit, t)
            break
    if not best:
        return i, rep, None, "未搜到"
    c, t = best
    role, url = CP.pick_role(c.get("media") or [{"role": "MASTER", "url": c.get("master")},
                                                {"role": "PORTRAIT_BANNER", "url": c.get("portrait")}])
    if not url:
        return i, rep, None, "无图"
    p = os.path.join(ORIG, "%04d.jpg" % i)
    tmp = p + ".tmp"
    try:
        AC.http_download(url, tmp)
        from PIL import Image
        im = Image.open(tmp).convert("RGB")
        im.save(p, "JPEG", quality=93)
        os.remove(tmp)
    except Exception as ex:
        return i, rep, None, "下载失败 %s" % ex
    open(os.path.join(ORIG, "%04d.txt" % i), "w", encoding="utf-8").write("rescan")
    return i, rep, c.get("name"), "ok"


def main():
    print("待重搜 %d 项" % len(need))
    ok = 0
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = [ex.submit(pick, it) for it in need]
        for f in as_completed(futs):
            i, rep, cand, st = f.result()
            RES[str(i)] = {"rep": rep, "cand": cand, "status": st}
            if st == "ok":
                ok += 1
            else:
                print("  MISS #%d %s : %s" % (i, rep, st))
    json.dump(RES, open(os.path.join(OUT, "rescan.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("重搜成功 %d / %d" % (ok, len(need)))


if __name__ == "__main__":
    main()
