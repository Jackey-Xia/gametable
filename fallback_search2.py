#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""方案A第2.5步：归一化搜索兜底 —— 全角转半角后重试所有仍缺封面的游戏。"""
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
    s = re.sub(r"\s+", " ", s).strip()
    return s


def probe(item):
    name, m = item
    base = norm(m["en"])
    # 括号后缀(豪华版/Rad Edition等)与冒号拆分依次尝试
    tries = [base]
    t2 = re.sub(r"\s*\([^)]*\)\s*", " ", base).strip()
    if t2 and t2 != base:
        tries.append(t2)
    for part in re.split(r"[:：]\s*", base):
        p = part.strip()
        if p and p not in tries and len(p) > 2:
            tries.append(p)
    try_limit = 4
    for q in tries[:try_limit]:
        try:
            j = api({"action": "query", "list": "search", "srsearch": q, "srlimit": 3})
            hits = j.get("query", {}).get("search", [])
            if not hits:
                continue
            t = hits[0]["title"]
            j2 = api({"action": "query", "prop": "revisions", "rvslots": "main",
                      "rvprop": "content", "titles": t}, timeout=60)
            pg = list(j2["query"]["pages"].values())[0]
            if "missing" in pg or "revisions" not in pg:
                continue
            content = pg["revisions"][0]["slots"]["main"]["*"]
            appid, cover = parse_wikitext(content)
            if not appid and not cover:
                # 标题差太远时意义不大, 但仍记录 title 便于人工核对
                m["title"] = m["title"] or t
                continue
            m["title"] = t
            m["appid"] = m["appid"] or appid
            m["cover"] = m["cover"] or cover
            m["missing"] = False
            return name, "ok"
        except Exception:
            time.sleep(1)
    return name, "fail"


todo = [(n, m) for n, m in meta.items() if not m.get("cover") and not m.get("appid")]
print("待归一化重试:", len(todo))
ok = 0
with ThreadPoolExecutor(max_workers=6) as ex:
    for i, (name, st) in enumerate(ex.map(probe, todo)):
        if st == "ok":
            ok += 1
        if (i + 1) % 100 == 0:
            print(f"  {i+1}/{len(todo)} 累计成功 {ok}")

json.dump(meta, open(META, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
matched = sum(1 for m in meta.values() if m.get("title"))
has_cover = sum(1 for m in meta.values() if m.get("cover"))
has_appid = sum(1 for m in meta.values() if m.get("appid"))
print(f"\n== 归一化兜底完成 ==\n有封面可用(cover或appid): {has_cover + has_appid - has_cover*0}/1180")
print(f"cover: {has_cover}  appid: {has_appid}  title: {matched}")
json.dump([{"name": n, "en": m["en"]} for n, m in meta.items() if not m.get("cover") and not m.get("appid")],
          open(os.path.join(OUT, "no_page.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
