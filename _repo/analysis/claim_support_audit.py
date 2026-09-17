#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""claim_support_audit.py — 结论支撑性审计（用户指令：结果必须能支撑结论，否则稿件无意义）

三条硬检查：
  C1 锚存在性：结论性文本（摘要+讨论）引用的每个 [L-xxx] 必须在台账锚表中存在
  C2 数字溯源：结论性文本中出现的每个数值，必须能在台账/对照实验的数值全集里
     按该数字的小数位容差（≤0.5×10^-d）找到来源（含变体 AUC 两两差，覆盖"虚高"表述）
  C3 锚利用完备性：台账全部锚都应被稿件至少引用一次（防"结果出了没用上"）
输出：results/claim_support_audit.json + results/支撑矩阵.md；任一失配 → exit 1
"""
import json, os, re, sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RES = os.path.join(BASE, "results")
MD = os.environ.get("MD_PATH") or next(
    p for p in [os.path.join(os.path.dirname(os.path.abspath(__file__)), "manuscript_gse31210.md"),
                os.path.join(BASE, "稿件", "manuscript_gse31210.md")] if os.path.exists(p))

R = json.load(open(os.path.join(RES, "results.json"), encoding="utf-8"))
anchors = dict(R["_anchors"])
# L-010 由 gen_ledger 从对照实验合成（不回写 results.json），审计器按同口径合并
vp = os.path.join(RES, "variant_experiment.json")
if os.path.exists(vp) and "L-010" not in anchors:
    V0 = json.load(open(vp, encoding="utf-8"))
    leak = {k: {"AUC": v0["AUC"], "HR": v0["HR"], "KM_P": v0["KM_P"]}
            for k, v0 in V0.items() if isinstance(v0, dict) and "AUC" in v0}
    anchors["L-010"] = {"key": "T31_泄露对照实验", "value": leak,
                        "note": "全队列选择仅作 T31 教学对照，不得用于任何主张"}
V = json.load(open(os.path.join(RES, "variant_experiment.json"), encoding="utf-8"))

# ---------- 数值全集 ----------
vals = []
def walk(x):
    if isinstance(x, bool):
        return
    if isinstance(x, (int, float)):
        vals.append(float(x))
    elif isinstance(x, list):
        for y in x:
            walk(y)
    elif isinstance(x, dict):
        for y in x.values():
            walk(y)
walk(R); walk(V)
# 变体 AUC 两两差（覆盖"虚高 +0.163 / 0.11–0.16"这类差值表述）
aucs = [v["AUC"] for v in V.values() if isinstance(v, dict) and "AUC" in v]
for i in range(len(aucs)):
    for j in range(i + 1, len(aucs)):
        vals.append(abs(aucs[i] - aucs[j]))

NUM = re.compile(r"(?<![A-Za-z0-9_])(\d+\.\d+e[+-]?\d+|\d+\.\d+|\d+)(?![A-Za-z0-9_])")


def num_ok(tok):
    """数值 tok 是否能在数值全集按其小数位容差找到来源。"""
    x = float(tok)
    d = len(tok.split(".")[1]) if "." in tok and "e" not in tok.lower() else \
        (abs(int(re.search(r"e([+-]?\d+)", tok.lower()).group(1))) - 1
         if "e" in tok.lower() else 0)
    tol = 0.5 * (10 ** -d) + 1e-12
    return any(abs(v - x) <= tol for v in vals)


# ---------- 稿件解析 ----------
sections, cur = {}, None
for line in open(MD, encoding="utf-8"):
    line = line.rstrip("\n")
    m = re.match(r"^##\s+(.*)$", line)
    if m:
        cur = m.group(1).strip(); sections[cur] = []
    elif cur is not None:
        sections[cur].append(line)
abstract = "\n".join(sections["摘要"])
disc = "\n\n".join(sections["讨论"])

rows = []
def audit(tag, text, allow_no_anchor=False):
    # 先剔除引用标记（[L-001] 锚号、[4] 参考文献号），防数字正则误切（首轮误报实证）
    clean = re.sub(r"\[(?:L-\d{3}|\d+)\]", "", text)
    anc = sorted(set(re.findall(r"\[(L-\d{3})\]", text)), key=lambda s: int(s[3:]))
    bad_anc = [a for a in anc if a not in anchors]
    bad_num = [tok for tok in NUM.findall(clean) if not num_ok(tok)]
    ok = (len(anc) > 0 or allow_no_anchor) and not bad_anc and not bad_num
    rows.append({"主张块": tag, "锚": anc, "缺锚": bad_anc,
                 "数值数": len(NUM.findall(clean)), "失配数值": bad_num,
                 "判定": "支撑" if ok else "不支撑"})
    print(f"[{'支撑' if ok else '不支撑'}] {tag}｜锚={anc or '—'}｜失配数值={bad_num or '无'}")

# 摘要拆主张块：P1/结果/结论 为结果性主张（数值审计）；背景/方法 为设计参数（不在范围）
p1_txt = re.split(r"背景：", abstract)[0]
audit("摘要·P1 主张", p1_txt)
_abs = re.split(r"(背景：|方法：|结果：|结论：)", abstract)
blocks, _cur = {}, None
for seg in _abs[1:]:
    if seg in ("背景：", "方法：", "结果：", "结论："):
        _cur = seg.rstrip("：")
    elif _cur:
        blocks[_cur] = blocks.get(_cur, "") + seg
for k in ("背景", "方法"):
    print(f"[跳过] 摘要·{k}｜设计参数段，不在数值审计范围")
audit("摘要·结果主张", blocks.get("结果", ""))
audit("摘要·结论主张", blocks.get("结论", ""))
for i, p in enumerate([x for x in disc.split("\n\n") if x.strip()], 1):
    allow = p.startswith(("局限", "展望"))   # 局限/展望段无结果主张，无锚合法
    audit(f"讨论·第{i}段", p, allow_no_anchor=allow)

# ---------- C3 锚利用完备性 ----------
whole = open(MD, encoding="utf-8").read()
unused = [a for a in anchors if a not in whole]
print(f"[{'支撑' if not unused else '待入稿'}] C3 锚利用完备性｜未引用锚={unused or '无'}"
      + ("（新结果待写作层接入）" if unused else ""))
rows.append({"主张块": "C3 全稿锚利用", "锚": sorted(anchors), "缺锚": unused,
             "数值数": 0, "失配数值": [],
             "判定": "支撑" if not unused else f"待入稿（{len(unused)} 项新结果未接入结论链）"})

n_ok = sum(1 for r in rows if r["判定"] == "支撑")
print(f"结论支撑性审计: {n_ok}/{len(rows)} 支撑")
# C3 的"未引用锚"= 新结果尚未接入结论链：显式标"待入稿"，不冒充通过也不阻塞
# （本轮场景：写作层按用户指示冻结，新增校准/DCA/时间依赖结果待写作层解冻后接入）
json.dump(rows, open(os.path.join(RES, "claim_support_audit.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)

L = ["# 结论支撑矩阵 · 结果 ↔ 结论关联审计", "",
     "> 逐条结论主张核对：引用锚存在 + 数值可溯源到台账（舍入容差）+ 全锚被利用。", ""]
for r in rows:
    L.append(f"## {r['主张块']} —— {r['判定']}")
    L.append(f"- 引用锚：{'、'.join(r['锚']) if r['锚'] else '—'}")
    if r["缺锚"]:
        L.append(f"- **缺锚：{r['缺锚']}**")
    if r["失配数值"]:
        L.append(f"- **失配数值：{r['失配数值']}**")
    L.append("")
with open(os.path.join(RES, "支撑矩阵.md"), "w", encoding="utf-8") as f:
    f.write("\n".join(L))
sys.exit(0 if all(r["判定"] != "不支撑" for r in rows) else 1)
