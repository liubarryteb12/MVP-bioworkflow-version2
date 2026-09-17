# -*- coding: utf-8 -*-
"""test_module_contracts.py — 模块契约冒烟测试（无数据文件、秒级、云端 pytest 执行）。

契约来源：`08.生信分析模块库/模块开发规范.md`（内化自 `10.代码生成规范参考`）。
覆盖五类契约：
  ① 注册表契约：编号规范、字段齐全、依赖已注册；
  ② 配置契约：所有 pipeline_config*.json 只引用已注册模块、装配可校验；
  ③ 纯函数数值契约：bh / logrank 的已知值；
  ④ 结构适配器回归：to_wide 对宽表、长表（pandas 3 字符串 dtype）、不可识别三态；
  ⑤ 插件与确定性：插件目录可加载、新模块无硬编码阈值、同输入同输出。

设计原则：只测契约与纯函数，不依赖任何数据文件（可离线、可云端、秒级）。
"""
import importlib.util
import json
import os
import re
import sys

import numpy as np
import pandas as pd
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bio_pipeline as bp  # noqa: E402

# 先加载插件（新模块以文件形式增量加入），否则配置校验会误报"未注册模块"
_LOADED_PLUGINS = bp.load_plugins()


# ---------- ① 注册表契约 ----------
def test_registry_ids_wellformed_and_unique():
    assert bp.REG, "注册表为空"
    for mid in bp.REG:
        assert re.fullmatch(r"M\d{2}[A-Za-z]?", mid), f"编号不合规：{mid}"


def test_registry_entries_have_full_contract():
    for mid, m in bp.REG.items():
        for key in ("name", "folder", "fn", "deps"):
            assert key in m, f"{mid} 缺字段 {key}"
        assert isinstance(m["name"], str) and m["name"], f"{mid} name 为空"
        assert isinstance(m["folder"], str) and m["folder"], f"{mid} folder 为空"
        assert callable(m["fn"]), f"{mid} fn 不可调用"
        assert isinstance(m["deps"], list), f"{mid} deps 必须是列表"
        for d in m["deps"]:
            assert d in bp.REG, f"{mid} 依赖未注册模块 {d}"


# ---------- ② 配置契约 ----------
@pytest.mark.parametrize("cfg_path", sorted(
    __import__("glob").glob(os.path.join(HERE, "pipeline_config*.json"))))
def test_configs_reference_registered_modules(cfg_path):
    cfg = json.load(open(cfg_path, encoding="utf-8"))
    assert isinstance(cfg.get("modules"), list) and cfg["modules"], "modules 不能为空"
    errs, _warns = bp.validate_config(cfg)
    assert not errs, f"{os.path.basename(cfg_path)} 装配致命错误：{errs}"
    for mid in cfg["modules"]:
        params = cfg.get("params", {}).get(mid, {})
        assert isinstance(params, dict), f"{mid} 的 params 必须是对象"


def test_validate_config_rejects_unknown_module():
    errs, _ = bp.validate_config({"modules": ["M99"]})
    assert errs and "M99" in errs[0]


# ---------- ③ 纯函数数值契约 ----------
def test_bh_matches_manual_value():
    p = np.array([0.01, 0.02, 0.03, 0.04, 0.05])
    assert np.allclose(bp.bh(p), 0.05, atol=1e-12)


def test_bh_is_monotone_and_bound_to_one():
    p = np.array([0.001, 0.5, 0.2, 0.9])
    q = bp.bh(p)
    assert np.all(q <= 1.0) and np.all(q >= 0.0)
    order = np.argsort(p)
    assert np.all(np.diff(q[order]) >= -1e-12), "BH 校正后应随 p 单调不减"


