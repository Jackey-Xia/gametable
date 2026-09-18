#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""blank_preview.py —— 任务2：留白商品找图结果 → 三形态对比预览。

对每张找到的源图生成三种成品形态（全部按前端 96×128 口径渲染）：
  A 方图留边版     ：源图满填裁成正方形 → 上下虚化补边
  B 竖图留边版     ：整图完整保留 + 左右虚化补边（不遮挡文字/字母）
  C 竖图满填不留边 ：源图按 3:4 居中满填裁切（主体最大，会裁内容）

输出 REPO/blank_review/（index.html + img/ + 清单.txt）
"""
import json, os, sys, shutil, html
from PIL import Image, ImageFilter, ImageEnhance
import numpy as np

REPO = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(REPO, "blank_review")
IMG = os.path.join(OUT, "img")
TW, TH = 144, 192

shutil.rmtree(IMG, ignore_errors=True)
os.makedirs(IMG, exist_ok=True)

state = json.load(open("/tmp/blank_state.json", encoding="utf-8"))
SRC = "/tmp/blank_orig"


def crop_sq(im):
    w, h = im.size
    s = min(w, h)
    x, y = (w - s) // 2, (h - s) // 2
    return im.crop((x, y, x + s, y + s))


def crop34(im):
    w, h = im.size
    tw = min(w, int(round(h * 3 / 4)))
    th = min(h, int(round(w * 4 / 3)))
    x, y = (w - tw) // 2, (h - th) // 2
    return im.crop((x, y, x + tw, y + th))


def form_a(im):
    """方图留边版"""
    fg = crop_sq(im).resize((504, 504), Image.LANCZOS)
    bg = im.resize((504, 672), Image.LANCZOS).filter(ImageFilter.GaussianBlur(24))
    bg = ImageEnhance.Color(bg).enhance(0.6)
    bg.paste(fg, (0, (672 - 504) // 2))
    return bg


def form_b(im):
    """竖图留边版: 整图完整保留 + 左右补边"""
    w, h = im.size
    if abs(w * 4 - h * 3) <= 12:
        return im.resize((504, 672), Image.LANCZOS)
    bg = im.resize((504, 672), Image.LANCZOS).filter(ImageFilter.GaussianBlur(24))
    bg = ImageEnhance.Color(bg).enhance(0.6)
    scale = min(504.0 / w, 672.0 / h)
    fw, fh = max(1, int(round(w * scale))), max(1, int(round(h * scale)))
    fg = im.resize((fw, fh), Image.LANCZOS)
    bg.paste(fg, ((504 - fw) // 2, (672 - fh) // 2))
    return bg


def form_c(im):
    """竖图满填不留边"""
    return crop34(im).resize((504, 672), Image.LANCZOS)


def sim(path):
    im = Image.open(path).convert("RGB")
    w, h = im.size
    s = max(TW / w, TH / h)
    im = im.resize((max(TW, int(w * s)), max(TH, int(h * s))), Image.LANCZOS)
    return im.crop(((im.width - TW) // 2, (im.height - TH) // 2,
                    (im.width - TW) // 2 + TW, (im.height - TH) // 2 + TH))


def sim_of(obj):
    """PIL 对象 -> 前端 96×128 口径缩略"""
    w, h = obj.size
    s = max(TW / w, TH / h)
    o = obj.resize((max(TW, int(w * s)), max(TH, int(h * s))), Image.LANCZOS)
    return o.crop(((o.width - TW) // 2, (o.height - TH) // 2,
                   (o.width - TW) // 2 + TW, (o.height - TH) // 2 + TH))


def mae(a, b):
    d = np.asarray(a, np.float32) - np.asarray(b, np.float32)
    return float(np.abs(d).mean())


rows, nmiss = [], 0
for k in sorted(state):
    v = state[k]
    i = v["i"]
    src = os.path.join(SRC, "%04d.jpg" % i)
    if v.get("step") in (None, "未找到") or v.get("step", "").startswith("未找到") or not os.path.exists(src):
        nmiss += 1
        rows.append({"i": i, "rep": k, "miss": True, "step": v.get("step") or "未找到"})
        continue
    im = Image.open(src).convert("RGB")
    A, B, C = form_a(im), form_b(im), form_c(im)
    for tag, obj in (("a", A), ("b", B), ("c", C)):
        obj.save(os.path.join(IMG, "%04d_%s.jpg" % (i, tag)), "JPEG", quality=82)
    sa, sb, sc = sim_of(A), sim_of(B), sim_of(C)
    rows.append({"i": i, "rep": k, "miss": False, "step": v.get("step"),
                 "cand": v.get("cand", ""), "role": v.get("role", ""),
                 "size": v.get("size"), "score": v.get("score"),
                 "diff_ac": round(mae(sa, sc), 1), "diff_ab": round(mae(sa, sb), 1)})


cards = []
for r in rows:
    n = r["i"]
    if r.get("miss"):
        cards.append("""<div class="card miss"><div class="hd"><b>#%d</b> %s</div>
