#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_figures.py — U07 图件（作图规范 v1.0 · 视觉规范修订）

对治《08.生信分析模块库/出图自查清单.md》六类缺陷（源自 09.SCI文章排版参考/01/不足.txt）：

  D1 文字/标签盖过数据 → 图例**置于轴内数据最空的角**（自动择位），且机器验证
                        框内数据点占比 ≤3%、不与轴内文字/别的图例相压、不出轴框
  D2 文字超出图框     → 固定栏宽 figsize + constrained_layout，文本锁在版心内
  D3 图例过长盖过数据 → 图例条目 ≤6、紧凑排布（小 handle/小行距），禁轴外右侧占位
  D4 图例体系缺失     → 有序列必有图例；多面板图加粗体面板标记；缩写就地定义
  D5 图与图跨页       → 一 Figure 一文件、单页矢量 PDF（保存后校验页数 = 1）
  D6 图间空白过多     → 统一栏宽网格（单栏 89mm / 双栏 183mm），同类图同尺寸

规范来源（2026-09-15 起以 09/03/图片最稳妥配置_照做版.md 与 README_出图工具.md 为最高依据）：
  **矢量是母版，位图是派生**：图表类产出 PDF+SVG 双矢量母版（Type42 嵌字体 / SVG
  字转路径，无 DPI 概念）+ PNG@1200dpi 派生副本（线条图位图规格，矢量直渲非插值）；
  TIFF+LZW 参数卡适用于"设备拍的"照片类位图，图表类不产出（实测 LZW 压不动抗锯齿：
  单栏 10.3MB/双栏 43MB，撞 Wiley 10MB 红线）；
  **JPG 禁用于线条图**（照做版"绝对不要做"表 + 出图工具 check 亦标违规）；
  图中文字 Arial/Helvetica 统一：正文 8pt（底线 7pt）、上下标 ≥6pt、面板标记 10–12pt 加粗；
  线宽 0.5–1.5pt（底线 0.25pt）、禁 background_grid；栏宽 single 85mm / double 174mm、高 ≤170mm；
  色板 Wong 2011（色盲安全）；**单文件 <10MB**（Wiley 硬规定，保存后逐文件校验）；
  投稿提交件 = figures/submission/Fig1..Fig4 / FigS1-2（pdf+svg 双格式，按正文出现顺序命名）。
