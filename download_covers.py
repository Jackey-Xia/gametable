#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""方案A第三步：按 games_meta.json 批量下载封面 -> cloudrepo/covers/。
优先 PCGamingWiki 盒图缩略图(420px)；无 cover 有 appid 时走 Steam 竖版海报(经 wsrv.nl 代理)。
产物:
  cloudrepo/covers/<hash>.jpg          封面图
  cloudrepo/covers/manifest.json       { 游戏名: "covers/<hash>.jpg" }
  match_out/fetch_report.json          抓取报告
"""
import json, os, re, hashlib, time, urllib.request, urllib.parse
from concurrent.futures import ThreadPoolExecutor

BASE = os.path.dirname(os.path.abspath(__file__))
COVERS = os.path.join(BASE, "covers")
os.makedirs(COVERS, exist_ok=True)
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/121.0 Safari/537.36")

meta = json.load(open(os.path.join(BASE, "match_out/games_meta.json"), encoding="utf-8"))


def http(url, referer=None, timeout=45):
    h = {"User-Agent": UA, "Accept": "*/*"}
    if referer:
        h["Referer"] = referer
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def fhash(en_title):
    return hashlib.md5(en_title.strip().lower().encode("utf-8")).hexdigest()[:12]


def main():
    # 1) 文件名 -> thumburl 批量解析（含去重）
    file2thumb = {}
    files = []
    seen_file = {}
    for name, m in meta.items():
        if not m.get("cover"):
            continue
        fn = m["cover"]
        seen_file.setdefault(fn, []).append(name)
        if fn not in files:
            files.append(fn)
    print("待解析封面文件:", len(files))
    for i in range(0, len(files), 50):
        batch = files[i:i + 50]
        try:
            j = json.loads(http("https://www.pcgamingwiki.com/w/api.php?" + urllib.parse.urlencode({
                "action": "query", "prop": "imageinfo", "iiprop": "url",
                "iiurlwidth": 420, "titles": "|".join("File:" + f for f in batch),
                "format": "json"}), timeout=90).decode("utf-8"))
            norm = {}
            for it in j.get("query", {}).get("normalized", []):
                norm[it["from"]] = it["to"]
            for p in j.get("query", {}).get("pages", {}).values():
                orig = p.get("title", "")
                ii = (p.get("imageinfo") or [{}])[0]
                u = ii.get("thumburl") or ii.get("url")
                if u:
                    file2thumb[orig] = u
        except Exception as e:
            print("imageinfo 批次失败:", str(e)[:120])
        time.sleep(0.4)
        if (i // 50) % 4 == 0:
            print(f"  解析进度 {i + len(batch)}/{len(files)}")
    print("拿到缩略图地址:", len(file2thumb))

    # 2) 组装下载任务（按 en/appid 去重，PS4/PS5 同游戏共用一张图）
    jobs = []       # (filename_on_disk, url, referer, [names])
    byname = {}     # name -> filename
    file_used = {}
    for name, m in meta.items():
        fn = None
        if m.get("cover") and m["cover"] in file2thumb:
            fn = fhash(m["cover"]) + ".jpg"
            jobs.append((fn, file2thumb[m["cover"]], "https://www.pcgamingwiki.com/", name))
        elif m.get("appid"):
            fn = fhash(m.get("title") or m["en"]) + "_s.jpg"
            url = ("https://wsrv.nl/?url=" + urllib.parse.quote(
                f"shared.fastly.steamstatic.com/store_item_assets/steam/apps/{m['appid']}/library_600x900.jpg", safe="")
                + "&w=420&output=jpg&q=78")
            jobs.append((fn, url, None, name))
        if fn:
            byname[name] = "covers/" + fn

    # 去重任务（同文件多游戏名 -> 下载一次，记录所有 name）
    ded = {}
    for fn, url, ref, name in jobs:
        ded.setdefault(fn, {"url": url, "ref": ref, "names": []})["names"].append(name)
    print("下载任务(去重后):", len(ded))

    # overrides：人工覆盖优先
    ov_path = os.path.join(BASE, "match_out/overrides.json")
    overrides = {}
    if os.path.exists(ov_path):
        overrides = json.load(open(ov_path, encoding="utf-8"))
        for name, path in overrides.items():
            byname[name] = path
        print("应用人工覆盖:", len(overrides))

    # 3) 并发下载
    def dl(item):
        fn, info = item
        dest = os.path.join(COVERS, fn)
        if os.path.exists(dest) and os.path.getsize(dest) > 3000:
            return fn, "cached"
        for attempt in range(2):
            try:
                raw = http(info["url"], referer=info["ref"])
                if len(raw) < 3000:
                    raise RuntimeError("too small %d" % len(raw))
                open(dest, "wb").write(raw)
                return fn, "ok"
            except Exception as e:
                err = str(e)[:100]
                time.sleep(1.5)
        return fn, "fail:" + err

    ok = fail = cached = 0
    failed_files = []
    with ThreadPoolExecutor(max_workers=8) as ex:
        for i, (fn, st) in enumerate(ex.map(dl, ded.items())):
            if st == "ok":
                ok += 1
            elif st == "cached":
                cached += 1
            else:
                fail += 1
                failed_files.append(fn)
            if (i + 1) % 100 == 0:
                print(f"  下载进度 {i+1}/{len(ded)}  ok={ok} cached={cached} fail={fail}")

    # 失败的名字从 manifest 移除（前端回退占位图）
    for fn in failed_files:
        info = ded[fn]
        for name in info["names"]:
            if name in byname and not (name in overrides):
                del byname[name]

    # 自定义覆盖文件存在性校验
    for name, path in list(byname.items()):
        if name in overrides:
            p = os.path.join(BASE, path)
            if not os.path.exists(p):
                del byname[name]

    # 合并旧 manifest: 本轮匹配不到的条目, 只要旧图文件还在就保留(防止误清下架已有封面)
    mpath = os.path.join(COVERS, "manifest.json")
    if os.path.exists(mpath):
        try:
            old = json.load(open(mpath, encoding="utf-8"))
            kept = 0
            for name, rel in old.items():
                if name not in byname and os.path.exists(os.path.join(BASE, rel)):
                    byname[name] = rel
                    kept += 1
            if kept:
                print("保留旧 manifest 条目:", kept)
        except Exception:
            pass

    json.dump(byname, open(os.path.join(COVERS, "manifest.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=0, sort_keys=True)
    json.dump({"ok": ok, "cached": cached, "fail": fail, "failed_files": failed_files,
               "no_page": json.load(open(os.path.join(BASE, "match_out/no_page.json"), encoding="utf-8"))},
              open(os.path.join(BASE, "match_out/fetch_report.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    total = sum(os.path.getsize(os.path.join(COVERS, f)) for f in os.listdir(COVERS) if f.endswith(".jpg"))
    print(f"\n== 抓取完成 == ok={ok} cached={cached} fail={fail}  总体积 {total/1048576:.1f} MB")
    print("manifest 条目:", len(byname))


if __name__ == "__main__":
    main()
