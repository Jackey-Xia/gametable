#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
missing_covers.py —— 盘点「目前无封面」的商品，并去港服中文页找回官方图
=============================================================================
阶段一(pick): 无图名单 -> 港服 zh-Hans 搜索 -> 严格评分 -> 记录候选与 media(MASTER/PORTRAIT_BANNER)
             产出 covers/missing_report.json (不下载图片, 不下结论)
"""
import json
import os
import sys
import time
import traceback

import autocover as A
import identify_zh as I

BASE = A.BASE
MANIFEST = A.MANIFEST
OUT = os.path.join(BASE, "covers", "missing_report.json")


def missing_names():
    ps = json.load(open(os.path.join(BASE, "data", "ps_games.json"), encoding="utf-8"))
    m = json.load(open(MANIFEST, encoding="utf-8"))
    skip = set(json.load(open(os.path.join(BASE, "covers", "auto_skip.json"), encoding="utf-8")) or [])
    nokey, empty = [], []
    seen = set()
    for r in (ps if isinstance(ps, list) else []):
        n = (r.get("name") or "").strip()
        if not n or n in seen:
            continue
        seen.add(n)
        if n not in m:
            nokey.append({"name": n, "en": r.get("en") or ""})
        elif not m[n]:
            empty.append({"name": n, "en": r.get("en") or ""})
    # manifest 里有键但商品已下架(死键)
    dead = [k for k in m if k not in seen]
    return nokey + empty, dead, skip


def main():
    miss, dead, skip = missing_names()
    print("无封面商品 %d | 已下架残留键值 %d | auto_skip 名单 %d" % (len(miss), len(dead), len(skip)))
    res = {"time": time.strftime("%Y-%m-%dT%H:%M:%S"), "dead_keys": dead, "items": []}
    t0 = time.time()
    for i, it in enumerate(miss, 1):
        name, en = it["name"], it["en"]
        try:
            c, s, ss, note, media = I.match_and_media(name, en)
        except Exception as ex:
            c, s, ss, note, media = None, 0, 0, "异常:%s" % str(ex)[:60], {}
        rec = {"name": name, "en": en, "score": round(s, 3), "second": round(ss, 3),
               "low": bool(note), "note": note,
               "store": (c or {}).get("name") or "", "product": (c or {}).get("id") or "",
               "zhM": media.get("MASTER") or "", "zhP": media.get("PORTRAIT_BANNER") or "",
               "in_skip": name in skip}
        res["items"].append(rec)
        tag = "OK " if (not note and s >= 0.85) else ("低置" if note and s >= 0.7 else "无  ")
        print("  %3d/%d [%s] %-30s -> %s" % (i, len(miss), tag, name[:30], rec["store"][:44]))
        json.dump(res, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    n_ok = len([r for r in res["items"] if r["zhM"] and not r["low"]])
    n_low = len([r for r in res["items"] if r["zhM"] and r["low"]])
    n_none = len([r for r in res["items"] if not r["zhM"]])
    print("完成 %.1fs | 高置信命中 %d | 低置信 %d | 港服无结果 %d" % (time.time() - t0, n_ok, n_low, n_none))
    print("报告 ->", OUT)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
    sys.exit(0)
