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

   ★★ 补充铁律（2026-09-17 店主定稿）：**没有竖图、只能用官方方图时，一律先做成「留边版」再入库**
   —— 前端卡片是 96×128（3:4）`object-fit:cover`，方图 1:1 上线必然被左右各裁掉 63px 原图像素，
      即便标题/Logo 侥幸没被切，画面边缘元素（角标、装饰、构图主体）也常被裁掉（店主多次反馈"有遮挡"）。
      因此判定标准从「标题有没有被切」收紧为：**只要无竖图 → 直接留边版（M-pad），零裁切。**
      留边版配方见 `make_pad34()`，role 记 `M-pad`。

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
ROLE_PAD = "M-pad"
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
