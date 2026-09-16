#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""missing_confirm.py —— 生成「无封面商品补图确认页」（自包含 HTML，图片 base64 内联）
=============================================================================
每张卡: 商品名 / 英文名 / 港服命中商品 / 形态(竖版|方图) / 新封面图
标注:
  - 高置信 / 待确认(低置信)
  - 港服中英同图（该游戏无专属中文 Logo 封面，标题仍为英文）
"""
import base64
import io
import json
import os

from PIL import Image

BASE = os.path.dirname(os.path.abspath(__file__))
OUT_PARENT = os.path.dirname(BASE)
W = 210


def thumb(path, quality=76):
    if not path or not os.path.exists(path):
        return ""
    try:
        im = Image.open(path).convert("RGB")
        h = max(1, int(im.height * W / im.width))
        im = im.resize((W, h), Image.LANCZOS)
        b = io.BytesIO()
        im.save(b, "JPEG", quality=quality, optimize=True, progressive=True)
        return "data:image/jpeg;base64," + base64.b64encode(b.getvalue()).decode()
    except Exception as ex:
        print("  thumb fail", path, str(ex)[:60])
        return ""


CSS = """<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>无封面商品补图确认 · 25 款</title><style>
*{box-sizing:border-box}body{background:#12141a;color:#e8eaed;font-family:-apple-system,"PingFang SC",sans-serif;margin:0;padding:24px}
h1{font-size:20px;margin:0 0 6px}.sub{color:#9aa0a6;font-size:13px;margin-bottom:10px;line-height:1.8}
.warn{background:#2b1d10;border:1px solid #7a4a12;color:#f0b357;padding:10px 12px;border-radius:8px;font-size:12.5px;margin:12px 0 20px;line-height:1.75}
.legend{background:#151c26;border:1px solid #24303f;color:#a8c0d8;padding:9px 12px;border-radius:8px;font-size:12.5px;margin:0 0 18px;line-height:1.8}
h2{font-size:15px;margin:24px 0 10px;padding-left:9px;border-left:3px solid #34a853}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(212px,1fr));gap:13px}
.card{background:#171a21;border:1px solid #262b34;border-radius:10px;padding:10px}
.card img{width:100%;border-radius:6px;display:block;background:#1e2128;outline:2px solid #34a853}
.nm{font-size:13.5px;font-weight:600;line-height:1.4;margin-bottom:3px}
.en{color:#7d8590;font-size:11px;word-break:break-all;margin-bottom:5px}
.st{color:#8ab4f8;font-size:11px;line-height:1.55;margin-bottom:7px}
.mt{font-size:11px;color:#6e7681;margin-top:6px}
.tag{display:inline-block;font-size:10.5px;padding:1px 6px;border-radius:4px;margin:0 4px 5px 0;background:#23303c;color:#79b8f3}
.tag.g{background:#1f3d2a;color:#8fd6a8}.tag.y{background:#3a2a12;color:#f0b357}.tag.p{background:#2a1e33;color:#c48ff0}
</style>"""


def main():
    rep = json.load(open(os.path.join(BASE, "covers", "missing_report.json"), encoding="utf-8"))
    by = {r["name"]: r for r in rep["items"]}
    ap = json.load(open(os.path.join(BASE, "covers", "missing_apply_report.json"), encoding="utf-8"))
    try:
        chk = {x["name"]: x for x in json.load(open(os.path.join(BASE, "covers", "missing_zhcheck.json"), encoding="utf-8"))}
    except Exception:
        chk = {}

    P = [d for d in ap["added"] if d["role"] == "P"]
    M = [d for d in ap["added"] if d["role"] == "M"]
    same = sorted(x["name"] for x in chk.values() if x["zhEnDist"] == 0)

    h = [CSS]
    h.append('<h1>无封面商品补图确认 · 25 款</h1>')
    h.append('<div class="sub">店主圈定：竖版 13 款（#15/48/50/51/52/54/55/71/73/76/83/88/108） · 方图 12 款（#5/12/13/28/35/41/46/64/65/81/95/101）<br>'
             '图片全部来自 PS 港服中文页（zh-Hans-HK）官方媒体库，按指定形态取图：竖版 = PORTRAIT_BANNER 2:3，方图 = MASTER 1:1</div>')
    if same:
        h.append('<div class="warn"><b>注意 %d 款「港服中英同图」</b>：%s —— 这些游戏港服中文页与英文页返回同一张图，'
                 '没有专属中文 Logo 封面，装上去标题仍是英文。属港服官方图，但语言不变。</div>' % (len(same), "、".join(same)))
    h.append('<div class="legend"><b>状态说明</b>　'
             '<span class="tag g">高置信</span>名字唯一精确匹配　'
             '<span class="tag y">待确认</span>分数 0.75~0.80 或并列，已按店主圈定装图，请核对下方「港服命中商品」　'
             '<span class="tag p">港服中英同图</span>港服无专属中文封面</div>')

    for title, lst in (("竖版 2:3（%d 款）" % len(P), P), ("方图 1:1（%d 款）" % len(M), M)):
        h.append('<h2>%s</h2><div class="grid">' % title)
        for d in lst:
            r = by[d["name"]]
            c = chk.get(d["name"], {})
            tg = []
            tg.append('<span class="tag">%s</span>' % ("竖版 2:3" if d["role"] == "P" else "方图 1:1"))
            if r["low"]:
                tg.append('<span class="tag y">待确认 %.2f/%.2f</span>' % (r["score"], r["second"]))
            else:
                tg.append('<span class="tag g">高置信</span>')
            if c.get("zhEnDist") == 0:
                tg.append('<span class="tag p">港服中英同图</span>')
            h.append('<div class="card"><div class="nm">%s</div><div class="en">%s</div>'
                     '<div class="st">港服命中：%s</div>%s<img src="%s">'
                     '<div class="mt">%d KB · 文件 %s</div></div>'
                     % (d["name"], (r.get("en") or "—"), (d["store"] or "")[:48],
                        "".join(tg), thumb(os.path.join(BASE, d["to"])),
                        d["size"] // 1024, os.path.basename(d["to"])))
        h.append("</div>")

    out = os.path.join(OUT_PARENT, "无封面商品补图确认-25款.html")
    open(out, "w", encoding="utf-8").write("".join(h))
    print(out, os.path.getsize(out) // 1024, "KB")


if __name__ == "__main__":
    main()
