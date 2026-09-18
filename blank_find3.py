#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""blank_find3.py —— 任务2 第④步补充: 对仍未找到的商品用人工短词再搜游民星空。"""
import json, os, sys

REPO = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, REPO)
import gamersky_cover as GK

STATE = "/tmp/blank_state.json"
SRC = "/tmp/blank_orig"

# 商品 -> 游民星空搜索词（按顺序试）
TERMS = {
    "文明7 席德·梅尔的文明帝国7（完整版）": ["文明7", "文明VII"],
    "饥荒（联机版）": ["饥荒：联机版", "饥荒"],
    "三国志8 威力加强版": ["三国志8", "三国志VIII", "三国志8威力加强版"],
    "异形：火力小队精英1（终极版）": ["异形：火力小队", "异形 火力小队精英"],
    "死亡之屋1（重制版）": ["死亡之屋 重制版", "死亡之屋", "HOUSE OF THE DEAD"],
    "莱莎的炼金工房1～常暗女王与秘密藏身处～": ["莱莎的炼金工房 常暗女王", "莱莎的炼金工房1", "莱莎的炼金工房"],
    "行尸走肉1（完整版）（美版英文）": ["行尸走肉 第一季", "行尸走肉"],
    "行尸走肉2（美版英文）": ["行尸走肉 第二季", "行尸走肉2"],
    "行尸走肉3": ["行尸走肉 新边界", "行尸走肉 第三季"],
    "行尸走肉4（完整版）": ["行尸走肉 最终季", "行尸走肉 第四季"],
}

state = json.load(open(STATE, encoding="utf-8"))
for rep, terms in TERMS.items():
    v = state.get(rep)
    if not v or not (v.get("step") or "").startswith("未找到"):
        continue
    hit = None
    for t in terms:
        try:
            it = GK.fetch(t, term=t)
        except Exception:
            it = None
        if it and it.get("url") and it.get("score", 0) >= 0.9:
            hit = (t, it)
            break
    if not hit:
        print("  仍无:", rep[:26])
        continue
    t, it = hit
    try:
        GK.download({"url": it["url"]}, os.path.join(SRC, "%04d.jpg" % v["i"]))
        v.update({"step": "④网上找图(游民短词)", "cand": it.get("storeName", ""), "role": "GAMERSKY"})
        state[rep] = v
        print("  命中:", rep[:26], "->", it.get("storeName", ""))
    except Exception as ex:
        print("  下载失败:", rep[:26], ex)
json.dump(state, open(STATE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
