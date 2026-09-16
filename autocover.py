#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
autocover.py —— 新商品封面自动抓取（港服 PS Store · zh-Hans 中文版主图）
================================================================
触发时机: deploy.yml 在每次构建前运行（AirScript 每小时推新数据 -> 自动发现新商品 -> 抓图 -> 提交 -> 部署）

流程:
  1. 读 data/ps_grid.json 的真实商品名（rows 第3列, 索引2）
  2. 已有封面(manifest 键) / 有意无封面(auto_skip) / 多次失败(auto_state) 的名字直接跳过
  3. 其余 = 新商品 -> 用 PS Store 搜索 API (getSearchResults persisted query) 搜港服 zh-Hans
  4. 严格评分匹配, 唯一最高分才自动入库; 有歧义 -> 记入 pending 交店主人工核对
  5. 下载 zh-Hans MASTER 官方主图(504x504, 中文版封面) -> covers/ac{md5}.jpg -> 更新 manifest
  6. 报告写 covers/autocover_report.json

安全红线（务必遵守）:
  - 只新增键, 绝不覆盖/删除已有 manifest 键
  - 绝不修改 data/ 下任何文件
  - 任何异常都不抛出(exit 0), 不阻断部署
"""
import hashlib
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
GRID = os.path.join(BASE, "data", "ps_grid.json")
MANIFEST = os.path.join(BASE, "covers", "manifest.json")
SKIP = os.path.join(BASE, "covers", "auto_skip.json")
STATE = os.path.join(BASE, "covers", "auto_state.json")
REPORT = os.path.join(BASE, "covers", "autocover_report.json")

SEARCH_API = "https://web.np.playstation.com/api/graphql/v1//op"
SEARCH_HASH = "4df6284f982e57bec70f23c77e2c219dc792eb19af7fb3d3a81767aa3f1958aa"  # getSearchResults persisted query (若 PS 改版失效需重新提取)
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"

MAX_TARGETS = 5        # 单次运行最多自动入库数
MAX_ATTEMPTS = 6       # 同名累计失败次数上限(之后进 pending 不再自动试)
MIN_SCORE = 0.80       # 自动入库最低分
SCORE_GAP = 0.04       # 与第二名最小分差(防歧义)

# DLC/噪声排除词(归一化后子串匹配; 命中则剔除候选) —— 持续维护
EXCLUDE = [
    "demo", "trial", "theme", "主题", "avatar", "seasonpass", "dlc",
    "upgrade", "升级", "pack", "bundle", "扩充", "物品", "道具", "服装",
    "立绘", "poster", "海报", "glasses", "headgear", "backpack",
    "sunglass", "preorder", "预购", "点数", "coins", "points", "credits",
    "currency", "subscription", "定期服务", "soundtrack", "原声带",
    "试玩版", "试玩", "体验版", "序章", "捆绑包", "合集包",
]

UA_STRIP = re.compile(r"[（(]\s*(?:PS4|PS5|PSVR|PSVR2|港版英文|美版英文|日版英文|中英文版|英文版|中文版|日文版|韩文版)\s*[）)]", re.I)


def norm(s):
    """归一化: 全角->半角, 去空白与标点, 小写"""
    if not s:
        return ""
    s = s.replace("（", "(").replace("）", ")")
    s = UA_STRIP.sub("", s)  # 先剥平台/版本括注(名称尾部常有, 港服名也带)
    out = []
    for ch in s:
        o = ord(ch)
        if 0xFF01 <= o <= 0xFF5E:  # 全角区
            ch = chr(o - 0xFEE0)
        if ch.isspace() or ch in "，,.。…?!？!·・:：;；'’‘\"“”~～-—_+=*/\\|<>「」『』()[]【】™®©":
            continue
        out.append(ch.lower())
    return "".join(out)


def strip_seq(n):
    """剥尾部序号: （1）/(1)/裸数字"""
    n = re.sub(r"[（(]\d+[）)]$", "", n)
    n = re.sub(r"\d+$", "", n)
    return n


def has_seq(n):
    return bool(re.search(r"[（(]\d+[）)]$|\d+$", n))


def is_excluded(store_name, wps_name=""):
    ns = norm(store_name)
    nw = norm(wps_name)
    for w in EXCLUDE:
        wn = norm(w)
        if wn and wn in ns and wn not in nw:
            return True
    return False


def http_json(url, timeout=25):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "application/json",
        "Content-Type": "application/json",
        "x-apollo-operation-name": "getSearchResults",
        "x-psn-store-locale-override": "zh-Hans-HK",
        "apollographql-client-name": "@sie-ppr-web-store/app",
        "apollographql-client-version": "0.114.0",
        "Referer": "https://store.playstation.com/",
        "Accept-Encoding": "identity",
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "ignore"))


def http_download(url, path, timeout=40):
    req = urllib.request.Request(url + ("&" if "?" in url else "?") + "w=480",
                                 headers={"User-Agent": UA, "Referer": "https://store.playstation.com/"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read()
    if len(data) < 3000:
        raise ValueError("image too small: %d bytes" % len(data))
    if not (data[:3] == b"\xff\xd8\xff" or data[:8] == b"\x89PNG\r\n\x1a\n"):
        raise ValueError("not an image")
    with open(path, "wb") as f:
        f.write(data)
    return len(data)


def store_search(term):
    """港服 zh-Hans 搜索, 返回 [ {id,name,platforms,master_url} ] (仅 Product 类型)"""
    if not term or not term.strip():
        return []
    q = urllib.parse.quote(json.dumps({
        "countryCode": "HK", "languageCode": "zh", "nextCursor": "",
        "pageOffset": 0, "pageSize": 24, "searchTerm": term,
    }, ensure_ascii=False))
    e = urllib.parse.quote(json.dumps({"persistedQuery": {"version": 1, "sha256Hash": SEARCH_HASH}}))
    url = "%s?operationName=getSearchResults&variables=%s&extensions=%s" % (SEARCH_API, q, e)
    d = http_json(url)
    rs = (((d.get("data") or {}).get("universalSearch") or {}).get("results")) or []
    out = []
    for r in rs:
        if r.get("__typename") != "Product":
            continue
        master = ""
        for m in r.get("media") or []:
            if m.get("role") == "MASTER" and m.get("type") == "IMAGE":
                master = m.get("url", "")
                break
        out.append({"id": r.get("id"), "name": r.get("name"), "platforms": r.get("platforms") or [], "master": master})
    return out


def _sub_score(nw, ns, base):
    """nw 是否为 ns 的子串; 港服名常带 (语言列表) 后缀。
    关键防误配: 若命中点之后的剩余部分以数字开头(续作序号, 如 '竟然|2日语...') -> 视为不同商品"""
    idx = ns.find(nw)
    if idx < 0:
        return 0.0
    rest = ns[idx + len(nw):]
    if rest[:1].isdigit():
        return 0.0
    return base


def score_one(wps, cand):
    s = 0.0
    nw, ns = norm(wps), norm(cand["name"])
    if not nw or not ns:
        return 0.0
    if nw == ns:
        s = 1.0
    else:
        bw, bs = strip_seq(nw), strip_seq(ns)
        if bw and bs and bw == bs:
            s = 0.85
        elif len(nw) >= 3:
            s = _sub_score(nw, ns, 0.80)
            if not s and len(ns) >= 3:
                s = _sub_score(ns, nw, 0.75)
        if not s:
            return 0.0
    if has_seq(nw) == has_seq(ns):
        s += 0.05
    return round(min(s, 1.05), 3)


def best_of(wps, cands, alt=""):
    """返回 (best_cand, best_score, second_score) 候选须唯一最高分(同名双平台算同分同类)"""
    scored = []
    for c in cands:
        if not c.get("master"):
            continue
        if is_excluded(c["name"], wps + " " + alt):
            continue
        s = max(score_one(wps, c), score_one(alt, c) if alt else 0.0)
        scored.append((s, c))
    scored.sort(key=lambda x: -x[0])
    if not scored or scored[0][0] < MIN_SCORE:
        return None, 0.0, 0.0
    best_s, best_c = scored[0]
    # 第二名: 排除与 best 同名(双平台副本)
    nb = norm(best_c["name"])
    second_s = 0.0
    for s, c in scored[1:]:
        if norm(c["name"]) != nb:
            second_s = s
            break
    return best_c, best_s, second_s


def load_json(p, default):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def grid_names():
    """表内全部真实商品名(去重), 保持出现顺序"""
    g = load_json(GRID, {})
    names, seen = [], set()
    for r in (g.get("rows") or [])[1:]:
        if not r or len(r) < 3:
            continue
        v = r[2]
        if v is None:
            continue
        v = str(v).strip()
        if not v or v in ("中文", "商品名称"):
            continue
        if v not in seen:
            seen.add(v)
            names.append(v)
    return names


def init_skip():
    """初始化 auto_skip: 当前所有无封面商品名(店主已定 清空/保持/港服无货), 排除本次手动补图的三个竟然键"""
    names = grid_names()
    m = load_json(MANIFEST, {})
    manual_new = set(sys.argv[2:]) if len(sys.argv) > 2 else set()
    missing = [n for n in names if n not in m and n not in manual_new]
    json.dump(missing, open(SKIP, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("auto_skip 初始化: %d 个名字 (无封面且非手动新增)" % len(missing))


def run():
    names = grid_names()
    m = load_json(MANIFEST, {})
    skip = set(load_json(SKIP, []))
    state = load_json(STATE, {})
    targets = [n for n in names if n not in m and n not in skip]
    print("商品总数 %d | 已有封面 %d | 有意无封面 %d | 待自动抓图 %d" % (len(names), len(m), len(skip), len(targets)))

    added, pending, errors = [], [], []
    done = 0
    for name in targets:
        if done >= MAX_TARGETS:
            pending.append({"name": name, "reason": "本轮配额用尽, 下轮继续"})
            continue
        st = state.get(name) or {}
        if st.get("n", 0) >= MAX_ATTEMPTS:
            pending.append({"name": name, "reason": "失败%d次, 需人工核对" % st.get("n")})
            continue

        # 找英文名(col4, 索引3)作备用搜索词
        en = ""
        g = load_json(GRID, {})
        for r in (g.get("rows") or [])[1:]:
            if r and len(r) > 3 and r[2] and str(r[2]).strip() == name and r[3]:
                en = str(r[3]).strip()
                break

        queries, seenq = [], set()
        for q in [name, en, strip_seq(norm(name))]:
            if q and q not in seenq:
                seenq.add(q)
                queries.append(q)

        best, bscore, sscore, ok = None, 0.0, 0.0, False
        try:
            round_best = None
            for qi, q in enumerate(queries[:2]):
                cands = store_search(q)
                # 英文词搜索时, 候选同时用 WPS 中文名与英文词打分(取高者)
                alt = "" if q == name else q
                c, s, ss = best_of(name, cands, alt)
                if c is None:
                    continue
                if round_best is not None and round_best[1] >= MIN_SCORE and c["id"] != round_best[0]["id"] and abs(s - round_best[1]) < SCORE_GAP:
                    round_best = (None, min(s, round_best[1]), 0)  # 两轮歧义 -> 放弃
                    break
                if round_best is None or s > round_best[1]:
                    round_best = (c, s, ss)
            if round_best and round_best[0] is not None:
                best, bscore, sscore = round_best
                ok = bscore >= MIN_SCORE and (bscore - sscore) >= SCORE_GAP
        except Exception as ex:
            errors.append({"name": name, "error": str(ex)[:200]})

        st["n"] = st.get("n", 0) + 1
        st["last"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        if ok:
            fn = "covers/ac%s.jpg" % hashlib.md5(name.encode()).hexdigest()[:12]
            try:
                sz = http_download(best["master"], os.path.join(BASE, fn))
                m[name] = fn
                done += 1
                added.append({"name": name, "product": best["id"], "storeName": best["name"],
                              "score": bscore, "file": fn, "bytes": sz})
                st["ok"] = fn
                print("  + %s  <-  %s (score %.2f)" % (name, best["name"], bscore))
            except Exception as ex:
                errors.append({"name": name, "error": "download: %s" % str(ex)[:150]})
                pending.append({"name": name, "reason": "下载失败: %s" % str(ex)[:80]})
                st["err"] = str(ex)[:120]
        else:
            top = ""
            if best:
                top = "%s (%.2f vs %.2f)" % (best["name"], bscore, sscore)
            pending.append({"name": name, "reason": "匹配有歧义或无命中", "top": top})
            st["err"] = "pending: " + top[:100]
            print("  ? %s  pending %s" % (name, top[:60]))
        state[name] = st

    json.dump(m, open(MANIFEST, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(state, open(STATE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    report = {
        "time": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "added": added, "pending": pending, "errors": errors,
        "stats": {"total": len(names), "covered": len(m), "pending_open": len(targets) - done},
    }
    json.dump(report, open(REPORT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("自动入库 %d | pending %d | 错误 %d -> covers/autocover_report.json" % (len(added), len(pending), len(errors)))


if __name__ == "__main__":
    try:
        if len(sys.argv) > 1 and sys.argv[1] == "--init-skip":
            init_skip()
        else:
            run()
    except Exception as e:
        print("autocover 致命异常(不阻断部署): %s" % e)
    sys.exit(0)
