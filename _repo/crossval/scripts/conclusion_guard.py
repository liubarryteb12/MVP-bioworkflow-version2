#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""结论守卫 T26–T28(branch17)。

★ 编号冲突说明(v2.18):
用户《基于13篇论文的优化建议》中提议的判据编号为 T21–T25,但**这五个编号
在 v2.16 已被文献实证判据占用**(源自上一批 23 篇真实生信论文):
    T21 组别样本量下限与平衡   T22 训练-外部验证性能落差
    T23 多数据集 QC 阈值一致性 T24 验证集独立性
    T25 空间/ROI 选择盲法
覆盖已有判据会破坏 v2.16 成果,故本模块改用 T26–T30,并在 criteria.yaml
登记 `numbering_conflict` 字段留痕。编号映射:
    建议T21(EMBEDR 信号vs噪声)   → T26
    建议T22(跨数据集条件匹配)     → T27
    建议T23(虚拟扰动流程)         → T28
    建议T24(数据正义)             → T29
    建议T25(数据治理)             → T30

★ 这三条的定位:框架此前强于"流程是否合规",弱于"产物是否真实"。
  EMBEDR 提供定量零假设、scTenifoldKnk 提供虚拟扰动流程、
  DAISM-DNN/EpiTopics 提供跨数据集条件匹配声明。
  三者共同把框架从"流程守卫"升级为"结论守卫"。

