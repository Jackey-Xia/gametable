#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""lock_covers.py —— 人工封面「锁死」守护：改名后自动重挂，绝不删图
================================================================
店主铁律（2026-09-20）：
    「一旦我人工确认过的图片全部与商品锁死，即使微调了商品名称也不要删掉图片」

与 rename_guard.py 的分工
------------------------
rename_guard : 只认英文名（1215 个封面里仅 ~122 条有 en），改名后覆盖不到 91% 的封面。
lock_covers  : 读 covers/pinned.json（全部人工封面的锁），三重锚点匹配 ——
               ① 中文名完全一致（含历史名）
               ② 英文名归一化一致
               ③ 中文名近似 + **版本标注必须一致**（difflib 相似度 ≥ 0.75，
                  且锁与候选的「（豪华版）/（完整版）/（终极版）…」标注集合完全相同）

铁律约束
--------
· 只增不删：只给「表里存在、manifest 里没封面」的行补登记；旧键、旧图一律保留。
· 绝不覆盖：manifest 已有封面的行，一个字都不动。
· 绝不删除：任何情况下不删 manifest 键、不删图片文件。
· 尊重 auto_skip：店主主动置空的商品不补图。
· 宁可漏挂、不可错挂：相似度不够 / 有多义候选 / 版本标注不一致 -> 跳过并打印待确认。

用法:
    python3 lock_covers.py           # dry-run
    python3 lock_covers.py --apply   # 落盘
