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

def _inject_sw_cache(site_dir):
    """改2026-11-22复核5: 把 sw.js 的 CACHE 常量从 ver.json 的 v 派生(md5[:8])。
    - 真发版(bump v) -> 派生名变 -> 浏览器装新 SW -> activate 清旧缓存 -> 老客首开即新页;
    - cron 每小时重建但 v 不变 -> 派生名不变 -> sw.js 字节不变 -> 不重装 SW -> 老客 0 成本。
    用 md5 而非时间戳: 时间戳每次 cron 都变, 等于每小时清一次缓存, 把 0 成本访问变 106KB 下载。"""
    import re as _re, json as _json, os as _os, hashlib as _hl
    vp = _os.path.join(site_dir, "ver.json")
    sp = _os.path.join(site_dir, "sw.js")
    if not (_os.path.exists(vp) and _os.path.exists(sp)):
        raise SystemExit("!! SW CACHE 注入前置缺失: %s / %s" % (vp, sp))
    v = str(_json.load(open(vp, encoding="utf-8")).get("v") or "").strip()
    if not v:
        raise SystemExit("!! ver.json 缺 v, 拒绝发布(SW 缓存名无法派生)")
    cache_name = "gt-sw-v" + _hl.md5(v.encode("utf-8")).hexdigest()[:8]
    sw = open(sp, encoding="utf-8").read()
    cnt = {"cache": 0}
    def rep(m):
        cnt["cache"] += 1
        return m.group(1) + cache_name + m.group(2)
    sw = _re.sub(r"(const CACHE = ')[^']*(';)", rep, sw)
    if cnt["cache"] != 1:
        raise SystemExit("!! sw.js CACHE 常量命中 %d 次(应恰好1次), 拒绝发布" % cnt["cache"])
    open(sp, "w", encoding="utf-8").write(sw)
    print("sw.js CACHE 已按 v 派生:", cache_name)

def _inject_versions(site_dir):
    """改2026-11-22: 把 site/ver.json 的 v / data_v 写进 site/index.html 的
    __GT_PAGE_VER / __GT_DATA_VER。这两个值前端用来判定"页面/数据是否过期",
    必须与 ver.json 完全一致, 否则 gt-autorefresh 每会话都会判"发现新版本"
    并空刷 1~3 次整页(实测 gt_vn=2)。"""
    import re as _re, json as _json, os as _os
    vp = _os.path.join(site_dir, "ver.json")
    hp = _os.path.join(site_dir, "index.html")
    if not (_os.path.exists(vp) and _os.path.exists(hp)):
        raise SystemExit("!! 版本注入前置缺失: %s / %s" % (vp, hp))
    _vj = _json.load(open(vp, encoding="utf-8"))
    v = str(_vj.get("v") or "").strip()
    dv = str(_vj.get("data_v") or v).strip()
    if not v or not dv:
        raise SystemExit("!! ver.json 缺少 v / data_v, 拒绝发布(否则前端版本自检失效)")
    html = open(hp, encoding="utf-8").read()
    cnt = {"data": 0, "page": 0}
    def rep_data(m):
        cnt["data"] += 1
        return m.group(1) + dv + m.group(2)
    def rep_page(m):
        cnt["page"] += 1
        return m.group(1) + v + m.group(2)
    html = _re.sub(r'(window\.__GT_DATA_VER=")[^"]*(")', rep_data, html)
    html = _re.sub(r'(window\.__GT_PAGE_VER=")[^"]*(")', rep_page, html)
    if cnt["data"] != 1 or cnt["page"] != 1:
        raise SystemExit("!! index.html 版本注入异常: DATA_VER=%d 次, PAGE_VER=%d 次 (各应恰好 1 次)"
                         % (cnt["data"], cnt["page"]))
    open(hp, "w", encoding="utf-8").write(html)
    print("index.html 版本已注入: data_v=%s v=%s" % (dv, v))

