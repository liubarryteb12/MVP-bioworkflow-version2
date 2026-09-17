#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
figure_kit.py —— 作图规范 v1.0 的可执行部分

覆盖:
  §A-1 分辨率 / §A-2 色彩模式 / §A-3 格式 / §A-7 色板与色盲
  §B-1 误差棒 / §B-2 n 值 / §B-3 显著性 / §B-5 箱线图定义
  §D   图注结构 / §5.7 命名 / §5.8 多格式导出

设计原则(与框架一致):
  - 只实现**可机械判定**的条目
  - Nature 官方措辞类条目不在本脚本判定,见 作图规范_v1.0.md 标注
  - 每项检查输出 (passed, observed, expected)
"""
import os, re, json, math
# ── 控制台编码加固（v2.25）──────────────────────────────────────────────────
# 起因：中文 Windows 默认控制台 cp936(GBK) 无法编码 ✓/✗/⚠ → UnicodeEncodeError。
try:
    import sys as _csys
    if _csys.stdout.isatty():
        _csys.stdout.reconfigure(errors="replace")
    else:
        _csys.stdout.reconfigure(encoding="utf-8", errors="replace")
    _csys.stderr.reconfigure(errors="replace")
except (AttributeError, ValueError):
    pass
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEC = os.path.join(ROOT, "spec", "figure_spec.yaml")


def load_spec():
    import yaml
    return yaml.safe_load(open(SPEC, encoding="utf-8"))


# ============ 颜色工具 ============
def hex2rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


def _srgb2lin(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _lin2srgb(c):
    c = max(0.0, min(1.0, c))
    return 12.92 * c if c <= 0.0031308 else 1.055 * (c ** (1 / 2.4)) - 0.055


# 二色觉模拟矩阵(线性 RGB 上的常用近似)
CVD = {
    "protanopia":   [[0.567, 0.433, 0.000], [0.558, 0.442, 0.000], [0.000, 0.242, 0.758]],
    "deuteranopia": [[0.625, 0.375, 0.000], [0.700, 0.300, 0.000], [0.000, 0.300, 0.700]],
    "tritanopia":   [[0.950, 0.050, 0.000], [0.000, 0.433, 0.567], [0.000, 0.475, 0.525]],
}


def simulate(rgb, kind):
    M = CVD[kind]
    lin = [_srgb2lin(c) for c in rgb]
    out = [sum(M[i][j] * lin[j] for j in range(3)) for i in range(3)]
    return tuple(_lin2srgb(o) for o in out)


def rgb2lab(rgb):
    r, g, b = [_srgb2lin(c) for c in rgb]
    X = r * 0.4124564 + g * 0.3575761 + b * 0.1804375
    Y = r * 0.2126729 + g * 0.7151522 + b * 0.0721750
    Z = r * 0.0193339 + g * 0.1191920 + b * 0.9503041
    Xn, Yn, Zn = 0.95047, 1.0, 1.08883

    def f(t):
        return t ** (1 / 3) if t > 0.008856 else (7.787 * t + 16 / 116)
    fx, fy, fz = f(X / Xn), f(Y / Yn), f(Z / Zn)
    return (116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz))


def delta_e(rgb1, rgb2):
    a, b = rgb2lab(rgb1), rgb2lab(rgb2)
    return math.sqrt(sum((a[i] - b[i]) ** 2 for i in range(3)))


def check_colors(colors, spec=None):
    """A-7:色板合规 + 三种色盲模拟下两两可区分"""
    spec = spec or load_spec()
    res = []
    rgb_list = [hex2rgb(c) if isinstance(c, str) else tuple(c) for c in colors]
    pal = set(h.lower() for h in spec["palettes"]["wong2011"])
    # ⚠ v2.4 修(pytest 边界测试发现):空列表 / 单色时下方 min() 会抛
    #   "min() arg is an empty sequence"。空输入应判"不适用"而非崩溃。
    if len(rgb_list) < 2:
        res.append(("C-6.c1", "颜色取自 Wong2011 色板",
                    f"{len(rgb_list)} 色(<2,不适用)", "n/a", True))
        return res

    in_pal = sum(1 for c in colors if isinstance(c, str) and c.lower() in pal)
    res.append(("C-6.c1", "颜色取自 Wong2011 色板", f"{in_pal}/{len(colors)}",
                f"{len(colors)}/{len(colors)}", in_pal == len(colors)))

    # 分级:protan/deutan 为强制项(Wong 色板针对此设计);
    # tritanopia 为建议项 —— 实测 Wong 前 6 色在 tritanopia 下 ΔE=8.65,
    # 即 Wong 色板**不保证**三色盲安全(与文献一致)。
    # 总的 worst 只统计**强制**模拟(protan/deutan);
    # tritanopia 为建议级,单独成项,不参与整体判定。
    worst = 1e9
    for kind in ("protanopia", "deuteranopia"):
        sims = [simulate(c, kind) for c in rgb_list]
        for i in range(len(sims)):
            for j in range(i + 1, len(sims)):
                worst = min(worst, delta_e(sims[i], sims[j]))
    thr = spec["colorblind"]["min_delta_e"]
    res.append(("C-6.c2", f"红绿色盲模拟后最小 ΔE ≥ {thr}(强制)", round(worst, 2),
                f"≥{thr}", worst >= thr))
    for kind in spec["colorblind"]["simulate"]:
        sims = [simulate(c, kind) for c in rgb_list]
        mn = min(delta_e(sims[i], sims[j])
                 for i in range(len(sims)) for j in range(i + 1, len(sims)))
        lvl = thr if kind != "tritanopia" else spec["colorblind"]["tritanopia_advisory"]
        res.append((f"C-6.c2.{kind[:5]}",
                    f"{kind} 可区分({'强制' if kind != 'tritanopia' else '建议'})",
                    round(mn, 2), f"≥{lvl}", mn >= lvl))
    # 红绿色相对(ΔE 的补充项)
    rg = check_redgreen(rgb_list, spec, colors)
    res.append(("C-6.c3", "无等亮度红绿对(色板外,建议级)",
                rg or "无", "无(建议)", (not rg) or True), )
    res[-1] = ("C-6.c3", "无等亮度红绿对(色板外,建议级)", rg or "无",
               "无", not rg)
    return res


# ============ 图注检查 ============
def _hue_sv(rgb):
    import colorsys
    h, s, v = colorsys.rgb_to_hsv(*rgb)
    return h * 360.0, s, v


def _rel_lum(rgb):
    lin = [_srgb2lin(c) for c in rgb]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def check_redgreen(rgb_list, spec=None, hex_list=None, advisory=True):
    """A-7 红绿对比检测。
    ⚠ 实测发现:ΔE **抓不到**红绿问题 —— 纯红/纯绿因相对亮度差异大
      (Y 0.213 vs 0.715),色盲模拟后仍可区分(ΔE≈15)。
      真正的危险是**等亮度红绿**:色相为红绿对立且亮度接近。
      故本项为 ΔE 检查的补充,不可互相替代。"""
    spec = spec or load_spec()
    risky = []
    # 适用范围:仅检查**色板外**的自选色。
    # 实测:Wong 色板内的 #D55E00(朱红) 与 #009E73(绿) ΔY=0.035,
    # 即色板本身就含等亮度红绿对 —— 但其安全性已由 ΔE 项(protan/deutan
    # 强制阈值)验证通过。若此处不排除色板内颜色,会造成**误伤**。
    pal = set(h.lower() for h in spec["palettes"]["wong2011"])
    inpal = [isinstance(h, str) and h.lower() in pal for h in (hex_list or [])]
    for i in range(len(rgb_list)):
        for j in range(i + 1, len(rgb_list)):
            if hex_list and (inpal[i] and inpal[j]):
                continue
            hi, si, vi = _hue_sv(rgb_list[i])
            hj, sj, vj = _hue_sv(rgb_list[j])
            if si < 0.25 or sj < 0.25:      # 低饱和不参与
                continue
            # 方向判定:必须一个落在红区、另一个落在绿区。
            # 仅用"色相差 120°"会把红-蓝(H 0 vs 240)误判为红绿对。
            def _is_red(h):   return h <= 30 or h >= 330
            def _is_green(h): return 80 <= h <= 170
            if not ((_is_red(hi) and _is_green(hj)) or (_is_green(hi) and _is_red(hj))):
                continue
            dl = abs(_rel_lum(rgb_list[i]) - _rel_lum(rgb_list[j]))
            if dl < spec["colorblind"]["redgreen"]["max_lum_diff"]:
                risky.append((i, j, round(abs(hi - hj) % 360, 1), round(dl, 3)))
    return risky


def check_legend(text, spec=None, kind="general"):
    """B-1/B-2/B-3/B-5/D:图注必含项"""
    spec = spec or load_spec()
    L = spec["legend"]
    res = []
    t = text or ""

    has_eb = any(k.lower() in t.lower() for k in L["error_bar_required"])
    res.append(("C-6.l1", "误差棒已定义(SD/SEM/CI)", has_eb, "True", has_eb))
    has_ct = any(k.lower() in t.lower() for k in L["center_required"])
    res.append(("C-6.l2", "中心度量已定义(mean/median)", has_ct, "True", has_ct))

    n_exact = re.findall(L["n_pattern"], t, re.I)
    res.append(("C-6.l3", "n 为精确整数", n_exact or "无", "≥1 处", bool(n_exact)))
    n_range = re.findall(L["n_forbid_range"], t, re.I)
    res.append(("C-6.l4", "n 未写成区间", n_range or "无", "无", not n_range))
    has_unit = any(k.lower() in t.lower() for k in L["replicate_unit_required"])
    res.append(("C-6.l5", "n 已定义重复单位", has_unit, "True", has_unit))

    if kind in ("general", "test"):
        has_test = any(k.lower() in t.lower() for k in L["test_required"])
        res.append(("C-6.l6", "统计检验已声明", has_test, "True", has_test))
        has_side = any(k.lower() in t.lower() for k in L["sided_required"])
        res.append(("C-6.l7", "单/双侧已声明", has_side, "True", has_side))

    if kind == "boxplot":
        for idx, (en, zh) in enumerate(L["boxplot_required"], 1):
            ok = bool(re.search(en, t, re.I)) or zh in t
            res.append((f"C-6.l8.{idx}", f"箱线图已定义{zh}", ok, "True", ok))

    if kind == "survival":
        for idx, kw in enumerate(["censoring|删失", "at-risk|risk table|风险表",
                                  "log-rank|wilcoxon", "HR"], 1):
            ok = bool(re.search(kw, t, re.I))
            res.append((f"C-6.l9.{idx}", f"生存曲线含 {kw.split('|')[0]}", ok, "True", ok))

    wc = len(re.findall(r"\b[\w'-]+\b", t))
    mx = L["max_words_nature"]
    res.append(("C-6.l10", f"图注字数 ≤ {mx}(Nature)", wc, f"≤{mx}", wc <= mx))
    return res


# ============ 命名检查 ============
def check_name(name, spec=None, allowed_steps=None):
    spec = spec or load_spec()
    res = []
    pat = spec["naming"]["pattern"]
    ok = bool(re.match(pat, name, re.I))
    res.append(("C-6.n1", f"命名匹配 {spec['naming']['example']}", name,
                spec["naming"]["example"], ok))
    m = re.match(r"^(\d{2})_([a-z][a-z0-9]*)_", name, re.I)
    if m and allowed_steps is not None:
        step = m.group(2)
        res.append(("C-6.n2", "analysis_step 属于框架阶段标签", step,
                    f"∈ {sorted(allowed_steps)}", step in allowed_steps))
    return res


# ============ 文件级检查 ============
def check_file(path, spec=None, expect_kind="vector"):
    """A-1/A-2/A-3:分辨率、色彩模式、体积"""
    spec = spec or load_spec()
    res = []
    fn = os.path.basename(path)
    ext = path.lower().rsplit(".", 1)[-1]
    size = os.path.getsize(path)
    res.append(("C-6.f1", f"{fn} 体积合规", f"{size/1024:.0f}KB",
                "≤10MB(主图，Wiley)", size <= spec["formats"]["max_bytes"]["main"]))
    if ext in ("pdf", "eps"):
        pass                      # 矢量图不走 PIL(PIL 无法读 PDF)
    else:
        try:
            from PIL import Image
            with Image.open(path) as im:
                mode = im.mode
                dpi = im.info.get("dpi", (0, 0))[0]
                w, h = im.size
            need = (spec["dpi"]["photo_min"] if expect_kind == "raster"
                    else spec["dpi"]["line_min"])
            # 容差:matplotlib 写 png 的 dpi 可能是 299.9994(浮点精度)
            res.append(("C-6.f2", f"{fn} dpi", round(dpi, 2), f">={need}",
                        dpi >= need - 0.5))
            rgb_ok = mode in ("RGB", "RGBA")
            res.append(("C-6.f3", f"{fn} 色彩模式 RGB", mode, "RGB", rgb_ok))
            mm_w = w / dpi * 25.4 if dpi else 0
            res.append(("C-6.f4", f"{fn} 宽度 <=183mm(双栏)", round(mm_w, 1),
                        "<=183", mm_w <= spec["size"]["double_col_max_mm"]))
        except Exception as e:
            res.append(("C-6.f2", f"{fn} 可读", f"异常 {e}", "可读", False))

    if ext in ("pdf", "eps"):
        try:
            from pypdf import PdfReader
            r = PdfReader(path)
            ft = set()
            for pg in r.pages:
                res_dict = pg.get("/Resources", {})
                fonts = res_dict.get("/Font", {})
                for k in (fonts.keys() if hasattr(fonts, "keys") else []):
                    obj = fonts[k].get_object()
                    ft.add(str(obj.get("/Subtype", "")))
            bad = [f for f in ft if f not in
                   ("/TrueType", "/Type0", "/CIDFontType2", "/CIDFontType0")]
            res.append(("C-6.f5", f"{fn} 字体类型合规", sorted(ft) or "无字体",
                        "TrueType/Type0", not bad))
        except Exception as e:
            res.append(("C-6.f5", f"{fn} 字体检查", f"异常 {e}", "可检", False))
    return res


# ============ 多格式导出 ============
def export_all(fig, stem, outdir, dpi_raster=600, dpi_preview=300):
    """§5.8:一次出 pdf/tiff/png/jpg 四格式"""
    import matplotlib
    matplotlib.rcParams["pdf.fonttype"] = 42
    matplotlib.rcParams["ps.fonttype"] = 42
    os.makedirs(outdir, exist_ok=True)
    out = {}
    out["pdf"] = os.path.join(outdir, f"{stem}.pdf")
    fig.savefig(out["pdf"], bbox_inches="tight")
    out["tiff"] = os.path.join(outdir, f"{stem}.tiff")
    fig.savefig(out["tiff"], dpi=dpi_raster, bbox_inches="tight")
    out["png"] = os.path.join(outdir, f"{stem}.png")
    fig.savefig(out["png"], dpi=dpi_preview, bbox_inches="tight")
    out["jpg"] = os.path.join(outdir, f"{stem}.jpg")
    fig.savefig(out["jpg"], dpi=dpi_preview, bbox_inches="tight",
                pil_kwargs={"quality": 95})
    return out


if __name__ == "__main__":
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    spec = load_spec()
    W = spec["palettes"]["wong2011"]

    print("=" * 70)
    print("  作图规范 v1.0 · 技术判据实跑验证")
    print("=" * 70)

    # ① 色板:Wong 应通过
    print("\n① A-7 色板 —— Wong2011(应通过)")
    for cid, lab, obs, exp, ok in check_colors(W[:6], spec):
        print(f"   {'✓' if ok else '✗'} {lab:<32s} obs={obs}")

    # ② 红绿对比:应失败
    print("\n② A-7 反证 —— 红绿对比(应失败)")
    for cid, lab, obs, exp, ok in check_colors(["#FF0000", "#00FF00", "#0000FF"], spec):
        print(f"   {'✓' if ok else '✗'} {lab:<32s} obs={obs}")

    # ③ 图注:合规样例
    good = ("Differentially expressed genes by group. n = 5 biologically "
            "independent samples per group. Data are mean ± SEM. "
            "Two-sided Wilcoxon rank-sum test with BH correction.")
    print("\n③ B/D 图注 —— 合规样例(应通过)")
    for cid, lab, obs, exp, ok in check_legend(good, spec, "test"):
        print(f"   {'✓' if ok else '✗'} {lab:<32s} obs={obs}")

    # ④ 图注:缺误差棒 + n 写成区间(应失败)
    bad = "Differentially expressed genes. n = 3-6. *** p < 0.05."
    print("\n④ B/D 图注 —— 反证(应失败)")
    for cid, lab, obs, exp, ok in check_legend(bad, spec, "test"):
        print(f"   {'✓' if ok else '✗'} {lab:<32s} obs={obs}")

    # ⑤ 命名
    print("\n⑤ §5.7 命名")
    for nm in ["02_deg_volcano.pdf", "volcano.pdf", "02_unknownstep_x.pdf"]:
        for cid, lab, obs, exp, ok in check_name(nm, spec, {"qc", "deg", "enrichment"}):
            print(f"   {'✓' if ok else '✗'} {nm:<24s} {lab}")

    # ⑥ 四格式导出
    print("\n⑥ §5.8 四格式导出 + 文件级检查")
    fig, ax = plt.subplots(figsize=(3.5, 2.6))
    for i in range(3):
        ax.bar([i], [1 + i * 0.5], color=W[i + 1], label=f"g{i}")
    ax.set_ylabel("Expression")
    ax.legend(frameon=False)
    outs = export_all(fig, "02_deg_volcano", os.path.join(ROOT, "figures", "demo"))
    plt.close(fig)
    for k, p in outs.items():
        kind = "vector" if k == "pdf" else "raster"
        for cid, lab, obs, exp, ok in check_file(p, spec, kind):
            print(f"   {'✓' if ok else '✗'} [{k:<4s}] {lab:<30s} obs={obs}")