<div class="none">未找到图（%s）—— 待网上找图 / 人工补</div></div>"""
                     % (n, html.escape(r["rep"]), html.escape(r["step"])))
        continue
    cards.append("""<div class="card">
  <div class="hd"><b>#%d</b> %s</div>
  <div class="row">
    <div class="col"><div class="cap">A 方图留边</div><img loading="lazy" src="img/%04d_a.jpg"></div>
    <div class="col"><div class="cap r">B 竖图留边(零裁切)</div><img loading="lazy" src="img/%04d_b.jpg"></div>
    <div class="col"><div class="cap r2">C 满填不留边</div><img loading="lazy" src="img/%04d_c.jpg"></div>
  </div>
  <div class="ft"><span class="tag t1">%s</span><span class="tag">%.2f分</span><span class="tag cand">%s</span></div>
</div>""" % (n, html.escape(r["rep"]), n, n, n,
             html.escape(r["step"]), r.get("score") or 0, html.escape((r.get("cand") or "")[:44])))

HTML = """<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>留白商品找图 · 三形态对比审核</title>
<style>
body{margin:0;background:#f5f6f7;font:14px/1.5 -apple-system,"PingFang SC","Microsoft YaHei",sans-serif;color:#1c1c1c}
header{position:sticky;top:0;z-index:9;background:#33260e;color:#f7efe2;padding:10px 14px}
header h1{margin:0 0 6px;font-size:16px;font-weight:600}
header p{margin:0;font-size:12px;opacity:.85}
input{padding:6px 10px;border-radius:6px;border:1px solid #6b5a38;background:#463tú71;color:#f7efe2;font-size:13px;margin-top:8px}
input{background:#46371f}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(400px,1fr));gap:10px;padding:12px}
.card{background:#fff;border:1px solid #e2e5e8;border-radius:10px;padding:8px}
.card.miss{opacity:.75;background:#faf7f2}
.hd{font-size:13px;margin-bottom:6px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.hd b{color:#b05e10;margin-right:6px}
.row{display:flex;gap:8px}
.col{flex:1;text-align:center}
.col img{width:100%%;border-radius:6px;display:block;background:#eee}
.cap{font-size:11px;color:#666;margin-bottom:3px}
.cap.r{color:#1e7e34;font-weight:600}.cap.r2{color:#c0392b;font-weight:600}
.none{font-size:12px;color:#999;padding:8px 0}
.ft{margin-top:6px;display:flex;gap:6px;flex-wrap:wrap}
.tag{font-size:11px;background:#eef1f3;color:#555;border-radius:4px;padding:2px 6px}
.tag.t1{background:#fff3e0;color:#b05e10}
.tag.cand{max-width:100%%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
</style></head><body>
<header>
  <h1>留白商品找图 · 三形态对比审核</h1>
  <p>A 方图留边（先裁方再上下补边）｜B 竖图留边（整图保留+左右补边，零裁切）｜C 满填不留边（3:4 满填裁切，主体最大）。挑中哪种把「编号+字母」报给我，如「#3 用 C」。</p>
  <input id="q" placeholder="搜商品名…">
</header>
<div class="grid" id="g">
%s
</div>
<script>
var q=document.getElementById('q');
q.oninput=function(){var s=q.value.trim().toLowerCase();
 document.querySelectorAll('.card').forEach(function(c){
  c.style.display=(!s||c.textContent.toLowerCase().indexOf(s)>=0)?'':'none';});};
</script>
</body></html>""" % ("\n".join(cards))

open(os.path.join(OUT, "index.html"), "w", encoding="utf-8").write(HTML)
with open(os.path.join(OUT, "清单.txt"), "w", encoding="utf-8") as f:
    f.write("留白商品找图 · 三形态清单\n" + "=" * 60 + "\n")
    for r in rows:
        if r.get("miss"):
            f.write("#%-4d %-40s [未找到] %s\n" % (r["i"], r["rep"][:40], r["step"]))
        else:
            f.write("#%-4d %-40s %s %s 候选=%s\n" % (
                r["i"], r["rep"][:40], r["step"], r.get("role", ""), (r.get("cand") or "")[:40]))
print("命中 %d / 未找到 %d -> %s" % (len(rows) - nmiss, nmiss, OUT))