def _assert_sw_structure(site_dir):
    """改2026-11-23复核7: 固化「删 clear 安全」的全部前提 —— sw.js 三件套必须齐全。
    skipWaiting(install 立即激活) + clients.claim(activate 接管已开页面) + activate 删旧 CACHE。
    任一缺失 -> 老客在同一会话内换不到新版(只能等下次冷开), 故 fail-closed 拒绝发布。
    检查注入后的 site/sw.js(CACHE 名已被替换, 但三件套的语句结构不变)。"""
    import os as _os, re as _re
    sp = _os.path.join(site_dir, "sw.js")
    sw = open(sp, encoding="utf-8").read()
    checks = (
        ("skipWaiting", r"skipWaiting\s*\("),
        ("clients.claim", r"clients\.claim\s*\("),
        ("activate 删旧 CACHE", r"keys\.filter"),
        ("CACHE 排除条件", r"!==\s*CACHE"),
    )
    missing = [name for name, pat in checks if not _re.search(pat, sw)]
    if missing:
        raise SystemExit("!! sw.js 结构断言失败: 缺 %s — 删 clear 的前提不成立, 老客本会话换不到新版, 拒绝发布" % "、".join(missing))
    print("sw.js 结构断言 PASS: skipWaiting / clients.claim / activate 删旧 CACHE 三件套齐全")

def _git_changed_index_or_sw(base_dir):
    """降级判据(仅在完全取不到线上 ver.json 时用): 本次发布是否改了 index.html/sw.js 但没 bump ver.json 的 v。
    ★复核9-③: 判据区间用 GitHub 提供的 before..sha, 不再用 HEAD~1:
      - HEAD~1 在「一次 push 推多个 commit」只看到最后一个 commit(漏判前面几个);
      - cron / workflow_dispatch 触发时 HEAD~1 与本次要不要发布无关(HEAD 根本没变)。
      before = github.event.before(push 前的 HEAD), sha = github.sha, 由 deploy.yml 经 env 传入(GT_BEFORE/GT_SHA)。
      ★cron/dispatch 时 before 为空 -> 直接放行+告警, 绝不拿 HEAD~1 顶替(那是误判源)。
    返回 (changed, detail); 取不到基线/before 为空/非 git -> (False, 原因), 调用方按可用性优先放行+告警。"""
    import subprocess as _sp, os as _os, re as _re
    before = (_os.environ.get("GT_BEFORE") or "").strip()
    sha = (_os.environ.get("GT_SHA") or "").strip()
    if before and set(before) == {"0"}:   # 首次推新分支, before 全 0 = 无基线
        before = ""
    if not before or not sha:
        return False, ("cron/dispatch 或无 git 基线(before=%r sha=%r), 放行+告警 — 不用 HEAD~1 顶替"
                       % (before[:12], sha[:12]))
    rng = before + ".." + sha
    try:
        r = _sp.run(["git", "diff", rng, "--name-only"],
                    cwd=base_dir, capture_output=True, text=True, timeout=15)
        if r.returncode != 0:
            return False, "git diff %s 不可用(%s)" % (rng, (r.stderr.strip()[:80] or "区间对象不在本地"))
        files = [x.strip() for x in r.stdout.splitlines() if x.strip()]
        touched = [f for f in files if f.endswith("/index.html") or f == "index.html"
                   or f.endswith("/sw.js") or f == "sw.js"]
        if not touched:
            return False, "区间 %s 未改 index.html/sw.js" % rng
        # 改了 index/sw: 再看同一区间是否也 bump 了 ver.json 的 v。
        # diff 里 v 行变化形如 '- "v": "old"' / '+ "v": "new"', 故统计以 '+ ' 或 '- ' 开头的含 "v": 行。
        rv = _sp.run(["git", "diff", rng, "--", "ver.json"],
                     cwd=base_dir, capture_output=True, text=True, timeout=15)
        vlines = [ln for ln in rv.stdout.splitlines() if _re.match(r'^[+-].*"v"\s*:', ln)]
        bumped = len(vlines) >= 2
        if bumped:
            return False, "区间 %s 改了 %s 且 ver.json.v 同步变(已 bump)" % (rng[:24], ",".join(touched))
        return True, "区间 %s 改了 %s 但 ver.json.v 未变" % (rng[:24], ",".join(touched))
    except Exception as e:
        return False, "git 判据异常(%s)" % e

