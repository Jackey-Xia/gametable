#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""missing_zhcheck.py —— 校验新装图是否为港服「中文页专属」中文版封面
=============================================================================
做法: 对同一 product，用 page_media(pid, "en-hk") 取同名 role 的英文页图，
与已装的中文页图做 dhash 比对:
  - zhEnDist == 0  -> 港服中英同图（该游戏没有专属中文 Logo 封面，标题仍是英文）
  - zhEnDist > 0   -> 港服中文页有专属中文封面（真的换成了中文标题）
产出 covers/missing_zhcheck.json
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import identify_zh as I  # noqa: E402

BASE = os.path.dirname(os.path.abspath(__file__))
ROLE = {"P": "PORTRAIT_BANNER", "M": "MASTER"}


def main():
    rep = json.load(open(os.path.join(BASE, "covers", "missing_report.json"), encoding="utf-8"))
    by = {r["name"]: r for r in rep["items"]}
    ap = json.load(open(os.path.join(BASE, "covers", "missing_apply_report.json"), encoding="utf-8"))
    out = []
    for d in ap["added"]:
        r = by[d["name"]]
        pid = r.get("product")
        role = ROLE[d["role"]]
        en, dd = None, -1
        try:
            en = I.page_media(pid, "en-hk").get(role)
            if en:
                p = I.download(en, "en_" + role)
                dd = I.dist(I.dhash(p), I.dhash(d["to"]))
        except Exception as ex:
            print("  fail", d["name"], str(ex)[:70])
        out.append({"name": d["name"], "role": d["role"], "store": d["store"],
                    "zhEnDist": dd, "enUrl": en})
        print("%-38s %s zhEn=%s" % (d["name"][:38], d["role"], dd))
    json.dump(out, open(os.path.join(BASE, "covers", "missing_zhcheck.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    same = [x["name"] for x in out if x["zhEnDist"] == 0]
    print("\n中英同图 %d 款: %s" % (len(same), "、".join(same)))


if __name__ == "__main__":
    main()
