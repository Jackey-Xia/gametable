#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fix_mingli.py —— 把「名利游戏（PS5）」也换成港服中文页竖版官方图，与「名利游戏（PS4）」统一
=================================================================================
背景: 同名两款(PS4/PS5 分列)当前海报不同 —— PS4 已是港服中文版(rc08cdb08fa1f6.jpg)，
      PS5 仍是英文版(Vanity Fair: The Pursuit)。港服中文页两个条目(PPSA26324/CUSA51488)
      返回同一张 PORTRAIT_BANNER 中文图，据此统一。
"""
import hashlib
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import identify_zh as I  # noqa: E402

BASE = os.path.dirname(os.path.abspath(__file__))
MANIFEST = os.path.join(BASE, "covers", "manifest.json")
TARGET = "名利游戏（PS5）"
URL = "https://image.api.playstation.com/vulcan/ap/rnd/202411/2810/53f3ed8ba940f448838cee52585d08ad064aecc131c591d3.png"


def main():
    m = json.load(open(MANIFEST, encoding="utf-8"))
    rel = "covers/rc%s.jpg" % hashlib.md5(TARGET.encode()).hexdigest()[:12]
    old = m.get(TARGET)
    p = I.download(URL, "ml_ps5")
    dst = os.path.join(BASE, rel)
    shutil.copy(p, dst)
    assert os.path.getsize(dst) > 3000, "文件过小"
    m[TARGET] = rel
    import autocover as A
    # 旧文件若不再被其它键引用则删除
    keep = {os.path.basename(x) for x in m.values()}
    removed = None
    if old and os.path.basename(old) not in keep and os.path.exists(os.path.join(BASE, old)):
        os.remove(os.path.join(BASE, old))
        removed = old
    json.dump(m, open(MANIFEST, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("%s\n  %s -> %s (%d B)\n  旧图删除: %s" % (TARGET, old, rel, os.path.getsize(dst), removed))

    # 顺便导出「中/英」两版港服图供对比展示
    for tag, loc in (("zh", "zh-hans-hk"), ("en", "en-hk")):
        pm = I.page_media("HP8406-PPSA26324_00-0440037362021369", loc)
        u = pm.get("PORTRAIT_BANNER")
        if u:
            I.download(u, "mlcmp_" + tag)
            print("  港服 %s 竖版图: %s" % (loc, u))


if __name__ == "__main__":
    main()
