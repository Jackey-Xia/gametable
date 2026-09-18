#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""apply_review_choices.py —— 执行店主在两个审核页上的挑选结果

① pad_review（留边版 vs 不留边满填充版）：选中编号 -> 换成「不留边·3:4 满填充」版
   注意：页面显示编号 #n 不等于 state 索引 i，需从 pad_review/index.html 反查
   data-name(=商品名) -> state.rep -> i -> /tmp/padvs/right/{i}.jpg

② blank_review（留白商品三形态）：选中编号 -> 采用 C 形态（满填不留边）
   页面编号 = state 的 i；源图 /tmp/blank_orig/{i}.jpg -> form_c()

用法：
  python3 apply_review_choices.py            # dry-run
  python3 apply_review_choices.py --apply    # 落盘 + 登记
"""
import json, os, sys, re, html, hashlib, shutil
from PIL import Image

REPO = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, REPO)
import cover_policy as CP

PAD_STATE = "/tmp/padvs/state.json"
PAD_RIGHT = "/tmp/padvs/right"
BLANK_STATE = "/tmp/blank_state.json"
BLANK_SRC = "/tmp/blank_orig"
PAD_HTML = os.path.join(REPO, "pad_review", "index.html")
TAG = "fill34|v1"

# ① 不留边满填充
PICK1 = [1,2,3,4,5,6,7,8,9,10,11,12,14,16,17,18,19,20,22,25,26,27,28,29,30,31,34,35,36,37,38,39,40,42,44,46,47,48,49,54,55,56,57,58,60,61,62,63,64,65,66,67,68,69,70,71,72,73,74,75,76,77,78,80,81,82,83,85,86,88,89,90,91,93,94,95,96,97,98,99,100,102,103,104,105,106,108,109,115,117,118,119,120,121,122,123,124,125,126,127,129,130,131,132,133,134,137,140,141,143,144,145,146,147,148,151,152,153,154,155,156,158,159,160,161,163,165,166,167,170,175,176,179,180,181,182,184,185,186,187,188,193,194,196,197,198,200,202,203,204,209,210,211,212,214,215,216,217,218,219,220,221,222,223,225,226,228,229,230,231,233,234,235,236,237,238,239,240,241,243,244,245,247,254,259,261,263,264,265,267,268,269,270,271,272,275,276,279,281,282,283,285,286,289,292,293,295,296,297,299,300,304,305,306,307,308,309,310,311,312,314,315,316,317,318,319,320,321,322,324,325,329,330,331,333,334,335,336,337,338,339,340,341,342,345,346,349,352,353,355,357,358,359,360,361,362,365,366,367,368,369,370,372,373,374,375,376,377,379,384,385,386,389,390,391,392,393,394,395,396,398,399,401,402,403,404,406,408,410,412,413,416,420,421,422,423,424,426,427,428,429,431,432,433,434,436,437,439,440,442,443,444,445,446,447,450,456,457,458,459,460,461,465,466,467,468,469,471,472,473,476,479,480,482,483,484,486,487,488,489,490,491,492,493,494,498,499,501,502,503,504,505,506,511,512,513,514,515,517,520,521,525,526,527,528,529,530,531,532,533,534,535,536,537,538,539,540,541,542,544,545,547,548,551,552,553,555,556,558,559,560,562,563,564,565,566,567,568,570,571,572,573,574,575,580,581,582,583,584,585,586,587,590,591,592,593,594,597,601,602,603,605,606,607,612,613,616,617,618,619,620,621,622]

# ② 留白商品 -> C 满填不留边
PICK2 = [6,7,13,14,18,20,23,25,27,29,30,44,48,50,51,52,53,56,57,60,61]


def crop34(im):
    w, h = im.size
    tw = min(w, int(round(h * 3 / 4)))
    th = min(h, int(round(w * 4 / 3)))
    x, y = (w - tw) // 2, (h - th) // 2
    return im.crop((x, y, x + tw, y + th))


def pad_index():
    """页面显示编号 #n -> state 记录"""
    s = open(PAD_HTML, encoding="utf-8").read()
    pat = re.compile(r'<div class="card" data-name="(.*?)" data-diff=".*?<div class="hd"><b>#(\d+)</b> ',
                     re.S)
    m = {}
    for name, n in pat.findall(s):
        m[int(n)] = html.unescape(name)
    return m


def new_rel(name, tag=TAG):
    return "covers/rc%s.jpg" % hashlib.md5((name + "|" + tag).encode("utf-8")).hexdigest()[:12]


