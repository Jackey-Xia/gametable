#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""blank_find2.py —— 任务2 第④步「网上找图」（对未找到的商品兜底）。

  a) 游民星空: 换英文名/别名再搜一次
  b) 维基百科: 页面主图（游戏条目主图即官方盒装封面）zh -> en
更新 /tmp/blank_state.json，下载到 /tmp/blank_orig/{i}.jpg
"""
import json, os, re, sys, urllib.parse, urllib.request, ssl

REPO = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, REPO)
import gamersky_cover as GK
import autocover as AC

STATE = "/tmp/blank_state.json"
SRC = "/tmp/blank_orig"
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120 Safari/537.36"}

state = json.load(open(STATE, encoding="utf-8"))


def http_bytes(url, timeout=30):
    req = urllib.request.Request(url, headers=UA)
    return urllib.request.urlopen(req, timeout=timeout, context=CTX).read()


def wiki_image(titles, lang=("zh", "en")):
    """依次在各语种维基找条目主图, 返回 (url, source) 或 (None, None)"""
    for lg in lang:
        for t in titles:
            if not t:
                continue
            try:
                u = "https://%s.wikipedia.org/api/rest_v1/page/summary/%s" % (
                    lg, urllib.parse.quote(t))
                d = json.loads(http_bytes(u))
            except Exception:
                continue
            og = d.get("originalimage") or {}
            th = d.get("thumbnail") or {}
            url = og.get("source") or th.get("source")
            if url and (og.get("width") or 0) >= 200:
                return url, "%s维基:%s" % (lg, d.get("title", t))
            if url and th.get("source"):
                return th["source"], "%s维基:%s" % (lg, d.get("title", t))
    return None, None


def main():
    todo = {k: v for k, v in state.items()
            if v.get("step") in (None, "未找到") or (v.get("step") or "").startswith("未找到")}
    print("网上找图兜底 %d 项" % len(todo))
    for rep, v in sorted(todo.items()):
        i = v["i"]
        got = False
        # a) 游民星空英文名
        en = (v.get("en") or "").strip()
        if en:
            for t in re.split(r"[/／]", en)[:2]:
                t = re.sub(r"[(（][^)）]*[)）]", "", t).strip()
                if not t:
                    continue
                try:
                    it = GK.fetch(rep, term=t)
                except Exception:
                    it = None
                if it and it.get("url") and it.get("score", 0) >= 0.9:
                    try:
                        GK.download({"url": it["url"]}, os.path.join(SRC, "%04d.jpg" % i))
                        v.update({"step": "④网上找图(游民英文名)", "cand": it.get("storeName", ""),
                                  "role": "GAMERSKY"})
                        got = True
                        break
                    except Exception:
                        pass
        # b) 维基百科盒图
        if not got:
            base = AC.strip_seq(AC.strip_ed(rep))
            titles = [base] + [t for t in re.split(r"[/／]", en or "") if t.strip()]
            url, srcname = wiki_image(titles)
            if url:
                try:
                    data = http_bytes(url)
                    p = os.path.join(SRC, "%04d.jpg" % i)
                    open(p, "wb").write(data)
                    from PIL import Image
                    im = Image.open(p)
                    im.load()
                    if im.width < 150:
                        os.remove(p)
                    else:
                        if im.format != "JPEG":          # 统一转 JPEG
                            im.convert("RGB").save(p, "JPEG", quality=93)
                        v.update({"step": "④网上找图(维基百科)", "cand": srcname,
                                  "role": "WIKI", "size": [im.width, im.height]})
                        got = True
                except Exception:
                    pass
        print("  #%d %s -> %s" % (i, rep[:26], v.get("step")))
        state[rep] = v
    json.dump(state, open(STATE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    miss = sum(1 for v in state.values() if (v.get("step") or "").startswith("未找到"))
    print("仍未找到 %d" % miss)


if __name__ == "__main__":
    main()