"""
import io, os, json, textwrap, shutil
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from matplotlib import legend as mlegend

SEED = 20260910
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RES = os.path.join(BASE, "results")
FIG = os.environ.get("FIG_DIR", os.path.join(BASE, "figures"))
os.makedirs(FIG, exist_ok=True)

# ── 栏宽网格（mm→in；09/03 照做版：单栏 8.5cm / 双栏 17.4cm 这组四家通吃）────
COL1, COL2 = 85 / 25.4, 174 / 25.4           # 3.346 in / 6.850 in
H_SINGLE = 3.0                                # 单栏图统一高度（D6：同类图同尺寸）
# ── 字号 / 线宽（09/03 照做版：正文 8pt 底线 7pt、上下标 ≥6pt、面板标记 10–12pt
#    加粗、线宽 0.5–1.5pt 底线 0.25pt）──
FS_MIN, FS_MAX = 7, 8
FS, FS_SMALL, FS_PANEL = 8, 7, 10             # 面板标记 10pt 加粗（规范单列）
LW_MIN, LW_MAX = 0.5, 1.5
LW, LW_THIN, LW_REF = 0.9, 0.6, 0.5           # 曲线 / 轴 / 辅助线（均落 0.5–1.5pt）
# ── 色板 Wong 2011（= Okabe-Ito，色盲安全；出图要求 3.3）─────────────────────
BLUE, VERM, GREY = "#0072B2", "#D55E00", "#999999"
RED = "#D62728"                               # 上调=红（用户 2026-09-15：上调红 / 下调蓝）

plt.rcParams.update({
    # 出图要求 0/3.2：全篇图统一 Arial/Helvetica（Windows=Arial，云端=Liberation Sans
    # 度量兼容，DejaVu 兜底希腊字母/箭头等）；不要 Times、不要中文字体
    "font.family": "sans-serif",
    "font.sans-serif": ["Arial", "Liberation Sans", "Helvetica", "DejaVu Sans"],
    "font.size": FS,
    "axes.titlesize": FS, "axes.labelsize": FS,
    "xtick.labelsize": FS_SMALL, "ytick.labelsize": FS_SMALL,
    "legend.fontsize": FS_SMALL,
    "axes.linewidth": LW_THIN, "axes.grid": False,
    "lines.linewidth": LW,
    "xtick.major.width": LW_THIN, "ytick.major.width": LW_THIN,
    "xtick.major.size": 2.5, "ytick.major.size": 2.5,
    "figure.constrained_layout.use": True,
    "pdf.fonttype": 42, "ps.fonttype": 42,     # C-4：出版 PDF 须 Type0/TrueType，禁 Type3
    "svg.fonttype": "path",                    # 09/03 出图工具：SVG 字转路径，换机不缺字体
})


# ══════════════════════════ 规范层（D1–D8 共用）══════════════════════════════
def new_fig(w=COL1, h=H_SINGLE):
    """D2/D6：按栏宽网格出图；constrained_layout 保证文本不出框、图间可无缝排布。
    同时限制刻度数量（D8 防御：图例移到右侧后绘图区变窄，刻度标签易互相重叠）。"""
    assert abs(w - COL1) < 1e-3 or abs(w - COL2) < 1e-3, "宽度须落在栏宽网格（85/170mm）"
    fig, ax = plt.subplots(figsize=(w, h), constrained_layout=True)
    ax.xaxis.set_major_locator(mticker.MaxNLocator(nbins=4))
    ax.yaxis.set_major_locator(mticker.MaxNLocator(nbins=4))
    return fig, ax


def _place_labels(ax, pts, labels, fontsize=FS_SMALL, italic=True, avoid=()):
    """D7/D8：图内点标签的**像素级贪心避让**。

    逐个标签尝试 8 个候选偏移，取第一个"完全落在坐标轴框内 且 不与已放标签/图例/
    轴内既有文字相交"的位置；全部候选冲突则**放弃该标签**（宁缺毋压），返回放置条数。
    """
    fig = ax.get_figure()
    placed, n = list(avoid), 0
    for (x, y), s in zip(pts, labels):
        got = None
        for dx, dy, va in [(0, 6, "bottom"), (0, -6, "top"), (8, 2, "bottom"),
                           (-8, 2, "bottom"), (0, 16, "bottom"), (0, -16, "top"),
                           (13, -10, "top"), (-13, -10, "top")]:
            ann = ax.annotate(s, (x, y), xytext=(dx, dy), textcoords="offset points",
                              ha="center", va=va, fontsize=fontsize,
                              style="italic" if italic else "normal")
            fig.canvas.draw()
            r = fig.canvas.get_renderer()
            ab, tb = ax.get_window_extent(r), ann.get_window_extent(r)
            ok = (tb.x0 >= ab.x0 and tb.x1 <= ab.x1 and tb.y0 >= ab.y0
                  and tb.y1 <= ab.y1
                  and all(_ov_area(tb, pb) <= 0.0 for pb in placed))
            if ok:
                got = ann; placed.append(tb); break
            ann.remove()
        if got is not None:
            n += 1
    return n


def wrap(s, n):
    """D2/D3：把超长文本按宽度换行，避免横向溢出图框。"""
    s = str(s)
    return "\n".join(textwrap.wrap(s, n)) if len(s) > n else s


# ── 图例择位：**优先右上角空白处**（用户 2026-09-15 规则）；只允许**轴内**候选
#    （轴外右侧会给 constrained_layout 预留空间，把绘图区压窄、图幅右侧空出一大片
#     —— 用户 2026-09-15 明确否决）。候选按此序评估，取"障碍+遮挡"最小者；
#    右上角若被数据/文字占用则自动顺延到次空的角，保证落在真空白处。──
_LEG_LOCS = ("upper right", "upper left", "lower left", "lower right",
             "center right", "center left", "upper center", "lower center")


def _densify(px, step=8.0):
    """把折线在**像素空间**按 ~step 像素间隔加密：长度代理，使"图例压住一段长
    直线段"也能被统计（仅靠顶点会漏检 axhline / 长台阶）。"""
    if len(px) < 2:
        return px
    seg = np.linalg.norm(np.diff(px, axis=0), axis=1)
    total = float(seg.sum())
    if total <= step:
        return px
    cum = np.concatenate([[0.0], np.cumsum(seg)]) / total
    t = np.linspace(0.0, 1.0, max(int(total / step) + 1, 2))
    return np.column_stack([np.interp(t, cum, px[:, 0]), np.interp(t, cum, px[:, 1])])


def _data_px(ax):
    """轴内数据元素的像素坐标，**分两类**返回：
       sc = 散点（每行 = 一个观测点）、ln = 曲线（按 8px 加密，行数与弧长成正比）。
    两类分开统计遮挡比例，语义分别是"挡掉多少点"与"挡掉多少曲线长度"。"""
    sc, ln = [], []
    for c in ax.collections:
        try:
            off = np.asarray(c.get_offsets(), float)
        except Exception:
            continue
        # 只认真正的散点（fill_between 的 PolyCollection offsets 恒为 [[0,0]]）
        if off.ndim == 2 and len(off) >= 2 and c.get_visible():
            sc.append(ax.transData.transform(off[:, :2]))
    for l in ax.lines:
        if not l.get_visible() or l.get_transform() is not ax.transData:
            continue                                   # 排除 axhline 等混合坐标参考线
        xy = np.asarray(l.get_xydata(), float)
        if xy.ndim == 2 and len(xy) >= 2:
            ln.append(_densify(ax.transData.transform(xy[:, :2])))
    return (np.vstack(sc) if sc else np.empty((0, 2)),
            np.vstack(ln) if ln else np.empty((0, 2)))


def _blk(px, b):
    """落在 bbox 内的数据元素数（px 为像素坐标 Nx2）。"""
    if len(px) == 0:
        return 0
    m = ((px[:, 0] >= b.x0) & (px[:, 0] <= b.x1)
         & (px[:, 1] >= b.y0) & (px[:, 1] <= b.y1))
    return int(m.sum())


def _block_ratio(data, lb):
    """图例框对数据的遮挡比例（0–1）：散点取点数比，曲线取弧长比，取大者。"""
    sc, ln = data
    ratios = []
    for px, w in ((sc, 1.0), (ln, 1.0)):        # 两类各自独立；曲线已按弧长加密
        if len(px):
            ratios.append(_blk(px, lb) * w / len(px))
    return max(ratios) if ratios else 0.0


# 图例可容忍的数据遮挡上限（散点/曲线各自）：超过即判 D1 违规
BLOCK_MAX = 0.03


