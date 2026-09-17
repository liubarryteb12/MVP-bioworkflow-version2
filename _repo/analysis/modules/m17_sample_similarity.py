# -*- coding: utf-8 -*-
"""M17 样本相似性与离群检测（插件示例，纯 numpy，确定性，无外源知识依赖）。

方法：样本间 Pearson 相关矩阵 → 每个样本的"对其他样本中位相关系数" →
低于阈值者列为离群候选。文献里常用于 QC/批次排查（Wen 2022 等 GEO 肺癌预后
研究的预处理环节），本模块把它固化为可调用单元。

依赖：仅 numpy/pandas（已在 requirements.txt）。
"""
import os

import numpy as np
import pandas as pd


def sample_similarity(expr, outlier_median_r):
    """纯函数：样本相关矩阵 + 离群候选（可单测，无副作用）。

    Args:
      expr: 基因 × 样本 表达矩阵（log2 尺度，建议已过滤低表达）。
      outlier_median_r: 判为离群候选的中位相关系数下限（须由 config 传入）。

    Returns:
      (相关矩阵 DataFrame, 离群候选 DataFrame)；
      样本数 < 3 时返回 (None, None) —— 无法定义"离群"，如实不产出结论。
    """
    if expr.shape[1] < 3:
        return None, None
    x = expr.to_numpy(dtype=float)
    x = x - x.mean(axis=0, keepdims=True)
    sd = x.std(axis=0, keepdims=True)
    sd[sd == 0] = np.nan                      # 常数列：相关无定义，置 NaN 后归零
    z = np.nan_to_num(x / sd, nan=0.0)
    corr = (z.T @ z) / z.shape[0]
    np.fill_diagonal(corr, 1.0)
    cm = pd.DataFrame(corr, index=expr.columns, columns=expr.columns)
    mask = np.eye(len(cm), dtype=bool)
    med = cm.where(~mask).median(axis=1)
    cand = pd.DataFrame({"sample": list(med.index), "median_r": med.to_numpy()})
    cand["outlier"] = cand["median_r"] < float(outlier_median_r)
    return cm, cand.sort_values("median_r")


def run(ctx, out):
    """模块入口：写相关矩阵、离群候选表与热图。"""
    cfg = ctx["config"]
    if "outlier_median_r" not in cfg:
        raise ValueError("M17 需在 config.params.M17 指定 outlier_median_r（例如 0.8）")
    expr, samples = ctx["expr"], ctx["samples"]
    sub = expr.loc[:, samples]
    cm, cand = sample_similarity(sub, cfg["outlier_median_r"])
    if cm is None:
        return f"样本数 {len(samples)} < 3，无法评估离群（不产出结论）"
    cm.to_csv(os.path.join(out, "M17_样本相关矩阵.csv"), encoding="utf-8-sig")
    cand.to_csv(os.path.join(out, "M17_离群候选.csv"), index=False, encoding="utf-8-sig")

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(6.2, 5.4), dpi=300)
    im = ax.imshow(cm.to_numpy(), cmap="viridis", vmin=float(np.nanmin(cm.to_numpy())), vmax=1.0)
    ax.set_title("Sample-sample correlation (log2)", fontsize=9)
    ax.set_xticks([]); ax.set_yticks([])
    fig.colorbar(im, ax=ax, shrink=0.8, label="Pearson r")
    fig.tight_layout()
    fig.savefig(os.path.join(out, "M17_相关热图.png"), dpi=300)
    plt.close(fig)

    n_out = int(cand["outlier"].sum())
    return (f"相关矩阵 {cm.shape}；离群候选 {n_out}（阈值中位 r < {cfg['outlier_median_r']}）；"
            f"最低中位 r = {cand['median_r'].min():.3f}（{cand['sample'].iloc[0]}）")


MODULES = [
    {"id": "M17", "name": "样本相似性与离群检测", "folder": "样本相似性与离群检测",
     "deps": ["M03"], "fn": run},
]
