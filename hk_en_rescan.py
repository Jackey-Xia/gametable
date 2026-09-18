#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""hk_en_rescan.py —— 剩余 D 组(未被选中更换的) 用 WPS 备注的英文名去港服页面重新搜索匹配对比。
英文名常被写成 "Call of Duty 14/COD 14/Call of Duty 14：WWII" 这类多别名串,
这里拆成多个检索词逐个搜, 比整串搜命中率高得多。
只写 /tmp, 不动 covers/。
"""
import json, os, re, sys, hashlib, shutil, threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from PIL import Image, ImageFilter

REPO = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, REPO)
import autocover as AC
import cover_policy as CP
import apply_en_choices as AE   # 复用 base_of / 已选编号

STATE = "/tmp/hk2_state.json"
RAWDIR = "/tmp/hk2_cand"; PROCDIR = "/tmp/hk2_proc"
os.makedirs(RAWDIR, exist_ok=True); os.makedirs(PROCDIR, exist_ok=True)
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


PAREN = re.compile(r"[（(][^）)]*[）)]")


def queries(en, cn):
    """把 WPS 英文名拆成多个可检索别名"""
    out = []

    def add(s):
        s = PAREN.sub("", s).strip(" ：:-—·、/／")
        s = re.sub(r"\s+", " ", s).strip()
        if len(s) >= 2 and s not in out:
            out.append(s)

    if en:
        parts = [p for p in re.split(r"[/／]", en) if p.strip()]
        for p in parts:
            add(p)
            sub = re.split(r"[：:]", p)
            for s in sub:
                add(s)
        add(en)
        add(PAREN.sub("", en))
    return out[:6]


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
    cn = AE.base_of(rep)
    en = EN.get(rep) or EN.get(cn) or ""
    rec["en"] = en
    qs = queries(en, cn)
    rec["qs"] = qs
    if not qs:
        rec["status"] = "noen"; state[rep] = rec; return

    cands = {}
    for q in qs:
        try:
            for c in AC.store_search(q):
                cands[c["id"]] = c
        except Exception as ex:
            rec["err"] = str(ex)[:120]
    rec["ncand"] = len(cands)
    if not cands:
        rec["status"] = "nomatch"; state[rep] = rec; return

    scored = []
    for c in cands.values():
        s = 0.0
        for probe in [cn, rep] + qs:
            s = max(s, AC.score_one(probe, c, True))
        # 中文名带版本标注时用中文名做版本校验
        s2 = AC.score_one(rep, c, True)
        s = max(s, s2)
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
    if s < 0.70:
        rec["status"] = "nomatch"; state[rep] = rec; return
    media = c.get("media") or [{"role": "MASTER", "url": c.get("master")},
                               {"role": "PORTRAIT_BANNER", "url": c.get("portrait")}]
    role, url = CP.pick_role(media)
    if not url:
        rec["status"] = "nomedia"; state[rep] = rec; return
    key = hashlib.md5(("HK2|" + cn).encode("utf-8")).hexdigest()[:12]
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
    cur_rel = man.get(rep) or man.get(cn) or ""
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
    zh = json.load(open("/tmp/zh_groups.json", encoding="utf-8"))
    enL = json.load(open("/tmp/en_review_lists.json", encoding="utf-8"))
    picked = set()
    for tag, lst, ps in (("E", enL["E"], AE.E_PICK), ("F", enL["F"], AE.F_PICK)):
        for i in ps:
            picked.add(lst[i - 1])
    reps = [r for r in zh["nomatch"] if r not in picked]
    todo = [r for r in reps if r not in state]
    print("剩余待复搜:", len(reps), "| 本轮:", len(todo), flush=True)
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