def _leg_kw(ncol, over=None):
    """紧凑图例样式：小 handle、小行距、无边框（占位越小越不挡数据）。
    over 用于逐图覆盖（如"气泡大小图例"的大圆点需要更宽的 handle 槽与更松的行距，
    否则圆点会溢出行槽、压到自己的数值标签上 —— 用户 2026-09-15 反馈）。"""
    kw = dict(frameon=False, ncol=ncol, handlelength=1.0, handletextpad=0.4,
              labelspacing=0.3, borderpad=0.2, borderaxespad=0.3,
              columnspacing=1.0, fontsize=FS_SMALL, title_fontsize=FS_SMALL)
    kw.update(over or {})
    return kw


def _mk_legend(ax, handles, labels, loc, ncol, title, keep, bbox=None, over=None):
    """建图例：keep=True 时用 add_artist（不顶掉同轴已有图例，供双图例图用）。
    bbox=（axes 分数坐标）时改走 bbox_to_anchor 精确锚定——两个图例要"上下紧排
    且互不重叠"必须用锚点，matplotlib 的 9 个 loc 只能贴轴角，做不到。"""
    kw = dict(loc=loc, title=title, **_leg_kw(ncol, over))
    if bbox is not None:
        kw.update(bbox_to_anchor=bbox, bbox_transform=ax.transAxes)
    if keep:
        leg = mlegend.Legend(ax, handles, labels, **kw)
        ax.add_artist(leg)
    else:
        leg = ax.legend(handles, labels, **kw)
    return leg


def legend_in(ax, handles=None, labels=None, ncol=1, prefer=None, avoid=(),
              title=None, keep=False, anchor=None, gap=3.0, leg_kw=None):
    """D1/D3：图例置于**轴内空白角**，位置由机器择定（不占版心外空间）。

    评分 =（与既有障碍相交数，数据遮挡比例）字典序最小；障碍包括轴内文字
    （基因标签 / P 值 / 风险表 / 轴内参考线文字）、先前已放的图例。

    anchor=（像素 bbox）时，先试"**紧贴该图例下沿、右对齐**"（gap pt 间距），
    即两个图例在同一个角里上下紧排成一块、互不重叠（用户 2026-09-15 规则：
    图例既不能放错位置，也不能互相压）；若该落点压数据/撞障碍，则沿同一列
    逐级下移，全不行才退回常规择优。
    返回图例 bbox 列表，供后续 `_place_labels()` 继续避让。
    """
    if handles is None:
        handles, labels = ax.get_legend_handles_labels()
    if not handles:
        return []
    assert len(handles) <= 6, f"D3 违规：图例 {len(handles)} 条 > 6"
    fig = ax.get_figure()
    r = fig.canvas.get_renderer()
    fig.canvas.draw()
    data = _data_px(ax)
    ab = ax.get_window_extent(r)
    barriers = list(avoid) + ([anchor] if anchor is not None else []) \
        + [t.get_window_extent(r) for t in ax.texts
           if str(t.get_text()).strip() and t.get_visible()]
    cands = []
    if anchor is not None:                       # 首选：紧贴 anchor 下沿右对齐
        _xa = min(1.0, (anchor.x1 - ab.x0) / (ab.x1 - ab.x0))
        for _g in (gap, gap + 8.0, gap + 20.0):
            _ya = (anchor.y0 - _g / 72.0 * fig.dpi - ab.y0) / (ab.y1 - ab.y0)
            cands.append(("upper right", (_xa, _ya)))
    cands += [(l, None) for l in ([prefer] if prefer else [])
              + [l for l in _LEG_LOCS if l != prefer]]
    best = None
    for loc, bb in cands:
        leg = _mk_legend(ax, handles, labels, loc, ncol, title, keep, bb, leg_kw)
        fig.canvas.draw()
        lb = leg.get_window_extent(r)
        clash = sum(1 for b in barriers if _ov_area(lb, b) > 2.0)
        out = (lb.x0 < ab.x0 - 1 or lb.x1 > ab.x1 + 1
               or lb.y0 < ab.y0 - 1 or lb.y1 > ab.y1 + 1)
        score = (clash + (1 if out else 0), round(_block_ratio(data, lb), 4))
        leg.remove()
        if best is None or score < best[0]:
            best = (score, loc, bb)
        if score == (0, 0.0):
            break
    leg = _mk_legend(ax, handles, labels, best[1], ncol, title, keep, best[2], leg_kw)
    fig.canvas.draw()
    lb = leg.get_window_extent(r)
    print(f"    [图例] loc={best[1]:<12s} 障碍={best[0][0]} 遮挡={best[0][1]:.2%}"
          f" 占轴宽 {(lb.x1 - lb.x0) / (ab.x1 - ab.x0):.0%}")
    return [lb]


def panel(ax, letter):
    """D4：多面板图的粗体面板标记（置于轴外左上，8pt）。单面板图不调用。"""
    ax.text(-0.16, 1.04, letter, transform=ax.transAxes, fontsize=FS_PANEL,
            fontweight="bold", va="bottom", ha="left")


def _overlap(b1, b2):
    return b1.x0 < b2.x1 and b2.x0 < b1.x1 and b1.y0 < b2.y1 and b2.y0 < b1.y1


def _ov_area(b1, b2):
    """两 bbox 相交面积（pt²）——用于容忍 1pt 级的擦边，只报真实重叠。"""
    dx = min(b1.x1, b2.x1) - max(b1.x0, b2.x0)
    dy = min(b1.y1, b2.y1) - max(b1.y0, b2.y0)
    return dx * dy if dx > 0 and dy > 0 else 0.0


