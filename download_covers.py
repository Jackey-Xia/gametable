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

    # 合并旧 manifest ★铁律(2026-09-20): 已有封面一律不被本脚本覆盖
    #   - 店主明确要求「人工确认过的图片与商品锁死」。本脚本图源是 PCGamingWiki 盒图 / Steam 海报,
    #     属兜底图, 只能补「完全没有封面」的商品, 绝不能替换已有的 PS 商城封面 / 人工定版图。
    #   - 旧条目只要图片文件还在磁盘上, 就无条件保留(优先级高于本轮抓取结果)。
    mpath = os.path.join(COVERS, "manifest.json")
    protected = 0
    filled = 0
    if os.path.exists(mpath):
        try:
            old = json.load(open(mpath, encoding="utf-8"))
            for name, rel in old.items():
                if not rel or not os.path.exists(os.path.join(BASE, rel)):
                    continue
                if name in byname and byname[name] != rel:
                    protected += 1       # 本轮本会覆盖 -> 保护旧封面
                else:
                    filled += 1
                byname[name] = rel
        except Exception:
            pass
    print("保留已有封面(不被覆盖): %d | 本轮新增填补: %d" % (protected + filled, len(byname) - protected - filled))

    # ★第二道铁律护栏(2026-09-21): covers/pinned.json 锁定的图片拥有最高优先级
    #   - 即使某个已锁定的图片文件被误删 / manifest 条目缺失, 本脚本也绝不用 PC 兜底图顶替
    #   - 命中锁且锁文件仍在磁盘 -> 按锁自愈还原; 命中锁但文件缺失 -> 维持现状(宁缺勿错)
    ppath = os.path.join(COVERS, "pinned.json")
    pin_heal = 0
    pin_hold = 0
    if os.path.exists(ppath):
        try:
            pdoc = json.load(open(ppath, encoding="utf-8"))
            for _lid, _lock in (pdoc.get("locks") or {}).items():
                rel = (_lock or {}).get("file") or ""
                names = [n for n in ((_lock or {}).get("cn") or []) if n]
                if (_lock or {}).get("en"):
                    names.append(_lock["en"])
                if not rel or not names:
                    continue
                exists = os.path.exists(os.path.join(BASE, rel))
                for nm in names:
                    if nm in byname:
                        if exists and byname[nm] != rel:
                            byname[nm] = rel
                            pin_heal += 1
                        elif not exists:
                            pin_hold += 1
        except Exception:
            pass
    print("锁定图片保护(不让位给 PC 兜底图): 自愈 %d | 缺失保持原状 %d" % (pin_heal, pin_hold))

    json.dump(byname, open(os.path.join(COVERS, "manifest.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2, sort_keys=True)
    json.dump({"ok": ok, "cached": cached, "fail": fail, "failed_files": failed_files,
               "no_page": json.load(open(os.path.join(BASE, "match_out/no_page.json"), encoding="utf-8"))},
              open(os.path.join(BASE, "match_out/fetch_report.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    total = sum(os.path.getsize(os.path.join(COVERS, f)) for f in os.listdir(COVERS) if f.endswith(".jpg"))
    print(f"\n== 抓取完成 == ok={ok} cached={cached} fail={fail}  总体积 {total/1048576:.1f} MB")
    print("manifest 条目:", len(byname))


if __name__ == "__main__":
    main()
