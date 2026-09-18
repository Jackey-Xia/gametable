#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
inherit_stock_covers.py —— 多库存封面沿用（2026-09-18 店主定稿）
================================================================
场景：店主给同一款游戏加库存时，WPS 表会拆成多行，商品名带库存序号，例如
        漫威金刚狼1 / 漫威金刚狼2 / … / 漫威金刚狼8
        鬼武者：剑之道1 … 鬼武者：剑之道8
        黑暗之魂3（豪华版）（1）/（2）

铁律（店主原话）：
  「像金刚狼、鬼武者这种同一商品多库存的，一旦确认仅增加了库存、而不是版本变化，
    那图片可直接延用。不要因为新增了金刚狼7 导致既不能读取已上传的、又不敢去抓图，
    反而 1~6 的图也没了。前端同一商品多库存只显示一个，
    你不能把已有已确定的图片给我清掉留空。」

本脚本因此只做一件事：**只增不删**
  - 只给「manifest 里还没有这个名字」的库存行补登记封面；
  - 封面直接沿用同款（同一基础名 + 同一英文名）已登记的那张图；
  - 绝不动、绝不删、绝不覆盖任何已存在的封面键（包括 1~6 这些已确认的）。

同款(同族)判据 —— 与前端 dupOf 一致，宁可保守：
  1. 去尾部库存序号后的基础名相同（支持 （1）/ (2) 与裸数字 1/2/3）
     · 数字前是 + - × x / & · 等连字符的不算库存序号（鬼武者1+2、FF7 重制 这类是作品名）
  2. 英文名归一化后相同（两边都空也算相同；一边空一边非空时，要求三项租金+发售日期全同）
  3. 发售地区都非空且不同 -> 视为不同版本，不沿用

用法:
  python3 inherit_stock_covers.py            # 正式写入
  python3 inherit_stock_covers.py --dry      # 只报告不改文件
