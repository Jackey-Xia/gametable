#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pad_vs_fill.py —— 任务1：现「留边版」 vs 「不留边·3:4 满填充版」的前端对比预览素材

口径：消费者前端卡片 .gcover = 96×128（3:4，object-fit:cover）
  左：现留边版（504×672，零裁切，整图保留 + 虚化补边）
  右：不留边版（原图按 3:4 居中满填充裁切，主体更大，但会裁掉内容）

原图获取优先级：
  1) /tmp/padvs/orig/{i}.jpg 缓存
  2) git 历史里的「源 xxx.jpg」（cover_sources.note 记录）
  3) 港服/美服重搜（pad_rescan_orig.py 产出，存到同一缓存目录）
  4) 从留边版画布反推内容区（近似）

用法：
  python3 pad_vs_fill.py            # 取原图 + 生成右图 + state.json
  python3 pad_vs_fill.py --html     # 额外生成单目录预览站点（在 REPO/pad_review/）
"""
import json, os, re, sys, subprocess, collections
from io import BytesIO
from PIL import Image

REPO = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, REPO)
import cover_policy as CP

OUT = "/tmp/padvs"
ORIG = os.path.join(OUT, "orig")
RIGHT = os.path.join(OUT, "right")
os.makedirs(ORIG, exist_ok=True)
os.makedirs(RIGHT, exist_ok=True)
GIT = ["git", "-C", REPO]
SRC_PAT = re.compile(r"源\s*([\w\-]+\.jpg)")


def git(*a):
    return subprocess.run(GIT + list(a), capture_output=True)


def blob_bytes(path):
    r = git("rev-list", "-n", "10", "HEAD", "--", path)
    if r.returncode != 0:
        return None
    for sha in r.stdout.decode().split():
        s = git("show", "%s:%s" % (sha, path))
        if s.returncode == 0 and s.stdout:
            return s.stdout
    return None


def detect_content(im):
    """从留边版画布反推内容区（补边是强模糊背景）"""
    try:
        import numpy as np
    except ImportError:
        return None
    a = np.asarray(im.convert("L"), dtype=np.float32)
    gx = np.abs(np.diff(a, axis=1))
    gy = np.abs(np.diff(a, axis=0))
    col = gx.mean(axis=0)
    row = gy.mean(axis=1)

    def span(v):
        v = np.convolve(v, np.ones(5) / 5.0, mode="same")
        lo, hi = v.min(), v.max()
        if hi <= lo:
            return 0, len(v)
        thr = lo + (hi - lo) * 0.35
        idx = np.where(v > thr)[0]
        if len(idx) < 5:
            return 0, len(v)
        return int(idx[0]), int(idx[-1]) + 1

    x0, x1 = span(col)
    y0, y1 = span(row)
    if (x1 - x0) < im.width * 0.5 and (y1 - y0) < im.height * 0.5:
        return None
    return x0, y0, x1, y1


def crop34(im):
    w, h = im.size
    tw = min(w, int(round(h * 3 / 4)))
    th = min(h, int(round(w * 4 / 3)))
    x = (w - tw) // 2
    y = (h - th) // 2
    return im.crop((x, y, x + tw, y + th))


def get_orig(i, cur_abs, note):
    """返回 (PIL.Image, from) ; from = cache|git|canvas|None"""
    p = os.path.join(ORIG, "%04d.jpg" % i)
    if os.path.exists(p):
        try:
            tag = "cache"
            tp = os.path.join(ORIG, "%04d.txt" % i)
            if os.path.exists(tp):
                tag = open(tp, encoding="utf-8").read().strip() or "cache"
            return Image.open(p).convert("RGB"), tag
        except Exception:
            pass
    m = SRC_PAT.search(note or "")
    if m:
        rel = "covers/" + m.group(1)
        fp = os.path.join(REPO, rel)
        data = open(fp, "rb").read() if os.path.exists(fp) else blob_bytes(rel)
        if data:
            try:
                im = Image.open(BytesIO(data)).convert("RGB")
                im.save(p, "JPEG", quality=93)
                open(os.path.join(ORIG, "%04d.txt" % i), "w", encoding="utf-8").write("git")
                return im, "git"
            except Exception:
                pass
    # 画布反推
    im0 = Image.open(cur_abs).convert("RGB")
    box = detect_content(im0)
    if box:
        x0, y0, x1, y1 = box
        if (x1 - x0) >= im0.width * 0.9 and (y1 - y0) >= im0.height * 0.9:
            return None, None          # 检测不出补边 -> 放弃
        im = im0.crop((x0, y0, x1, y1))
        im.save(p, "JPEG", quality=93)
        open(os.path.join(ORIG, "%04d.txt" % i), "w", encoding="utf-8").write("canvas")
        return im, "canvas"
    return None, None


def main():
    src = CP.load_sources()
    man = CP.load_manifest()
    pad = {n: v for n, v in src.items()
           if (v.get("role") or "").endswith("-pad") and man.get(n)}
    byrel = collections.defaultdict(list)
    for n in sorted(pad):
        byrel[man[n]].append(n)

    state = {}
    cnt = collections.Counter()
    for i, rel in enumerate(sorted(byrel), 1):
        keys = byrel[rel]
        rep = keys[0]
        rec = pad[rep]
        cur = os.path.join(REPO, rel)
        im, frm = get_orig(i, cur, rec.get("note"))
        info = ""
        if im is None:
            info = "缺原图"
        else:
            w, h = im.size
            info = "%s %dx%d" % (frm, w, h)
            crop34(im).resize((504, 672), Image.LANCZOS).save(
                os.path.join(RIGHT, "%04d.jpg" % i), "JPEG", quality=92)
        cnt[frm or "none"] += 1
        state[str(i)] = {"i": i, "rep": rep, "keys": keys, "rel": rel,
                         "info": info, "from": frm or "none",
                         "store": (rec.get("store") or "")[:60],
                         "role": rec.get("role")}
    json.dump(state, open(os.path.join(OUT, "state.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("留边键 %d -> 唯一图 %d；原图来源 %s" % (len(pad), len(state), dict(cnt)))
    need = [v for v in state.values() if v["from"] in ("none", "canvas")]
    print("需重搜/复核: %d" % len(need))
    json.dump(need, open(os.path.join(OUT, "need.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