def test_logrank_detects_separation_and_null():
    e = np.ones(8, dtype=int)
    # 分离组：早期事件集中在一组 → 应显著
    chi_sep, p_sep = bp.logrank(np.array([1., 2, 3, 4, 5, 6, 7, 8]), e,
                                np.array([0, 0, 0, 0, 1, 1, 1, 1]))
    assert chi_sep > 0 and p_sep < 0.05, "完全分离的两组应显著"
    # 真实零假设：两组经历同一事件时间（观察数 = 期望数）→ chi² 恰为 0
    chi_null, p_null = bp.logrank(np.full(8, 5.0), e, np.array([0, 1, 0, 1, 0, 1, 0, 1]))
    assert chi_null == pytest.approx(0.0, abs=1e-9), f"零假设下应无信号，实际 {chi_null}"
    assert p_null > 0.9


# ---------- ④ 结构适配器回归（M11 宽表识别） ----------
def _long_table(samples, terms, dtype_str=True):
    rows = []
    for s in samples:
        for k, tm in enumerate(terms):
            rows.append({("Name" if dtype_str else "sample"): s,
                         ("Term" if dtype_str else "geneset"): tm,
                         "ES": 100.0 + k, "NES": 0.5 + 0.01 * k})
    df = pd.DataFrame(rows)
    if dtype_str:                       # 显式转成 pandas 3 的字符串 dtype（回归点）
        df["Name"] = df["Name"].astype("str")
        df["Term"] = df["Term"].astype("str")
    return df


def test_to_wide_passthrough_for_wide_input():
    samples = ["GSM1", "GSM2", "GSM3"]
    wide = pd.DataFrame(np.ones((4, 3)), index=["g1", "g2", "g3", "g4"], columns=samples)
    out, why = bp.to_wide(wide, samples)
    assert out is not None and out.shape == (4, 3) and "宽表" in why


def test_to_wide_from_long_table_with_str_dtype():
    samples = [f"GSM{i}" for i in range(6)]
    terms = ["E2F Targets", "Mitotic Spindle", "G2M Checkpoint"]
    out, why = bp.to_wide(_long_table(samples, terms), samples)
    assert out is not None, f"长表应能转宽（回归：pandas 3 str dtype），实际原因：{why}"
    assert set(out.columns) == set(samples), "列应为样本"
    assert set(out.index) == set(terms), "行应为基因集"
    assert out.loc["E2F Targets", "GSM0"] == pytest.approx(0.5)


def test_to_wide_reports_failure_instead_of_pretending():
    df = pd.DataFrame({"a": ["x", "y"], "b": [1.0, 2.0], "NES": [0.1, 0.2]})
    out, why = bp.to_wide(df, ["GSM1", "GSM2", "GSM3"])
    assert out is None and "无列取值与样本 ID 重合过半" in why


def test_to_wide_is_deterministic():
    samples = [f"GSM{i}" for i in range(5)]
    terms = ["T1", "T2"]
    df = _long_table(samples, terms)
    a, _ = bp.to_wide(df, samples)
    b, _ = bp.to_wide(df, samples)
    assert a.equals(b)


