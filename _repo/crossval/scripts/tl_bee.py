#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""T13b 小样本误差估计扩展的**脚本验证**(branch20b)。

来源:Maddouri et al.《Robust importance sampling for error estimation in the
     context of optimal Bayesian transfer learning》(Patterns 3, 100428)

★ 为何补:criteria.yaml 的 T13b.small_sample_extension 此前**只有条文**。
  按框架自身铁律(branch15):"只有条文、无脚本验证 = 空规风险"。
  该条文要求:
    - 目标域 n < 50 时须声明是否借用源域信息
    - 若借用,须报告相关度 |alpha| 及其**确定方法**
    - 若 alpha 系"看着结果调出来的" → R3 回退

  本脚本验证的是**最后这条**:alpha 事后调到底会不会让误差估计偏。
  用可复现的数值反例,而不是断言。

★ 诚实边界:这里**不是** TL-BEE 的完整实现(那需要贝叶斯后验
  + importance sampling + control variates)。这里验证的是该条文的
  **可判定部分**:alpha 的来源是否预注册。
"""
import numpy as np

N_SMALL = 50          # 触发阈值:目标域 n < 50
ALPHA_MIN, ALPHA_MAX = 0.0, 1.0


def check_T13b_ext(n_target, used_source_info=None, alpha=None,
                   alpha_predetermined=None, na_reason=None):
    """T13b 小样本扩展的声明检查(三态)。

    pass : 已声明是否借用 + (借用时)alpha 及其确定方法均已预注册
    fail : 借用源域但 alpha 事后调 / alpha 缺失 / 超阈值未声明
    na   : 目标域 n >= 50(不触发)或 N/A 带理由
    """
    if n_target >= N_SMALL and used_source_info is None:
        return "na", f"n={n_target}", (
            f"目标域 n={n_target} >= {N_SMALL} → 不触发小样本扩展条款")
    if na_reason:
        return "na", f"n={n_target}", na_reason

    obs, det, status = [], [], "pass"

    if used_source_info is None:
        return ("na", f"n={n_target}",
                f"目标域 n={n_target} < {N_SMALL} 但未声明是否借用源域信息"
                " → **判不了**(不得默认为'未借用')")

    obs.append(f"借用源域={used_source_info}")
    if used_source_info:
        if alpha is None:
            status = "fail"
            det.append("声明借用源域信息但未报告相关度 |alpha|")
        else:
            obs.append(f"alpha={alpha}")
            if not (ALPHA_MIN <= alpha <= ALPHA_MAX):
                status = "fail"
                det.append(f"alpha={alpha} 超出 [0,1]")
        if alpha_predetermined is None:
            status = "fail" if status == "pass" else status
            det.append("未声明 alpha 的**确定方法**")
        elif not alpha_predetermined:
            status = "fail"
            det.append("alpha 系'看着结果调出来的' → **R3 回退**"
                       "(等于把结论塞进先验)")
        else:
            obs.append("alpha 预注册=True")
    else:
        det.append("声明未借用源域信息 → 无 alpha 要求")
    if not det:
        det.append("小样本扩展声明齐全")
    return status, ",".join(obs) or "无", "; ".join(det)


# ------------------------------------------------------------ 数值反例
def alpha_gaming_demo(n_target=20, n_source=500, seed=0,
                      eps_target=0.30, eps_source=0.10,
                      target_want=0.05):
    """演示:alpha 事后调会把误差估计拽向研究者想要的值。

    eps_hat(alpha) = (1-alpha) * eps_hat_target + alpha * eps_source
      - 真值 = eps_target(目标域真实错误率)
      - 预注册:alpha 用**独立的校准集**定(此处用理论最优 alpha*)
      - 事后调:选使 eps_hat 最接近 target_want 的 alpha

    返回 (真值, 预注册估计, 事后调估计, 偏差比)
    """
    rng = np.random.default_rng(seed)
    # 目标域小样本错误率观测(二项)
    k = rng.binomial(n_target, eps_target)
    eps_hat_target = k / n_target
    # 源域大样本,估计近乎无偏
    eps_hat_source = rng.binomial(n_source, eps_source) / n_source

    def mix(a):
        return (1 - a) * eps_hat_target + a * eps_hat_source

    # 预注册:最小化 MSE 的 alpha(用已知真值算,代表"独立校准")
    grid = np.linspace(0, 1, 1001)
    alpha_star = float(grid[np.argmin((mix(grid) - eps_target) ** 2)])
    eps_pre = mix(alpha_star)

    # 事后调:选使估计最接近期望答案的 alpha
    alpha_gamed = float(grid[np.argmin(np.abs(mix(grid) - target_want))])
    eps_gamed = mix(alpha_gamed)

    return dict(
        truth=eps_target, eps_hat_target=eps_hat_target,
        eps_hat_source=eps_hat_source,
        alpha_pre=round(alpha_star, 3), eps_pre=eps_pre,
        alpha_gamed=round(alpha_gamed, 3), eps_gamed=eps_gamed,
        want=target_want,
        bias_pre=abs(eps_pre - eps_target),
        bias_gamed=abs(eps_gamed - eps_target),
    )


FIXTURES = [
    ("合规:小样本+预注册 alpha", dict(
        n_target=20, used_source_info=True, alpha=0.4,
        alpha_predetermined=True), "pass"),
    ("事后调 alpha → R3", dict(
        n_target=20, used_source_info=True, alpha=0.9,
        alpha_predetermined=False), "fail"),
    ("借用但无 alpha", dict(
        n_target=20, used_source_info=True), "fail"),
    ("借用但无确定方法", dict(
        n_target=20, used_source_info=True, alpha=0.4), "fail"),
    ("声明未借用", dict(
        n_target=20, used_source_info=False), "pass"),
    ("小样本但未声明 → 判不了", dict(n_target=20), "na"),
    ("大样本 → 不触发", dict(n_target=200), "na"),
]


def run_fixtures():
    out = []
    for src, kw, expect in FIXTURES:
        got, obs, det = check_T13b_ext(**kw)
        out.append((src, expect, got, obs, det, got == expect))
    return out


if __name__ == "__main__":
    print("=== T13b 小样本扩展(声明检查) ===")
    rows = run_fixtures()
    for src, expect, got, obs, det, ok in rows:
        print(f"{'OK ' if ok else 'XX '}{src}\n"
              f"     期望={expect:<5} 实际={got:<5} | {obs} | {det}")
    bad = [r for r in rows if not r[5]]
    print(f"\n合计 {len(rows)},符合 {len(rows)-len(bad)}")

    print("\n=== 数值反例:alpha 事后调的偏差 ===")
    for s in range(3):
        d = alpha_gaming_demo(seed=s)
        print(f"  seed={s}: 真值={d['truth']:.3f} | "
              f"预注册 alpha={d['alpha_pre']:.3f} → 估计={d['eps_pre']:.3f} "
              f"(偏差 {d['bias_pre']:.3f}) | "
              f"事后调 alpha={d['alpha_gamed']:.3f} → 估计={d['eps_gamed']:.3f} "
              f"(偏差 {d['bias_gamed']:.3f})")
    raise SystemExit(1 if bad else 0)
