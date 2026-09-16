#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
recover_all.py —— 已有封面商品「全量重抓港服 zh-Hans 中文版官方主图」
=====================================================================
背景: 早期批次抓图走英文页, 拿到的是英文 Logo 版主图; 港服 zh-Hans 页/接口才是中文版。
     本脚本对当前所有「已有封面的商品」重新走港服中文接口抓一遍 MASTER 主图并替换。

用法:
  python3 recover_all.py --dry --sample 30     # 试跑 30 个, 只看匹配结果不落盘
  python3 recover_all.py                       # 全量重抓并替换
  python3 recover_all.py --concurrency 8       # 指定并发

安全设计:
  - 只有「高分 + 与第二名拉开的唯一匹配」才替换 (比自动管线更严: MIN_SCORE=0.85)
  - 歧义/无命中/下载失败 -> 保留原图不动, 记入 pending 供人工核对
  - 新图与旧图字节完全相同 -> 丢弃新文件, 保持原状 (无意义 churn)
  - 换图必换名 (rc{hash}.jpg), 防 CDN 缓存旧图
  - 绝不修改 data/ 下任何文件
"""
import concurrent.futures as cf
import hashlib
import json
import os
import sys
import time
import traceback

import autocover as A
import cover_policy as CP

BASE = A.BASE
COVERS = os.path.join(BASE, "covers")
MANIFEST = A.MANIFEST
REPORT = os.path.join(COVERS, "recover_report.json")

MIN_SCORE = 0.85      # 比自动管线(0.80)更严, 避免把已有正确封面换错
SCORE_GAP = 0.04
CONCURRENCY = 6
RETRY = 2


def load_grid():
    """返回 (真名列表, 真名->英文名)"""
    g = A.load_json(A.GRID, {})
    names, seen, enmap = [], set(), {}
    for r in (g.get("rows") or [])[1:]:
        if not r or len(r) < 3 or r[2] is None:
            continue
        v = str(r[2]).strip()
        if not v or v in ("中文", "商品名称"):
            continue
        e = str(r[3]).strip() if len(r) > 3 and r[3] else ""
        if v not in seen:
            seen.add(v)
            names.append(v)
        if e and v not in enmap:
            enmap[v] = e
    return names, enmap


def search_with_retry(term):
    last = None
    for _ in range(RETRY + 1):
        try:
            return A.store_search(term)
        except Exception as ex:
            last = ex
            time.sleep(1.2)
    raise last


def pick(name, en):
    """返回 (cand, score, second, note) —— 两轮搜索(中文名/英文名)取最优, 冲突则放弃"""
    queries, seenq = [], set()
    for q in [name, en, A.strip_seq(A.norm(name))]:
        if q and q not in seenq:
            seenq.add(q)
            queries.append(q)
    rb = None
    for q in queries[:2]:
        try:
            cands = search_with_retry(q)
        except Exception as ex:
            return None, 0.0, 0.0, "搜索失败: %s" % str(ex)[:80]
        alt = "" if q == name else q
        c, s, ss = A.best_of(name, cands, alt)
        if c is None:
            continue
        if rb is not None and rb[1] >= MIN_SCORE and c["id"] != rb[0]["id"] and abs(s - rb[1]) < SCORE_GAP:
            return None, min(s, rb[1]), 0.0, "两轮歧义(中/英命中不同商品)"
        if rb is None or s > rb[1]:
            rb = (c, s, ss)
    if rb is None:
        return None, 0.0, 0.0, "无候选"
    return rb[0], rb[1], rb[2], ""


def md5file(p):
    with open(p, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


def work(item):
    name, en, old_rel = item
    out = {"name": name, "en": en, "old": old_rel, "status": "", "score": 0.0,
           "second": 0.0, "storeName": "", "product": "", "new": "", "note": ""}
    try:
        c, s, ss, note = pick(name, en)
        out["score"], out["second"], out["note"] = s, ss, note
        if c is None:
            out["status"] = "KEEP"
            return out
        out["storeName"], out["product"] = c["name"], c["id"]
        if s < MIN_SCORE or (s - ss) < SCORE_GAP:
            out["status"] = "KEEP"
            out["note"] = note or ("分不足/有歧义 %.2f vs %.2f" % (s, ss))
            return out
        new_rel = "covers/rc%s.jpg" % hashlib.md5(name.encode()).hexdigest()[:12]
        new_abs = os.path.join(BASE, new_rel)
        # ★ 形态优先级: 竖版 PORTRAIT_BANNER > 方图 MASTER（与 autocover 一致）
        role, url = CP.pick_role(c.get("media") or [
            {"role": "MASTER", "url": c.get("master")},
            {"role": "PORTRAIT_BANNER", "url": c.get("portrait")},
        ])
        if not url:
            out["status"] = "KEEP"
            out["note"] = "港服无可用形态图"
            return out
        out["role"] = CP.ROLE_CODE.get(role, "")
        try:
            A.http_download(url, new_abs)
        except Exception as ex:
            out["status"] = "KEEP"
            out["note"] = "下载失败: %s" % str(ex)[:80]
            return out
        old_abs = os.path.join(BASE, old_rel)
        if os.path.exists(old_abs) and md5file(old_abs) == md5file(new_abs):
            os.remove(new_abs)          # 与旧图完全一致 -> 无需更换
            out["status"] = "SAME"
            return out
        out["status"] = "REPLACE"
        out["new"] = new_rel
        return out
    except Exception as ex:
        out["status"] = "KEEP"
        out["note"] = "异常: %s" % str(ex)[:120]
        return out


def main():
    dry = "--dry" in sys.argv
    sample = 0
    if "--sample" in sys.argv:
        sample = int(sys.argv[sys.argv.index("--sample") + 1])
    if "--concurrency" in sys.argv:
        globals()["CONCURRENCY"] = int(sys.argv[sys.argv.index("--concurrency") + 1])

    names, enmap = load_grid()
    m = A.load_json(MANIFEST, {})
    # ★ 人工封面保护: 默认跳过 cover_sources.json 里 source=manual 的封面
    #   只有店主明确要求全量重抓时加 --include-manual（此时视同人工授权, 仍以 manual 身份写入）
    include_manual = "--include-manual" in sys.argv
    if include_manual:
        print("!! 已加 --include-manual: 人工封面也会被重抓(等同店主重新授权)")
    _src = CP.load_sources()
    protected = {n for n, v in _src.items() if v.get("source") == CP.SRC_MANUAL and not include_manual}
    # 目标 = 表内真名 且 manifest 里已有封面 且非人工封面
    items = [(n, enmap.get(n, ""), m[n]) for n in names if n in m and n not in protected]
    globals()["SRC_ATTR"] = CP.SRC_MANUAL if include_manual else CP.SRC_STORE_ZH_HK
    # manifest 中不在表内的键 = 失效键(改名), 尝试按英文名/剥序号仍无法映射 -> 报告
    dead = [k for k in m if k not in set(names)]
    if sample:
        items = items[:sample]

    print("表内真名 %d | manifest %d | 待重抓 %d | 失效键 %d | dry=%s 并发=%d"
          % (len(names), len(m), len(items), len(dead), dry, CONCURRENCY))
    t0 = time.time()
    results = []
    with cf.ThreadPoolExecutor(max_workers=CONCURRENCY) as ex:
        for i, r in enumerate(ex.map(work, items), 1):
            results.append(r)
            if i % 25 == 0 or i == len(items):
                rep = sum(1 for x in results if x["status"] == "REPLACE")
                same = sum(1 for x in results if x["status"] == "SAME")
                keep = sum(1 for x in results if x["status"] == "KEEP")
                print("  %d/%d  替换%d 相同%d 保留%d  (%.0fs)"
                      % (i, len(items), rep, same, keep, time.time() - t0))
    print("耗时 %.0fs" % (time.time() - t0))

    rep = [r for r in results if r["status"] == "REPLACE"]
    same = [r for r in results if r["status"] == "SAME"]
    keep = [r for r in results if r["status"] == "KEEP"]

    if not dry:
        for r in rep:
            old_abs = os.path.join(BASE, r["old"])
            # ★ 人工封面保护: cover_policy 会拒绝任何非 manual 的覆盖
            ok, msg = CP.set_cover(r["name"], r["new"], globals().get("SRC_ATTR", CP.SRC_STORE_ZH_HK),
                                   r.get("role", ""), r.get("storeName", ""),
                                   "recover_all 全量重抓 · 港服中文页")
            if not ok:
                print("  GUARD %s -> %s" % (r["name"], msg[:80]))
                if os.path.exists(os.path.join(BASE, r["new"])):
                    os.remove(os.path.join(BASE, r["new"]))
                continue
            m[r["name"]] = r["new"]
            if os.path.exists(old_abs) and old_abs not in {v for v in m.values()}:
                os.remove(old_abs)
        json.dump(m, open(MANIFEST, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    else:
        for r in rep:
            p = os.path.join(BASE, r["new"])
            if os.path.exists(p):
                os.remove(p)

    out = {
        "time": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "dry": dry,
        "scanned": len(results),
        "replaced": rep, "identical": [r["name"] for r in same], "kept": keep,
        "dead_keys": dead,
        "stats": {"replaced": len(rep), "same": len(same), "keep": len(keep),
                  "manifest": len(m), "seconds": int(time.time() - t0)},
    }
    json.dump(out, open(REPORT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    print("\n=== 结果 ===")
    print("替换 %d | 图完全相同 %d | 保留原图 %d | 失效键 %d" % (len(rep), len(same), len(keep), len(dead)))
    print("明细 -> covers/recover_report.json")
    if keep:
        print("\n保留原图的(需人工核对, 前20):")
        for r in keep[:20]:
            print("  %-34s %s" % (r["name"][:34], (r["note"] or "")[:60]))
    if rep:
        print("\n已替换样本(前15):")
        for r in rep[:15]:
            print("  %-30s -> %s (%.2f)" % (r["name"][:30], r["storeName"][:34], r["score"]))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
    sys.exit(0)
