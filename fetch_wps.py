#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WPS 开放平台 API 取数: 读取游戏表指定 sheet 的矩形范围 → 转成 parse_ps.py 兼容的 kdc 格式

用法:
  python3 fetch_wps.py <file_id> <worksheet_id> <row_to> [--type auto|sheets|airsheet] [输出路径]

环境变量:
  WPS_APP_ID / WPS_APP_SECRET

输出格式与 kdocs read_file kdc 一致:
  {"data":{"content":{"range_data":[{"rangeData":[{cellText,rowFrom,rowTo,colFrom,colTo}...]}]}}}
"""
import json, os, sys, time, urllib.request, urllib.parse

API = "https://openapi.wps.cn"


def http_json(url, data=None, headers=None, method=None):
    req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def get_token():
    body = urllib.parse.urlencode({
        "grant_type": "client_credentials",
        "client_id": os.environ["WPS_APP_ID"],
        "client_secret": os.environ["WPS_APP_SECRET"],
    }).encode()
    resp = http_json(API + "/oauth2/token", data=body, method="POST")
    tok = resp.get("access_token")
    if not tok:
        raise SystemExit("token 获取失败: " + json.dumps(resp, ensure_ascii=False)[:500])
    return tok


def api_get(tok, path, params=None):
    q = ("?" + urllib.parse.urlencode(params)) if params else ""
    req = urllib.request.Request(API + path + q, headers={"Authorization": "Bearer " + tok})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def list_worksheets(tok, file_id, ftype):
    return api_get(tok, f"/v7/{ftype}/{file_id}/worksheets")


def read_range(tok, file_id, wid, ftype, row_from, row_to, col_from, col_to):
    return api_get(tok, f"/v7/{ftype}/{file_id}/worksheets/{wid}/range_data",
                   {"row_from": row_from, "row_to": row_to, "col_from": col_from, "col_to": col_to})


def detect_type(tok, file_id):
    """依次尝试 sheets / airsheet, 返回可用的类型名"""
    for ftype in ("sheets", "airsheet"):
        try:
            resp = list_worksheets(tok, file_id, ftype)
            if resp.get("code") == 0:
                print("文件类型判定:", ftype)
                return ftype
            print(ftype, "不可用:", json.dumps(resp, ensure_ascii=False)[:200])
        except Exception as e:
            print(ftype, "请求异常:", str(e)[:200])
    raise SystemExit("两种文件类型接口均不可用, 请检查应用权限(需 kso.sheets.read 或 kso.airsheet.read)")


def main():
    file_id, wid, row_to = sys.argv[1], sys.argv[2], int(sys.argv[3])
    ftype = sys.argv[4] if len(sys.argv) > 4 and not sys.argv[4].startswith("--") else "auto"
    out = sys.argv[-1] if len(sys.argv) > 4 else "kdc_export.json"
    col_from, col_to = 0, 16
    tok = get_token()
    if ftype in ("auto",):
        ftype = detect_type(tok, file_id)

    items = []
    step = 300
    r = 0
    while r <= row_to:
        r2 = min(r + step - 1, row_to)
        resp = read_range(tok, file_id, wid, ftype, r, r2, col_from, col_to)
        if resp.get("code") != 0:
            raise SystemExit(f"读取 {r}-{r2} 失败: " + json.dumps(resp, ensure_ascii=False)[:500])
        for it in resp.get("data", {}).get("range_data", []):
            items.append({
                "cellText": it.get("cell_text", ""),
                "rowFrom": it.get("row_from", 0),
                "rowTo": it.get("row_to", it.get("row_from", 0)),
                "colFrom": it.get("col_from", 0),
                "colTo": it.get("col_to", it.get("col_from", 0)),
                "isCellPic": bool(it.get("is_cell_pic")),
            })
        print(f"rows {r}-{r2} ok, items={len(items)}")
        r = r2 + 1
        time.sleep(0.15)

    export = {"data": {"content": {"range_data": [{"rangeData": items}]}}}
    with open(out, "w", encoding="utf-8") as f:
        json.dump(export, f, ensure_ascii=False)
    print("已写出:", out, "cells:", len(items))


if __name__ == "__main__":
    main()