def _read_local_idxbase(base_dir):
    """复核10: 读 actions/cache 恢复的「上次成功发布基线」(.gt_idxbase.json)。
    deploy.yml 在成功构建后把 site/ver.json 的 v/idx_v/sw_v 写成此文件并存入 actions/cache;
    下次 run 开始时 restore 到工作区。路径可由 env GT_IDXBASE 覆盖(测试用)。
    返回 dict{v,idx_v,sw_v} 或 None(无文件/损坏)。"""
    import os as _os, json as _json
    p = (_os.environ.get("GT_IDXBASE") or "").strip() or _os.path.join(base_dir, ".gt_idxbase.json")
    try:
        if _os.path.exists(p):
            d = _json.load(open(p, encoding="utf-8"))
            return d if isinstance(d, dict) else None
    except Exception:
        pass
    return None

def _summary_write(text):
    """复核19/20: 写 GitHub job summary(可观测性)。本地无 GITHUB_STEP_SUMMARY 时静默返回, 零副作用。
    ★复核20: ①写入失败(环境变量缺失/权限异常/磁盘满)只打印一行, 绝不让它把发布带失败;
    ②单次写入上限 14 行, 只写分支/结论/v/指纹/原因这类要点, 不把逐条 key 或全部指纹倒进 Summary,
       防刷屏也防日志里暴露无关数据。首次写入自动加一个总标题(进程内标志, 一次 CI run 只加一次)。"""
    try:
        import os as _o
        p = _o.environ.get("GITHUB_STEP_SUMMARY", "").strip()
        if p:
            lines = str(text).rstrip().splitlines()
            if len(lines) > 14:
                lines = lines[:14] + ["…（其余省略，详见 Actions 日志）"]
            with open(p, "a", encoding="utf-8") as f:
                if not getattr(_summary_write, "_titled", False):
                    f.write("## GameTable CI 门禁报告（dry_run 同样生成）— ⚠️ 复核26：只证明门禁放行，不证明已上线（上线判据见文末 GT_PUBLISH 行）\n\n")
                    _summary_write._titled = True
                f.write("\n".join(lines) + "\n\n")
    except Exception as e:
        print("!! job summary 写入失败（已忽略，不影响发布）: %s" % e)


