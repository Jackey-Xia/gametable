#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cover_policy.py —— 封面读取/写入的唯一规则来源（Single Source of Truth）
======================================================================
店主确定的三条优先级（2026-09-16 定稿，任何脚本都必须走这里，不许各自实现）：

1. **图片读取优先级**：人工指定/按需调整过的  >  脚本自动抓取的
   → 凡是 `source == "manual"` 的记录，任何自动化流程都**不得**替换、删除、覆盖。
     连 manifest 里有键但 policy 里没登记的，一律保守视作 manual（历史数据默认人肉维护过）。

2. **自动抓图来源优先级**：PS 港服中文页（zh-Hans-HK）官方图  >  其它任何来源
   → 自动抓只能走 `store_zh_hk`；第三方图床 / 其它地区页不再作为自动来源。

3. **图片形态优先级**：竖图 2:3（PORTRAIT_BANNER）  >  方图 1:1（MASTER）
   → 同一商品官方同时提供两种形态时，**自动抓图默认取竖版**；只有竖版不存在时才退回方图。
     人工指定时以人工的形态为准。

   ★★★ **形态终版规则（2026-09-18 晚店主定稿，取代 09-17 的"无竖图一律留边"）**
   —— 一切以**消费者前端 96×128（3:4）实际展示**为准，由 `decide_form()` 统一判定：
     ① **方图（1:1）源** → **留边版**（方图上线必被左右各裁 63px，零裁切优先）
     ② **非方图（竖图）源** → 前端上下裁切带内**有文字/字母被遮挡** → 留边版；
        **不遮挡任何文字/字母** → **原图直上**（主体更大；人物/图案被裁没关系）
     ③ **纯横版（w/h ≥ 1.15）** → 原图直上（补边会把主体压成扁条）
     无法做文字识别时 → 保守取留边版（绝不冒险切字）。
   自动抓图与人工换图**都必须**走 `decide_form()` / `install_cover()`，不许各自判断。

产出文件 covers/cover_sources.json：
  { "商品名": {"file": "covers/xxx.jpg", "source": "manual|store_zh_hk",
               "role": "P|M", "store": "港服命中名", "time": "...", "note": "..."} }
