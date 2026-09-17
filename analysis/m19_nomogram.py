# -*- coding: utf-8 -*-
"""M19 列线图与 5 年无复发生存换算（内化自参考文件 D 层 #14 ROC/列线图）。

做法：Cox PH（临床变量 + 可选上游风险评分）→ ① 系数表（HR/CI/P）；
② 简化列线图（各变量按"系数 × 取值范围"的效应量线性映射到 0–100 分）；
③ 总分 → 5 年无复发生存概率换算表（Breslow 基线累积风险）。

口径声明：本列线图为"基于 Cox 线性预测子的简化版"，适合论文展示与交互复核，
不作为独立验证证据；评分若来自上游模块，须注意其口径（见模块验证矩阵交叉核对表）。
"""
import os

import numpy as np
import pandas as pd


def _field(meta, sample, key):
    """取 GEO characteristics 键值（键前缀匹配，值取第一个冒号之后）。

    与执行器 gf() 同版实现（插件不 import 执行器以避免循环依赖）；键常带限定词，
    如 "age (years): 55"、"gender: female"，必须按冒号切分而非按下标切割。
    """
    k = str(key).strip().lower().rstrip(":")
    for v in meta.get(sample, []):
        if ":" not in v:
            continue
        name, val = v.split(":", 1)
        if name.strip().lower().startswith(k):
            val = val.strip()
            if val:
                return val
    return None


def points_per_unit(coefs, ranges, span=100.0):
    """列线图分值映射（纯函数）。

    Args:
      coefs: {变量: Cox 系数}
      ranges: {变量: (min, max)} 该变量取值范围
      span: 效应量最大的变量其全范围对应的分值（默认 100）

    Returns:
      {变量: {"per_unit": 每单位取值分值, "range_points": 全范围分值}}
      使 max(|coef|*range) 的变量 range_points = span，其余按比例。
    """
    effects = {k: abs(coefs[k]) * abs(ranges[k][1] - ranges[k][0]) for k in coefs}
    mx = max(effects.values()) if effects else 0.0
    if mx == 0:
        return {k: {"per_unit": 0.0, "range_points": 0.0} for k in coefs}
    return {k: {"per_unit": span * abs(coefs[k]) / mx,
                "range_points": span * effects[k] / mx} for k in coefs}


def surv_prob(baseline_cumhaz_at_t, linear_predictor):
    """Cox 基线生存 → 个体 t 时点生存概率 S(t) = exp(-H0(t)·exp(lp))（纯函数）。"""
    return float(np.exp(-float(baseline_cumhaz_at_t) * np.exp(float(linear_predictor))))


def baseline_at(event_times, cumhaz, t0):
    """取 t0 处的基线累积风险（阶跃函数，右连续；纯函数，便于单测）。"""
    et = np.asarray(event_times, dtype=float)
    ch = np.asarray(cumhaz, dtype=float).ravel()
    if et.size == 0 or ch.size == 0:
        return 0.0
    n = min(et.size, ch.size)
    et, ch = et[:n], ch[:n]
    idx = np.searchsorted(et, float(t0), side="right") - 1
    return float(ch[idx]) if idx >= 0 else 0.0


def extract_baseline(cox):
    """取 Cox 基线累积风险曲线（兼容 statsmodels 版本差异，纯函数可测）。

    实践证据：本环境 `baseline_cumulative_hazard` 是**非可调用属性** =
    [H0, times, S0] 三个数组的列表（直接调用会抛 'list' object is not callable，
    见 run 34766532160）。部分版本为方法。统一返回 (times, cumhaz)。
    """
    bc = cox.baseline_cumulative_hazard
    res = bc() if callable(bc) else bc
    if isinstance(res, list):
        # statsmodels 源码 docstring：triples (time, hazard, survival)
        # 即 inner = [时间数组, 累积风险 H0, 生存 S0]。曾误取 inner[0] 当 H0
        # （实为时间数组），致 H0(1825d)=2282（run 34768479253 实证），已改正。
        inner = res[0]
        if isinstance(inner, list) and len(inner) >= 2:
            return np.asarray(inner[0]).ravel(), np.asarray(inner[1]).ravel()
        inner = np.asarray(inner)
        return np.arange(inner.size, dtype=float), inner.ravel()
    arr = np.asarray(res)
    if arr.ndim == 2 and arr.shape[1] >= 2:
        return arr[:, 0].ravel(), arr[:, 1].ravel()
    return np.arange(arr.size, dtype=float), arr.ravel()


def _covariates(ctx, samples):
    """组装协变量表：年龄 / 男性 / 分期序数 / 可选上游评分。

    字段名因数据集而异 → 可由 config 覆盖（age_key / gender_key / stage_key），
    默认适配 GSE31210：'age (years)'、'gender'、'pathological stage'。
    """
    meta, cfg = ctx["meta"], ctx["config"]
    stage_map = {"IA": 1.0, "IB": 2.0, "I": 1.0, "II": 3.0,
                 "IIIA": 4.0, "IIIB": 4.0, "III": 4.0, "IV": 6.0}
    age_key = cfg.get("age_key", "age")
    gender_key = cfg.get("gender_key", "gender")
    stage_key = cfg.get("stage_key", "pathological stage")
    df = pd.DataFrame({
        "age": [pd.to_numeric(_field(meta, s, age_key), errors="coerce") for s in samples],
        "male": [1.0 if ((_field(meta, s, gender_key) or _field(meta, s, "sex") or "")
                         .lower().startswith("m")) else 0.0 for s in samples],
        "stage_ord": [stage_map.get((_field(meta, s, stage_key) or "").strip().upper(), np.nan)
                      for s in samples],
    }, index=samples)
    score = ctx.get("oof_score")
    if score is not None:
        df["risk_score"] = pd.to_numeric(score.reindex(samples), errors="coerce")
    return df


