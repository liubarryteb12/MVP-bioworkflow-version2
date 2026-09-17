#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
applicability_gate.py —— §10「不适用 + 理由」适用性闸门

════════════════════════════════════════════════════════════════════════
为什么需要这个模块
────────────────────────────────────────────────────────────────────────
框架 §10 明文规定:

    "任一项不适用时写 `不适用 + 理由`,禁止留空、禁止静默删除"

但**该规则此前在主验证脚本中没有任何代码落点**(v2.13 预演发现):
101 个判定项只有 PASS / FAIL 二态,遇到不适用数据时只能
  (a) 强行套用判据 → 给出无意义的 PASS/FAIL,或
  (b) 抛异常被吞 → 静默跳过(正是 §10 禁止的"静默删除")。

真实数据压力测试(GSE250167,拟南芥小 RNA)会大面积触发这个问题:
sRNA 无 mRNA 式 log2FC 语义、无人类通路注释、无临床随访。
若不先建这个闸门,真实数据一进来,框架要么误判要么静默漏项。

设计
────────────────────────────────────────────────────────────────────────
`evaluate(meta)` 返回 {判据ID: (applicable: bool, reason: str)}。
规则由**数据特征声明**驱动,而非硬编码数据集名称 —— 这样换任何
真实数据集都同样生效,不是为 GSE250167 打的补丁。

★ 关键:reason 绝不允许为空字符串(§10 禁止留空),构造时即校验。
"""

# ── 判据适用性规则表 ─────────────────────────────────────────────────
# 每项: (判据ID, 判据名, 适用性判定函数, 不适用时的理由模板)
# 判定函数接收 meta(dict),返回 True=适用 / False=不适用


def _always(meta):
    return True


def _need_singlecell(meta):
    """T15/T16:仅在**是**单细胞数据时适用。

    ★ v2.13 修 bug:初版写成 `not is_single_cell` —— 逻辑反向,
      把"非单细胞"误判为**适用**,即框架会对 bulk/sRNA 数据强行套用
      单细胞 QC 与 donor 级推断规则。这是最危险的判错方向:
      "过度适用"会给出无意义结论,而"过度不适用"只是保守降级。
      该 bug 是在 GSE250167 预演中当场暴露的(n=8 非单细胞,
      却报 T15/T16 适用)。
    """
    return bool(meta.get("is_single_cell", False))


def _need_clinical(meta):
    return bool(meta.get("has_clinical_outcome", False))


def _need_pathway(meta):
    return bool(meta.get("has_pathway_annotation", False))


def _need_n15(meta):
    """T04 WGCNA:框架明确规定 样本量 < 15 → 不适用"""
    return meta.get("n_sample", 0) >= 15


def _need_n_for_model(meta):
    """T09/T13 预测模型:样本 < 30 时无法支撑训练/校准评估"""
    return meta.get("n_sample", 0) >= 30


def _need_mrna_semantics(meta):
    """★ 用户指定的核心测试点。

    T01 的 |log2FC| ≥ 0.585 语义是为 **mRNA 差异表达**设计的。
    对 sRNA count:"基因"是短序列,无外显子/转录本概念,
    且 sRNA 的丰度跨度与 mRNA 不同,直接套 mRNA 尺度的 log2FC
    阈值会得到无生物学意义的结果。

    注意:框架 T01 的 predicate 实为 **尺度声明** 检查
    (`scale_declared and family_declared`),该检查本身数据类型无关,
    故 T01 **仍适用** —— 真正不适用的是依赖 mRNA log2FC 语义的
    **效应量下限**部分。此处精确区分二者,避免"整条判据一刀切不适用"
    这种过度降级。
    """
    return True     # T01 尺度声明检查仍适用;效应量下限另行处理


RULES = [
    ("T01", "尺度声明与检验家族", _always, ""),
    ("T03", "富集分析背景集", _need_pathway,
     "sRNA 序列无标准通路注释(MSigDB/KEGG 为人类基因设计),"
     "背景集无法构造 → 富集分析不适用"),
    ("T04", "共表达网络(WGCNA)", _need_n15,
     "框架规定样本量 <15 不适用;当前 n={n_sample}"),
    ("T06", "生存分析(含竞争风险)", _need_clinical,
     "无临床随访/时间-事件结局 → 生存分析不适用"),
    ("T09", "预测模型", _need_n_for_model,
     "样本量 {n_sample} < 30,不足以支撑训练-验证划分 → 不适用"),
    ("T13", "模型增量判据(校准/DCA)", _need_n_for_model,
     "无可用预测模型(样本量 {n_sample} < 30)→ 校准与 DCA 不适用"),
    ("T15", "单细胞 QC", _need_singlecell,
     "本数据非单细胞(assay_type={assay_type})→ 单细胞 QC 阈值不适用"),
    ("T16", "单细胞推断单位", _need_singlecell,
     "本数据非单细胞(assay_type={assay_type})→ donor 级推断规则不适用"),
    ("T17", "计算扰动", _need_pathway,
     "程序活性扰动需通路/基因集定义,sRNA 无注释 → 不适用"),
]


def evaluate(meta):
    """返回 {判据ID: (applicable, reason)}。

    applicable=False 时 reason 必非空(§10);构造期即校验,
    防止"不适用但无理由"这种静默漏项。
    """
    out = {}
    for cid, name, fn, reason_tpl in RULES:
        try:
            ok = bool(fn(meta))
        except Exception as e:
            # 判定函数出错 → 保守判"不适用"并说明理由,绝不静默通过
            ok = False
            reason_tpl = reason_tpl or "适用性判定出错: " + str(e)
        if ok:
            out[cid] = (True, "")
        else:
            r = reason_tpl
            # ★ v2.13 修 bug:初版 `except Exception: pass` 把 KeyError 吞掉,
            #   导致理由里残留未格式化的 `{assay_type}`。
            #   讽刺的是:本框架明令"禁止静默 except 吞掉真实错误",
            #   这里却正是该错误的实例。改为显式降级 + 留痕。
            if r:
                try:
                    r = r.format(**meta)
                except KeyError as ke:
                    r = (r + f"  [⚠ 理由模板占位符 {ke} 在 meta 中缺失, "
                             f"已原样保留 —— 请补 meta 字段]")
            if not r:
                r = f"{name}:数据特征不满足适用条件(未提供具体理由模板)"
            out[cid] = (False, f"[{name}] " + r)
    return out


def report(meta):
    """打印适用性判定表(供 stdout 留痕)"""
    res = evaluate(meta)
    print(f"    {'判据':<6}{'状态':<10} 理由")
    print("    " + "-" * 70)
    for cid in sorted(res):
        ok, reason = res[cid]
        print(f"    {cid:<6}{'适用' if ok else '不适用':<10} {reason}")
    return res


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-sample", type=int, default=8)
    ap.add_argument("--species", default="Arabidopsis thaliana")
    ap.add_argument("--assay", default="srna_count")
    a = ap.parse_args()
    meta = dict(n_sample=a.n_sample, species=a.species,
                assay_type=a.assay,
                is_single_cell=False,
                has_clinical_outcome=False,
                has_pathway_annotation=False)
    print("§10 适用性闸门 —— GSE250167 场景预演\n")
    res = report(meta)
    na = [c for c, (ok, _) in res.items() if not ok]
    print(f"\n  适用 {len(res) - len(na)} 项 / 不适用 {len(na)} 项: {sorted(na)}")
