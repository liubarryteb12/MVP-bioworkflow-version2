#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
休眠判据激活分支(branch22) —— v2.21 新增

起因(L2 判据消融的直接产物):
    消融统计出 T03 / T09 / T12 / T18 / WP-9 五条判据
    **在 criteria.yaml 里有 predicate、有 on_fail,但从未被任何判定项触发**
    —— 即"休眠判据"(审核 §2 定义:direct=0 且 branch=0)。

为什么必须激活而不是标记:
    框架铁律"无具体坑的规则不立"。一条从未被验证的判据有两种可能:
      ① 它的坑真实存在,只是没人写验证 → 应补验证
      ② 它的坑已被别的判据覆盖 → 应合并或删除
    无论哪种,**"休眠"都不是可接受终态** —— 它与第 11 条陷阱同源:
    判据在那里、条文完整、看起来完备,但从未真正拦过任何东西。

本分支为 T03/T09/T12/T18 各建夹具,双向验证(违规应拦 / 合规应放行)。
WP-9 由 export_guard.py 验证(独立脚本,落盘 writing/export 报告)。

设计纪律:
  - 每条判据至少 1 个"应拦"用例 + 1 个"应放行"用例
  - 违规未拦 = 空规 → 该判据判 FAIL(不是判据本身 FAIL,是本分支自检 FAIL)
  - blocking=False 的判据(T12)违规时判 warn,不是 fail —— 尊重原判据语义
