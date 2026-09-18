#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pad_preview_html.py —— 任务1：生成「现留边版 vs 不留边·满填充竖图版」对比预览站点。

输出 REPO/pad_review/：
  index.html  单页对比（左=现留边版, 右=不留边 3:4 满填充裁切），含搜索/筛选
  img/NNNN_l.jpg / NNNN_r.jpg
  清单.txt    编号对照表（供店主报编号）
"""
import json, os, shutil, html
from PIL import Image, ImageChops
import numpy as np

REPO = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(REPO, "pad_review")
IMG = os.path.join(OUT, "img")
PAD = "/tmp/padvs"
TW, TH = 144, 192          # 前端 96×128 的 1.5 倍

shutil.rmtree(IMG, ignore_errors=True)
os.makedirs(IMG, exist_ok=True)

state = json.load(open(os.path.join(PAD, "state.json"), encoding="utf-8"))
rescan = {}
p = os.path.join(PAD, "rescan.json")
if os.path.exists(p):
    rescan = json.load(open(p, encoding="utf-8"))


def sim(path):
    """按前端 96×128 口径(object-fit:cover)取景后放大, 得到预览缩略图"""
    im = Image.open(path).convert("RGB")
    w, h = im.size
    s = max(TW / w, TH / h)
    nw, nh = max(TW, int(round(w * s))), max(TH, int(round(h * s)))
    im = im.resize((nw, nh), Image.LANCZOS)
    x, y = (nw - TW) // 2, (nh - TH) // 2
    return im.crop((x, y, x + TW, y + TH))


def mae(a, b):
    d = np.asarray(a, dtype=np.float32) - np.asarray(b, dtype=np.float32)
    return float(np.abs(d).mean())


rows = []
for k in sorted(state, key=lambda x: int(x)):
    v = state[k]
    i = v["i"]
    lp = os.path.join(REPO, v["rel"])
    rp = os.path.join(PAD, "right", "%04d.jpg" % i)
    if not (os.path.exists(lp) and os.path.exists(rp)):
        continue
    L, R = sim(lp), sim(rp)
    L.save(os.path.join(IMG, "%04d_l.jpg" % i), "JPEG", quality=82)
    R.save(os.path.join(IMG, "%04d_r.jpg" % i), "JPEG", quality=82)
    diff = mae(L, R)
    frm = v.get("from")
    tag = {"git": "原图精确", "rescan": "原图重搜", "canvas": "画布近似", "cache": "原图精确"}.get(frm, frm)
    rows.append({"i": i, "rep": v["rep"], "keys": v["keys"], "diff": round(diff, 1),
                 "tag": tag, "info": v.get("info", ""), "rel": v["rel"]})

# 差异极小的排最后（原图本来就 3:4，换不换没区别）
rows.sort(key=lambda r: (r["diff"] < 3.0, r["rep"]))
order = {r["i"]: n + 1 for n, r in enumerate(rows)}

with open(os.path.join(OUT, "清单.txt"), "w", encoding="utf-8") as f:
    f.write("留边版 vs 不留边满填充版 · 编号清单（共 %d 项）\n" % len(rows))
    f.write("=" * 60 + "\n")
    for r in rows:
        f.write("#%-4d %-38s 差异%5.1f  %s  %s\n" % (
            order[r["i"]], r["rep"][:38], r["diff"], r["tag"], r["info"]))

cards = []
for r in rows:
    n = order[r["i"]]
    dim = "无差异" if r["diff"] < 3 else ("差异大" if r["diff"] > 25 else "有差异")
    cards.append("""<div class="card" data-name="%s" data-diff="%s">
  <div class="hd"><b>#%d</b> %s</div>
  <div class="row">
    <div class="col"><div class="cap">现用 · 留边版</div><img loading="lazy" src="img/%04d_l.jpg"></div>
    <div class="col"><div class="cap r">不留边 · 满填充</div><img loading="lazy" src="img/%04d_r.jpg"></div>
  </div>
  <div class="ft"><span class="tag t-%s">%s</span><span class="tag">%s</span><span class="tag">差异%.1f</span></div>
</div>""" % (html.escape(r["rep"]), dim, n, html.escape(r["rep"]),
             r["i"], r["i"],
             "ok" if dim != "无差异" else "gray", dim, r["tag"], r["diff"]))

HTML = """<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>留边版 vs 不留边满填充版 · 对比审核</title>
<style>
body{margin:0;background:#f5f6f7;font:14px/1.5 -apple-system,"PingFang SC","Microsoft YaHei",sans-serif;color:#1c1c1c}
header{position:sticky;top:0;z-index:9;background:#0f2b22;color:#eaf3ef;padding:10px 14px}
header h1{margin:0 0 6px;font-size:16px;font-weight:600}
header p{margin:0;font-size:12px;opacity:.85}
.tools{display:flex;gap:8px;flex-wrap:wrap;margin-top:8px}
input,select{padding:6px 10px;border-radius:6px;border:1px solid #3c5b50;background:#123a2e;color:#eaf3ef;font-size:13px}
input{min-width:180px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:10px;padding:12px}
.card{background:#fff;border:1px solid #e2e5e8;border-radius:10px;padding:8px}
.hd{font-size:13px;margin-bottom:6px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.hd b{color:#c0392b;margin-right:6px}
.row{display:flex;gap:8px}
.col{flex:1;text-align:center}
.col img{width:100%%;border-radius:6px;display:block;background:#eee}
.cap{font-size:11px;color:#666;margin-bottom:3px}
.cap.r{color:#c0392b;font-weight:600}
.ft{margin-top:6px;display:flex;gap:6px;flex-wrap:wrap}
.tag{font-size:11px;background:#eef1f3;color:#555;border-radius:4px;padding:2px 6px}
.tag.t-ok{background:#e6f4ea;color:#1e7e34}
.tag.t-gray{background:#f0f0f0;color:#999}
</style></head><body>
<header>
  <h1>留边版 vs 不留边满填充版 · 对比审核（共 %d 项）</h1>
  <p>左＝现在线上用的留边版（零裁切，整图保留 + 虚化补边）；右＝不留边、按前端 96×128 满填充裁切（主体更大，但会裁掉内容）。看中哪个把<b>编号</b>报给我即可。</p>
  <div class="tools">
    <input id="q" placeholder="搜商品名…">
    <select id="f"><option value="">全部</option><option value="有差异">有差异</option><option value="差异大">差异大</option><option value="无差异">无差异(换不换一样)</option></select>
  </div>
</header>
<div class="grid" id="g">
%s
</div>
<script>
var q=document.getElementById('q'),f=document.getElementById('f');
function run(){var s=q.value.trim().toLowerCase(),d=f.value;
 document.querySelectorAll('.card').forEach(function(c){
  var ok1=!s||c.dataset.name.toLowerCase().indexOf(s)>=0;
  var ok2=!d||c.dataset.diff===d;
  c.style.display=(ok1&&ok2)?'':'none';});}
q.oninput=run;f.onchange=run;
</script>
</body></html>""" % (len(rows), "\n".join(cards))

open(os.path.join(OUT, "index.html"), "w", encoding="utf-8").write(HTML)
print("生成 %d 张卡片 -> %s" % (len(rows), OUT))
print("图片 %d 张, HTML %.1f MB" % (len(os.listdir(IMG)),
                                    os.path.getsize(os.path.join(OUT, "index.html")) / 1e6))
