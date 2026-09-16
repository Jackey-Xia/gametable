#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
identify_zh.py v2 —— 核查「已有封面里, 哪些不是/没有港服中文页的中文版图」
（只读识别: 不写 manifest、不往仓库下载任何图片；图片只缓存到 /tmp）
=================================================================================
关键修正(用户核对后):
  PS 商店同一商品有多个 role 的图: MASTER(方 1:1) / PORTRAIT_BANNER(竖 2:3) / ...
  本地封面也分两种形态: 504x504 方图(=MASTER) 与 504x756 竖版(=PORTRAIT_BANNER)
  => 必须「同形态对同 role」比较, 否则会把同一张图判成不同(旧版脚本的 bug)

判定链路(每个商品):
  A. 港服 zh-Hans 搜索匹配到官方条目 -> 取其全部 role 图
  B. 抓 en-hk 商品页 -> 取英文版全部 role 图
  C. 比 local vs 中文版同形态图 / 英文版同形态图
  D. 比 中文版 vs 英文版 同形态图 -> 判断港服是否真有「专属中文封面」

状态分类:
  OK_ZH         本地已是港服中文页的图                      -> 无需处理
  NEED_ZH_IS_EN ★港服有专属中文封面, 本地是英文版图          -> 建议换(本次核查的重点)
  NEED_ZH_OTHER ★港服有专属中文封面, 本地是其它/旧版图       -> 建议核对
  VERT_NO_ZH    本地竖版图无中文版式(竖版中英同图), 但港服方图有中文版 -> 换会改版式, 由店主决定
  NO_ZH_COVER   港服中英文封面是同一张(该商品没有专属中文封面) -> 无中文版可换
  OTHER_IMG     港服中英同图, 但本地图与官方图不同           -> 可能错图/旧图
  LOW_CONF      名称匹配置信度不足 -> 需人工确认匹配是否正确
  NO_MATCH      港服搜索没找到该商品 -> 无法判断
  ERR           出错

用法:
  python3 identify_zh.py --sample 30
  python3 identify_zh.py                     # 全量(约 10-20 分钟)