"""
import json
import os
import time

BASE = os.path.dirname(os.path.abspath(__file__))
MANIFEST = os.path.join(BASE, "covers", "manifest.json")
SOURCES = os.path.join(BASE, "covers", "cover_sources.json")

# 形态优先级：竖图 > 方图（role 是 PS Store media 的字段名）
ROLE_PREF = ["PORTRAIT_BANNER", "MASTER"]
ROLE_CODE = {"PORTRAIT_BANNER": "P", "MASTER": "M"}

# 留边版（方图补虚化边到 3:4, 前端零裁切）
ROLE_PAD = "M-pad"        # 方图源 -> 上下补边留边版
ROLE_PAD_P = "P-pad"      # 竖图/其它源 -> 整图保留 + 左右补边留边版
PAD_BLUR = 40      # 背景高斯模糊半径
PAD_COLOR = 0.9    # 背景降饱和, 避免虚化色块抢眼

# 来源优先级：人工 > 港服中文页自动抓取
SRC_MANUAL = "manual"
SRC_STORE_ZH_HK = "store_zh_hk"
SOURCE_RANK = {SRC_MANUAL: 100, SRC_STORE_ZH_HK: 10}


def load_json(p, default):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def load_sources():
    return load_json(SOURCES, {})


def save_sources(src):
    # ★ 键必须 sorted 输出: 仓库既有文件为字典序, 保序写入会让新增键漂到末尾,
    #   造成整文件重排的千行噪声 diff（历史遗留问题, 2026-09-17 修正）
    src = {k: src[k] for k in sorted(src)}
    json.dump(src, open(SOURCES, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def load_manifest():
    return load_json(MANIFEST, {})


def save_manifest(m):
    # ★ indent=2 + 字典序，必须与仓库既有 covers/manifest.json 一致（autocover.py 也统一），
    #   否则每次写入都会整文件重排, 产生千行噪声 diff 并放大冲突面积
    m = {k: m[k] for k in sorted(m)}
    json.dump(m, open(MANIFEST, "w", encoding="utf-8"), ensure_ascii=False, indent=2)


def pick_role(media):
    """按「竖图 > 方图」挑选一张官方图
    media: [{"role": "MASTER"|"PORTRAIT_BANNER", "url": "...", "type": "IMAGE"}, ...]
    返回: (role, url)；都没有则返回 (None, None)
    """
    avail = {}
    for m in media or []:
        role = m.get("role")
        url = m.get("url") or ""
        if role in ROLE_PREF and url and (m.get("type") in (None, "IMAGE")):
            avail.setdefault(role, url)
    for role in ROLE_PREF:
        if avail.get(role):
            return role, avail[role]
    return None, None


def need_pad(role, media=None):
    """是否必须做留边版：命中方图且该商品没有竖图 -> True
    判据（2026-09-17 店主定稿）：无竖图时方图上线必被左右各裁 63px 原图像素，
    即便标题完整，画面边缘元素也常被裁 -> 一律留边，不再逐张目检。
    role : "MASTER" | "PORTRAIT_BANNER"
    media: 原始 media 列表（可选，用于再确认是否真的没竖图）
    """
    if role != "MASTER":
        return False
    if media:
        has_portrait = any(
            (m.get("role") == "PORTRAIT_BANNER" and m.get("url")) for m in media
        )
        if has_portrait:
            return False
    return True


def make_pad34(src_abs, dst_abs):
    """把方图(通常 504×504)做成 3:4 留边版：原图居中 + 上下各补虚化带
    配方与古墓丽影10 首例一致：
      背景 = 原图拉伸到 504×672 -> GaussianBlur(40) -> Color 0.9
      再把原图居中贴到画布 -> 成品 504×672 恰好 3:4，前端 object-fit:cover 零裁切
    依赖 Pillow；任何失败都返回 False（调用方应回退原图，不阻断流程）。
    """
    try:
        from PIL import Image, ImageFilter, ImageEnhance
    except Exception:
        return False
    try:
        im = Image.open(src_abs).convert("RGB")
        w, h = im.size
        if w <= 0 or h <= 0:
            return False
        # 目标 3:4：以原图宽度为基准，高度 = w * 4/3
        tw, th = w, int(round(w * 4 / 3))
        bg = im.resize((tw, th)).filter(ImageFilter.GaussianBlur(PAD_BLUR))
        bg = ImageEnhance.Color(bg).enhance(PAD_COLOR)
        canvas = bg.copy()
        canvas.paste(im, (0, (th - h) // 2))
        canvas.save(dst_abs, "JPEG", quality=92)
        return True
    except Exception:
        return False


def make_pad_auto(src_abs, dst_abs):
    """任意形态 -> 3:4 留边版（2026-09-18 店主定稿：全部封面一律留边，零裁切）
    方图(≈1:1)  : 等比到 504×504 居中 + 上下虚化补边 -> 504×672
    竖图/其它   : 整图等比缩放完整保留 + 左右虚化补边 -> 504×672（绝不裁掉任何内容）
    横图(w/h≥1.15): ★ 返回 False —— 不做留边，调用方直用原图
    已是 3:4    : 原样保存
    依赖 Pillow；失败返回 False（调用方应回退原图，不阻断部署）。
    """
    try:
        from PIL import Image, ImageFilter, ImageEnhance
    except ImportError:
        return False
    try:
        im = Image.open(src_abs).convert("RGB")
        w, h = im.size
        if w <= 0 or h <= 0:
            return False
        if abs(w * 4 - h * 3) <= 12:                 # 已是 3:4
            im.save(dst_abs, "JPEG", quality=92)
            return True
        # ★★ 2026-09-18 店主裁定：纯横版主视觉（如 504×284 的 EDITION_KEY_ART）
        #    补边后整图被压成扁扁一条、主体过小，反而难看 —— 这类直用原图，
        #    由前端按容器高度撑满、左右裁切，主体最大化。
        if w >= h * 1.15:
            return False
        bg = im.resize((504, 672), Image.LANCZOS).filter(ImageFilter.GaussianBlur(PAD_BLUR))
        bg = ImageEnhance.Color(bg).enhance(PAD_COLOR)
        canvas = bg.copy()
        if abs(w - h) <= max(w, h) * 0.05:           # 方图: 缩到 504 见方后上下补边
            fg = im.resize((504, 504), Image.LANCZOS)
            canvas.paste(fg, (0, (672 - 504) // 2))
        else:                                         # 竖图/横图: 整图完整保留, 居中
            scale = min(504.0 / w, 672.0 / h)
            fw, fh = int(round(w * scale)), int(round(h * scale))
            canvas.paste(im.resize((fw, fh), Image.LANCZOS), ((504 - fw) // 2, (672 - fh) // 2))
        canvas.save(dst_abs, "JPEG", quality=92)
        return True
    except Exception:
        return False


def cut_ratio(w, h):
    """前端 96×128（3:4）显示 w×h 的图时，上下各被裁掉的比例（相对图高）"""
    try:
        r = float(w) / float(h)
    except Exception:
        return 0.0
    cr = 0.5 * (1 - (4.0 / 3.0) * r)
    return cr if cr > 0 else 0.0


def _vision_bin():
    """macOS Vision OCR 小工具（自带坐标）。优先已编译的 /tmp/ocrbox，
    否则用仓库内 tools/ocrbox.swift 现编一个；非 macOS 返回 None。"""
    import shutil, subprocess
    for p in ("/tmp/ocrbox", os.path.join(BASE, "tools", "ocrbox")):
        if os.path.exists(p) and os.access(p, os.X_OK):
            return p
    sw = os.path.join(BASE, "tools", "ocrbox.swift")
    if os.path.exists(sw) and shutil.which("swiftc"):
        try:
            r = subprocess.run(["swiftc", "-O", sw, "-o", "/tmp/ocrbox"],
                               capture_output=True, timeout=180)
            if r.returncode == 0 and os.path.exists("/tmp/ocrbox"):
                return "/tmp/ocrbox"
        except Exception:
            pass
    return None


def text_boxes(path):
    """识别图中文字块，返回 [(x, y, w, h, text)]（x/y 为左上角，全部归一化 0~1）。
    取不到任何 OCR 能力时返回 None（None = 无法判定，调用方须保守处理）。
    优先级：macOS Vision（准） > pytesseract（CI Linux 备用）。"""
    import subprocess
    exe = _vision_bin()
    if exe:
        try:
            r = subprocess.run([exe, path], capture_output=True, timeout=60)
            for line in r.stdout.decode("utf-8", "replace").splitlines():
                try:
                    j = json.loads(line)
                except Exception:
                    continue
                iw, ih = float(j.get("w") or 0), float(j.get("h") or 0)
                out = []
                for b in j.get("blocks") or []:
                    if (b.get("c") or 0) < 0.3:
                        continue
                    out.append((float(b.get("x") or 0), float(b.get("y") or 0),
                                float(b.get("w") or 0), float(b.get("h") or 0),
                                b.get("t") or ""))
                if out:
                    return out
                return []
        except Exception:
            pass
    try:
        import pytesseract
        from PIL import Image
        im = Image.open(path)
        iw, ih = im.size
        d = pytesseract.image_to_data(im, lang="chi_sim+eng",
                                      output_type=pytesseract.Output.DICT)
        out = []
        for i, t in enumerate(d.get("text") or []):
            t = (t or "").strip()
            try:
                conf = float(d["conf"][i])
            except Exception:
                conf = -1
            if not t or conf < 30:
                continue
            out.append((float(d["left"][i]) / iw, float(d["top"][i]) / ih,
                        float(d["width"][i]) / iw, float(d["height"][i]) / ih, t))
        return out
    except Exception:
        return None


def decide_form(src_abs, boxes=None):
    """★★ 形态终版判定（2026-09-18 店主定稿）——自动抓图与人工换图唯一入口
    返回 (mode, info)
      mode = "pad"  做 3:4 留边版（零裁切）
      mode = "orig" 原图直上（前端按 object-fit:cover 裁切展示）
      mode = "keep" 已是 3:4，原样保存
    info 里给出尺寸/裁切比例/判定依据，写进 cover_sources.note 备查。
    """
    try:
        from PIL import Image
        w, h = Image.open(src_abs).size
    except Exception:
        return "pad", "无法读取尺寸, 保守留边"
    if w <= 0 or h <= 0:
        return "pad", "尺寸异常, 保守留边"
    if abs(w * 4 - h * 3) <= 12:
        return "keep", "已是 3:4 %dx%d, 原样" % (w, h)
    if w >= h * 1.15:                                   # ③ 纯横版
        return "orig", "纯横版 %dx%d, 原图直上(留边会把主体压扁)" % (w, h)
    if abs(w - h) <= max(w, h) * 0.05:                  # ① 方图
        return "pad", "方图 %dx%d, 留边版(前端会左右各裁 63px)" % (w, h)
    # ② 竖图：看前端上下裁切带里有没有文字/字母
    cr = cut_ratio(w, h)
    if boxes is None:
        boxes = text_boxes(src_abs)
    if boxes is None:
        return "pad", "竖图 %dx%d 上下各裁 %.1f%%, 无 OCR 能力, 保守留边" % (w, h, cr * 100)
    if not boxes:
        return "pad", "竖图 %dx%d 上下各裁 %.1f%%, 未识别到文字, 保守留边" % (w, h, cr * 100)
    lo, hi = cr + 0.006, 1 - cr - 0.006
    hit = [b[4] for b in boxes if b[1] < lo or (b[1] + b[3]) > hi]
    if hit:
        return "pad", "竖图 %dx%d 上下各裁 %.1f%%, 裁切带内有文字 %s" % (
            w, h, cr * 100, "、".join(hit[:3]))
    return "orig", "竖图 %dx%d 上下各裁 %.1f%%, 裁切带内无文字, 原图直上" % (w, h, cr * 100)


def install_cover(name, src_abs, source=SRC_MANUAL, store="", note="", tag=""):
    """按 decide_form() 落盘并登记（人工换图请用这个入口，自动抓图也可复用）
    tag: 参与文件名哈希的标记（换判定/重做时传不同 tag，保证换图必换名）
    返回 (ok, rel_path_or_msg)
    """
    import hashlib, shutil
    mode, info = decide_form(src_abs)
    if mode == "pad":
        suffix = "pad34" + ("|" + tag if tag else "")
        rel = "covers/rc%s.jpg" % hashlib.md5((name + "|" + suffix).encode()).hexdigest()[:12]
        if not make_pad_auto(src_abs, os.path.join(BASE, rel)):
            return False, "留边处理失败 " + info
        role = ROLE_PAD_P if "竖图" in info else ROLE_PAD
    elif mode == "keep":
        suffix = "keep" + ("|" + tag if tag else "")
        rel = "covers/rc%s.jpg" % hashlib.md5((name + "|" + suffix).encode()).hexdigest()[:12]
        shutil.copy(src_abs, os.path.join(BASE, rel))
        role = "P"
    else:  # orig
        suffix = "orig" + ("|" + tag if tag else "")
        rel = "covers/rc%s.jpg" % hashlib.md5((name + "|" + suffix).encode()).hexdigest()[:12]
        shutil.copy(src_abs, os.path.join(BASE, rel))
        role = "M" if "横版" in info else "P"
    full = (note + " · " if note else "") + info
    return set_cover(name, rel, source, role, store, full)


def is_protected(name):
    """该封面是否受保护(=人工制定)，保护措施：不允许任何自动流程改动"""
    src = load_sources()
    rec = src.get(name)
    if rec:
        return rec.get("source") == SRC_MANUAL
    # 无记录但 manifest 已有封面 -> 保守视作人工（历史数据）
    m = load_manifest()
    return bool(m.get(name))


def guard(name, source):
    """写入前拦截：(ok, reason)
    - 新写入任何来源都允许
    - 已存在 manual 记录时，除 manual 外的来源一律拒绝
    - 已是 store_zh_hk 记录时，manual 允许覆盖（人工优先），同来源也允许（如修 bug）
    """
    src = load_sources()
    rec = src.get(name)
    if not rec:
        m = load_manifest()
        if m.get(name) and source != SRC_MANUAL:
            return False, "manifest 已有封面且无来源记录, 保守视作人工维护 (%s)" % m[name]
        return True, ""
    old = rec.get("source")
    if old == SRC_MANUAL and source != SRC_MANUAL:
        return False, "已登记为人工封面, 禁止自动流程覆盖 (%s)" % rec.get("file")
    return True, ""


def set_cover(name, rel_path, source, role="", store="", note=""):
    """统一写 manifest + cover_sources，并做保护校验
    rel_path: 'covers/xxx.jpg'
    source  : manual | store_zh_hk
    role    : P(竖) | M(方)
    返回 (ok, msg)
    """
    ok, why = guard(name, source)
    if not ok:
        return False, why
    m = load_manifest()
    m[name] = rel_path
    save_manifest(m)
    src = load_sources()
    src[name] = {
        "file": rel_path,
        "source": source,
        "role": role,
        "store": store,
        "time": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "note": note,
    }
    save_sources(src)
    return True, rel_path


def remove_old(m, old_rel):
    """旧图确认不再被任何键引用后才删除"""
    if not old_rel:
        return None
    keep = {os.path.normpath(v) for v in m.values() if v}
    p = os.path.normpath(old_rel)
    if p in keep:
        return None
    fp = os.path.join(BASE, old_rel)
    if os.path.exists(fp):
        os.remove(fp)
        return old_rel
    return None


def stats():
    src = load_sources()
    from collections import Counter
    return Counter(v.get("source") for v in src.values())


if __name__ == "__main__":
    print("cover_policy 优先级: 1) 人工 > 自动  2) 港服中文页 > 其它来源  3) 竖图 2:3 > 方图 1:1")
    print("记录数:", len(load_sources()), dict(stats()))
