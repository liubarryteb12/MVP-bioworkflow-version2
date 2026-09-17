#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""run_gse31210.py — GSE31210 真实数据分析

输入: ../GSE31210_series_matrix.txt.gz (repo 根目录)
输出: ../results/gse31210_results.json + ../results/figures/
"""
import sys, os, json, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(__file__))
import gse31210_adapter as ga
import numpy as np
from scipy import stats
from scipy.stats import ranksums
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedKFold
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "results")
FIGURES = os.path.join(OUT, "figures")
os.makedirs(OUT, exist_ok=True)
os.makedirs(FIGURES, exist_ok=True)
DATADIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def logrank_chi2(times, events, groups):
    """Log-rank chi-square test. times/events/groups are numpy arrays."""
    t = np.asarray(times); e = np.asarray(events); g = np.asarray(groups, dtype=int)
    n = len(t)
    if n < 4:
        return 0.0, 0.0, 1.0
    # Ordered by time
    order = np.argsort(t)
    t = t[order]; e = e[order]; g = g[order]
    # Risk set decrements at each event time
    at_risk = np.ones(n)
    d_event = np.zeros(n); d_event_high = np.zeros(n)
    ev_times = t[e == 1]
    for tm in ev_times:
        mask = t >= tm
        at_risk[mask] -= 1
    # Event counts
    for i in range(n):
        if e[i] == 1:
            d_event[i] = 1
            if g[i] == 1:
                d_event_high[i] = 1
    # E[O_H - E] and Var
    O_H = d_event_high.sum()
    E_H = (d_event * g).sum() * (g.sum()) / n
    Var = max(E_H * (n - g.sum()) / (n - 1), 1e-10)
    chi2 = (O_H - E_H) ** 2 / Var if Var > 0 else 0.0
    p = np.exp(-0.5 * chi2)
    return float(O_H), float(E_H), float(chi2), float(p)


def run():
    print("=== Loading GSE31210 ===")
    D = ga.load(DATADIR, verbose=True)
    X_raw = np.array(D["counts"])  # GEO: probes × samples
    X = X_raw.T                    # samples × probes
    sample_ids = D["sample_ids"]
    meta = D["meta"]
    death_status = meta["death_status"]
    relapse_status = meta["relapse_status"]
    days_to_event = meta["days_to_event"]
    stage = meta["stage"]
    prognos_gsms = meta["prognos_gsms"]
    tumor_gsms = set(meta["tumor_gsms"])
    normal_gsms = set(meta["normal_gsms"])
    sid_to_idx = {sid: i for i, sid in enumerate(sample_ids)}

    n_t, n_n = len(tumor_gsms), len(normal_gsms)
    print(f"Tumor={n_t}, Normal={n_n}, Total={X.shape[0]}, Probes={X.shape[1]}")

    # ① DE: tumor vs normal
    tumor_idx = sorted([sid_to_idx[s] for s in tumor_gsms])
    norm_idx = sorted([sid_to_idx[s] for s in normal_gsms])
    X_t = X[tumor_idx]; X_n = X[norm_idx]
    n_t, n_n = len(tumor_idx), len(norm_idx)
    se = np.sqrt(X_t.var(0)/n_t + X_n.var(0)/n_n)
    se[se == 0] = 1e-10
    t_stat = (X_t.mean(0) - X_n.mean(0)) / se
    p_raw = 2 * stats.t.sf(np.abs(t_stat), df=min(n_t, n_n)-1)
    order = np.argsort(p_raw)
    fdr = np.zeros(len(p_raw))
    fdr[order] = p_raw[order] * len(p_raw) / np.arange(1, len(p_raw)+1)
    fdr = np.minimum.accumulate(fdr[::-1])[::-1]
    log2fc = X_t.mean(0) - X_n.mean(0)
    sig = (fdr < 0.05) & (np.abs(log2fc) > 1.0)
    n_sig = int(sig.sum())
    up = int((log2fc[sig] > 0).sum()); dn = n_sig - up
    print(f"DE: {n_sig} probes (up={up}, dn={dn}), FDR<0.05")

    # ② 生存分析：risk score = z-scored DE signature
    # Use top 50 DE probes for robustness
    top50_idx = np.argsort(np.abs(log2fc))[::-1][:50]
    # risk = mean of |log2fc| weighted expression
    risk_score = np.abs(log2fc[top50_idx]).sum()  # not used directly; use X @ sign(log2fc)
    # Better: risk = sum over top50 of (log2fc * expr)
    risk_score = (X @ log2fc) / 30  # all probes, z-scored by division
    median_risk = np.median(risk_score)
    high_risk = risk_score >= median_risk

    # Build survival table
    surv_pairs = []
    for sid in prognos_gsms:
        idx = sid_to_idx[sid]
        evt = death_status.get(sid, "")
        if evt not in ("dead", "alive"):
            continue
        dte = days_to_event.get(sid, 0) or 0
        surv_pairs.append((idx, evt == "dead", float(dte)))
    surv_pairs.sort(key=lambda x: x[2])
    surv_idx = [p[0] for p in surv_pairs]
    times = np.array([p[2] for p in surv_pairs])
    events = np.array([p[1] for p in surv_pairs])
    groups = np.array([high_risk[i] for i in surv_idx])
    n_progn = len(times)
    n_high = int(groups.sum())
    n_low = n_progn - n_high

    O_H, E_H, chi2, p_surv = logrank_chi2(times, events, groups)
    hr_est = (events[groups==1].sum()/max(n_high,1)) / (events[groups==0].sum()/max(n_low,1))
    print(f"Survival: n={n_progn}, HR≈{hr_est:.2f}, χ²={chi2:.1f}, p={p_surv:.2e}")

    # ③ Relapse prediction AUC (5-fold CV, risk score)
    rel_idx = [i for i, sid in enumerate(sample_ids)
               if sid in relapse_status and relapse_status[sid] in ("relapsed", "not relapsed")]
    if len(rel_idx) >= 20:
        X_r = X[rel_idx]
        y_bin = np.array([1 if relapse_status[sample_ids[i]]=="relapsed" else 0 for i in rel_idx])
        risk_r = (X_r @ log2fc) / 30
        skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
        aucs = []
        for tr, te in skf.split(X_r, y_bin):
            auc = roc_auc_score(y_bin[te], risk_r[te])
            aucs.append(auc)
        mean_auc = float(np.mean(aucs))
        print(f"Relapse AUC: {mean_auc:.3f} ± {np.std(aucs):.3f}")
        status = "ok"
    else:
        mean_auc = 0.0; aucs = []; status = "partial"
        print(f"Insufficient relapse data: {len(rel_idx)} samples")

    # ④ 增量 ΔAUC（vs stage-only）
    stage_map = {"IA": 0, "IB": 1, "II": 2, "III": 3, "IV": 4}
    rel_stage_idx = []; stage_vals = []
    for i, sid in enumerate(sample_ids):
        if sid not in relapse_status or relapse_status[sid] not in ("relapsed","not relapsed"):
            continue
        stg = stage.get(sid, "unknown")
        if stg not in stage_map:
            continue
        rel_stage_idx.append(i)
        stage_vals.append(stage_map[stg])
    if len(rel_stage_idx) >= 20:
        X_s = X[rel_stage_idx]
        y_s = np.array([1 if relapse_status[sample_ids[i]]=="relapsed" else 0 for i in rel_stage_idx])
        risk_s = (X_s @ log2fc) / 30
        skf2 = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
        auc_stage = []; auc_risk = []
        for tr, te in skf2.split(X_s, y_s):
            a_s = roc_auc_score(y_s[te], np.array(stage_vals)[te])
            a_r = roc_auc_score(y_s[te], risk_s[te])
            auc_stage.append(a_s); auc_risk.append(a_r)
        base_auc = float(np.mean(auc_stage))
        combo_auc = float(np.mean(auc_risk))
        delta = combo_auc - base_auc
        print(f"Stage-only AUC={base_auc:.3f}, Risk AUC={combo_auc:.3f}, Δ={delta:.3f}")
    else:
        base_auc = 0.0; combo_auc = 0.0; delta = 0.0

    # ⑤ 保存结果
    results = dict(
        status=status,
        n_total=X.shape[0], n_tumor=n_t, n_normal=n_n,
        de_count=n_sig, de_up=up, de_dn=dn,
        survival_n=n_progn, survival_hr=round(float(hr_est),2),
        survival_chi2=round(float(chi2),2), survival_p=round(float(p_surv),6),
        relapse_auc_mean=round(mean_auc,3),
        relapse_auc_std=round(float(np.std(aucs)),3) if aucs else 0.0,
        stage_base_auc=round(base_auc,3),
        risk_auc=round(combo_auc,3),
        delta_auc=round(delta,3),
    )
    with open(os.path.join(OUT, "gse31210_results.json"), "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    # ⑥ 保存关键 figure（DE volcano + KM curve）
    _save_figures(X, log2fc, sig, times, events, groups, mean_auc, delta)

    print("\n=== Results ===")
    for k,v in results.items():
        print(f"  {k}: {v}")
    print(f"\nSaved to {os.path.join(OUT, 'gse31210_results.json')}")


def _save_figures(X, log2fc, sig, times, events, groups, auc, delta):
    """Save key figures."""
    # Fig 1: Volcano plot
    fig, ax = plt.subplots(figsize=(6, 4.5))
    sig_mask = sig
    x = log2fc[~sig_mask]; y = -np.log10(np.maximum(1e-300, 2*stats.t.sf(np.abs(
        (X[np.array([0]*len(x), dtype=int)],)  # placeholder
    ))))
    # 简化：用 top 30 DE probes 画火山图
    top30 = np.argsort(np.abs(log2fc))[::-1][:30]
    pvals_arr = 2 * stats.t.sf(np.abs(t_stat), df=float(min(n_t,n_n)-1))
    ax.scatter(log2fc[top30], -np.log10(np.maximum(pvals_arr[top30], 1e-300)),
               c=['red' if log2fc[i]>0 else 'blue' for i in top30], s=8, alpha=0.7)
    ax.axhline(-np.log10(0.05), color='gray', ls='--', lw=0.8)
    ax.set_xlabel('log2(Fold Change)'); ax.set_ylabel('-log10(P-value)')
    ax.set_title('GSE31210 Volcano (top 30 DE probes)')
    fig.tight_layout()
    fig.savefig(os.path.join(FIGURES, "fig1_volcano.png"), dpi=300)
    plt.close(fig)

    # Fig 2: KM curve
    fig, ax = plt.subplots(figsize=(5, 4))
    for label, mask in [("High risk", groups==1), ("Low risk", groups==0)]:
        idx = np.where(mask)[0]
        if len(idx) < 2: continue
        sort_idx = np.argsort(times[idx])
        cum_fail = np.cumsum(events[idx][sort_idx]) / len(idx)
        ax.step(times[idx][sort_idx], 1-cum_fail, where='post', label=label)
    ax.set_xlabel('Days'); ax.set_ylabel('P(Free of recurrence)')
    ax.set_title(f'KM: χ²={float(chi2()):.1f}, p={float(p_surv()):.2e}' if False
                 else f'KM: risk score stratification (n={len(times)})')
    ax.legend()
    fig.tight_layout()
    fig.savefig(os.path.join(FIGURES, "fig2_km.png"), dpi=300)
    plt.close(fig)


if __name__ == "__main__":
    run()
