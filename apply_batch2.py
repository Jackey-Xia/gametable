#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
apply_batch2.py —— 第二批封面替换（店主指定清单）
=================================================================
与 apply_zh.py 的差别：
  1. 清单里既有 NEED_ZH_IS_EN，也有 NEED_ZH_OTHER / OTHER_IMG / LOWCONF_* —— 不限状态，按名字直取
  2. 三条特殊项用 override 指定官方图（避免自动匹配到 DLC / 豪华版 / 错商品）：
     - 赛博朋克2077+往日之影（终极版）(1)(2) -> 《赛博朋克 2077：终极版》(PS5) 官方主图
     - 影子战术：爱子的选择                  -> Shadow Tactics: Aiko's Choice（普通版, 非豪华版）
     - 瑞奇与叮当                            -> 港服 PlayStation Hits 版官方图(英文 logo)
  3. 严格同形态替换：本地竖版 -> PORTRAIT_BANNER，本地方图 -> MASTER
  4. 换图必换名 covers/rc{md5(name)[:12]}.jpg（防 CDN / Service Worker 缓存），旧图删除
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
OUT = os.path.join(BASE, "covers", "zh_apply_report2.json")

WANT = ["只狼：影逝二度", "赛博朋克2077+往日之影（终极版）（1）", "赛博朋克2077+往日之影（终极版）（2）",
        "黑白莫比乌斯：岁月的代价", "AI梦境档案 涅槃肇始", "合金弹头：战略版", "失落之魂", "超级浣熊羊",
        "逆转检察官1&2：御剑精选集", "不义联盟2（传奇版）", "使命召唤16：现代战争/COD16",
        "共鸣：瘟疫传说传承1", "共鸣：瘟疫传说传承2", "女鬼桥1：开魂路", "女鬼桥2：释魂路",
        "如龙7外传 人中之龙7外传：英雄无名", "影之刃零1", "影之刃零2", "战场的赋格曲1", "春逝百年抄",
        "纪念碑谷1", "纸间迷迹", "绝对魔权1", "绝对魔权2", "英雄联盟外传：破败之王", "蠕行的恐惧",
        "巫师之昆特牌", "影子战术：爱子的选择", "层层恐惧", "海绵宝宝：宇宙摇摆",
        "超侦探事件簿 雾雨迷宫PLUS", "瑞奇与叮当"]

# 特殊指定（覆盖核查报告里的自动匹配结果）
OVERRIDE = {
    # 《赛博朋克 2077：终极版》(PS5) —— MASTER(方图)
    "赛博朋克2077+往日之影（终极版）（1）":
        "https://image.api.playstation.com/vulcan/ap/rnd/202311/2812/d2a44736cace2e6cb1a8244455e8890b0afb17d663552e7d.png",
    "赛博朋克2077+往日之影（终极版）（2）":
        "https://image.api.playstation.com/vulcan/ap/rnd/202311/2812/d2a44736cace2e6cb1a8244455e8890b0afb17d663552e7d.png",
    # Shadow Tactics: Aiko's Choice（普通版）—— PORTRAIT_BANNER(竖版)
    "影子战术：爱子的选择":
        "https://image.api.playstation.com/vulcan/ap/rnd/202402/2213/cbd33c2c0fc0d71f6947ed650a647d53024d5bada5bd0b1d.png",
    # 瑞奇与叮当 PlayStation Hits（港版/英文 logo）—— MASTER(方图)
    "瑞奇与叮当":
        "https://image.api.playstation.com/vulcan/img/rnd/202011/1020/2sD70skhUEhaf3gwCWJsEfGt.png",
}


def main():
    dry = "--dry" in sys.argv
    rep = json.load(open(REPORT, encoding="utf-8"))
    by = {i["name"]: i for i in rep.get("items") or []}
    m = json.load(open(MANIFEST, encoding="utf-8"))

    done, skip, err = [], [], []
    for name in WANT:
        r = by.get(name)
        if r is None:
            skip.append({"name": name, "why": "核查报告中无此商品"})
            continue
        shape = r.get("shLocal") or "M"
        url = OVERRIDE.get(name)
        src_kind = "override" if url else "zh"
        if not url:
            url = r.get("zhP") if shape == "P" else r.get("zhM")
        if not url:
            skip.append({"name": name, "why": "港服无该形态官方图"})
            continue
        rel = "covers/rc%s.jpg" % hashlib.md5(name.encode()).hexdigest()[:12]
        meta = {"name": name, "from": m.get(name), "to": rel, "shape": shape,
                "score": r.get("score"), "status": r.get("status"),
                "store": r.get("storeName"), "src": src_kind,
                "zhEnSame": (r.get("dZhEn") == 0)}
        if dry:
            done.append(meta)
            continue
        try:
            p = I.download(url, "b2_" + shape)
            if not p:
                raise ValueError("下载失败")
            dst = os.path.join(BASE, rel)
            with open(p, "rb") as fi, open(dst, "wb") as fo:
                fo.write(fi.read())
            if os.path.getsize(dst) < 3000:
                raise ValueError("文件过小")
            old = m.get(name)
            m[name] = rel
            # 登记为人工封面: 今后任何自动流程都不得覆盖
            CP.set_cover(name, rel, CP.SRC_MANUAL, shape, r.get("storeName", ""),
                         "店主指定清单 -> apply_batch2")
            keep = {"covers/" + os.path.basename(x) for x in m.values()}
            if old and old not in keep and os.path.exists(os.path.join(BASE, old)):
                os.remove(os.path.join(BASE, old))
            meta["size"] = os.path.getsize(dst)
            done.append(meta)
        except Exception as ex:
            err.append({"name": name, "error": str(ex)[:120]})

    if not dry:
        json.dump(m, open(MANIFEST, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    out = {"time": time.strftime("%Y-%m-%dT%H:%M:%S"), "dry": dry, "replaced": done,
           "skipped": skip, "errors": err,
           "stats": {"targets": len(WANT), "replaced": len(done), "skip": len(skip),
                     "err": len(err), "manifest": len(m)}}
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("目标 %d | 替换 %d | 跳过 %d | 失败 %d%s" % (len(WANT), len(done), len(skip), len(err),
                                                  " (dry)" if dry else ""))
    for d in done:
        print("  %-32s %-22s %s -> %s [%s]" % (d["name"][:32], d.get("from"), d.get("shape"),
                                               d["to"], d.get("src")))
    for s in skip:
        print("  SKIP", s)
    for e in err:
        print("  ERR ", e)
    print("清单 ->", OUT)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
    sys.exit(0)