def _texts(ax):
    """该轴上全部可见文字（标题/轴标/刻度标签/图内标注）。"""
    out = [ax.title, ax.xaxis.label, ax.yaxis.label]
    out += list(ax.get_xticklabels()) + list(ax.get_yticklabels()) + list(ax.texts)
    return [t for t in out if t is not None and t.get_visible() and str(t.get_text()).strip()]


def audit(fig, name):
    """D1/D2/D3/D4/D6 + 规范区间（字号/线宽/禁网格）的机器自检；返回问题列表。"""
    fig.canvas.draw()
    r = fig.canvas.get_renderer()
    issues = []
    # D2：整幅内容（含全部文字）必须落在画布内。用 get_tightbbox 判定——
    #     逐条 Text 判定会误伤 xlim 之外、本就不绘制的越界刻度标签（实测假阳性）。
    tb = fig.get_tightbbox(r)                          # 单位：英寸
    w, h = fig.get_size_inches()
    if tb.x0 < -0.02 or tb.y0 < -0.02 or tb.x1 > w + 0.02 or tb.y1 > h + 0.02:
        issues.append(f"D2 内容出框：tight={tuple(round(v, 2) for v in tb.bounds)}")
    for ax in fig.axes:
        if len(fig.axes) > 1 and ax.texts == []:
            issues.append("D4 多面板图缺面板标记")
        texts = ax.get_xticklabels() + ax.get_yticklabels() + [ax.xaxis.label, ax.yaxis.label]
        if ax.get_title():
            texts.append(ax.title)
        for t in texts:                                # 规范：字号 ∈ [5,8]
            if not t.get_text() or not t.get_visible():
                continue                               # 跳过空串与越界 tick 的隐形 Text
            if not (FS_MIN - 1e-6 <= t.get_fontsize() <= FS_PANEL + 1e-6):
                issues.append(f"字号越界 {t.get_fontsize():g}pt：{t.get_text()[:14]}")
        for ln in ax.lines:                            # 规范：线宽 ≤ 1.0pt
            if ln.get_linewidth() > LW_MAX + 1e-9:
                issues.append(f"线宽越界 {ln.get_linewidth():g}pt")
        for c in ax.collections:
            lws = np.atleast_1d(c.get_linewidths())
            if lws.size and lws.max() > LW_MAX + 1e-9:
                issues.append(f"散点线宽越界 {lws.max():g}pt")
        if any(g.get_visible() for g in ax.get_xgridlines() + ax.get_ygridlines()):
            issues.append("存在背景网格（规范禁止）")
        ab = ax.get_window_extent(r)                   # D7：图内标注须落在坐标轴框内
        for t in ax.texts:
            if not str(t.get_text()).strip() or not t.get_visible():
                continue
            tb = t.get_window_extent(r)
            if tb.x0 < ab.x0 - 1 or tb.x1 > ab.x1 + 1 or tb.y0 < ab.y0 - 1 or tb.y1 > ab.y1 + 1:
                issues.append(f"D7 图内文字超出坐标轴框：{str(t.get_text())[:14]}")
    legends = [(ax, leg) for ax in fig.axes for leg in ax.get_children()
               if isinstance(leg, mlegend.Legend)]
    legends += [(None, leg) for leg in fig.legends]
    # D8：文字互不相压（刻度标签 / 图内标注 / 图例文字，容忍 ≤2pt² 擦边）
    _boxes = [(t, t.get_window_extent(r)) for ax in fig.axes for t in _texts(ax)]
    _boxes += [(t, t.get_window_extent(r)) for _, leg in legends for t in leg.get_texts()
               if str(t.get_text()).strip()]
    for _i in range(len(_boxes)):
        for _j in range(_i + 1, len(_boxes)):
            if _overlap(_boxes[_i][1], _boxes[_j][1]) and _ov_area(_boxes[_i][1], _boxes[_j][1]) > 2.0:
                issues.append(f"D8 文字重叠：{str(_boxes[_i][0].get_text())[:10]}"
                              f" ↔ {str(_boxes[_j][0].get_text())[:10]}")
    # D1：图例**必须在轴内**且不挡数据/不压图内文字。
    #     （旧判据"图例不得与坐标轴重叠"= 强制轴外 → 绘图区被压窄、图幅右侧一片空白，
    #      用户 2026-09-15 明确否决；改为度量"遮挡了多少数据"才是真要求。）
    for ax, leg in legends:
        if len(leg.get_texts()) > 6:                    # D3
            issues.append("D3 图例条目 > 6")
        lb = leg.get_window_extent(r)
        if ax is None:
            W, H = fig.get_size_inches()[0] * fig.dpi, fig.get_size_inches()[1] * fig.dpi
            if lb.x0 < -1 or lb.y0 < -1 or lb.x1 > W + 1 or lb.y1 > H + 1:
                issues.append("D1 画布级图例超出画布")
            continue
        ab = ax.get_window_extent(r)
        if (lb.x0 < ab.x0 - 1 or lb.x1 > ab.x1 + 1
                or lb.y0 < ab.y0 - 1 or lb.y1 > ab.y1 + 1):
            issues.append(f"D1 图例超出坐标轴框：{leg.get_texts()[0].get_text()[:14]}")
        _sc, _ln = _data_px(ax)
        _blk_r = _block_ratio((_sc, _ln), lb)
        if _blk_r > BLOCK_MAX:                          # D1：遮挡数据 ≤3%
            issues.append(f"D1 图例遮挡数据 {_blk_r:.1%}"
                          f"（点 {_blk(_sc, lb)}/{len(_sc)}、"
                          f"线 {_blk(_ln, lb)}/{len(_ln)}）")
        for t in ax.texts:                              # D1：不得压住图内文字
            if not str(t.get_text()).strip() or not t.get_visible():
                continue
            if _ov_area(lb, t.get_window_extent(r)) > 2.0:
                issues.append(f"D1 图例压住图内文字：{str(t.get_text())[:14]}")
    # D9：版心利用率——坐标轴宽度须占画布宽度 ≥55%（防"图例占位把绘图区压窄、
    #     图幅空一大片"这类结构性浪费复发）
    fw = fig.get_size_inches()[0] * fig.dpi
    for ax in fig.axes:
        ab = ax.get_window_extent(r)
        frac = (ab.x1 - ab.x0) / fw
        if frac < 0.55:
            issues.append(f"D9 绘图区横向利用率仅 {frac:.0%}（<55%，图幅被浪费）")
    for ax in fig.axes:                                 # D4：有序列必有图例
        if len(ax.get_legend_handles_labels()[1]) >= 2 and not legends:
            issues.append("D4 多序列缺图例")
    if not any(abs(w - c) < 1e-3 for c in (COL1, COL2)):  # D6：栏宽网格
        issues.append(f"D6 宽度 {w:.2f}in 不在栏宽网格")
    if h * 25.4 > 170 + 1:
        issues.append("高度 > 170mm")
    print(f"  [审计{'✗' if issues else '✓'}] {name}"
          + ("：" + "；".join(issues) if issues else "：D1–D8 + 规范区间通过"))
    return issues


