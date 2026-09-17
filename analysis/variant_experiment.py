#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""variant_experiment.py — 受控对照实验：特征选择协议对 GSE31210 风险评分效能的影响
变体：
  A 折内 χ²-top200（T31 合规，结局对齐排序）
  B 折内 χ²-top50
  C 全队列初筛+全队列拟合（泄露对照：模仿 Wen 2022 的做法，仅作 T31 教学对照，不得用于主张）
另核对 stage 取值分布（排查 stage_I 亚组缺失）。
复用 analyze_gse31210 的解析与统计函数（同 seed=20260910）。
"""
import gzip, json, os, warnings
import numpy as np
import pandas as pd
from scipy import stats
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold
from sklearn.metrics import roc_auc_score
warnings.filterwarnings("ignore")

SEED = 20260910
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.environ.get(
    "GSE_DATA_PATH",
    r"d:/00.AIagent/codebuddy_workspace/生信分析+SCI文章写作工作流搭建/06.测试用数据/GSE31210_series_matrix.txt.gz")
RES = os.path.join(BASE, "results")


def bh(p):
    p = np.asarray(p, float); n = len(p)
    o = np.argsort(p); ps = p[o]
    q = np.minimum.accumulate((ps * n / np.arange(1, n + 1))[::-1])[::-1]
    out = np.empty(n); out[o] = np.minimum(q, 1.0)
    return out


def logrank(t, e, g):
    t, e, g = np.asarray(t, float), np.asarray(e, int), np.asarray(g, int)
    O1 = E1 = V = 0.0
    for tt in np.unique(t[e == 1]):
        ar = (t >= tt).sum(); ev_ = ((t == tt) & (e == 1)).sum()
        n1 = ((t >= tt) & (g == 1)).sum(); e1 = ((t == tt) & (e == 1) & (g == 1)).sum()
        O1 += e1; E1 += ev_ * n1 / ar
        if ar > 1:
            V += ev_ * (n1 / ar) * (1 - n1 / ar) * (ar - ev_) / (ar - 1)
    chi2 = (O1 - E1) ** 2 / V if V > 0 else 0.0
    return chi2, float(stats.chi2.sf(chi2, 1))


# --- 解析（同主脚本） ---
samples, rows, meta = None, [], {}
with gzip.open(DATA, "rt", errors="replace") as f:
    in_table = False
    for line in f:
        line = line.rstrip("\n")
        if line.startswith("!Sample_geo_accession"):
            samples = [s.strip('"') for s in line.split("\t")[1:]]
        elif line.startswith("!Sample_characteristics_ch1"):
            vals = [v.strip('"') for v in line.split("\t")[1:]]
            for i, s in enumerate(samples):
                meta.setdefault(s, []).append(vals[i] if i < len(vals) else "")
        elif line.startswith("!series_matrix_table_begin"):
            in_table = True
        elif in_table and line.startswith("!series_matrix_table_end"):
            break
        elif in_table:
            parts = [c.strip('"') for c in line.split("\t")]
            if parts[0] == "ID_REF":
                continue
            rows.append(parts)
expr = pd.DataFrame([[float(v) for v in r[1:]] for r in rows],
                    index=[r[0] for r in rows], columns=samples)
expr = np.log2(expr + 1)


def gf(s, prefix):
    vals = [v[len(prefix):].lstrip(":").strip() for v in meta[s] if v.startswith(prefix)]
    vals = [v for v in vals if v]
    return vals[0] if vals else None


info = pd.DataFrame(index=samples)
info["tissue"] = [gf(s, "tissue:") for s in samples]
info["age"] = pd.to_numeric([gf(s, "age (years):") for s in samples], errors="coerce")
info["sex"] = [gf(s, "gender:") for s in samples]
info["stage"] = [gf(s, "pathological stage") for s in samples]
info["relapse"] = [gf(s, "relapse:") for s in samples]
info["rfs_days"] = pd.to_numeric([gf(s, "days before relapse/censor") for s in samples], errors="coerce")
info["exclude"] = [gf(s, "exclude for prognosis analysis") for s in samples]

tum = info["tissue"] == "primary lung tumor"
print("stage 取值分布（肿瘤）:", info.loc[tum, "stage"].value_counts(dropna=False).to_dict())
print("exclude 取值分布（肿瘤）:", info.loc[tum, "exclude"].value_counts(dropna=False).to_dict())

prog = tum & (info["exclude"].fillna("").str.split(":").str[-1].str.strip() != "exclude")
pi = info.loc[prog].copy()
ev = (pi["relapse"] == "relapsed").astype(int).values
tt = pi["rfs_days"].values.astype(float)
valid = np.isfinite(tt) & (tt > 0)
pi, ev, tt = pi.loc[valid], ev[valid], tt[valid]
print(f"预后集 n={len(ev)} 事件={ev.sum()}")
Et = expr.loc[:, tum].values; En = expr.loc[:, ~tum].values
tstat, pval = stats.ttest_ind(Et, En, axis=1, equal_var=False)
l2fc = Et.mean(1) - En.mean(1)
padj = bh(pval)
deg_cols = np.where((np.abs(l2fc) >= 0.585) & (padj < 0.05) & np.isfinite(pval))[0]
Etum = expr.loc[:, info["tissue"] == "primary lung tumor"]
Xi = Etum.loc[:, pi.index].values.T

from statsmodels.duration.hazard_regression import PHReg


def evaluate(score, ev_, tt_):
    auc = roc_auc_score(ev_, score)
    cox = PHReg(tt_, score.reshape(-1, 1), status=ev_).fit()
    hr = float(np.exp(cox.params[0])); p_cox = float(cox.pvalues[0])
    g = (score > np.median(score)).astype(int)
    c2, p_km = logrank(tt_, ev_, g)
    return {"AUC": round(auc, 4), "HR": round(hr, 3), "CoxP": round(p_cox, 5), "KM_P": round(p_km, 5)}


def run_variant(name, topk, in_fold=True):
    """in_fold=True: 折内初筛(χ²排序)+折内拟合；False: 全队列初筛+全队列拟合（泄露对照）"""
    oof = np.full(len(ev), np.nan)
    if in_fold:
        skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=SEED)
        for tr, te in skf.split(Xi[:, deg_cols], ev):
            chis = [logrank(tt[tr], ev[tr], (Xi[tr, j] > np.median(Xi[tr, j])).astype(int))[0]
                    for j in deg_cols]
            feats = deg_cols[np.argsort(-np.asarray(chis))[:topk]]
            mu, sd = Xi[np.ix_(tr, feats)].mean(0), Xi[np.ix_(tr, feats)].std(0) + 1e-9
            clf = LogisticRegression(C=0.1, max_iter=2000, random_state=SEED)
            clf.fit((Xi[np.ix_(tr, feats)] - mu) / sd, ev[tr])
            oof[te] = clf.decision_function((Xi[np.ix_(te, feats)] - mu) / sd)
        res = evaluate(oof, ev, tt); res["类型"] = "折内（T31 合规）"
    else:
        chis = [logrank(tt, ev, (Xi[:, j] > np.median(Xi[:, j])).astype(int))[0] for j in deg_cols]
        feats = deg_cols[np.argsort(-np.asarray(chis))[:topk]]
        mu, sd = Xi[:, feats].mean(0), Xi[:, feats].std(0) + 1e-9
        clf = LogisticRegression(C=0.1, max_iter=2000, random_state=SEED)
        clf.fit((Xi[:, feats] - mu) / sd, ev)
        res = evaluate(clf.decision_function((Xi[:, feats] - mu) / sd), ev, tt)
        res["类型"] = "全队列（泄露对照，模仿 Wen 做法）"
    res["topk"] = topk
    print(f"变体 {name}: {res}")
    return name, res


out = {}
out["A_折内chi2_top200"] = run_variant("A", 200, True)[1]
out["B_折内chi2_top50"] = run_variant("B", 50, True)[1]
out["C_泄露对照_top200"] = run_variant("C", 200, False)[1]
out["D_泄露对照_top50"] = run_variant("D", 50, False)[1]
out["stage分布"] = info.loc[tum, "stage"].value_counts(dropna=False).to_dict()
with open(os.path.join(RES, "variant_experiment.json"), "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=1, default=str)
print("已落盘 results/variant_experiment.json")