"""
import difflib
import json
import os
import re
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
import cover_policy as CP  # noqa: E402

GAMES = os.path.join(BASE, "data", "ps_games.json")
GRID = os.path.join(BASE, "data", "ps_grid.json")
AUTO_SKIP = os.path.join(BASE, "covers", "auto_skip.json")

SEQ_KAKO = re.compile(r"[（(]\s*\d+\s*[）)]\s*$")
PAREN = re.compile(r"[（(]([^（）()]{1,14})[）)]")


# ---------------------------------------------------------------- 归一化工具
def norm_cn(s):
    """中文名归一化：去空白、去尾部库存序号、全角括号统一"""
    s = str(s or "").strip()
    t = SEQ_KAKO.sub("", s).strip()
    while True:
        t2 = SEQ_KAKO.sub("", t).strip()
        if t2 == t:
            break
        t = t2
    t = t.replace("　", "").replace(" ", "")
    return t


def en_key(s):
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower())


def version_tags(s):
    """版本标注集合：'真·三国无双 起源（豪华版）' -> {'豪华版'}（纯数字库存序号不算）"""
    out = set()
    for g in PAREN.findall(str(s or "")):
        g = g.strip()
        if not g or g.isdigit():
            continue
        out.add(g)
    return out


def numbers(s):
    """作品序号集合：去掉所有括号内容后取数字串
    '使命召唤16：现代战争（重制版）' -> {'16'}
    '使命召唤6：现代战争2（重制版）' -> {'6','2'}
    用于硬性拦截「COD16 错挂 COD6 封面」这类只差一个数字的误匹配。
    """
    t = re.sub(r"[（(][^（）()]*[）)]", "", str(s or ""))
    return set(re.findall(r"\d+", t))


def strip_alias(s):
    """去掉 '/P3R' '/COD12' 这类 ASCII 斜杠别名段"""
    t = re.sub(r"[/／][A-Za-z0-9\s·_\-\.]*", "", str(s or ""))
    return re.sub(r"[\s　]", "", t)


def bigrams(s):
    s = norm_cn(s)
    if len(s) < 2:
        return {s} if s else set()
    return {s[i:i + 2] for i in range(len(s) - 1)}


def sim(a, b):
    return difflib.SequenceMatcher(None, a, b).ratio()


# ---------------------------------------------------------------- 数据加载
def load_rows():
    """[(name, en)] 保持表格顺序"""
    rows, seen = [], set()
    if os.path.exists(GAMES):
        try:
            for g in json.load(open(GAMES, encoding="utf-8")):
                n = str(g.get("name") or "").strip()
                if not n or n in seen:
                    continue
                seen.add(n)
                rows.append((n, str(g.get("en") or "")))
        except Exception as e:
            print("ps_games.json 读取失败(%s), 回退 ps_grid" % e)
    if not rows and os.path.exists(GRID):
        try:
            for r in (json.load(open(GRID, encoding="utf-8")).get("rows") or [])[2:]:
                if not r or len(r) < 3:
                    continue
                n = str(r[2] or "").strip()
                if not n or n in seen:
                    continue
                seen.add(n)
                rows.append((n, str(r[3] or "") if len(r) > 3 else ""))
        except Exception as e:
            print("ps_grid.json 读取失败: %s" % e)
    return rows


def load_skip():
    if not os.path.exists(AUTO_SKIP):
        return set()
    try:
        v = json.load(open(AUTO_SKIP, encoding="utf-8"))
        if isinstance(v, list):
            return {str(x).strip() for x in v}
        if isinstance(v, dict):
            return {str(k).strip() for k in v}
    except Exception:
        pass
    return set()


# ---------------------------------------------------------------- 匹配
def build_index(locks):
    """{bigram: [lid]} 倒排 + 英文名索引"""
    bg, ek = {}, {}
    for lid, rec in locks.items():
        ekv = en_key(rec.get("en"))
        if ekv and len(ekv) >= 6:
            ek.setdefault(ekv, []).append(lid)
        for cn in (rec.get("cn") or []):
            for b in bigrams(cn):
                bg.setdefault(b, []).append(lid)
    return bg, ek


def match_lock(name, en, locks, bg, ek, table_set):
    """返回 (lid, score, why) 或 (None, 0, 原因)"""
    nn = norm_cn(name)
    if not nn:
        return None, 0, "空名"
    ncn = strip_alias(name)
    nvt = version_tags(name)
    nnum = numbers(name)

    # ① 中文名完全一致
    for lid, rec in locks.items():
        for cn in (rec.get("cn") or []):
            if norm_cn(cn) == nn or strip_alias(cn) == ncn:
                return lid, 1.0, "中文名一致"
    # ② 英文名一致（版本标注也须一致，避免基础版/豪华版互挂）
    ekv = en_key(en)
    if ekv and len(ekv) >= 6:
        for lid in ek.get(ekv, []):
            rec = locks[lid]
            if en_key(rec.get("en")) != ekv:
                continue
            cns = rec.get("cn") or []
            if cns and version_tags(cns[0]) == nvt:
                return lid, 0.99, "英文名一致"
    # ③ 中文名近似（bigram 倒排取候选）
    cands = {}
    for b in bigrams(name):
        for lid in bg.get(b, []):
            cands[lid] = cands.get(lid, 0) + 1
    if not cands:
        return None, 0, "无候选"
    ranked = sorted(cands.items(), key=lambda kv: -kv[1])[:40]
    scored = []
    for lid, _ov in ranked:
        rec = locks[lid]
        best, bestcn = 0.0, ""
        for cn in (rec.get("cn") or []):
            # ★ 硬护栏一：作品序号不一致 -> 直接判负（COD16 绝不能挂 COD6 的图）
            cnum = numbers(cn)
            if nnum and cnum and nnum != cnum:
                continue
            a, b = norm_cn(cn), nn
            sa = strip_alias(cn)
            r = max(sim(a, b), sim(sa, ncn))
            # ★ 硬护栏二：版本标注（豪华版/完整版/终极版…）不同 -> 视为不同版本商品
            if version_tags(cn) != nvt:
                r -= 0.35
            if r > best:
                best, bestcn = r, cn
        if best >= 0.75:
            scored.append((best, lid, bestcn))
    if not scored:
        return None, 0, "相似度不足/序号不符"
    scored.sort(key=lambda t: -t[0])
    top = scored[0]
    if len(scored) > 1 and top[0] - scored[1][0] < 0.06:
        return None, top[0], "多义候选(%s)" % "、".join(
            (locks[s[1]].get("cn") or ["?"])[0][:12] for s in scored[:2])
    return top[1], top[0], "近似匹配 %.2f 《%s》" % (top[0], top[2][:24])


def main():
    apply = "--apply" in sys.argv
    locks = CP.load_pinned().get("locks", {})
    if not locks:
        print("pinned.json 无锁记录 —— 先跑 build_pinned.py")
        return 0
    rows = load_rows()
    table = {norm_cn(n) for n, _ in rows}
    skip = load_skip()
    m = CP.load_manifest()
    src = CP.load_sources()
    print("表内商品 %d | 锁 %d | 已登记封面 %d | auto_skip %d"
          % (len(rows), len(locks), len(m), len(skip)))

    bg, ek = build_index(locks)
    need = [(n, e) for n, e in rows if n not in m and n.strip() not in skip]
    print("待补封面 %d" % len(need))
    if not need:
        return 0

    bound, pending = [], []
    for name, en in need:
        lid, score, why = match_lock(name, en, locks, bg, ek, table)
        if not lid:
            pending.append((name, why, score))
            continue
        rec = locks[lid]
        rel = rec.get("file")
        if not rel or not os.path.exists(os.path.join(BASE, rel)):
            pending.append((name, "锁内图片缺失 %s" % rel, score))
            continue
        if apply:
            ok, msg = CP.set_cover(
                name, rel, CP.SRC_MANUAL, rec.get("role", ""), rec.get("store", ""),
                "★人工锁死沿用(锁%s, %s)" % (lid, why), en=en or rec.get("en", ""))
            if not ok:
                print("   ! 写入被拦截 %s : %s" % (name, msg))
                continue
            m = CP.load_manifest()
            # 把新名字并进锁的中文名历史，下次再改名仍能认出
            try:
                CP.pin_lock(name, rel, rec.get("role", ""), rec.get("store", ""),
                            rec.get("note", ""), en or rec.get("en", ""), "PS")
            except Exception:
                pass
        bound.append((name, rec.get("cn", ["?"])[0], rel, why))

    print("锁死重挂 %d | 待人工确认 %d%s"
          % (len(bound), len(pending), "" if apply else "（dry-run 未写入）"))
    for name, old, rel, why in bound:
        print("   ✓ %s  <-  锁《%s》 %s  [%s]" % (name, old, rel, why))
    if pending:
        print("   待确认(宁漏不挂):")
        for name, why, sc in pending[:25]:
            print("     ? %s  (%s, %.2f)" % (name, why, sc))
    return len(bound)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("lock_covers 异常(不阻断部署): %s" % e)
