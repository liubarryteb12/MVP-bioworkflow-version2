# -*- coding: utf-8 -*-
"""§10「不适用 + 理由」第三态 与 适用性闸门 的单元测试。

起因(v2.13 真实数据压力测试预演):
  引入第三态时连犯 3 次同类错误 —— npass / nna / total 的 sum 与公式
  在 passed=None 时崩溃或漏计。这些 bug 靠"看输出正常"发现不了,
  必须靠边界测试固化。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(os.path.dirname(HERE), "scripts")
sys.path.insert(0, SCRIPTS)

import importlib.util


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


va = _load("va", os.path.join(SCRIPTS, "verify_all.py"))
ag = _load("ag", os.path.join(SCRIPTS, "applicability_gate.py"))


# ── 第三态:计数 ────────────────────────────────────────────────────
def test_ledger_three_state_count():
    """pass / fail / N/A 三态各自独立计数,互不污染。"""
    L = va.Ledger()
    L.add("t", "通过项", 1, 1, True)
    L.add("t", "失败项", 0, 1, False)
    L.add_na("t", "不适用项", "理由X")
    assert L.npass == 1, f"npass 应为 1,实为 {L.npass}"
    assert L.nfail == 1, f"nfail 应为 1,实为 {L.nfail}"
    assert L.nna == 1, f"nna 应为 1,实为 {L.nna}"
    # ★ 回归:初版 total=npass+nfail,把 N/A 项漏掉(§10 禁止的静默删除)
    assert L.npass + L.nfail + L.nna == 3


def test_ledger_empty_reason_rejected():
    """§10:不适用项必须给理由,空理由必须报错(禁止留空)。"""
    L = va.Ledger()
    for bad in ("", "   ", None):
        try:
            L.add_na("t", "无理由项", bad)
        except ValueError:
            continue
        raise AssertionError(f"空理由 {bad!r} 未被拦截")


def test_na_row_shape():
    """N/A 行的字段形态:passed 为 None 且带 na 标记。"""
    L = va.Ledger()
    L.add_na("b", "某判据", "理由")
    r = L.rows[-1]
    assert r["passed"] is None, "N/A 项 passed 必须为 None(第三态)"
    assert r.get("na") is True
    assert r["observed"] == "不适用"


# ── 适用性闸门 ──────────────────────────────────────────────────────
SRNA_META = dict(n_sample=8, assay_type="srna_count",
                 species="Arabidopsis thaliana",
                 is_single_cell=False,
                 has_clinical_outcome=False,
                 has_pathway_annotation=False)


def test_gate_srna_scene():
    """GSE250167 场景:单细胞/生存/富集/模型类判据均不适用。"""
    res = ag.evaluate(SRNA_META)
    for cid in ("T03", "T04", "T06", "T09", "T13", "T15", "T16", "T17"):
        ok, reason = res[cid]
        assert not ok, f"{cid} 在 sRNA 场景应不适用"
        assert reason.strip(), f"{cid} 不适用但无理由(§10 禁止)"
        assert "{" not in reason, f"{cid} 理由含未格式化占位符: {reason}"
    # T01 尺度声明检查与数据类型无关,仍适用
    assert res["T01"][0] is True


def test_gate_single_cell_scene():
    """单细胞场景:T15/T16 必须转为适用(回归 v2.13 逻辑反向 bug)。"""
    meta = dict(SRNA_META, is_single_cell=True, n_sample=2000)
    res = ag.evaluate(meta)
    assert res["T15"][0] is True, "单细胞数据下 T15 必须适用"
    assert res["T16"][0] is True, "单细胞数据下 T16 必须适用"


def test_gate_reason_never_empty():
    """任何不适用的判据都必须有非空理由 —— 全场景遍历。"""
    import itertools
    for n, sc, clin, path in itertools.product(
            (8, 20, 200), (False, True), (False, True), (False, True)):
        meta = dict(n_sample=n, assay_type="x", is_single_cell=sc,
                    has_clinical_outcome=clin,
                    has_pathway_annotation=path)
        for cid, (ok, reason) in ag.evaluate(meta).items():
            if not ok:
                assert reason.strip(), f"{cid} 在 {meta} 下不适用但无理由"


def test_gate_missing_key_not_silently_swallowed():
    """★ 回归:初版 except: pass 吞掉 KeyError,理由残留 {assay_type}。

    框架明令禁止静默 except —— 这里必须显式降级并留痕。
    """
    meta = dict(n_sample=8, is_single_cell=False)   # 故意缺 assay_type
    res = ag.evaluate(meta)
    ok, reason = res["T15"]
    assert not ok
    # 要么格式化成功,要么显式标注占位符缺失;绝不静默保留裸 {xxx}
    assert ("{" not in reason) or ("占位符" in reason), \
        f"占位符缺失被静默吞掉: {reason}"