"""


# ---------------------------------------------------------------- T03
def check_T03(pvalues, declared_family, actual_family, method="BH"):
    """T03 多重检验校正范围:声明的家族与执行的家族必须一致。

    坑:声明"全基因组校正",实际只对差异基因子集做 BH —— 校正范围被
       悄悄缩小,假阳性率高于声称值。这是富集分析/差异分析的高频退修点。
    """
    if declared_family is None or actual_family is None:
        return "na", "未声明校正家族"
    if method not in ("BH", "Bonferroni", "FDR", "none"):
        return "fail", f"未知校正方法 {method}"
    d, a = int(declared_family), int(actual_family)
    if a > d:
        return "fail", f"实际校正家族({a})大于声明({d}),方向异常"
    if a < d:
        # 实际校正的假设数少于声明 → 校正范围被缩小
        return "fail", (f"实际校正 {a} 个假设,但声明 {d} 个 —— "
                        f"校正范围被缩小,声称的 FDR 不成立")
    return "pass", f"声明与执行一致({d})"


# ---------------------------------------------------------------- T09
def check_T09(source, declared):
    """T09 预测概率来源声明:source 必须声明且不得为 insample。

    坑:用样本内拟合概率做校准/DCA —— 训练内斜率恒等于 1(未正则化
       logistic),校准永远"合格"。这是 H-1 的判据化。
    """
    if not declared:
        return "na", "未声明预测概率来源(不得默认为样本内)"
    s = str(source).lower()
    if s in ("insample", "in-sample", "train", "training", "样本内"):
        return "fail", "预测概率来自样本内 — 训练内校准斜率恒≈1,判据形同虚设"
    if s in ("cv", "cross-validation", "nested_cv", "holdout",
             "independent", "external"):
        return "pass", f"来源已声明且为样本外({source})"
    return "na", f"未识别的来源标注 '{source}' — 须明确到 cv/holdout/external"


# ---------------------------------------------------------------- T12
def check_T12(acc_insample, auc_outsample):
    """T12 过拟合警示:样本内高准确率 + 样本外显著下降 → 须标注。

    ★ blocking=False:本判据只要求"强制标注",不阻断。
      夹具判定期望值为 warn,不是 fail —— 尊重原判据语义,
      否则会把"应警告"误判为"应阻断",是判据语义的越界改写。
    """
    try:
        ai = float(acc_insample)
        ao = float(auc_outsample)
    except (TypeError, ValueError):
        return "na", "缺样本内准确率或样本外 AUC"
    if ai > 0.95 and (ai - ao) > 0.05:
        return "warn", (f"样本内 {ai:.3f} vs 样本外 {ao:.3f},落差 "
                        f"{ai - ao:.3f} > 0.05 — 须强制标注过拟合警示")
    return "pass", f"落差 {ai - ao:.3f} 在容差内"


# ---------------------------------------------------------------- T18
def check_T18(preregistered, reported):
    """T18 敏感性分析:预注册的变体必须全部报告。

    坑:预注册 4 个变体,只报告"最好看"的 2 个 —— 选择性报告,
       是硬阻断条款(blocking=True)。
    """
    if not preregistered:
        return "na", "未预注册敏感性分析变体"
    pre = set(str(x) for x in preregistered)
    rep = set(str(x) for x in (reported or []))
    missing = sorted(pre - rep)
    if missing:
        return "fail", (f"预注册 {len(pre)} 个变体,仅报告 {len(rep)} 个;"
                        f"缺:{','.join(missing)} — 选择性报告")
    extra = sorted(rep - pre)
    if extra:
        return "warn", f"报告了未预注册的变体:{','.join(extra)} — 须声明为探索性"
    return "pass", f"预注册 {len(pre)} 个变体全部报告"


# ---------------------------------------------------------------- 夹具
def branch22_dormant(L):
    """为休眠判据 T03/T09/T12/T18 建双向夹具。

    每条至少:违规应拦 + 合规应放行。
    末项自检:任一"应拦"用例未拦 → 本分支判 FAIL(空规暴露)。
    """
    sect = "分支 22 · 休眠判据激活(T03/T09/T12/T18)"

    expect = []   # (标签, 期望状态)

    # ---- T03 ----
    st, det = check_T03([0.01] * 100, declared_family=20000,
                        actual_family=20000)
    L.add("22", "[T03] 合规:声明与执行一致(20000)", st, "pass", st == "pass",
          det)
    expect.append(("T03-合规", "pass", st))

    st, det = check_T03([0.01] * 100, declared_family=20000,
                        actual_family=500)
    L.add("22", "[T03] 声明全基因组却只校正 500 个:应拦", st, "fail",
          st == "fail", det)
    expect.append(("T03-缩小范围", "fail", st))

    st, det = check_T03([0.01] * 100, declared_family=None,
                        actual_family=500)
    L.add("22", "[T03] 未声明家族:应判不适用", st, "na", st == "na", det)
    expect.append(("T03-未声明", "na", st))

    # ---- T09 ----
    st, det = check_T09("cv", declared=True)
    L.add("22", "[T09] 合规:声明 CV 概率", st, "pass", st == "pass", det)
    expect.append(("T09-合规", "pass", st))

    st, det = check_T09("insample", declared=True)
    L.add("22", "[T09] 声明样本内概率:应拦", st, "fail", st == "fail", det)
    expect.append(("T09-样本内", "fail", st))

    st, det = check_T09("cv", declared=False)
    L.add("22", "[T09] 未声明来源:应判不适用", st, "na", st == "na", det)
    expect.append(("T09-未声明", "na", st))

    # ---- T12(blocking=False → 期望 warn,不是 fail)----
    st, det = check_T12(0.80, 0.78)
    L.add("22", "[T12] 合规:落差 0.02", st, "pass", st == "pass", det)
    expect.append(("T12-合规", "pass", st))

    st, det = check_T12(1.000, 0.544)
    L.add("22", "[T12] 样本内 1.000 / 样本外 0.544:应警告", st, "warn",
          st == "warn", det)
    expect.append(("T12-过拟合", "warn", st))

    st, det = check_T12(None, 0.7)
    L.add("22", "[T12] 缺样本内指标:应判不适用", st, "na", st == "na", det)
    expect.append(("T12-缺输入", "na", st))

    # ---- T18 ----
    st, det = check_T18(["A", "B", "C", "D"], ["A", "B", "C", "D"])
    L.add("22", "[T18] 合规:4 个变体全报", st, "pass", st == "pass", det)
    expect.append(("T18-合规", "pass", st))

    st, det = check_T18(["A", "B", "C", "D"], ["A", "B"])
    L.add("22", "[T18] 预注册 4 个仅报 2 个:应拦", st, "fail", st == "fail",
          det)
    expect.append(("T18-选择性报告", "fail", st))

    st, det = check_T18(["A", "B"], ["A", "B", "E"])
    L.add("22", "[T18] 报告未预注册变体:应警告", st, "warn", st == "warn", det)
    expect.append(("T18-额外变体", "warn", st))

    st, det = check_T18([], [])
    L.add("22", "[T18] 未预注册:应判不适用", st, "na", st == "na", det)
    expect.append(("T18-未预注册", "na", st))

    # ---- 空规自检:所有"应拦"用例必须真的被拦 ----
    missed = [f"{n}(期望{e},实得{g})" for n, e, g in expect if g != e]
    L.add("22", "T03/T09/T12/T18 夹具全部按预期拦截或放行(无空规)",
          "无偏差" if not missed else ";".join(missed),
          "无偏差", not missed, criteria="GLOBAL")
    return sect


if __name__ == "__main__":
    import sys
    sys.path.insert(0, ".")
    from verify_all import Ledger, sect as _sect
    L = Ledger()
    _sect(branch22_dormant(L))
    print(f"\n  pass={L.npass} fail={L.nfail} na={L.nna}")
    sys.exit(1 if L.nfail else 0)
