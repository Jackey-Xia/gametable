#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""详情节流 v2（2026-11-22）
data/game_details.json -> site/details/p00..p63.json + site/details/_keys.json

分桶规则：桶号 = ord(中文名首字符) % 64（JS 侧同式：name.charCodeAt(0) % 64）
  - 名字首字符是 BMP 内汉字（99% 情况）→ Python ord 与 JS charCodeAt 完全一致；
  - 若首字符是 emoji / 扩展 B 区（UTF-16 代理对），两侧算出的桶号不同 → 前端走整包兜底，不会取错内容。
产物是 CI 生成物（site/ 目录），不提交仓库，因此 65 个小文件不会造成 git 历史膨胀。

用法：python3 split_details.py   （在 sync_all.py 之后、upload artifact 之前）
"""
import json, os, re, sys, gzip

BASE = os.path.dirname(os.path.abspath(__file__))
SRC_DET = os.path.join(BASE, "data", "game_details.json")
OUT_DIR = os.path.join(BASE, "site", "details")
NBUCKET = 64


def gz_size(p):
    with open(p, "rb") as f:
        return len(gzip.compress(f.read(), 6))


def main():
    if not os.path.exists(SRC_DET):
        print("!! 无 data/game_details.json, 跳过详情节流")
        return 0
    det = json.load(open(SRC_DET, encoding="utf-8"))
    buckets = {}
    for k, v in det.items():
        b = (ord(k[0]) if k else 0) % NBUCKET
        buckets.setdefault(b, {})[k] = v
    os.makedirs(OUT_DIR, exist_ok=True)
    # 清空旧分片：site/details 是纯生成目录，任何 *.json 都可清（本地重复跑不留残片）
    for f in os.listdir(OUT_DIR):
        if f.endswith(".json"):
            try:
                os.remove(os.path.join(OUT_DIR, f))
            except OSError:
                pass
    total = gz_total = 0
    mx = (0, 0)
    for b in range(NBUCKET):
        mp = buckets.get(b)
        if not mp:
            continue
        p = os.path.join(OUT_DIR, "p%02d.json" % b)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(mp, f, ensure_ascii=False, separators=(",", ":"))
        raw = os.path.getsize(p)
        gz = gz_size(p)
        total += raw
        gz_total += gz
        if gz > mx[0]:
            mx = (gz, b)
    keys = sorted(det.keys())
    with open(os.path.join(OUT_DIR, "_keys.json"), "w", encoding="utf-8") as f:
        json.dump({k: 1 for k in keys}, f, ensure_ascii=False, separators=(",", ":"))
    print("详情 {} 条 -> {} 片(64 桶), raw {:.1f}KB / gz {:.1f}KB; 单片最大 {:.1f}KB(p{:02d}); _keys {:.1f}KB gz"
          .format(len(det), len(buckets), total / 1024, gz_total / 1024, mx[0] / 1024, mx[1],
                  gz_size(os.path.join(OUT_DIR, "_keys.json")) / 1024))
    return 0


if __name__ == "__main__":
    sys.exit(main())
#（注：内容由AI生成）