def save(fig, name):
    from PIL import Image
    issues = audit(fig, name)
    # 09/03 出图工具核心思路：**矢量是母版，位图是派生**。图表类产出 PDF+SVG 双矢量
    # 母版（Type42 嵌字体 / SVG 字转路径，均无 DPI 概念）+ PNG@1200dpi 派生副本
    # （线条图位图规格；由矢量母版直接渲染，非插值放大）。TIFF+LZW 参数卡适用于
    # "设备拍的"照片类位图 —— 图表类存 TIFF 即使 LZW 也压不动抗锯齿（实测单栏
    # 10.3MB、双栏 43MB，撞 Wiley 10MB 红线）；JPG 有损噪点（工具 check 亦标线条图
    # 违规），二者对图表类均不产出。
    for ext, kw in [("pdf", {}), ("svg", {}), ("png", {})]:
        dpi = 1200 if ext == "png" else 300              # 线条图位图 1200dpi（照做版参数卡）
        p = os.path.join(FIG, f"{name}.{ext}")
        fig.savefig(p, dpi=dpi, **kw)                   # 不裁框：尺寸=栏宽网格（D6）
        if ext == "png":                                # C-6 色彩模式：RGB（matplotlib 默认 RGBA）
            with open(p, "rb") as f:                    # 先读入内存，避免 PIL 句柄与写回冲突（曾致 Errno 22）
                data = f.read()
            im = Image.open(io.BytesIO(data))
            if im.mode != "RGB":
                bg = Image.new("RGB", im.size, (255, 255, 255))
                bg.paste(im, mask=im.split()[-1] if im.mode in ("RGBA", "LA") else None)
                buf = io.BytesIO()
                bg.save(buf, format="PNG", dpi=(dpi, dpi))
                tmp = p + ".tmp"
                with open(tmp, "wb") as f:
                    f.write(buf.getvalue())
                os.replace(tmp, p)
                im.close()
        _mb = os.path.getsize(p) / 1048576              # 09/03 照做版：单文件 <10MB（Wiley 硬规定）
        if _mb > 10:
            issues.append(f"单文件 {_mb:.1f}MB > 10MB（Wiley 硬规定，按降级顺序处理）")
    try:                                                # D5：一 Figure 一文件、单页
        from pypdf import PdfReader
        n = len(PdfReader(os.path.join(FIG, f"{name}.pdf")).pages)
        if n != 1:
            issues.append(f"D5 PDF {n} 页（应单页）")
    except ImportError:
        pass
    # 09/03 照做版 §文件命名：投稿件按正文出现顺序命名（Fig1…；补充材料 FigS1…）。
    # 复制双矢量母版（PDF+SVG；字体嵌入/字转路径已由 rcParams 保证）。
    _alias = SUBMIT_ALIAS.get(name)
    if _alias:
        _sub = os.path.join(FIG, "submission")
        os.makedirs(_sub, exist_ok=True)
        for _ve in ("pdf", "svg"):
            shutil.copy2(os.path.join(FIG, f"{name}.{_ve}"),
                         os.path.join(_sub, f"{_alias}.{_ve}"))
    plt.close(fig)
    print(f"  图件：{name} 母版 pdf+svg + png@1200dpi"
          + (f" → submission/{_alias}.pdf/.svg" if _alias else ""))
    return issues


# ══════════════════════════ 图件 ════════════════════════════════════════════
# 09/03 照做版 §文件命名：投稿件按正文出现顺序命名（Fig1…；补充材料 FigS1…）
SUBMIT_ALIAS = {"01_deg_volcano": "Fig1", "02_enrichment_dotplot": "Fig2",
                "03_survival_km_risk": "Fig3", "04_performance_roc_cv": "Fig4",
                "05_performance_calibration_curve": "FigS1",
                "06_dca_net_benefit": "FigS2"}
R = json.load(open(os.path.join(RES, "results.json"), encoding="utf-8"))
_audit_issues = []

