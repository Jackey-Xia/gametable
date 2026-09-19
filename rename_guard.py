#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""rename_guard.py —— 店主在 WPS 里改商品中文名后，封面自动沿用（防「封面消失」）

场景：商品「Keeper」改名「守望者」（英文名 Keeper 不变、分组 K→S）后，
      封面 manifest 的键仍是旧中文名 -> 前端按新名查不到 -> 显示占位图。

判定：孤儿键（manifest 里有封面、但表里已没有这个中文名）
      命中一行「英文名 == 孤儿键」或「英文名 == 记录里的 en」且该行目前没有封面
      -> 把旧封面登记到新中文名下（旧键保留兜底，只增不删）

用法：
  python3 rename_guard.py           # dry-run
  python3 rename_guard.py --apply   # 落盘登记
"""
import json, os, sys

REPO = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, REPO)
import cover_policy as CP

GRID = os.path.join(REPO, "data", "ps_grid.json")


def load_grid():
    g = json.load(open(GRID, encoding="utf-8"))
    rows = (g.get("rows") or [])[2:]
    out = []
    for r in rows:
        if not r or len(r) < 3:
            continue
        name = str(r[2]).strip() if r[2] else ""
        if not name:
            continue
        en = str(r[3]).strip() if len(r) > 3 and r[3] else ""
        out.append((name, en))
    return out


def main():
    apply = "--apply" in sys.argv
    m = CP.load_manifest()
    src = CP.load_sources()
    grid = load_grid()
    table = {n for n, _ in grid}

    orphans = [k for k in m if k not in table and m.get(k)
               and os.path.exists(os.path.join(REPO, m[k]))]
    en2names = {}
    for n, en in grid:
        if en:
            en2names.setdefault(en.lower(), []).append(n)

    moved, nohit = [], []
    for k in sorted(orphans):
        rec = src.get(k) or {}
        key_en = (rec.get("en") or "").strip().lower()
        cands = []
        if k.strip().lower() in en2names:
            cands += en2names[k.strip().lower()]
        if key_en and key_en in en2names:
            cands += en2names[key_en]
        cands = [n for n in dict.fromkeys(cands) if n not in m]
        if not cands:
            nohit.append(k)
            continue
        rel = m[k]
        for n in cands:
            note = (rec.get("note") or "") + " · 改名沿用(旧键: %s)" % k
            if apply:
                ok, msg = CP.set_cover(n, rel, rec.get("source") or "manual",
                                       rec.get("role", ""), rec.get("store", ""),
                                       note, en=dict(grid).get(n, ""))
                if not ok:
                    print("   ! 失败 %s -> %s : %s" % (k, n, msg))
                    continue
                m = CP.load_manifest()
            moved.append((k, n, rel))

    print("孤儿键 %d | 改名沿用 %d | 无匹配 %d" % (len(orphans), len(moved), len(nohit)))
    for k, n, rel in moved:
        print("   %s  ->  %s   (%s)" % (k, n, rel))
    if nohit:
        print("   无匹配(改名/下架待确认):", nohit[:20])
    if not apply:
        print("(dry-run) 加 --apply 落盘")


if __name__ == "__main__":
    main()
