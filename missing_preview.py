#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
missing_preview.py —— 把 missing_report.json 渲染成「无封面商品 · 港服候选图」挑选页
=============================================================================
- 每张卡展示港服命中商品名 + 方图(MASTER) + 竖版(PORTRAIT_BANNER)，图片本地压缩后 base64 内联
- 卡片可单选「用竖版 / 用方图 / 不要」，底部一键复制所选清单(name|role)，店主回传即可批量装图
"""
import base64
import io
import json
import os
import sys

import identify_zh as I
from PIL import Image

BASE = os.path.dirname(os.path.abspath(__file__))
REPORT = os.path.join(BASE, "covers", "missing_report.json")
OUT_PARENT = os.path.dirname(BASE)
W = 200


def thumb(url, tag):
    """下载 -> 缩到宽 W -> JPEG q74 -> base64"""
    if not url:
        return ""
    try:
        p = I.download(url, tag)
        im = Image.open(p).convert("RGB")
        h = max(1, int(im.height * W / im.width))
        im = im.resize((W, h), Image.LANCZOS)
        b = io.BytesIO()
        im.save(b, "JPEG", quality=74, optimize=True, progressive=True)
        return "data:image/jpeg;base64," + base64.b64encode(b.getvalue()).decode()
    except Exception as ex:
        print("   img fail", tag, str(ex)[:60])
        return ""


def main():
    rep = json.load(open(REPORT, encoding="utf-8"))
    items = rep["items"]
    rows = []
    for i, r in enumerate(items, 1):
        print("[%3d/%d] %s" % (i, len(items), r["name"][:36]))
        bM = thumb(r.get("zhM"), "mpM%d" % i)
        bP = thumb(r.get("zhP"), "mpP%d" % i)
        rows.append({**r, "bM": bM, "bP": bP})

    ok = len([r for r in rows if r["zhM"] and not r["low"]])
    low = len([r for r in rows if r["zhM"] and r["low"]])
    none = len([r for r in rows if not r["zhM"]])
    haveP = len([r for r in rows if r["zhP"]])

    # CSS 段含 width:100% 等百分号, 不能参与 % 格式化, 单独拼接
    CSS = """<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>无封面商品 · 港服中文页候选图</title><style>