# ---------- 图1 火山图（deg） ----------
d = pd.read_csv(os.path.join(RES, "T02_差异表达全表.csv"))
d["-log10P"] = -np.log10(d["P"].clip(lower=1e-300))
fig, ax = new_fig(COL1, H_SINGLE)
m = ~d["DEG"].astype(bool)
ax.scatter(d.loc[m, "log2FC"], d.loc[m, "-log10P"], s=2, c=GREY, alpha=0.35, linewidths=0)
up = d["DEG"].astype(bool) & (d["log2FC"] > 0)
dn = d["DEG"].astype(bool) & (d["log2FC"] < 0)
ax.scatter(d.loc[dn, "log2FC"], d.loc[dn, "-log10P"], s=3, c=BLUE, linewidths=0,
           label=f"Down-regulated (n = {int(dn.sum())})")
ax.scatter(d.loc[up, "log2FC"], d.loc[up, "-log10P"], s=3, c=RED, linewidths=0,
           label=f"Up-regulated (n = {int(up.sum())})")
ax.axhline(-np.log10(0.05), ls="--", lw=LW_REF, c="k")
ax.axvline(0.585, ls="--", lw=LW_REF, c="k")
ax.axvline(-0.585, ls="--", lw=LW_REF, c="k")
ax.set_xlabel("log2 fold change (tumour vs normal)")
ax.set_ylabel("-log10 P (Welch t-test)")
# 出图要求：图内不得出现图题（图题/图注写在稿件正文里）——标题移入图注。
# 注：T02_DEG.value 是 {'总数','上调','下调'} 字典，直接串进标题会渲染出超长文本
#     （原缺陷 D2 源头）；DEG 计数已由图例承担。
# 出图要求 4.6：火山图须有关键基因标签；基因名斜体（3.2）。每侧取 -log10P 前 3 个。
# 位置由 `_place_labels()` 像素级避让决定（D7 不出框 + D8 不重叠；全冲突则弃标）。
_pts, _labs = [], []
for _msk in (up, dn):
    for _i, _r in d[_msk].nlargest(3, "-log10P").iterrows():
        _pts.append((_r["log2FC"], _r["-log10P"])); _labs.append(str(_r["symbol"]))
_avoid = legend_in(ax, ncol=1)   # 图例先在轴内择位（不占版心外空间）
_place_labels(ax, _pts, _labs, avoid=_avoid)   # 标签再避让（含图例框）
_audit_issues += save(fig, "01_deg_volcano")

# ---------- 图2 富集点图（enrichment） ----------
try:
    _up = pd.read_csv(os.path.join(RES, "T04_富集_上调.csv"))
    _dn = pd.read_csv(os.path.join(RES, "T04_富集_下调.csv"))
    sel = pd.concat([_up.assign(grp="Up-regulated"), _dn.assign(grp="Down-regulated")])
    sel = sel.sort_values("Adjusted P-value").groupby("grp").head(8)
    sel = sel.sort_values(["grp", "Adjusted P-value"], ascending=[True, False]).reset_index(drop=True)
    # 纵坐标槽位按**标签实际行数**分配：wrap 后各标签 1–3 行不等，固定行距会令多行
    # 标签互相叠压（用户 2026-09-14 反馈"纵坐标文字叠起来了"的根因）。
    # 出图要求 4.6：富集图须含**基因数**（气泡大小 + 大小图例）与颜色图例。
    # 基因数取 T04 的 Overlap 分子（如 "38/109" → 38）。
    sel["n_gene"] = sel["Overlap"].astype(str).str.split("/").str[0].astype(int)
    labs = [wrap(t, 40) + f" (n={int(c)})" for t, c in zip(sel["Term"], sel["n_gene"])]
    ln = np.array([l.count("\n") + 1 for l in labs], float)
    ypos = np.concatenate([[0.0], np.cumsum(ln)])[:-1]   # 行 i 的起点 = 前 i 个标签占的总行数
    # 图高随总行数自适应：行高取 1.7 倍 FS_SMALL（系数随字号 6→7pt 等比校准自 2.0，
    # 保持绝对行距 ~12pt 不变，防高度超 170mm 上限；constrained_layout 会扣掉标题/
    # 轴标的固定余量），另留 1.3in 版面余量
    fig, ax = new_fig(COL2, max(3.3, float(ln.sum()) * FS_SMALL * 1.7 / 72 + 1.3))
    _nmin = float(sel["n_gene"].min())
    _sz = 10 + (sel["n_gene"].astype(float) - _nmin) * 2.2      # 气泡面积随基因数增大
    for grp, col in [("Up-regulated", RED), ("Down-regulated", BLUE)]:
        s = (sel["grp"] == grp).to_numpy()
        ax.scatter(sel.loc[s, "Adjusted P-value"], ypos[s], s=_sz[s].to_numpy(), c=col,
                   linewidths=0, label=f"{grp} genes (n = {int(s.sum())})")
    # 刻度须对准**槽位中心**（ypos + (行数-1)/2）：matplotlib 多行标签按中心对齐刻度，
    # 锚在槽首会向上凸出半格、与上一标签交叠（7pt 下实测触发 D8；6pt 时恰好擦边未报）
    ax.set_yticks(ypos + (ln - 1) / 2.0)
    ax.set_yticklabels(labs, fontsize=FS_SMALL)
    ax.set_ylim(float(ypos[-1] + ln[-1]) - 0.35, -0.75)
    ax.set_xscale("log")
    ax.set_xlabel("Adjusted P-value (Benjamini–Hochberg)")
    # 双图例**同角堆叠在右上空白区**：方向（颜色）在上、基因数（气泡大小）紧贴其
    # 下沿右对齐，两块互不重叠（用户 2026-09-15 反馈：基因数图例位置错、还叠压方向
    # 图例与数据点 —— 左下角压住 Regulation Of Angiogenesis 那颗大蓝点）。
    # 方向图例改用**等大小**圆形 handle（红=上调 / 蓝=下调）：原散点 handle 会随基因数
    # 变大小，既在紧凑行距下令两枚圆点互相叠压，又与"大小=基因数"的语义混淆
    # （用户 2026-09-15 反馈：图例重叠、圆圈大小不等、位置不对）。
    from matplotlib.lines import Line2D
    _n_up = int((sel["grp"] == "Up-regulated").sum())
    _n_dn = int((sel["grp"] == "Down-regulated").sum())
    _MS = 5.0
    _h_dir = [Line2D([], [], marker="o", ls="", mfc=RED, mec=RED, ms=_MS,
                     label=f"Up-regulated genes (n = {_n_up})"),
              Line2D([], [], marker="o", ls="", mfc=BLUE, mec=BLUE, ms=_MS,
                     label=f"Down-regulated genes (n = {_n_dn})")]
    _a1 = legend_in(ax, _h_dir, [h.get_label() for h in _h_dir], ncol=1,
                    prefer="upper right")                       # 方向图例 → 右上空白角
    _ref = sorted({int(sel["n_gene"].min()), int(sel["n_gene"].median()),
                   int(sel["n_gene"].max())})
    _sh = [Line2D([], [], marker="o", ls="", mfc="none", mec="0.35",
                  ms=float(np.sqrt(10 + (v - _nmin) * 2.2)), label=str(v)) for v in _ref]
    # 大小图例的 handle 槽宽 / 行距须随**最大气泡直径**放宽：默认 handlelength=1.0、
    # labelspacing=0.3（6pt 字号下的 6pt / 1.8pt）装不下 ~11.6pt 的大圆点 —— 圆点会
    # 溢出槽位压住自己的数值标签、上下行圆点也会互相叠压（用户 2026-09-15 反馈）。
    _dmax = float(np.sqrt(10 + (max(_ref) - _nmin) * 2.2))         # 最大气泡直径 pt
    legend_in(ax, _sh, [str(v) for v in _ref], ncol=1, title="Gene count",
              prefer="upper right", avoid=_a1, keep=True, anchor=_a1[0],
              leg_kw=dict(handlelength=_dmax / FS_SMALL + 0.4,
                          labelspacing=_dmax / FS_SMALL - 0.8))
    _audit_issues += save(fig, "02_enrichment_dotplot")
