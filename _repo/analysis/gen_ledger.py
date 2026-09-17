#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gen_ledger.py — 从 results.json 生成台账.md（唯一数字来源 + [L-xxx] 锚表）"""
import json, os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
R = json.load(open(os.path.join(BASE, "results", "results.json"), encoding="utf-8"))
anchors = R["_anchors"]
L = ["# 台账 · GSE31210 全流程实战（唯一数字来源）", "",
     "> 稿件与图注引用的一切数字只许来自本文件；本文件由 results.json 机器生成，不手改。", ""]
for k, v in R.items():
    if k.startswith("_"):
        continue
    val = v["value"] if isinstance(v, dict) and "value" in v else v
    note = v.get("note", "") if isinstance(v, dict) else ""
    L.append(f"## {k}\n\n- 值：`{json.dumps(val, ensure_ascii=False)}`")
    if note:
        L.append(f"- 说明：{note}")
    L.append("")
# 泄露对照实验（variant_experiment.json）→ L-010
vp = os.path.join(BASE, "results", "variant_experiment.json")
if os.path.exists(vp):
    V = json.load(open(vp, encoding="utf-8"))
    leak = {k: {"AUC": v["AUC"], "HR": v["HR"], "KM_P": v["KM_P"]} for k, v in V.items()
            if isinstance(v, dict) and "AUC" in v}
    anchors["L-010"] = {"key": "T31_泄露对照实验", "value": leak,
                        "note": "全队列选择+全队列拟合（模仿 Wen 2022 做法）仅作 T31 教学对照，不得用于任何主张"}
    L.append("## T31_泄露对照实验\n")
    L.append(f"- 值：`{json.dumps(leak, ensure_ascii=False)}`")
    L.append("- 说明：对照性质见上；详见 results/variant_experiment.json。")

L.append("## [L-xxx] 证据锚表（稿件同句引用用）\n")
for a, v in anchors.items():
    L.append(f"- **{a}** ← {v['key']}")
for a, v in anchors.items():
    L.append(f"- **{a}** ← {v['key']}")
with open(os.path.join(BASE, "results", "台账.md"), "w", encoding="utf-8") as f:
    f.write("\n".join(L))
print("台账已生成 results/台账.md，锚数：", len(anchors))
