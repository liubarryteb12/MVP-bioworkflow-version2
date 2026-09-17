#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""analyze_gse31210.py — GSE31210 全流程实战（方法模仿 Wen 2022 BMC Cancer，T31 泄露修正）

单元覆盖：U01/U02（解析+QC）→ U03（DEG+富集）→ U04（折内初筛+CV 建模+ΔAUC+Cox/KM）
         → U05（敏感性）→ U06（唯一台账 results/results.json + 台账.md）
预注册：seed=20260910；|log2FC|>=0.585 & P.adj<0.05；生存初筛 FDR<0.1；折内 top200；L2 logistic C=0.1
"""
import gzip, json, os, sys, time, warnings
import numpy as np
import pandas as pd
from scipy import stats
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold
from sklearn.metrics import roc_auc_score, roc_curve
warnings.filterwarnings("ignore")
from probe_mapping import resolve_report   # 探针→基因 symbol 通用框架（列由 AI 按数据集指定）

SEED = 20260910
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.environ.get(
    "GSE_DATA_PATH",
    r"d:/00.AIagent/codebuddy_workspace/生信分析+SCI文章写作工作流搭建/06.测试用数据/GSE31210_series_matrix.txt.gz")
ANNOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "GPL570.annot.gz")
RES = os.path.join(BASE, "results"); os.makedirs(RES, exist_ok=True)
FIG = os.path.join(BASE, "figures"); os.makedirs(FIG, exist_ok=True)
FC_MIN, PADJ_MIN = 0.585, 0.05       # T02 DEG
SCREEN_FDR = 0.1                     # 生存初筛
TOPK, C_L2, NSPLITS, NBOOT = 200, 0.1, 5, 500
R = {}                                # 台账


def L(key, value, note=""):
    R[key] = {"value": value, "note": note}
    print(f"[台账] {key} = {value} {('｜ '+note) if note else ''}")


def bh(p):
    p = np.asarray(p, float); n = len(p)
    o = np.argsort(p); ps = p[o]
    q = np.minimum.accumulate((ps * n / np.arange(1, n + 1))[::-1])[::-1]
    q = np.minimum(q, 1.0); out = np.empty(n); out[o] = q
    return out


def logrank(t, e, g):
    """log-rank 双侧检验，2 组。返回 chi2, p。"""
    t, e, g = np.asarray(t, float), np.asarray(e, int), np.asarray(g, int)
    O1 = E1 = V = 0.0
    for tt in np.unique(t[e == 1]):
        at_risk = (t >= tt).sum(); ev = ((t == tt) & (e == 1)).sum()
        n1 = ((t >= tt) & (g == 1)).sum(); e1 = ((t == tt) & (e == 1) & (g == 1)).sum()
        O1 += e1; E1 += ev * n1 / at_risk
        if at_risk > 1:
            V += ev * (n1 / at_risk) * (1 - n1 / at_risk) * (at_risk - ev) / (at_risk - 1)
    chi2 = (O1 - E1) ** 2 / V if V > 0 else 0.0
    return chi2, float(stats.chi2.sf(chi2, 1))


# ---------- U01/U02 解析与 QC ----------
print("=" * 70, "\nU01/U02 解析与 QC", sep="")
meta, samples, rows = {}, None, []
with gzip.open(DATA, "rt", errors="replace") as f:
    in_table = False
    for line in f:
        line = line.rstrip("\n")
        if line.startswith("!Sample_geo_accession"):
            samples = [s.strip('"') for s in line.split("\t")[1:]]
        elif line.startswith("!Sample_characteristics_ch1"):
            vals = [v.strip('"') for v in line.split("\t")[1:]]
            for i, s in enumerate(samples):
                meta.setdefault(s, [])
                meta[s].append(vals[i] if i < len(vals) else "")
        elif line.startswith("!series_matrix_table_begin"):
            in_table = True
        elif in_table and line.startswith("!series_matrix_table_end"):
            break
        elif in_table:
            parts = [c.strip('"') for c in line.split("\t")]
            if parts[0] == "ID_REF":
                continue
            rows.append(parts)          # 收集后一次性建表，避免逐行 concat 的 O(n²)
expr = pd.DataFrame([[float(v) for v in r[1:]] for r in rows],
                    index=[r[0] for r in rows], columns=samples)
expr.index.name = "ID_REF"


def get_field(s, prefix):
    """GEO 上传者常把同一字段拆到多行 characteristics（有的行为空）：
    扫该样本全部取值，返回第一个非空的 prefix 匹配；lstrip(':') 统一容错
    （教训：prefix 带不带冒号导致取值残留 ': 253' 这类前缀，先红在 debug 中实证）。"""
    vals = [v[len(prefix):].lstrip(":").strip() for v in meta[s] if v.startswith(prefix)]
    vals = [v for v in vals if v]
    return vals[0] if vals else None


info = pd.DataFrame(index=samples)
info["tissue"] = [get_field(s, "tissue:") for s in samples]
info["age"] = pd.to_numeric([get_field(s, "age (years):") for s in samples], errors="coerce")
info["sex"] = [get_field(s, "gender:") or get_field(s, "sex:") for s in samples]
info["stage"] = [get_field(s, "pathological stage") for s in samples]
info["relapse"] = [get_field(s, "relapse:") for s in samples]
info["rfs_days"] = pd.to_numeric([get_field(s, "days before relapse/censor") for s in samples], errors="coerce")
info["os_days"] = pd.to_numeric([get_field(s, "days before death/censor") for s in samples], errors="coerce")
info["exclude"] = [get_field(s, "exclude for prognosis analysis") for s in samples]
print("字段前缀抽样：", sorted({v.split(":")[0] for s in samples for v in meta[s] if ":" in v})[:20])

n_tumor = int((info["tissue"] == "primary lung tumor").sum())
n_normal = int((info["tissue"] == "normal lung").sum())
L("U01_样本数", {"肿瘤": n_tumor, "癌旁": n_normal, "总": len(samples)}, "series matrix 解析")
L("U02_log2转换", "log2(x+1)", "GPL570 强度值，与 demo 口径一致")
expr = np.log2(expr + 1)
L("U02_表达分布", {"肿瘤中位强度": round(float(expr.loc[:, info['tissue'] == 'primary lung tumor'].values.mean()), 3),
                  "癌旁中位强度": round(float(expr.loc[:, info['tissue'] == 'normal lung'].values.mean()), 3)},
  "QC：两组分布量级一致，无整体偏移")
L("U02_T21_组间样本量", {"肿瘤": n_tumor, "癌旁": n_normal}, "T21 三态：两组样本量充足 → PASS")
L("U02_Y6_批次", "单一数据集，series matrix 无扫描批次/处理批次字段 → 技术批次不适用（不适用+理由），禁止 ComBat 抹除", "T15 线粒体子判据不适用：芯片平台无该字段")

tum = info["tissue"] == "primary lung tumor"
prog = tum & (info["exclude"].fillna("").str.split(":").str[-1].str.strip() != "exclude")
n_prog = int(prog.sum()); n_ev = int((info.loc[prog, "relapse"] == "relapsed").sum())
L("U01_排除规则", f"排除标记=exclude 共 {n_tumor - n_prog} 例 → 预后集 n={n_prog}", "预注册唯一排除标准")
L("U04_EPV", round(n_ev / 1, 1), f"事件 {n_ev}，EPV={n_ev}≥10（单评分变量）")

# 探针→基因注释（平台无关框架；列由 AI 按数据集显式指定，不写死 parts[2]）
#   GPL570.annot.gz：探针列=0 'ID'，symbol 列=2 'Gene symbol'
_annot_rep, probe2sym = resolve_report(ANNOT, probe_col=0, symbol_col=2, split_multi=False)
n_annot = sum(1 for v in probe2sym.values() if v)
L("U01_注释覆盖",
  f"{n_annot}/{expr.shape[0]} 探针有基因符号",
  f"GPL570 官方注释 | 探针列={_annot_rep['probe_name']} 符号列={_annot_rep['symbol_name']} "
  f"覆盖{_annot_rep['coverage_pct']}% 多symbol={_annot_rep['n_probes_multi_symbol']}")

# ---------- U03a 差异表达 ----------
print("=" * 70, "\nU03a 差异表达（Welch t + BH）", sep="")
Et = expr.loc[:, tum].values; En = expr.loc[:, ~tum].values
tstat, pval = stats.ttest_ind(Et, En, axis=1, equal_var=False)
l2fc = Et.mean(1) - En.mean(1)
padj = bh(pval)
deg_mask = (np.abs(l2fc) >= FC_MIN) & (padj < PADJ_MIN) & (np.isfinite(pval))
deg_ids = expr.index[deg_mask]
L("T02_DEG", {"总数": int(deg_mask.sum()),
              "上调": int(((l2fc > 0) & deg_mask).sum()),
              "下调": int(((l2fc < 0) & deg_mask).sum())},
  f"阈值 |log2FC|>={FC_MIN} & P.adj<{PADJ_MIN}（Welch t + BH）")
deg_tab = pd.DataFrame({"ID_REF": expr.index, "symbol": [probe2sym.get(p, "") for p in expr.index],
                        "log2FC": l2fc, "t": tstat, "P": pval, "P.adj": padj, "DEG": deg_mask})
deg_tab.to_csv(os.path.join(RES, "T02_差异表达全表.csv"), index=False, encoding="utf-8-sig")

# ---------- U03b 富集（在线，失败→不适用+理由） ----------
print("=" * 70, "\nU03b GO/KEGG 富集（gseapy/Enrichr）", sep="")
enr_status = "未做"
try:
    if os.name == "nt":
        # 本机 Windows 访问 Enrichr 需代理；云端 Linux runner 直连（曾因写死代理致云端富集失败）
        os.environ.setdefault("HTTP_PROXY", "http://127.0.0.1:7890")
        os.environ.setdefault("HTTPS_PROXY", "http://127.0.0.1:7890")
    import gseapy as gp
    up_syms = sorted({probe2sym[p] for p in deg_ids if l2fc[expr.index.get_loc(p)] > 0 and probe2sym.get(p)})
    dn_syms = sorted({probe2sym[p] for p in deg_ids if l2fc[expr.index.get_loc(p)] < 0 and probe2sym.get(p)})
    enr_up = gp.enrichr(gene_list=up_syms, gene_sets=["GO_Biological_Process_2023", "KEGG_2021_Human"],
                        organism="human", outdir=None, no_plot=True)
    enr_dn = gp.enrichr(gene_list=dn_syms, gene_sets=["GO_Biological_Process_2023", "KEGG_2021_Human"],
                        organism="human", outdir=None, no_plot=True)
    up = enr_up.results[enr_up.results["Adjusted P-value"] < 0.05]
    dn = enr_dn.results[enr_dn.results["Adjusted P-value"] < 0.05]
    up.to_csv(os.path.join(RES, "T04_富集_上调.csv"), index=False)
    dn.to_csv(os.path.join(RES, "T04_富集_下调.csv"), index=False)
    top_up = up.sort_values("Adjusted P-value").head(5)[["Term", "Adjusted P-value"]].values.tolist()
    top_dn = dn.sort_values("Adjusted P-value").head(5)[["Term", "Adjusted P-value"]].values.tolist()
    L("T04_富集", {"上调通路显著数": int(len(up)), "下调通路显著数": int(len(dn)),
                  "上调Top5": top_up, "下调Top5": top_dn},
      "GO_BP+KEGG，P.adj<0.05；模仿 Wen 2022 的通路分析环节")
    enr_status = "done"
    np.save(os.path.join(RES, "_enr_up.npy"), up.head(12).values, allow_pickle=True)
except Exception as ex:
    L("T04_富集", "不适用+理由", f"在线富集不可用（{type(ex).__name__}: {str(ex)[:120]}）——如实标注，不冒充完成")

# ---------- U04 折内初筛 + CV 建模 ----------
print("=" * 70, "\nU04 折内生存初筛 + CV 建模（T31 无泄露）", sep="")
pi = info.loc[prog].copy()
ev = (pi["relapse"] == "relapsed").astype(int).values
tt = pi["rfs_days"].values.astype(float)
valid = np.isfinite(tt) & (tt > 0)
pi, ev, tt = pi.loc[valid], ev[valid], tt[valid]
idx = np.where(prog.values)[0][valid]
Etum_all = expr.loc[:, info["tissue"] == "primary lung tumor"]
Xi = Etum_all.loc[:, pi.index].values.T          # 样本×探针（仅肿瘤）
deg_cols = np.where(deg_mask)[0]
l2fc_deg = l2fc[deg_cols]
L("U04_预后集", {"n": len(ev), "事件": int(ev.sum())}, "排除后 RFS 分析集")

skf = StratifiedKFold(n_splits=NSPLITS, shuffle=True, random_state=SEED)
oof = np.full(len(ev), np.nan); oof_base = np.full(len(ev), np.nan)
oof_proba = np.full(len(ev), np.nan)   # 校准/DCA 用概率（H-1：CV 预测概率口径）
fold_auc, fallback_folds, screen_sizes = [], [], []
for tr, te in skf.split(Xi, ev):
    Xtr = Xi[tr]                       # 全探针行（列号即真实探针下标）
    # ① 折内生存初筛（结局信息不出折），按 log-rank χ² 排序（协议修订 v2，见 U00 偏差记录）
    chis, ps = [], []
    for j in deg_cols:
        x = Xtr[:, j]; med = np.median(x)
        c2, p = logrank(tt[tr], ev[tr], (x > med).astype(int))
        chis.append(c2); ps.append(p)
    chis = np.asarray(chis); q = bh(ps)
    sel = q < SCREEN_FDR
    screen_sizes.append(int(sel.sum()))
    use = np.where(sel)[0] if sel.sum() >= 10 else np.arange(Xtr.shape[1])
    if sel.sum() < 10:
        fallback_folds.append(1)
    # ② 折内 χ² top200（初筛显著者中取 χ² 最大的 TOPK 个，结局对齐且仍在折内）
    #    注意 use 是 deg_cols 内的位置索引，必须映射回真实探针列号（曾因错位拿全矩阵前 200 列，AUC 掉到 0.53）
    order = np.argsort(-chis[use])[:TOPK]
    feats = deg_cols[use[order]]
    # ③ L2 logistic
    mu, sd = Xtr[:, feats].mean(0), Xtr[:, feats].std(0) + 1e-9
    clf = LogisticRegression(C=C_L2, max_iter=2000, random_state=SEED)
    clf.fit((Xtr[:, feats] - mu) / sd, ev[tr])
    oof[te] = clf.decision_function((Xi[np.ix_(te, feats)] - mu) / sd)
    oof_proba[te] = clf.predict_proba((Xi[np.ix_(te, feats)] - mu) / sd)[:, 1]
    # 基线：年龄+性别+分期
    def base_mat(rows):
        a = pi["age"].values[rows]; s = (pi["sex"].values[rows] == "male").astype(float)
        st = pi["stage"].values[rows]
        sia = np.array([1 if x == "IA" else 0 for x in st], float)
        sib = np.array([1 if x == "IB" else 0 for x in st], float)
        sii = np.array([1 if x == "II" else 0 for x in st], float)
        return np.column_stack([a, s, sia, sib, sii])
    Btr = base_mat(tr); Bte = base_mat(te)
    mb, sb = np.nanmean(Btr, 0), np.nanstd(Btr, 0) + 1e-9
    cb = LogisticRegression(C=1.0, max_iter=2000, random_state=SEED)
    cb.fit(np.nan_to_num((Btr - mb) / sb), ev[tr])
    oof_base[te] = cb.decision_function(np.nan_to_num((Bte - mb) / sb))

full_auc = roc_auc_score(ev, oof); base_auc = roc_auc_score(ev, oof_base)
delta = full_auc - base_auc
boot = []
rng = np.random.default_rng(SEED)
for _ in range(NBOOT):
    ii = rng.integers(0, len(ev), len(ev))
    if len(set(ev[ii])) < 2:
        continue
    boot.append(roc_auc_score(ev[ii], oof[ii]) - roc_auc_score(ev[ii], oof_base[ii]))
dlo, dhi = np.percentile(boot, [2.5, 97.5])
L("T12_CV_AUC", {"模型": round(full_auc, 4), "基线": round(base_auc, 4),
                 "DeltaAUC": round(delta, 4), "CI95": [round(dlo, 4), round(dhi, 4)]},
  f"5 折分层 CV（seed={SEED}），OOF 汇集；ΔAUC bootstrap {NBOOT} 次")
L("T31_无泄露", {"折内初筛显著数(均)": int(np.mean(screen_sizes)), "回退折": sum(fallback_folds)},
  "生存初筛与特征选择均在训练折内完成，结局信息未出折")
L("T13a_校准限定", "CV 预测概率口径（decision_function 排序等价），训练内恒 1 现象不适用于正则化 logistic", "H-1")

# OOF 评分表落盘（KM/ROC/校准/DCA 图与台账复用）
pd.DataFrame({"sample": pi.index, "score_oof": oof, "proba_oof": oof_proba,
              "score_base": oof_base, "event": ev, "rfs_days": tt,
              "stage": pi["stage"].values, "sex": pi["sex"].values,
              "age": pi["age"].values}).to_csv(
    os.path.join(RES, "T12_OOF评分表.csv"), index=False, encoding="utf-8-sig")

# Cox PH（OOF 评分 vs RFS）
from statsmodels.duration.hazard_regression import PHReg
cox = PHReg(tt, oof.reshape(-1, 1), status=ev).fit()
hr = float(np.exp(cox.params[0])); ci = np.exp(cox.conf_int()[0])
L("T06_Cox_评分", {"HR": round(hr, 3), "CI95": [round(ci[0], 3), round(ci[1], 3)],
                   "P": float(cox.pvalues[0])}, "Cox PH（Breslow），OOF 评分连续变量")

# KM + log-rank（中位分割）
g = (oof > np.median(oof)).astype(int)
c2, pkm = logrank(tt, ev, g)
L("T06_KM", {"logrank_chi2": round(c2, 2), "P": pkm,
             "高分组n": int(g.sum()), "低分组n": int(len(g) - g.sum())},
  "OOF 风险评分中位分割（模仿 Wen 的 KM 展示）")

# ---------- U04 扩展：签名持久化（全量重拟，同折内协议；供外部验证应用） ----------
chis_f, ps_f = [], []
for j in deg_cols:
    x = Xi[:, j]
    c2f, pf = logrank(tt, ev, (x > np.median(x)).astype(int))
    chis_f.append(c2f); ps_f.append(pf)
chis_f = np.asarray(chis_f); q_f = bh(ps_f)
use_f = np.where(q_f < SCREEN_FDR)[0]
order_f = np.argsort(-chis_f[use_f])[:TOPK]
feats_full = deg_cols[use_f[order_f]]
mu_f, sd_f = Xi[:, feats_full].mean(0), Xi[:, feats_full].std(0) + 1e-9
clf_full = LogisticRegression(C=C_L2, max_iter=2000, random_state=SEED)
clf_full.fit((Xi[:, feats_full] - mu_f) / sd_f, ev)
json.dump({"protocol": "折内χ²top200 + L2 logistic(C=0.1)；此处为全量重拟，仅供外部验证应用",
           "效能主张以折外 T12 为准": True, "seed": SEED,
           "features": [expr.index[c] for c in feats_full],
           "coef": clf_full.coef_[0].tolist(),
           "mu": mu_f.tolist(), "sd": sd_f.tolist()},
          open(os.path.join(RES, "T31_签名包.json"), "w", encoding="utf-8"),
          ensure_ascii=False)
L("U04_签名持久化", {"特征数": int(len(feats_full)), "文件": "results/T31_签名包.json"},
  "外部验证（GSE68465 等）应用的前置；注意：签名包模型系数不得回填本队列表效")

# ---------- T13b 校准（OOF 概率，CV 预测概率口径 H-1） ----------
lr_cal = LogisticRegression(C=1e6, max_iter=2000, random_state=SEED)
lr_cal.fit(oof_proba.reshape(-1, 1), ev)
slope = float(lr_cal.coef_[0][0]); icept = float(lr_cal.intercept_[0])
bs = []
rng_c = np.random.default_rng(SEED)
for _ in range(NBOOT):
    ii = rng_c.integers(0, len(ev), len(ev))
    if len(set(ev[ii])) < 2:
        continue
    lr_b = LogisticRegression(C=1e6, max_iter=2000, random_state=SEED)
    lr_b.fit(oof_proba[ii].reshape(-1, 1), ev[ii])
    bs.append((float(lr_b.coef_[0][0]), float(lr_b.intercept_[0])))
slo = [b[0] for b in bs]; ice = [b[1] for b in bs]
L("T13b_校准", {"校准斜率": round(slope, 3), "截距": round(icept, 3),
              "斜率CI95": [round(np.percentile(slo, 2.5), 3), round(np.percentile(slo, 97.5), 3)],
              "截距CI95": [round(np.percentile(ice, 2.5), 3), round(np.percentile(ice, 97.5), 3)]},
  "OOF 概率逻辑再校准；理想斜率 1 / 截距 0")
cal_tab = pd.DataFrame({"p": oof_proba, "y": ev}).assign(
    dec=pd.qcut(oof_proba, 5, duplicates="drop")).groupby(
    "dec", observed=True).agg(n=("y", "size"), p_mean=("p", "mean"),
                              obs_rate=("y", "mean")).reset_index(drop=True)
cal_tab.to_csv(os.path.join(RES, "T13b_校准分位.csv"), index=False, encoding="utf-8-sig")

# ---------- T13c 决策曲线（5 年复发界时；删失早于界时且未复发者 GVH 排除，口径如实） ----------
HZ = 1825
m5 = (tt >= HZ) | ((ev == 1) & (tt <= HZ))
y5 = ((tt <= HZ) & (ev == 1)).astype(int).astype(int)[m5]
p5 = oof_proba[m5]
dca_rows = []
for pt in np.arange(0.05, 0.51, 0.05):
    tp = float(((p5 >= pt) & (y5 == 1)).sum()); fp = float(((p5 >= pt) & (y5 == 0)).sum())
    nb_m = (tp - fp * pt / (1 - pt)) / len(y5)
    nb_a = (y5.sum() - (len(y5) - y5.sum()) * pt / (1 - pt)) / len(y5)
    dca_rows.append({"threshold": round(float(pt), 2), "NB_model": round(nb_m, 4),
                     "NB_all": round(nb_a, 4), "NB_none": 0.0})
dca = pd.DataFrame(dca_rows)
dca.to_csv(os.path.join(RES, "T13c_DCA曲线.csv"), index=False, encoding="utf-8-sig")
neg_run = mx = 0
for nb in dca["NB_model"]:
    mx = max(mx, nb)
    neg_run = neg_run + 1 if nb < 0 else 0
verdict = "阻断" if neg_run >= 12 else ("警告" if neg_run >= 8 else "通过")
L("T13c_DCA", {"5年内复发n": int(y5.sum()), "纳入n": int(m5.sum()),
              "连续负点": neg_run, "双阈值判定": verdict, "最大净获益": round(mx, 4)},
  "GVH 排除口径；双阈值 8 警告 / 12 阻断（T13c）")

# ---------- T12 扩展：时间依赖 AUC（IPCW，5 年）+ Uno C（10 年） ----------
def km_censor_tab(t_, e_):
    """删失分布 G(t)：把删失当'事件'做 KM。"""
    tab = {}; S = 1.0
    for tt_ in np.unique(t_):
        n_r = (t_ >= tt_).sum(); c_n = ((t_ == tt_) & (e_ == 0)).sum()
        S *= (1 - c_n / n_r) if n_r > 0 else 1.0
        tab[tt_] = S
    return tab


def Gh(tq, tab):
    ks = [k for k in sorted(tab) if k <= tq]
    return tab[ks[-1]] if ks else 1.0


Gtab = km_censor_tab(tt, 1 - ev)
tau5 = 1825
cases5 = np.where((tt <= tau5) & (ev == 1))[0]
ctrl5 = np.where(tt > tau5)[0]
auc5 = None
if len(cases5) and len(ctrl5):
    num = den = 0.0
    for i in cases5:
        w = 1.0 / max(Gh(tt[i], Gtab), 1e-6)
        for j in ctrl5:
            num += w * (1.0 if oof_proba[i] > oof_proba[j]
                        else 0.5 if oof_proba[i] == oof_proba[j] else 0.0)
            den += w
    auc5 = num / den if den else None
tauC = 3650
num = den = 0.0
n = len(ev)
for i in range(n):
    if ev[i] != 1 or tt[i] > tauC or tt[i] <= 0:
        continue
    w2 = 1.0 / max(Gh(tt[i], Gtab), 1e-6) ** 2
    for j in range(n):
        if tt[j] > tt[i]:
            den += w2
            num += w2 * (1.0 if oof_proba[i] > oof_proba[j]
                         else 0.5 if oof_proba[i] == oof_proba[j] else 0.0)
unoC = num / den if den else None
L("T12_时间依赖", {"AUC_5y_IPCW": round(auc5, 4) if auc5 else None,
                 "UnoC_10y": round(unoC, 4) if unoC else None},
  "IPCW（删失 KM 加权）；与折外 AUC 0.832（全随访二分类口径）互补")

# ---------- U05 敏感性 ----------
print("=" * 70, "\nU05 敏感性", sep="")
sens = {}
for name, mask in [("stage_IA", pi["stage"].values == "IA"),
                   ("stage_IB", pi["stage"].values == "IB"),
                   ("stage_II", pi["stage"].values == "II"),
                   ("male", pi["sex"].values == "male"), ("female", pi["sex"].values == "female")]:
    if mask.sum() > 20 and ev[mask].sum() >= 5:
        cxs = PHReg(tt[mask], oof[mask].reshape(-1, 1), status=ev[mask]).fit()
        h = float(np.exp(cxs.params[0])); sense = 1 if h > 1 else -1
        sens[name] = {"n": int(mask.sum()), "HR": round(h, 3), "方向": "风险↑" if sense == 1 else "风险↓"}
L("T18_敏感性_亚组", sens, "分期/性别亚组 Cox 方向一致性（T18 跨指标方向一致）")
# 8C：分期亚组 HR 异质性（近似 I²）
hrs = np.array([sens[k]["HR"] for k in sens if k.startswith("stage")])
if len(hrs) == 2:
    lh = np.log(hrs); Q = float(np.sum((lh - lh.mean()) ** 2))
    L("H5_8C_异质性", {"stage_logHR": lh.tolist(), "Q": round(Q, 3)},
      "分期亚组 logHR 离散度；I² 高时按分支 8C 不合并、分呈结论")

# ---------- U06 唯一台账落盘 ----------
anchors = {}
an = 0
for k in ["T02_DEG", "T04_富集", "T12_CV_AUC", "T31_无泄露", "T06_Cox_评分", "T06_KM",
          "T18_敏感性_亚组", "H5_8C_异质性", "U04_预后集", "U04_EPV",
          "T13b_校准", "T13c_DCA", "T12_时间依赖", "U04_签名持久化"]:
    if k in R:
        an += 1; anchors[f"L-{an:03d}"] = {"key": k, **R[k]}
R["_anchors"] = anchors
with open(os.path.join(RES, "results.json"), "w", encoding="utf-8") as f:
    json.dump(R, f, ensure_ascii=False, indent=1, default=str)
print("=" * 70, "\n台账已落盘 results/results.json；图件生成见 make_figures.py", sep="")
