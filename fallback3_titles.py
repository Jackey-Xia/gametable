#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""方案A第2.6步：标题变体批量探测 —— 绕开搜索限流。
规则: NFKC 归一(全角/罗马数字自动转半角) -> 生成 <=6 个标题变体 -> 50个/批 titles= 精确探测。
"""
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


def variants(en):
    b = norm(en)
    out = []
    cands = [b]
    stripped = re.sub(r"\s*\([^)]*\)\s*", " ", b).strip()
    if stripped and stripped != b:
        cands.append(stripped)
    for c in list(cands):
        parts = [p.strip() for p in re.split(r"[:\-–]\s*", c) if len(p.strip()) > 2]
        for p in parts:
            if p not in cands:
                cands.append(p)
    # 数字结尾 -> 加感叹号变体 (Slap them All 1 -> Slap Them All!)
    for c in list(cands):
        m = re.match(r"^(.*?)(\d+)$", c)
        if m and m.group(2) in ("1", "2", "3"):
            alt = m.group(1).rstrip() + "!"
            if alt not in cands:
                cands.append(alt)
    return [c for c in cands if c][:6]


todo = {n: m for n, m in meta.items() if not m.get("cover") and not m.get("appid")}
print("待变体探测:", len(todo))

# 变体 -> 游戏名 倒排
v2names = {}
for n, m in todo.items():
    for v in variants(m["en"]):
        v2names.setdefault(v, []).append(n)
allv = list(v2names.keys())
print("变体总数:", len(allv))


def fetch_batch(batch):
    """batch: 变体列表。返回 {variant: content}"""
    try:
        j = api({"action": "query", "prop": "revisions", "rvslots": "main",
                 "rvprop": "content", "titles": "|".join(batch), "redirects": 1}, timeout=120)
    except Exception:
        return {}
    q = j.get("query", {})
    norm_map = {}
    for it in q.get("normalized", []) + q.get("redirects", []):
        norm_map[it["from"]] = it["to"]
    pages = {p["title"]: p for p in q.get("pages", {}).values()}
    res = {}
    for v in batch:
        t = norm_map.get(v, v)
        pg = pages.get(t)
        if pg and "revisions" in pg:
            try:
                res[v] = pg["revisions"][0]["slots"]["main"]["*"]
            except Exception:
                pass
    return res


BATCH = 50
found_content = {}
batches = [allv[i:i + BATCH] for i in range(0, len(allv), BATCH)]
with ThreadPoolExecutor(max_workers=3) as ex:
    for i, res in enumerate(ex.map(fetch_batch, batches)):
        found_content.update(res)
        if (i + 1) % 5 == 0:
            print(f"  批次 {i+1}/{len(batches)}  命中变体 {len(found_content)}")

print("命中变体:", len(found_content), "/", len(allv))

# 用命中的内容回填 meta（同一游戏取第一个命中的变体）
hits = 0
for n, m in todo.items():
    for v in variants(m["en"]):
        c = found_content.get(v)
        if not c:
            continue
        appid, cover = parse_wikitext(c)
        if appid or cover:
            m["title"] = v
            m["appid"] = appid
            m["cover"] = cover
            m["missing"] = False
            hits += 1
            break

json.dump(meta, open(META, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
c = sum(1 for m in meta.values() if m.get("cover"))
a = sum(1 for m in meta.values() if m.get("appid"))
print(f"\n== 变体探测完成 == 本轮新增 {hits}\ncover: {c}  appid: {a}  合计去重: {sum(1 for m in meta.values() if m.get('cover') or m.get('appid'))}/1180")
json.dump([{"name": n, "en": m["en"]} for n, m in meta.items() if not m.get("cover") and not m.get("appid")],
          open(os.path.join(OUT, "no_page.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
