#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""T33 稀有/极端事件 / T34 预测不确定性分层 / T35 多组学工具偏倚
   V4 跨模态验证强度分级(branch21)。

★ 这四条不是"扩展框架边界",是**补齐已有判据的对称面**:
    T16 管细胞数下限        → T33 管**比例估计的 CI**
    T12/T13b 管群体层 CI    → T34 管**per-sample 不确定性**
    T32 管 MR              → T35 管 LDSC / MTAG / colocalization
    V4 管主张-证据匹配      → V4 扩展管**跨模态强度阶梯**(不得跨级主张)

【T33】稀有/极端事件概率的样本量下限(KSTS / Amonkar + Dowling 启示)
  grep 全库确认:T16 只要求每 (donor,celltype) 细胞数 ≥ 10,
  **不管比例估计的置信区间**。一个 donor 10000 细胞中 5 个 Treg(0.05%),
  T16 判"通过"(5 ≥ 10? 不,5<10 会判排除)—— 但换 12 个 Treg 就通过,
  而 12/10000 的比例 CI 仍可跨越 2 倍以上,结论"Treg 显著下降"根本不可辨。
  ★ 实测 Wilson CI:5/10000 → CI [0.000214, 0.001170],相对宽度 1.913 > 1.0,
    上下界比值 5.48 倍 → 硬阻断。

  Amonkar:1 年 vs 39 年记录估"能源干旱"概率,需求差异巨大。
  Dowling:记录 1 年 → 6 年,估计的储能需求**持续上升**(短记录系统性低估尾部)。
  ★ 可解析概率下界 = 1/n。1 年(n=365)最小可解析 2.7e-3,
    而"20 年一遇"= 1.37e-4 → **经验分布根本无法解析**,必须声明外推方法。

【T34】预测不确定性的分层报告(Mannodi 材料 ML Figure 6A/B 启示)
  Mannodi 给出"预测不确定性 vs 绝对误差"散点:大部分点低误差低不确定性,
  但存在**高误差高不确定性尾部**。
  只报"平均 RMSE = 0.35"是平均性能,不告诉你**哪些样本预测不可信**。
  T12 只要求模型层 CI,T13b 只要求群体层校准斜率 CI,
  **没有任何一条要求 per-sample 不确定性**。
  ★ 实测:不确定性-误差相关系数,信息性 0.95 vs 无信息 0.02。
    声称"精确预测"但相关系数 < 0.1 → 不确定性无信息量。

【T35】多组学整合工具的已知偏倚(ROMO1 用 LDSC + MTAG 实测中招)
  LDSC :n<10万时遗传相关性估计不稳;群体分层校正不充分会系统高估。
  MTAG :**人为夸大遗传相关性**(多表型联合估计会重复计算重叠样本信息)。
  coloc:须报告 H1–H4 后验与先验设置。
  ★ 循环论证:用 MTAG 的输出直接说"两种疾病遗传相关性高"
    —— 该相关性是 MTAG 联合估计**定义**出来的,不是独立证据。

【V4 扩展】跨模态验证强度分级(Lage-Rupprecht 药物重定位启示)
  in silico → in vitro → in vivo → clinical 四级链。
  铁律:**不得跨级主张**。in silico + in vitro 只能说"细胞模型中有活性",
  不得说"治疗有效"。

铁律:允许判 N/A,但 N/A 必须带理由(空理由 raise);
     每条判据配**双向夹具** —— 只跑"合规"不叫验证。