def _assert_idx_bump(site_dir, base_dir):
    """改2026-11-23复核8: 防止「改了 index.html/sw.js 却没 bump v」(CACHE 由 v 派生的配套门禁)。
    ★两侧 hash 都取「注入后的最终产物」site/index.html + site/sw.js, 口径一致(产物才是老客拿到的字节)。
    三支判定(复核8-③, 消除 fail-closed 的可用性单点):
      分支A 线上有 idx_v  -> md5 产物指纹比对; 指纹变而 v 没 bump 则拒发(主判据)。
      分支B 取到 ver.json 但无 idx_v -> bootstrap 放行 + 写基线; 首版本身无保护, 注释/发布单标注。
      分支C 完全取不到 ver.json(3次重试失败) -> 降级 git 判据: 本次 commit 改了 index/sw 而 v 没变则拒发+告警;
            否则放行+告警(不因网络抖动每小时拦死 cron)。本地(无 GITHUB_ACTIONS)一律只警告不拦。"""
    import hashlib as _hl, json as _json, os as _os, time as _time, urllib.request as _ur
    hp = _os.path.join(site_dir, "index.html")   # 注入后产物
    sp = _os.path.join(site_dir, "sw.js")        # 注入后产物
    if not (_os.path.exists(hp) and _os.path.exists(sp)):
        raise SystemExit("!! idx_v 断言前置缺失: %s / %s" % (hp, sp))
    idx_now = _hl.md5(open(hp, "rb").read()).hexdigest()[:12]
    sw_now = _hl.md5(open(sp, "rb").read()).hexdigest()[:12]
    vp = _os.path.join(site_dir, "ver.json")
    vj = _json.load(open(vp, encoding="utf-8"))
    v = str(vj.get("v") or "").strip()
    vj["idx_v"] = idx_now                          # 注: 首次发布线上无基线, 本次为种基线版(无保护)
    vj["sw_v"] = sw_now
    with open(vp, "w", encoding="utf-8") as f:
        _json.dump(vj, f, ensure_ascii=False, indent=1)
    print("ver.json 已写入产物指纹 idx_v=%s sw_v=%s (同次发布上线; 首次种基线版自身无基线保护)" % (idx_now, sw_now))
    in_ci = bool(_os.environ.get("GITHUB_ACTIONS"))
    live = None; err = None
    for attempt in range(3):
        try:
            req = _ur.Request("https://jackey-xia.github.io/gametable/ver.json?cb=" + idx_now + str(attempt),
                              headers={"Cache-Control": "no-store", "User-Agent": "GT-CI-idx-check/1.0"})
            with _ur.urlopen(req, timeout=8) as r:
                live = _json.loads(r.read().decode("utf-8"))
            break
        except Exception as e:
            err = e
            if attempt < 2: _time.sleep(2)

    def reject(msg, branch="?", online_v=""):
        # 复核20: 拒发出口补分支标记 —— 上线后第2步要凭 Summary 确认"真的是 A 支拒发", 不能只看"拒发"二字。
        _summary_write("### idx_v 门禁判定\n\n- **分支**：%s\n- **结论**：拒发\n- v（本次 / 线上）：`%s` / `%s`\n- idx_v now：`%s`，sw_v now：`%s`\n- 原因：%s"
                       % (branch, v[:24], str(online_v)[:24], idx_now, sw_now, msg))
        if in_ci: raise SystemExit("!! " + msg)
        print("!! 警告(本地不拦): " + msg)

    # 分支C(复核10修正): 完全取不到线上 ver.json = 最坏时机(CI 连自己站点都拉不到)。
    # ★权重修正: 原逻辑「无可疑改动就放行」方向反了 —— cron 正常走 A 支(能拉到 ver.json 且有 idx_v),
    #   C 支只在拉不到基线时触发; 此时放行一个「内容改了/v没bump/CACHE名不变/MY不变」的产物,
    #   老客永久看不到新代码且不自动恢复(停更1小时可恢复, 这个不行)。
    # 新判据: 先读 actions/cache 恢复的上次成功基线做 md5 比对; 本地缓存也没有 -> 拒发+告警。
    if not isinstance(live, dict):
        local = _read_local_idxbase(base_dir)
        if isinstance(local, dict) and str(local.get("idx_v") or "").strip():
            lp_v = str(local.get("v") or "").strip()
            for label, key, now in (("index.html", "idx_v", idx_now), ("sw.js", "sw_v", sw_now)):
                prev = str(local.get(key) or "").strip()
                if prev and prev != now and lp_v and v == lp_v:
                    reject("取不到线上 ver.json; 用 actions/cache 本地基线比对: %s 指纹已变(%s %s->%s)但 v 未 bump(基线/本次都是 %s)。请 bump v 再发布"
                           % (label, key, prev, now, v), "C")
            print("!! 分支C: 取不到线上 ver.json, 用 actions/cache 本地基线(v=%s, idx_v=%s)比对无异常, 放行"
                  % (lp_v[:24], str(local.get("idx_v"))[:12]))
            _summary_write("### idx_v 门禁判定\n\n- **分支**：C（取不到线上 ver.json，用 actions/cache 本地基线）\n- **结论**：放行\n- v（本次 / 基线）：`%s` / `%s`\n- idx_v now / prev：`%s` / `%s`\n- sw_v now / prev：`%s` / `%s`"
                           % (v[:24], lp_v[:24], idx_now, str(local.get("idx_v"))[:12], sw_now, str(local.get("sw_v"))[:12]))
        else:
            reject("取不到线上 ver.json(%s), 且 actions/cache 无上次成功发布的 idx_v/sw_v 基线 — 无法核实 index/sw 变更是否伴随 bump v, 拒发(网络恢复或基线就绪后重试)" % err, "C")
        return

    lv = str(live.get("v") or "").strip()
    seeded = bool(str(live.get("idx_v") or "").strip())
    # 分支B: 取到了 ver.json 但没有 idx_v 字段 = 首次种基线, 放行(首版无保护)
    if not seeded:
        print("!! 线上 ver.json 无 idx_v/sw_v 基线 — 分支B bootstrap 放行并写入基线, 首版自身无保护; 下一版起生效")
        _summary_write("### idx_v 门禁判定\n\n- **分支**：B（线上无 idx_v/sw_v，首次种基线）\n- **结论**：放行（首版自身无保护，下一版起 A 支生效）\n- v（本次 / 线上）：`%s` / `%s`\n- idx_v now：`%s`，sw_v now：`%s`"
                       % (v[:24], lv[:24], idx_now, sw_now))
        return
    # 分支A: 有基线, 产物指纹比对
    for label, key, now in (("index.html", "idx_v", idx_now), ("sw.js", "sw_v", sw_now)):
        prev = str(live.get(key) or "").strip()
        if not prev:
            continue
        if prev != now and lv and v == lv:
            reject("%s 产物指纹已变(%s %s->%s)但 v 未 bump(线上/本次都是 %s)。请 bump ver.json 的 v 再发布"
                   % (label, key, prev, now, v), "A", lv)
    # 走到这里 = 分支A 全部通过
    _summary_write("### idx_v 门禁判定\n\n- **分支**：A（线上有基线，产物指纹比对）\n- **结论**：放行\n- v（本次 / 线上）：`%s` / `%s`\n- idx_v now / 线上：`%s` / `%s`\n- sw_v now / 线上：`%s` / `%s`"
                   % (v[:24], lv[:24], idx_now, str(live.get("idx_v") or "")[:12], sw_now, str(live.get("sw_v") or "")[:12]))

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
# 扫码登录助手页（独立工具页，长期可访问）
ql = os.path.join(BASE, "qr-login.html")
if os.path.exists(ql):
    shutil.copyfile(ql, os.path.join(site, "qr-login.html"))
