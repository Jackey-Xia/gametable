#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
preview_rest88.py —— 「剩余无封面商品 · 双源候选图」挑选页
=========================================================
读 covers/missing_report.json（港服中文页候选，方图/竖图）
 + covers/gamersky_missing.json（游民星空竖版候选，第三方源）
只渲染**当前仍无封面**的商品（以 covers/auto_skip.json 为准），重新编号 1..N。

每张卡：港服竖版 / 港服方图 / 游民竖版 三选一，或「不要」。
底部一键复制所选清单：  name|role   （role = P / M / GS）
"""
import base64
import io
import json
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
import identify_zh as I          # noqa: E402
import gamersky_cover as G       # noqa: E402
from PIL import Image            # noqa: E402

MISS = os.path.join(BASE, "covers", "missing_report.json")
GSKY = os.path.join(BASE, "covers", "gamersky_missing.json")
SKIP = os.path.join(BASE, "covers", "auto_skip.json")
OUT = "/Users/jackey/WorkBuddy/2026-09-08-16-48-51/gametable/剩余无封面-双源候选图.html"
W = 200


def thumb(url, tag, force_w=None):
    if not url:
        return "", 0, 0
    w = force_w or W
    try:
        p = I.download(url, tag)
        im = Image.open(p).convert("RGB")
        ow, oh = im.size
        h = max(1, int(oh * w / ow))
        im = im.resize((w, h), Image.LANCZOS)
        b = io.BytesIO()
        im.save(b, "JPEG", quality=74, optimize=True, progressive=True)
        return "data:image/jpeg;base64," + base64.b64encode(b.getvalue()).decode(), ow, oh
    except Exception as ex:
        print("   img fail", tag, str(ex)[:60])
        return "", 0, 0


def thumb_gs(url, tag):
    if not url:
        return "", 0, 0
    try:
        b = G.http(url)
        im = Image.open(io.BytesIO(b)).convert("RGB")
        ow, oh = im.size
        h = max(1, int(oh * W / ow))
        im = im.resize((W, h), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=76)
        return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode(), ow, oh
    except Exception as ex:
        print("   gs img fail", tag, str(ex)[:60])
        return "", 0, 0


def norm(s):
    return G.norm(s or "")


def warn_tags(name, store):
    tags = []
    a, b = norm(name), norm(store)
    if a and b.startswith(a):
        rest = b[len(a):]
        if rest and rest[0].isdigit():
            tags.append("疑似续作「%s」，需核对" % rest[:3])
    elif a and not (a in b or b in a):
        tags.append("名称不完全一致，需核对")
    if "版" in (name or "") and "版" not in (store or ""):
        tags.append("店名含版本词、候选无版本标注")
    return tags


CSS = """
*{box-sizing:border-box}
body{margin:0;background:#f4f6f8;color:#1d2733;font:14px/1.6 -apple-system,"PingFang SC","Microsoft YaHei",sans-serif}
header{position:sticky;top:0;z-index:50;background:#0f2d25;color:#e8f1ec;padding:14px 22px;display:flex;flex-wrap:wrap;gap:14px;align-items:center;box-shadow:0 2px 12px rgba(0,0,0,.18)}
header h1{font-size:17px;margin:0;font-weight:600}
header .sub{opacity:.75;font-size:12px}
.bar{margin-left:auto;display:flex;gap:10px;align-items:center;flex-wrap:wrap}
button{font:inherit;border:0;border-radius:8px;padding:9px 16px;cursor:pointer;background:#c9a227;color:#1a1a1a;font-weight:600}
button.ghost{background:rgba(255,255,255,.14);color:#e8f1ec;font-weight:500}
.filters{padding:12px 22px;background:#fff;border-bottom:1px solid #e2e8ee;display:flex;gap:10px;flex-wrap:wrap;align-items:center;position:sticky;top:56px;z-index:40}
.filters label{font-size:13px;color:#48586b;display:inline-flex;gap:6px;align-items:center;cursor:pointer}
.filters input[type=text]{padding:7px 12px;border:1px solid #cfd8e3;border-radius:8px;width:210px;font:inherit}
select{padding:7px 10px;border:1px solid #cfd8e3;border-radius:8px;font:inherit;background:#fff}
main{padding:18px 22px 140px;display:grid;grid-template-columns:repeat(auto-fill,minmax(430px,1fr));gap:16px}
.card{background:#fff;border:1px solid #e2e8ee;border-radius:12px;padding:14px;display:flex;gap:14px}
.card.sel{border-color:#c9a227;box-shadow:0 0 0 2px rgba(201,162,39,.28)}
.no{width:30px;height:30px;flex:0 0 30px;border-radius:50%;background:#0f2d25;color:#c9a227;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:13px}
.info{flex:1;min-width:0}
.nm{font-weight:600;font-size:15px;margin-bottom:2px;word-break:break-all}
.en{font-size:11.5px;color:#7b8a9b;margin-bottom:6px;word-break:break-all}
.tag{display:inline-block;font-size:11px;padding:2px 7px;border-radius:5px;margin:2px 4px 2px 0}
.t-hi{background:#e6f4ea;color:#1e7e34}
.t-lo{background:#fff4e0;color:#9a6400}
.t-no{background:#f1f3f5;color:#6b7785}
.t-w{background:#fdeaea;color:#b3261e}
.opts{display:flex;gap:10px;flex-wrap:wrap;margin-top:8px}
.opt{border:1px solid #dbe3ec;border-radius:10px;padding:8px;cursor:pointer;background:#fbfcfd;text-align:center;width:112px;position:relative}
.opt.on{border-color:#c9a227;background:#fffbe9;box-shadow:0 0 0 2px rgba(201,162,39,.25)}
.opt img{width:100%;border-radius:6px;display:block;background:#eef1f4}
.opt .lb{font-size:11px;color:#5b6b7d;margin-top:5px}
.opt .dim{font-size:10px;color:#93a1b0}
.opt .rk{position:absolute;top:4px;left:4px;font-size:10px;background:#0f2d25;color:#c9a227;border-radius:4px;padding:1px 5px}
.nonebtn{margin-top:10px;font-size:12px;color:#8a97a6;cursor:pointer;text-decoration:underline;background:none;padding:0}
footer{position:fixed;bottom:0;left:0;right:0;background:#fff;border-top:1px solid #e2e8ee;padding:12px 22px;display:flex;gap:12px;align-items:center;z-index:60;box-shadow:0 -2px 14px rgba(0,0,0,.08)}
#cnt{font-weight:600;color:#0f2d25}
#out{flex:1;font-size:12px;color:#48586b;background:#f4f6f8;border:1px solid #e2e8ee;border-radius:8px;padding:8px 12px;white-space:pre;overflow-x:auto;max-height:64px}
"""


def main():
    skip = set(json.load(open(SKIP, encoding="utf-8")))
    items = [r for r in json.load(open(MISS, encoding="utf-8"))["items"] if r.get("name") in skip]
    items.sort(key=lambda r: (not r.get("store"), -(r.get("score") or 0), r["name"]))
    gs = {r["name"]: r for r in json.load(open(GSKY, encoding="utf-8")) if r.get("url")}

    rows = []
    for i, r in enumerate(items, 1):
        nm = r["name"]
        print("[%2d/%d] %s" % (i, len(items), nm[:34]))
        bP, pw, ph = thumb(r.get("zhP"), "r88P%d" % i)
        bM, mw, mh = thumb(r.get("zhM"), "r88M%d" % i)
        g = gs.get(nm)
        bG, gw, gh = thumb_gs(g["url"], "r88G%d" % i) if g else ("", 0, 0)
        rows.append({
            "idx": i, "name": nm, "en": r.get("en", ""),
            "store": r.get("store", ""), "score": r.get("score", 0),
            "second": r.get("second", 0),
            "warn": warn_tags(nm, r.get("store", "")) + (warn_tags(nm, g.get("storeName", "")) if g else []),
            "P": bP, "Pd": "%dx%d" % (pw, ph) if bP else "",
            "M": bM, "Md": "%dx%d" % (mw, mh) if bM else "",
            "G": bG, "Gd": "%dx%d" % (gw, gh) if bG else "",
            "gsName": g.get("storeName", "") if g else "",
        })
    json.dump(rows, open(os.path.join(BASE, "covers", "rest88_rows.json"), "w", encoding="utf-8"),
              ensure_ascii=False)

    data = json.dumps(rows, ensure_ascii=False)
    html = []
    html.append("<!doctype html><html lang=zh-CN><head><meta charset=utf-8>"
                "<meta name=viewport content='width=device-width,initial-scale=1'>"
                "<title>剩余无封面商品 · 双源候选图</title><style>" + CSS + "</style></head><body>")
    html.append("<header><h1>剩余无封面商品 · 双源候选图</h1>"
                "<span class='sub'>共 %d 款 &nbsp;|&nbsp; 港服中文页 / 游民星空 &nbsp;|&nbsp; "
                "默认竖版优先</span>"
                "<div class=bar>"
                "<button class=ghost onclick='pickAll(\"P\")'>全选港服竖版</button>"
                "<button class=ghost onclick='pickAll(\"M\")'>全选港服方图</button>"
                "<button onclick='copyOut()'>复制所选清单</button>"
                "</div></header>" % len(rows))
    html.append("<div class=filters>"
                "<input type=text id=q placeholder='搜索商品名…' oninput='render()'>"
                "<label><input type=checkbox id=fHi onchange='render()'>只看高置信</label>"
                "<label><input type=checkbox id=fG onchange='render()'>只看有游民候选</label>"
                "<label><input type=checkbox id=fNo onchange='render()'>只看港服搜不到</label>"
                "<label><input type=checkbox id=fPick onchange='render()'>只看已选</label>"
                "<select id=sort onchange='render()'><option value=0>默认排序</option>"
                "<option value=1>按置信度</option><option value=2>按名称</option></select>"
                "</div>")
    html.append("<main id=main></main>")
    html.append("<footer><span id=cnt>已选 0</span><div id=out>点卡片里的图片选择；下方一键复制清单</div></footer>")
    html.append("<script>const DATA=%s;let SEL={};" % data)
    html.append(r"""
function score(r){return r.score||0}
function cls(r){
  if(!r.store) return 'no';
  if(score(r)>=0.85 && (score(r)-(r.second||0))>=0.04) return 'hi';
  return 'lo';
}
function pick(i,role){ if(SEL[i]===role) delete SEL[i]; else SEL[i]=role; render(); }
function pickAll(role){
  document.querySelectorAll('#main .card').forEach(c=>{
    const i=+c.dataset.i;
    const r=DATA.find(x=>x.idx===i);
    if(role==='P'&&r.P) SEL[i]='P';
    if(role==='M'&&r.M) SEL[i]='M';
    if(role==='G'&&r.G) SEL[i]='G';
  });
  render();
}
function esc(s){return (s||'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]))}
function render(){
  const q=document.getElementById('q').value.trim().toLowerCase();
  const fHi=document.getElementById('fHi').checked;
  const fG=document.getElementById('fG').checked;
  const fNo=document.getElementById('fNo').checked;
  const fPick=document.getElementById('fPick').checked;
  const so=+document.getElementById('sort').value;
  let list=DATA.filter(r=>{
    if(q && !((r.name+' '+r.en+' '+r.store).toLowerCase().includes(q))) return false;
    const c=cls(r);
    if(fHi && c!=='hi') return false;
    if(fG && !r.G) return false;
    if(fNo && r.store) return false;
    if(fPick && !SEL[r.idx]) return false;
    return true;
  });
  if(so===1) list.sort((a,b)=>score(b)-score(a));
  if(so===2) list.sort((a,b)=>a.name.localeCompare(b.name,'zh'));
  const m=document.getElementById('main');
  m.innerHTML=list.map(r=>{
    const c=cls(r);
    const badge = c==='hi' ? "<span class='tag t-hi'>港服高置信 "+score(r).toFixed(2)+"</span>"
      : c==='lo' ? "<span class='tag t-lo'>港服待确认 "+score(r).toFixed(2)+"</span>"
      : "<span class='tag t-no'>港服未搜到</span>";
    const warn=r.warn.map(w=>"<span class='tag t-w'>"+esc(w)+"</span>").join('');
    const sel=SEL[r.idx]||'';
    const opt=(role,img,dim,label,rank)=> img
      ? "<div class='opt "+(sel===role?'on':'')+"' data-i='"+r.idx+"' data-r='"+role+"'>"
        +"<span class='rk'>"+rank+"</span><img src='"+img+"' loading=lazy>"
        +"<div class='lb'>"+label+"</div><div class='dim'>"+dim+"</div></div>" : "";
    const store=r.store?"<div class='en'>港服命中："+esc(r.store)+"</div>":"";
    const gsn=r.gsName?"<div class='en'>游民命中："+esc(r.gsName)+"</div>":"";
    return "<div class='card "+(sel?'sel':'')+"' data-i='"+r.idx+"'>"
      +"<div class='no'>"+r.idx+"</div><div class='info'>"
      +"<div class='nm'>"+esc(r.name)+"</div>"
      +"<div class='en'>"+esc(r.en)+"</div>"+badge+warn+store+gsn
      +"<div class='opts'>"+opt('P',r.P,r.Pd,'港服竖版','P')+opt('M',r.M,r.Md,'港服方图','M')
      +opt('G',r.G,r.Gd,'游民竖版','GS')+"</div>"
      +((r.P||r.M||r.G)?"<button class=nonebtn data-none='"+r.idx+"'>不要 / 清除</button>":"")
      +"</div></div>";
  }).join('');
  m.querySelectorAll('.opt').forEach(o=>o.onclick=()=>pick(+o.dataset.i,o.dataset.r));
  m.querySelectorAll('[data-none]').forEach(b=>b.onclick=()=>{delete SEL[+b.dataset.none];render();});
  const ids=Object.keys(SEL).sort((a,b)=>a-b);
  document.getElementById('cnt').textContent='已选 '+ids.length;
  document.getElementById('out').textContent=ids.map(i=>{
    const r=DATA.find(x=>x.idx==i);
    return r.name+'|'+(SEL[i]==='G'?'GS':SEL[i]);
  }).join('\n');
}
function copyOut(){
  const t=document.getElementById('out').textContent;
  if(!t.trim()){alert('还没有选择任何封面');return}
  navigator.clipboard.writeText(t).then(()=>alert('已复制 '+t.split('\n').length+' 条，粘贴发给我即可'));
}
render();
""")
    html.append("</script></body></html>")
    open(OUT, "w", encoding="utf-8").write("\n".join(html))
    print("\nOK ->", OUT, "| 卡片", len(rows))


if __name__ == "__main__":
    main()
