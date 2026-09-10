#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""巡检修复 + 宽松补图（按用户三条建议）。
1) 对 74 款疑似配错: 重新宽松搜索, 找到更优(相似度>=0.6)则替换;
   标题是名称前/后缀截断(同一游戏不同叫法)则保留; 否则清除避免错图。
2) 对无图游戏: 去版本后缀+斜杠拆名+冒号拆段, 模糊搜索(>=0.6 才收), 中英文都核对。
低并发+限速防封。产出: match_out/games_meta.json 更新。
"""
import json, os, re, sys, time, unicodedata
import urllib.request, urllib.parse
from difflib import SequenceMatcher
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


def base_name(en):
    """去括号版本后缀 + 去常见版本词"""
    b = norm(en)
    b = re.sub(r"\s*\([^)]*\)\s*", " ", b)
    b = re.sub(r"\b(Deluxe|Ultimate|Premium|Complete|Gold|Definitive|Collector)?\s*(Edition|Editions|Version|Collection)\b\s*$", "", b, flags=re.I)
    return re.sub(r"\s+", " ", b).strip(" -–:")


def sim(a, b):
    a, b = norm(a).lower(), norm(b).lower()
    r = SequenceMatcher(None, a, b).ratio()
    if a and (a in b or b in a):
        r = max(r, 0.75)  # 截断/包含视为同游戏强信号
    return r


def queries(en):
    """生成候选搜索词: 斜杠拆名 / 冒号拆段 / 前4词"""
    qs, seen = [], set()

    def add(x):
        x = x.strip()
        if x and len(x) > 2 and x.lower() not in seen:
            seen.add(x.lower()); qs.append(x)

    b = base_name(en)
    for part in re.split(r"\s*/\s*", b):
        add(part)
        add(re.split(r"[:：]\s*", part)[0])
        add(" ".join(part.split()[:4]))
    add(b)
    return qs[:5]


def search_best(en):
    """宽松搜索: 多查询词 × 前5命中, 取相似度最高且>=0.6 的候选。"""
    best = None  # (score, title, appid, cover)
    for q in queries(en):
        try:
            j = api({"action": "query", "list": "search", "srsearch": q, "srlimit": 5})
            time.sleep(0.4)
            hits = j.get("query", {}).get("search", [])
        except Exception:
            time.sleep(2); continue
        for h in hits:
            sc = sim(en, h["title"])
            if best and sc <= best[0]:
                continue
            try:
                j2 = api({"action": "query", "prop": "revisions", "rvslots": "main",
                          "rvprop": "content", "titles": h["title"]}, timeout=60)
                time.sleep(0.3)
                pg = list(j2["query"]["pages"].values())[0]
                if "missing" in pg or "revisions" not in pg:
                    continue
                appid, cover = parse_wikitext(pg["revisions"][0]["slots"]["main"]["*"])
            except Exception:
                time.sleep(2); continue
            if (appid or cover) and sc >= 0.6:
                best = (sc, h["title"], appid, cover)
    return best


def fix_one(item):
    name, m, mode = item
    best = search_best(m["en"])
    if mode == "suspect":
        if best:
            _, t, appid, cover = best
            old_sc = sim(m["en"], m.get("title") or "")
            if old_sc >= 0.75 and not best:
                return name, "keep-old"
            # 新候选更优才替换; 新旧都一般时保留旧的仅当旧行是包含关系
            if old_sc >= 0.75 and sim(m["en"], t) <= old_sc:
                return name, "keep-old"
            m["title"], m["appid"], m["cover"], m["missing"] = t, appid, cover, False
            return name, "replaced"
        # 没找到更优: 旧行若是包含/截断关系则保留, 否则清除防错图
        old_t = m.get("title") or ""
        if old_t and (norm(m["en"]).lower() in norm(old_t).lower() or norm(old_t).lower() in norm(m["en"]).lower()):
            return name, "keep-old"
        m["title"] = m["appid"] = m["cover"] = ""
        m["missing"] = True
        return name, "cleared"
    else:  # fill 空白
        if best:
            _, t, appid, cover = best
            m["title"], m["appid"], m["cover"], m["missing"] = t, appid, cover, False
            return name, "filled"
        return name, "none"


suspect = json.load(open(os.path.join(OUT, "suspect.json"), encoding="utf-8"))
todo_s = [(s["name"], meta[s["name"]], "suspect") for s in suspect if s["name"] in meta]
todo_f = [(n, meta[n], "fill") for n, m in meta.items() if not m.get("cover") and not m.get("appid")]
print(f"疑似复查: {len(todo_s)}  空白补图: {len(todo_f)}")

stats = {}
for label, todo in (("复查", todo_s), ("补图", todo_f)):
    cnt = {}
    with ThreadPoolExecutor(max_workers=2) as ex:
        for i, (name, st) in enumerate(ex.map(fix_one, todo)):
            cnt[st] = cnt.get(st, 0) + 1
            if (i + 1) % 40 == 0:
                print(f"  {label} {i+1}/{len(todo)} {cnt}")
    stats[label] = cnt
    print(f"== {label}完成: {cnt}")

json.dump(meta, open(META, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
c = sum(1 for m in meta.values() if m.get("cover"))
print(f"\n== 总结 == 复查:{stats['复查']} 补图:{stats['补图']}\n当前有图: {c}/1183")
