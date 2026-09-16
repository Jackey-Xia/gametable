# -*- coding: utf-8 -*-
"""gamersky_preview.py —— 渲染「游民星空竖版封面候选」挑选页(自包含 HTML)

读 covers/gamersky_missing.json（gamersky_cover.py --missing 产出），
把每条的游民封面下载并缩到宽 210 内联，输出可勾选页面。
"""
import base64
import io
import json
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
import gamersky_cover as G  # noqa: E402
from PIL import Image  # noqa: E402

SRC = os.path.join(BASE, "covers", "gamersky_missing.json")
OUT = "/Users/jackey/WorkBuddy/2026-09-08-16-48-51/gametable/无封面商品-游民星空候选图.html"

# 店主点名要看的商品（在预览页顶部做「现有 vs 游民竖版」并排对比）
SPECIAL = ["奥丁领域 里普特拉西尔"]


def thumb(url, w=210):
    b = G.http(url)
    im = Image.open(io.BytesIO(b)).convert("RGB")
    h = int(im.height * w / im.width)
    im = im.resize((w, h), Image.LANCZOS)
    o = io.BytesIO()
    im.save(o, "JPEG", quality=76)
    return "data:image/jpeg;base64," + base64.b64encode(o.getvalue()).decode(), im.width, im.height


def warn_tags(name, store):
    """自动标注可疑匹配：命中条目是续作 / 同名不同版"""
    tags = []
    a, b = G.norm(name), G.norm(store)
    if a and b.startswith(a):
        rest = b[len(a):]
        if rest and rest[0].isdigit():
            tags.append("疑似续作 %s，需核对" % rest[:3])
    elif a and not (a in b or b in a):
        tags.append("名称不完全一致，需核对")
    return tags


