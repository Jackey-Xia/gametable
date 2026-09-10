#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""方案A第一步：1180 款游戏 -> PCGamingWiki 批量匹配，产出 appid/封面映射。
产物: match_out/games_meta.json  (name -> {en,title,appid,cover,missing})
"""
import json, os, re, sys, time, hashlib
import urllib.request, urllib.parse
from concurrent.futures import ThreadPoolExecutor

API = "https://www.pcgamingwiki.com/w/api.php"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/121.0 Safari/537.36")
BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "match_out")
os.makedirs(OUT, exist_ok=True)

games = json.load(open(os.path.join(BASE, "cloudrepo/data/ps_games.json"), encoding="utf-8"))


def http(url, timeout=40):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def api(params, timeout=40):
    p = dict(params); p["format"] = "json"
    return json.loads(http(API + "?" + urllib.parse.urlencode(p), timeout).decode("utf-8"))


def parse_wikitext(content):
    """从页面 wikitext 提取 steam appid 与 cover 字段。"""
    appid = cover = ""
    m = re.search(r"steam\s*appid\s*=\s*(\d+)", content, re.I)
    if m:
        appid = m.group(1)
    m = re.search(r"\|\s*cover\s*=\s*([^\n|}]+)", content)
    if m:
        cover = m.group(1).strip().replace("''", "")
        cover = re.sub(r"\[\[|\]\]|\{\{.*?\}\}", "", cover).strip()
        cover = cover.split("|")[0].strip()
        if cover.lower().endswith((".jpg", ".jpeg", ".png", ".webp", ".gif")):
            pass
        else:
            cover = ""  # 不是图片文件名则丢弃
    return appid, cover


def main():
    meta = {}  # name -> dict
    for g in games:
        meta[g["name"]] = {"en": g.get("en", ""), "title": "", "appid": "", "cover": "", "missing": False}

    names = list(meta.keys())
    BATCH = 50
    batches = [names[i:i + BATCH] for i in range(0, len(names), BATCH)]
    print(f"共 {len(names)} 款，{len(batches)} 批批量查询...")

    def do_batch(b):
        titles = "|".join(m["en"] for m in (meta[n] for n in b))
        try:
            j = api({"action": "query", "prop": "revisions", "rvslots": "main",
                     "rvprop": "content", "titles": titles, "redirects": 1}, timeout=90)
            return b, j, None
        except Exception as e:
            return b, None, str(e)[:150]

    results = {}
    with ThreadPoolExecutor(max_workers=4) as ex:
        for b, j, err in ex.map(do_batch, batches):
            if err:
                print("批次失败(将重试):", err)
                results[tuple(b)] = None
                continue
            q = j.get("query", {})
            # 建立规范化标题映射 (redirects 规范化后 en -> title)
            norm = {}
            for item in q.get("normalized", []) + q.get("redirects", []):
                norm[item["from"]] = item["to"]
            pages = {p["title"]: p for p in q.get("pages", {}).values()}
            for n in b:
                t = norm.get(meta[n]["en"], meta[n]["en"])
                pg = pages.get(t)
                if not pg or "missing" in pg:
                    meta[n]["missing"] = True
                    continue
                meta[n]["title"] = t
                try:
                    content = pg["revisions"][0]["slots"]["main"]["*"]
                    appid, cover = parse_wikitext(content)
                    meta[n]["appid"] = appid
                    meta[n]["cover"] = cover
                except Exception:
                    meta[n]["missing"] = True
            results[tuple(b)] = True
            done = sum(1 for m in meta.values() if m["title"] or m["missing"])
            print(f"  进度 {done}/{len(names)}")

    # 重试失败批次
    retry = [list(k) for k, v in results.items() if v is None]
    for b in retry:
        print("重试批次", len(b))
        time.sleep(2)
        _, j, err = do_batch(b) if False else do_batch(b)  # noqa
    # 简化：不再复杂重试，失败项走单查
    todo = [n for n in names if not meta[n]["title"] and not meta[n]["missing"]]
    print("批量未覆盖，逐个查询:", len(todo))

    def probe(n):
        en = meta[n]["en"]
        try:
            j = api({"action": "query", "list": "search", "srsearch": en, "srlimit": 1})
            hits = j.get("query", {}).get("search", [])
            if not hits:
                meta[n]["missing"] = True
                return n, "no page"
            t = hits[0]["title"]
            j2 = api({"action": "query", "prop": "revisions", "rvslots": "main",
                      "rvprop": "content", "titles": t}, timeout=60)
            pg = list(j2["query"]["pages"].values())[0]
            content = pg["revisions"][0]["slots"]["main"]["*"]
            appid, cover = parse_wikitext(content)
            meta[n]["title"] = t
            meta[n]["appid"] = appid
            meta[n]["cover"] = cover
            return n, "ok"
        except Exception as e:
            return n, str(e)[:100]

    with ThreadPoolExecutor(max_workers=6) as ex:
        for i, (n, st) in enumerate(ex.map(probe, todo)):
            if (i + 1) % 50 == 0:
                print(f"  单查进度 {i+1}/{len(todo)}")

    json.dump(meta, open(os.path.join(OUT, "games_meta.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    ok = sum(1 for m in meta.values() if m["title"])
    has_cover = sum(1 for m in meta.values() if m["cover"])
    has_appid = sum(1 for m in meta.values() if m["appid"])
    print(f"\n== 匹配完成 ==\n匹配页面: {ok}/{len(names)}\n有cover字段: {has_cover}\n有appid: {has_appid}")
    print("无页面:", [n for n in names if meta[n]["missing"]][:20])


if __name__ == "__main__":
    main()