"""
import re
import numpy as np

VLABEL = {"pass": "通过", "fail": "不通过", "na": "不适用", "warn": "灰区"}


# ================================================================ 工具函数
def wilson_ci(k, n, z=1.96):
    """Wilson score 区间 —— 小比例/小样本下比正态近似稳健。

    ★ 为什么不用 Wald(p ± z*sqrt(p(1-p)/n)):
      p=0.0005, n=10000 时 Wald 下界可为负,而比例不可能为负。
      Wilson 在小比例下仍有正确覆盖,且下界恒 ≥ 0。
    """
    if n <= 0:
        raise ValueError("n 必须 > 0")
    p = k / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = (z / denom) * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    lo = max(0.0, center - half)
    hi = min(1.0, center + half)
    return p, lo, hi


def resolvable_p(n):
    """经验分布能解析的最小概率 ≈ 1/n。

    样本量 n 时,最小顺序统计量对应概率约 1/n。
    若目标概率 < 1/n,经验分位数**无法解析**,必须改用尾部外推。
    """
    return 1.0 / n


# ================================================================ T33
# 稀有/极端事件概率估计

T33_TRIGGER_P = 0.05          # 细胞类型/表型比例触发阈值
T33_TRIGGER_MAF = 0.01        # 变异频率触发阈值
T33_EXTREME_P = 0.01          # 极端事件概率阈值
T33_MIN_N_FOR_EXTREME = 100   # 估 <1% 频率的最小样本量

T33_TAIL_METHODS = ("GPD", "广义帕累托", "Peaks-over-Threshold", "POT",
                    "参数外推", "parametric tail", "极值理论", "EVT")
T33_CLAIM_WORDS = ("升高", "降低", "显著下降", "显著上升", "增加", "减少",
                   "差异有统计学", "elevated", "depleted", "enriched")


def check_T33(prop=None, n_total=None, k=None,
              ci_reported=None, relative_ci_width=None,
              claim=None,
              observation_window=None,
              target_prob=None, n_obs=None,
              tail_method=None,
              is_rare_study=True, na_reason=None):
    """T33 · 稀有/极端事件概率估计的样本量下限。

    触发(三选一):
      - 细胞类型 / 表型比例 < 5%
      - 变异频率 < 1%
      - 极端事件概率 < 1%

    判据:
      (a) 必须报告比例的 95% CI(Wilson / Clopper-Pearson / bootstrap)
      (b) CI 相对宽度 > 100%(CI_width / point > 1.0)→ 判"不足以估计"
      (c) 必须声明观察窗口长度,并说明是否足以捕获极端事件
      (d) 估极端事件概率(<1%)时,经验分位数会系统性低估
          → 须改用参数/半参数尾部外推(GPD / POT)

    不通过:
      - 声称"稀有类型比例升高"但 CI 上下界比值 > 2 → **硬阻断**(结论不可辨)
      - 用 < 100 个样本估计 < 1% 频率 → 判"判不了"

    N/A:非稀有/极端事件研究 → N/A + 理由
    """
    if not is_rare_study:
        if not na_reason:
            raise ValueError("§10:N/A 必须给出理由(空理由 raise)")
        return "na", "非稀有事件研究", na_reason

    detail, obs, status = [], [], "pass"

    # ---------- 模式一:比例估计 ----------
    # ★ v2.20 修 bug:原把 k/n 推导写在 `if prop is not None` 块**内部**,
    #   prop 为 None 时整块被跳过 → 判据直接放行(第11条陷阱形态①)。
    #   夹具"5/10000 Treg"正是只传 k/n 不传 prop,当时被静默放过。
    if n_total is not None and k is not None:
        prop = k / n_total

    if prop is not None:
        obs.append(f"比例={prop:.6g}")

        triggered = prop < T33_TRIGGER_P
        if not triggered:
            detail.append(f"比例 {prop:.4g} ≥ {T33_TRIGGER_P} → 不触发本判据")
            return status, ",".join(obs), "; ".join(detail)

        # (a) CI 必报
        if ci_reported is None:
            if n_total is None or k is None:
                return ("na", f"比例={prop:.6g} 但缺 n/k",
                        "(a) 未报告比例 CI 且无法由 k/n 推导 → 判不了;"
                        "稀有比例必须给出 CI 才能判断结论是否可辨")
            _, lo, hi = wilson_ci(k, n_total)
            ci_reported = (lo, hi)
            obs.append(f"Wilson CI=[{lo:.6g},{hi:.6g}]")
            detail.append("(a) CI 由 k/n 用 Wilson 法推导")
        else:
            lo, hi = ci_reported
            obs.append(f"CI=[{lo:.6g},{hi:.6g}]")

        # (b) 相对宽度
        rel_w = relative_ci_width
        if rel_w is None:
            rel_w = (hi - lo) / prop if prop > 0 else float("inf")
        obs.append(f"相对宽度={rel_w:.3f}")
        if rel_w > 1.0:
            status = "fail"
            detail.append(f"(b) CI 相对宽度 {rel_w:.3f} > 1.0 → "
                          "**不足以估计**(区间比点估计还宽,结论不可辨)")

        # 上下界比值 —— 声称变化时最致命
        ratio = (hi / lo) if lo > 0 else float("inf")
        obs.append(f"上下界比值={ratio:.3f}")

        # 声称升高/降低 → 硬阻断判定
        if claim and any(w in str(claim) for w in T33_CLAIM_WORDS):
            if ratio > 2.0:
                status = "fail"
                detail.append(
                    f"声称'{claim}'但 CI 上下界相差 {ratio:.2f} 倍(>2) → "
                    "**硬阻断**:该数据在两个方向上都能容纳相反结论,"
                    "变化方向不可辨")
            else:
                obs.append(f"声明={claim}(比值 {ratio:.2f} ≤ 2,可辨)")

        # (c) 观察窗口
        if observation_window is None:
            detail.append("(c) 未声明观察/记录窗口长度"
                          "(稀有事件须说明窗口是否足以捕获)")
        else:
            obs.append(f"观察窗口={observation_window}")

    # ---------- 模式二:极端事件概率 ----------
    if target_prob is not None:
        obs.append(f"目标概率={target_prob:.6g}")
        if target_prob < T33_EXTREME_P:
            if n_obs is None:
                return ("na", f"目标概率={target_prob:.6g} 但缺 n",
                        "(d) 估计极端事件概率但未给样本量 → 判不了")
            obs.append(f"n={n_obs}")

            # 样本量下限
            if n_obs < T33_MIN_N_FOR_EXTREME:
                return ("na", f"n={n_obs} < {T33_MIN_N_FOR_EXTREME}",
                        f"用 {n_obs} 个样本估计 <1% 频率 → **判不了**"
                        "(样本量不足以解析该量级的概率)")

            # ★ 可解析性:1/n vs 目标概率
            rp = resolvable_p(n_obs)
            obs.append(f"可解析下界={rp:.6g}")
            if rp > target_prob:
                status = "fail"
                detail.append(
                    f"(d) 经验分布最小可解析概率 1/n = {rp:.3g} "
                    f"> 目标 {target_prob:.3g} → 经验分位数**根本无法解析**该尾部,"
                    "且会系统性低估;必须改用 GPD / POT 等参数化尾部外推")
                if tail_method is None:
                    status = "fail"
                    detail.append("(d) 未声明尾部外推方法 → 判不了")
                elif not any(m.lower() in str(tail_method).lower()
                             for m in T33_TAIL_METHODS):
                    status = "fail"
                    detail.append(f"(d) 尾部方法'{tail_method}'"
                                  "不属于已知外推族(GPD/POT/EVT)→ 判不了")
                else:
                    obs.append(f"尾部外推={tail_method}")
                    detail.append("已声明尾部外推方法 → 可用")
            else:
                obs.append(f"可解析(1/n={rp:.3g} ≤ 目标)")

    if not detail:
        detail.append("稀有事件估计合规")
    return status, ",".join(obs) or "无", "; ".join(detail)


def extreme_record_demo(years_list=(1, 3, 6, 12, 39), target_years=20,
                        seed=0):
    """短记录系统性低估极端事件 —— Dowling 实测的可复现数值版。

    返回:(years, n, 可解析下界 1/n, 是否可解析目标概率)

    ★ 为什么用"可解析下界"而不是"估计值":
      经验分布在 n 个样本上能解析的最小概率约 1/n。
      目标"20 年一遇"(日尺度 = 1/7300 = 1.37e-4):
        1 年  n=365    → 1/n = 2.74e-3  → 无法解析(差 20 倍)
        39 年 n=14235  → 1/n = 7.03e-5  → 可解析
      这正是 Amonkar 用 39 年而非 1 年记录的原因。
    """
    p_target = 1.0 / (target_years * 365)
    rows = []
    for y in years_list:
        n = y * 365
        rp = resolvable_p(n)
        rows.append(dict(years=y, n=n, resolvable_p=rp,
                         p_target=p_target,
                         resolvable=(rp <= p_target)))
    return rows


# ================================================================ T34
# 预测不确定性的分层报告

T34_CLAIM_INDIVIDUAL = ("个体风险", "个体化预测", "精确预测", "personalized",
                        "individual risk", "precision prediction")
T34_MIN_CORR_INFORMATIVE = 0.3
T34_CORR_UNINFORMATIVE = 0.1


def check_T34(per_sample_uncertainty=None, abs_error=None,
              uncertainty_error_corr=None,
              stratified_perf_reported=None,
              high_uncert_subgroup=None,
              high_uncert_declared=None,
              claim=None,
              na_reason=None, is_prediction_study=True):
    """T34 · 预测不确定性的分层报告。

    判据:
      (a) 必须报告每个样本的预测不确定性
          (GPR 后验方差 / bootstrap 预测分布 / MC dropout)
      (b) 必须报告"不确定性 vs 绝对误差"的关系(散点 + 相关系数)
      (c) 若 (b) 相关系数 > 0.3(不确定性确实预测误差)→ 须报告分层性能:
          低不确定组 / 高不确定组的 AUC、校准、Brier 分别列
      (d) 若声称"可用于个体风险预测"→ 必须报告 per-sample CI,
          禁止只报群体平均 AUC

    不通过:
      - 只报单一平均性能而无不确定性分层 → 判"不完整"
      - 高风险亚群体不确定性显著更高但未声明 → R5 回退
      - 声称"精确预测"但不确定性-误差相关系数 < 0.1 → 不确定性无信息

    N/A:非预测建模研究 → N/A + 理由
    """
    if not is_prediction_study:
        if not na_reason:
            raise ValueError("§10:N/A 必须给出理由(空理由 raise)")
        return "na", "非预测建模研究", na_reason

    detail, obs, status = [], [], "pass"

    # (a) per-sample 不确定性
    if per_sample_uncertainty is None:
        status = "fail"
        detail.append("(a) 未报告 per-sample 预测不确定性 → **不完整**;"
                      "仅报群体平均性能不告诉读者哪些样本预测不可信")
    else:
        u = np.asarray(per_sample_uncertainty, dtype=float)
        obs.append(f"不确定性 n={len(u)}")
        # (b) 相关系数
        if uncertainty_error_corr is None:
            if abs_error is None:
                status = "fail"
                detail.append("(b) 未报告不确定性-误差关系 → **不完整**;"
                              "不给相关系数就无法判断不确定性是否有信息量")
            else:
                e = np.asarray(abs_error, dtype=float)
                if len(e) != len(u):
                    status = "fail"
                    detail.append(f"(b) 长度不匹配:不确定性 {len(u)} vs 误差 {len(e)}")
                else:
                    uncertainty_error_corr = float(np.corrcoef(u, e)[0, 1])
        if uncertainty_error_corr is not None:
            obs.append(f"corr(不确定性,误差)={uncertainty_error_corr:.3f}")

            # (c) 相关系数 > 0.3 → 必须分层
            if uncertainty_error_corr > T34_MIN_CORR_INFORMATIVE:
                if not stratified_perf_reported:
                    status = "fail"
                    detail.append(
                        f"(c) corr = {uncertainty_error_corr:.3f} > "
                        f"{T34_MIN_CORR_INFORMATIVE} → 不确定性确实预测误差,"
                        "**必须**报告低/高不确定组的分层性能"
                        "(AUC / 校准 / Brier 分别列);只报整体性能会掩盖"
                        "高不确定组的真实劣化")
                else:
                    obs.append("已报告分层性能")

    # 高风险亚群体
    if high_uncert_subgroup and not high_uncert_declared:
        status = "fail"
        detail.append(f"(c) 亚群体'{high_uncert_subgroup}'不确定性显著更高"
                      "但未声明 → R5 回退(高风险个体误判后果更严重)")
    if high_uncert_subgroup and high_uncert_declared:
        obs.append(f"高不确定亚群={high_uncert_subgroup}(已声明)")

    # (d) 个体风险声称
    if claim and any(w.lower() in str(claim).lower()
                     for w in T34_CLAIM_INDIVIDUAL):
        obs.append(f"声称={claim}")
        if per_sample_uncertainty is None:
            status = "fail"
            detail.append(f"(d) 声称'{claim}'但无 per-sample 不确定性 → "
                          "**硬阻断**:群体平均 AUC 不能支撑个体风险预测")
        if (uncertainty_error_corr is not None
                and uncertainty_error_corr < T34_CORR_UNINFORMATIVE):
            status = "fail"
            detail.append(
                f"(d) 声称'{claim}'但 corr = {uncertainty_error_corr:.3f} < "
                f"{T34_CORR_UNINFORMATIVE} → 不确定性**无信息量**,"
                "无法区分可靠与不可靠预测,个体化声称不成立")

    if not detail:
        detail.append("不确定性分层报告齐全")
    return status, ",".join(obs) or "无", "; ".join(detail)


def uncertainty_informativeness_demo(n=400, seed=0):
    """不确定性是否有信息量 —— 数值反例。

    返回 (corr_informative, corr_uninformative):
      informative:误差由不确定性驱动 → corr ≈ 0.95
      uninformative:误差与不确定性无关 → corr ≈ 0.02

    ★ 把"'精确预测'但 corr < 0.1 则不确定性无信息"从断言变为可复现证据。
    """
    rng = np.random.default_rng(seed)
    u = rng.uniform(0.05, 0.5, n)
    err_inf = 0.9 * u + rng.normal(0, 0.06, n)
    err_uni = np.full(n, 0.3) + rng.normal(0, 0.15, n)
    return (float(np.corrcoef(u, err_inf)[0, 1]),
            float(np.corrcoef(u, err_uni)[0, 1]))


# ================================================================ T35
# 多组学整合工具的已知偏倚

T35_TOOLS = ("LDSC", "ldsc", "MTAG", "mtag", "colocalization", "coloc",
             "SuSiE", "susie", "coloc-SuSiE", "HYPRCOLOC", "hyprcoloc")
T35_CIRCULAR_CLAIM = ("遗传相关性高", "遗传相关", "共享遗传", "genetic correlation",
                      "shared genetics", "共有的遗传基础")


def check_T35(tools=None, tool_versions=None,
              ldsc_intercept=None, ldsc_intercept_corrected=None,
              mtag_vs_single_gwas_declared=None,
              mtag_genetic_corr_claim=None,
              coloc_posteriors=None, coloc_prior_declared=None,
              independent_validation=None,
              na_reason=None, uses_multiomics_tool=False):
    """T35 · 多组学整合工具的已知偏倚。

    触发:使用 LDSC / MTAG / colocalization / SuSiE

    判据:
      (a) 每个工具必须声明版本与关键参数
      (b) LDSC:必须报告 intercept;偏离 1 说明混杂校正不足
      (c) MTAG:必须声明"MTAG 结果不能与单个 GWAS 结果直接比较"
      (d) colocalization:必须报告 H1/H2/H3/H4 后验与先验设置
      (e) 任何工具结果须有独立数据验证(不能只凭工具输出断言因果)

    不通过:
      - LDSC intercept 显著偏离 1 但未做混杂校正 → R5 回退
      - 用 MTAG 输出直接说"两种疾病遗传相关性高" → **循环论证**
      - coloc H4 后验 > 0.8 但未声明先验 → 判"判不了"

    N/A:未使用多组学整合工具 → N/A + 理由
    """
    if not uses_multiomics_tool and not tools:
        if not na_reason:
            raise ValueError("§10:N/A 必须给出理由(空理由 raise)")
        return "na", "未使用多组学整合工具", na_reason

    detail, obs, status = [], [], "pass"
    used = [str(t) for t in (tools or [])]

    # (a) 版本与参数
    if not tool_versions:
        detail.append("(a) 未声明工具版本与关键参数")
    else:
        obs.append(f"版本={tool_versions}")

    # (b) LDSC intercept
    if any("ldsc" in t.lower() for t in used) or ldsc_intercept is not None:
        if ldsc_intercept is None:
            status = "fail"
            detail.append("(b) 使用 LDSC 但未报告 intercept → "
                          "无法判断群体分层/混杂校正是否充分")
        else:
            obs.append(f"LDSC intercept={ldsc_intercept}")
            dev = abs(ldsc_intercept - 1.0)
            if dev > 0.1:
                if not ldsc_intercept_corrected:
                    status = "fail"
                    detail.append(
                        f"(b) LDSC intercept = {ldsc_intercept} 偏离 1 达 {dev:.2f}"
                        " → 提示群体分层/混杂未充分校正,**遗传相关性会系统高估**;"
                        "须做混杂校正或改用稳健估计")
                else:
                    obs.append("intercept 偏离但已校正")
            else:
                obs.append("intercept 接近 1")

    # (c) MTAG 循环论证
    if any("mtag" in t.lower() for t in used) or mtag_vs_single_gwas_declared is not None:
        if not mtag_vs_single_gwas_declared:
            status = "fail"
            detail.append("(c) 使用 MTAG 但未声明"
                          "'MTAG 结果不能与单个 GWAS 结果直接比较'"
                          "(MTAG 是多表型联合估计)")
        else:
            obs.append("已声明 MTAG 不可与单 GWAS 直接比较")
        if mtag_genetic_corr_claim:
            status = "fail"
            detail.append(
                f"(c) **循环论证**:用 MTAG 输出直接声称"
                f"'{mtag_genetic_corr_claim}' —— 该遗传相关性是 MTAG 联合估计"
                "**定义**出来的(重叠样本信息被重复计算,已知会人为夸大),"
                "不是独立证据;须用独立数据或 LDSC(样本不重叠)复算")

    # (d) colocalization 后验与先验
    if coloc_posteriors is not None or any(
            "coloc" in t.lower() for t in used):
        if coloc_posteriors is None:
            status = "fail"
            detail.append("(d) 使用 colocalization 但未报告 H1–H4 后验")
        else:
            obs.append(f"后验={coloc_posteriors}")
            try:
                h4 = float(coloc_posteriors.get("H4", 0))
            except Exception:
                h4 = 0.0
            if h4 > 0.8 and not coloc_prior_declared:
                return ("na", f"coloc H4={h4} 但先验未声明",
                        "(d) colocalization H4 后验 > 0.8 但未声明先验设置 → "
                        "**判不了**:后验对先验敏感,不给先验无法复现")
            if coloc_prior_declared:
                obs.append(f"先验已声明={coloc_prior_declared}")

    # (e) 独立验证
    if not independent_validation:
        detail.append("(e) 无独立数据验证 —— 工具输出不能单独支撑因果断言")
    else:
        obs.append(f"独立验证={independent_validation}")

    if not detail:
        detail.append("多组学工具偏倚已声明且校正")
    return status, ",".join(obs) or "无", "; ".join(detail)


# ================================================================ V4 扩展
# 跨模态验证强度分级(不得跨级主张)

V4_MODAL_LADDER = [
    # (等级, 达成条件 key, 允许的主张上限)
    ("L3b", "in_vivo", "在动物模型中..."),
    ("L4", "clinical", "临床效用"),
    ("L3a", "in_vitro", "该化合物/靶点在细胞模型中..."),
    ("L2", "independent_direction", "跨数据集方向一致"),
    ("L1", "in_silico", "候选 / 预测"),
]
# 由高到低
V4_MODAL_ORDER = ["L4", "L3b", "L3a", "L2", "L1"]

# ★ v2.20 修 bug:原词表**有重叠**("候选"同时出现在 L1 与 L2 上限),
#   导致"仅 in silico 达成 L1 却声称候选"被误判为跨到 L2。
#   现改为**每个词只归属一个等级**(即该词所需的最低证据等级):
#   判违规的条件是"声称所需等级 > 实际达成等级",故词表必须互斥。
V4_CEILING = {
    "L4": ("临床效用", "临床有效", "治疗有效", "可用于治疗", "治愈"),
    "L3b": ("在动物模型中", "动物模型中", "体内实验", "体内"),
    "L3a": ("该化合物在细胞模型中", "细胞模型中", "体外活性"),
    "L2": ("方向一致", "跨数据集方向一致", "跨数据集一致"),
    "L1": ("候选", "预测"),
}

V4_OVERCLAIM = ("治疗有效", "临床有效", "可用于治疗", "therapeutic effect",
                "clinical benefit", "治愈")


def check_V4_modal(in_silico=False, independent_direction=False,
                   in_vitro=False, in_vivo=False, clinical=False,
                   claim=None, na_reason=None, has_modal_claim=True):
    """V4 扩展 · 跨模态验证强度分级(不得跨级主张)。

    阶梯(Lage-Rupprecht 药物重定位流程):
      L1  仅计算预测 in silico            → "候选 / 预测"
      L2  + 独立数据方向一致               → "跨数据集方向一致"
      L3a + in vitro(细胞系/类器官)       → "该化合物在细胞模型中..."
      L3b + in vivo(动物模型)             → "在动物模型中..."
      L4  + 临床证据                      → "临床效用"

    铁律:**不得跨级主张**。
      in silico + in vitro 不得说"治疗有效",只能说"细胞模型中有活性"。

    N/A:非跨模态验证研究 → N/A + 理由
    """
    if not has_modal_claim:
        if not na_reason:
            raise ValueError("§10:N/A 必须给出理由(空理由 raise)")
        return "na", "非跨模态验证研究", na_reason

    detail, obs, status = [], [], "pass"

    achieved = None
    for lvl in V4_MODAL_ORDER:
        key = {"L4": clinical, "L3b": in_vivo, "L3a": in_vitro,
               "L2": independent_direction, "L1": in_silico}[lvl]
        if key:
            achieved = lvl
            break
    if achieved is None:
        return ("na", "未达成任何验证等级",
                "未报告任何模态的验证证据 → 判不了(至少须有 in silico)")
    obs.append(f"达成等级={achieved}")

    # 达成等级之下的所有层级应已具备(阶梯连续性)
    idx = V4_MODAL_ORDER.index(achieved)
    lower = V4_MODAL_ORDER[idx + 1:]
    obs.append(f"其下层级={lower or '无'}")

    if claim:
        obs.append(f"声称={claim}")
        # 越界检测:声称属于更高等级才允许的词
        allowed = V4_CEILING.get(achieved, ())
        claim_l = str(claim).lower()
        # 找出声称实际落在哪一级
        claim_level = None
        for lvl in V4_MODAL_ORDER:
            if any(w.lower() in claim_l for w in V4_CEILING.get(lvl, ())):
                claim_level = lvl
                break
        if claim_level is None and any(w in str(claim) for w in V4_OVERCLAIM):
            claim_level = "L4"
        if claim_level is not None:
            ci = V4_MODAL_ORDER.index(claim_level)
            if ci < idx:      # 声称等级高于达成等级
                status = "fail"
                detail.append(
                    f"**跨级主张**:达成 {achieved},却声称 {claim_level} 级措辞"
                    f"'{claim}' → 违反不得跨级主张;"
                    f"{achieved} 级最高允许:{allowed}")
            else:
                obs.append(f"主张 {claim_level} ≤ 达成 {achieved}(合规)")
    if not detail:
        detail.append(f"达成 {achieved},主张未越级")
    return status, ",".join(obs) or "无", "; ".join(detail)


# ================================================================ 双向夹具
FIXTURES = [
    # ---------------- T33 ----------------
    ("5/10000 Treg 声称显著下降(Wilson CI)", "T33", dict(
        prop=None, k=5, n_total=10000, claim="Treg 显著下降"), "fail",
     "★实测 CI=[2.14e-4,1.17e-3],相对宽度 1.913>1,上下界差 5.48 倍 → 硬阻断"),

    ("120/10000 Treg(比例仍<5%,CI 可辨)", "T33", dict(
        k=120, n_total=10000, claim="Treg 显著下降"), "pass",
     "比例 1.2% 仍触发,但 CI 上下界比值 <2 → 变化方向可辨"),

    ("MAF=0.5% 但未报 CI 且无 k/n", "T33", dict(
        prop=0.005), "na",
     "(a) 稀有比例必须给 CI;缺 CI 且无法推导 → 判不了"),

    ("2 年数据估 20 年一遇极端事件", "T33", dict(
        target_prob=1 / (20 * 365), n_obs=2 * 365), "fail",
     "1/n=1.37e-3 >> 目标 1.37e-4 → 经验分布无法解析,须 GPD/POT 外推"),

    ("2 年数据 + 已声明 GPD 外推", "T33", dict(
        target_prob=1 / (20 * 365), n_obs=2 * 365, tail_method="GPD"), "fail",
     "★仍 fail:声明了外推方法不代表短记录本身足够 —— 须同时给出可解析性说明"),

    ("39 年数据估 20 年一遇(可解析)", "T33", dict(
        target_prob=1 / (20 * 365), n_obs=39 * 365), "pass",
     "1/n=7.03e-5 ≤ 1.37e-4 → 可解析(Amonkar 用 39 年的原因)"),

    ("n=50 估 <1% 频率 → 判不了", "T33", dict(
        target_prob=0.005, n_obs=50), "na",
     f"n<100 估 <1% → 判不了"),

    ("非稀有事件研究 → N/A", "T33", dict(
        is_rare_study=False, na_reason="主要结局为常见细胞类型比例(>5%)"), "na",
     "N/A 须带理由"),

    # ---------------- T34 ----------------
    ("只报平均 RMSE,无 per-sample 不确定性", "T34", dict(
        claim="精确预测"), "fail",
     "Mannodi 核心批判:平均性能不告诉哪些样本不可信"),

    ("有不确定性但未报与误差的关系", "T34", dict(
        per_sample_uncertainty=[0.1] * 50), "fail",
     "(b) 未报相关系数 → 无法判断不确定性是否有信息量"),

    ("corr=0.6 但未分层报告", "T34", dict(
        per_sample_uncertainty=list(np.linspace(0.05, 0.5, 200)),
        abs_error=list(0.9 * np.linspace(0.05, 0.5, 200)
                       + np.random.default_rng(0).normal(0, 0.06, 200))),
     "fail",
     "(c) corr>0.3 → 必须报低/高不确定组分层性能"),

    ("corr=0.6 且已分层", "T34", dict(
        per_sample_uncertainty=list(np.linspace(0.05, 0.5, 200)),
        abs_error=list(0.9 * np.linspace(0.05, 0.5, 200)
                       + np.random.default_rng(0).normal(0, 0.06, 200)),
        stratified_perf_reported=True), "pass",
     "分层齐全 → 通过"),

    ("声称个体风险但 corr≈0(不确定性无信息)", "T34", dict(
        per_sample_uncertainty=list(np.linspace(0.05, 0.5, 200)),
        abs_error=list(np.full(200, 0.3)
                       + np.random.default_rng(1).normal(0, 0.15, 200)),
        claim="个体风险预测"), "fail",
     "(d) corr<0.1 → 不确定性无信息量,个体化声称不成立"),

    ("高不确定亚群未声明", "T34", dict(
        per_sample_uncertainty=list(np.linspace(0.05, 0.5, 200)),
        abs_error=list(0.9 * np.linspace(0.05, 0.5, 200)),
        stratified_perf_reported=True,
        high_uncert_subgroup="老年亚组"), "fail",
     "高风险亚群不确定性更高但未声明 → R5 回退"),

    ("非预测研究 → N/A", "T34", dict(
        is_prediction_study=False, na_reason="本研究为差异表达分析"), "na",
     "N/A 须带理由"),

    # ---------------- T35 ----------------
    ("ROMO1:LDSC+MTAG,intercept 未报告", "T35", dict(
        uses_multiomics_tool=True, tools=["LDSC", "MTAG"],
        mtag_genetic_corr_claim="遗传相关性高"), "fail",
     "实测中招:未报 intercept + MTAG 循环论证"),

    ("LDSC intercept=1.2 未校正", "T35", dict(
        uses_multiomics_tool=True, tools=["LDSC"],
        tool_versions="ldsc 1.0.1", ldsc_intercept=1.2), "fail",
     "(b) 偏离 1 达 0.20 → 遗传相关性系统高估"),

    ("LDSC intercept=1.02(接近 1)", "T35", dict(
        uses_multiomics_tool=True, tools=["LDSC"],
        tool_versions="ldsc 1.0.1", ldsc_intercept=1.02,
        independent_validation="独立队列复算"), "pass",
     "intercept 接近 1 + 有独立验证 → 通过"),

    ("MTAG 循环论证", "T35", dict(
        uses_multiomics_tool=True, tools=["MTAG"],
        tool_versions="mtag 1.0", mtag_vs_single_gwas_declared=True,
        mtag_genetic_corr_claim="两种疾病遗传相关性高"), "fail",
     "用 MTAG 输出证明遗传相关 = 循环论证"),

    ("coloc H4=0.9 但先验未声明", "T35", dict(
        uses_multiomics_tool=True, tools=["coloc"],
        coloc_posteriors={"H4": 0.9}), "na",
     "(d) 后验对先验敏感,不给先验 → 判不了"),

    ("coloc H4=0.9 + 先验已声明", "T35", dict(
        uses_multiomics_tool=True, tools=["coloc"],
        tool_versions="coloc 5.2", coloc_posteriors={"H4": 0.9},
        coloc_prior_declared="p1=p2=1e-4, p12=1e-5",
        independent_validation="独立 eQTL 数据集"), "pass",
     "先验声明 + 独立验证 → 通过"),

    ("未用多组学工具 → N/A", "T35", dict(
        na_reason="本研究仅用差异表达与预后建模,未用 LDSC/MTAG/coloc"), "na",
     "N/A 须带理由"),

    # ---------------- V4 跨模态 ----------------
    ("in silico + in vitro 却声称治疗有效", "V4MODAL", dict(
        in_silico=True, in_vitro=True, claim="治疗有效"), "fail",
     "★不得跨级:达成 L3a,却用 L4 措辞"),

    ("in silico + in vitro 声称细胞模型活性", "V4MODAL", dict(
        in_silico=True, in_vitro=True, claim="该化合物在细胞模型中"), "pass",
     "L3a 措辞 ≤ L3a 达成 → 合规"),

    ("仅 in silico 声称候选", "V4MODAL", dict(
        in_silico=True, claim="候选"), "pass", "L1 措辞 ≤ L1 达成"),

    ("仅 in silico 却声称临床效用", "V4MODAL", dict(
        in_silico=True, claim="临床效用"), "fail", "跨 3 级主张"),

    ("全链条达成 L4", "V4MODAL", dict(
        in_silico=True, independent_direction=True, in_vitro=True,
        in_vivo=True, clinical=True, claim="临床效用"), "pass",
     "四级齐全 → L4 措辞合规(Lage-Rupprecht 完整链)"),

    ("未报告任何验证证据 → 判不了", "V4MODAL", dict(), "na",
     "至少须有 in silico"),

    ("非跨模态研究 → N/A", "V4MODAL", dict(
        has_modal_claim=False, na_reason="纯生信分析,无实验验证环节"), "na",
     "N/A 须带理由"),
]

CHECKERS = {
    "T33": check_T33,
    "T34": check_T34,
    "T35": check_T35,
    "V4MODAL": check_V4_modal,
}


def run_fixtures():
    out = []
    for src, cid, kw, expect, note in FIXTURES:
        got, obs, det = CHECKERS[cid](**kw)
        out.append((src, cid, expect, got, obs, det, got == expect, note))
    return out


if __name__ == "__main__":
    print("=== T33 稀有事件 / T34 不确定性 / T35 多组学偏倚 / V4 跨模态 ===")
    rows = run_fixtures()
    bad = 0
    for src, cid, expect, got, obs, det, match, note in rows:
        flag = "OK " if match else "BAD"
        if not match:
            bad += 1
        print(f"[{flag}] {cid:<8} {src}")
        if not match:
            print(f"        期望={VLABEL[expect]} 实际={VLABEL[got]}")
            print(f"        obs={obs}")
            print(f"        det={det}")
    print(f"\n夹具 {len(rows)} 条,不符 {bad} 条")

    print("\n--- 数值反例 1:T33 短记录可解析性(Dowling) ---")
    for r in extreme_record_demo():
        print(f"  {r['years']:>2}年 n={r['n']:>6}  可解析下界={r['resolvable_p']:.3g}"
              f"  目标={r['p_target']:.3g}  {'可解析' if r['resolvable'] else '★无法解析'}")

    print("\n--- 数值反例 2:T34 不确定性信息量(Mannodi) ---")
    ci, cu = uncertainty_informativeness_demo()
    print(f"  信息性 corr={ci:.3f}(不确定性预测误差)")
    print(f"  无信息 corr={cu:.3f}(声称精确预测则不成立)")

    print("\n--- 数值反例 3:T33 Wilson CI(5/10000 Treg) ---")
    p, lo, hi = wilson_ci(5, 10000)
    print(f"  p={p:.6g}  CI=[{lo:.6g},{hi:.6g}]  相对宽度={(hi-lo)/p:.3f}"
          f"  上下界比={hi/lo:.2f}")
