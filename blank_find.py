#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""blank_find.py —— 任务2：留白商品按优先级找图。

优先级（任一步命中即停）：
  ① 港服商店搜「中文名 or 英文名」(zh-Hans-HK)
  ② 美服商店搜「英文名」(en-US)
  ③ 游民星空 APP 主预览图
  ④ （网上找图 —— 由主会话另行处理）

只写 /tmp：/tmp/blank_state.json + /tmp/blank_orig/{i}.jpg
"""
import json, os, re, sys, threading, urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed

REPO = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, REPO)
import autocover as AC
import cover_policy as CP
import en_rescan as ER
import gamersky_cover as GK

OUTDIR = "/tmp/blank_orig"
os.makedirs(OUTDIR, exist_ok=True)
STATE = "/tmp/blank_state.json"
LOCK = threading.Lock()

LANG = re.compile(r"[(（][^)）]*[)）]")

# 人工覆盖: 自动匹配指错时指定正确条目 (step, locale, country, lang, 商城条目名)
OVERRIDE = {
    "圣歌Anthem（黎明军团版）": ("②美服", "en-US", "US", "en", "Anthem"),
}


def aliases_zh(name):
    """中文名 -> 检索词列表（拆 / 别名、去版本括注、去库存序号）"""
    out = []
    for part in re.split(r"[/＋+]", name):
        t = part.strip()
        if not t:
            continue
        t = AC.strip_seq(AC.strip_ed(t))
        t = re.sub(r"\s+", " ", t).strip()
        if t and t not in out:
            out.append(t)
    return out or [name]


def aliases_en(en):
    if not en:
        return []
    out = []
    for part in re.split(r"[/／]", en):
        t = part.strip()
        t = re.sub(r"[(（][^)）]*[)）]", "", t).strip()
        t = re.sub(r"^[Ww][Ii][Tt][Hh]\s+", "", t)
        if t and t not in out:
            out.append(t)
    return out


def seq_of(n):
    """提取尾部作品序号：先剥掉尾部括注（版本/库存号），再看裸数字结尾"""
    if not n:
        return None
    t = n.strip()
    while True:
        t2 = re.sub(r"[(（][^()（）]*[)）]\s*$", "", t).strip()
        if t2 == t or not t2:
            break
        t = t2
    m = re.match(r"^(.*?)(\d+)$", t)
    if m and m[1] and not re.search(r"[0-9+\-×xX/／&·.。、]$", m[1]):
        return int(m.group(2))
    return None


def seq_bad(wps, cand):
    """wps 带作品序号且候选名带不同序号 -> 明显错配"""
    a, b = seq_of(wps), seq_of(cand or "")
    return a is not None and b is not None and a != b


def pick_media_url(c):
    role, url = CP.pick_role(c.get("media") or [{"role": "MASTER", "url": c.get("master")},
                                                {"role": "PORTRAIT_BANNER", "url": c.get("portrait")}])
    return role, url


DLC_RE = re.compile(
    r"点数|季票|season\s*pass|dlc|upgrade|升级|currency|credits|coins|points|"
    r"subscription|定期服务|soundtrack|原声带|demo|trial|theme|主题|avatar|头像|"
    r"预购|preorder|试玩|体验版|序章|物品|道具|服装|survival\s*pack|starter\s*pack|"
    r"supporter|豪华升级|deluxe\s*upgrade|扩展包|extension|expansion|outfit|skin|costume", re.I)
PACK_RE = re.compile(r"\bpack\b|bundle|捆绑|合集包", re.I)


def bad_cand(c, wps, alt):
    """DLC/噪声候选过滤; 商品名本身是合辑(+号/合辑词)时不排除 pack/bundle 类"""
    nm = c.get("name") or ""
    if DLC_RE.search(nm):
        return True
    if PACK_RE.search(nm) and not (
            PACK_RE.search(wps) or PACK_RE.search(alt or "")
            or "+" in wps or "＋" in wps or "合辑" in wps or "合集" in wps):
        return True
    return False


def try_store(term, wps, alt="", locale="zh-Hans-HK", country="HK", lang="zh", min_score=0.72):
    """PS 商店搜索 + 打分 + 序号/DLC 校验, 返回 (cand, score) 或 (None, 0)"""
    if not term:
        return None, 0.0
    try:
        if locale == "zh-Hans-HK":
            cands = AC.store_search(term)
        else:
            cands = ER.search_en(term, locale=locale, country=country, lang=lang)
    except Exception:
        return None, 0.0
    best, bs = None, 0.0
    for c in cands:
        if seq_bad(wps, c.get("name") or "") or seq_bad(alt, c.get("name") or ""):
            continue
        if bad_cand(c, wps, alt):
            continue
        s = max(AC.score_one(wps, c, False), AC.score_one(alt, c, False) if alt else 0.0)
        if s > bs:
            best, bs = c, s
    if best and bs >= min_score:
        return best, bs
    return None, 0.0


def find(i, rep, en, cur_cover):
    rec = {"i": i, "rep": rep, "en": en, "step": None}
    zh_terms = aliases_zh(rep)
    en_terms = aliases_en(en)
    alt = en_terms[0] if en_terms else ""

    # ⓪ 人工覆盖: 已知自动匹配会指错的, 直接指定服区+条目名
    ov = OVERRIDE.get(rep)
    if ov:
        step, locale, country, lang, term = ov
        c, s = try_store(term, rep, "", locale=locale, country=country, lang=lang, min_score=0.0)
        if c:
            return finish(rec, i, c, step + "(指定)", 1.0)
        rec["step"] = "未找到(覆盖条目未命中)"
        return rec

    # ① 港服: 中文名 -> 英文名
    for t in zh_terms:
        c, s = try_store(t, rep, alt)
        if c:
            return finish(rec, i, c, "①港服(中文名)", s)
    if alt:
        for t in [alt] + en_terms[1:]:
            c, s = try_store(t, alt, rep, locale="zh-Hans-HK", country="HK", lang="zh", min_score=0.8)
            if c:
                return finish(rec, i, c, "①港服(英文名)", s)

    # ② 美服: 英文名
    if alt:
        for t in en_terms:
            c, s = try_store(t, alt, rep, locale="en-US", country="US", lang="en", min_score=0.72)
            if c:
                return finish(rec, i, c, "②美服(英文名)", s)

    # ③ 游民星空
    for t in zh_terms:
        try:
            it = GK.fetch(rep, term=t)
        except Exception:
            it = None
        if it and it.get("url") and it.get("score", 0) >= 0.9 \
                and not seq_bad(rep, it.get("storeName") or "") and not seq_bad(rep, it.get("slug") or ""):
            p = os.path.join(OUTDIR, "%04d.jpg" % i)
            try:
                GK.download({"url": it["url"]}, p)
                from PIL import Image
                im = Image.open(p); im.load()
                rec.update({"step": "③游民星空", "url": it["url"], "cand": it.get("storeName", ""),
                            "role": "GAMERSKY", "size": list(im.size)})
                print("  #%d %s -> ③游民星空 %s" % (i, rep_s(rep), it.get("storeName", "")))
                return rec
            except Exception:
                pass

    # ④ 网上找图(第一档): 其它官方服区 —— 日服/欧服/韩服, 都是官方原版图
    for label, loc, ctry, lg, term in (
            ("④日服", "ja-JP", "JP", "ja", alt or rep),
            ("④欧服", "en-GB", "GB", "en", alt),
            ("④韩服", "ko-KR", "KR", "ko", alt),
    ):
        if not term:
            continue
        c, s = try_store(term, alt or rep, rep, locale=loc, country=ctry, lang=lg, min_score=0.75)
        if c:
            return finish(rec, i, c, label, s)

    rec["step"] = "未找到"
    print("  #%d %s -> 未找到" % (i, rep_s(rep)))
    return rec


def finish(rec, i, c, step, score):
    role, url = pick_media_url(c)
    if not url:
        rec["step"] = "未找到"
        return rec
    p = os.path.join(OUTDIR, "%04d.jpg" % i)
    try:
        AC.http_download(url, p)
        from PIL import Image
        im = Image.open(p); im.load()
    except Exception:
        rec["step"] = "未找到"
        return rec
    rec.update({"step": step, "url": url, "cand": c.get("name", ""), "role": role,
                "score": round(score, 2), "size": list(im.size)})
    print("  #%d %s -> %s 分%.2f %s" % (i, rep_s(rec["rep"]), step, score, (c.get("name") or "")[:30]))
    return rec


def rep_s(s):
    return s[:24]


def main():
    grid = json.load(open(os.path.join(REPO, "data/ps_grid.json"), encoding="utf-8"))
    man = CP.load_manifest()
    sk = json.load(open(os.path.join(REPO, "covers/auto_skip.json"), encoding="utf-8"))
    rows = (grid.get("rows") or [])[2:]
    names, EN = [], {}
    for r in rows:
        if r and len(r) > 2 and r[2] and str(r[2]).strip():
            n = str(r[2]).strip()
            if n not in EN:
                EN[n] = str(r[3] or "").strip()
            names.append(n)
    miss = sorted({n for n in names if not man.get(n)})
    print("留白商品 %d 个" % len(miss))

    state = json.load(open(STATE, encoding="utf-8")) if os.path.exists(STATE) else {}
    todo = [n for n in miss if n not in state or state[n].get("step") in (None, "未找到")]
    print("本轮处理 %d 个" % len(todo))
    results = {}
    with ThreadPoolExecutor(max_workers=6) as ex:
        futs = {ex.submit(find, k + 1, n, EN.get(n, ""), man.get(n)): n for k, n in enumerate(todo)}
        for f in as_completed(futs):
            rec = f.result()
            results[rec["rep"]] = rec
    state.update(results)
    json.dump(state, open(STATE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    ok = sum(1 for v in state.values() if v.get("step") not in (None, "未找到"))
    print("累计命中 %d / %d" % (ok, len(state)))


if __name__ == "__main__":
    main()
