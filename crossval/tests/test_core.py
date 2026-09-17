# -*- coding: utf-8 -*-
"""
pytest 单元测试 + 边界测试
代码员视角 P0:"自证只能证明在我试过的输入上能跑通,不等于测试。"
"""
import os, sys
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import figure_kit as fk


def test_hex2rgb_basic():
    """hex2rgb 返回 0-1 归一化值(非 0-255)"""
    assert fk.hex2rgb("#000000") == (0.0, 0.0, 0.0)
    assert fk.hex2rgb("#FFFFFF") == (1.0, 1.0, 1.0)
    assert fk.hex2rgb("#FF0000") == (1.0, 0.0, 0.0)
    assert fk.hex2rgb("ff0000") == (1.0, 0.0, 0.0)


def test_rel_lum_monotone():
    a = fk._rel_lum(fk.hex2rgb("#000000"))
    b = fk._rel_lum(fk.hex2rgb("#808080"))
    c = fk._rel_lum(fk.hex2rgb("#FFFFFF"))
    assert a < b < c


def test_rel_lum_white_black():
    assert abs(fk._rel_lum(fk.hex2rgb("#FFFFFF")) - 1.0) < 1e-6
    assert abs(fk._rel_lum(fk.hex2rgb("#000000")) - 0.0) < 1e-6


def test_rel_lum_green_brighter_than_red():
    """G 权重 0.7152 >> R 0.2126 —— 这是 §0.2 '等亮度红绿' 论证的基础"""
    lg = fk._rel_lum(fk.hex2rgb("#00FF00"))
    lr = fk._rel_lum(fk.hex2rgb("#FF0000"))
    assert lg - lr > 0.4, f"纯绿({lg:.3f}) 应远高于纯红({lr:.3f})"


def test_delta_e_self_zero():
    assert fk.delta_e(fk.hex2rgb("#FF0000"), fk.hex2rgb("#FF0000")) < 1e-6


def test_delta_e_black_white_large():
    assert fk.delta_e(fk.hex2rgb("#000000"), fk.hex2rgb("#FFFFFF")) > 90


def test_delta_e_symmetric():
    assert abs(fk.delta_e(fk.hex2rgb("#FF0000"), fk.hex2rgb("#0000FF")) - fk.delta_e(fk.hex2rgb("#0000FF"), fk.hex2rgb("#FF0000"))) < 1e-6


@pytest.mark.parametrize("kind", ["protanopia", "deuteranopia", "tritanopia"])
def test_simulate_preserves_range(kind):
    out = fk.simulate(fk.hex2rgb("#C81E5A"), kind)
    assert len(out) == 3 and all(0 <= v <= 255 for v in out)


@pytest.mark.parametrize("kind", ["protanopia", "deuteranopia", "tritanopia"])
def test_simulate_is_pure_function(kind):
    assert fk.simulate(fk.hex2rgb("#0CC8F0"), kind) == fk.simulate(fk.hex2rgb("#0CC8F0"), kind)


def test_hue_of_primary_colors():
    """色相方向判定的基础:红≈0°、绿≈120°、蓝≈240°"""
    def hue(h): return fk._hue_sv(fk.hex2rgb(h))[0]
    assert hue("#FF0000") < 30 or hue("#FF0000") > 330
    assert 80 <= hue("#00FF00") <= 170
    assert 200 <= hue("#0000FF") <= 260


def test_red_blue_not_flagged_as_redgreen():
    """红-蓝色相差 120° 但不是红绿对 —— 必须靠方向判定排除"""
    r, b = fk.hex2rgb("#FF0000"), fk.hex2rgb("#0000FF")
    assert len(fk.check_redgreen([r, b], hex_list=["#FF0000", "#0000FF"],
                                 advisory=True)) == 0


def test_equal_luminance_redgreen_detected():
    """等亮度红绿必须被检出 —— 这是 ΔE 抓不到的那一类(§0.2 核心论证)"""
    r, g = fk.hex2rgb("#D91E1E"), fk.hex2rgb("#1E963C")
    assert abs(fk._rel_lum(r) - fk._rel_lum(g)) < 0.15, "构造须为等亮度"
    v = fk.check_redgreen([r, g], hex_list=["#D91E1E", "#1E963C"], advisory=True)
    assert len(v) >= 1, "等亮度红绿应被标记"


def test_unequal_luminance_redgreen_not_flagged():
    """非等亮度红绿不应被标记 —— 亮度差本身提供了可区分性"""
    r, g = fk.hex2rgb("#C0392B"), fk.hex2rgb("#27AE60")
    assert abs(fk._rel_lum(r) - fk._rel_lum(g)) > 0.15, "构造须为非等亮度"
    v = fk.check_redgreen([r, g], hex_list=["#C0392B", "#27AE60"], advisory=True)
    assert len(v) == 0, f"非等亮度红绿不应标记,实得 {v}"


def _name_passed(name, steps):
    res = fk.check_name(name, allowed_steps=steps)
    return all(t[-1] for t in res)


def test_check_name_valid():
    assert _name_passed("01_qc_violin_mito.pdf", {"qc", "deg"})


def test_check_name_bad_step():
    assert not _name_passed("01_zzz_x.pdf", {"qc", "deg"})


def test_check_name_bad_pattern():
    assert not _name_passed("my_figure.pdf", {"qc"})


def test_empty_color_list():
    """⚠ 回归:空列表曾使 min() 抛 empty sequence"""
    res = fk.check_colors([])
    assert res and all(t[-1] for t in res), "空输入应判不适用而非崩溃"


def test_single_color():
    """⚠ 回归:单色同样曾崩溃"""
    res = fk.check_colors(["#000000"])
    assert res and all(t[-1] for t in res)


def test_identical_colors_zero_de():
    assert fk.delta_e((0.1, 0.2, 0.3), (0.1, 0.2, 0.3)) < 1e-9


@pytest.mark.parametrize("h", ["#000000","#FFFFFF","#FF0000","#00FF00","#0000FF"])
def test_extreme_rgb(h):
    c = fk.hex2rgb(h)
    assert all(0 <= v <= 255 for v in fk.simulate(c, "protanopia"))


def test_check_legend_empty_string():
    """空图注必须报缺失(而非崩溃)"""
    res = fk.check_legend("", kind="bar")
    assert isinstance(res, list) and len(res) > 0
    assert not all(t[-1] for t in res), "空图注不应全通过"


def test_check_legend_missing_n():
    """缺 n 值必须被判失败"""
    res = fk.check_legend("Data are mean ± SEM.", kind="bar")
    failed = [t for t in res if not t[-1]]
    assert failed, f"缺 n 的图注应至少有一项失败,实得全通过: {res}"
