# -*- coding: utf-8 -*-
"""改75: 生成 pinyin.js —— 汉字→无声调拼音映射, 供前端"同音搜索提示"使用。
覆盖: GB2312 全部汉字(6763, 含所有常用字) + 游戏库内出现的全部唯一字(双保险)。
输出: cloudrepo/pinyin.js  →  window.GT_PINYIN = {"字":"pin1yin", ...} (无声调小写)
"""
import json, os, sys

BASE = os.path.dirname(os.path.abspath(__file__))
VENV = "/Users/jackey/.workbuddy/binaries/python/envs/default/bin/python"
assert sys.executable.startswith("/Users/jackey/.workbuddy/binaries/python/envs"), "请用 managed venv 运行"
from pypinyin import pinyin, Style

def one(ch):
    try:
        return pinyin(ch, style=Style.NORMAL, errors="ignore")[0][0].lower()
    except Exception:
        return ""

chars = set()

# 1) GB2312 全部汉字
for hi in range(0xB0, 0xF8):
    for lo in range(0xA1, 0xFF):
        try:
            chars.add(bytes([hi, lo]).decode("gb2312"))
        except Exception:
            pass

# 2) 游戏库内全部唯一字(中英文名), 防止生僻游戏字漏网
games = []
pj = os.path.join(BASE, "data", "ps_games.json")
if os.path.exists(pj):
    games = json.load(open(pj, encoding="utf-8"))
for g in games:
    for k in ("name", "en"):
        v = str(g.get(k) or "")
        for ch in v:
            if ord(ch) > 127:
                chars.add(ch)

m = {}
for ch in sorted(chars):
    p = one(ch)
    if p:
        m[ch] = p

out = os.path.join(BASE, "pinyin.js")
with open(out, "w", encoding="utf-8") as f:
    f.write("/* 改75: 汉字→拼音映射(GB2312+游戏库全字), 供同音搜索使用。由 gen_pinyin.py 生成 */\n")
    f.write("window.GT_PINYIN=")
    json.dump(m, f, ensure_ascii=False, separators=(",", ":"))
    f.write(";\n")

print("chars=%d  size=%.1fKB -> %s" % (len(m), os.path.getsize(out) / 1024, out))
