#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""汇总 PS/NS/会员资费 -> data.js (仅公开展示字段, 不含账号密码等敏感列)
数据来源优先级:
  1. PS:  始终从 data/ps_games.json (由 parse_ps.py 从 kdocs 实时导出解析)
  2. NS:  若存在 data/ns_games.json 则用之(自动同步时由 kdocs NS表导出生成), 否则用内置快照
  3. 会员: 若存在 data/membership.json 则用之, 否则用内置快照(源自原表, 低频变更)
"""
import json, datetime, re, os

BASE=os.path.dirname(os.path.abspath(__file__))  # 仓库根目录
ps=json.load(open(os.path.join(BASE,"data/ps_games.json"),encoding="utf-8"))

ALLOW={"PS4","PS5","PSVR"}
REGION_MAP={"港HK":"港版","美US":"美版","日JP":"日版","欧EU":"欧版","国CN":"国行"}
clean=[]
for g in ps:
    # 剔除单字母占位伪记录
    if len(g["name"])<=2 and g["name"] in set("ABCDEFGHIJKLMNOPQRSTUVWXYZ"):
        continue
    hs=[h for h in g["hs"] if h in ALLOW]
    if not hs: continue
    rec={"name":g["name"],"en":g["en"],"date":g["date"],
         "region":REGION_MAP.get(g["region"],g["region"]),
         "letter":g["letter"],"hs":hs,
         # 改67: 价格/库存字段强制转字符串, 防止数字类型导致页面 fmtMoney 抛错
         "ck7":str(g["ck7"]),"fc7":str(g["fc7"]),"xd30":str(g["xd30"]),
         "ck4":g["ck4"],"ck5":g["ck5"],"fc":g["fc"],"xd":g["xd"]}
    clean.append(rec)
print("PS 清洗后:",len(clean))

def S(*v): return v

ns=[
 {"name":"咚奇刚：蕉力全开（完整版）","en":"Donkey Kong Bananza","region":"港HK",
  "hosts":[{"h":"NS1","date":"2025年9月12日","ck_stock":"有","fc_stock":"有","xd_stock":"有"},
           {"h":"NS2","date":"2025年9月12日","ck_stock":"有","fc_stock":"有","xd_stock":"有"}]},
 {"name":"集合啦！动物森友会（完整版）","en":"Animal Crossing：New Horizons（Complete Edition）","region":"港HK",
  "hosts":[{"h":"NS1","date":"2020年3月20日","ck_stock":"有","fc_stock":"有","xd_stock":"有"},
           {"h":"NS2","date":"2026年1月15日","ck_stock":"有","fc_stock":"有","xd_stock":"有"}]},
 {"name":"蜡笔小新：煤炭镇的小白","en":"Shin-chan: Shiro and the Coal Town","region":"港HK",
  "hosts":[{"h":"NS1","date":"2024年5月2日","ck_stock":"有","fc_stock":"有","xd_stock":"有"},
           {"h":"NS2","date":"2024年5月2日","ck_stock":"有","fc_stock":"有","xd_stock":"有"}]},
 {"name":"马里奥+疯狂兔子 希望之星（黄金版）","en":"Mario+Rabbids Sparks of Hope（Gold Edition）","region":"港HK",
  "hosts":[{"h":"NS1","date":"2022年10月20日","ck_stock":"有","fc_stock":"有","xd_stock":"有"},
           {"h":"NS2","date":"2022年10月20日","ck_stock":"有","fc_stock":"有","xd_stock":"有"}]},
 {"name":"异度神剑2+黄金之国伊拉","en":"Xenoblade2+Torna~The Golden Country","region":"日JP",
  "hosts":[{"h":"NS1","date":"2018年4月3日","ck_stock":"有","fc_stock":"有","xd_stock":"有"},
           {"h":"NS2","date":"2026年7月30日","ck_stock":"有","fc_stock":"有","xd_stock":"有"}]},
]

# 会员资费（中）结构化内容
membership={
 "title":"「夏天Jackey」PS数字游戏 · 会员资费",
 "sub":"可认证：买家账号游玩（有存档有奖杯）；非认证：卖家账号游玩（无存档无奖杯）",
 "plans":[
   {"class":"周租会员","scheme":"方案A","cert":"非认证","fee":"78元/年","eligible":"发售满24个月","price":"1元","tenure":"7天（到期可续）"},
   {"class":"周租会员","scheme":"方案A","cert":"可认证","fee":"128元/年","eligible":"发售满24个月","price":"2元","tenure":"7天（到期可续）"},
   {"class":"周租会员","scheme":"方案B","cert":"非认证","fee":"128元/年","eligible":"发售满12个月","price":"1元","tenure":"7天（到期可续）"},
   {"class":"周租会员","scheme":"方案B","cert":"可认证","fee":"198元/年","eligible":"发售满12个月","price":"2元","tenure":"7天（到期可续）"},
   {"class":"周租会员","scheme":"方案C","cert":"非认证","fee":"258元/年","eligible":"发售满6个月","price":"1元","tenure":"7天（到期可续）"},
   {"class":"周租会员","scheme":"方案C","cert":"可认证","fee":"398元/年","eligible":"发售满6个月","price":"2元","tenure":"7天（到期可续）"},
   {"class":"周租会员","scheme":"方案D","cert":"非认证","fee":"358元/年","eligible":"发售满3个月","price":"1元","tenure":"7天（到期可续）"},
   {"class":"周租会员","scheme":"方案D","cert":"可认证","fee":"498元/年","eligible":"发售满3个月","price":"2元","tenure":"7天（到期可续）"},
   {"class":"不限时会员","scheme":"方案E","cert":"非认证","fee":"458元/年","eligible":"发售满1个月","price":"1元","tenure":"不限时"},
   {"class":"不限时会员","scheme":"方案E","cert":"可认证","fee":"598元/年","eligible":"发售满1个月","price":"2元","tenure":"不限时"},
   {"class":"终身会员","scheme":"方案F","cert":"非认证","fee":"558元/终身","eligible":"所有游戏","price":"标准价3-7折","tenure":"7天（到期可续）"},
   {"class":"终身会员","scheme":"方案F","cert":"可认证","fee":"798元/终身","eligible":"所有游戏","price":"标准价3-7折","tenure":"7天（到期可续）"},
 ],
 "common":{"count":"1个/次","deposit":"免押"},
 "rules":[ # 方案规则说明
   "【方案A-D 周租会员】1. 会员价（限时）持有1个游戏；2. 持有的游戏不归还，额外租赁按【标准价7折（限时）】收费。",
   "【方案E 不限时会员】1. 会员价（不限时）持有1个发售＞1个月的游戏；2. 标准价7折（限时）持有1个发售＜1个月的游戏；3. 额外租赁按发售时长打折（限时）：【6折】1个月＜发售≤6个月 /【5折】6个月＜发售≤12个月 /【4折】12个月＜发售≤24个月 /【3折】发售＞24个月。",
   "【方案F 终身会员】1. 标准价打折（限时）持有1个游戏：【7折】发售＜1个月 /【6折】1个月＜发售≤6个月 /【5折】6个月＜发售≤12个月 /【4折】12个月＜发售≤24个月 /【3折】发售＞24个月；2. 持有的游戏不归还，额外租赁按【标准价（限时）】收费。"
 ],
 "notice":[
   "1、会员一经办理不得以任何理由退费。",
   "2、非认证：用卖家账号玩游戏，存档/进度/奖杯保留在卖家账号。\n可认证：用买家账号玩游戏，存档/进度/奖杯保留在买家账号。\n限定版：离线认证30天，按标准价计费，不享会员折扣。",
   "3、此服务仅支持会员本人使用，禁止外借或转让、租不认证改认证、登录多台主机/手机APP/网页、修改账号资料或账号内充值消费。",
   "4、账号解绑后必须第一时间联系店主回收账号；私自解绑未联系确认导致无法回收的，按续期计费至会员期结束。违规使用本店有权取消会员资格并终止服务。"
 ]
}

updated=datetime.date.today().strftime("%Y-%m-%d")

# 改86: 把 AirScript 的同步时间戳也带进 data.js(原 `updated` 只精确到日, 看不出是否最新)
synced=""
try:
    for _src in ("ps_grid.json","ns_grid.json"):
        _p=os.path.join(BASE,"data",_src)
        if os.path.exists(_p):
            with open(_p,encoding="utf-8") as _f: _g=json.load(_f)
            _t=(_g.get("synced_at") or "").strip()
            if _t: synced=synced+(_src[:2].upper()+" "+_t+"  ") if synced else _t
except Exception:
    pass

data={"updated":updated,"synced":synced,
 "promo":"一次拍2单7天送3天=17天，一次拍3单7天送9天=30天",
 "ps":clean,"ns":ns,"membership":membership}

js="window.GT_DATA="+json.dumps(data,ensure_ascii=False,separators=(",",":"))+";"
out=os.path.join(BASE,"data.js")
open(out,"w",encoding="utf-8").write(js)
print("written",out, len(js)//1024,"KB")
print("updated",updated)