def run(ctx, out):
    """模块入口：Cox 系数表 + 简化列线图 + 总分-5年无复发生存表。"""
    from statsmodels.duration.hazard_regression import PHReg
    cfg = ctx["config"]
    horizon_days = float(cfg.get("horizon_days", 1825))
    samples, tt, ev = ctx["keep"], ctx["tt"], ctx["ev"]
    X = _covariates(ctx, samples)
    mask = np.isfinite(X.to_numpy(dtype=float)).all(axis=1) & np.isfinite(tt)
    if mask.sum() < 30:
        return (f"协变量完整样本仅 {int(mask.sum())}（<30），不足以拟合 Cox，"
                f"不产出列线图（不假装成功）")
    Xm, ttm, evm, idx = X[mask], tt[mask], ev[mask], np.where(mask)[0]
    cox = PHReg(ttm, Xm.to_numpy(dtype=float), status=evm).fit()
    coefs = {c: float(cox.params[i]) for i, c in enumerate(Xm.columns)}
    ci = cox.conf_int()
    coef_tab = pd.DataFrame({
        "variable": list(coefs),
        "coef": [coefs[c] for c in coefs],
        "HR": [float(np.exp(coefs[c])) for c in coefs],
        "CI_low": [float(np.exp(ci[i][0])) for i in range(len(coefs))],
        "CI_high": [float(np.exp(ci[i][1])) for i in range(len(coefs))],
        "P": [float(cox.pvalues[i]) for i in range(len(coefs))],
    })
    coef_tab.to_csv(os.path.join(out, "M19_Cox系数表.csv"), index=False, encoding="utf-8-sig")

    ranges = {c: (float(Xm[c].min()), float(Xm[c].max())) for c in Xm.columns}
    pts = points_per_unit(coefs, ranges)

    # 基线累积风险：statsmodels 的 baseline_cumulative_hazard 是 [H0,times,S0] 列表属性
    # （非方法，曾致 'list' not callable，run 34766532160 实证），统一由 extract_baseline 抽取
    et, bh = extract_baseline(cox)
    h0 = baseline_at(et, bh, horizon_days)

    lp = Xm.to_numpy(dtype=float) @ np.asarray(list(coefs.values()))
    total_points = np.zeros(len(Xm))
    for c in Xm.columns:
        total_points += pts[c]["per_unit"] * (Xm[c].to_numpy() - ranges[c][0])
    conv = pd.DataFrame({
        "total_points": np.round(total_points, 1),
        "linear_predictor": lp,
        f"RFS_prob_{int(horizon_days)}d": [surv_prob(h0, v) for v in lp],
    }).sort_values("total_points")
    conv.to_csv(os.path.join(out, f"M19_总分_{int(horizon_days)}天无复发生存.csv"),
                index=False, encoding="utf-8-sig")

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    n = len(pts)
    fig, ax = plt.subplots(figsize=(7.2, 0.9 + 0.55 * n), dpi=300)
    for i, (c, v) in enumerate(pts.items()):
        y = n - i
        ax.hlines(y, 0, 100, color="#334155", lw=1.0)
        for tick in range(0, 101, 10):
            ax.vlines(tick, y - 0.08, y + 0.08, color="#334155", lw=0.7)
        ax.text(-2, y, f"{c}\n[HR {np.exp(coefs[c]):.2f}]", ha="right", va="center", fontsize=7)
        lo, hi = ranges[c]
        ax.text(0, y + 0.22, f"{lo:.3g}", fontsize=6, ha="center")
        ax.text(100, y + 0.22, f"{hi:.3g}", fontsize=6, ha="center")
        ax.text(50, y - 0.3, f"全范围={v['range_points']:.0f} 分", fontsize=6,
                ha="center", color="#0072B2")
    ax.set_xlim(-30, 110); ax.set_ylim(0.3, n + 0.8)
    ax.set_yticks([]); ax.set_xlabel("Points", fontsize=8)
    ax.set_title(f"Simplified nomogram (Cox; n={int(mask.sum())})", fontsize=9)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    fig.tight_layout()
    fig.savefig(os.path.join(out, "M19_列线图.png"), dpi=300)
    plt.close(fig)

    sig = [c for c in coefs if float(cox.pvalues[list(coefs).index(c)]) < 0.05]
    return (f"n={int(mask.sum())}；H0({int(horizon_days)}d)={h0:.3f}；"
            f"显著变量 {sig if sig else '无'}（P<0.05）")


MODULES = [
    {"id": "M19", "name": "列线图与5年无复发生存", "folder": "列线图",
     "deps": ["M07"], "fn": run},
]
