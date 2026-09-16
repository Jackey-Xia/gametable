#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
apply_missing.py —— 按店主在挑选页回传的清单(name|role)给「原本无封面」的商品装图
=============================================================================
用法:
  python3 apply_missing.py picks.txt          # 每行 "商品名|P" 或 "商品名|M"
  python3 apply_missing.py --all-portrait     # 全部尽量用竖版(缺竖版则用方图), 跳过 low
  python3 apply_missing.py --all-portrait --include-lowconf
说明:
  - 图片来源严格取 missing_report.json 里记录的港服中文页 media URL(ROLE 对应 P=PORTRAIT_BANNER / M=MASTER)
  - 写 covers/rc{md5(name)[:12]}.jpg, 更新 manifest, 并从 auto_skip.json 移除(不再是留白)
"""
import base64
import hashlib
import json
import os
import sys
import time
import traceback

import autocover as A
import identify_zh as I

BASE = A.BASE
MANIFEST = A.MANIFEST
SKIP = os.path.join(BASE, "covers", "auto_skip.json")
REPORT = os.path.join(BASE, "covers", "missing_report.json")
OUT = os.path.join(BASE, "covers", "missing_apply_report.json")


def load_report():
    rep = json.load(open(REPORT, encoding="utf-8"))
    return {r["name"]: r for r in rep["items"]}


def main():
    by = load_report()
    picks = []
    if "--all-portrait" in sys.argv:
        low = "--include-lowconf" in sys.argv
        for r in json.load(open(REPORT, encoding="utf-8"))["items"]:
            if r["low"] and not low:
                continue
            role = "P" if r.get("zhP") else ("M" if r.get("zhM") else "")
            if role:
                picks.append((r["name"], role))
    else:
        arg = [a for a in sys.argv[1:] if not a.startswith("--")]
        if not arg:
            print("用法: apply_missing.py picks.txt | --all-portrait [--include-lowconf]")
            return
        for line in open(arg[0], encoding="utf-8"):
            line = line.strip()
            if not line or "|" not in line:
                continue
            n, v = line.rsplit("|", 1)
            picks.append((n.strip(), v.strip().upper()))

    m = json.load(open(MANIFEST, encoding="utf-8"))
    skip = set(json.load(open(SKIP, encoding="utf-8")) or [])
    done, err, skip_r = [], [], []
    for name, role in picks:
        r = by.get(name)
        if not r:
            err.append({"name": name, "error": "报告里没有这条"})
            continue
        url = r.get("zhP") if role == "P" else r.get("zhM")
        if not url:
            err.append({"name": name, "error": "港服无该形态图(%s)" % role})
            continue
        rel = "covers/rc%s.jpg" % hashlib.md5(name.encode()).hexdigest()[:12]
        try:
            p = I.download(url, "ms_" + role)
            dst = os.path.join(BASE, rel)
            with open(p, "rb") as fi, open(dst, "wb") as fo:
                fo.write(fi.read())
            if os.path.getsize(dst) < 3000:
                raise ValueError("文件过小")
            old = m.get(name)
            m[name] = rel
            keep = {"covers/" + os.path.basename(x) for x in m.values()}
            if old and old not in keep and os.path.exists(os.path.join(BASE, old)):
                os.remove(os.path.join(BASE, old))
            done.append({"name": name, "to": rel, "role": role, "store": r["store"],
                         "size": os.path.getsize(dst)})
            if name in skip:
                skip.discard(name)
                skip_r.append(name)
        except Exception as ex:
            err.append({"name": name, "error": str(ex)[:120]})

    json.dump(m, open(MANIFEST, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(sorted(skip), open(SKIP, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    out = {"time": time.strftime("%Y-%m-%dT%H:%M:%S"), "added": done, "errors": err,
           "unskipped": skip_r, "stats": {"picks": len(picks), "added": len(done),
                                          "err": len(err), "manifest": len(m), "skip": len(skip)}}
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("选中 %d | 装图 %d | 失败 %d | manifest %d | 剩余留白 %d"
          % (len(picks), len(done), len(err), len(m), len(skip)))
    for e in err:
        print("  ERR", e)
    print("清单 ->", OUT)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
    sys.exit(0)