# 改75: 拼音映射(同音搜索), 由 gen_pinyin.py 生成
pyjs = os.path.join(BASE, "pinyin.js")
if os.path.exists(pyjs):
    shutil.copyfile(pyjs, os.path.join(site, "pinyin.js"))
# 改70: Service Worker (封面本地锁存)
sw = os.path.join(BASE, "sw.js")
if os.path.exists(sw):
    shutil.copyfile(sw, os.path.join(site, "sw.js"))
# 版本号文件(页面自动刷新机制用): 每次改版必须更新 ver.json 的 v 值
# 改164: WPS 价格库存同步后把 data.js 的 synced 注入 site/ver.json。
#        前端据此判定 IndexedDB 缓存是否过期, 并给 data.js 请求拼 &s=<synced> 绕开 HTTP/SW 缓存;
#        没有这一步, 手机/微信老客在 WPS 表改价改库存后会一直看到旧数据。
vj = os.path.join(BASE, "ver.json")
if os.path.exists(vj):
    dst_vj = os.path.join(site, "ver.json")
    try:
        import re as _re
        with open(vj, encoding="utf-8") as _f:
            _ver = json.load(_f)
        _js = open(os.path.join(BASE, "data.js"), encoding="utf-8").read()
        _m = _re.search(r'"synced"\s*:\s*"([^"]*)"', _js)
        if _m and _m.group(1):
            _ver["synced"] = _m.group(1)
        # 改167-3: 把封面清单 / 淘宝表的内容指纹写进 ver.json。
        #   老客 IDB 里存有 gt_cover_map + gt_cover_v / gt_taobao + __v,
        #   指纹一致即可跳过 manifest(约30KB) 与 taobao(约97KB) 的重下; 内容一变指纹就变。
        import hashlib as _hash
        def _fp(*_paths):
            _hh = _hash.md5()
            for _pp in _paths:
                _qq = os.path.join(BASE, _pp)
                if os.path.exists(_qq):
                    with open(_qq, "rb") as _fb:
                        _hh.update(_fb.read())
            return _hh.hexdigest()[:12]
        _ver["cover_v"] = _fp("covers/manifest.json", "covers/manifest_ps.json")
        _ver["tb_v"] = _fp("data/taobao.json")
        print("ver.json 已注入 cover_v/tb_v:", _ver.get("cover_v"), _ver.get("tb_v"))
        with open(dst_vj, "w", encoding="utf-8") as _f:
            json.dump(_ver, _f, ensure_ascii=False, indent=1)
        print("ver.json 已注入 synced:", _ver.get("synced"))
    except Exception as _e:
        print("ver.json 注入 synced 失败, 回退原样拷贝:", _e)
        shutil.copyfile(vj, dst_vj)
# 改2026-11-22: 版本注入 + 断言。此步失败 => sync_all.py 非 0 退出 => job 失败 => 不发布(线上保持旧版本)
_inject_versions(site)
_inject_sw_cache(site)   # 改2026-11-22复核5: SW 缓存名由 v 派生
_assert_sw_structure(site)     # 改2026-11-23复核7: sw.js skipWaiting/claim/删旧CACHE 三件套缺一拒发
_assert_idx_bump(site, BASE)   # 改2026-11-23复核7: 注入后产物指纹; 改 index/sw 未 bump v 拒发; CI fail-closed
av = os.path.join(BASE, "avatar.jpg")
if os.path.exists(av):
    shutil.copyfile(av, os.path.join(site, "avatar.jpg"))
