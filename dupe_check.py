#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""dupe_check.py —— 同名多条目海报不一致排查
=============================================
1) 本地分组扫描: 按「去平台标注名」分组, 同组>1 条的用 dhash 比内容, 输出不一致组
2) 对不一致组查港服中文页是否有官方图(M/P), 供统一决策
3) 生成对比页 gametable/同款多条目海报不一致.html
"""
import base64
import io
import json
import os
import re
import sys
from collections import defaultdict

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import identify_zh as I  # noqa: E402

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(BASE), "同款多条目海报不一致.html")
W = 190


def base_name(n):
    s = re.sub(r"[（(](PS[45]|PS5|PS4|PSVR2?|中文版|中英文版|英文版)[)）]", "", n)
    return re.sub(r"\s+", "", s).strip()


def b64(p):
    im = Image.open(p).convert("RGB")
    h = max(1, int(im.height * W / im.width))
    im = im.resize((W, h), Image.LANCZOS)
    b = io.BytesIO()
    im.save(b, "JPEG", quality=78, optimize=True, progressive=True)
    return "data:image/jpeg;base64," + base64.b64encode(b.getvalue()).decode()


def main():
    m = json.load(open(os.path.join(BASE, "covers", "manifest.json"), encoding="utf-8"))
    g = defaultdict(list)
    for k, v in m.items():
        if v:
            g[base_name(k)].append(k)
    groups = []
    for b, keys in g.items():
        if len(keys) < 2:
            continue
        hs = {k: I.dhash(os.path.join(BASE, m[k])) for k in keys}
        ref = hs[keys[0]]
        if any(I.dist(ref, hs[k]) > 2 for k in keys[1:]):
            groups.append((b, keys))
    print("同名多条目 %d 组, 封面内容不同 %d 组" % (sum(1 for b, l in g.items() if len(l) > 1), len(groups)))

    # 查港服官方图
    for b, keys in groups:
        print("==", b)
        try:
            rs = I._zh_media_once(b)
        except Exception as e:
            print("   search err", str(e)[:60])
            rs = []
        for r in rs[:2]:
            md = {x.get("role"): x.get("url") for x in (r.get("media") or [])
                  if x.get("role") in ("MASTER", "PORTRAIT_BANNER")}
            print("   港服:", (r.get("name") or "")[:34], "M" if md.get("MASTER") else "-", "P" if md.get("PORTRAIT_BANNER") else "-")
            r["_md"] = md
        for k in keys:
            im = Image.open(os.path.join(BASE, m[k]))
            print("   %-28s %s %dx%d %.0fKB" % (k, m[k], im.width, im.height, os.path.getsize(os.path.join(BASE, m[k])) / 1024))

    CSS = """<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>同款多条目 · 海报不一致排查</title><style>
*{box-sizing:border-box}body{background:#12141a;color:#e8eaed;font-family:-apple-system,"PingFang SC",sans-serif;margin:0;padding:24px}
h1{font-size:20px;margin:0 0 6px}.sub{color:#9aa0a6;font-size:13px;line-height:1.8;margin-bottom:16px}
h2{font-size:15px;margin:26px 0 10px;padding-left:9px;border-left:3px solid #34a853}
.row{display:flex;gap:14px;flex-wrap:wrap}
.col{background:#171a21;border:1px solid #262b34;border-radius:10px;padding:11px;width:212px}
.col img{width:100%;border-radius:6px;display:block;background:#1e2128}
.nm{font-size:13.5px;font-weight:700;margin-bottom:5px}
.f{font-size:11px;color:#6e7681;margin-top:6px;word-break:break-all;line-height:1.5}
.bad img{outline:2px solid #d9534f}.good img{outline:2px solid #34a853}
.tip{background:#151c26;border:1px solid #24303f;color:#a8c0d8;padding:9px 12px;border-radius:8px;font-size:12.5px;line-height:1.75;margin:0 0 8px}
</style>"""
    h = [CSS, "<h1>同款多条目 · 海报不一致排查</h1>",
         '<div class="sub">你的表里同一款游戏按平台分列两个条目（PS4/PS5）。全库扫描 8 组同名条目，发现 <b>3 组</b>两件海报不一致，列表如下（每条都配了港服中文页可取的官方图情况）。<br>'
         '要不要统一、统一成哪种，你说了算 —— 说个组名我就照着改。</div>']
    tips = {
        "女神异闻录5：皇家版/P5R": "PS4 那件是 256×384 的第三方低清图（英文 PERSONA5 ROYAL），PS5 是官方高清。建议把 PS4 升级成同一张官方图。",
        "暗夜长梦": "两件是同一张美术，但一件竖版 2:3、一件方图 1:1，列表里并排会一高一矮。建议统一成同一种形态。",
        "虚构世界2：信条谷": "同上：一件竖版、一件方图，形态不一致。建议统一。",
    }
    for b, keys in groups:
        h.append("<h2>%s</h2>" % b)
        if tips.get(b):
            h.append('<div class="tip">%s</div>' % tips[b])
        h.append('<div class="row">')
        for k in keys:
            p = os.path.join(BASE, m[k])
            im = Image.open(p)
            h.append('<div class="col bad"><div class="nm">%s</div><img src="%s"><div class="f">%s<br>%d×%d · %.0f KB</div></div>'
                     % (k, b64(p), m[k], im.width, im.height, os.path.getsize(p) / 1024))
        h.append("</div>")
    open(OUT, "w", encoding="utf-8").write("".join(h))
    print(OUT, os.path.getsize(OUT) // 1024, "KB")


if __name__ == "__main__":
    main()