except Exception as ex:
    print("图2 跳过:", ex)

# ---------- 图3 KM 曲线（survival） ----------
k = pd.read_csv(os.path.join(RES, "T12_OOF评分表.csv"))


def km(t, e):
    t, e = np.asarray(t, float), np.asarray(e, int)
    ts = np.unique(t[e == 1]); surv = 1.0
    out_t, out_s, out_lo, out_hi = [0.0], [1.0], [1.0], [1.0]
    cum_h = 0.0
    for tt in ts:
        n_r = (t >= tt).sum(); n_e = ((t == tt) & (e == 1)).sum()
        surv *= (1 - n_e / n_r)
        cum_h += n_e / (n_r * (n_r - n_e)) if n_r > n_e else 0
        se = surv * np.sqrt(cum_h)
        out_t.append(tt); out_s.append(surv)
        out_lo.append(max(surv - 1.96 * se, 0)); out_hi.append(min(surv + 1.96 * se, 1))
    # 曲线须延伸至该组**末次随访**（最大观察时间）：否则当末次观察为删失时曲线会
    # 提前在最后事件处截断，与下方风险人数表(number at risk)自相矛盾，亦不符 SCI KM 惯例。
    tmax = float(t.max())
    if tmax > out_t[-1]:
        out_t.append(tmax); out_s.append(out_s[-1])
        out_lo.append(out_lo[-1]); out_hi.append(out_hi[-1])
    return np.array(out_t), np.array(out_s), np.array(out_lo), np.array(out_hi)


med = k["score_oof"].median()
hi = k[k["score_oof"] > med]; lo = k[k["score_oof"] <= med]
p_km = R["T06_KM"]["value"]["P"]
cox = R["T06_Cox_评分"]["value"]
# 出图要求 4.6：KM 曲线须含 log-rank P、HR (95% CI) 与风险人数表（number at risk）。
# 曲线 + 风险表用上下双轴（sharex）；图题移入图注（图内不得出现图题）。
fig, (ax, axt) = plt.subplots(2, 1, figsize=(COL1, 3.7), sharex=True,
                              height_ratios=[3.0, 0.8], constrained_layout=True)
# 图例标签只留组名+n（8pt 下带 events 的长标签使右上角放不下、图例被挤到左侧压曲线
# —— 实测遮挡 14.6%；各組事件数由图注与统计文本承担）
for grp, c, lab in [(hi, VERM, f"High risk (n = {len(hi)})"),
                    (lo, BLUE, f"Low risk (n = {len(lo)})")]:
    T, S, L, H = km(grp["rfs_days"], grp["event"])
    ax.step(T, S, where="post", c=c, lw=LW, label=lab)
    ax.fill_between(T, L, H, step="post", alpha=0.15, color=c, linewidth=0)
    # 删失标记(censor marks)：在删失时点画短竖线，置于当时生存估计处（SCI KM 常规）。
    tc = np.sort(grp["rfs_days"].to_numpy()[grp["event"].to_numpy() == 0])
    for _tt in tc:
        _s = float(S[T <= _tt][-1]) if np.any(T <= _tt) else 1.0
        ax.plot([_tt, _tt], [_s - 0.025, _s + 0.025], c=c, lw=LW, solid_capstyle="butt")
