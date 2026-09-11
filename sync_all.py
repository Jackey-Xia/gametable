#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""云端同步总入口: fetch(可选) -> parse -> build data.js
本地用法:  python3 sync_all.py                 (仅用已有 data/ 导出解析重建)
云端用法:  python3 sync_all.py --fetch         (先调 WPS API 拉表再解析)
"""
import json, os, subprocess, sys

BASE = os.path.dirname(os.path.abspath(__file__))
FILE_ID = os.environ.get("GT_FILE_ID", "RyUrbsiPh1MJwyApToNorxCM7reggrwFc")
PS_WID = os.environ.get("GT_PS_WID", "3")
PS_ROWS = int(os.environ.get("GT_PS_ROWS", "1971"))

def run(cmd, env=None):
    print(">>", " ".join(cmd))
    e = os.environ.copy()
    if env:
        e.update(env)
    subprocess.run(cmd, check=True, cwd=BASE, env=e)

if "--fetch" in sys.argv:
    exp = os.path.join(BASE, "data", "kdc_export.json")
    try:
        run(["python3", "fetch_wps.py", FILE_ID, PS_WID, str(PS_ROWS), "auto", exp])
    except subprocess.CalledProcessError:
        print("!! WPS API 拉取失败, 回退用仓库内置快照继续构建（线上保持旧数据不中断）")
        if not os.path.exists(exp):
            print("!! 无本地导出, 跳过 parse, 直接用已有 ps_games.json 构建")

ps_json = os.path.join(BASE, "data", "ps_games.json")
exp_json = os.path.join(BASE, "data", "kdc_export.json")
grid_json = os.path.join(BASE, "data", "ps_grid.json")   # AirScript 云端脚本直推(首选)
if os.path.exists(grid_json):
    run(["python3", "parse_ps.py", grid_json, ps_json])
elif os.path.exists(exp_json):
    run(["python3", "parse_ps.py", exp_json, ps_json])
elif not os.path.exists(ps_json):
    raise SystemExit("既无导出也无快照, 无法构建")
run(["python3", "build_data.py"])

# 组装 Pages 站点目录: index.html + 最新 data.js
import shutil
site = os.path.join(BASE, "site")
os.makedirs(site, exist_ok=True)
shutil.copyfile(os.path.join(BASE, "data.js"), os.path.join(site, "data.js"))
shutil.copyfile(os.path.join(BASE, "index.html"), os.path.join(site, "index.html"))
# 改75: 拼音映射(同音搜索), 由 gen_pinyin.py 生成
pyjs = os.path.join(BASE, "pinyin.js")
if os.path.exists(pyjs):
    shutil.copyfile(pyjs, os.path.join(site, "pinyin.js"))
# 改70: Service Worker (封面本地锁存)
sw = os.path.join(BASE, "sw.js")
if os.path.exists(sw):
    shutil.copyfile(sw, os.path.join(site, "sw.js"))
av = os.path.join(BASE, "avatar.jpg")
if os.path.exists(av):
    shutil.copyfile(av, os.path.join(site, "avatar.jpg"))
bg = os.path.join(BASE, "bg.jpg")
if os.path.exists(bg):
    shutil.copyfile(bg, os.path.join(site, "bg.jpg"))
# 改68: 封面目录整体同步 (covers/manifest.json + 图片) 到 Pages 站点
cv_src = os.path.join(BASE, "covers")
if os.path.isdir(cv_src):
    cv_dst = os.path.join(site, "covers")
    if os.path.isdir(cv_dst):
        shutil.rmtree(cv_dst)
    shutil.copytree(cv_src, cv_dst, ignore=shutil.ignore_patterns("*.pyc"))
    print("covers/ 已同步:", len([f for f in os.listdir(cv_dst) if f.endswith(".jpg")]), "张")
print("sync_all 完成, site/ 已就绪")