*{box-sizing:border-box}body{background:#12141a;color:#e8eaed;font-family:-apple-system,"PingFang SC",sans-serif;margin:0;padding:20px}
h1{font-size:19px;margin:0 0 4px}.sub{color:#9aa0a6;font-size:12.5px;line-height:1.8;margin-bottom:14px}
.bar{position:sticky;top:0;background:#12141a;padding:10px 0;border-bottom:1px solid #2a2d35;z-index:9;display:flex;gap:8px;flex-wrap:wrap;align-items:center}
button,.tab{background:#1e2630;color:#cfe3f5;border:1px solid #2f3b48;border-radius:7px;padding:6px 11px;font-size:12.5px;cursor:pointer}
button:hover,.tab:hover{background:#27313d}.tab.on{background:#1f4d33;border-color:#2e7d51;color:#c9f2da}
.hint{color:#8b949e;font-size:12px;margin-left:auto}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(430px,1fr));gap:12px;margin-top:14px}
.card{background:#171a21;border:1px solid #262b34;border-radius:10px;padding:11px;display:flex;gap:11px}
.card.pick{outline:2px solid #34a853;background:#141c17}.card.no{border-color:#4a2a2a;opacity:.55}
.nm{font-size:13.5px;font-weight:600;line-height:1.4}.en{color:#7d8590;font-size:11px;margin-top:2px;word-break:break-all}
.st{color:#8ab4f8;font-size:11px;margin-top:4px;line-height:1.5}.meta{font-size:11px;color:#6e7681;margin-top:3px}
img{width:96px;border-radius:5px;display:block;background:#22262e;margin-bottom:6px}
.opt{position:relative;cursor:pointer}.opt input{position:absolute;opacity:0;width:0;height:0}
.opt span.lbl{display:block;font-size:10.5px;color:#7d8590;text-align:center}
.opt input:checked + div{outline:2px solid #34a853;border-radius:6px}
.opt.n input:checked + div{outline-color:#d9534f}
.tag{display:inline-block;font-size:10px;padding:1px 5px;border-radius:4px;margin-top:4px;background:#3a2a12;color:#f0b357}
.tag.g{background:#1f3d2a;color:#8fd6a8}.tag.r{background:#3d2126;color:#f0a0a8}
textarea{width:100%;height:90px;background:#0e1116;color:#c9d1d9;border:1px solid #2a2d35;border-radius:8px;font-size:12px;padding:8px;margin-top:10px}
</style>"""
    HDR = ('<h1>无封面商品 · 港服中文页候选图</h1>'
           '<div class="sub">共 %d 款目前没有封面。下面列出港服中文页搜到的官方图，'
           '<b>竖版</b>（2:3，卡片显示最完整，推荐）和<b>方图</b>（1:1）都在。<br>'
           '<b>高置信</b>的默认已替你选好（有竖版用竖版）；<b>待确认</b>的默认「不用」，'
           '看图确认没错再手动点一版。底部「生成所选清单」→ 复制发我即可批量装图。</div>'
           '<div class="bar"><span class="tab on" data-f="all">全部 %d</span><span class="tab" data-f="ok">高置信 %d</span>'
           '<span class="tab" data-f="low">待确认 %d</span><span class="tab" data-f="none">港服没找到 %d</span>'
           '<span class="hint">有竖版 %d / 只有方图 %d</span></div>'
           '<div class="grid" id="g">') % (len(rows), len(rows), ok, low, none, haveP,
                                          len([r for r in rows if r["zhM"]]) - haveP)
    h = [CSS + HDR]

    for i, r in enumerate(rows, 1):
        cls = "ok" if (r["zhM"] and not r["low"]) else ("low" if r["zhM"] else "none")
        if not r["zhM"]:
            h.append('<div class="card" data-f="none" data-n="%s"><div style="flex:1"><div class="nm">%d. %s</div>'
                     '<div class="en">%s</div><div class="meta" style="margin-top:10px;color:#f0a0a8">港服中文页未搜到对应商品</div></div></div>'
                     % (r["name"].replace('"', "&quot;"), i, r["name"], (r.get("en") or "")))
            continue
        # 默认策略: 高置信 -> 有竖版用竖版、否则方图; 低置信 -> 默认不用(需店主手动点头, 防错图)
        use_p = bool(r["bP"]) and not r["low"]
        use_m = (not r["bP"]) and not r["low"]
        opt = []
        if r["bP"]:
            opt.append('<label class="opt" onclick="event.stopPropagation()"><input type="radio" name="c%d" value="P"%s onchange="cnt()"><div><img src="%s"></div><span class="lbl">竖版 2:3</span></label>' % (i, " checked" if use_p else "", r["bP"]))
        if r["bM"]:
            opt.append('<label class="opt" onclick="event.stopPropagation()"><input type="radio" name="c%d" value="M"%s onchange="cnt()"><div><img src="%s"></div><span class="lbl">方图 1:1</span></label>' % (i, " checked" if use_m else "", r["bM"]))
        opt.append('<label class="opt n" onclick="event.stopPropagation()"><input type="radio" name="c%d" value="N"%s onchange="cnt()"><div style="width:96px;height:60px;display:flex;align-items:center;justify-content:center;color:#f0a0a8;font-size:12px">不用</div><span class="lbl">跳过</span></label>' % (i, " checked" if r["low"] else ""))
        tg = '<span class="tag">待确认 %.2f/%.2f</span>' % (r["score"], r["second"]) if r["low"] else ""
        h.append('<div class="card pick" data-f="%s" data-n="%s"><div style="min-width:150px;max-width:190px">'
                 '<div class="nm">%d. %s</div><div class="en">%s</div><div class="st">港服：%s</div>%s</div>%s</div>'
                 % (cls, r["name"].replace('"', "&quot;"), i, r["name"], (r.get("en") or ""), r["store"], tg, "".join(opt)))

    h.append("""</div><div style="margin-top:16px"><button onclick="gen()">生成所选清单</button>
<button onclick="allP()">全部尽量用竖版</button><button onclick="copy()">复制</button>
<span id="cnt" style="color:#8ab4f8;font-size:12.5px;margin-left:8px"></span></div>
<textarea id="out" placeholder="点上面按钮生成"></textarea>
<script>
function cnt(){var t=document.querySelectorAll('.card.pick').length;document.getElementById('cnt').textContent='已选 '+t+' 款';}
function allP(){document.querySelectorAll('input[value=P]').forEach(function(i){i.checked=true});cnt();}
function copy(){var e=document.getElementById('out');e.select();document.execCommand('copy');}
function gen(){
  var lines=[];
  document.querySelectorAll('.card').forEach(function(c){
    if(!c.dataset.n) return;
    var s=c.querySelector('input:checked'); if(!s||s.value==='N') return;
    lines.push(c.dataset.n+'|'+s.value);
  });
  document.getElementById('out').value=lines.join('\\n');
  cnt();
}
document.querySelectorAll('.tab').forEach(function(t){
  t.onclick=function(){
    document.querySelectorAll('.tab').forEach(function(x){x.classList.remove('on')});t.classList.add('on');
    var f=t.dataset.f;
    document.querySelectorAll('.card').forEach(function(c){c.style.display=(f==='all'||c.dataset.f===f)?'':'none'});
  };
});
cnt();
</script>""")
    out = os.path.join(OUT_PARENT, "无封面商品-港服候选图.html")
    open(out, "w", encoding="utf-8").write("".join(h))
    print("->", out, "%.1f MB" % (os.path.getsize(out) / 1048576))


if __name__ == "__main__":
    main()
