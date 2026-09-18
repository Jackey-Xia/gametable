#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""hk2_preview.py —— 剩余 D 组用 WPS 英文名重搜港服的结果预览 + 清单（前端 96×128 口径）"""
import json, os
from PIL import Image, ImageDraw, ImageFont

REPO = "/Users/jackey/WorkBuddy/2026-09-08-16-48-51/gametable/cloudrepo"
state = json.load(open("/tmp/hk2_state.json", encoding="utf-8"))
OUT = "/tmp/hk2_review"
os.makedirs(OUT, exist_ok=True)
TH_W, TH_H, GAP, LABEL_H = 168, 224, 8, 46
FONT = ImageFont.truetype("/System/Library/Fonts/Hiragino Sans GB.ttc", 18)
FONT_S = ImageFont.truetype("/System/Library/Fonts/Hiragino Sans GB.ttc", 14)


def sim_crop(path, w=TH_W, h=TH_H):
    try:
        im = Image.open(path).convert("RGB")
    except Exception:
        return Image.new("RGB", (w, h), (210, 70, 70))
    iw, ih = im.size
    s = max(w / iw, h / ih)
    nw, nh = max(w, int(round(iw * s))), max(h, int(round(ih * s)))
    im = im.resize((nw, nh), Image.LANCZOS)
    x = (nw - w) // 2; y = (nh - h) // 2
    return im.crop((x, y, x + w, y + h))


# 人工复核后确认「商城条目指错/版本对不上」的名单（看图 + 候选名比对），预览里标红
DOUBT = {
    "战地风云5/战地5（决定版）", "生化危机4：重制版（黄金版）（1）", "耻辱1/羞辱1（决定版）（港版英文）",
    "逃生1（完整版）", "三位一体1-4（合集版）", "为了吾王1", "使命召唤14：二战/COD14（豪华版）",
    "使命召唤18：决胜时刻 先锋/COD18", "哈迪斯1", "四海兄弟123合集", "天国：拯救2（皇家版）（1）",
    "如龙2 人中之龙：极2（1）", "孤岛惊魂：破晓 新曙光", "星球大战：战场前线1（终极版）",
    "星球大战：战机中队/中队争雄（1）", "死亡空间：重制版", "海绵宝宝：派大星游戏",
    "海贼王：无限世界 赤红（豪华版）", "海贼王：寻秘世界（豪华版）", "猫咪斗恶龙3",
    "生化奇兵123合集（典藏版）", "疯狂兔子：传奇派对1", "重装机兵xeno：重生",
    "质量效应123（传奇版）（港版英文）", "WRC7（1）", "中土世界：暗影组合包",
    "F1 25（经典/传奇版）", "兽人必须死3（完整版）", "战地风云4/战地4（高级版）（港版英文）",
    "狙击手：幽灵战士契约1（完整版）", "火影忍者 终极风暴羁绊（豪华版）",
}

H, M, L = [], [], []
for rep, v in state.items():
    st = v.get("status")
    (H if st == "ok" else M if st == "low" else L).append(rep)
H.sort(key=lambda r: -state[r].get("score", 0))
M.sort(key=lambda r: -state[r].get("score", 0))
L.sort()


def sheet(items, fname, tag):
    COLS, ROWS = 4, 6
    per = COLS * ROWS
    i = 0
    while i < len(items):
        chunk = items[i:i + per]
        W = COLS * (TH_W * 2 + GAP) + (COLS + 1) * GAP
        Hh = ROWS * (TH_H + LABEL_H + GAP) + GAP + 34
        img = Image.new("RGB", (W, Hh), (248, 248, 248))
        dr = ImageDraw.Draw(img)
        dr.text((GAP, 6), tag, fill=(30, 30, 30), font=FONT)
        for j, rep in enumerate(chunk):
            v = state[rep]
            r, c = divmod(j, COLS)
            x0 = GAP + c * (TH_W * 2 + GAP + GAP)
            y0 = 34 + GAP + r * (TH_H + LABEL_H + GAP)
            dr.text((x0, y0 + 2), "#%d %s" % (i + j + 1, rep[:22]), fill=(15, 15, 15), font=FONT)
            img.paste(sim_crop(os.path.join(REPO, v.get("cur") or "")), (x0, y0 + 27))
            img.paste(sim_crop(v.get("proc") or ""), (x0 + TH_W + GAP, y0 + 27))
            bad = rep in DOUBT
            dr.rectangle([x0 + TH_W + GAP, y0 + 27, x0 + TH_W * 2 + GAP, y0 + 27 + TH_H],
                         outline=(215, 40, 40) if bad else (170, 170, 170),
                         width=3 if bad else 1)
            info = "%s%s 分%.2f 差%.0f" % ("⚠存疑 " if bad else "",
                                          (v.get("cand_name") or "")[:16], v.get("score", 0), v.get("bmae", 0))
            dr.text((x0, y0 + 27 + TH_H + 3), info, fill=(200, 30, 30) if bad else (95, 95, 95), font=FONT_S)
        img.save(os.path.join(OUT, fname % (i // per + 1)))
        i += per


sheet(H, "H_%02d.png", "H组 · 港服英文名重搜-高分匹配（%d 个，左=现用 / 右=港服）" % len(H))
sheet(M, "I_%02d.png", "I组 · 港服英文名重搜-低分匹配（%d 个，需人工确认）" % len(M))

out = ["剩余 D 组 %d 个 · 用 WPS 英文名重搜港服" % len(state), "=" * 60,
       "H组 高分匹配: %d 个" % len(H),
       "I组 低分(0.70~0.80): %d 个" % len(M),
       "J组 仍未匹配(含表格无英文名): %d 个" % len(L), ""]


def dump(lst, title):
    out.append("-" * 60); out.append(title); out.append("-" * 60)
    for i, rep in enumerate(lst):
        v = state[rep]
        out.append("#%-3d %s%-24s en=%-20s 分%.2f [%s] 候选=%s" % (
            i + 1, "⚠" if rep in DOUBT else " ", rep[:24], (v.get("en") or "")[:20],
            v.get("score", 0), v.get("status"), (v.get("cand_name") or "")[:34]))


dump(H, "H组"); dump(M, "I组"); dump(L, "J组")
open(os.path.join(OUT, "清单.txt"), "w", encoding="utf-8").write("\n".join(out))
json.dump({"H": H, "I": M, "J": L}, open("/tmp/hk2_lists.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print("H=%d I=%d J=%d -> %s" % (len(H), len(M), len(L), OUT))
