#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""branch17 · 结论守卫 T26–T30 实跑分支。

★ 每条判据都配**双向夹具**:违规项应被拦(红),合规项应放行(绿)。
  只跑"合规"不叫验证 —— 那证明不了守卫抓得到东西(第 11 条陷阱形态①)。
"""
import numpy as np

import conclusion_guard as CG
import data_ethics as DE


def _sig_data(n=300, p=50, nclust=3, seed=0):
    """有真实**低维流形**结构的高维数据。

    ★ v2.18 修夹具 bug:初版写成 X = 簇心 + 各向同性噪声(50 维独立噪声)。
      这种数据**没有低维流形结构** —— 簇内 100 个点在高维的 k 近邻由 50 维
      噪声决定,PCA 投影到 2 维后由 2 维噪声决定,两者**互不相关**,
      实测邻居重叠度仅 0.144,与零数据的 0.136 无区别 → T26 判不出信号,
      真信号与噪声的 sig_frac 分别为 0.0% 与 1.3%,判据形同虚设。

      真实单细胞数据的结构是**低维流形 + 基因相关**:少数潜变量驱动,
      故 PCA 能恢复流形、邻居得以保住。夹具必须复现这一点,否则
      验证的是"夹具无结构",不是"判据无效"。
    """
    rng = np.random.default_rng(seed)
    lab = rng.integers(0, nclust, n)
    # 低维流形:2 维坐标,簇间分离远大于簇内
    c2 = rng.normal(0, 4.0, size=(nclust, 2))
    L2 = c2[lab] + rng.normal(0, 0.2, size=(n, 2))
    # 随机线性投影到高维(模拟基因相关结构)
    A = rng.normal(0, 1.0, size=(2, p))
    X = L2 @ A + rng.normal(0, 0.15, size=(n, p))
    return X, lab


def _weak_data(n=300, p=50, nclust=3, seed=0):
    """弱信噪比的流形数据 —— 用于验证 T26 的**梯度**(非二值)。

    ★ 实测:同一判据下 sig_frac 随信噪比单调变化
      簇内0.15/噪声0.10 → 76.0%   0.20/0.15 → 64.3%   0.30/0.30 → 32.7%
      0.40/0.50 → 29.7%           0.60/0.80 → 20.7%   纯噪声 → 0.3%~1.3%
    说明 T26 不是"通过/不通过"开关,而是**连续质量分**;50% 门槛的含义是
    "低于此则基于该嵌入的结论须降级为探索级"(EMBEDR 的设计意图)。
    """
    rng = np.random.default_rng(seed)
    lab = rng.integers(0, nclust, n)
    c2 = rng.normal(0, 4.0, size=(nclust, 2))
    L2 = c2[lab] + rng.normal(0, 0.6, size=(n, 2))
    A = rng.normal(0, 1.0, size=(2, p))
    return L2 @ A + rng.normal(0, 0.8, size=(n, p)), lab


def _noise_data(n=300, p=50, seed=1):
    """纯噪声(无任何联合结构)。"""
    rng = np.random.default_rng(seed)
    return rng.normal(0, 1.0, size=(n, p)), rng.integers(0, 3, n)


def branch17_conclusion(L):
    print("\n" + "-" * 74)
    print("  分支17 · 结论守卫 T26–T30(把框架从'流程守卫'升级为'结论守卫')")
    print("-" * 74)

    # ================================================ T26 信号 vs 噪声
    print("\n  【T26】嵌入信号-噪声定量零假设(EMBEDR)")
    X, lab = _sig_data()
    Ysig, _ = CG._pca(X, 2)
    st, obs, det = CG.check_T26(X, Ysig, n_embed=3, n_null=2, celltypes=lab,
                                 seed=0, embed_fn=CG._pca_bootstrap)
    L.add("17", "T26 真信号嵌入:应识别为信号", f"{st}|{obs}", "pass/warn",
          st in ("pass", "warn"), det[:88])

    Xw, labw = _weak_data()
    Yw, _ = CG._pca(Xw, 2)
    stw, obsw, detw = CG.check_T26(Xw, Yw, n_embed=3, n_null=2, seed=0,
                                   embed_fn=CG._pca_bootstrap)
    L.add("17", "T26 弱信噪比嵌入:应降级(探索级)", f"{stw}|{obsw}", "fail",
          stw == "fail", detw[:80])

    Xn, labn = _noise_data()
    Yn, _ = CG._pca(Xn, 2)
    # ★ 关键夹具:把随机噪声的嵌入当"真实嵌入"输入 → 应被拒
    st2, obs2, det2 = CG.check_T26(Xn, Yn, n_embed=3, n_null=2, celltypes=labn,
                                    seed=0, embed_fn=CG._pca_bootstrap)
    L.add("17", "T26 噪声冒充嵌入:应被拒(红)", f"{st2}|{obs2}", "fail",
          st2 == "fail", det2[:88])

    # 形状不匹配 → 应判 N/A 而非崩溃
    st3, obs3, det3 = CG.check_T26(X, np.zeros((5, 2)))
    L.add("17", "T26 形状不匹配:应判不适用", f"{st3}", "na", st3 == "na", det3[:60])

    # ================================================ T27 跨数据集条件匹配
    print("\n  【T27】跨数据集泛化条件匹配声明(DAISM-DNN / EpiTopics)")
    cases = [
        ("微调合规(n_calib=30)", dict(strategy="微调", n_calib=30, gt_source="FACS",
                                      batch_overlap=0.72, ever_tuned_on_target=None),
         ("pass",)),
        ("微调但 n_calib=8(<20)", dict(strategy="微调", n_calib=8, gt_source="FACS",
                                       batch_overlap=0.72), ("fail",)),
        ("零样本但调过参(泄漏)", dict(strategy="零样本迁移", ever_tuned_on_target=True,
                                      batch_overlap=0.6), ("fail",)),
        ("从头训练却声称'跨数据集复现'", dict(strategy="从头训练", batch_overlap=0.6,
                                             claim="本模型实现跨数据集复现"), ("fail",)),
        ("零样本合规", dict(strategy="零样本迁移", ever_tuned_on_target=False,
                            batch_overlap=0.65), ("pass",)),
        ("未提供批次诊断", dict(strategy="零样本迁移", ever_tuned_on_target=False),
         ("fail", "warn")),
    ]
    for name, kw, expect in cases:
        st, obs, det = CG.check_T27(**kw)
        L.add("17", f"T27 {name}", f"{st}|{obs}", "/".join(expect),
              st in expect, det[:80])

    # ================================================ T28 虚拟扰动流程
    print("\n  【T28】计算扰动可复现流程(scTenifoldKnk)")
    # 构造 3 个功能模块,每模块 8 个基因
    rng = np.random.default_rng(7)
    ncell, nmod, per = 120, 3, 8
    ngene = nmod * per
    module_of_gene = {i: f"M{i // per}" for i in range(ngene)}
    base = rng.normal(0, 1, size=(ncell, nmod))
    Xm = np.hstack([base[:, [m]] @ rng.normal(0, 1, size=(1, per)) +
                    rng.normal(0, 0.35, size=(ncell, per)) for m in range(nmod)])

    st, obs, det = CG.check_T28(Xm, module_of_gene, ko_gene_idx=5,
                                neg_ctrl_idx=20, seed=7, n_subsample=6)
    L.add("17", "T28 真实模块结构:扰动应可复现", f"{st}|{obs}", "pass/warn",
          st in ("pass", "warn"), det[:88])

    # ★ 阴性对照夹具:用一个"与目标基因同模块"的基因当对照 → 应高度相关 → fail
    st2, obs2, det2 = CG.check_T28(Xm, module_of_gene, ko_gene_idx=5,
                                   neg_ctrl_idx=6, seed=7, n_subsample=4)
    L.add("17", "T28 假阴性对照(同模块):应判特异性不成立", f"{st2}|{obs2}",
          "fail", st2 == "fail", det2[:88])

    # 措辞纪律
    st3, obs3, det3 = CG.check_T28(Xm, module_of_gene, ko_gene_idx=5,
                                   seed=7, n_subsample=3, claim="本结果完成功能验证")
    L.add("17", "T28 虚拟KO写'功能验证':应拦", f"{st3}", "fail", st3 == "fail", det3[:70])

    # ================================================ T29 数据正义
    print("\n  【T29】数据正义自查(Braun & Hummel)")
    st, obs, det = DE.check_T29(kind="人群数据", sensitive=True,
                                subgroup_n={"男": 120, "女": 96, "少数群体": 11},
                                risk_asymmetry=["老年组"], clinical_claim=True,
                                exit_option=True, privacy_absence_reported=True)
    L.add("17", "T29 完整举证:应通过", f"{st}|{obs}", "pass", st == "pass", det[:80])

    st2, obs2, det2 = DE.check_T29(kind="人群数据", sensitive=True,
                                   adequacy_claim=True, clinical_claim=True)
    L.add("17", "T29 声称充分却无子群样本量+未评风险却称可临床转化",
          f"{st2}|{obs2}", "fail", st2 == "fail", det2[:88])

    st3, obs3, det3 = DE.check_T29(kind="纯方法学", na_reason="无人群数据,纯算法研究")
    L.add("17", "T29 纯方法学:应判不适用", f"{st3}", "na", st3 == "na", det3[:60])

    # N/A 空理由必须报错(§10)
    try:
        DE.check_T29(kind="纯方法学")
        L.add("17", "T29 N/A 空理由应抛错", "未抛错", "raise", False)
    except ValueError:
        L.add("17", "T29 N/A 空理由应抛错", "ValueError", "raise", True)

    # ================================================ T30 数据治理
    print("\n  【T30】数据治理声明(PORT)")
    st, obs, det = DE.check_T30(data_source="本地采集",
                                data_flow="本地设备内", features_visible=True,
                                withdraw=True, secondary_use="仅限本研究,合同约束",
                                anon_claim=True, anon_method="差分隐私")
    L.add("17", "T30 完整声明:应通过", f"{st}|{obs}", "pass", st == "pass", det[:80])

    st2, obs2, det2 = DE.check_T30(data_source="本地采集",
                                   data_flow="本地", features_visible=True,
                                   withdraw=True, secondary_use="仅限本研究",
                                   anon_claim=True, anon_method=None,
                                   gdpr_scope=True, gdpr_article=None)
    L.add("17", "T30 称匿名无方法 + GDPR无法条:应拦", f"{st2}|{obs2}", "fail",
          st2 == "fail", det2[:88])

    st3, obs3, det3 = DE.check_T30(data_source="公开二次数据")
    L.add("17", "T30 公开二次数据:应判不适用", f"{st3}", "na", st3 == "na", det3[:60])

    return True