ax.text(0.98, 0.04, f"Log-rank P = {p_km:.1e}\nHR = {cox['HR']:.3f}"
        f" (95% CI {cox['CI95'][0]:.3f}\u2013{cox['CI95'][1]:.3f})",
        transform=ax.transAxes, ha="right", va="bottom", fontsize=FS_SMALL)
ax.set_ylabel("Relapse-free survival")
ax.set_xlim(left=0); ax.set_ylim(0, 1.02)
legend_in(ax, ncol=1)                     # 默认偏好右上空白角
# 风险人数表：与横轴共享数据坐标。组名**单独成行**（原与首个数字同行 → D8 重叠），
# 端点数字左/右对齐（居中会越出框 → D7）。
tmax = int(k["rfs_days"].max()); rt = [0, tmax // 3, 2 * tmax // 3, tmax]
ax.set_xticks(rt)
axt.set_ylim(0, 5.6); axt.set_yticks([])   # 末行须离底边 ≥ 半行高，否则压框（D7）
for _sp in ("top", "right", "left"):
    axt.spines[_sp].set_visible(False)
axt.set_xlabel("Days to relapse or censoring")
axt.text(0, 5.0, "No. at risk", fontsize=FS_SMALL, ha="left", va="center")
for _base, (_g, _nm) in [(4.0, (hi, "High risk")), (2.0, (lo, "Low risk"))]:
    axt.text(0, _base, _nm, fontsize=FS_SMALL, ha="left", va="center")
    for _t in rt:
        _ha = "left" if _t == rt[0] else ("right" if _t == rt[-1] else "center")
        axt.text(_t, _base - 1.0, str(int((_g["rfs_days"] >= _t).sum())),
                 fontsize=FS_SMALL, ha=_ha, va="center")
_audit_issues += save(fig, "03_survival_km_risk")

# ---------- 图4 ROC（performance） ----------
from sklearn.metrics import roc_curve
fpr1, tpr1, _ = roc_curve(k["event"], k["score_oof"])
fpr0, tpr0, _ = roc_curve(k["event"], k["score_base"])
a1 = R["T12_CV_AUC"]["value"]["模型"]; a0 = R["T12_CV_AUC"]["value"]["基线"]
fig, ax = new_fig(COL1, H_SINGLE)
ax.plot(fpr0, tpr0, c=BLUE, lw=LW, ls="--", label=f"Clinical baseline (AUC = {a0:.3f})")
ax.plot(fpr1, tpr1, c=VERM, lw=LW, label=f"Risk score (AUC = {a1:.3f})")
ax.plot([0, 1], [0, 1], c=GREY, lw=LW_REF, ls=":")
ax.set_xlabel("1 - specificity"); ax.set_ylabel("Sensitivity")
ax.set_xlim(-0.02, 1.02); ax.set_ylim(-0.02, 1.02)
legend_in(ax, ncol=1)                     # 默认偏好右上空白角
_audit_issues += save(fig, "04_performance_roc_cv")

# ---------- 图5 校准曲线（performance，补充材料） ----------
cal_p = os.path.join(RES, "T13b_校准分位.csv")
if os.path.exists(cal_p):
    cal = pd.read_csv(cal_p)
    fig, ax = new_fig(COL1, H_SINGLE)
    ax.plot([0, 1], [0, 1], c=GREY, lw=LW_REF, ls=":", label="Ideal calibration")
    ax.scatter(cal["p_mean"], cal["obs_rate"], s=22, c=VERM, zorder=3, linewidths=0,
               label="Observed (quintile mean)")
    ax.set_xlabel("Predicted probability (out-of-fold)")
    ax.set_ylabel("Observed relapse rate")
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    legend_in(ax, ncol=1)                 # 默认偏好右上空白角
    _audit_issues += save(fig, "05_performance_calibration_curve")
else:
    print("图5 跳过：缺 T13b_校准分位.csv")

# ---------- 图6 决策曲线（dca，补充材料） ----------
dca_p = os.path.join(RES, "T13c_DCA曲线.csv")
if os.path.exists(dca_p):
    dc = pd.read_csv(dca_p)
    fig, ax = new_fig(COL1, H_SINGLE)
    ax.axhline(0, c=GREY, lw=LW_REF, ls=":", label="Treat none")
    ax.plot(dc["threshold"], dc["NB_all"], c=BLUE, lw=LW, ls="--", label="Treat all")
    ax.plot(dc["threshold"], dc["NB_model"], c=VERM, lw=LW, label="Risk score")
    ax.set_xlabel("Threshold probability"); ax.set_ylabel("Net benefit")
    legend_in(ax, ncol=1)                 # 默认偏好右上空白角
    _audit_issues += save(fig, "06_dca_net_benefit")
else:
    print("图6 跳过：缺 T13c_DCA曲线.csv")

print("全部图件完成 →", FIG)
if _audit_issues:
    print(f"！！视觉审计存在 {len(_audit_issues)} 项问题，见上（应修复而非放行）")
    raise SystemExit(1)
print("视觉审计：D1–D6 全部通过")