def main():
    rep = json.load(open(SRC, encoding="utf-8"))
    hit = [r for r in rep if r.get("url")]
    miss = [r for r in rep if not r.get("url")]
    rows = []
    for i, r in enumerate(hit, 1):
        try:
            src, w, h = thumb(r["url"])
        except Exception as e:
            print("  缩略图失败", r["name"], str(e)[:60])
            continue
        rows.append({"name": r["name"], "store": r.get("storeName") or "", "src": src,
                     "w": w, "h": h, "url": r["url"], "score": r.get("score", 0), "idx": i,
                     "tags": warn_tags(r["name"], r.get("storeName") or "")})
        print("  %3d  %-32s %s" % (i, r["name"][:32], r.get("storeName", "")[:24]), flush=True)

    css = """
*{box-sizing:border-box}body{background:#12141a;color:#e8eaed;font-family:-apple-system,"PingFang SC",sans-serif;margin:0;padding:22px}
h1{font-size:20px;margin:0 0 6px}.sub{color:#9aa0a6;font-size:13px;line-height:1.7;margin-bottom:14px}
.bar{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin:14px 0 18px}
.tab{font-size:13px;padding:5px 12px;border-radius:999px;background:#1e2128;border:1px solid #2a2d35;cursor:pointer;user-select:none}
.tab.on{background:#23303c;border-color:#3d6b96;color:#8ec7ff}.hint{font-size:12px;color:#6b7280;margin-left:6px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:14px}
.card{background:#1a1d24;border:1px solid #262a33;border-radius:12px;padding:10px;display:flex;gap:10px;flex-direction:column}
.card.on{border-color:#34a853;box-shadow:0 0 0 1px #34a85355}
.card img{width:100%;border-radius:8px;display:block;background:#22262e}
.nm{font-size:13px;font-weight:600;line-height:1.4}
.st{font-size:11.5px;color:#7f8794;line-height:1.5}.st b{color:#8ec7ff;font-weight:600}
.tg{display:inline-block;font-size:10.5px;padding:1px 6px;border-radius:4px;background:#2a1e33;color:#c48ff0;margin-top:3px}
.btnbar{position:fixed;right:18px;bottom:18px;display:flex;gap:8px}
.btn{background:#2b6cb0;color:#fff;border:0;border-radius:10px;padding:10px 16px;font-size:13.5px;cursor:pointer;box-shadow:0 6px 18px #0008}
.btn.g{background:#2f855a}
#out{position:fixed;left:18px;right:18px;bottom:74px;background:#0f1115;border:1px solid #2a2d35;border-radius:10px;padding:10px;font-size:12px;color:#c9d1d9;max-height:130px;overflow:auto;display:none;white-space:pre-wrap}
"""
    H = ['<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">',
         '<title>无封面商品 · 游民星空竖版候选</title><style>%s</style>' % css,
         '<h1>无封面商品 · 游民星空竖版封面候选</h1>',
         '<div class="sub">共 %d 款无封面。其中 <b>%d 款</b>在游民星空找到竖版封面（下方），%d 款没找到。<br>'
         '游民图是 366×517 竖版（比例 1.413，非标准 2:3），分辨率低于港服官方图，'
         '但站点卡片 96×128 按 cover 裁切显示，够用。<br>'
         '<b>这是第三方来源</b>，只能按「人工指定」入库，不会进自动抓图管线。</div>'
         % (len(rep), len(rows), len(miss)),
         '<div class="bar"><span class="tab on" id="t-all">全部 %d</span>'
         '<span class="tab" id="t-sel">已选 <span id="c">0</span></span>'
         '<span class="hint">点卡片切换选中；默认全选，不想要的点掉即可</span></div>' % len(rows)]

    # ---- 店主点名款：与现有封面并排对比 ----
    import cover_policy as CP
    m = CP.load_manifest()
    for nm in SPECIAL:
        it = G.fetch(nm)
        if not it:
            print("  点名款未找到:", nm)
            continue
        try:
            gsrc, gw, gh = thumb(it["url"])
        except Exception as e:
            print("  点名款图失败", nm, str(e)[:50])
            continue
        old_rel = m.get(nm) or ""
        old_html = '<div class="st">（当前无封面）</div>'
        if old_rel and os.path.exists(os.path.join(BASE, old_rel)):
            im = Image.open(os.path.join(BASE, old_rel)).convert("RGB")
            o2 = io.BytesIO()
            im.resize((210, int(im.height * 210 / im.width)), Image.LANCZOS).save(o2, "JPEG", quality=76)
            old_html = ('<img src="data:image/jpeg;base64,%s" style="outline:1px solid #4a5462">'
                        % base64.b64encode(o2.getvalue()).decode())
        H.append('<h2 style="font-size:16px;margin:26px 0 4px">店主点名款</h2>'
                 '<div class="sub" style="margin-bottom:10px"><b>%s</b> —— 当前封面是港服的方图'
                 '（港服该商品没有竖版），游民星空有竖版可换。</div>' % nm)
        H.append('<div class="bar" style="margin:0 0 12px">'
                 '<div class="card" style="width:214px;margin:0"><div class="st">当前 · 港服官方方图</div>%s'
                 '<div class="nm">%s</div></div>'
                 '<div class="card on" data-n="%s" style="width:214px;margin:0">'
                 '<div class="st">游民竖版 %d×%d</div><img src="%s">'
                 '<div class="nm">%s</div><span class="tg">第三方源 · 需人工入库</span></div></div>'
                 % (old_html, nm, nm, gw, gh, gsrc, it["storeName"]))

    for d in rows:
        tg = "".join('<span class="tg">%s</span>' % t for t in d["tags"])
        H.append('<div class="card on" data-n="%s" data-i="%d">'
                 '<img src="%s" loading="lazy">'
                 '<div class="nm">%d. %s</div>'
                 '<div class="st">游民条目：<b>%s</b><br>%d×%d · 匹配 %.2f</div>'
                 '<span class="tg">第三方源 · 需人工入库</span>%s</div>'
                 % (d["name"].replace('"', "&quot;"), d["idx"], d["src"],
                    d["idx"], d["name"], d["store"], d["w"], d["h"], d["score"], tg))

    H.append('<div class="btnbar"><button class="btn" onclick="gen()">生成所选清单</button>'
             '<button class="btn g" onclick="cp()">复制</button></div>')
    H.append('<pre id="out"></pre>')
    H.append("""<script>
var cards=[].slice.call(document.querySelectorAll('.card[data-n]'));
function cnt(){document.getElementById('c').textContent=cards.filter(function(c){return c.classList.contains('on')}).length}
cards.forEach(function(c){c.onclick=function(){c.classList.toggle('on');cnt()}});
function gen(){var L=cards.filter(function(c){return c.classList.contains('on')}).map(function(c){return c.dataset.n});
var o=document.getElementById('out');o.style.display='block';o.textContent=L.join('\\n');cnt();}
function cp(){var o=document.getElementById('out');if(!o.textContent)gen();
navigator.clipboard.writeText(o.textContent).then(function(){alert('已复制 '+o.textContent.split('\\n').length+' 条')});}
document.getElementById('t-all').onclick=function(){cards.forEach(function(c){c.classList.add('on')});cnt()};
document.getElementById('t-sel').onclick=function(){cards.forEach(function(c){c.classList.remove('on')});cnt()};
cnt();
</script>""")

    open(OUT, "w", encoding="utf-8").write("".join(H))
    print("\n%s  %.1f MB" % (OUT, os.path.getsize(OUT) / 1048576))
    print("未命中 %d 款: %s" % (len(miss), "、".join(m["name"] for m in miss[:40])))


if __name__ == "__main__":
    main()
