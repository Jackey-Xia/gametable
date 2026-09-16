#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gen_zh_report.py —— 把 identify_zh.py 的核查结果渲染成可视化 HTML 清单(自包含, 图片内联)
产出: <工作区>/港服中文封面核查.html  +  covers/zh_identify_report.json(原始数据)
"""
import base64
import io
import json
import os
import re
import sys

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import identify_zh as I

BASE = I.BASE
OUT = "/Users/jackey/WorkBuddy/2026-09-08-16-48-51/gametable/港服中文封面核查.html"

GROUPS = [
    ("NEED_ZH_IS_EN", "★ 建议更换：港服中文页有中文封面，当前用的是英文版图", "need"),
    ("NEED_ZH_OTHER", "★ 建议核对：港服有中文封面，当前是其它/旧版图", "need"),
    ("OTHER_IMG", "当前图与港服官方图不同（可能是旧版或非官方图）", "other"),
    ("LOWCONF_NEED_ZH_IS_EN", "待核对：疑似英文版封面（本地名称与港服条目匹配存疑）", "low"),
    ("LOWCONF_NEED_ZH_OTHER", "待核对：疑似有中文封面（匹配存疑）", "low"),
    ("LOWCONF_OTHER_IMG", "待核对：疑似与官方图不同（匹配存疑）", "low"),
    ("LOWCONF_OK_ZH", "待核对：疑似已是中文封面（匹配存疑）", "low"),
    ("VERT_NO_ZH", "竖版图无中文版式（港服该商品竖版中英同图）", "info"),
    ("NO_ZH_COVER", "港服中英封面本就同一张，无中文版可换", "info"),
    ("NO_MATCH", "港服未匹配到条目（需人工确认，多为店家用名与官方名差异大）", "info"),
    ("ERR", "出错 / 官方无对应形态图", "info"),
    ("OK_ZH", "已是港服中文页的图（无需处理）", "ok"),
]

# 这些分组只列名字清单(不渲染图片), 控制报告体积
COMPACT = {"OK_ZH", "LOWCONF_OK_ZH", "NO_MATCH", "ERR", "NO_ZH_COVER"}


def thumb(path_or_url, tag, h=150):
    try:
        if path_or_url.startswith("http"):
            p = I.download(path_or_url, tag)
        else:
            p = path_or_url
        if not p or not os.path.exists(p):
            return ""
        im = Image.open(p).convert("RGB")
        w = max(1, int(h * im.size[0] / im.size[1]))
        im = im.resize((w, h), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=62)
        return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return ""


def esc(s):
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


COMPACT_TPL = (
    '<section class="card %s" id="g-%s">'
    '<h2>%s <span class="cnt">%d</span></h2>'
    '<div class="clist">%s</div></section>'
)


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else os.path.join(BASE, "covers", "zh_identify_report.json")
    global OUT
    if len(sys.argv) > 2:
        OUT = sys.argv[2]
    d = json.load(open(src, encoding="utf-8"))
    items = d["items"]
    by = {}
    for r in items:
        by.setdefault(r["status"], []).append(r)

    total = len(items)
    cards = []
    for key, title, kind in GROUPS:
        rows = by.get(key) or []
        if not rows:
            continue
        if key in COMPACT:
            names = "、".join(esc(r["name"]) for r in sorted(rows, key=lambda x: x["name"]))
            cards.append(COMPACT_TPL % (kind, key, esc(title), len(rows), names))
            continue
        body = []
        for r in sorted(rows, key=lambda x: x["name"]):
            shape = "竖版" if r.get("shLocal") == "P" else "方图"
            zurl = r["zhP"] if r.get("shLocal") == "P" else r["zhM"]
            eurl = r["enP"] if r.get("shLocal") == "P" else r["enM"]
            cur = thumb(os.path.join(BASE, r["old"]), "loc" + r["shLocal"])
            zh = thumb(zurl, "zh" + r["shLocal"]) if zurl else ""
            en = thumb(eurl, "en" + r["shLocal"]) if eurl else ""
            d_zh = r.get("dLocalZh", 99)
            tag = ('<span class="pill %s">%s</span>' % (kind, title.split("：")[0]))
            store = esc(r.get("storeName") or "")
            note = esc(r.get("note") or "")
            body.append("""
      <div class="row {kind}">
        <div class="info">
          <div class="nm">{name}</div>
          <div class="meta">{shape}封面 · 与中文版差异 {dzh} · 匹配港服条目：<b>{store}</b></div>
          <div class="note">{note}</div>
        </div>
        <div class="imgs">
          <figure><img src="{cur}"><figcaption>当前</figcaption></figure>
          <figure class="hl"><img src="{zh}"><figcaption>港服中文版</figcaption></figure>
          <figure><img src="{en}"><figcaption>港服英文版</figcaption></figure>
        </div>
      </div>""".format(kind=kind, name=esc(r["name"]), shape=shape, dzh=d_zh, store=store,
                       note=note, cur=cur, zh=zh, en=en))
        cards.append("""  <section class="card {kind}" id="g-{key}">
    <h2>{title} <span class="cnt">{n}</span></h2>
    {body}
  </section>""".format(kind=kind, title=esc(title), n=len(rows), key=key, body="".join(body)))

    stat = []
    for key, title, kind in GROUPS:
        n = len(by.get(key) or [])
        stat.append('<a class="s {kind}" href="#g-%s"><b>%d</b><span>%s</span></a>' % (key, n, esc(title.split("：")[0].replace("★ ", ""))))

    html = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>港服中文封面核查 · 夏天Jackey 游戏租赁</title>
<style>
:root{--bg:#f6f7f9;--card:#fff;--line:#e5e7eb;--txt:#1f2430;--dim:#6b7280;
--need:#d92d20;--low:#b7791f;--other:#b54708;--info:#475467;--ok:#067647}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--txt);font:14px/1.6 -apple-system,"PingFang SC","Microsoft YaHei",sans-serif}
header{position:sticky;top:0;z-index:9;background:#fff;border-bottom:1px solid var(--line);padding:18px 24px}
h1{margin:0 0 4px;font-size:19px}
.sub{color:var(--dim);font-size:12.5px}
.stats{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px}
.s{display:flex;align-items:center;gap:6px;padding:6px 10px;border:1px solid var(--line);border-radius:8px;
   text-decoration:none;color:var(--txt);background:#fbfbfc;font-size:12.5px}
.s b{font-size:15px}
.s.need b{color:var(--need)} .s.low b{color:var(--low)} .s.other b{color:var(--other)}
.s.info b{color:var(--info)} .s.ok b{color:var(--ok)}
main{padding:18px 24px 80px;max-width:1240px;margin:0 auto}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;margin-bottom:18px;overflow:hidden}
.card h2{font-size:15px;margin:0;padding:14px 18px;border-bottom:1px solid var(--line);display:flex;gap:10px;align-items:center}
.card.need h2{background:#fef3f2;color:#912018}
.card.low h2{background:#fffaeb;color:#93370d}
.card.other h2{background:#fffaeb;color:#93370d}
.card.ok h2{background:#f6fef9;color:#05603a}
.card.info h2{background:#f8f9fc;color:#344054}
.cnt{margin-left:auto;font-weight:600;color:var(--dim);font-size:12.5px}
.row{display:grid;grid-template-columns:minmax(260px,1fr) auto;gap:16px;padding:14px 18px;border-bottom:1px solid #f1f2f4;align-items:center}
.row:last-child{border-bottom:0}
.nm{font-weight:600;font-size:14.5px}
.meta{color:var(--dim);font-size:12.5px;margin-top:2px}
.note{color:var(--other);font-size:12.5px;margin-top:2px}
.imgs{display:flex;gap:10px}
figure{margin:0;text-align:center}
figure img{width:auto;height:190px;border:1px solid var(--line);border-radius:8px;background:#fff;display:block}
figure.hl img{border:2px solid #12b76a;box-shadow:0 0 0 3px #d1fadf}
figcaption{font-size:11.5px;color:var(--dim);margin-top:4px}
.clist{padding:12px 18px;color:#374151;font-size:12.5px;line-height:1.9}
@media(max-width:760px){.row{grid-template-columns:1fr}.imgs{flex-wrap:wrap}figure img{height:140px}}
</style></head><body>
<header>
  <h1>港服中文封面核查 · 「夏天Jackey」游戏租赁</h1>
  <div class="sub">核查时间 __TIME__ · 已上架且有封面的商品 __TOTAL__ 款 · 仅识别未改动任何图片</div>
  <div class="stats">__STAT__</div>
</header>
<main>
__CARDS__
</main></body></html>"""
    html = (html.replace("__TIME__", esc(d.get("time", "")))
                .replace("__TOTAL__", str(total))
                .replace("__STAT__", "".join(stat))
                .replace("__CARDS__", "".join(cards)))

    open(OUT, "w", encoding="utf-8").write(html)
    print("生成:", OUT, "%.1f MB" % (os.path.getsize(OUT) / 1048576))
    for key, title, kind in GROUPS:
        print("  %-26s %4d" % (key, len(by.get(key) or [])))


if __name__ == "__main__":
    main()
