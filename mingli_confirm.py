#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mingli_confirm.py —— 生成「名利游戏 PS4/PS5 海报统一」确认页"""
import base64
import io
import json
import os
import subprocess

from PIL import Image

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(BASE), "名利游戏-海报统一确认.html")
W = 240


def b64(path):
    if not path or not os.path.exists(path):
        return ""
    im = Image.open(path).convert("RGB")
    h = max(1, int(im.height * W / im.width))
    im = im.resize((W, h), Image.LANCZOS)
    b = io.BytesIO()
    im.save(b, "JPEG", quality=80, optimize=True, progressive=True)
    return "data:image/jpeg;base64," + base64.b64encode(b.getvalue()).decode()


def git_show(rel):
    dst = "/tmp/ml_old_" + os.path.basename(rel)
    if not os.path.exists(dst):
        try:
            open(dst, "wb").write(subprocess.check_output(["git", "show", "HEAD:" + rel], cwd=BASE))
        except Exception:
            return None
    return dst


m = json.load(open(os.path.join(BASE, "covers", "manifest.json"), encoding="utf-8"))
ps4 = os.path.join(BASE, m["名利游戏（PS4）"])
ps5 = os.path.join(BASE, m["名利游戏（PS5）"])
ps5_old = git_show("covers/70f11d4736e4_s.jpg")
zh = os.path.join(BASE, "cloudrepo", "mlcmp_zh") if os.path.exists(os.path.join(BASE, "cloudrepo", "mlcmp_zh")) else None

CSS = """<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>名利游戏 · 两款海报统一确认</title><style>
*{box-sizing:border-box}body{background:#12141a;color:#e8eaed;font-family:-apple-system,"PingFang SC",sans-serif;margin:0;padding:24px}
h1{font-size:20px;margin:0 0 6px}.sub{color:#9aa0a6;font-size:13px;line-height:1.8;margin-bottom:16px}
.ok{background:#14241a;border:1px solid #2e7d51;color:#8fd6a8;padding:10px 12px;border-radius:8px;font-size:12.5px;margin:0 0 20px;line-height:1.75}
.row{display:flex;gap:16px;flex-wrap:wrap}
.col{background:#171a21;border:1px solid #262b34;border-radius:10px;padding:12px;width:262px}
.col img{width:100%;border-radius:6px;display:block;background:#1e2128}
.nm{font-size:14px;font-weight:700;margin-bottom:4px}
.cap{font-size:11.5px;color:#7d8590;margin:6px 0 4px}
.new img{outline:2px solid #34a853}.old{opacity:.9}.old img{outline:2px solid #d9534f}
.f{font-size:11px;color:#6e7681;margin-top:6px;word-break:break-all}
h2{font-size:15px;margin:26px 0 10px;padding-left:9px;border-left:3px solid #34a853}
</style>"""

h = [CSS, "<h1>名利游戏 · 两款海报统一确认</h1>",
     '<div class="sub">你的表里「名利游戏（PS4）」和「名利游戏（PS5）」是两个条目，之前海报一个是中文版、一个是英文版（Vanity Fair: The Pursuit）。<br>'
     '港服中文页对该游戏的 PS4 条目（CUSA51488）与 PS5 条目（PPSA26324）返回的是<b>同一张</b>中文竖版图，现已统一。</div>',
     '<div class="ok">✔ 已统一：两款现在都是港服中文页竖版官方图（标题「名利游戏」），形态 2:3，港服该商品中英页确有区分（英文页图为 Vanity Fair: The Pursuit 版）。</div>',
     '<h2>名利游戏（PS5）· 变更前后</h2><div class="row">']
h.append('<div class="col old"><div class="nm">名利游戏（PS5）</div><div class="cap">变更前 · 英文版</div><img src="%s"><div class="f">covers/70f11d4736e4_s.jpg（已删除）</div></div>' % b64(ps5_old))
h.append('<div class="col new"><div class="nm">名利游戏（PS5）</div><div class="cap">变更后 · 港服中文版</div><img src="%s"><div class="f">%s</div></div>' % (b64(ps5), m["名利游戏（PS5）"]))
h.append("</div>")
h.append('<h2>两款现状（应完全一致）</h2><div class="row">')
for nm in ("名利游戏（PS4）", "名利游戏（PS5）"):
    h.append('<div class="col new"><div class="nm">%s</div><div class="cap">当前 · 港服中文版</div><img src="%s"><div class="f">%s</div></div>'
             % (nm, b64(os.path.join(BASE, m[nm])), m[nm]))
h.append("</div>")

open(OUT, "w", encoding="utf-8").write("".join(h))
print(OUT, os.path.getsize(OUT) // 1024, "KB")
