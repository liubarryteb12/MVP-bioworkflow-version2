#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""文献实证缺口判据 T21–T25(branch16)。

来源:用户提供的 23 篇已发表论文。本模块不验证这些论文的"科学正确性",
只把其中**客观可查的数字/做法**当作夹具(fixture),检验框架判据
在真实生信实践中的拦截能力。

铁律:无具体坑的规则不立。每条判据都锚定一篇文献里的具体数字或做法。

判据:
  T21 组别样本量下限与平衡     ← 文献17 Table1(RA 16 vs 4)
  T22 训练-外部验证性能落差    ← 文献18(训练AUC .666 / 验证 .560)
  T23 多数据集 QC 阈值一致性   ← 文献19(2.5% vs 5%/25%)
  T24 验证集独立性(数据泄露)   ← 文献19(跨物种验证优先)
  T25 空间/ROI 选择盲法        ← 文献21(手动选) vs 文献19(盲法)
"""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ---------------------------------------------------------------- T21
# ★ v2.16 修订:原为二值,导致 n=6 恰卡下界被判 PASS(夹具 T1D 10v6 暴露)。
# 小样本是**连续风险**,不是阈值开关。改为三态(与 H-2 双阈值同构):
#   fail : min < 6            —— 功效不足,禁止据此下结论
#   warn : 6 <= min < 10      —— 灰区,须显式声明小样本并做敏感性分析
#   pass : min >= 10 且组比<=4
T21_FAIL_N = 6        # 低于此 → fail
T21_WARN_N = 10       # 低于此 → 灰区(不得直接判通过)
T21_MAX_RATIO = 4.0   # 最大组 / 最小组


def check_T21(group_sizes):
    """组别样本量下限与平衡(三态)。

    坑(文献17 Table1):RA 16 vs 4(对照仅4例)、T1D 10 vs 6(临界)。
    在其上做 limma DGE + BH 校正,功效极低却照常报告"显著差异"。
    """
    if not group_sizes:
        return "fail", "空", "未提供分组样本量"
    mn, mx = min(group_sizes), max(group_sizes)
    ratio = (mx / mn) if mn else float("inf")
    obs = f"min={mn},max={mx},ratio={ratio:.2f}"
    det = []
    if mn < T21_FAIL_N:
        det.append(f"最小组 n={mn} < {T21_FAIL_N}(功效不足)")
    if ratio > T21_MAX_RATIO:
        det.append(f"组比 {ratio:.2f} > {T21_MAX_RATIO}(严重不平衡)")
    if det:
        return "fail", obs, "; ".join(det)
    if mn < T21_WARN_N:
        return "warn", obs, (
            f"最小组 n={mn} 落在灰区[{T21_FAIL_N},{T21_WARN_N}),"
            f"须声明小样本并做敏感性分析,不得直接判通过")
    return "pass", obs, "样本量与平衡性充足"


# ---------------------------------------------------------------- T22
T22_MAX_DROP = 0.10   # 训练→外部验证 AUC 最大允许落差
T22_MIN_EXT = 0.60    # 外部验证 AUC 下限


def check_T22(auc_train, auc_ext):
    """训练-外部验证性能落差。

    坑(文献18):训练集 AUC 0.666,外部验证 AUC 0.560(落差 0.106),
    C-index 0.631(95%CI 0.580–0.652),论文仍称"confirmed predictivity"。
    落差被"验证集存在"这一事实掩盖 —— 有验证集 ≠ 泛化。
    """
    if auc_train is None or auc_ext is None:
        return False, "缺失", "缺少训练集或外部验证集 AUC"
    drop = auc_train - auc_ext
    ok_drop = drop <= T22_MAX_DROP
    ok_ext = auc_ext >= T22_MIN_EXT
    obs = f"train={auc_train},ext={auc_ext},drop={drop:.3f}"
    det = []
    if not ok_drop:
        det.append(f"落差 {drop:.3f} > {T22_MAX_DROP}(泛化衰减过大)")
    if not ok_ext:
        det.append(f"外部验证 AUC {auc_ext} < {T22_MIN_EXT}(接近随机)")
    return (ok_drop and ok_ext), obs, "; ".join(det) or "泛化稳定"


# ---------------------------------------------------------------- T23
def check_T23(qc_thresholds, rationale=""):
    """多数据集/多模态 QC 阈值一致性。

    坑(文献19):自产 snRNA 用 >2.5% mito 过滤;公共数据 GSE243981
    用 5%(snRNA)与 25%(scRNA)。阈值不同**本身是合理的**(模态不同),
    但必须声明理由;若静默使用不同阈值,读者无法判断差异来自生物学还是 QC。
    """
    vals = sorted({round(float(v), 4) for v in qc_thresholds})
    same = len(vals) <= 1
    if same:
        return True, f"统一={vals[0] if vals else 'NA'}", "阈值统一"
    has_r = bool((rationale or "").strip())
    obs = f"不同阈值={vals}"
    if has_r:
        return True, obs, f"阈值不同但已声明理由:{rationale.strip()[:40]}"
    return False, obs, f"阈值不同({vals})且未声明理由"


# ---------------------------------------------------------------- T24
def check_T24(same_cohort: bool, independent: bool = False):
    """验证集独立性(数据泄露)。

    坑/正例(文献19):明确写"To avoid potential data leakage artifacts
    inherent to train-test splits within our specific mouse cohort,
    we prioritized cross-species validation"。
    同一队列内随机 split 会泄露批次/个体信息,使验证 AUC 虚高。
    """
    if independent:
        return True, "独立队列/跨物种", "验证集独立于训练集"
    if same_cohort:
        return False, "同队列 split", "验证集与训练集同队列(存在数据泄露风险)"
    return False, "未声明", "未声明验证集来源独立性"


# ---------------------------------------------------------------- T25
def check_T25(roi_method: str, blinded: bool = False,
              preregistered: bool = False):
    """空间/ROI 选择的盲法或客观标准。

    坑(文献21):"we manually selected by location the hippocampal
    subfields" —— 手动按位置选 ROI,且选区者知道分组时存在选择偏倚。
    正例(文献19):"the region selector was blinded to the tissue
    samples' genotype origin" —— 盲法选区。
    """
    if blinded or preregistered:
        tag = "盲法" if blinded else "预注册客观标准"
        return True, f"{roi_method}/{tag}", f"ROI 选择采用{tag}"
    return False, f"{roi_method}/非盲", (
        f"ROI 选择为'{roi_method}'且未盲法、未预注册(选择偏倚风险)")


# ================================================================ 夹具
# (来源, 判据, kwargs, 期望 passed, 备注)
FIXTURES = [
    # --- T21:文献17 真实分组(三态) ---
    ("文献17 Table1 RA(16 vs 4)", "T21",
     dict(group_sizes=[16, 4]), "fail", "对照组仅4例,功效不足→拦"),
    ("文献17 Table1 T1D(10 vs 6)", "T21",
     dict(group_sizes=[10, 6]), "warn", "n=6落灰区,须声明不得直判通过"),
    ("文献17 Table1 MS(99 vs 45)", "T21",
     dict(group_sizes=[99, 45]), "pass", "平衡且充足(合规对照)"),
    ("合规对照(50 vs 50)", "T21",
     dict(group_sizes=[50, 50]), "pass", "平衡"),

    # --- T22:文献18 真实 AUC ---
    ("文献18 训练.666/验证.560", "T22",
     dict(auc_train=0.666, auc_ext=0.560), "fail",
     "落差0.106>0.10且验证0.560<0.60"),
    ("合规对照(0.80/0.78)", "T22",
     dict(auc_train=0.80, auc_ext=0.78), "pass", "落差0.02,泛化稳定"),

    # --- T23:文献19 QC 阈值(有/无声明) ---
    ("文献19 QC(2.5/5/25%,有声明)", "T23",
     dict(qc_thresholds=[2.5, 5, 25], rationale="不同模态(snRNA vs scRNA)"),
     "pass", "阈值不同但已声明理由"),
    ("文献19 变体(阈值不同,无声明)", "T23",
     dict(qc_thresholds=[2.5, 5, 25], rationale=""), "fail",
     "同文献做法但缺声明→应拦"),
    ("合规对照(统一2.5%)", "T23",
     dict(qc_thresholds=[2.5, 2.5]), "pass", "阈值统一"),

    # --- T24:文献19 跨物种 vs 同队列 ---
    ("文献19 跨物种验证(mouse→human)", "T24",
     dict(same_cohort=False, independent=True), "pass", "独立队列,正确做法"),
    ("同队列随机split(典型泄露)", "T24",
     dict(same_cohort=True, independent=False), "fail", "应拦数据泄露"),

    # --- T25:文献21 手动 vs 文献19 盲法 ---
    ("文献21 手动按位置选ROI", "T25",
     dict(roi_method="manually selected by location", blinded=False),
     "fail", "非盲手动选区,应拦"),
    ("文献19 盲法选区", "T25",
     dict(roi_method="blinded region selector", blinded=True),
     "pass", "盲法,正确做法"),
]

CHECKERS = {
    "T21": check_T21,
    "T22": check_T22,
    "T23": check_T23,
    "T24": check_T24,
    "T25": check_T25,
}


VLABEL = {"pass": "PASS", "warn": "灰区(不得判通过)", "fail": "FAIL"}


def run_fixtures():
    """返回 [(来源, 判据, 期望, 实际, 观测, 说明, 符合?)]"""
    out = []
    for src, cid, kw, expect, note in FIXTURES:
        got_raw, obs, det = CHECKERS[cid](**kw)
        # 统一为三态 verdict(T21 原生三态,其余由 bool 归一)
        got = got_raw if isinstance(got_raw, str) else (
            "pass" if got_raw else "fail")
        out.append((src, cid, expect, got, obs, det, got == expect))
    return out


def branch16_literature(L):
    """把文献夹具跑进台账。

    台账记的是**判据有效性**(实际verdict 是否等于期望),
    而非"论文是否合格" —— 后者由 verdict 本身表达(见 detail)。
    若某条文献**违规项**被判 PASS → 判据空规(与第11条陷阱同族)。
    """
    rows = run_fixtures()
    for src, cid, expect, got, obs, det, match in rows:
        L.add("16", f"[{cid}] {src}", f"实际={VLABEL[got]}",
              f"期望={VLABEL[expect]}", match, detail=f"{obs} | {det}")
    n_warn = sum(1 for r in rows if r[3] == "warn")
    L.add("16", "灰区项数(T21 小样本临界,须声明)", n_warn,
          ">=1(夹具含 T1D 10v6)", n_warn >= 1,
          detail="灰区=不得直接判通过,须声明小样本+敏感性分析", criteria="T21")
    bad = [r[0] for r in rows if not r[6]]
    L.add("16", "文献夹具全部按预期拦截/放行(无空规)",
          bad or "全部符合", "全部符合", not bad, criteria="GLOBAL")
    return rows


if __name__ == "__main__":
    print("=== 文献实证夹具 T21–T25(三态) ===")
    rows = run_fixtures()
    for src, cid, expect, got, obs, det, match in rows:
        flag = "OK " if match else "XX "
        print(f"{flag}[{cid}] {src}\n"
              f"     期望={VLABEL[expect]:<14} 实际={VLABEL[got]:<14}"
              f" | {obs} | {det}")
    bad = [r for r in rows if not r[6]]
    nw = sum(1 for r in rows if r[3] == "warn")
    print(f"\n合计 {len(rows)} 条,符合 {len(rows)-len(bad)},"
          f"不符合 {len(bad)},灰区 {nw}")
    raise SystemExit(1 if bad else 0)
