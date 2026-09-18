#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""validate_hk2.py —— 对港服英文名重搜的匹配结果做可信度校验, 拆成「可信 / 可疑」两组。
校验点：
  1) 数字一致性：商品名与候选名的标题数字不同（耻辱1 vs 耻辱2）-> 可疑
     （若去掉数字后的基础名在 manifest 里另有同款键, 说明是库存序号, 不算可疑）
  2) 词元覆盖：核心词重叠率过低（战地5 vs 战地1 尚可, 使命召唤14 vs WWII Tank Battle Arena 直接暴露）
  3) 版本一致性：商品名声明了版本而候选名没有任何版本词 -> 可疑（生化危机4重制版 vs 2005原版）
"""
import json, os, re, sys

REPO = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, REPO)
import autocover as AC
import cover_policy as CP

CJK = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf]")
EXTRA_ED = ["重制版", "重置版", "复刻版", "重制", "remaster", "remake", "remastered"]


def norm(s):
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", str(s or "").lower()).strip()


def strip_all_ed(s):
    t = norm(s)
    for w in list(getattr(AC, "EDITION_WORDS", [])) + EXTRA_ED:
        t = t.replace(norm(w), " ")
    return re.sub(r"\s+", " ", t).strip()


def nums(s):
    return set(re.findall(r"\d+", strip_all_ed(s)))


def tokens(s):
    t = strip_all_ed(s)
    if CJK.search(t):
        # 中文按字集参与比较
        return set(re.findall(r"[\u4e00-\u9fff]", t)) | set(re.findall(r"[a-z0-9]+", t))
    return set(t.split())


def main():
    st = json.load(open("/tmp/hk2_state.json", encoding="utf-8"))
    L = json.load(open("/tmp/hk2_lists.json", encoding="utf-8"))
    man = CP.load_manifest()
    # 始终从状态里取, 避免重复运行时把上一次的分组结果当输入
    H = [r for r, v in st.items() if v.get("status") == "ok"]
    good, doubt = [], []
    for rep in H:
        v = st[rep]
        cand = v.get("cand_name") or ""
        cn = rep
        en = v.get("en") or ""
        probe = en if CJK.search(en) is None and en else cn
        # 库存序号判定：去掉数字后的基础名是否也是 manifest 键
        b = re.sub(r"\d+\s*$", "", cn).strip()
        b2 = re.sub(r"[（(]\s*\d+\s*[）)]\s*$", "", cn).strip()
        stock_seq = any((x in man and x != cn) for x in (b, b2))
        nw, nc = nums(cn) or nums(en), nums(cand)
        # 候选名带「PS4 & PS5 / 语言列表」等噪声, 只算商品核心词被覆盖的比例;
        # 取所有别名变体里覆盖率最高的那个, 数字另按数字规则判
        tc = {t for t in tokens(cand) if not t.isdigit()}
        cov = 0.0
        for pv in [probe] + [q for q in (v.get("qs") or []) if q] + [cn]:
            tw = {t for t in tokens(pv) if not t.isdigit()}
            if not tw:
                continue
            cov = max(cov, len(tw & tc) / len(tw))
        ed_want = bool(norm(AC.wanted_edition(cn) or "")) if hasattr(AC, "wanted_edition") else False
        ed_cand = bool(norm(AC.edition_of(cand) or "")) if hasattr(AC, "edition_of") else False
        reasons = []
        if nw and nc and nw != nc and not stock_seq:
            reasons.append("数字不符%s≠%s" % (sorted(nw), sorted(nc)))
        if cov < 0.8:
            reasons.append("核心词覆盖率低%.0f%%" % (cov * 100))
        if ed_want and not ed_cand and not stock_seq:
            reasons.append("版本存疑(商品标%s, 候选无版本词)" % AC.wanted_edition(cn))
        (doubt if reasons else good).append(rep)
        if reasons:
            v["doubt"] = "、".join(reasons)
    json.dump(st, open("/tmp/hk2_state.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    good.sort(key=lambda r: -st[r].get("score", 0))
    doubt.sort(key=lambda r: -st[r].get("score", 0))
    L["H"] = good; L["H2"] = doubt
    json.dump(L, open("/tmp/hk2_lists.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("可信 %d | 可疑 %d" % (len(good), len(doubt)))
    print("\n--- 可疑清单 ---")
    for i, r in enumerate(doubt):
        print("  #%-3d %-24s -> %-34s %s" % (i + 1, r[:24], (st[r].get("cand_name") or "")[:34],
                                             st[r].get("doubt", "")))


if __name__ == "__main__":
    main()