"""
import concurrent.futures as cf
import hashlib
import json
import os
import re
import sys
import time
import traceback
import urllib.parse
import urllib.request

import autocover as A
from PIL import Image

BASE = A.BASE
MANIFEST = A.MANIFEST
REPORT = os.path.join(BASE, "covers", "zh_identify_report.json")
CACHE = "/tmp/zhcov"
UA = A.UA

MIN_SCORE = 0.85
SCORE_GAP = 0.04
SAME_DIST = 6
CONCURRENCY = 6
os.makedirs(CACHE, exist_ok=True)


# ---------------- 感知哈希 ----------------
def dhash(path, size=8):
    im = Image.open(path).convert("L").resize((size + 1, size), Image.LANCZOS)
    px = list(im.getdata())
    bits = []
    for r in range(size):
        row = px[r * (size + 1):(r + 1) * (size + 1)]
        bits.extend(1 if row[c] > row[c + 1] else 0 for c in range(size))
    return bits


def dist(a, b):
    if not a or not b:
        return 99
    return sum(1 for x, y in zip(a, b) if x != y)


def aspect(path):
    w, h = Image.open(path).size
    return w / float(h)


def download(url, tag, timeout=40):
    if not url:
        return None
    req = urllib.request.Request(url + ("&" if "?" in url else "?") + "w=504",
                                 headers={"User-Agent": UA, "Referer": "https://store.playstation.com/"})
    p = os.path.join(CACHE, "%s_%s.img" % (tag, hashlib.md5(url.encode()).hexdigest()[:16]))
    if os.path.exists(p) and os.path.getsize(p) > 3000:
        return p
    for i in range(5):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = r.read()
            if len(data) < 3000:
                raise ValueError("too small")
            with open(p, "wb") as f:
                f.write(data)
            return p
        except Exception:
            if i == 4:
                return None
            time.sleep(0.8 * (i + 1))
    return None


# ---------------- 港服数据 ----------------
def search_zh(term):
    for i in range(3):
        try:
            return A.store_search(term)
        except Exception:
            if i == 2:
                raise
            time.sleep(1.2)


def zh_media(term):
    """返回 (cand, score, second, note, media{role:url})"""
    for i in range(3):
        try:
            return _zh_media_once(term)
        except Exception as ex:
            if i == 2:
                return None, 0.0, 0.0, "搜索失败:%s" % str(ex)[:60], {}
            time.sleep(1.2)


def _zh_media_once(term):
    q = urllib.parse.quote(json.dumps({
        "countryCode": "HK", "languageCode": "zh", "nextCursor": "",
        "pageOffset": 0, "pageSize": 24, "searchTerm": term,
    }, ensure_ascii=False))
    e = urllib.parse.quote(json.dumps({"persistedQuery": {"version": 1, "sha256Hash": A.SEARCH_HASH}}))
    url = "%s?operationName=getSearchResults&variables=%s&extensions=%s" % (A.SEARCH_API, q, e)
    req = urllib.request.Request(url, headers={
        "User-Agent": UA, "Accept": "application/json", "Content-Type": "application/json",
        "x-apollo-operation-name": "getSearchResults", "x-psn-store-locale-override": "zh-Hans-HK",
        "apollographql-client-name": "@sie-ppr-web-store/app", "apollographql-client-version": "0.114.0",
        "Referer": "https://store.playstation.com/", "Accept-Encoding": "identity"})
    with urllib.request.urlopen(req, timeout=30) as r:
        d = json.loads(r.read().decode("utf-8", "ignore"))
    rs = (((d.get("data") or {}).get("universalSearch") or {}).get("results")) or []
    return rs


ROMAN = {"1": "i", "2": "ii", "3": "iii", "4": "iv", "5": "v", "6": "vi",
         "7": "vii", "8": "viii", "9": "ix", "10": "x"}


def seqnum(n):
    m = re.search(r"(\d+)$", n)
    return m.group(1) if m else ""


def norm_roman(s):
    """把名称里的阿拉伯数字换成罗马数字(便于 '暗黑血统3' -> '暗黑血统iii')"""
    return re.sub(r"\d+", lambda m: ROMAN.get(m.group(0), m.group(0)), s)


R2N = {"I": "1", "II": "2", "III": "3", "IV": "4", "V": "5", "VI": "6", "VII": "7",
       "VIII": "8", "IX": "9", "X": "10", "XI": "11", "XII": "12", "XIII": "13"}
ROMAN_RE = re.compile(r"(?<![A-Za-z])(" + "|".join(sorted(R2N, key=len, reverse=True)) + r")(?![A-Za-z])")


def strip_parens(s):
    for _ in range(3):
        s2 = re.sub(r"[（(][^（）()]*[）)]", " ", s or "")
        if s2 == s:
            break
        s = s2
    return re.sub(r"\s+", " ", s).strip()


PLAT_STRIP = re.compile(r"\b(?:PS5|PS4)\s*[&＆/+・]\s*(?:PS5|PS4)\b|\bPS[45]\s*(?:版)?\b", re.I)


def norm3(s):
    t = PLAT_STRIP.sub(" ", strip_parens(s))
    t = re.sub(r"[《》〈〉]", "", t)
    return A.norm(t)


def norm_seq(s):
    """把独立出现的罗马数字序号换成阿拉伯数字再归一化
    (商店名 'Darkest Dungeon II' -> 'darkestdungeon2', 从而让'续作拒绝'规则生效)"""
    s2 = ROMAN_RE.sub(lambda m: " %s " % R2N[m.group(1)], s or "")
    return norm3(s2)


def score2(wps, cand, alts=()):
    """alts: WPS 英文名等多个评分锚点。比 autocover.score_one 更宽容:
    一方有序号一方没有时给低分(供人工核对); 但双方序号不同或子串剩余以数字开头 -> 判为不同商品"""
    best = 0.0
    for q in [wps] + [a for a in alts if a]:
        if not q:
            continue
        for nw in {norm_seq(q), norm_roman(norm_seq(q))}:
            ns = norm_seq(cand["name"])
            if not nw or not ns:
                continue
            s = 0.0
            if nw == ns:
                s = 1.0
            else:
                bw, bs = A.strip_seq(nw), A.strip_seq(ns)
                if bw and bs and bw == bs:
                    a, b = seqnum(nw), seqnum(ns)
                    if a and b and a != b:
                        s = 0.0                      # 序号不同 -> 不同商品
                    elif (a == "") != (b == ""):
                        s = 0.78                     # 一方有序号(店家用序号区分SKU) -> 低分待核
                    else:
                        s = 0.85
                elif len(nw) >= 3 and nw in ns:
                    rest = ns[ns.find(nw) + len(nw):]
                    s = 0.0 if rest[:1].isdigit() else 0.80
                elif len(ns) >= 3 and ns in nw:
                    rest = nw[nw.find(ns) + len(ns):]
                    s = 0.0 if rest[:1].isdigit() else 0.75
                elif len(ns) == 2 and (nw.startswith(ns) or nw.endswith(ns)):
                    s = 0.72      # 极短中文名(如 '艾希'): 仅当作为 WPS 名首/尾主体时接受
            if not s and len(ns) >= 6 and len(nw) >= 5:
                import difflib
                if difflib.SequenceMatcher(None, nw, ns).ratio() >= 0.82:
                    s = 0.75      # 译名差异(如 赫丘勒·白罗 vs 赫尔克里·波洛)
            if not s and len(ns) >= 4 and len(nw) >= 3:
                cn = set(ch for ch in ns if "\u4e00" <= ch <= "\u9fff")
                cw = set(ch for ch in nw if "\u4e00" <= ch <= "\u9fff")
                if cn and len(cn) >= 3 and len(cn & cw) / float(len(cn)) >= 0.9:
                    s = 0.75      # 候选名的汉字几乎都出现在 WPS 名里 -> 疑似同一款
            if s and A.has_seq(nw) and A.has_seq(ns) and seqnum(nw) == seqnum(ns):
                s += 0.05      # 只有"双方都带相同序号"才加分
            best = max(best, min(s, 1.05))
    return round(best, 3)


DLC_HINT = ("dlc", "pack", "pass", "bundle", "expansion", "追加", "扩充", "皮肤", "服装", "道具",
            "角色", "套装", "season", "kit", "set", "theme", "主题", "avatar", "头像", "currency",
            "coins", "points", "积分", "点数", "货币", "道具包", "升级")
VER_HINT = ("deluxe", "complete", "ultimate", "definitive", "remaster", "enhanced", "augmented",
            "premium", "yearone", "gold", "digital", "豪华", "完整", "终极", "决定", "重制", "重置",
            "复刻", "黄金", "数字", "季度", "年度", "收藏", "特别", "典藏")


def subtitle_of(store_name):
    """商店名里的副标题(DLC/衍生作多写成 '主名: 副标题' 或 '主名 - 副标题')"""
    m = re.search(r"[:：]\s*(.+)$", store_name) or re.search(r"\s[-–—]\s(.+)$", store_name)
    return norm3(m.group(1)) if m else ""


def is_dlc_subtitle(store_name, wps_all):
    """副标题看起来像 DLC/衍生内容, 且 WPS 名里没有 -> 视为 DLC 排除。
    副标题若只是版本词(Deluxe/Complete/豪华版...)则不排除"""
    st = subtitle_of(store_name)
    if len(st) < 3 or st in wps_all:
        return False
    if any(v in st for v in VER_HINT):
        return False
    return any(h in st for h in DLC_HINT)


def best_of2(wps, cands, alts=(), floor=0.72):
    scored = []
    nw_all = norm3(wps) + "".join(norm3(a) for a in alts)
    for c in cands:
        if not c.get("master"):
            continue
        if A.is_excluded(strip_parens(c["name"]), strip_parens(wps)):
            continue
        if is_dlc_subtitle(c["name"], nw_all):
            continue
        scored.append((score2(wps, c, alts), c))
    import difflib
    probes = [norm3(wps)] + [norm3(a) for a in alts if a]

    def rel(cand):
        ns = norm3(cand["name"])
        return max((difflib.SequenceMatcher(None, p, ns).ratio() for p in probes if p), default=0.0)

    scored.sort(key=lambda x: (-x[0], -rel(x[1])))
    if not scored or scored[0][0] < floor:
        return None, 0.0, 0.0
    bs, bc = scored[0]
    nb = A.norm(bc["name"])
    ss = 0.0
    for s2, c2 in scored[1:]:
        if A.norm(c2["name"]) != nb:
            ss = s2
            break
    return bc, bs, ss


def variants(name, en):
    """搜索词候选(按优先级): 中文原名/去版本括注 -> 英文名去括号去尾序号 -> 分段/主干 -> 括注/英文原样"""
    out, seen = [], set()
    STOP = ("完整版", "豪华版", "数字版", "中文版", "英文版", "标准版", "终极版", "普通版", "年度版",
            "季票", "DLC", "增强版", "决定版", "重制版", "重置版", "复刻版", "导演剪辑版", "周年纪念版",
            "周年版", "纪念版", "特别版", "限定版", "收藏版", "体验版", "试玩版", "序章", "合集")

    def add(s):
        s = re.sub(r"\s+", " ", (s or "").strip())
        if s in STOP:
            return
        if s and len(s) >= 2 and s not in seen:
            seen.add(s)
            out.append(s)

    add(name)
    add(re.sub(r"[（(]\s*(?:PS4|PS5|PSV|PSVR2?|NS|Switch|豪华版|完整版|中文版|英文版|决定版|重制版|重置版)\s*[）)]", "", name))
    # 英文名: 去掉括注 + 去掉结尾序号
    if en:
        e = re.sub(r"[（(][^）)]*[）)]", " ", en)
        e = re.sub(r"\s+", " ", e).strip(" -—:：")
        add(e)
        add(re.sub(r"\s*\d+$", "", e))
        add(re.sub(r"\s*(?:the\s+)?(?:complete|deluxe|ultimate|definitive|remastered|enhanced|augmented|premium|year\s*one)\s*(?:edition)?$",
                   "", e, flags=re.I))
    add(re.sub(r"[（(][^）)]*[）)]", "", name).strip())
    for part in re.split(r"[/／|｜]", name):
        add(part)
    add(re.split(r"[:：\-—]", name)[0])
    for mm in re.findall(r"[（(]([^）)]+)[）)]", name):
        add(mm)
    add(en)
    for mm in re.findall(r"[A-Za-z0-9][A-Za-z0-9 :'\-\.]{2,}", name):
        add(re.sub(r"\s*\d+$", "", mm.strip()))
    add(re.sub(r"\d+", lambda m: ROMAN.get(m.group(0), m.group(0)), name))
    add(A.strip_seq(A.norm(name)))
    return out[:10]


def match_and_media(name, en):
    """名称匹配 + 取该条目全部 media。
    策略: 按变体逐个搜索; 中文轮出现"高分且唯一"即采信; 否则记录全局最佳(标记低置信)。"""
    queries = variants(name, en)
    en_anchor = strip_parens(en) if en else ""
    anchors = [en_anchor]
    if en_anchor:
        anchors.append(re.sub(r"[\u2019']s\b", "", en_anchor))
        anchors.append(re.sub(r"\s*(?:the\s+)?(?:complete|deluxe|ultimate|definitive|remastered|enhanced|augmented|premium)\s*(?:edition)?\s*$", "", en_anchor, flags=re.I))
        pass  # 不剥英文锚点序号, 保留续作区分能力
    anchors = [a for i, a in enumerate(anchors) if a and a not in anchors[:i]]
    rb = None            # 采信结果 (cand, score, second)
    best_media = {}
    weak = None          # 低置信兜底
    weak_media = {}
    for q in queries[:5]:
        try:
            rs = zh_media(q)
        except Exception as ex:
            return None, 0.0, 0.0, "搜索失败:%s" % str(ex)[:60], {}
        cands = []
        medmap = {}
        for r in rs:
            if r.get("__typename") != "Product":
                continue
            mm = {}
            for m in r.get("media") or []:
                if m.get("type") == "IMAGE":
                    mm.setdefault(m.get("role"), m.get("url"))
            if not mm.get("MASTER"):
                continue
            c = {"id": r.get("id"), "name": r.get("name"), "master": mm["MASTER"]}
            cands.append(c)
            medmap[c["id"]] = mm
        c, s, ss = best_of2(name, cands, anchors)
        if c is None:
            continue
        if s > (weak[1] if weak else 0):
            weak = (c, s, ss)
            weak_media = medmap[c["id"]]
        # 高分且与第二名拉开 -> 直接采信
        if s >= MIN_SCORE and (s - ss) >= SCORE_GAP:
            rb = (c, s, ss)
            best_media = medmap[c["id"]]
            break
    if rb is not None:
        return rb[0], rb[1], rb[2], "", best_media
    if weak is not None:
        return weak[0], weak[1], weak[2], "低置信(--> %s)" % weak[0]["name"][:40], weak_media
    return None, 0.0, 0.0, "无候选", {}


def page_media(product_id, locale):
    """抓商品页, 解析全部 role 图"""
    url = "https://store.playstation.com/%s/product/%s" % (locale, product_id)
    req = urllib.request.Request(url, headers={
        "User-Agent": UA, "Accept-Language": "en" if locale.startswith("en") else "zh-CN"})
    for i in range(3):
        try:
            with urllib.request.urlopen(req, timeout=35) as r:
                html = r.read().decode("utf-8", "ignore")
            out = {}
            for pat in (r'"role":"([A-Z_0-9]+)","type":"IMAGE","url":"(.*?)"',
                        r'"type":"IMAGE","role":"([A-Z_0-9]+)","url":"(.*?)"'):
                for m in re.finditer(pat, html):
                    out.setdefault(m.group(1), m.group(2))
            return out
        except Exception:
            if i == 2:
                return {}
            time.sleep(1.5)
    return {}


# ---------------- 单商品核查 ----------------
def _work(item):
    name, en, old_rel = item
    r = {"name": name, "en": en, "old": old_rel, "status": "ERR", "score": 0.0,
         "second": 0.0, "storeName": "", "product": "",
         "zhM": "", "enM": "", "zhP": "", "enP": "",
         "shLocal": "", "shZh": "", "shEn": "",
         "dLocalZh": 99, "dLocalEn": 99, "dZhEn": 99, "note": ""}
    try:
        c, s, ss, note, zmed = match_and_media(name, en)
        r["score"], r["second"], r["note"] = s, ss, note
        if c is None:
            r["status"] = "NO_MATCH" if "无候选" in note or "歧义" in note else "ERR"
            return r
        r["storeName"], r["product"] = c["name"], c["id"]
        # 匹配置信度不足时仍继续比对, 但状态加 LOWCONF_ 前缀(报告里单列, 由店主一眼核对)
        low = s < MIN_SCORE or (s - ss) < SCORE_GAP
        r["low"] = low
        if low:
            r["note"] = (r["note"] or "") + " 匹配待确认(%.2f vs %.2f)" % (s, ss)
        old_abs = os.path.join(BASE, old_rel)
        if not os.path.exists(old_abs):
            r["status"] = "ERR"
            r["note"] = "本地文件缺失"
            return r

        ar = aspect(old_abs)
        r["shLocal"] = "P" if ar < 0.85 else "M"

        if r["shLocal"] == "P" and not zmed.get("PORTRAIT_BANNER"):
            # 搜索结果没带竖版(2:3)图 -> 用中文商品页补全
            zpage = page_media(c["id"], "zh-hans-hk")
            for k2, v2 in zpage.items():
                zmed.setdefault(k2, v2)
        emed = page_media(c["id"], "en-hk")
        r["zhM"] = zmed.get("MASTER", "")
        r["zhP"] = zmed.get("PORTRAIT_BANNER", "")
        r["enM"] = emed.get("MASTER", "")
        r["enP"] = emed.get("PORTRAIT_BANNER", "")
        r["shZh"] = "P" if (r["zhP"] and not r["zhM"]) else "M"
        r["shEn"] = "P" if (r["enP"] and not r["enM"]) else "M"

        # 本地图形态对应的 role
        zurl = r["zhP"] if r["shLocal"] == "P" else r["zhM"]
        eurl = r["enP"] if r["shLocal"] == "P" else r["enM"]
        zp = download(zurl, "zh" + r["shLocal"])
        ep = download(eurl, "en" + r["shLocal"])
        lp = old_abs
        if not zp:
            r["status"] = "ERR"
            r["note"] = "中文版图下载失败"
            return r
        r["dLocalZh"] = dist(dhash(lp), dhash(zp))
        if ep:
            r["dLocalEn"] = dist(dhash(lp), dhash(ep))
        # 中英文同形态图是否有差异(是否存在专属中文封面)
        zM = download(r["zhM"], "zhM") if r["zhM"] else None
        eM = download(r["enM"], "enM") if r["enM"] else None
        if zM and eM:
            r["dZhEn"] = dist(dhash(zM), dhash(eM))
        zP = download(r["zhP"], "zhP") if r["zhP"] else None
        eP = download(r["enP"], "enP") if r["enP"] else None
        r["dZhEnP"] = dist(dhash(zP), dhash(eP)) if (zP and eP) else 99
        S = r["shLocal"]
        d_lz, d_le = r["dLocalZh"], r["dLocalEn"]
        d_ze = r["dZhEnP"] if S == "P" else r["dZhEn"]      # 本地形态下: 中文版 vs 英文版 是否同一张

        if d_lz >= 90:
            r["status"] = "ERR"
            r["note"] = "该商品在港服没有对应形态的官方图(本地为%s)" % ("竖版" if S == "P" else "方图")
            return r

        if d_ze <= SAME_DIST:
            # 该形态下 港服中英文封面本同一张 -> 不存在"专属中文封面"
            if d_lz <= SAME_DIST:
                r["status"] = "OK_ZH"
            else:
                r["status"] = "OTHER_IMG"
                r["note"] = "港服中英文封面同一张(无中文版差异), 但本地图与官方不同"
            if S == "P" and r["dZhEn"] > SAME_DIST:
                r["note"] = (r["note"] + " | 港服【方图】有中文版, 如需中文封面可改版式").strip(" |")
            return r

        # 港服确有专属中文封面
        if d_lz <= SAME_DIST:
            r["status"] = "OK_ZH"
        elif d_le <= 10 and (d_lz - d_le) >= 8:
            r["status"] = "NEED_ZH_IS_EN"      # 本地图确实就是港服英文版 -> 明确可换
        elif d_le <= 6:
            r["status"] = "NEED_ZH_IS_EN"
        else:
            # 本地图与中/英版都不像(旧版或非官方图), 但港服确有中文版
            r["status"] = "NEED_ZH_OTHER"
            r["note"] = (r["note"] + " 与官方中/英版图都不一致").strip()
        return r
    except Exception as ex:
        r["status"] = "ERR"
        r["note"] = str(ex)[:150]
        return r


def work(item):
    r = _work(item)
    if r.get("low") and r["status"] not in ("NO_MATCH", "ERR"):
        r["status"] = "LOWCONF_" + r["status"]
    return r


def main():
    sample = int(sys.argv[sys.argv.index("--sample") + 1]) if "--sample" in sys.argv else 0
    if "--concurrency" in sys.argv:
        globals()["CONCURRENCY"] = int(sys.argv[sys.argv.index("--concurrency") + 1])

    g = A.load_json(A.GRID, {})
    names, enmap, seen = [], {}, set()
    for row in (g.get("rows") or [])[1:]:
        if not row or len(row) < 3 or row[2] is None:
            continue
        v = str(row[2]).strip()
        if not v or v in ("中文", "商品名称"):
            continue
        if len(row) > 3 and row[3]:
            enmap.setdefault(v, str(row[3]).strip())
        if v not in seen:
            seen.add(v)
            names.append(v)
    m = A.load_json(MANIFEST, {})
    items = [(n, enmap.get(n, ""), m[n]) for n in names if n in m]
    total = len(items)
    if sample:
        items = items[:sample]

    print("有封面商品 %d%s | 并发 %d" % (total, " (样本 %d)" % sample if sample else "", CONCURRENCY))
    t0 = time.time()
    res = []
    with cf.ThreadPoolExecutor(max_workers=CONCURRENCY) as ex:
        for i, r in enumerate(ex.map(work, items), 1):
            res.append(r)
            if i % 25 == 0 or i == len(items):
                from collections import Counter
                c = Counter(x["status"] for x in res)
                print("  %d/%d (%.0fs) %s" % (i, len(items), time.time() - t0,
                                              {k: c[k] for k in ("OK_ZH", "NEED_ZH_IS_EN", "NEED_ZH_OTHER",
                                                                 "VERT_NO_ZH", "NO_ZH_COVER", "OTHER_IMG",
                                                                 "LOW_CONF", "NO_MATCH") if c[k]}))

    json.dump({"time": time.strftime("%Y-%m-%dT%H:%M:%S"), "items": res,
               "stats": {"scanned": len(res), "total": total}},
              open(REPORT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    from collections import Counter
    c = Counter(r["status"] for r in res)
    labels = {
        "OK_ZH": "已是港服中文页图(无需处理)",
        "NEED_ZH_IS_EN": "★港服有专属中文封面, 本地是英文版图(建议换)",
        "NEED_ZH_OTHER": "★港服有专属中文封面, 本地是其它/旧版图(建议核对)",
        "VERT_NO_ZH": "本地竖版无中文版式; 港服方图有中文版(换会改版式)",
        "NO_ZH_COVER": "港服中英文封面本就同一张(无中文版可换)",
        "OTHER_IMG": "本地图与港服官方图不同(可能错图/旧图)",
        "LOW_CONF": "名称匹配置信度不足(需人工确认)",
        "NO_MATCH": "港服未匹配到条目(无法判断)",
        "ERR": "出错",
    }
    print("\n耗时 %.0fs" % (time.time() - t0))
    for k, v in c.most_common():
        print("  %-16s %4d  %s" % (k, v, labels.get(k, "")))
    print("报告 ->", REPORT)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
    sys.exit(0)
