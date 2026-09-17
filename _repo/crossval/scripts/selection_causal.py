#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""T31 特征选择泄露 / T32 孟德尔随机化(branch20)。

★ 为什么补这两条 —— 覆盖度复查发现的两类"框架完全没有"的缺口:

【T31】特征选择必须在评估折叠内。
  grep 全库 '特征选择' / '嵌套' / 'CV 内' 命中 0 次。
  T09 只管"性能评估不得用样本内概率",**不管特征选择本身用了全数据集**。
  这是生信预后模型的**头号 AUC 虚高源**:
     全数据集做差异表达 / 单因素 Cox / LASSO 选基因
     → 再在同一批样本上 CV 评估 AUC
     → 每一折的验证集都参与了选基因,性能系统性虚高(selection bias)
  本轮 13 篇里三篇中招(肺癌4基因 / 卵巢癌2基因 / ROMO1),全部是这一结构。

  ★ 与建议文档的两处自相矛盾调和:
    §0 诊断表把 WCMI(小波+条件互信息选特征)标为"缺口",
    §4 又说"属特征工程,不吸收"。
    两者都对 —— **不吸收 WCMI 的方法,但吸收它暴露的防错点**,
    即"特征选择的位置"。T31 正是这个防错点。

【T32】孟德尔随机化。
  建议 §0 写"有 MR 但无判据" —— 实跑 grep:'MR'/'孟德尔'/'mendel' 均 0 次,
  框架里**根本没有 MR**(不是"有而缺判据")。建议此处事实有误,已记录。
  但 MR 确是生信高频(ROMO1 那篇就用 two-sample MR),故补。

铁律:允许判 N/A(非此类研究),但 N/A 必须带理由;
     每条判据配**双向夹具** —— 只跑"合规"不叫验证。
