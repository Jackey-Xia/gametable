#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""方案A第2.7步：慢速搜索兜底（低并发+限速，规避限流）。"""
import json, os, re, sys, time, unicodedata
import urllib.request, urllib.parse
from concurrent.futures import ThreadPoolExecutor

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "match_out")
META = os.path.join(OUT, "games_meta.json")
meta = json.load(open(META, encoding="utf-8"))

sys_path = os.path.join(BASE, "match_covers.py")
ns = {"__file__": sys_path}
exec(open(sys_path, encoding="utf-8").read().split('def main()')[0], ns)
api, parse_wikitext = ns["api"], ns["parse_wikitext"]


def norm(s):
    s = unicodedata.normalize("NFKC", s or "")
    s = s.replace("・", " ").replace("·", " ")
    return re.sub(r"\s+", " ", s).strip()


def probe(item):
    name, m = item
    b = norm(m["en"])
    q0 = re.sub(r"\s*\([^)]*\)\s*", " ", b).strip() or b
    for q in [q0, b, q0.split(":")[0].strip()]:
        if not q or len(q) < 2:
            continue
        try:
            j = api({"action": "query", "list": "search", "srsearch": q, "srlimit": 3})
            hits = j.get("query", {}).get("search", [])
            time.sleep(0.5)
            if not hits:
                continue
            got = False
            for h in hits[:2]:
                t = h["title"]
                j2 = api({"action": "query", "prop": "revisions", "rvslots": "main",
                          "rvprop": "content", "titles": t}, timeout=60)
                time.sleep(0.3)
                pg = list(j2["query"]["pages"].values())[0]
                if "missing" in pg or "revisions" not in pg:
                    continue
                appid, cover = parse_wikitext(pg["revisions"][0]["slots"]["main"]["*"])
                if appid or cover:
                    m["title"] = t
                    m["appid"] = m["appid"] or appid
                    m["cover"] = m["cover"] or cover
                    m["missing"] = False
                    got = True
                    break
            if got:
                return name, "ok"
        except Exception:
            time.sleep(3)
    return name, "fail"


todo = [(n, m) for n, m in meta.items() if not m.get("cover") and not m.get("appid")]
print("慢速搜索:", len(todo))
ok = 0
lock_print = [0]
with ThreadPoolExecutor(max_workers=2) as ex:
    for name, st in ex.map(probe, todo):
        if st == "ok":
            ok += 1
        lock_print[0] += 1
        if lock_print[0] % 50 == 0:
            print(f"  {lock_print[0]}/{len(todo)} 成功 {ok}")

json.dump(meta, open(META, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
c = sum(1 for m in meta.values() if m.get("cover"))
print(f"\n== 慢速搜索完成 == 本轮新增 {ok}  cover: {c}/1180")
json.dump([{"name": n, "en": m["en"]} for n, m in meta.items() if not m.get("cover") and not m.get("appid")],
          open(os.path.join(OUT, "no_page.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