"""
import json
import os
import re
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
GAMES = os.path.join(BASE, "data", "ps_games.json")   # parse_ps.py 产物(每次构建现生成)
GRID = os.path.join(BASE, "data", "ps_grid.json")
STATE = os.path.join(BASE, "covers", "auto_state.json")

import cover_policy as CP

# 尾部库存序号: 括号数字 / 裸数字(数字前不能是连字符或数字)
SEQ_KAKO = re.compile(r"[（(]\s*\d+\s*[）)]\s*$")
SEQ_BARE = re.compile(r"^(.*?)(\d+)$")


def seq_base(n):
    """去尾部库存序号 -> (base, is_seq)
    鬼武者1+2      -> ('鬼武者1+2', False)   # + 后面是作品序号, 不是库存序号
    漫威金刚狼7    -> ('漫威金刚狼', True)
    黑暗之魂3（豪华版）（1） -> ('黑暗之魂3（豪华版）', True)
    """
    s = str(n or "").strip()
    t = SEQ_KAKO.sub("", s).strip()
    while True:                      # 可能多层: X（1）（2）
        t2 = SEQ_KAKO.sub("", t).strip()
        if t2 == t:
            break
        t = t2
    m = SEQ_BARE.match(t)
    if m and m.group(1):
        head = m.group(1)
        if not re.search(r"[0-9+\-×xX/／&·.。、\s]$", head):
            return head.strip(), True
    return (t, True) if t != s else (s, False)


def en_key(s):
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower())


def load_records():
    """返回 [(name, en, region, ck7, fc7, xd30, date)]，保持表格顺序"""
    recs, seen = [], set()
    if os.path.exists(GAMES):
        try:
            for g in json.load(open(GAMES, encoding="utf-8")):
                n = str(g.get("name") or "").strip()
                if not n or n in seen:
                    continue
                seen.add(n)
                recs.append((n, str(g.get("en") or ""), str(g.get("region") or "").strip(),
                             str(g.get("ck7") or ""), str(g.get("fc7") or ""),
                             str(g.get("xd30") or ""), str(g.get("date") or "")))
        except Exception as e:
            print("ps_games.json 读取失败(%s), 回退 ps_grid" % e)
    if not recs and os.path.exists(GRID):
        try:
            rows = json.load(open(GRID, encoding="utf-8")).get("rows") or []
            for r in rows[2:]:
                if not r or len(r) < 5:
                    continue
                n = str(r[2] or "").strip()
                if not n or n in seen:
                    continue
                seen.add(n)
                recs.append((n, str(r[3] or ""), str(r[6] or "").strip(),
                             str(r[8] or ""), str(r[10] or ""), str(r[12] or ""), str(r[4] or "")))
        except Exception as e:
            print("ps_grid.json 读取失败: %s" % e)
    return recs


def same_family(a, b):
    """两条记录是否为「同一商品的不同库存」"""
    na, ea, ra, pa = a[0], en_key(a[1]), str(a[2] or "").replace(" ", ""), (a[3], a[4], a[5], a[6])
    nb, eb, rb, pb = b[0], en_key(b[1]), str(b[2] or "").replace(" ", ""), (b[3], b[4], b[5], b[6])
    ba, sa = seq_base(na)
    bb, sb = seq_base(nb)
    if not (sa and sb) or ba != bb or not ba:
        return False
    if ra and rb and ra != rb:          # 地区都填了且不同 -> 不同版本
        return False
    if ea and eb:
        return ea == eb
    if not ea and not eb:
        return True
    return pa == pb                      # 一方英文名缺失: 靠 价格+日期 兜底


def main():
    dry = "--dry" in sys.argv
    recs = load_records()
    m = CP.load_manifest()
    src = CP.load_sources()
    print("表内商品 %d | 已登记封面 %d" % (len(recs), len(m)))

    miss = [r for r in recs if r[0] not in m]
    print("无封面 %d" % len(miss))
    if not miss:
        return 0

    # 已有封面的记录，按表格顺序（同款取最靠前那行，通常是店主最早确认的那张）
    covered = [r for r in recs if r[0] in m]
    added = []
    for r in miss:
        donor = None
        for c in covered:
            if same_family(r, c):
                donor = c
                break
        if not donor:
            continue
        rel = m[donor[0]]
        rec = src.get(donor[0]) or {}
        # 沿用来源: 人工指定的仍记 manual(受保护, 自动流程不得覆盖); 自动抓的记 store_zh_hk
        source = rec.get("source") or CP.SRC_MANUAL
        note = "多库存沿用: 与《%s》同一商品仅增加库存, 直接沿用同款封面" % donor[0]
        if dry:
            print("  [dry] %s  <-  %s (%s)" % (r[0], donor[0], rel))
            added.append((r[0], rel))
            continue
        ok, msg = CP.set_cover(r[0], rel, source, rec.get("role", ""), rec.get("store", ""), note)
        if ok:
            m = CP.load_manifest()      # set_cover 已落盘, 刷新内存避免后续误判
            covered.append(r)
            print("  + %s  <-  %s (%s)" % (r[0], donor[0], rel))
            added.append((r[0], rel))
        else:
            print("  ! %s 写入被拦截: %s" % (r[0], msg))

    print("沿用 %d 个多库存封面%s" % (len(added), "（dry-run 未写入）" if dry else ""))

    # 顺手清掉 auto_state 里已不在表内的残留键（如店主删掉的 漫威金刚狼8），避免旧 pending 干扰
    if not dry:
        try:
            state = json.load(open(STATE, encoding="utf-8"))
            live = {r[0] for r in recs}
            dead = [k for k in state if k not in live]
            if dead:
                for k in dead:
                    state.pop(k, None)
                state = {k: state[k] for k in sorted(state)}
                json.dump(state, open(STATE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
                print("清理 auto_state 残留 %d 条: %s" % (len(dead), "、".join(dead[:8])))
        except Exception:
            pass
    return len(added)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("inherit 异常(不阻断部署): %s" % e)
