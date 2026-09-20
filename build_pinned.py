#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_pinned.py —— 由现有 manifest / cover_sources 生成「人工封面永久锁死表」

背景（2026-09-20 店主铁律）：
    「一旦我人工确认过的图片全部与商品锁死，即使微调了商品名称也不要删掉图片」

现有防线只靠 cover_sources.en（1215 个封面里只有 ~122 条有英文名），
改名后 91% 的封面无处可挂 -> 前端白图。本脚本把**全部人工封面**登记进
covers/pinned.json，锁的锚点有三重：
    ① 中文名（含历史名，改名后旧名也留在 cn 列表里）
    ② 英文名（有则记，en 归一化后匹配）
    ③ 图片文件 md5（同名同图/换名同图都能认出来）

只增不删：已存在的锁不会被覆盖，只做合并续期。

用法:
    python3 build_pinned.py            # 生成/合并
    python3 build_pinned.py --report   # 只看统计
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cover_policy as CP


def main():
    report = "--report" in sys.argv
    man = CP.load_manifest()
    src = CP.load_sources()
    print("manifest %d | sources %d" % (len(man), len(src)))

    p = CP.load_pinned()
    locks = p.get("locks", {})
    by_cn, by_md5 = {}, {}
    for lid, rec in locks.items():
        for cn in (rec.get("cn") or []):
            by_cn[cn] = lid
        if rec.get("md5"):
            by_md5.setdefault((rec.get("platform", "PS"), rec.get("md5")), []).append(lid)

    n_manual = n_auto = n_new = 0
    for name in sorted(man):
        rel = man.get(name)
        if not rel:
            continue
        rec = src.get(name) or {}
        # 人工确认 = 显式 manual，或历史遗留「有封面无来源记录」（保守视作人工维护过）
        if rec.get("source") == CP.SRC_STORE_ZH_HK:
            n_auto += 1
            continue
        if not os.path.exists(os.path.join(CP.BASE, rel)):
            print("   ! 文件缺失, 跳过: %s -> %s" % (name, rel))
            continue
        n_manual += 1
        if report:
            continue
        # 已锁过 -> 只续期
        if name in by_cn:
            r = locks[by_cn[name]]
            r["file"] = rel
            r["md5"] = CP._file_md5(rel)
            for k, v in (("role", rec.get("role", "")), ("store", rec.get("store", "")),
                         ("note", rec.get("note", "")), ("en", rec.get("en", ""))):
                if v:
                    r[k] = v
            continue
        md5 = CP._file_md5(rel)
        hit = by_md5.get(("PS", md5)) if md5 else None
        if hit:                      # 同图(多库存/换名不换图) -> 并入中文名历史
            r = locks[hit[0]]
            r.setdefault("cn", []).append(name)
            if rec.get("en") and not r.get("en"):
                r["en"] = rec["en"]
            by_cn[name] = hit[0]
            continue
        lid = "p%04d" % (len(locks) + 1)
        while lid in locks:
            lid = "p%04d" % (int(lid[1:]) + 1)
        locks[lid] = {
            "cn": [name], "en": rec.get("en", ""), "file": rel, "md5": md5,
            "role": rec.get("role", ""), "store": rec.get("store", ""),
            "note": rec.get("note", ""), "platform": "PS",
            "time": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        by_cn[name] = lid
        if md5:
            by_md5.setdefault(("PS", md5), []).append(lid)
        n_new += 1

    if not report:
        p["_meta"] = {"updated": time.strftime("%Y-%m-%dT%H:%M:%S"),
                      "count": len(locks),
                      "rule": "人工确认过的封面永久锁死: 改名可重挂, 图片绝不删除"}
        CP.save_pinned(p)
    print("人工封面 %d | 自动封面(未锁) %d | 新增锁 %d | 锁总数 %d"
          % (n_manual, n_auto, n_new, len(locks)))
    return 0


if __name__ == "__main__":
    main()
