#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""详情分片 CI 门禁（2026-11-22 复核5 新增）
把「桶号一致性」从手工验证固化成构建期硬断言。split_details.py 之后运行。
校验三件事, 任一不过 -> SystemExit 非0 -> CI job 失败 -> 不发布:
  1. 分片 key 并集 == 整包 game_details.json 的 key 集合(无缺/无多/无跨片重复)
  2. 每条 key 的桶号 == 所在分片文件名桶号(ord(key[0])%64 == pNN)
  3. 用 data.js 的商品过 gtFindDet 同序回退链后, 商品名首字符桶号 == 命中 key 桶号
     (否则分片 100% 落空、全部回落整包, 优化白做)
改分桶规则 / 改 gtFindDet 回退链 / 改名逻辑前, 此门禁会先拦住。
"""
import glob, json, os, re, sys

BASE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(BASE, "data", "game_details.json")
SHARD_DIR = os.path.join(BASE, "site", "details")
DATA_JS = os.path.join(BASE, "data.js")
NBUCKET = 64

def die(msg, code=1):
    """code=1 通用分片失败；code=4 专用于「480 宽度 URL 禁令」，便于 CI 日志与重跑策略区分。"""
    print("!! 分片门禁失败:", msg)
    sys.exit(code)

def bucket_of(name):
    return (ord(name[0]) if name else 0) % NBUCKET


def _walk_urls(node, out):
    """封面清单的值可能是 str / list / 嵌套 dict，统一摊平成 URL 字符串列表。"""
    if isinstance(node, str):
        out.append(node)
    elif isinstance(node, list):
        for x in node:
            _walk_urls(x, out)
    elif isinstance(node, dict):
        for x in node.values():
            _walk_urls(x, out)

def main():
    if not os.path.exists(SRC):
        die("缺 data/game_details.json")
    if not os.path.isdir(SHARD_DIR):
        die("缺 site/details/ 分片目录")
    whole = json.load(open(SRC, encoding="utf-8"))

    # --- 1 & 2: 分片并集一致 + 桶号归位 ---
    union = {}
    shard_files = sorted(f for f in os.listdir(SHARD_DIR) if re.fullmatch(r"p\d{2}\.json", f))
    if not shard_files:
        die("site/details/ 无 pNN.json 分片")
    for fn in shard_files:
        b_file = int(re.match(r"p(\d{2})\.json", fn).group(1))
        mp = json.load(open(os.path.join(SHARD_DIR, fn), encoding="utf-8"))
        for k, v in mp.items():
            if k in union:
                die("key 跨片重复: %s(在 %s 与 %s)" % (k, union[k][0], fn))
            if bucket_of(k) != b_file:
                die("桶号错位: key=%s 算得 p%02d 却在 %s" % (k, bucket_of(k), fn))
            union[k] = (fn, v)
    missing = set(whole) - set(union)
    extra = set(union) - set(whole)
    if missing:
        die("分片缺 %d 条 key: %s" % (len(missing), list(missing)[:5]))
    if extra:
        die("分片多 %d 条 key: %s" % (len(extra), list(extra)[:5]))
    # 内容也要逐条一致
    for k in whole:
        if union[k][1] != whole[k]:
            die("分片内容与整包不符: %s" % k)
    print("门禁1/2 PASS: 分片 %d 片, key %d 条, 并集一致且桶号归位" % (len(shard_files), len(union)))

    # --- 3: data.js 商品回退链桶号一致 ---
    if not os.path.exists(DATA_JS):
        die("缺 data.js(商品名桶号校验需要)")
    js = open(DATA_JS, encoding="utf-8").read()
    marker = "window.GT_DATA="
    i = js.find(marker)
    if i < 0:
        die("data.js 无 window.GT_DATA=")
    raw = js[i + len(marker):].strip().rstrip(";").strip()
    data = json.loads(raw)
    games = []
    for grp in ("ps", "ns"):
        games.extend(data.get(grp, []))
    keys = set(whole)

    def find_key(g):
        n = g.get("name", "") or ""
        if g.get("region"):
            rk = n + "（" + re.sub(r"\s", "", str(g["region"])) + "）"
            if rk in keys:
                return rk
        if n in keys:
            return n
        m = re.match(r"^(.*?)(\d+)$", n)
        if m and m.group(1) in keys:
            return m.group(1)
        b = re.sub(r"[（(]\s*\d+\s*[)）]\s*$", "", n)
        if b and b != n and b in keys:
            return b
        return None

    hit = 0
    mismatch = 0
    samples = []
    for g in games:
        k = find_key(g)
        if not k:
            continue
        hit += 1
        nb = bucket_of(g.get("name", "") or "")
        kb = bucket_of(k)
        if nb != kb:
            mismatch += 1
            if len(samples) < 5:
                samples.append((g.get("name"), k, "p%02d" % nb, "p%02d" % kb))
    if mismatch:
        die("商品桶号不一致 %d 条(会全落整包): %s" % (mismatch, samples))
    print("门禁3 PASS: 商品 %d 条, 命中详情 %d 条, 桶号 mismatch 0" % (len(games), hit))

    # --- 4: 480 宽度 URL 禁令 + 封面清单三元数（复核28 店主从「建议」升级为 CI 规则） ---
    # 480×672 只允许走详情位按需单张取。一旦进入 manifest / 预取清单（前端预取 = manifest 全量 URL），
    # 后台预取体积会从两档后的约 12.0MB 涨到约 53MB，比现状 38.3MB 还重 38% —— 等于把超重问题放大塞进后台。
    # 三个数必须一起打印：键数 / 唯一 URL / weserv 占比。单看任一个都会误读成本口径。
    # ★ 只拦「宽度 480」，**高度 480 不算**：仅匹配 w=480 / width=480 / 480x672（宽×高命名）。
    #   `h=480`、`height=480`、方图 480×480 的「高」都不在此禁令范围内 —— 禁止把正则扩写成
    #   `(w|h|width|height)=480`，那会误杀合法的高度/裁剪参数。480×672 这条约束针对的是
    #   「进入列表位/预取清单的单张体积」，不是分辨率某一个维度等于 480。
    # ★ 命中时固定：退出码 4 + 文案前缀「480 宽度门禁: 命中 N 条」，便于与其他 CI 失败区分。
    cv_lines = []
    manifest_cov = "无 site/ 目录，未扫描"
    site_dir = os.path.join(BASE, "site")
    if os.path.isdir(site_dir):
        covers_dir = os.path.join(site_dir, "covers")
        # ★ 第 31 轮最终签：glob 全扫，替代写死两份。前端会按 tab 加载
        #   covers/manifest_<tab>.json（index.html:2152），写死列表会漏掉新增 tab 清单。
        found = sorted(glob.glob(os.path.join(covers_dir, "manifest*.json")))
        names = [os.path.basename(x) for x in found]
        CORE_MANIFESTS = ("manifest.json", "manifest_ps.json")
        # ① 核心两份仍必须存在（站点运行基线；缺一 = 普通失败 exit 1，不与 480 的 exit 4 混淆）
        for core in CORE_MANIFESTS:
            if core not in names:
                die("site/ 已生成但缺 covers/%s（封面清单必须进站，否则此断言形同虚设）" % core)
        # ② 覆盖率断言（第 31 轮新增）：打印扫描文件数 + 完整清单，N 必须 >= 预期值。
        #    预期值默认 2（核心两份）；将来新增 tab 清单时把 GT_EXPECTED_MANIFEST_COUNT
        #    调高，门禁会强制「产出清单数 >= 预期」，防止 CI 少生成一份时 glob 只扫到子集还 PASS。
        expected = int(os.environ.get("GT_EXPECTED_MANIFEST_COUNT", "2"))
        manifest_cov = "扫描 %d 份 manifests（预期 >= %d）: %s" % (
            len(found), expected, ", ".join(names))
        print("门禁4 覆盖率: " + manifest_cov)
        if len(found) < expected:
            die("覆盖率门禁: 只扫到 %d 份 manifest*.json，少于预期 %d 份（清单=%s）—— "
                "CI 产物可能未完整生成，断言形同虚设" % (len(found), expected, names))
        # ③ 逐份全扫：每一份扫到的清单都做 480 检查 + 打印三元数（不再只查写死两份）
        for fp in found:
            base = os.path.basename(fp)
            rel = "covers/" + base
            try:
                mp = json.load(open(fp, encoding="utf-8"))
            except Exception as ex:
                die("空清单门禁: %s 不是合法 JSON（解析失败: %s）—— 文件损坏不得报 PASS" % (rel, ex))
            # ★ 第 35 轮实测订正（CI run 45160744208 failure）：原「每份 manifest 必须 URL 数 > 0」
            #   误杀了 2026-11-02 改162 留下的合法空 tab 占位 manifest_mem.json / manifest_ns.json
            #   （两个 tab 业务上就 0 条封面，文件为 {}）。前端 gtLoadCovers(tab) 动态拉
            #   covers/manifest_<tab>.json 且用 Object.keys(m).length 判空 —— 空是合法业务状态。
            #   空清单门禁原意是防「文件在、内容 0 条 URL 却报 PASS」的静默失败，故只放宽这一态：
            #     ① 每份必须是合法 JSON 对象(dict)：非对象 / 解析失败一律拒；
            #     ② 核心两份必须 URL 数 > 0：被清空 = 真故障，仍 exit 1；
            #     ③ tab 清单仅允许「空 dict」{}：有键却 0 条 URL（损坏 / 被清空）仍 exit 1。
            #   合法空 tab 清单仍计入覆盖率扫描数、仍逐份打印、仍做 480 检查，断言覆盖面不缩小。
            if not isinstance(mp, dict):
                die("空清单门禁: %s 不是合法 JSON 对象（tab 清单只允许 {} 或含 URL 的映射）—— "
                    "文件损坏或被写成非对象不得报 PASS" % rel)
            urls = []
            _walk_urls(mp, urls)
            is_core = base in CORE_MANIFESTS
            empty_ok = (not is_core) and len(mp) == 0
            if not urls and not empty_ok:
                die("空清单门禁: %s 扫到 0 条 URL（文件存在但内容为空 / 值全非字符串）—— "
                    "封面清单不得为空，否则断言形同虚设" % rel)
            if empty_ok:
                print("门禁4 合法空 tab 清单[%s]: {} 占位，计入覆盖率/480 检查，不判失败" % rel)
            bad = [u for u in urls if re.search(r"[?&](w|width)=480\b|480x672", u)]
            if bad:
                die("480 宽度门禁: 命中 %d 条（禁止进列表位/预取清单）｜文件=%s ｜样例=%s"
                    % (len(bad), rel, bad[:3]), 4)
            uniq = set(urls)
            wes = [u for u in uniq if "weserv" in u]
            pct = (100.0 * len(wes) / len(uniq)) if uniq else 0.0
            line = "%d 键 / %d 唯一 URL / weserv %.1f%% / 480 宽度 0 条" % (
                len(mp), len(uniq), pct)
            cv_lines.append((rel, line))
            print("门禁4 PASS[%s]: %s" % (rel, line))

    print("全部通过: 分片 %d 片 / key %d 条 / 商品命中 %d / mismatch 0"
          % (len(shard_files), len(union), hit))
    for rel, line in cv_lines:
        print("           封面清单 %s: %s" % (rel, line))
    # 复核19: 真实分片指标写 job summary(数字取实测, 不硬编码)
    try:
        sp = os.environ.get("GITHUB_STEP_SUMMARY", "").strip()
        if sp:
            with open(sp, "a", encoding="utf-8") as f:
                f.write("### 详情分片门禁\n\n- 分片：**%d 片**（64 桶中非空）\n- 详情 key：**%d 条**\n- 商品回退链命中：**%d**\n- 桶号 mismatch：**0**\n- 封面清单覆盖率：**%s**\n- 结论：通过\n\n"
                        % (len(shard_files), len(union), hit, manifest_cov))
                for rel, line in cv_lines:
                    f.write("- 封面清单 `%s`：**%s**\n" % (rel, line))
                if cv_lines:
                    f.write("\n")
    except Exception:
        pass
    return 0

if __name__ == "__main__":
    sys.exit(main())
