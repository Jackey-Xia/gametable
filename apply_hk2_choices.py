#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""apply_hk2_choices.py —— 按店主审核编号, 把 H 组(用 WPS 英文名重搜港服)选中的封面换成港服页面图。
同一基础名的多库存行一起换同一张。
直接用 hk_en_rescan 已经按形态规则处理好的成品图(/tmp/hk2_proc), 保证与预览所见一致。
用法: python3 apply_hk2_choices.py [--apply]  (默认 dry-run)
"""
import json, os, re, sys, hashlib, shutil, collections

REPO = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, REPO)
import cover_policy as CP

STATE = "/tmp/hk2_state.json"
LISTS = "/tmp/hk2_lists.json"

H_PICK = [15, 24, 25, 37, 43, 49, 56, 65]

SEQ = re.compile(r"[（(]\s*\d+\s*[）)]\s*$")
TAGZ = "hk2rc1"


def base_of(n):
    t = SEQ.sub("", n).strip()
    m = re.match(r"^(.*?)(\d+)$", t)
    if m and m[1] and not re.search(r"[0-9+\-×xX/／&·.。、\s]$", m[1]):
        t = m[1].strip()
    return t


def main():
    apply = "--apply" in sys.argv
    state = json.load(open(STATE, encoding="utf-8"))
    L = json.load(open(LISTS, encoding="utf-8"))
    man = CP.load_manifest()
    fam = collections.defaultdict(list)
    for k in man:
        fam[base_of(k)].append(k)

    todo, skip = [], []
    for i in H_PICK:
        lst = L["H"]
        if i < 1 or i > len(lst):
            skip.append((i, None, "编号越界(共%d)" % len(lst)))
            continue
        rep = lst[i - 1]
        v = state.get(rep) or {}
        proc = v.get("proc")
        if not proc or not os.path.exists(proc):
            skip.append((i, rep, "港服成品图缺失"))
            continue
        keys = sorted(set(fam.get(base_of(rep), [rep])))
        todo.append((i, rep, proc, keys, v))

    print("选中 %d 项 -> 可执行 %d | 跳过 %d" % (len(H_PICK), len(todo), len(skip)))
    for s in skip:
        print("  SKIP", s)
    print("\n明细：")
    for i, rep, proc, keys, v in todo:
        print("  H%-3d %-30s keys=%d 分%.2f cand=%s\n        形态=%s" % (
            i, rep[:30], len(keys), v.get("score", 0), (v.get("cand_name") or "")[:40],
            v.get("form_info")))
        for k in keys:
            if k != rep:
                print("        + %s" % k)

    if not apply:
        print("\n(dry-run；加 --apply 落盘)")
        return

    done = fail = files = 0
    for i, rep, proc, keys, v in todo:
        info = v.get("form_info") or ""
        padded = ("留边" in info) or ("有文字" in info)
        mode = "pad" if padded else "orig"
        rel = "covers/rc%s.jpg" % hashlib.md5((rep + "|%s|%s" % (mode, TAGZ)).encode()).hexdigest()[:12]
        dst = os.path.join(CP.BASE, rel)
        if not os.path.exists(dst):
            shutil.copy(proc, dst)
        files += 1
        role = CP.ROLE_PAD_P if padded else ("M" if "横版" in info else "P")
        note = "店主审核 H%d · 换成港服页面图 · %s" % (i, info)
        for k in keys:
            ok, msg = CP.set_cover(k, rel, CP.SRC_MANUAL, role, (v.get("cand_name") or ""), note)
            if ok:
                done += 1
            else:
                print("  ! 写入被拦截 %s: %s" % (k, msg))
                fail += 1
    print("\n完成：新增图片 %d 张，登记 %d 个键，失败 %d" % (files, done, fail))


if __name__ == "__main__":
    main()
