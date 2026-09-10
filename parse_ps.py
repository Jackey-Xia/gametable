#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""解析 kdocs 导出的 PS游戏 sheet(rangeData JSON) → 公开展示用 products JSON
仅保留公开列: 0序列字母 2中文名 3英文名 4发售日期 5主机 6地区 7可认证库存 8可认证7天租金
9非认证库存 10非认证7天租金 11限定版库存 12限定版30天租金
剔除敏感列(账号/密码/邮箱绑定手机)与内部备注/图例图片。
"""
import json, re, sys, datetime, os

# 用法: python3 parse_ps.py <kdocs导出文件路径> [输出json路径]
if len(sys.argv) < 2:
    print("用法: parse_ps.py <kdocs read_file 落盘 txt/json> [out.json]")
    sys.exit(2)
SRC = sys.argv[1]
OUT = sys.argv[2] if len(sys.argv) > 2 else "/Users/jackey/WorkBuddy/2026-09-08-16-48-51/gametable/data/ps_games.json"
os.makedirs(os.path.dirname(OUT), exist_ok=True)

def is_num_like(v):
    if v is None: return False
    if isinstance(v,(int,float)): return True
    s=str(v).strip()
    return bool(re.fullmatch(r'-?\d+(\.\d+)?', s))

def norm(v):
    if v is None: return ""
    s=str(v)
    s=s.replace("\n"," ").replace("\r"," ")
    s=re.sub(r'\s+',' ',s).strip()
    return s

raw=open(SRC,encoding="utf-8",errors="replace").read()
data=json.loads(raw)

# ---- AirScript 直推格式: {type:"airscript_grid", rows:[[..],..]} ----
if isinstance(data,dict) and data.get("type")=="airscript_grid":
    MAXR=4000; MAXC=17
    grid=[[""]*MAXC for _ in range(MAXR)]
    rows_in=data.get("rows") or []
    def _norm_v(v):
        if v is None: return ""
        s=str(v)
        if s.endswith(".0"):  # JS/Py 浮点整数值还原
            try:
                f=float(s)
                if f==int(f): s=str(int(f))
            except ValueError: pass
        return norm(s)
    last0=""; last2=""; last3=""; last4=""; last5=""; last6=""
    last8=""; last10=""; last12=""; last9=""; last11=""; last7=""
    last3_name=""  # en 锚点行的中文名
    def _base_name(nm):
        s = nm
        while True:
            s2 = re.sub(r'（\d+）$', '', s)
            if s2 == s: break
            s = s2
        return re.sub(r'\d+$', '', s)
    for r,row in enumerate(rows_in[:MAXR]):
        has=False
        raw0=""  # col0 原始值(填充前), 用于判断是否新组首行
        for c in range(min(len(row),MAXC)):
            v=row[c]
            if v is None: continue
            has=True
            if c==0: raw0=_norm_v(v)
            s=_norm_v(v)
            # col4 发售日期: Excel日期序列号(20000~80000 ≈ 1954~2119年) 转显示文本
            if c==4 and re.fullmatch(r'\d+(\.\d+)?',s):
                f=float(s)
                if 20000<f<80000:
                    import datetime as _dt
                    d=_dt.date(1899,12,30)+_dt.timedelta(days=int(f))
                    s=f"{d.year}年{d.month}月{d.day}日"
            grid[r][c]=s
        if has:
            # 模拟合并格展开: 游戏名(col2)/字母(col0)向下填充到该组所有子行
            if grid[r][2]!="": last2=grid[r][2]
            else: grid[r][2]=last2
            if grid[r][0]!="": last0=grid[r][0]
            else: grid[r][0]=last0
            # 字母分隔带行(单字母=col0、无库存/租金/日期)不填充 col3~6, 保持可识别
            band = (len(grid[r][2])==1 and grid[r][2]==grid[r][0]
                    and grid[r][7]=="" and grid[r][8]=="" and grid[r][4]=="")
            if not band:
                # col3英文名: 合并格继承; 延续行(col0空)直接继承, 序号变体行(名字同源)也继承, 其余新组不继承防误带
                if grid[r][3]!="":
                    last3=grid[r][3]
                    last3_name=grid[r][2]
                elif raw0=="" or _base_name(grid[r][2])==_base_name(last3_name):
                    grid[r][3]=last3
                # col4日期/col5主机/col6地区 纵向合并格: 向下填充
                if grid[r][4]!="": last4=grid[r][4]
                else: grid[r][4]=last4
                if grid[r][5]!="": last5=grid[r][5]
                else: grid[r][5]=last5
                if grid[r][6]!="": last6=grid[r][6]
                else: grid[r][6]=last6
                # 租金列(col8/col10/col12)也是按组合并格: 向下填充
                if grid[r][8]!="": last8=grid[r][8]
                else: grid[r][8]=last8
                if grid[r][10]!="": last10=grid[r][10]
                else: grid[r][10]=last10
                if grid[r][12]!="": last12=grid[r][12]
                else: grid[r][12]=last12
                # 非认证(col9)/限定版(col11)/可认证(col7)库存也常见跨行合并: 向下填充
                if grid[r][9]!="": last9=grid[r][9]
                else: grid[r][9]=last9
                if grid[r][11]!="": last11=grid[r][11]
                else: grid[r][11]=last11
                if grid[r][7]!="": last7=grid[r][7]
                else: grid[r][7]=last7
        else:
            grid[r][2]=""; last2=""; last3=""; last4=""; last5=""; last6=""; last0=""
            last8=""; last10=""; last12=""; last9=""; last11=""; last7=""  # 整行空 -> 断开填充
    print("airscript_grid 输入, rows:", min(len(rows_in),MAXR))
else:
    content=data["data"]["content"]
    parts = content["range_data"] if isinstance(content.get("range_data"), list) else [content["range_data"]]
    print("parts:", len(parts) if isinstance(content.get("range_data"), list) else "single")

    MAXR=4000; MAXC=17
    grid=[ [""]*MAXC for _ in range(MAXR) ]
    n_items=0
    for p in parts:
        rd=p["detail"]["rangeData"] if "detail" in p and "rangeData" in p["detail"] else p["rangeData"]
        if rd is None: continue
        for it in rd:
            n_items+=1
            r0=it.get("rowFrom", it.get("originRow",0)); r1=it.get("rowTo", r0)
            c0=it.get("colFrom", it.get("originCol",0)); c1=it.get("colTo", c0)
            if it.get("isCellPic"): val=None
            else: val=norm(it.get("cellText"))
            if val=="" and it.get("understandableType",{}).get("type")=="date":
                val=norm(it.get("cellText"))
            if r0<0 or r0>=MAXR: continue
            if c1>=MAXC: c1=MAXC-1
            for r in range(r0, min(r1,MAXR-1)+1):
                for c in range(c0,c1+1):
                    if val!="" or grid[r][c]=="":
                        grid[r][c]=val

    print("items:",n_items)

# 统计每行是否有游戏名，粗看结构
products=[]
seen_block=[]
r=4
LTR = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
while r < 4000:
    name=grid[r][2]
    if name=="":
        r+=1; continue
    # 字母分隔带行: col2=col0 为单字母、无日期、无库存/价格(整行仅填充字母) -> 跳过
    if (len(name)==1 and name in LTR and grid[r][0].strip()==name
            and grid[r][4]=="" and grid[r][7]=="" and grid[r][8]==""):
        r+=1; continue
    gname=name
    grp=[]
    while r<4000:
        nm=grid[r][2]
        if nm=="":
            r+=1
            break
        if nm!=gname:
            break
        grp.append(r)
        r+=1
    if not grp: continue
    letter=grid[grp[0]][0].strip()[:1]
    if letter not in LTR: letter=""

    def firstval(col):
        for rr in grp:
            v=grid[rr][col]
            if v!="":
                return v
        return ""

    def stock(col, host=None):
        """库存判定: 有=True 无/空=False; host 指定时只看该主机子行"""
        for rr in grp:
            if host is not None and grid[rr][5]!=host:
                continue
            v=grid[rr][col]
            if v!="":
                return 1 if v=="有" else 0
        return None if host is not None else 0

    rec={"name":gname,"en":grid[grp[0]][3],"date":grid[grp[0]][4],
         "region":grid[grp[0]][6],"letter":letter,
         # 租金按游戏(合并格,组内取第一个非空)
         "ck7":firstval(8),"fc7":firstval(10),"xd30":firstval(12),
         # 库存: 可认证 PS4/PS5 独立位(col7 按主机子行); 非认证(col9)/限定版(col11) 共用位
         "ck4":stock(7,"PS4"),"ck5":stock(7,"PS5"),
         "fc":stock(9),"xd":stock(11)}
    # 改67v: PSVR等无PS4/PS5子行的游戏, 可认证库存取组内第一个col7值(通用位), 使前端能显示 库存:有/无
    if not any(grid[rr][5] in ("PS4","PS5") for rr in grp):
        v7=firstval(7)
        rec["ck4"]=(1 if v7=="有" else 0) if v7!="" else None
        rec["ck5"]=None
    # 该游戏实际支持的主机(子行存在才有效)
    rec["hs"]=[h for h in ("PS4","PS5","PSVR") if any(grid[rr][5]==h for rr in grp)]
    products.append(rec)

cleaned=[]
for rec in products:
    rec2={k:rec[k] for k in ("name","en","date","region","letter","ck7","fc7","xd30","ck4","ck5","fc","xd","hs")}
    cleaned.append(rec2)

print("总组(游戏)数:", len(cleaned))
# 去除无有效主机的行(理论不会)
cleaned=[c for c in cleaned if c["hs"]]
print("有效游戏数:", len(cleaned))

with open(OUT,"w",encoding="utf-8") as f:
    json.dump(cleaned,f,ensure_ascii=False,separators=(",",":"))
print("written",OUT, len(json.dumps(cleaned,ensure_ascii=False)))

# 汇总概览
from collections import Counter
letters=Counter(c["letter"] for c in cleaned)
print("字母分布:", dict(sorted(letters.items())))
print("主机组合:", dict(Counter(tuple(c["hs"]) for c in cleaned)))
print("库存样例(前3):", [(c["name"],c["ck4"],c["ck5"],c["fc"],c["xd"]) for c in cleaned[:3]])