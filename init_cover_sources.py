#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""init_cover_sources.py —— 一次性初始化 covers/cover_sources.json
==================================================================
按文件名前缀回溯每条封面的来源（2026-09-16 之前的历史数据）：
  - `covers/ac*.jpg`      -> source = store_zh_hk  (autocover 自动抓取)
  - 其余（`rc*`/`*_s.jpg`等）-> source = manual     (人工批次 / 店主圈定，受保护)
形态 role 由图片实际尺寸判定：高/宽 >= 1.4 -> P(竖版)，否则 M(方图)。
已存在的记录不会被覆盖（除非 --force）。
"""
import json
import os
import sys
from collections import Counter

from PIL import Image

BASE = os.path.dirname(os.path.abspath(__file__))
MANIFEST = os.path.join(BASE, "covers", "manifest.json")
SOURCES = os.path.join(BASE, "covers", "cover_sources.json")


def role_of(path):
    try:
        im = Image.open(path)
        return "P" if im.height / max(1, im.width) >= 1.4 else "M"
    except Exception:
        return ""


def main():
    force = "--force" in sys.argv
    m = json.load(open(MANIFEST, encoding="utf-8"))
    src = json.load(open(SOURCES, encoding="utf-8")) if os.path.exists(SOURCES) else {}
    if src and not force:
        print("已存在 %d 条记录，加 --force 才会重建" % len(src))

    changed = 0
    for name, rel in m.items():
        if not rel:
            continue
        p = os.path.join(BASE, rel)
        if rel.startswith("covers/ac"):
            source = "store_zh_hk"
            note = "autocover 自动抓取 · 港服中文页"
        else:
            source = "manual"
            note = "历史人工批次(受保护)"
        if name in src and not force:
            continue
        src[name] = {
            "file": rel,
            "source": source,
            "role": role_of(p),
            "store": src.get(name, {}).get("store", ""),
            "time": "2026-09-16T18:00:00",
            "note": note,
        }
        changed += 1

    json.dump(src, open(SOURCES, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    c = Counter(v["source"] for v in src.values())
    rc = Counter(v["role"] for v in src.values())
    print("初始化完成: 登记 %d 条 (本次写入 %d)" % (len(src), changed))
    print("来源分布:", dict(c))
    print("形态分布:", dict(rc))


if __name__ == "__main__":
    main()
