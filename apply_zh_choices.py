#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""apply_zh_choices.py —— 按店主审核编号, 把 A/B 组选中的封面换成港服页面图。
同一基础名的多库存行一起换同一张（前端同款只显示一张）。
用法: python3 apply_zh_choices.py [--dry]  (默认 dry-run)
"""
import json, os, re, sys, collections

REPO = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, REPO)
import cover_policy as CP

STATE = "/tmp/zh_state.json"
LISTS = "/tmp/zh_review_lists.json"

A_PICK = [1, 6, 9, 10, 11, 13, 14, 15, 16, 17, 18, 20, 21, 22, 23, 25, 26, 28, 29]
B_PICK = [6, 14, 17, 22, 25, 26, 27, 28, 29, 32, 33, 34, 36, 41, 42, 43, 53, 60, 64, 66, 67, 68,
          69, 71, 76, 77, 78, 80, 81, 83, 84, 86, 87, 88, 90, 91, 92, 93, 94, 95, 96, 98, 99,
          100, 101, 102, 103, 104, 105, 108, 109, 110, 111, 112, 113, 114, 115, 117, 118, 119,
          120, 121, 122, 123, 124, 125, 126, 127, 128, 129, 131, 132, 134, 136, 137, 138, 139,
          140, 141, 142, 144, 145, 146, 147, 151, 152, 153, 154, 155, 156, 157]

SEQ = re.compile(r"[（(]\s*\d+\s*[）)]\s*$")


def base_of(n):
    t = SEQ.sub("", n).strip()
    m = re.match(r"^(.*?)(\d+)$", t)
    if m and m[1] and not re.search(r"[0-9+\-×xX/／&·.。、\s]$", m[1]):
        t = m[1].strip()
    return t


def main():
    dry = "--dry" in sys.argv
    state = json.load(open(STATE, encoding="utf-8"))
    L = json.load(open(LISTS, encoding="utf-8"))
    man = CP.load_manifest()

    fam = collections.defaultdict(list)
    for k in man:
        fam[base_of(k)].append(k)

    targets = []
    for tag, lst, picks in (("A", L["A"], A_PICK), ("B", L["B"], B_PICK)):
        for i in picks:
            if i < 1 or i > len(lst):
                print("  ! 编号越界 %s%d (共%d)" % (tag, i, len(lst)))
                continue
            targets.append((tag, i, lst[i - 1]))

    todo, skip = [], []
    for tag, i, rep in targets:
        v = state.get(rep) or {}
        raw = v.get("raw")
        if not raw or not os.path.exists(raw):
            skip.append((tag, i, rep, "港服图未下载"))
            continue
        keys = sorted(fam.get(base_of(rep), [rep]))
        todo.append((tag, i, rep, raw, keys, v))

    print("选中 %d 项 -> 可执行 %d | 跳过 %d" % (len(targets), len(todo), len(skip)))
    for s in skip:
        print("  SKIP", s)
    print("\n明细：")
    for tag, i, rep, raw, keys, v in todo:
        print("  %s%-3d %-30s keys=%d score=%.2f cand=%s" % (
            tag, i, rep[:30], len(keys), v.get("score", 0), (v.get("cand_name") or "")[:34]))

    if dry:
        print("\n(dry-run；确认无误加 --apply 落盘)")
        return

    import hashlib, shutil
    done = fail = files = 0
    for tag, i, rep, raw, keys, v in todo:
        mode, info = CP.decide_form(raw)
        TagZ = "hkrc1"
        if mode == "pad":
            rel = "covers/rc%s.jpg" % hashlib.md5((rep + "|pad34|" + TagZ).encode()).hexdigest()[:12]
            if not CP.make_pad_auto(raw, os.path.join(CP.BASE, rel)):
                print("  ! 留边失败", rep, info); fail += 1; continue
            role = CP.ROLE_PAD_P if "竖图" in info else CP.ROLE_PAD
        else:
            suffix = "keep" if mode == "keep" else "orig"
            rel = "covers/rc%s.jpg" % hashlib.md5((rep + "|%s|%s" % (suffix, TagZ)).encode()).hexdigest()[:12]
            shutil.copy(raw, os.path.join(CP.BASE, rel))
            role = "M" if "横版" in info else "P"
        files += 1
        note = "店主审核 %s%d · 换成港服页面图 · %s" % (tag, i, info)
        for k in keys:
            ok, msg = CP.set_cover(k, rel, CP.SRC_MANUAL, role,
                                   (v.get("cand_name") or ""), note)
            if ok:
                done += 1
            else:
                print("  ! 写入被拦截 %s: %s" % (k, msg)); fail += 1
    print("\n完成：新增图片 %d 张，登记 %d 个键，失败 %d" % (files, done, fail))


if __name__ == "__main__":
    main()
