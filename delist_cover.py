#!/usr/bin/env python3
"""下架商品封面清理工具（可复用）

用法:
    python3 delist_cover.py "商品名"            # dry-run，只看会被清理什么
    python3 delist_cover.py "商品名" --apply    # 真正删除登记 + 图片文件

作用:
  商品从 WPS 价目表下架后，covers/manifest.json 与 cover_sources.json 里会残留
  孤儿键（名字在表格里已查不到，封面图也永远用不上）。本脚本把该键从两个索引里
  摘掉，并在确认没有其它键共用同一张图后删除 covers/*.jpg。

安全:
  - 商品名仍在 data/ps_grid.json 里 -> 拒绝执行（不是下架，别误删）
  - 图片被别的商品共用 -> 只摘键，保留图片
"""
import json
import os
import sys

import cover_policy as C

GRID = os.path.join(C.BASE, "data", "ps_grid.json")


def grid_names():
    """表格里出现过的所有商品名（含英文名），用于判断商品是否真的已下架"""
    try:
        g = json.load(open(GRID, encoding="utf-8"))
        rows = g["rows"] if isinstance(g, dict) else g
    except Exception as e:
        print("读取 ps_grid.json 失败:", e)
        return set()
    names = set()
    for r in rows[2:]:
        for cell in r[:4]:
            if isinstance(cell, str) and cell.strip():
                names.add(cell.strip())
    return names


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    apply_ = "--apply" in sys.argv
    force = "--force" in sys.argv        # 店主明确要求连同锁死图一起清掉才用
    if not args:
        print(__doc__)
        return
    name = args[0]

    names = grid_names()
    if name in names:
        print("拒绝执行：'%s' 仍在价目表中，不是下架商品。" % name)
        return

    m = C.load_manifest()
    s = C.load_sources()
    rel = m.get(name)
    if not rel:
        print("manifest 中没有 '%s'，无需清理。" % name)
        return

    others = [k for k, v in m.items() if v == rel and k != name]
    fp = os.path.join(C.BASE, rel)
    is_lock = C.is_locked_file(rel)
    print("商品名  :", name)
    print("封面文件:", rel, "| 磁盘存在:", os.path.exists(fp))
    print("共用同图的其它商品:", others or "无")
    print("永久锁死登记:", "★是(人工确认过的封面)" if is_lock else "否")
    if is_lock and not force:
        print("\n拒绝执行：该图在 covers/pinned.json 里已永久锁死（店主铁律："
              "人工确认过的图片即使改名也不删）。\n"
              "若确属彻底下架且不再需要，请显式加 --force。")

    if not apply_:
        print("\n[dry-run] 加 --apply 才会真正删除。")
        return
    if is_lock and not force:
        return

    # 先摘键，再判断图片是否还被引用
    m.pop(name, None)
    s.pop(name, None)
    C.save_manifest(m)
    C.save_sources(s)
    print("已从 manifest / cover_sources 摘除该键")

    keep = {os.path.normpath(v) for v in m.values() if v}
    if os.path.normpath(rel) in keep:
        print("图片仍被其它商品引用，保留:", rel)
    elif is_lock and not force:
        print("图片已永久锁死，保留:", rel)
    elif os.path.exists(fp):
        os.remove(fp)
        print("已删除图片:", rel)
        if force:
            C.unpin(name)
            print("已解除该商品的锁死登记")
    elif force:
        C.unpin(name)
    print("完成。")


if __name__ == "__main__":
    main()
