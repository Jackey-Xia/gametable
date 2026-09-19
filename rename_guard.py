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


def norm_en(s):
    """英文名归一化: 小写 + 只留字母数字(用于宽松包含匹配)"""
    return "".join(ch for ch in str(s or "").lower() if ch.isalnum())


def strip_alias(s):
    """去掉中文名里的斜杠别名段, 用于判断"规范化改名"
    '使命召唤12：黑色行动3/COD12（僵尸编年史版）' -> '使命召唤12：黑色行动3（僵尸编年史版）'
    """
    import re
    # 只删 "/COD12" 这类 ASCII 别名段(遇中文/全角括号即停), 避免吃掉后面的版本括注
    t = re.sub(r"[/／][A-Za-z0-9\s·_\-\.]*", "", str(s or ""))
    return re.sub(r"[\s　]", "", t)


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
    en2names_norm = {}
    for n, en in grid:
        if en:
            en2names_norm.setdefault(norm_en(en), []).append(n)

    moved, nohit = [], []
    for k in sorted(orphans):
        rec = src.get(k) or {}
        key_en = (rec.get("en") or "").strip().lower()
        cands = []
        if k.strip().lower() in en2names:
            cands += en2names[k.strip().lower()]
        if key_en and key_en in en2names:
            cands += en2names[key_en]
        # ★ 英文名放宽: 归一化后相等, 或一方包含另一方(长度>=10)
        kn = norm_en(rec.get("en") or "")
        for cand_en, names in en2names_norm.items():
            if not cand_en or len(cand_en) < 10:
                continue
            if kn and len(kn) >= 10 and (cand_en in kn or kn in cand_en):
                cands += names
            if k.strip() and norm_en(k) and len(norm_en(k)) >= 10 \
               and (cand_en in norm_en(k) or norm_en(k) in cand_en):
                cands += names
        # ★★ 中文名规范化: 去掉 "/COD12" 这类斜杠别名段后相等 -> 同一商品改名, 沿用
        kb = strip_alias(k)
        if kb:
            for n, _en in grid:
                if n in m:
                    continue
                if strip_alias(n) == kb:
                    cands.append(n)
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
