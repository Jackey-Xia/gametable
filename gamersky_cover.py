# -*- coding: utf-8 -*-
"""gamersky_cover.py —— 从游民星空(ku.gamersky.com)取竖版游戏封面

背景
----
港服 PS Store 部分商品**没有 PORTRAIT_BANNER(竖版 2:3)**，只有 MASTER(方图)；
另有一批商品在港服**完全搜不到**。游民星空游戏库对每款游戏都有一张竖版封面，
可作为这些情况的补充来源。

取图原理（纯 HTTP，无需浏览器、无防盗链）
------------------------------------
1. 搜索：``https://so.gamersky.com/?s={中文名}`` → 页面内出现 ``ku.gamersky.com/{年}/{slug}/``
2. 页面解析（PC 版 ku 页的封面是 JS 动态加载的，**必须走 wap 版**）：
   ``https://wap.gamersky.com/ku/{slug}/`` → ``<img class="game_fm" src="...">``
3. 封面 URL 规律：``https://imgs.gamersky.com/ku/{年}/ku_{slug去连字符小写}.jpg``
   - 不带后缀 = 缩略图 135x191（太小）
   - ``_b`` 后缀 = **366x517**（约 1.413:1，本项目实际使用这个）

画像限制（务必知情）
--------------------
- 分辨率 366x517，比港服 504x756 小；比例 1.413 而非标准 2:3(1.5)。
  站点卡片是 96x128 的 ``object-fit:cover``，实际显示够用（2x 屏需 192px 宽）。
- **第三方来源**：按 cover_policy 规则②，自动抓图只认港服中文页。
  本脚本产出必须登记为 ``manual``（人工指定），不得进自动管线。

用法::

    python3 gamersky_cover.py --search 杀戮尖塔          # 只查链接
    python3 gamersky_cover.py --fetch 杀戮尖塔            # 下载封面到 covers/gs{md5}.jpg
    python3 gamersky_cover.py --missing                   # 全量无封面商品批量试抓(只报告, 不落盘)
"""
import hashlib
import io
import json
import os
import re
import ssl
import sys
import time
import urllib.parse
import urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
MANIFEST = os.path.join(BASE, "covers", "manifest.json")

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
UA_M = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
        "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1")
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

SEARCH = "https://so.gamersky.com/?s=%s"
WAP_KU = "https://wap.gamersky.com/ku/%s/"
IMG = "https://imgs.gamersky.com/ku/%s/ku_%s%s.jpg"


def http(url, mobile=False, timeout=30):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA_M if mobile else UA,
        "Accept-Language": "zh-CN,zh;q=0.9",
    })
    return urllib.request.urlopen(req, timeout=timeout, context=CTX).read()


def norm(s):
    """归一化游戏名: 剥平台/版本括注、去空白与全角标点"""
    s = re.sub(r"[（(](?:PS[45]|PS5|PS4|PSVR2?|中文版|中英文版|中韩文版|英文版|日文版|"
               r"简体中文版|完整版|豪华版|传奇版|终极版|大师版|决定版|重制版|联机版)[)）]", "", s)
    s = re.sub(r"[\s:：·・\-—_/&+]+", "", s)
    return s.lower()


# ---------------------------------------------------------------- 搜索
def search_kus(term):
    """游民站内搜索 → [{slug, year, url, title}]"""
    try:
        html = http(SEARCH % urllib.parse.quote(term), mobile=True).decode("utf-8", "ignore")
    except Exception:
        return []
    out, seen = [], set()
    for m in re.finditer(r'ku\.gamersky\.com/(\d{4})/([a-z0-9\-]+)/', html):
        yr, slug = m.group(1), m.group(2)
        if slug in seen:
            continue
        seen.add(slug)
        # 尝试抓该条目的中文标题（搜索页里链接附近有游戏名）
        out.append({"year": yr, "slug": slug,
                    "url": "https://ku.gamersky.com/%s/%s/" % (yr, slug)})
    return out


def ku_title(slug):
    """从 wap 页取游戏中文名 + 封面 url"""
    try:
        html = http(WAP_KU % slug, mobile=True).decode("utf-8", "ignore")
    except Exception:
        return None, None
    t = re.search(r'class="game_fm"[^>]*src="([^"]+)"', html)
    fm = t.group(1) if t else None
    n = re.search(r'<h5>([^<]+)</h5>', html)
    title = n.group(1).strip() if n else ""
    return title, fm