# ---------- ⑤ 插件契约 ----------
def _load_plugin(fname):
    path = os.path.join(HERE, "modules", fname)
    spec = importlib.util.spec_from_file_location(f"plug_{fname[:-3]}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_plugin_modules_are_loadable_and_registered():
    loaded = bp.load_plugins()
    assert "M17" in loaded, f"插件未加载成功，实际加载：{loaded}"
    assert "M17" in bp.REG
    for mid in loaded:
        assert bp.REG[mid]["fn"] is not None


def test_plugin_rejects_hardcoded_default_threshold():
    """阈值必须来自 config：缺参必须报错，而不是偷偷用默认值。"""
    mod = _load_plugin("m17_sample_similarity.py")
    with pytest.raises(ValueError):
        mod.run({"config": {}, "expr": pd.DataFrame(np.ones((3, 3))),
                 "samples": ["a", "b", "c"]}, os.getcwd())


def test_plugin_sample_similarity_flags_planted_outlier():
    mod = _load_plugin("m17_sample_similarity.py")
    rng = np.random.default_rng(7)
    latent = rng.normal(size=(60, 1))
    core = latent @ np.ones((1, 8)) + rng.normal(scale=0.3, size=(60, 8))
    alien = rng.normal(scale=1.0, size=(60, 1))
    expr = pd.DataFrame(np.column_stack([core, alien]),
                        columns=[f"S{i}" for i in range(9)],
                        index=[f"G{j}" for j in range(60)])
    cm, cand = mod.sample_similarity(expr, 0.8)
    assert cm.shape == (9, 9)
    assert cand.iloc[0]["sample"] == "S8" and bool(cand.iloc[0]["outlier"]), \
        "植入的离群样本应被识别为最低中位相关"
    assert not cand.iloc[1:]["outlier"].any(), "同源样本不应误判"


def test_plugin_sample_similarity_refuses_tiny_design():
    mod = _load_plugin("m17_sample_similarity.py")
    expr = pd.DataFrame(np.ones((5, 2)), columns=["a", "b"])
    assert mod.sample_similarity(expr, 0.8) == (None, None)


# ---------- ⑥ v2 方法补齐插件（M18 相关性 / M19 列线图 / M20 LASSO） ----------
def test_field_parsing_handles_qualified_keys():
    """回归：字段名带限定词（age (years): 55）时按下标切割会残留 "(years): 55"。

    实证来源：run 34764600101 的 M19 报"协变量完整样本仅 0"（age 全 NaN）。
    """
    meta = {"S1": ["tissue: primary lung tumor", "age (years): 55", "gender: female",
                   "relapse: relapsed", "days before relapse/censor: 253",
                   "exclude for prognosis analysis due to incomplete resection or "
                   "adjuvant therapy: exclude", "pathological stage: II", ""]}
    assert bp.gf(meta, "S1", "tissue:") == "primary lung tumor"
    assert bp.gf(meta, "S1", "age") == "55", "带限定词的键必须取冒号后的值"
    assert bp.gf(meta, "S1", "relapse:") == "relapsed"
    assert bp.gf(meta, "S1", "days before relapse/censor") == "253"
    assert bp.gf(meta, "S1", "exclude") == "exclude"
    assert bp.gf(meta, "S1", "pathological stage") == "II"
    assert bp.gf(meta, "S1", "not_exists") is None
    m19 = _load_plugin("m19_nomogram.py")
    assert m19._field(meta, "S1", "gender") == "female"
    assert pd.to_numeric(m19._field(meta, "S1", "age"), errors="coerce") == pytest.approx(55)


def test_m19_covariates_are_configurable_and_numeric():
    m19 = _load_plugin("m19_nomogram.py")
    meta = {f"S{i}": [f"age (years): {50 + i}", "gender: male" if i % 2 else "gender: female",
                      "pathological stage: IB"] for i in range(40)}
    ctx = {"meta": meta, "config": {}}
    X = m19._covariates(ctx, [f"S{i}" for i in range(40)])
    assert X["age"].notna().all() and X["age"].iloc[0] == pytest.approx(50)
    assert X["male"].sum() == 20 and X["stage_ord"].eq(2.0).all()
    ctx2 = {"meta": {"S1": ["A: 1", "G: male", "S: III"]},
            "config": {"age_key": "a", "gender_key": "g", "stage_key": "s"}}
    X2 = m19._covariates(ctx2, ["S1"])
    assert X2.loc["S1", "age"] == pytest.approx(1) and X2.loc["S1", "male"] == 1.0
    assert X2.loc["S1", "stage_ord"] == pytest.approx(4.0), "分期映射应可跨数据集"


def test_m19_extract_baseline_handles_statsmodels_list_attribute():
    """回归：statsmodels baseline_cumulative_hazard 是 [H0,times,S0] 列表属性（非方法），
    直接调用会抛 'list' object is not callable（run 34766532160 实证）。"""
    from statsmodels.duration.hazard_regression import PHReg
    rng = np.random.default_rng(3)
    n = 150
    X = pd.DataFrame(rng.normal(size=(n, 2)), columns=["a", "b"])
    tt = rng.exponential(size=n) + 1.0
    ev = (rng.uniform(size=n) > 0.3).astype(int)
    cox = PHReg(tt, X.to_numpy(float), status=ev).fit()
    m19 = _load_plugin("m19_nomogram.py")
    times, bh = m19.extract_baseline(cox)
    assert times.ndim == 1 and bh.ndim == 1 and len(times) == len(bh) and len(times) > 0
    assert np.all(np.diff(bh) >= -1e-9), "基线累积风险应单调非降"
    t0 = float(np.median(times))
    assert m19.baseline_at(times, bh, t0) >= 0
    s_t0 = m19.surv_prob(m19.baseline_at(times, bh, t0), 0.0)
    assert 0 < s_t0 <= 1.0, "lp=0 时 S0 应在 (0,1]"


def test_m19_extract_baseline_orders_time_hazard_correctly():
    """回归：statsmodels 三元组顺序为 (time, hazard, survival)，曾误取反导致 H0 读到时间值
    （H0(1825d)=2282，run 34768479253 实证）。锁定顺序。"""
    from statsmodels.duration.hazard_regression import PHReg
    rng = np.random.default_rng(5)
    n = 200
    X = pd.DataFrame(rng.normal(size=(n, 2)), columns=["a", "b"])
    tt = rng.exponential(size=n) + 1.0
    ev = (rng.uniform(size=n) > 0.3).astype(int)
    cox = PHReg(tt, X.to_numpy(float), status=ev).fit()
    m19 = _load_plugin("m19_nomogram.py")
    times, bh = m19.extract_baseline(cox)
    raw = cox.baseline_cumulative_hazard[0]   # 三元组 (time, hazard, survival)
    assert np.allclose(times, np.asarray(raw[0]).ravel()), "times 应为三元组第 1 个"
    assert np.allclose(bh, np.asarray(raw[1]).ravel()), "cumhaz 应为三元组第 2 个（hazard）"
    surv = np.asarray(raw[2]).ravel()
    assert np.allclose(surv, np.exp(-bh)), "S0 = exp(-H0) 必须成立（锁定列顺序）"


def test_m19_run_end_to_end(tmp_path):
    """端到端冒烟：合成数据跑通 run()，产出 Cox 表 / 列线图（四格式）/ RFS 换算表。

    回归锁定（云端 run 34770322198 实证）：列线图曾用中文标签，DejaVu Sans 无中日韩
    字形 → 图上渲染成豆腐块；故此处捕获 matplotlib "Glyph ... missing" 告警并断言为空。
    """
    import warnings
    m19 = _load_plugin("m19_nomogram.py")
    rng = np.random.default_rng(7)
    n = 120
    meta = {f"S{i}": [f"age (years): {40 + int(rng.integers(0, 40))}",
                      "gender: male" if rng.random() > 0.5 else "gender: female",
                      "pathological stage: II"] for i in range(n)}
    tt = rng.integers(100, 2000, size=n).astype(float)
    ev = rng.integers(0, 2, size=n)
    ctx = {"meta": meta, "keep": [f"S{i}" for i in range(n)],
           "tt": tt, "ev": ev, "config": {}}
    out = str(tmp_path / "m19")
    os.makedirs(out, exist_ok=True)
    with warnings.catch_warnings(record=True) as rec:
        warnings.simplefilter("always")
        msg = m19.run(ctx, out)
    missing = [str(w.message) for w in rec if "Glyph" in str(w.message)]
    assert not missing, f"图内文本缺字形（会渲染成豆腐块）：{missing}"
    assert "n=" in msg, msg
    for f in ("M19_Cox系数表.csv", "M19_总分_1825天无复发生存.csv"):
        assert os.path.exists(os.path.join(out, f)), f"缺失产出 {f}"
    for ext in ("png", "pdf", "tiff", "jpg"):        # §F 四格式齐全
        f = f"M19_列线图.{ext}"
        assert os.path.exists(os.path.join(out, f)), f"缺失产出 {f}"


def test_v2_method_plugins_are_registered():
    loaded = bp.load_plugins()
    for mid in ("M17", "M18", "M19", "M20"):
        assert mid in loaded, f"{mid} 未注册；已加载 {loaded}"


def test_m18_corr_matrix_and_traits():
    m18 = _load_plugin("m18_correlation.py")
    x = np.linspace(0, 1, 20)
    samples = [f"S{i}" for i in range(20)]
    mat = pd.DataFrame(np.column_stack([x, 2 * x + 1, -x]).T,
                       index=["g1", "g2", "g3"], columns=samples)
    cm = m18.corr_matrix(mat)
    assert cm.shape == (3, 3)
    assert cm.loc["g1", "g2"] == pytest.approx(1.0), "线性同向应 r=1"
    assert cm.loc["g1", "g3"] == pytest.approx(-1.0), "线性反向应 r=-1"
    traits = pd.DataFrame({"t": x, "nan_col": [np.nan] * 20}, index=samples)
    tab = m18.corr_with_traits(mat, traits, min_n=10)
    hit = tab[(tab.gene == "g1") & (tab.trait == "t")].iloc[0]
    assert hit["r"] == pytest.approx(1.0) and hit["n"] == 20
    miss = tab[(tab.gene == "g1") & (tab.trait == "nan_col")].iloc[0]
    assert np.isnan(miss["r"]), "有效配对不足时不得给出相关系数"


def test_m18_collapses_duplicate_gene_symbols():
    """回归：多探针→同一 Symbol 时索引重复，曾致 stack 报错（run 34762853449）。"""
    m18 = _load_plugin("m18_correlation.py")
    mat = pd.DataFrame([[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]],
                       index=["p1", "p2", "p3"], columns=["S1", "S2"])
    sym = {"p1": "G1", "p2": "G1", "p3": "G2"}
    out, n_dup = m18.collapse_by_symbol(mat, sym)
    assert n_dup == 1 and list(out.index) == ["G1", "G2"]
    assert out.loc["G1", "S1"] == 3.0, "同符号探针应取最大值"
    assert len(out.index) == len(set(out.index)), "聚合后索引必须唯一"
    out2, n2 = m18.collapse_by_symbol(mat, {})
    assert n2 == 0 and out2.equals(mat), "无注释时应原样返回"


def test_m19_nomogram_scaling_and_survival():
    m19 = _load_plugin("m19_nomogram.py")
    coefs = {"a": 1.0, "b": 2.0, "c": 3.0}
    ranges = {"a": (0, 10), "b": (0, 10), "c": (0, 10)}
    pts = m19.points_per_unit(coefs, ranges, span=100.0)
    assert pts["c"]["range_points"] == pytest.approx(100.0), "最大效应变量全范围=100 分"
    assert pts["a"]["range_points"] == pytest.approx(100 / 3)
    assert m19.surv_prob(0.1, 0.0) == pytest.approx(np.exp(-0.1))
    assert m19.surv_prob(0.0, 99.0) == pytest.approx(1.0)
    et = np.array([100.0, 200.0, 300.0])
    ch = np.array([0.05, 0.12, 0.20])
    assert m19.baseline_at(et, ch, 150.0) == pytest.approx(0.05)
    assert m19.baseline_at(et, ch, 250.0) == pytest.approx(0.12)
    assert m19.baseline_at(et, ch, 50.0) == pytest.approx(0.0)


def test_m20_lasso_is_sparse_and_deterministic():
    m20 = _load_plugin("m20_lasso_cox.py")
    rng = np.random.default_rng(11)
    n, p = 120, 60
    X = rng.normal(size=(n, p))
    signal = X[:, 0] - 1.5 * X[:, 1]
    y = (signal + rng.normal(scale=0.5, size=n) > 0).astype(int)
    sel, coef = m20.lasso_select(X, y, c=0.05)
    assert 0 < sel.sum() < p, f"LASSO 应稀疏（入选 {sel.sum()}/{p}）"
    sel2, coef2 = m20.lasso_select(X, y, c=0.05)
    assert np.array_equal(sel, sel2) and np.allclose(coef, coef2), "同输入须同输出"