def clear_skip(keys, apply):
    """auto_skip.json 可能是 list 或 dict，两种都兼容"""
    p = os.path.join(REPO, "covers", "auto_skip.json")
    sk = json.load(open(p, encoding="utf-8"))
    if isinstance(sk, dict):
        hit = [k for k in keys if k in sk]
        if hit and apply:
            for k in hit:
                del sk[k]
    else:
        hit = [k for k in keys if k in sk]
        if hit and apply:
            sk = [x for x in sk if x not in set(hit)]
    if hit and apply:
        json.dump(sk, open(p, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2,
                  sort_keys=isinstance(sk, dict))
    return hit


def main():
    apply = "--apply" in sys.argv
    man = CP.load_manifest()
    src = CP.load_sources()
    pad_idx = pad_index()
    pst = json.load(open(PAD_STATE, encoding="utf-8"))
    rep2v = {v["rep"]: v for v in pst.values()}

    plan1 = []
    for n in sorted(set(PICK1)):
        rep = pad_idx.get(n)
        if rep is None:
            print("① 无效编号", n); continue
        v = rep2v.get(rep)
        if v is None:
            print("① 未匹配", n, rep); continue
        rp = os.path.join(PAD_RIGHT, "%04d.jpg" % v["i"])
        if not os.path.exists(rp):
            print("① 缺右图", n, rep); continue
        plan1.append((n, v, rp))

    print("① 待换 %d 项（唯一图）-> 涉及键 %d" % (len(plan1), sum(len(v["keys"]) for _, v, _ in plan1)))
    # 质量提示：canvas 反推的原图
    warn1 = [(n, v["rep"]) for n, v, _ in plan1 if v.get("from") == "canvas"]
    print("   其中原图为画布反推(近似): %d" % len(warn1), warn1[:8])

    plan2 = []
    bst = json.load(open(BLANK_STATE, encoding="utf-8"))
    i2k = {v["i"]: k for k, v in bst.items()}
    for i in sorted(set(PICK2)):
        k = i2k.get(i)
        if k is None:
            print("② 无效编号", i); continue
        sp = os.path.join(BLANK_SRC, "%04d.jpg" % i)
        if not os.path.exists(sp):
            print("② 缺源图", i, k); continue
        plan2.append((i, k, bst[k], sp))
    print("② 待换 %d 项" % len(plan2))
    for i, k, v, sp in plan2:
        print("   #%d %s | %s | %s" % (i, k[:26], v.get("step"), (v.get("cand") or "")[:34]))

    if not apply:
        print("\n(dry-run) 加 --apply 落盘")
        return

    done1 = []
    for n, v, rp in plan1:
        rep = v["rep"]
        rel = new_rel(rep)
        dst = os.path.join(REPO, rel)
        im = Image.open(rp).convert("RGB")
        if im.size != (504, 672):
            im = crop34(im).resize((504, 672), Image.LANCZOS)
        im.save(dst, "JPEG", quality=92)
        role = (v.get("role") or "").replace("-pad", "-fill") or "P-fill"
        note = "①店主审核: 改为不留边·3:4满填充版（原图 %s）" % (v.get("info") or "")
        for k in v["keys"]:
            ok, msg = CP.set_cover(k, rel, "manual", role,
                                   store=v.get("store") or src.get(rep, {}).get("store", ""),
                                   note=note + (" · 同款多库存沿用" if len(v["keys"]) > 1 else ""))
            if not ok:
                print("   ! 失败", k, msg)
        done1.append((n, rep, rel, len(v["keys"])))
    print("① 完成 %d 项 / %d 键" % (len(done1), sum(d[3] for d in done1)))

    done2 = []
    for i, k, v, sp in plan2:
        rel = new_rel(k)
        dst = os.path.join(REPO, rel)
        im = crop34(Image.open(sp).convert("RGB")).resize((504, 672), Image.LANCZOS)
        im.save(dst, "JPEG", quality=92)
        note = "②店主审核: 采用C满填不留边 · %s · %s" % (v.get("step") or "", (v.get("cand") or "")[:40])
        ok, msg = CP.set_cover(k, rel, "manual", "P", store=v.get("cand") or "", note=note)
        if not ok:
            print("   ! 失败", k, msg)
        done2.append((i, k, rel))
    print("② 完成 %d 项" % len(done2))

    # 清留白名单
    keys = [k for _, v, _ in plan1 for k in v["keys"]] + [k for _, k, _ in done2]
    hit = clear_skip(keys, True)
    print("清除 auto_skip: %d" % len(hit), hit[:10])

    json.dump({"p1": [{"n": a, "rep": b, "rel": c, "keys": d} for a, b, c, d in done1],
               "p2": [{"i": a, "key": b, "rel": c} for a, b, c in done2]},
              open("/tmp/apply_review_choices.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("明细 -> /tmp/apply_review_choices.json")


if __name__ == "__main__":
    main()
