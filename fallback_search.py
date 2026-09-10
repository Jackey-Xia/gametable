#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""方案A第二步：对精确匹配失败的 855 款用 list=search 兜底，更新 games_meta.json。"""
import json, os, re, time
import urllib.request, urllib.parse
from concurrent.futures import ThreadPoolExecutor

API = "https://www.pcgamingwiki.com/w/api.php"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/121.0 Safari/537.36")
BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "match_out")

META = os.path.join(OUT, "games_meta.json")
meta = json.load(open(META, encoding="utf-8"))

sys_path = os.path.join(BASE, "match_covers.py")
ns = {"__file__": sys_path}
exec(open(sys_path, encoding="utf-8").read().split('def main()')[0], ns)  # 复用 http/api/parse_wikitext
api, parse_wikitext = ns["api"], ns["parse_wikitext"]


def probe(item):
    name, m = item
    en = m["en"]
    for attempt, q in enumerate([en, re.sub(r"\s*\d+$", "", en), en.split(":")[0]]):
        try:
            j = api({"action": "query", "list": "search", "srsearch": q, "srlimit": 3})
            hits = j.get("query", {}).get("search", [])
            if not hits:
                continue
            # 优先取标题最接近的
            t = hits[0]["title"]
            j2 = api({"action": "query", "prop": "revisions", "rvslots": "main",
                      "rvprop": "content", "titles": t}, timeout=60)
            pg = list(j2["query"]["pages"].values())[0]
            if "missing" in pg or "revisions" not in pg:
                continue
            content = pg["revisions"][0]["slots"]["main"]["*"]
            appid, cover = parse_wikitext(content)
            m["title"] = t
            m["appid"] = m["appid"] or appid
            m["cover"] = m["cover"] or cover
            m["missing"] = False
            return name, "ok", t
        except Exception as e:
            time.sleep(1)
    return name, "fail", ""


todo = [(n, m) for n, m in meta.items() if m.get("missing") or (not m.get("title") and not m.get("cover"))]
print("待搜索兜底:", len(todo))
ok = 0
with ThreadPoolExecutor(max_workers=6) as ex:
    for i, (name, st, t) in enumerate(ex.map(probe, todo)):
        if st == "ok":
            ok += 1
        if (i + 1) % 100 == 0:
            print(f"  {i+1}/{len(todo)} 累计成功 {ok}")

json.dump(meta, open(META, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
matched = sum(1 for m in meta.values() if m.get("title"))
has_cover = sum(1 for m in meta.values() if m.get("cover"))
has_appid = sum(1 for m in meta.values() if m.get("appid"))
print(f"\n== 兜底完成 ==\n匹配页面: {matched}/1180\n有cover: {has_cover}\n有appid: {has_appid}")
json.dump([n for n, m in meta.items() if not m.get("title")],
          open(os.path.join(OUT, "no_page.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
