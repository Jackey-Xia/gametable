#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""全库封面统一改成 3:4 留边版（2026-09-18 店主定稿：所有封面一律留边，零裁切）

- 方图(≈1:1)  -> 缩到 504 见方居中 + 上下虚化补边
- 竖图/横图   -> 整图等比完整保留 + 左右（或上下）虚化补边
- 已是 3:4    -> 跳过

同一张源图被多个商品名共用时只算一次补边，再复制到各自文件名。
文件名沿用既有约定 rc{md5(商品名+'|pad34')[:12]}.jpg（换名即刷新前端缓存）。

用法: python3 pad_all.py          # dry-run
      python3 pad_all.py --apply  # 真正写入并删除旧图
"""
import hashlib
import os
import shutil
import sys
import tempfile

from PIL import Image

import cover_policy as C

APPLY = "--apply" in sys.argv


def shape(p):
    w, h = Image.open(p).size
    if abs(w * 4 - h * 3) <= 12:
        return "34", (w, h)
    if abs(w - h) <= max(w, h) * 0.05:
        return "sq", (w, h)
    if w >= h * 1.15:
        # ★ 2026-09-18 店主裁定：横版主视觉不做留边（补边后主体过小），保持原图
        return "land", (w, h)
    return "vh", (w, h)


def main():
    man = C.load_manifest()
    srcs = C.load_sources()
    groups = {}
    for k, v in man.items():
        groups.setdefault(v, []).append(k)

    todo, skip34, skipland, fail = [], [], [], []
    for rel, keys in groups.items():
        p = os.path.join(C.BASE, rel)
        if not os.path.exists(p):
            fail.append((rel, "文件缺失"))
            continue
        try:
            kind, sz = shape(p)
        except Exception as e:
            fail.append((rel, "读图失败 %s" % e))
            continue
        if kind == "34":
            skip34.append((rel, keys, sz))
            continue
        if kind == "land":
            # 横版主视觉: 补边会把主体压得极小, 保持原图不动
            skipland.append((rel, keys, sz))
            continue
        todo.append((rel, keys, kind, sz))

    print("唯一图 %d | 需转换 %d 张(涉及 %d 个商品键) | 已是3:4跳过 %d 张 | 横版保持原图 %d 张 | 异常 %d"
          % (len(groups), len(todo), sum(len(k) for _, k, _, _ in todo),
             len(skip34), len(skipland), len(fail)))
    for rel, keys, sz in skipland[:10]:
        print("   横版保持原图: %s %s -> %d 个键" % (rel, sz, len(keys)))
    for rel, keys, kind, sz in todo[:8]:
        print("   例: %s %s %s -> %d 个键" % (rel, sz, kind, len(keys)))
    for rel, why in fail[:10]:
        print("   FAIL", rel, why)
    if not APPLY:
        print("\n[dry-run] 加 --apply 才会写入。")
        return

    done = 0
    for rel, keys, kind, sz in todo:
        src_p = os.path.join(C.BASE, rel)
        tmp = os.path.join(tempfile.gettempdir(), "padall_%s.jpg" % hashlib.md5(rel.encode()).hexdigest()[:10])
        try:
            if not C.make_pad_auto(src_p, tmp):
                fail.append((rel, "补边失败"))
                continue
        except Exception as e:
            fail.append((rel, "补边异常 %s" % e))
            continue
        role_code = C.ROLE_PAD if kind == "sq" else C.ROLE_PAD_P
        note = "全库批量改留边版(%s, 3:4 零裁切), 源 %s" % (
            "方图上下补边" if kind == "sq" else "整图保留+补边", os.path.basename(rel))
        for name in keys:
            fn = "rc%s.jpg" % hashlib.md5((name + "|pad34").encode("utf-8")).hexdigest()[:12]
            newrel = "covers/" + fn
            dst = os.path.join(C.BASE, newrel)
            shutil.copyfile(tmp, dst)
            ok, msg = C.set_cover(name, newrel, "manual", role=role_code,
                                  store=srcs.get(name, {}).get("store", ""),
                                  note=note)
            if not ok:
                fail.append((name, "set_cover 拒绝: %s" % msg))
                continue
            done += 1
        os.remove(tmp)
        m = C.load_manifest()
        C.remove_old(m, rel)

    print("已转换键 %d | 失败 %d" % (done, len(fail)))
    for x, y in fail[:20]:
        print("   FAIL", x, y)
    m = C.load_manifest()
    bad = [(k, v) for k, v in m.items() if not os.path.exists(os.path.join(C.BASE, v))]
    print("收尾校验: manifest %d 条, 缺失 %d" % (len(m), len(bad)))


if __name__ == "__main__":
    main()
