#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
portrait_revert.py —— 竖图形态回归（2026-09-18 店主定稿 · 需求1）
================================================================
一切以消费者前端实际展示为准（卡片 .gcover 96×128 = 3:4，object-fit:cover）：

  ① 方图（1:1 源）        -> 保持留边版 M-pad（左右各裁 63px 必切内容，留边零裁切）
  ② 竖图（非 1:1 源）     -> 若前端裁切会**遮挡文字/字母** -> 留边版 P-pad（零裁切）
                              若前端裁切**不遮挡任何文字/字母** -> 还原原图竖图版（主体更大）
                              （人物/图案被裁没关系，只看文字与字母）

裁切量：容器 3:4，图宽高比 r = w/h（< 0.75 时才被上下裁）
        上下各裁比例 cr = 0.5 * (1 - (4/3) * r)

原图来源：cover_sources.note 里记的「源 xxx.jpg」——该文件在全库留边时被删除，
          但 blob 仍在 git 历史里，用 git rev-list + git show 取回。

用法:
  python3 portrait_revert.py             # 只判定，输出统计 + /tmp/portrait_result.json
  python3 portrait_revert.py --apply     # 落盘（恢复原图 + 改写 manifest/cover_sources）
"""
import json
import os
import re
import subprocess
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
GIT = ["git", "-C", BASE]
OCR_ALL = "/tmp/ocr_all.jsonl"
OUT_JSON = "/tmp/portrait_result.json"
MARGIN = 0.006          # 判定安全边距(归一化): 文字需离裁切线 >0.6% 图高才算「不遮挡」
MIN_CONF = 0.3

import cover_policy as CP


def git(*args):
    return subprocess.run(GIT + list(args), capture_output=True)


def jpeg_size(data):
    """从 JPEG 二进制头解析 (w,h)"""
    try:
        i = 2
        n = len(data)
        while i < n - 9:
            if data[i] != 0xFF:
                i += 1
                continue
            m = data[i + 1]
            if m in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                h = int.from_bytes(data[i + 5:i + 7], "big")
                w = int.from_bytes(data[i + 7:i + 9], "big")
                return w, h
            if m in (0xD8, 0xD9) or 0xD0 <= m <= 0xD7:
                i += 2
                continue
            ln = int.from_bytes(data[i + 2:i + 4], "big")
            i += 2 + ln
    except Exception:
        pass
    return None


def load_ocr():
    d = {}
    if not os.path.exists(OCR_ALL):
        return d
    for line in open(OCR_ALL, encoding="utf-8"):
        try:
            j = json.loads(line)
        except Exception:
            continue
        d[os.path.basename(j.get("file", ""))] = j
    return d


def cut_ratio(w, h):
    """前端 96×128 显示该图时上下各裁掉的比例（相对图高）"""
    r = float(w) / float(h)
    cr = 0.5 * (1 - (4.0 / 3.0) * r)
    return cr if cr > 0 else 0.0


def blob_bytes(path):
    """从 git 历史取回已删除文件的字节。
    ⚠️ rev-list 的**第一条**往往是"删除该文件的提交"（该文件已不在树里）,
       必须往后找到第一个 git show 成功的提交。
    """
    r = git("rev-list", "-n", "8", "HEAD", "--", path)
    if r.returncode != 0:
        return None
    for sha in r.stdout.decode().split():
        s = git("show", "%s:%s" % (sha, path))
        if s.returncode == 0 and s.stdout:
            return s.stdout
    return None


def main():
    apply = "--apply" in sys.argv

    src = CP.load_sources()
    man = CP.load_manifest()
    ocr = load_ocr()

    ppad = {n: v for n, v in src.items() if v.get("role") == "P-pad"}
    print("P-pad 键:", len(ppad))

    pat = re.compile(r"源\s*([\w\-]+\.jpg)")
    revert, keep_occluded, keep_notext, nohist = [], [], [], []
    detail = {}
    occl_detail = []

    for name, rec in sorted(ppad.items()):
        cur_rel = rec.get("file") or man.get(name)
        if not cur_rel:
            continue
        cur_fn = os.path.basename(cur_rel)
        j = ocr.get(cur_fn) or {}
        blocks = [b for b in (j.get("blocks") or []) if (b.get("c") or 0) >= MIN_CONF]

        m = pat.search(rec.get("note") or "")
        if not m:
            nohist.append(name)
            continue
        old_rel = "covers/" + m.group(1)
        data = None
        if os.path.exists(os.path.join(BASE, old_rel)):
            data = open(os.path.join(BASE, old_rel), "rb").read()
        else:
            data = blob_bytes(old_rel)
        if not data:
            nohist.append(name)
            continue
        sz = jpeg_size(data)
        if not sz:
            nohist.append(name)
            continue
        w, h = sz
        if w >= h * 1.15 or abs(w * 4 - h * 3) <= 12:
            # 源不是真正的竖图（横图/已3:4）-> 保持现状
            nohist.append(name)
            continue

        cr = cut_ratio(w, h)
        if not blocks:
            keep_notext.append(name)          # OCR 未认出文字 -> 保守保持留边
            continue
        lo, hi = cr + MARGIN, 1 - cr - MARGIN
        hit = [b for b in blocks if b["y"] < lo or (b["y"] + b["h"]) > hi]
        if hit:
            keep_occluded.append(name)
            occl_detail.append({"name": name, "old": old_rel, "w": w, "h": h,
                                "cut": round(cr, 4),
                                "text": [b["t"][:20] for b in hit[:3]]})
        else:
            revert.append(name)
            detail[name] = {"old": old_rel, "w": w, "h": h, "cut": round(cr, 4),
                            "cur": cur_rel}

    print("\n=== 判定结果（竖图源 %d 个）===" % len(ppad))
    print("  还原原图竖图版（前端不遮挡文字）:", len(revert))
    print("  保持留边版  （文字会被裁）      :", len(keep_occluded))
    print("  保持留边版  （OCR 无文字/保守） :", len(keep_notext))
    print("  保持现状    （原图不可考）      :", len(nohist))

    json.dump({"revert": revert, "keep_occluded": keep_occluded,
               "keep_notext": keep_notext, "nohist": nohist,
               "detail": detail, "occluded": occl_detail},
              open(OUT_JSON, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("结果 ->", OUT_JSON)

    print("\n--- 还原样例 ---")
    for n in revert[:10]:
        d = detail[n]
        print("   %-30s %-26s %dx%d 上下各裁 %.1f%%" %
              (n[:30], os.path.basename(d["old"]), d["w"], d["h"], d["cut"] * 100))
    print("\n--- 判定遮挡样例 ---")
    for o in occl_detail[:10]:
        print("   %-30s %dx%d 被裁文字 %s" % (o["name"][:30], o["w"], o["h"], o["text"]))

    # 裁切带专项复核：窄条里另认出文字的改判为「保持留边」（保守，宁可不还原）
    excl = set()
    if os.path.exists("/tmp/band_result.json"):
        excl = set(json.load(open("/tmp/band_result.json", encoding="utf-8")).get("flagged") or [])
        if excl:
            print("\n裁切带复核改判（保持留边）:", len(excl))

    if not apply:
        print("\n(dry-run；加 --apply 落盘)")
        return

    done = 0
    for name in revert:
        if name in excl:
            continue
        d = detail[name]
        old_rel = d["old"]
        dst = os.path.join(BASE, old_rel)
        if not os.path.exists(dst):
            data = blob_bytes(old_rel)
            if not data:
                print("  ! 取回失败", name)
                continue
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            with open(dst, "wb") as f:
                f.write(data)
        rec = src.get(name) or {}
        ok, msg = CP.set_cover(name, old_rel, CP.SRC_MANUAL if hasattr(CP, "SRC_MANUAL") else "manual",
                               "P", rec.get("store", ""),
                               "竖图原图直上(前端 96×128 裁切不遮挡文字/字母, 主体更大) · 原留边版 %s" % d["cur"])
        if ok:
            done += 1
        else:
            print("  ! 写入被拦截", name, msg)
    print("已还原 %d 个竖图原图" % done)


if __name__ == "__main__":
    main()