avp = os.path.join(BASE, "avatar.png")
if os.path.exists(avp):
    shutil.copyfile(avp, os.path.join(site, "avatar.png"))
avog = os.path.join(BASE, "avatar-og.png")
if os.path.exists(avog):
    shutil.copyfile(avog, os.path.join(site, "avatar-og.png"))
avf = os.path.join(BASE, "avatar_fill.png")
if os.path.exists(avf):
    shutil.copyfile(avf, os.path.join(site, "avatar_fill.png"))
avof = os.path.join(BASE, "avatar-og_fill.png")
if os.path.exists(avof):
    shutil.copyfile(avof, os.path.join(site, "avatar-og_fill.png"))
ogp = os.path.join(BASE, "og-share.png")
if os.path.exists(ogp):
    shutil.copyfile(ogp, os.path.join(site, "og-share.png"))
ic = os.path.join(BASE, "icon.png")
if os.path.exists(ic):
    shutil.copyfile(ic, os.path.join(site, "icon.png"))
bg = os.path.join(BASE, "bg.jpg")
if os.path.exists(bg):
    shutil.copyfile(bg, os.path.join(site, "bg.jpg"))
# 改h5: hero 桌面背景 + 标语图层
for _n in ("bg-d.jpg", "slogan-m.png", "slogan-d.png"):
    _p = os.path.join(BASE, _n)
    if os.path.exists(_p):
        shutil.copyfile(_p, os.path.join(site, _n))
# 改114: 页头封面随 tab 切换(会员资费/PS白金 主题大图)
for _b in ("banner_mem.jpg", "banner_plat.jpg"):
    _bp = os.path.join(BASE, _b)
    if os.path.exists(_bp):
        shutil.copyfile(_bp, os.path.join(site, _b))
# 改130: 淘宝商品链接表(商品卡片「去淘宝下单」按钮用) -> 站点根目录 taobao.json
tb = os.path.join(BASE, "data", "taobao.json")
if os.path.exists(tb):
    shutil.copyfile(tb, os.path.join(site, "taobao.json"))
    print("taobao.json 已同步")
# 改154: 游戏详情数据(查看详情弹层图文) -> 站点根目录 game_details.json
gd = os.path.join(BASE, "data", "game_details.json")
if os.path.exists(gd):
    shutil.copyfile(gd, os.path.join(site, "game_details.json"))
    print("game_details.json 已同步")
# 改134: 淘宝中转页(只靠商品id跳转, 不依赖会过期的短链) -> 站点根目录 tb.html
_tbh = os.path.join(BASE, "tb.html")
if os.path.exists(_tbh):
    shutil.copyfile(_tbh, os.path.join(site, "tb.html"))
# 改68: 封面目录整体同步 (covers/manifest.json + 图片) 到 Pages 站点
cv_src = os.path.join(BASE, "covers")
if os.path.isdir(cv_src):
    cv_dst = os.path.join(site, "covers")
    if os.path.isdir(cv_dst):
        shutil.rmtree(cv_dst)
    shutil.copytree(cv_src, cv_dst, ignore=shutil.ignore_patterns("*.pyc"))
    print("covers/ 已同步:", len([f for f in os.listdir(cv_dst) if f.endswith(".jpg")]), "张")

# 用户上传的截图画廊图片（与 covers 分离，避免干扰封面清单/自动抓取逻辑）
sh_src = os.path.join(BASE, "shots")
if os.path.isdir(sh_src):
    sh_dst = os.path.join(site, "shots")
    if os.path.isdir(sh_dst):
        shutil.rmtree(sh_dst)
    shutil.copytree(sh_src, sh_dst, ignore=shutil.ignore_patterns("*.pyc"))
    print("shots/ 已同步:", len([f for f in os.listdir(sh_dst) if f.endswith(".jpg")]), "张")
# 审核预览目录（如 pad_review/）原样带上站点
for extra in ("pad_review", "blank_review"):
    ex_src = os.path.join(BASE, extra)
    if os.path.isdir(ex_src):
        shutil.copytree(ex_src, os.path.join(site, extra), dirs_exist_ok=True)
        print(extra + "/ 已同步")
print("sync_all 完成, site/ 已就绪")
