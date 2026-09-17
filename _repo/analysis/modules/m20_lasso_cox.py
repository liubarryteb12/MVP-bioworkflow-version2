# -*- coding: utf-8 -*-
"""M20 LASSO 稀疏风险模型（内化自参考文件 D 层 #13 LASSO 风险模型）。

与 M08 的关系（重要）：M08 = 折内 log-rank χ² 排序 + L2 logistic（稠密）；
M20 = **折内 L1（LASSO）** 稀疏筛选，用于复现文献常见"LASSO 签名"写法并对照
"稀疏 vs 稠密"的折外表现。两者都是折内协议，**数字口径不同、不得混用同一句**。

说明：本项目未引入 sksurv，LASSO 在"复发二分类"口径上实现（L1 logistic）；
下游 Cox PH 仅用于把折外评分换算为 HR，不作为独立证据。
"""
import os

import numpy as np
import pandas as pd


def make_l1_logistic(c, seed):
    """构造 L1（LASSO）logistic，兼容 sklearn 新旧 API。

    sklearn ≥1.8 弃用 penalty='l1'（改 l1_ratio=1，1.10 将移除），旧版不认识 l1_ratio
    → 先试新 API，TypeError（旧版未知参数）再回退旧写法。降级路径必须有注释与依据。
    """
    from sklearn.linear_model import LogisticRegression
    try:
        return LogisticRegression(l1_ratio=1.0, solver="liblinear", C=float(c),
                                  max_iter=2000, random_state=int(seed))
    except TypeError:
        return LogisticRegression(penalty="l1", solver="liblinear", C=float(c),
                                  max_iter=2000, random_state=int(seed))


def lasso_select(X, y, c=0.1, seed=20260910):
    """L1（LASSO）稀疏特征选择（纯函数）。

    Args:
      X: 样本 × 特征矩阵（调用方须先标准化）。
      y: 0/1 结局。
      c: 正则强度倒数（越小越稀疏）。
      seed: 随机种子（确定性）。

    Returns:
      (非零掩码 ndarray[bool], 系数 ndarray)
    """
    clf = make_l1_logistic(c, seed)
    clf.fit(X, y)
    coef = clf.coef_.ravel()
    return coef != 0, coef


def run(ctx, out):
    """模块入口：折内 LASSO 筛选 → 折外评分 → AUC/HR + 稀疏结构归档。"""
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import StratifiedKFold
    from sklearn.metrics import roc_auc_score
    from statsmodels.duration.hazard_regression import PHReg

    cfg = ctx["config"]
    if "topk" not in cfg:
        raise ValueError("M20 需在 config.params.M20 指定 topk（候选 DEG 数）")
    seed = int(cfg.get("seed", ctx.get("seed", 20260910)))
    c_reg = float(cfg.get("C", 0.1))
    n_splits = int(cfg.get("n_splits", 5))

    expr, keep, tt, ev = ctx["expr"], ctx["keep"], ctx["tt"], ctx["ev"]
    deg = ctx["deg"]
    deg_ids = deg.loc[deg.DEG, "ID_REF"].tolist()
    chis = [ctx["logrank"](tt, ev, (expr.loc[p, keep].values >
                                    np.median(expr.loc[p, keep].values)).astype(int))[0]
            for p in deg_ids]
    feats = list(np.asarray(deg_ids)[np.argsort(-np.asarray(chis))[:int(cfg["topk"])]])
    X_all = expr.loc[feats, keep].values.T

    skf = StratifiedKFold(n_splits, shuffle=True, random_state=seed)
    oof = np.full(len(keep), np.nan)
    per_fold, freq = [], {}
    for k, (tr, te) in enumerate(skf.split(X_all, ev), 1):
        mu, sd = X_all[tr].mean(0), X_all[tr].std(0)
        sd[sd == 0] = 1.0
        Ztr, Zte = (X_all[tr] - mu) / sd, (X_all[te] - mu) / sd
        sel, coef = lasso_select(Ztr, ev[tr], c=c_reg, seed=seed)
        per_fold.append({"fold": k, "n_selected": int(sel.sum()),
                         "features": ";".join(np.asarray(feats)[sel])})
        for f in np.asarray(feats)[sel]:
            freq[f] = freq.get(f, 0) + 1
        clf = make_l1_logistic(c_reg, seed)
        clf.fit(Ztr[:, sel] if sel.any() else Ztr, ev[tr])
        oof[te] = clf.decision_function(Zte[:, sel] if sel.any() else Zte)

    auc = float(roc_auc_score(ev, oof))
    cox = PHReg(tt, oof.reshape(-1, 1), status=ev).fit()
    hr, ci = float(np.exp(cox.params[0])), np.exp(cox.conf_int()[0])

    pd.DataFrame(per_fold).to_csv(os.path.join(out, "M20_每折入选.csv"),
                                 index=False, encoding="utf-8-sig")
    top = (pd.DataFrame({"feature": list(freq), "n_folds": list(freq.values())})
             .sort_values("n_folds", ascending=False))
    top.to_csv(os.path.join(out, "M20_跨折入选频次.csv"), index=False, encoding="utf-8-sig")
    pd.DataFrame({"sample": keep, "score_lasso": oof, "event": ev, "rfs_days": tt}).to_csv(
        os.path.join(out, "M20_OOF评分.csv"), index=False, encoding="utf-8-sig")
    ctx["oof_score"] = pd.Series(oof, index=keep)      # 供 M19 复用（模块间传递）

    return (f"折外 AUC={auc:.4f}，HR={hr:.3f} "
            f"（折内 LASSO 入选 {[p['n_selected'] for p in per_fold]} / {len(feats)}）")


MODULES = [
    {"id": "M20", "name": "LASSO稀疏风险模型", "folder": "LASSO风险模型",
     "deps": ["M04", "M07"], "fn": run},
]