def cover_url(fm_url, year, slug):
    """把 wap 页的缩略图地址升级为 _b 大图"""
    if fm_url:
        big = fm_url if "_b." in fm_url else re.sub(r"\.jpg$", "_b.jpg", fm_url)
        return big, fm_url
    guess = IMG % (year, slug.replace("-", ""), "")
    return guess, re.sub(r"\.jpg$", "_b.jpg", guess)


def fetch(name, term=None, dry=False):
    """为 name 找游民竖版封面; dry=True 只返回信息不落盘"""
    terms = [t for t in [term, name, norm(name)] if t]
    cands = []
    for t in terms[:2]:
        for c in search_kus(t)[:6]:
            if c["slug"] in {x["slug"] for x in cands}:
                continue
            cands.append(c)
    # 先按 slug/标题的粗略相似度排序，减少 wap 页请求数
    nn_all = norm(name)
    def rough(c):
        s = norm(c["slug"])
        if s == nn_all:
            return 0
        if nn_all and (nn_all in s or s in nn_all):
            return 1
        try:
            import difflib
            return 2 - difflib.SequenceMatcher(None, nn_all, s).ratio()
        except Exception:
            return 3
    cands.sort(key=rough)
    best = None
    for c in cands[:4]:
        title, fm = ku_title(c["slug"])
        if not title and not fm:
            continue
        big, small = cover_url(fm, c["year"], c["slug"])
        # 名字吻合度
        nt, nn = norm(title), norm(name)
        score = 1.0 if nt == nn else (0.9 if (nn and (nn in nt or nt in nn)) else 0.0)
        item = {"name": name, "slug": c["slug"], "year": c["year"], "storeName": title,
                "url": big, "small": small, "score": score}
        if score >= 0.9:
            best = item
            break
        if best is None and score > 0:
            best = item
    return best


def download(item, dest):
    b = http(item["url"])
    from PIL import Image
    im = Image.open(io.BytesIO(b))
    if im.width < 200:                       # 退回小图不可用
        raise RuntimeError("分辨率过低 %dx%d" % (im.width, im.height))
    with open(dest, "wb") as f:
        f.write(b)
    return len(b), im.width, im.height


# ---------------------------------------------------------------- CLI
def main():
    argv = sys.argv[1:]
    if "--missing" in argv:
        import cover_policy as CP
        m = CP.load_manifest()
        ps = json.load(open(os.path.join(BASE, "data", "ps_games.json"), encoding="utf-8"))
        todo = [(r["name"], r.get("en") or "") for r in ps if r.get("name") and not m.get(r["name"])]
        print("无封面商品 %d 款, 开始试抓游民封面…" % len(todo), flush=True)
        rep = []
        for i, (n, en) in enumerate(todo, 1):
            try:
                it = fetch(n)
            except Exception as e:
                it = None
                print("  ERR", n, str(e)[:60], flush=True)
            if it:
                rep.append(it)
                print("  %3d/%d ✓ %-28s -> %s" % (i, len(todo), n[:28], it["storeName"][:22]), flush=True)
            else:
                rep.append({"name": n, "storeName": "", "url": "", "score": 0, "slug": ""})
                print("  %3d/%d ✗ %s" % (i, len(todo), n[:40]), flush=True)
            time.sleep(0.3)
        out = os.path.join(BASE, "covers", "gamersky_missing.json")
        json.dump(rep, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        ok = [r for r in rep if r["url"]]
        print("\n命中 %d / %d -> %s" % (len(ok), len(rep), out))
        return

    if "--search" in argv:
        term = argv[argv.index("--search") + 1]
        for c in search_kus(term)[:10]:
            t, fm = ku_title(c["slug"])
            big, _ = cover_url(fm, c["year"], c["slug"])
            print("%-40s %-30s %s" % (c["slug"], t or "?", big))
        return

    if "--fetch" in argv:
        term = argv[argv.index("--fetch") + 1]
        it = fetch(term)
        if not it:
            print("未找到:", term)
            return
        fn = "covers/gs%s.jpg" % hashlib.md5(it["name"].encode()).hexdigest()[:12]
        sz, w, h = download(it, os.path.join(BASE, fn))
        print("✓ %s\n   游民条目: %s\n   文件: %s  %dB  %dx%d" % (it["name"], it["storeName"], fn, sz, w, h))
        return

    print(__doc__)


if __name__ == "__main__":
    main()
