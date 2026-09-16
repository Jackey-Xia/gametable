#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
apply_zh.py —— 按 identify_zh.py 的核查结果, 把指定商品的封面替换为港服中文版官方图
=============================================================================
特点:
  - 严格按形态替换: 本地竖版(2:3) -> 港服 PORTRAIT_BANNER; 本地方图(1:1) -> 港服 MASTER
  - 只处理核查报告中指定状态的名字(默认 NEED_ZH_IS_EN; 可用 --include-lowconf 带上 LOWCONF_NEED_ZH_IS_EN)
  - 换图必换名(rc{hash}.jpg, 防 CDN 缓存), 旧文件删除; 同步更新 covers/manifest.json
  - 只动 covers/**, 不动 data/**; 生成 covers/zh_apply_report.json 变更清单

用法:
  python3 apply_zh.py --dry                 # 试跑, 只出清单不落盘
  python3 apply_zh.py                       # 执行替换(默认只换"明确是英文版"的)
  python3 apply_zh.py --include-lowconf     # 连同"匹配待确认"的一起换(风险自负)
  python3 apply_zh.py --names "光明记忆：无限" "黄泉之路"   # 只换指定的几款
"""
import hashlib
import json
import os
import sys
import time
import traceback

import autocover as A
import cover_policy as CP
import identify_zh as I

BASE = A.BASE
MANIFEST = A.MANIFEST
REPORT = os.path.join(BASE, "covers", "zh_identify_report.json")
OUT = os.path.join(BASE, "covers", "zh_apply_report.json")


def main():
    dry = "--dry" in sys.argv
    low = "--include-lowconf" in sys.argv
    only = []
    if "--names" in sys.argv:
        only = sys.argv[sys.argv.index("--names") + 1:]

    with open(REPORT, encoding="utf-8") as f:
        rep = json.load(f)
    items = rep.get("items") or []
    want = {"NEED_ZH_IS_EN"}
    if low:
        want.add("LOWCONF_NEED_ZH_IS_EN")
    targets = [r for r in items if r["status"] in want]
    if only:
        targets = [r for r in items if r["name"] in only]

    m = json.load(open(MANIFEST, encoding="utf-8"))
    done, skip, err = [], [], []
    for r in targets:
        name = r["name"]
        url = r["zhP"] if r.get("shLocal") == "P" else r["zhM"]
        if not url:
            skip.append({"name": name, "why": "港服无该形态图"})
            continue
        rel = "covers/rc%s.jpg" % hashlib.md5(name.encode()).hexdigest()[:12]
        if dry:
            done.append({"name": name, "from": m.get(name), "to": rel, "shape": r.get("shLocal"),
                         "score": r.get("score"), "store": r.get("storeName")})
            continue
        try:
            dst = os.path.join(BASE, rel)
            src = I.download(url, "zh" + r.get("shLocal", "M"))
            if not src:
                raise ValueError("下载失败")
            with open(src, "rb") as fi, open(dst, "wb") as fo:
                fo.write(fi.read())
            old = m.get(name)
            m[name] = rel
            # 登记为人工封面: 今后任何自动流程都不得覆盖
            CP.set_cover(name, rel, CP.SRC_MANUAL, r.get("shLocal", ""),
                         r.get("storeName", ""), "店主圈定清单 -> apply_zh")
            keep = {"covers/" + os.path.basename(p) for p in m.values()}
            if old and old not in keep and os.path.exists(os.path.join(BASE, old)):
                os.remove(os.path.join(BASE, old))
            done.append({"name": name, "from": old, "to": rel, "shape": r.get("shLocal"),
                         "score": r.get("score"), "store": r.get("storeName")})
        except Exception as ex:
            err.append({"name": name, "error": str(ex)[:120]})

    if not dry:
        json.dump(m, open(MANIFEST, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    out = {"time": time.strftime("%Y-%m-%dT%H:%M:%S"), "dry": dry, "replaced": done,
           "skipped": skip, "errors": err,
           "stats": {"targets": len(targets), "replaced": len(done), "skip": len(skip), "err": len(err),
                     "manifest": len(m)}}
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("目标 %d | 替换 %d | 跳过 %d | 失败 %d%s" % (len(targets), len(done), len(skip), len(err),
                                                " (dry-run 未落盘)" if dry else ""))
    for d in done[:40]:
        print("  %-32s %s -> %s (%s)" % (d["name"][:32], d.get("from"), d["to"], d.get("shape")))
    print("清单 ->", OUT)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
    sys.exit(0)
