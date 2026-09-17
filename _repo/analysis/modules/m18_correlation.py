# -*- coding: utf-8 -*-
"""M18 相关性分析（内化自参考文件《生信分析方法体系 v2》§〇 v2.1 常规操作）。

两类相关：① 基因-基因（表达相关矩阵 → 共表达簇证据）；
② 基因-临床性状（与年龄 / 复发事件 / 随访天数的相关）。
本模块自包含：不 import 执行器（避免循环依赖），所需的 GEO 字段小助手在此重复实现。
"""
import os

import numpy as np
import pandas as pd
from scipy import stats


def _field(meta, sample, key):
    """取 GEO characteristics 键值（键前缀匹配，值取第一个冒号之后）。

    与执行器 gf() 同版实现（插件不 import 执行器以避免循环依赖）；键常带限定词，
    如 "age (years): 55"，必须按冒号切分，否则解析出 "(years): 55"。
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


def collapse_by_symbol(mat, sym):
    """按基因符号聚合探针（同符号取最大值），返回 (聚合后矩阵, 合并掉的探针数)。

    为什么必须做：GPL570 上多个探针常映射到同一 Symbol，直接 rename 会让相关矩阵
    索引重复，`stack()` 抛 "Columns with duplicate values are not supported"
    （本轮 run 34762853449 实证；契约测试 test_m18_collapses_duplicate_gene_symbols 锁死）。
    """
    if not sym:
        return mat, 0
    names = [sym.get(i, i) for i in mat.index]
    n_dup = len(names) - len(set(names))
    return (mat.groupby(names).max() if n_dup else mat), n_dup


def corr_matrix(mat):
    """基因 × 基因 Pearson 相关矩阵（纯函数）。mat: 基因 × 样本。"""
    r = np.corrcoef(mat.to_numpy(dtype=float))
    return pd.DataFrame(r, index=mat.index, columns=mat.index)


def corr_with_traits(mat, traits, min_n=10):
    """基因表达 vs 样本性状的 Pearson r / P（纯函数）。

    Args:
      mat: 基因 × 样本表达矩阵。
      traits: 样本 × 变量表（数值或可转数值；允许 NaN）。
      min_n: 有效配对样本数下限，低于则该项记 NaN（不给有偏结论）。

    Returns:
      长表 DataFrame：gene / trait / n / r / P / FDR（BH，NaN 不参与校正）。
    """
    rows = []
    for g in mat.index:
        x_all = mat.loc[g].to_numpy(dtype=float)
        for t in traits.columns:
            y_all = pd.to_numeric(traits[t], errors="coerce").to_numpy(dtype=float)
            ok = np.isfinite(x_all) & np.isfinite(y_all)
            if ok.sum() < min_n or np.std(x_all[ok]) == 0 or np.std(y_all[ok]) == 0:
                rows.append({"gene": g, "trait": t, "n": int(ok.sum()), "r": np.nan, "P": np.nan})
                continue
            r, p = stats.pearsonr(x_all[ok], y_all[ok])
            rows.append({"gene": g, "trait": t, "n": int(ok.sum()),
                         "r": float(r), "P": float(p)})
    tab = pd.DataFrame(rows)
    p = tab["P"].to_numpy(dtype=float)
    q = np.full(len(tab), np.nan)
    m = np.isfinite(p)
    if m.any():
        q[m] = stats.false_discovery_control(p[m], method="bh")
    tab["FDR"] = q
    return tab


def run(ctx, out):
    """模块入口：相关矩阵 + 高相关基因对 + 基因-临床相关表 + 热图。"""
    cfg = ctx["config"]
    expr, meta, keep = ctx["expr"], ctx["meta"], ctx.get("keep") or ctx["samples"]
    probes = cfg.get("gene_probes")
    if not probes:
        if "topn" not in cfg:
            raise ValueError("M18 需在 config.params.M18 指定 topn 或 gene_probes")
        deg = ctx.get("deg")
        if deg is None:
            raise ValueError("M18 未给 gene_probes 且上游无 M04（DEG），无法选基因")
        top = deg.loc[deg.DEG].assign(abs_t=lambda d: d["t"].abs()) \
                 .nlargest(int(cfg["topn"]), "abs_t")
        probes = top["ID_REF"].tolist()
    probes = [p for p in probes if p in expr.index]
    if len(probes) < 2:
        return f"可用探针不足 2（{len(probes)}），不产出相关矩阵（不假装成功）"

    sym = ctx.get("probe2sym") or {}
    mat = expr.loc[probes, keep]
    mat, n_dup = collapse_by_symbol(mat, sym)      # 多探针同符号必须聚合（见函数说明）

    cm = corr_matrix(mat)
    cm.to_csv(os.path.join(out, "M18_相关矩阵.csv"), encoding="utf-8-sig")
    pairs = (cm.where(np.triu(np.ones(cm.shape), 1).astype(bool)).stack()
               .rename("r").reset_index())
    pairs.columns = ["gene_a", "gene_b", "r"]
    min_abs_r = float(cfg.get("min_abs_r", 0.5))
    hi = pairs.loc[pairs["r"].abs() >= min_abs_r].sort_values("r", key=lambda s: -s.abs())
    hi.to_csv(os.path.join(out, "M18_高相关基因对.csv"), index=False, encoding="utf-8-sig")

    # 临床性状：年龄 / 复发事件 / 随访天数（沿用 M07 的合格样本口径）
    ev = ctx.get("ev")
    tt = ctx.get("tt")
    traits = pd.DataFrame({
        "age": [pd.to_numeric(_field(meta, s, "age"), errors="coerce") for s in keep],
        "relapse_event": list(ev) if ev is not None else np.nan,
        "rfs_days": list(tt) if tt is not None else np.nan,
    }, index=keep)
    ct = corr_with_traits(mat, traits, min_n=int(cfg.get("min_n", 10)))
    ct.to_csv(os.path.join(out, "M18_基因_临床相关表.csv"), index=False, encoding="utf-8-sig")

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(6.4, 5.6), dpi=300)
    im = ax.imshow(cm.to_numpy(), cmap="RdBu_r", vmin=-1, vmax=1)
    ax.set_xticks(range(len(cm))); ax.set_yticks(range(len(cm)))
    ax.set_xticklabels(cm.columns, rotation=90, fontsize=5)
    ax.set_yticklabels(cm.index, fontsize=5)
    ax.set_title("Gene-gene Pearson r", fontsize=9)
    fig.colorbar(im, ax=ax, shrink=0.8)
    fig.tight_layout()
    fig.savefig(os.path.join(out, "M18_相关热图.png"), dpi=300)
    plt.close(fig)

    sig = int((ct["FDR"] < 0.05).sum()) if len(ct) else 0
    return (f"基因 {len(mat)} 个（合并重复符号探针 {n_dup}）；高相关对（|r|≥{min_abs_r}）{len(hi)}；"
            f"基因-临床显著项（FDR<0.05）{sig}")


MODULES = [
    {"id": "M18", "name": "相关性分析", "folder": "相关性分析",
     "deps": ["M04"], "fn": run},
]