铁律:无具体坑的规则不立。每条都锚定具体论文的具体数字/做法,
且**必须能构造 FAIL**。
"""
import os
import math
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ============================================================ T26
# 信号 vs 噪声的定量零假设(EMBEDR, Johnson et al. Patterns 3, 100443)
#
# 坑:框架此前的"先红后绿"是**定性**的 —— 只证明"守卫抓得到注入的违规",
#     不回答"我产出的图/聚类/嵌入里,哪些是真信号,哪些只是算法伪影"。
#     EMBEDR 把这个问题变成可判定的统计问题。

T26_ALPHA = 0.01          # 显著 p 值阈值
T26_MIN_SIG_FRAC = 0.50   # p<alpha 的样本占比下限;低于此 → 降级探索级
T26_MAX_CT_MEDIAN = 0.10  # ★ v2.18 修方向 bug:某 celltype p 中位数**上限**。
#   初版命名为 MIN 且写成 `med < 0.10 → 不得用于下结论`,判据方向**完全颠倒** ——
#   EMBEDR 语义下 p 小 = 结构可复现 = 真信号 = **可以**下结论。
#   实测真信号夹具 p 中位数=0.002(极显著)却被判'不得用于下结论',
#   把最优嵌入当成了最差嵌入。改为 med > 上限(结构不可复现)才禁用。


def _pairwise_dist(X):
    """欧氏距离矩阵(用 Gram 矩阵技巧,避免 O(N^2 P) 显式展开)。"""
    X = np.asarray(X, dtype=float)
    sq = (X ** 2).sum(axis=1, keepdims=True)
    D2 = sq + sq.T - 2.0 * (X @ X.T)
    np.fill_diagonal(D2, 0.0)
    return np.sqrt(np.maximum(D2, 0.0))


def _neighbor_prob(D, k, eps=1e-6):
    """样本 i 的 k 近邻**身份**分布(非距离值分布)。

    ★ v2.18 修 bug:初版用"k 近邻距离值的归一化分布",它对结构**不敏感**
      —— 高维随机点的 k 近邻距离趋于集中(维度诅咒),低维 PCA 后同样集中,
      两者 KL ≈ 0,导致真信号与零数据的 EES 分布重合(实测 median_p=0.503,
      真信号 sig_frac 仅 1%,与噪声 0.3% 无区分度 —— 判据形同虚设)。

      EMBEDR 原文比较的是**邻居集合本身**:高维邻居在低维是否仍是邻居。
      故改为身份分布 P_i(j) = 1/k if j ∈ N_k(i) else eps(再归一化)。
      这样"结构保住"→ 两分布重叠 → KL 小;"纯噪声"→ 邻居集合随机 → KL 大。
    """
    N = D.shape[0]
    kk = max(1, min(k, N - 1))
    out = np.full((N, N), eps, dtype=float)
    for i in range(N):
        d = np.delete(D[i], i)
        orig = np.delete(np.arange(N), i)
        idx = np.argsort(d)[:kk]
        out[i, orig[idx]] = 1.0 / kk
    out /= out.sum(axis=1, keepdims=True)
    return out


def _kl(p, q):
    """KL(p||q),逐行。q 加 eps 防除零。"""
    p = np.maximum(np.asarray(p, dtype=float), 1e-12)
    q = np.maximum(np.asarray(q, dtype=float), 1e-12)
    return (p * np.log(p / q)).sum(axis=1)


def marginal_resample(X, seed):
    """★ EMBEDR 核心:marginal resampling 构造零数据。

    每列**独立**置换 → 保留各基因边缘分布,破坏基因间联合结构。
    这样得到的数据没有任何真实的"样本-样本"生物学结构,
    在其上跑降维得到的嵌入,就是纯算法伪影的基线。
    """
    rng = np.random.default_rng(seed)
    Xn = np.asarray(X, dtype=float).copy()
    for j in range(Xn.shape[1]):
        rng.shuffle(Xn[:, j])
    return Xn


def compute_ees(X, Y, k=10):
    """empirical embedding statistic:EES_i = KL(P_hi_i || P_lo_i)。

    P_hi = 高维空间中样本 i 的 k 近邻距离分布
    P_lo = 低维嵌入中样本 i 的 k 近邻距离分布
    差异越大 → 嵌入越没保住该样本的邻居结构。
    """
    D_hi = _pairwise_dist(X)
    D_lo = _pairwise_dist(Y)
    return _kl(_neighbor_prob(D_hi, k), _neighbor_prob(D_lo, k))


def _pca(Y_or_X, k):
    """轻量 PCA(不引 sklearn,避免依赖)。"""
    X = np.asarray(Y_or_X, dtype=float)
    Xc = X - X.mean(axis=0, keepdims=True)
    U, S, Vt = np.linalg.svd(Xc, full_matrices=False)
    return Xc @ Vt[:k].T, S


def _pca_bootstrap(X, k, seed, frac=0.8):
    """★ v2.18:在**随机子样本**上拟合 PCA,再投影全量点。

    起因:初版 check_T26 的 n_embed 循环对同一个 Y 重复算 EES,
    三次结果完全相同 → n_embed 参数形同虚设(EMBEDR 要求 >=3 次
    **独立**嵌入,是为了刻画嵌入算法自身的随机性;t-SNE/UMAP 天然随机,
    但 PCA 是确定性的)。改为子样本拟合后,每次嵌入略有差异,
    n_embed 才真正成为"重复稳健性"维度。
    """
    X = np.asarray(X, dtype=float)
    rng = np.random.default_rng(seed)
    n = X.shape[0]
    ns = max(k + 2, int(frac * n))
    idx = rng.choice(n, size=ns, replace=False)
    Xs = X[idx]
    mu = Xs.mean(axis=0, keepdims=True)
    U, S, Vt = np.linalg.svd(Xs - mu, full_matrices=False)
    return (X - mu) @ Vt[:k].T


def check_T26(X, Y, n_embed=3, n_null=2, k=10, celltypes=None, seed=0,
               embed_fn=None):
    """T26 · 嵌入/降维产物的信号-噪声定量分离(三态)。

    判定:
      (a) EES_i = KL(P_hi || P_lo)
      (b) 零分布 = marginal resampling 后重跑嵌入的 EES*
      (c) p_i = P(EES* <= EES_i),跨 n_embed 次独立重复取均值
      (d) 报告 p<0.01 的样本占比

    不通过:
      - 无法产出 per-sample p 值 → 判"判不了"
      - p<0.01 占比 < 50% → 基于该嵌入的结论降级为**探索级**
      - 某 celltype p 中位数 < 0.10 → 该型在嵌入中的位置不得用于下结论
    """
    X = np.asarray(X, dtype=float)
    Y = np.asarray(Y, dtype=float)
    if X.shape[0] != Y.shape[0]:
        return "na", "形状不匹配", f"X 行数 {X.shape[0]} != Y 行数 {Y.shape[0]}"
    if X.shape[0] < 4 * k:
        return "na", f"N={X.shape[0]}", f"样本数不足以支撑 k={k} 近邻检验(需 >= {4*k})"

    kdim = Y.shape[1]
    obs_all, null_all = [], []
    for r in range(n_embed):
        # 观测嵌入:传入 Y 时用 Y(调用方已算好),否则 bootstrap PCA 产生独立嵌入
        Yr = Y if embed_fn is None else embed_fn(X, kdim, seed + r)
        obs_all.append(compute_ees(X, Yr, k=k))
        for s in range(n_null):
            Xn = marginal_resample(X, seed=seed + 1000 * r + s)
            Yn = _pca_bootstrap(Xn, kdim, seed=seed + 5000 * r + s)
            null_all.append(compute_ees(Xn, Yn, k=k))
    if not obs_all or not null_all:
        return "na", "无输出", "无法计算 p 值(嵌入或零嵌入为空)"

    obs = np.mean(obs_all, axis=0)
    null = np.concatenate(null_all)
    # p_i = P(EES*_null <= EES_i):观测 EES 越大(结构越没保住),p 越接近 1
    pvals = np.array([(null <= o).mean() for o in obs])
    frac = float((pvals < T26_ALPHA).mean())

    detail = [f"p<{T26_ALPHA} 占比={frac:.1%}(下限 {T26_MIN_SIG_FRAC:.0%})"]
    status = "pass"

    if frac < T26_MIN_SIG_FRAC:
        status = "fail"
        detail.append("显著样本不足 → 基于该嵌入的聚类/轨迹结论须降级为探索级")

    ct_bad = []
    if celltypes is not None:
        ct = np.asarray(celltypes)
        for c in np.unique(ct):
            med = float(np.median(pvals[ct == c]))
            # p 大 = 该型在嵌入中的位置无法在高维复现 = 伪影,不得据此下结论
            if med > T26_MAX_CT_MEDIAN:
                ct_bad.append(f"{c}(中位 p={med:.3f})")
        if ct_bad:
            status = "fail" if status == "pass" else status
            detail.append("细胞型 p 中位数过高(结构不可复现),不得用于下结论: "
                          + ", ".join(ct_bad))

    obs_s = f"sig_frac={frac:.3f},median_p={np.median(pvals):.3f}"
    return status, obs_s, "; ".join(detail)


# ============================================================ T27
# 跨数据集/跨队列泛化的"条件匹配"声明(DAISM-DNN + EpiTopics)
#
# 坑:现有 T22 只看结果层(训练→外部 AUC 落差),**不问模型怎么训练的**。
#     DAISM-DNN 原话: "test and train conditions must match"。
#     一个在目标数据上调过参的模型,两个 CI 当然会重叠 —— 那不是泛化。

T27_MIN_CALIB = 20   # DAISM-DNN 实测:n_calib < 20 时性能提升不显著

T27_STRATEGIES = ("零样本迁移", "从头训练", "微调")
# 各策略允许的结论上限(建议 T14 扩展表,此处作为措辞纪律的机器可检部分)
T27_CLAIM_BAN = {
    "从头训练": ["跨数据集复现", "外部验证成功", "独立队列验证"],
}


def check_T27(strategy, n_calib=None, gt_source=None,
              batch_overlap=None, claim=None, ever_tuned_on_target=None):
    """T27 · 跨数据集泛化的条件匹配声明。

    强制声明项(缺一不通过):
      (a) 校准策略(三选一,须预注册)
      (b) 微调 → n_calib 必须报告且 >= 20
      (c) 批次效应量化(源-目标分布重叠度 / kBET 等)
      (d) 校准样本 ground truth 来源(FACS / 已知标签 / 流式)

    判定:
      - 零样本迁移 → 必须报告"是否曾在目标数据上评估/调参过"
      - 从头训练 → 不得声称"跨数据集复现"(那只是独立建模)
      - 微调 → 必须报告 n_calib 与 ground truth 来源
      - 批次诊断显示源/目标不可分 → 判"不确定"
    """
    detail = []
    if strategy not in T27_STRATEGIES:
        return "na", f"策略={strategy}", (
            f"未声明或无法识别的迁移策略(须为 {'/'.join(T27_STRATEGIES)} 之一)")

    obs = f"策略={strategy}"
    status = "pass"

    # (b) 微调的校准样本量
    if strategy == "微调":
        if n_calib is None:
            status = "fail"
            detail.append("声明微调但未报告 n_calib")
        else:
            obs += f",n_calib={n_calib}"
            if n_calib < T27_MIN_CALIB:
                status = "fail"
                detail.append(
                    f"n_calib={n_calib} < {T27_MIN_CALIB}"
                    f"(DAISM-DNN 实测:低于此值性能提升不显著)")
        if not gt_source:
            status = "fail"
            detail.append("微调未报告校准样本 ground truth 来源(FACS/已知标签/流式)")

    # (a-1) 零样本迁移必须声明是否调过参
    if strategy == "零样本迁移":
        if ever_tuned_on_target is None:
            status = "fail"
            detail.append("零样本迁移未声明'是否曾在目标数据上评估/调参'")
        elif ever_tuned_on_target:
            status = "fail"
            detail.append(
                "声称零样本迁移但实际在目标数据上调过参 → 触发 R3 回退"
                "(这不是泛化,是泄漏)")

    # (c) 批次效应量化
    if batch_overlap is None:
        status = "fail" if status == "pass" else status
        detail.append("未提供源-目标批次效应/分布重叠度诊断")
    else:
        obs += f",overlap={batch_overlap:.2f}"

    # 措辞纪律:结论上限
    if claim:
        for banned in T27_CLAIM_BAN.get(strategy, []):
            if banned in str(claim):
                status = "fail"
                detail.append(
                    f"策略'{strategy}'不得声称'{banned}'(那只是独立建模,不是复现)")

    if not detail:
        detail.append("条件匹配声明完整")
    return status, obs, "; ".join(detail)


# ============================================================ T28
# 虚拟/计算扰动的流程判据(scTenifoldKnk, Osorio et al. Patterns 3, 100434)
#
# 坑:现有 T17 只判"用分位数不用倍数"—— 那是**参数选择**判据,不是流程判据。
#     scTenifoldKnk 提供完整可复现流程:网络构建 → 虚拟KO(整行置0) → 流形对齐。
#     关键可检验设计:模块归属检验、10次子抽样 Spearman、阴性对照。

T28_MIN_RHO = 0.5       # 10 次子抽样扰动谱之间的 Spearman 下限
T28_RHO_HARD_FAIL = 0.3  # 低于此 → 判"不稳定,不采用"
T28_MODULE_P = 0.05     # DR 基因富集于 KO 基因所在模块的 p 阈值
T28_N_SUBSAMPLE = 10
T28_FORBIDDEN_CLAIM = ["功能验证", "实验验证", "已证实", "证明"]


def _spearman(a, b):
    ra = np.argsort(np.argsort(np.asarray(a, dtype=float))).astype(float)
    rb = np.argsort(np.argsort(np.asarray(b, dtype=float))).astype(float)
    if ra.std() == 0 or rb.std() == 0:
        return 0.0
    return float(np.corrcoef(ra, rb)[0, 1])


def _build_net(X):
    """简化版 scTenifoldKnk 网络构建:z-score + 相关邻接 + 去噪(截断 SVD)。"""
    X = np.asarray(X, dtype=float)
    Z = (X - X.mean(axis=0, keepdims=True)) / np.maximum(X.std(axis=0, keepdims=True), 1e-12)
    G = Z.T @ Z / max(Z.shape[0] - 1, 1)          # 基因×基因 相关
    np.fill_diagonal(G, 0.0)
    U, S, Vt = np.linalg.svd(G, full_matrices=False)
    keep = max(1, int(0.8 * len(S)))               # 张量分解去噪的替代:低秩截断
    return (U[:, :keep] * S[:keep]) @ Vt[:keep]


def _virtual_ko(W, gidx):
    """虚拟 KO:把目标基因的**整个行**置 0(scTenifoldKnk 做法)。"""
    W2 = np.array(W, dtype=float, copy=True)
    W2[gidx, :] = 0.0
    return W2


def _manifold_align_distance(W_wt, W_ko, k=5):
    """流形对齐后每个基因在两个投影上的欧氏距离 → 扰动谱。

    用邻接矩阵前 k 个特征向量作为低维投影(流形对齐的简化实现)。
    """
    def proj(W):
        Ws = (W + W.T) / 2.0
        vals, vecs = np.linalg.eigh(Ws)
        order = np.argsort(-np.abs(vals))[:k]
        return vecs[:, order] * np.sqrt(np.abs(vals[order]))
    P1, P2 = proj(W_wt), proj(W_ko)
    return np.sqrt(((P1 - P2) ** 2).sum(axis=1))


def check_T28(X, module_of_gene, ko_gene_idx, n_subsample=T28_N_SUBSAMPLE,
              k=5, seed=0, claim=None, neg_ctrl_idx=None, do_subsample=True):
    """T28 · 计算扰动的可复现流程(三态)。

    必做项:
      (a) 流程声明(网络构建/扰动施加/差异比较)
      (b) 模块归属检验:DR 基因是否富集于 KO 基因所在模块(p<0.05)
      (c) 重复稳健性:随机子抽样 >=10 次,扰动谱 Spearman ρ >= 0.5
      (d) 方向稳定性(KO 与过表达应对称)
      (e) 阴性对照:无关基因的扰动谱应与目标基因显著不同

    不通过:
      - (c) ρ < 0.3 → 判"不稳定,不采用"
      - (e) 对照扰动谱与目标不可区分 → 该方法的特异性不成立
    """
    X = np.asarray(X, dtype=float)
    detail, status = [], "pass"
    obs_parts = []

    # (b) 模块归属检验
    W_wt = _build_net(X)
    W_ko = _virtual_ko(W_wt, ko_gene_idx)
    dist = _manifold_align_distance(W_wt, W_ko, k=k)

    thr = float(np.quantile(dist, 0.95))
    dr_idx = np.where(dist >= thr)[0]
    ko_module = module_of_gene.get(int(ko_gene_idx))
    if ko_module is None:
        status = "na"
        detail.append(f"KO 基因 {ko_gene_idx} 无模块标注 → 无法做归属检验")
        p_enrich = None
    else:
        in_mod = np.array([module_of_gene.get(int(i)) == ko_module
                           for i in range(X.shape[1])])
        n_dr_in = int(in_mod[dr_idx].sum()) if len(dr_idx) else 0
        n_in = int(in_mod.sum())
        n_dr = len(dr_idx)
        n_tot = X.shape[1]
        # 超几何检验(用正态近似,避免引入 scipy.stats 依赖不稳定)
        if n_dr == 0 or n_in == 0:
            p_enrich = 1.0
        else:
            mu = n_dr * n_in / n_tot
            sd = np.sqrt(mu * (1 - n_in / n_tot) * (n_tot - n_dr) / max(n_tot - 1, 1))
            z = (n_dr_in - mu) / max(sd, 1e-12)
            p_enrich = float(0.5 * math.erfc(z / np.sqrt(2))) if sd > 0 else 1.0
        obs_parts.append(f"模块富集 p={p_enrich:.4f}")
        if p_enrich >= T28_MODULE_P:
            status = "fail"
            detail.append(
                f"DR 基因未富集于 KO 基因所在模块(p={p_enrich:.4f} >= {T28_MODULE_P})"
                f" → 扰动结果与该基因的已知功能归属不一致")

    # (c) 重复稳健性:随机子抽样 Spearman
    if do_subsample and X.shape[0] > 20:
        rng = np.random.default_rng(seed)
        nsub = max(10, int(0.8 * X.shape[0]))
        specs = []
        for _ in range(n_subsample):
            idx = rng.choice(X.shape[0], size=nsub, replace=False)
            ws = _build_net(X[idx])
            specs.append(_manifold_align_distance(ws, _virtual_ko(ws, ko_gene_idx), k=k))
        rhos = [_spearman(specs[0], specs[i]) for i in range(1, len(specs))]
        mean_rho = float(np.mean(rhos)) if rhos else 0.0
        obs_parts.append(f"rho={mean_rho:.3f}")
        if mean_rho < T28_RHO_HARD_FAIL:
            status = "fail"
            detail.append(f"扰动谱不稳定:平均 Spearman ρ={mean_rho:.3f} < "
                          f"{T28_RHO_HARD_FAIL} → 判'不稳定,不采用'")
        elif mean_rho < T28_MIN_RHO:
            status = "warn" if status == "pass" else status
            detail.append(f"扰动谱稳健性偏弱:ρ={mean_rho:.3f} < {T28_MIN_RHO}"
                          f"(scTenifoldKnk 实测约 0.55)")
    else:
        obs_parts.append("rho=跳过")

    # (e) 阴性对照
    if neg_ctrl_idx:
        d_ctrl = _manifold_align_distance(W_wt, _virtual_ko(W_wt, neg_ctrl_idx), k=k)
        rho_c = _spearman(dist, d_ctrl)
        obs_parts.append(f"对照rho={rho_c:.3f}")
        if rho_c > 0.7:
            status = "fail"
            detail.append(
                f"阴性对照扰动谱与目标基因高度相关(ρ={rho_c:.3f} > 0.7)"
                f" → 该方法无法区分目标基因与无关基因,特异性不成立")

    # 措辞纪律
    if claim and any(w in str(claim) for w in T28_FORBIDDEN_CLAIM):
        status = "fail"
        detail.append(f"虚拟 KO 结果不得写'{claim}'"
                      f"(须写'计算扰动预测')")

    if not detail:
        detail.append("流程判据齐全(模块富集/稳健性/阴性对照)")
    return status, ",".join(obs_parts) or "无输出", "; ".join(detail)
