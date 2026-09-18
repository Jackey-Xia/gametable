#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""apply_en_choices.py —— 按店主审核编号, 把 E/F 组选中的封面换成美服页面图。
同一基础名的多库存行一起换同一张。
用法: python3 apply_en_choices.py [--dry]  (默认 dry-run)
"""
import json, os, re, sys, hashlib, shutil, collections

REPO = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, REPO)
import cover_policy as CP

STATE = "/tmp/en_state.json"
LISTS = "/tmp/en_review_lists.json"

E_PICK = [3, 5, 6, 12, 16, 17, 22, 23, 25, 32, 37, 43, 47, 52, 53, 55, 58, 59,
          71, 83, 89, 90, 91, 92, 95, 96, 97, 101, 110, 112, 113, 114]
F_PICK = [3, 6]

SEQ = re.compile(r"[（(]\s*\d+\s*[）)]\s*$")

# 人工纠偏：自动匹配明显指错条目时, 在这里指定正确的商城条目名（仍按美服取图）
OVERRIDE = {
    "魔界村 经典回归": "Ghosts 'n Goblins Resurrection",   # 自动匹成了另一款《Goblins》
}


def override_raw(rep, term):
    """按指定条目名重新取图, 返回本地路径或 None"""
    import en_rescan as ER
    try:
        rs = ER.search_en(term)
    except Exception as ex:
        print("  ! 纠偏搜索失败", rep, ex)
        return None
    best = None
    for c in rs:
        if c["name"].strip().lower() == term.strip().lower():
            best = c
            break
    if best is None and rs:
        best = rs[0]
    if best is None:
        return None
    media = best.get("media") or [{"role": "MASTER", "url": best.get("master")},
                                  {"role": "PORTRAIT_BANNER", "url": best.get("portrait")}]
    role, url = CP.pick_role(media)
    if not url:
        return None
    import hashlib
    p = "/tmp/en_cand/ov%s.jpg" % hashlib.md5((rep + term).encode()).hexdigest()[:12]
    if not os.path.exists(p):
        import autocover as AC
        AC.http_download(url, p)
    return p


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
    for tag, lst, picks in (("E", L["E"], E_PICK), ("F", L["F"], F_PICK)):
        for i in picks:
            if i < 1 or i > len(lst):
                print("  ! 编号越界 %s%d (共%d)" % (tag, i, len(lst)))
                continue
            targets.append((tag, i, lst[i - 1]))

    todo, skip = [], []
    for tag, i, rep in targets:
        v = state.get(rep) or {}
        raw = v.get("raw")
        if rep in OVERRIDE:
            ov = override_raw(rep, OVERRIDE[rep])
            if ov:
                raw = ov
                v = dict(v); v["cand_name"] = OVERRIDE[rep] + " (人工纠偏)"
                v["raw"] = ov
        if not raw or not os.path.exists(raw):
            skip.append((tag, i, rep, "美服图未下载"))
            continue
        keys = sorted(fam.get(base_of(rep), [rep]))
        todo.append((tag, i, rep, raw, keys, v))

    print("选中 %d 项 -> 可执行 %d | 跳过 %d" % (len(targets), len(todo), len(skip)))
    for s in skip:
        print("  SKIP", s)
    print("\n明细：")
    for tag, i, rep, raw, keys, v in todo:
        print("  %s%-3d %-28s keys=%d score=%.2f cand=%s" % (
            tag, i, rep[:28], len(keys), v.get("score", 0), (v.get("cand_name") or "")[:36]))

    if dry:
        print("\n(dry-run；加 --apply 落盘)")
        return

    done = fail = files = 0
    for tag, i, rep, raw, keys, v in todo:
        mode, info = CP.decide_form(raw)
        TagZ = "usrc1"
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
        note = "店主审核 %s%d · 换成美服页面图 · %s" % (tag, i, info)
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
