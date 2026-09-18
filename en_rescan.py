#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""en_rescan.py —— D组(港服未匹配)241 个改用「英文关键词 + 美服 en-US」重新匹配, 产出对比预览。
只扫描写 /tmp, 不动 covers/。落盘替换另见 apply_en_choices.py
用法: python3 en_rescan.py
"""
import json, os, re, sys, hashlib, shutil, threading, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from PIL import Image, ImageFilter

REPO = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, REPO)
import autocover as AC
import cover_policy as CP

STATE = "/tmp/en_state.json"
RAWDIR = "/tmp/en_cand"; PROCDIR = "/tmp/en_proc"
os.makedirs(RAWDIR, exist_ok=True); os.makedirs(PROCDIR, exist_ok=True)
SEQ = re.compile(r"[（(]\s*\d+\s*[）)]\s*$")
LOCK = threading.Lock()

man = json.load(open(os.path.join(REPO, "covers/manifest.json"), encoding="utf-8"))
grid = json.load(open(os.path.join(REPO, "data/ps_grid.json"), encoding="utf-8"))
EN = {}
for r in (grid.get("rows") or [])[1:]:
    if r and len(r) > 3 and r[2] and str(r[2]).strip():
        EN[str(r[2]).strip()] = str(r[3] or "").strip()

state = json.load(open(STATE, encoding="utf-8")) if os.path.exists(STATE) else {}


def save_state():
    with LOCK:
        json.dump(state, open(STATE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def search_en(term, locale="en-US", country="US", lang="en"):
    """跨服搜索: 地区/语种由 x-psn-store-locale-override 决定, 必须用英文关键词"""
    if not term or not term.strip():
        return []
    q = urllib.parse.quote(json.dumps({
        "countryCode": country, "languageCode": lang, "nextCursor": "",
        "pageOffset": 0, "pageSize": 24, "searchTerm": term,
    }, ensure_ascii=False))
    e = urllib.parse.quote(json.dumps({"persistedQuery": {"version": 1, "sha256Hash": AC.SEARCH_HASH}}))
    url = "%s?operationName=getSearchResults&variables=%s&extensions=%s" % (AC.SEARCH_API, q, e)
    req = urllib.request.Request(url, headers={
        "User-Agent": AC.UA, "Accept": "application/json", "Content-Type": "application/json",
        "x-apollo-operation-name": "getSearchResults",
        "x-psn-store-locale-override": locale,
        "apollographql-client-name": "@sie-ppr-web-store/app",
        "apollographql-client-version": "0.114.0",
        "Referer": "https://store.playstation.com/",
        "Accept-Encoding": "identity",
    })
    with urllib.request.urlopen(req, timeout=30) as r:
        d = json.loads(r.read().decode("utf-8", "ignore"))
    rs = (((d.get("data") or {}).get("universalSearch") or {}).get("results")) or []
    out = []
    for it in rs:
        if it.get("__typename") != "Product":
            continue
        master, portrait = "", ""
        for m in it.get("media") or []:
            if m.get("type") not in (None, "IMAGE"):
                continue
            role = m.get("role")
            if role == "MASTER" and not master:
                master = m.get("url", "")
            elif role == "PORTRAIT_BANNER" and not portrait:
                portrait = m.get("url", "")
        if not (master or portrait):
            continue
        out.append({"id": it.get("id"), "name": it.get("name"), "platforms": it.get("platforms") or [],
                    "master": master, "portrait": portrait, "media": it.get("media") or []})
    return out


def bmae(a, b):
    try:
        A = Image.open(a).convert("RGB").resize((48, 64), Image.LANCZOS).filter(ImageFilter.GaussianBlur(2))
        B = Image.open(b).convert("RGB").resize((48, 64), Image.LANCZOS).filter(ImageFilter.GaussianBlur(2))
    except Exception:
        return 999
    pa, pb = A.load(), B.load()
    d = 0
    for y in range(64):
        for x in range(48):
            ra, ga, ba = pa[x, y]; rb, gb, bb = pb[x, y]
            d += abs(ra - rb) + abs(ga - gb) + abs(ba - bb)
    return d / (48 * 64 * 3)


def prep(raw, proc):
    """与正式换图同一套形态规则"""
    mode, info = CP.decide_form(raw)
    if mode == "pad":
        if not CP.make_pad_auto(raw, proc):
            return False, info
    else:
        shutil.copy(raw, proc)
    return True, info


def work(rep):
    if rep in state:
        return
    rec = {}
    wps = SEQ.sub("", rep).strip() or rep
    en = EN.get(rep) or EN.get(wps) or ""
    rec["wps"] = wps; rec["en"] = en
    if not en:
        rec["status"] = "noen"; state[rep] = rec; return

    cands = {}
    for q in [en, re.sub(r"[（(].*?[）)]", "", en).strip()]:
        if not q:
            continue
        try:
            for c in search_en(q):
                cands[c["id"]] = c
        except Exception as ex:
            rec["err"] = str(ex)[:120]
    if not cands:
        rec["status"] = "nomatch"; state[rep] = rec; return

    scored = []
    for c in cands.values():
        s = AC.score_one(en, c, True)
        s = max(s, AC.score_one(wps, c, True))
        if s <= 0:
            continue
        scored.append((s, c))
    if not scored:
        rec["status"] = "nomatch"; state[rep] = rec; return
    scored.sort(key=lambda x: -x[0])
    s, c = scored[0]
    rec["cand_name"] = c["name"]; rec["score"] = round(s, 3)
    rec["second"] = (scored[1][1]["name"] if len(scored) > 1 else "")
    rec["second_score"] = round(scored[1][0], 3) if len(scored) > 1 else 0
    if s < 0.65:
        rec["status"] = "nomatch"; state[rep] = rec; return
    media = c.get("media") or [{"role": "MASTER", "url": c.get("master")},
                               {"role": "PORTRAIT_BANNER", "url": c.get("portrait")}]
    role, url = CP.pick_role(media)
    if not url:
        rec["status"] = "nomedia"; state[rep] = rec; return
    key = hashlib.md5(("EN|" + wps).encode("utf-8")).hexdigest()[:12]
    raw = os.path.join(RAWDIR, key + ".jpg")
    if not os.path.exists(raw):
        try:
            AC.http_download(url, raw)
        except Exception as ex:
            rec["status"] = "dlfail"; rec["err"] = str(ex)[:120]; state[rep] = rec; return
    rec["raw"] = raw
    proc = os.path.join(PROCDIR, key + ".jpg")
    if not os.path.exists(proc):
        ok, info = prep(raw, proc)
        if not ok:
            rec["status"] = "procfail"; state[rep] = rec; return
        rec["form_info"] = info
    rec["proc"] = proc
    cur_rel = man.get(rep) or man.get(wps) or ""
    rec["cur"] = cur_rel
    cur = os.path.join(REPO, cur_rel)
    rec["bmae"] = round(bmae(proc, cur), 2) if cur_rel and os.path.exists(cur) else 999
    rec["role"] = role
    try:
        w, h = Image.open(raw).size; rec["dims"] = [w, h]
    except Exception:
        pass
    rec["status"] = "ok" if s >= 0.80 else "low"
    state[rep] = rec


def main():
    groups = json.load(open("/tmp/zh_groups.json", encoding="utf-8"))
    reps = groups["nomatch"]
    todo = [r for r in reps if r not in state]
    print("待扫描:", len(reps), "| 剩余:", len(todo), flush=True)
    if todo:
        done = [0]
        with ThreadPoolExecutor(max_workers=3) as ex:
            futs = [ex.submit(work, r) for r in todo]
            for f in as_completed(futs):
                done[0] += 1
                if done[0] % 25 == 0:
                    save_state(); print("... %d/%d" % (done[0], len(todo)), flush=True)
    save_state()
    st = {}
    for v in state.values():
        st[v.get("status")] = st.get(v.get("status"), 0) + 1
    print("完成。状态分布:", st)


if __name__ == "__main__":
    main()