"""
import re

VLABEL = {"pass": "通过", "fail": "不通过", "na": "不适用", "warn": "灰区"}


# ================================================================ T31
# 特征选择 / 超参调优的执行位置

# 合规位置
T31_NESTED = ("nested", "嵌套", "折内", "训练折内", "inner", "in-fold")
# 违规位置:全数据集一次性选择
T31_OUTER = ("全数据集", "整个队列", "outer", "全队列", "先在全部样本",
             "whole cohort", "all samples")
# 独立选择集:等价 nested(选择在一个完全不参与评估的子集上完成)
T31_HOLDOUT = ("独立选择集", "selection set", "holdout selection",
               "独立子集", "discovery cohort")

# 措辞越界:含泄露却声称高性能
T31_PERF_CLAIM = ("高性能", "优异", "AUC", "准确预测", "excellent",
                  "robust performance")

# ★ v2.20 冗余度维度(WCMI 启示):选择位置正确 ≠ 特征集可用
T31_REDUNDANCY_MAX_FRAC = 0.30    # |r|>0.9 占比超过此值 → 冗余过高
T31_REDUNDANCY_WARN_FRAC = 0.10   # 超过此值 → 灰区,建议评估


def check_T31(selection_place=None, n_outer=None, n_inner=None,
              tuned_hp_in_fold=None, external_val=None,
              perf_claim=None, na_reason=None, is_ml_study=True,
              n_selected=None, redundancy_reported=None,
              max_abs_r=None, frac_r_gt_0_9=None):
    """T31 · 特征选择与超参调优必须在评估折叠内(选择泄露)。

    判据:
      (a) 必须声明特征选择的执行位置。未声明 → **判不了**(不得默认 nested)
      (b) nested / 独立选择集 → 通过
      (c) 全数据集一次性选择(outer) → 不通过
      (d) 声称 nested 但给不出外层/内层折数 → 视为未声明(判不了)
      (e) 超参调优同样须在训练折内
      (f) 全数据集选择 + 却声称高性能 → 追加 R5 措辞越界
      (g) 有完全独立外部验证集时:该集性能可用,但训练-CV 性能须标"乐观"

    N/A:非建模类研究(如纯差异表达、纯方法学)→ N/A + 理由
    """
    if not is_ml_study:
        if not na_reason:
            raise ValueError("§10:N/A 必须给出理由(空理由 raise)")
        return "na", "非建模研究", na_reason

    detail, obs, status = [], [], "pass"

    # (a) 位置声明 —— 缺失即判不了,这是本判据的核心
    if selection_place is None:
        return ("na", "未声明选择位置",
                "未声明特征选择执行位置 → **判不了**;"
                "不得默认为 nested(默认放行 = 空规,第11条陷阱形态①)")
    obs.append(f"位置={selection_place}")

    place = str(selection_place).lower()

    # (c) 全数据集选择 —— 直接不通过
    if any(k.lower() in place for k in T31_OUTER):
        status = "fail"
        detail.append("特征选择在**全数据集**一次性完成后再做 CV/拆分评估"
                      " → 每一折验证集都参与了选择,性能系统性虚高"
                      "(selection bias / leakage)")
    # (b) 合规
    elif any(k.lower() in place for k in (T31_NESTED + T31_HOLDOUT)):
        # (d) 声称 nested 必须给出折数
        if any(k.lower() in place for k in T31_NESTED):
            if n_outer is None or n_inner is None:
                return ("na", f"位置={selection_place} 但折数缺失",
                        "声称 nested 但未给出外层/内层折数 → 视为未声明"
                        "(可核验性要求:声称 nested 必须能画出嵌套结构)")
            obs.append(f"外层{n_outer}折/内层{n_inner}折")
        detail.append("特征选择在评估折叠内/独立选择集完成 → 通过")
    else:
        return ("na", f"位置={selection_place}",
                "选择位置表述无法归类(nested/outer/独立选择集)"
                " → 判不了,须明确化")

    # (e) 超参调优
    if tuned_hp_in_fold is None:
        detail.append("(e) 未声明超参调优是否在训练折内(若有调参,须声明)")
    elif not tuned_hp_in_fold:
        status = "fail"
        detail.append("超参调优在折叠外进行 → 同为泄露")
    else:
        obs.append("超参折内调优=True")

    # (f) 泄露 + 高性能声称 = 措辞越界
    if status == "fail" and perf_claim:
        detail.append(f"含选择泄露却声称'{perf_claim}' → 追加 R5 措辞越界,"
                      "须标注'含选择泄露,性能估计乐观'")

    # (g) 外部验证集
    if external_val:
        obs.append(f"外部验证={external_val}")
        if status == "fail":
            detail.append("虽有外部验证集,但**训练-CV 阶段性能仍须标注乐观**"
                          " —— 外部集可用不等于 CV 估计无偏(见 T22 落差判据)")

    # ---- (h)(i) 冗余度维度(v2.20 扩展,WCMI 启示) ----
    # ★ 建议文档指出:T31 只管"选择位置",是**半条判据**。
    #   即使选择位置正确,选出的特征间若高度冗余(|r|>0.9),
    #   会虚高性能且无法解释 —— 这是同一问题的另一半。
    # ★ 触发条件:给出了选中特征数(n_selected)。
    #   不给特征数 = 没有"特征集"可评,本维度不触发(不是默认放行,
    #   是无评估对象;与 T33 的"触发条件"设计同构)。
    if n_selected is not None:
        obs.append(f"选中特征数={n_selected}")
        if (redundancy_reported is None and max_abs_r is None
                and frac_r_gt_0_9 is None):
            status = "fail"
            detail.append("(h) 声称筛选出特征集但**未报告特征间冗余度** → "
                          "判不完整;须给相关矩阵(Pearson/Spearman)")
        else:
            if redundancy_reported:
                obs.append(f"冗余度已报告={redundancy_reported}")
            if max_abs_r is not None:
                obs.append(f"max|r|={max_abs_r}")
            if frac_r_gt_0_9 is not None:
                obs.append(f"|r|>0.9占比={frac_r_gt_0_9}")
                if frac_r_gt_0_9 > T31_REDUNDANCY_MAX_FRAC:
                    status = "fail"
                    detail.append(
                        f"(i) |r|>0.9 的特征对占比 {frac_r_gt_0_9:.0%} > "
                        f"{T31_REDUNDANCY_MAX_FRAC:.0%} → **冗余过高**,"
                        "须做特征去冗余(mRMR / 条件互信息 / VIF 剔除)后重跑;"
                        "高冗余特征集下的性能须标注'乐观'")
                elif frac_r_gt_0_9 > T31_REDUNDANCY_WARN_FRAC:
                    detail.append(
                        f"(i) |r|>0.9 占比 {frac_r_gt_0_9:.0%} 处于灰区"
                        f"(>{T31_REDUNDANCY_WARN_FRAC:.0%})→ 建议评估去冗余")

    if not detail:
        detail.append("选择位置合规")
    return status, ",".join(obs) or "无", "; ".join(detail)


# ================================================================ T32
# 孟德尔随机化工具变量假设

T32_PLEIOTROPY_TEST = ("MR-Egger", "egger_intercept", "MR-PRESSO",
                       "presso", "加权中位数", "weighted median",
                       "weighted mode")
T32_CAUSAL_OVERCLAIM = ("证明因果", "证实因果", "确定因果", "proves causal",
                        "causal proof", "确证因果")
T32_CAUSAL_OK = ("提示因果", "支持因果", "suggests causal", "consistent with")


def check_T32(is_mr=False, f_stat=None, iv_count=None,
              independence_declared=None, pleiotropy_test=None,
              pleiotropy_present=None, heterogeneity_reported=None,
              two_sample=False, ancestry_matched=None,
              exposure_gwas_is_discovery=None,
              causal_claim=None, na_reason=None):
    """T32 · 孟德尔随机化工具变量假设。

    必答项(IV 三假设 + 可核验性):
      (a) 关联性:IV 与暴露强相关,弱工具变量(F < 10)→ 判不确定
      (b) 独立性:IV 与混杂无关(人群分层须主成分校正)—— 须声明
      (c) 排他性:IV 仅通过暴露影响结局(水平多效性)—— 须检验
      (d) 多效性存在时须用稳健方法(median / mode / PRESSO 校正后)
      (e) 异质性(Cochran Q / I²)须报告
      (f) two-sample MR:两样本祖源必须匹配 → 不匹配硬阻断
      (g) 若 IV-暴露关联来自同一 GWAS 发现集 → Winner's curse 须声明
      (h) 措辞:MR 写"提示/支持因果",禁"证明/证实因果"

    N/A:非 MR 研究 → N/A + 理由
    """
    if not is_mr:
        if not na_reason:
            raise ValueError("§10:N/A 必须给出理由(空理由 raise)")
        return "na", "非MR研究", na_reason

    detail, obs, status = [], [], "pass"

    # (a) 弱工具变量
    if f_stat is None and iv_count is None:
        status = "fail"
        detail.append("(a) 未报告 IV 的 F 统计量或工具数 → 无法排除弱工具变量偏倚")
    else:
        if f_stat is not None:
            obs.append(f"F={f_stat}")
            if f_stat < 10:
                status = "fail"
                detail.append(f"F={f_stat} < 10 → **弱工具变量**,"
                              "IV 与暴露关联弱,因果估计向混杂偏倚方向收缩")
        if iv_count is not None:
            obs.append(f"IV数={iv_count}")

    # (b) 独立性
    if independence_declared is None:
        status = "fail" if status == "pass" else status
        detail.append("(b) 未声明 IV 与混杂因素的独立性"
                      "(人群分层须用主成分校正并声明)")
    else:
        obs.append(f"独立性={independence_declared}")

    # (c)(d) 多效性
    if pleiotropy_test is None:
        status = "fail"
        detail.append("(c) 未做水平多效性检验"
                      f"(须为 {'/'.join(T32_PLEIOTROPY_TEST[:4])} 之一)")
    else:
        obs.append(f"多效性检验={pleiotropy_test}")
        if pleiotropy_present:
            robust = any(k.lower() in str(pleiotropy_test).lower()
                         for k in ("median", "mode", "presso"))
            if not robust:
                status = "fail"
                detail.append("(d) 存在水平多效性但未用稳健方法"
                              "(weighted median / mode / PRESSO 校正后)"
                              " → 排他性假设不成立")
            else:
                obs.append("已用稳健方法")
    if heterogeneity_reported is None:
        detail.append("(e) 未报告异质性(Cochran Q / I²)")
    else:
        obs.append(f"异质性={heterogeneity_reported}")

    # (f) two-sample 祖源匹配
    if two_sample:
        obs.append("two-sample")
        if ancestry_matched is None:
            status = "fail"
            detail.append("(f) two-sample MR 未声明两样本祖源匹配")
        elif not ancestry_matched:
            status = "fail"
            detail.append("(f) two-sample MR 两样本**祖源不一致** → **硬阻断**"
                          "(人群结构混杂会使 IV-暴露关联不可迁移)")
        else:
            obs.append("祖源匹配=True")

    # (g) Winner's curse
    if exposure_gwas_is_discovery:
        detail.append("(g) IV-暴露关联来自同一 GWAS 发现集"
                      " → Winner's curse,效应量可能高估,须声明")
        obs.append("发现集复用")

    # (h) 措辞
    if causal_claim:
        if any(k in str(causal_claim) for k in T32_CAUSAL_OVERCLAIM):
            status = "fail"
            detail.append(f"(h) 措辞'{causal_claim}'越界 —— MR 只能"
                          "'提示/支持因果',不得写'证明/证实因果'")
        else:
            obs.append(f"措辞={causal_claim}")

    if not detail:
        detail.append("MR 三假设均已声明且检验齐全")
    return status, ",".join(obs) or "无", "; ".join(detail)


# ================================================================ 双向夹具
# 每条判据:合规项应放行,违规项应拦。只跑合规 = 空规(第11条陷阱形态①)。
FIXTURES = [
    # ---------------- T31:实证锚点来自本轮 13 篇 ----------------
    ("肺癌4基因(Wen 2022 BMC Cancer 22:193)", "T31", dict(
        selection_place="全数据集", perf_claim="高性能",
        external_val="TCGA"), "fail",
     "全队列 CIBERSORT+ESTIMATE+GO/KEGG+Cox+LASSO 选基因 → 再 TCGA 验证"),

    ("卵巢癌2基因(Liang 2021 Front Oncol 11:711020)", "T31", dict(
        selection_place="全数据集", perf_claim="AUC 良好"), "fail",
     "scRNA 定亚群 → bulk 上 WGCNA+单因素Cox+LASSO 选基因 → 同队列评估"),

    ("ROMO1(Wang 2025 FIG 25:91)", "T31", dict(
        selection_place="全数据集"), "fail",
     "whole blood bulk 上 DGE + LASSO 选基因"),

    ("合规:嵌套 CV", "T31", dict(
        selection_place="nested", n_outer=10, n_inner=5,
        tuned_hp_in_fold=True), "pass", "真嵌套可选结构"),

    ("合规:独立选择集", "T31", dict(
        selection_place="独立选择集", tuned_hp_in_fold=True,
        external_val="独立队列"), "pass", "选择在不参与评估的子集上完成"),

    ("声称 nested 但无折数 → 判不了", "T31", dict(
        selection_place="nested"), "na", "可核验性:给不出折数即视为未声明"),

    ("未声明选择位置 → 判不了", "T31", dict(), "na",
     "核心:不得默认 nested,默认放行即空规"),

    ("非建模研究 → N/A", "T31", dict(
        is_ml_study=False, na_reason="纯差异表达分析,无预测建模"), "na",
     "N/A 须带理由"),

    # ---------------- T31 冗余度维度(v2.20 扩展, WCMI 启示) ----------------
    ("WCMI:选了20个特征但完全未报冗余度", "T31", dict(
        selection_place="nested", n_outer=10, n_inner=5,
        tuned_hp_in_fold=True, n_selected=20), "fail",
     "★选择位置正确(嵌套CV)但特征集冗余未知 → 判**不完整**;"
     "这是 T31 的另一半:位置对 ≠ 特征集可用"),

    ("|r|>0.9 占比 45% 未去冗余", "T31", dict(
        selection_place="nested", n_outer=10, n_inner=5,
        tuned_hp_in_fold=True, n_selected=20,
        redundancy_reported=True, max_abs_r=0.97,
        frac_r_gt_0_9=0.45), "fail",
     "冗余过高:高度冗余特征集会**虚高性能且无法解释**,须去冗余后重跑"),

    ("|r|>0.9 占比 12%(灰区)", "T31", dict(
        selection_place="nested", n_outer=10, n_inner=5,
        tuned_hp_in_fold=True, n_selected=20,
        redundancy_reported=True, max_abs_r=0.93,
        frac_r_gt_0_9=0.12), "pass",
     ">10% 触发灰区提示,但未超 30% → 仍通过"),

    ("|r|>0.9 占比 6%(可解释特征集)", "T31", dict(
        selection_place="nested", n_outer=10, n_inner=5,
        tuned_hp_in_fold=True, n_selected=20,
        redundancy_reported=True, max_abs_r=0.86,
        frac_r_gt_0_9=0.06), "pass", "冗余度低 → 通过"),

    # ---------------- T32 ----------------
    ("ROMO1 two-sample MR(Wang 2025)", "T32", dict(
        is_mr=True, two_sample=True, causal_claim="提示因果"), "fail",
     "原文未报告 F 统计量/多效性检验/祖源匹配 → 判不了即不通过"),

    ("弱工具变量 F=8", "T32", dict(
        is_mr=True, f_stat=8, independence_declared=True,
        pleiotropy_test="MR-Egger", heterogeneity_reported=True), "fail",
     "F<10 → 弱工具变量偏倚"),

    ("多效性存在但未用稳健方法", "T32", dict(
        is_mr=True, f_stat=42, independence_declared=True,
        pleiotropy_test="MR-Egger", pleiotropy_present=True,
        heterogeneity_reported=True), "fail", "排他性假设不成立"),

    ("two-sample 祖源不一致", "T32", dict(
        is_mr=True, f_stat=42, independence_declared=True,
        pleiotropy_test="MR-PRESSO", heterogeneity_reported=True,
        two_sample=True, ancestry_matched=False), "fail", "硬阻断"),

    ("措辞越界:证明因果", "T32", dict(
        is_mr=True, f_stat=42, independence_declared=True,
        pleiotropy_test="MR-PRESSO", heterogeneity_reported=True,
        causal_claim="证明因果"), "fail", "R5 措辞越界"),

    ("合规 MR", "T32", dict(
        is_mr=True, f_stat=42, iv_count=18, independence_declared=True,
        pleiotropy_test="MR-PRESSO", heterogeneity_reported=True,
        two_sample=True, ancestry_matched=True,
        causal_claim="提示因果"), "pass", "三假设齐全"),

    ("非 MR 研究 → N/A", "T32", dict(
        na_reason="本研究为差异表达+预后建模,未用 Mendelian randomization"),
        "na", "N/A 须带理由"),
]

CHECKERS = {"T31": check_T31, "T32": check_T32}


def run_fixtures():
    out = []
    for src, cid, kw, expect, note in FIXTURES:
        got, obs, det = CHECKERS[cid](**kw)
        out.append((src, cid, expect, got, obs, det, got == expect))
    return out


if __name__ == "__main__":
    print("=== T31 特征选择泄露 / T32 孟德尔随机化(双向夹具) ===")
    rows = run_fixtures()
    for src, cid, expect, got, obs, det, match in rows:
        flag = "OK " if match else "XX "
        print(f"{flag}[{cid}] {src}\n"
              f"     期望={VLABEL[expect]:<6} 实际={VLABEL[got]:<6} | {obs} | {det}")
    bad = [r for r in rows if not r[6]]
    print(f"\n合计 {len(rows)} 条,符合 {len(rows)-len(bad)},不符合 {len(bad)}")
    raise SystemExit(1 if bad else 0)
