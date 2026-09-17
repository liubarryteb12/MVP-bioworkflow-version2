#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
T36 · 多组件整合的增量消融(branch23) —— v2.21 新增

起因(审核 §3 对 v2.20 的裁定):
    "T31 判『特征集内部是否冗余』(静态),T36 判『组件之间是否有增益』(动态)。
     二者决策依据不同:T31 看相关系数,T36 看 ΔAUC —— 不能并入。"

    v2.20 的 13 篇文献里至少 3 篇中招:
      - ROMO1(多组学整合)
      - p53(scRNA + scATAC + 空间 + WGS 四组学)
      - Lage-Rupprecht(knowledge graph + in vitro)
    三篇都声称"整合有用",**都没做消融**。

核心判据:
    (a) 全组件模型性能
    (b) 每个组件的单组件性能(leave-one-in)
    (c) 移除每个组件后的 Δ性能(leave-one-out)
    (d) 移除某组件后 Δ < 阈值 且 CI 跨 0 → 该组件无贡献
    (e) 某组件无贡献但仍声称"整合了 N 个组学" → R5 回退

与 T31 的分工(必须写清,否则会被误合并):
    T31 —— 静态:选中特征集**内部**的相关系数 / 冗余度
    T36 —— 动态:组件**之间**的增量增益(ΔAUC / ΔC-index)

设计纪律:
  - 不得默认"整合一定有用" —— 那是循环论证
  - 缺消融证据即判"不完整",不是"通过"
  - CI 跨 0 的组件不得声称有贡献
"""


def check_T36(components, perf_full, perf_single, perf_loo,
              delta_threshold=0.01, ci_lo=None, ci_hi=None):
    """多组件整合的增量消融。

    参数
    ----
    components   : list[str] 组件名(组学 / 算法 / 特征集)
    perf_full    : float     全组件性能(AUC / C-index)
    perf_single  : dict      {组件名: 单组件性能}
    perf_loo     : dict      {组件名: 移除该组件后的性能}
    delta_threshold : float  判定"有贡献"的最小增量(默认 0.01)
    ci_lo/ci_hi  : dict      {组件名: (lo, hi)} Δ 的置信区间;可为空

    返回 (status, detail, per_component)
        status: pass / warn / fail / na
    """
    if not components or len(components) < 2:
        return "na", "单组件研究,不触发多组件消融", {}
    if perf_full is None:
        return "na", "缺全组件性能", {}

    miss_single = [c for c in components if c not in (perf_single or {})]
    miss_loo = [c for c in components if c not in (perf_loo or {})]
    if miss_single or miss_loo:
        return "fail", (
            "消融不完整:缺 leave-one-in(%s) 或 leave-one-out(%s) —— "
            "只报全组件性能不能证明整合有增益"
            % (",".join(miss_single) or "无", ",".join(miss_loo) or "无")), {}

    per = {}
    no_gain = []
    for c in components:
        delta = float(perf_full) - float(perf_loo[c])
        lo = hi = None
        if ci_lo and c in ci_lo:
            lo = float(ci_lo[c])
        if ci_hi and c in ci_hi:
            hi = float(ci_hi[c])
        cross0 = (lo is not None and hi is not None and lo < 0 < hi)
        gain = (delta >= delta_threshold) and not cross0
        per[c] = dict(delta=round(delta, 4), ci=(lo, hi), crosses_zero=cross0,
                      has_gain=gain, single=perf_single.get(c))
        if not gain:
            no_gain.append(c)

    if len(no_gain) == len(components):
        return "fail", (
            "全部 %d 个组件均无显著增量 —— '整合带来增益'不成立;"
            "若仍声称整合有用即为循环论证" % len(components)), per
    if no_gain:
        return "warn", (
            "组件 %s 无显著增量(Δ<%s 或 CI 跨 0),须声明其贡献有限,"
            "不得统称为'多组学整合带来提升'" % (",".join(no_gain),
                                        delta_threshold)), per
    return "pass", ("全部 %d 个组件均有增量(Δ≥%s 且 CI 不跨 0)"
                    % (len(components), delta_threshold)), per


def branch23_component_ablation(L):
    """T36 夹具:三篇文献中招场景 + 合规对照。"""
    expect = []

    def _run(tag, exp, **kw):
        st, det, per = check_T36(**kw)
        L.add("23", "[T36] " + tag, st, exp, st == exp, det)
        expect.append((tag, exp, st))
        return st, det, per

    # ---- 文献夹具:ROMO1(多组学整合,未做消融)----
    _run("ROMO1 多组学:只报全组件性能,无消融 → 应拦", "fail",
         components=["转录组", "蛋白组", "MR"], perf_full=0.812,
         perf_single={"转录组": 0.74}, perf_loo={})

    # ---- p53 四组学,同病 ----
    _run("p53 四组学:缺 leave-one-out → 应拦", "fail",
         components=["scRNA", "scATAC", "空间", "WGS"], perf_full=0.79,
         perf_single={"scRNA": 0.70}, perf_loo={"scRNA": 0.77})

    # ---- 合规:全部组件有增量 ----
    _run("合规:三组件均有增量且 CI 不跨 0", "pass",
         components=["转录组", "蛋白组", "临床"], perf_full=0.85,
         perf_single={"转录组": 0.72, "蛋白组": 0.68, "临床": 0.70},
         perf_loo={"转录组": 0.80, "蛋白组": 0.79, "临床": 0.81},
         ci_lo={"转录组": 0.02, "蛋白组": 0.03, "临床": 0.02},
         ci_hi={"转录组": 0.08, "蛋白组": 0.09, "临床": 0.06})

    # ---- 一个组件无贡献(CI 跨 0)→ warn ----
    _run("一个组件 CI 跨 0 → 应警告", "warn",
         components=["转录组", "蛋白组", "临床"], perf_full=0.85,
         perf_single={"转录组": 0.72, "蛋白组": 0.68, "临床": 0.70},
         perf_loo={"转录组": 0.80, "蛋白组": 0.845, "临床": 0.81},
         ci_lo={"转录组": 0.02, "蛋白组": -0.01, "临床": 0.02},
         ci_hi={"转录组": 0.08, "蛋白组": 0.02, "临床": 0.06})

    # ---- 全部无贡献 → fail ----
    _run("全部组件无增量 → 应拦(循环论证)", "fail",
         components=["A", "B"], perf_full=0.70,
         perf_single={"A": 0.69, "B": 0.68},
         perf_loo={"A": 0.698, "B": 0.699},
         ci_lo={"A": -0.005, "B": -0.006},
         ci_hi={"A": 0.007, "B": 0.008})

    # ---- N/A ----
    _run("单组件研究 → 应判不适用", "na",
         components=["转录组"], perf_full=0.74,
         perf_single={"转录组": 0.74}, perf_loo={})

    # ---- 空规自检 ----
    missed = [f"{n}(期望{e},实得{g})" for n, e, g in expect if g != e]
    L.add("23", "T36 夹具全部按预期拦截或放行(无空规)",
          "无偏差" if not missed else ";".join(missed), "无偏差",
          not missed)
    return "分支 23 · 多组件整合增量消融(T36)"


if __name__ == "__main__":
    import sys
    sys.path.insert(0, ".")
    from verify_all import Ledger, sect
    L = Ledger()
    sect(branch23_component_ablation(L))
    print(f"\n  pass={L.npass} fail={L.nfail} na={L.nna}")
    sys.exit(1 if L.nfail else 0)
