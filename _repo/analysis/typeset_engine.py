#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""typeset_engine.py — SCI 预印本 PDF 排版引擎（内化自 09.SCI文章排版参考/01 的规范与模板）

规范来源：09.SCI文章排版参考/01/SCI预印本PDF排版规范与复用指南.md
  A4 / 54pt 四边距 / 双程页码（Page X of Y）/ 层级字色（#0f172a/#0072B2/#334155）/
  图注绑定 KeepTogether / 参考文献悬挂缩进 / 三线表斑马纹
本内化版增补：① 字体注册（多候选探测 + **真嵌入** + CJK 覆盖实测；**禁止**回落 base-14）；
  ② 页眉可配置；③ 声明（Declarations）节；④ 正文双端对齐；⑤ 构建后 PDF 自检。

字体纪律（两条，均有实证）：
  · run 34796985194：`fonts-noto-cjk` 装在编译之后 → 引擎静默回落 base-14 → **中文整段丢失**
    （PDF 中文字符数 = 0）。→ 候选逐个探测并**真嵌入**；禁 base-14；构建后自检。
  · 用户 2026-09-14（黑框）：主字体**缺字形**时 PDF 文本层仍可抽取，但画出来是 `.notdef`
    方框 —— 只看"中文字符数/是否嵌入"抓不到。→ 注册**全部可用字体**，`_wrap()` 逐字选
    覆盖字体；构建前 `assert_glyph_coverage()` 断言**字符集全覆盖**，缺字即抛错。
"""
import os, re
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Image as RLImage,
                                Table, TableStyle, PageBreak, KeepTogether, HRFlowable)
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont, TTFError
from PIL import Image

HEADER_TEXT = "PREPRINT MANUSCRIPT DRAFT"

# 版面基线（2026-09-14 终版，用户裁定："排版定稿观感"优先）：
# PDF = 排版定稿：A4、54pt 四边距（版心 171.9mm，恰好容下 170mm 双栏图 → 1.0× 零缩放）、
#       衬线 Times/宋体、正文 10pt/14.5 两端对齐（配合 wordWrap='CJK'）；
# docx = 投稿工作稿：TNR 12pt + 双倍行距 + 连续行号（09/02 排版要求 §1 对 Word 稿的要求，
#       由 export_manuscript.style_submission 落实）。两套口径各归其位，不再互相套用。
MARGIN_PT = 54


def _mpl_ttf(name):
    """matplotlib 自带 TTF 路径（保证存在，作最后兜底；无 CJK 覆盖）。"""
    try:
        import matplotlib
        return os.path.join(matplotlib.get_data_path(), "fonts", "ttf", name)
    except Exception:
        return ""


# 候选字体（优先级从上到下）：逐个探测**存在性**再注册；全部失败即抛错。
# 反面教训（run 34796985194）：原实现只探一个 Noto 路径，探不到就静默回落 base-14
# Helvetica —— base-14 既不嵌入、也无 CJK，导致中文正文被整段丢弃（PDF 中文字符数=0）。
#
# SCI 版式选型（用户 2026-09-14 反馈"不像 SCI 排版"）：**拉丁衬线作主字体**，
# 中文由宋体类经 `_wrap()` 逐段承接 —— 西文/数字/符号用 Times 类衬线、中文用宋体，
# 这正是逐字回退机制的另一主用途（无衬线黑体是网页版式，不是 SCI 版式）。
_FONT_CANDIDATES = [
    # ⓪ 拉丁衬线主字体
    ("C:/Windows/Fonts/times.ttf", "C:/Windows/Fonts/timesbd.ttf", None),        # Windows Times
    ("/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf",
     "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf", None),     # 云端（Times 度量兼容）
    # ① 中文宋体类（衬线；粗体由黑体承接）
    ("C:/Windows/Fonts/simsun.ttc", "C:/Windows/Fonts/simhei.ttf", 0),           # Windows 宋体
    ("/usr/share/fonts/truetype/arphic/uming.ttc",
     "/usr/share/fonts/truetype/arphic/uming.ttc", 0),                           # 云端 AR PL UMing（明体）
    # ② 其他可嵌入 CJK / 备用
    ("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
     "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc", 0),
    ("/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
     "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf", None),
    ("C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/msyhbd.ttc", 0),
    ("/usr/share/fonts/truetype/arphic/ukai.ttc",
     "/usr/share/fonts/truetype/arphic/ukai.ttc", 0),
    # macOS
    ("/System/Library/Fonts/PingFang.ttc", "/System/Library/Fonts/PingFang.ttc", 0),
    # ③ Noto CJK：**CFF/PostScript 轮廓，ReportLab 报 "postscript outlines are not
    #    supported"**（run 34815434564 实证）。保留在末尾，只为给出明确的失败信息。
    ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
     "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", 0),
    # ④ 兜底：DejaVu（嵌入 OK；符号覆盖广——↑→≥ 等宋体缺的字形由此承接）
    (_mpl_ttf("DejaVuSans.ttf"), _mpl_ttf("DejaVuSans-Bold.ttf"), None),
]


def _has_cjk(text):
    import re
    return bool(re.search(r"[\u4e00-\u9fff]", text or ""))


def _coverage(path):
    """返回字体覆盖的码位集合（读 cmap）。读不到返回空集（视作不覆盖任何字符）。"""
    try:
        from matplotlib.ft2font import FT2Font
        return set(FT2Font(path).get_charmap())
    except Exception:
        return set()


# 已注册字体登记表：[(reportlab 名, 路径, 覆盖码位集合)]；[0] 为**主字体**
_REGISTERED = []


def _register_pair(name, reg, bold, ttc_index):
    """注册一对（常规/粗体）并登记覆盖集合；失败返回 False（调用方跳过该候选）。"""
    if ttc_index is not None:                        # .ttc 字体集合需指定子字体
        pdfmetrics.registerFont(TTFont(name, reg, subfontIndex=ttc_index))
        pdfmetrics.registerFont(TTFont(name + "-Bold",
                                       bold if os.path.exists(bold) else reg,
                                       subfontIndex=ttc_index))
    else:
        pdfmetrics.registerFont(TTFont(name, reg))
        pdfmetrics.registerFont(TTFont(name + "-Bold", bold if os.path.exists(bold) else reg))
    # 字体族：让 <b>/<i> 映射到**已嵌入**字体，否则会回落 base-14 Helvetica-Bold（不嵌入）
    pdfmetrics.registerFontFamily(name, normal=name, bold=name + "-Bold",
                                 italic=name, boldItalic=name + "-Bold")
    _REGISTERED.append((name, reg, _coverage(reg)))
    return True


def register_fonts():
    """注册**主字体 + 全部可用备用字体**（覆盖驱动，防 .notdef 黑框）。

    契约（两条，均有 run 实证）：
      ① **禁止**回落 base-14：既不嵌入、也无 CJK，会静默丢中文（run 34796985194）；
      ② 主字体缺字形时**不得**直接画 .notdef（黑框）——这正是用户 2026-09-14 反馈的
         "部分黑框/黑块"：文本层能抽出字，但画出来是方框。故本函数把候选表里所有
         可嵌入字体都注册进来，配合 `_wrap()` 逐字选字体，并在构建前断言覆盖完备。
    """
    main = None
    for reg, bold, ttc_index in _FONT_CANDIDATES:
        if not reg or not os.path.exists(reg):
            continue
        try:
            name = "DOC" if main is None else f"ALT{len(_REGISTERED)}"
            if not _register_pair(name, reg, bold, ttc_index):
                continue
            if main is None:
                main = name
                from reportlab import rl_config
                rl_config.canvas_basefontname = main      # 画布初始字体默认是 base-14
                print(f"[排版] 主字体已嵌入：{os.path.basename(reg)}"
                      f"（覆盖 {len(_REGISTERED[-1][2])} 码位）")
                if ord("中") not in _REGISTERED[-1][2]:
                    print("[排版] 警告：主字体不含中文，含中文稿件将由备用字体承接")
            else:
                print(f"[排版] 备用字体已注册：{os.path.basename(reg)}"
                      f"（覆盖 {len(_REGISTERED[-1][2])} 码位）")
        except (TTFError, OSError, ValueError) as ex:
            print(f"[排版] 字体注册失败（{reg}）：{ex}")
    if main is None:
        raise RuntimeError(
            "未找到可嵌入的 TTF 字体：请安装 fonts-wqy-zenhei / fonts-droid-fallback；"
            "禁止回落 base-14（会丢中文且不嵌入）")
    cjk_ok = any(ord("中") in cov for _n, _p, cov in _REGISTERED)
    return "DOC", "DOC-Bold", cjk_ok


def _font_name_for(ch):
    """选一个覆盖该字符的已注册字体名；无则返回 None。"""
    cp = ord(ch)
    for name, _path, cov in _REGISTERED:
        if cp in cov:
            return name
    return None


def missing_glyphs(text):
    """返回**无任何已注册字体覆盖**的字符集合（这些会渲染成黑框）。"""
    return {ch for ch in set(text or "") if not ch.isspace() and _font_name_for(ch) is None}


def _wrap(text):
    """把主字体未覆盖的字符用备用字体包起来（防 .notdef 黑框）。

    ReportLab 不做逐字回退，缺字形直接画方框；这里按覆盖集合把连续的同字体片段
    包成 `<font name="ALTn">…</font>`，并保持与原有 `<b>` 等标记兼容（标记字符是
    ASCII，必在主字体覆盖内，故不会被包裹）。
    """
    if not text or not _REGISTERED:
        return text
    main = _REGISTERED[0][0]
    out, run, cur = [], [], main

    def flush():
        if run:
            s = "".join(run)
            out.append(s if cur == main else f'<font name="{cur}">{s}</font>')
            del run[:]

    for ch in text:
        nm = _font_name_for(ch) or main
        if nm != cur:
            flush()
            cur = nm
        run.append(ch)
    flush()
    return "".join(out)


def _needs_alt(text):
    """该串是否含需要备用字体承接的字符（用于决定表格单元格是否转 Paragraph）。"""
    if not _REGISTERED:
        return False
    main = _REGISTERED[0][0]
    return any((not ch.isspace()) and (_font_name_for(ch) or main) != main
               for ch in text or "")


FONT, FONTB, FONT_CJK = register_fonts()


class NumberedCanvas(canvas.Canvas):
    """双程画布：动态总页数 Page X of Y；第 2 页起画页眉（规范 §二）。"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setFont(FONT, 10)          # 初始字体也用嵌入字体（默认是 base-14 Helvetica）
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_header_footer(num_pages)
            super().showPage()
        super().save()

    def _draw_mixed(self, text, x, y, size):
        """按字符覆盖**分段选字体**绘制（canvas.drawString 不走 Paragraph 的 <font> 回退）。

        教训（2026-09-14）：主字体换成 Times 后，页眉里的中文标题（running_header）
        被静默画丢 —— 每页少 24 字 × 4 页 ≈ 92 字。Paragraph 有 `_wrap()` 承接，
        canvas 没有，必须在这里做同款分段。
        """
        from reportlab.pdfbase.pdfmetrics import stringWidth
        cur, run, cx = None, [], x

        def flush():
            nonlocal cx
            if run:
                s = "".join(run)
                self.setFont(cur, size)
                self.drawString(cx, y, s)
                cx += stringWidth(s, cur, size)
                del run[:]

        for ch in text:
            nm = _font_name_for(ch) or FONT
            if nm != cur:
                flush()
                cur = nm
            run.append(ch)
        flush()

    def draw_header_footer(self, page_count):
        self.saveState()
        self.setFont(FONT, 8)
        self.setFillColor(colors.HexColor("#64748b"))
        page_w, page_h = A4
        margin = MARGIN_PT
        if self._pageNumber > 1:
            self._draw_mixed(HEADER_TEXT, margin, page_h - 36, 8)
            self.setStrokeColor(colors.HexColor("#cbd5e1"))
            self.setLineWidth(0.5)
            self.line(margin, page_h - 42, page_w - margin, page_h - 42)
        self.drawRightString(page_w - margin, 36, f"Page {self._pageNumber} of {page_count}")
        self.drawString(margin, 36, "Confidential Manuscript Draft · Typeset with ReportLab Engine")
        self.setStrokeColor(colors.HexColor("#cbd5e1"))
        self.setLineWidth(0.5)
        self.line(margin, 46, page_w - margin, 46)
        self.restoreState()


def get_image_flowable(image_path, target_width=5.0 * inch):
    """等比缩放宽高（规范 §4.1：不拉伸变形）。"""
    if not os.path.exists(image_path):
        return Spacer(1, 10)
    im = Image.open(image_path)
    aspect = im.height / im.width
    return RLImage(image_path, width=target_width, height=target_width * aspect)


def setup_typography_styles():
    """版式样式表 —— **排版定稿观感**（2026-09-14 终版，用户裁定）。

    定位：本引擎产出的是"排版完整版 PDF"（定稿观感），对应出版社**已排版文章**的样子；
    "TNR 12pt + 双倍行距 + 行号"是模板对 **Word 投稿工作稿** 的要求，由
    `export_manuscript.style_submission()` 在三份 docx 上落实 —— 两套口径各归其位。

    四条不变量（历轮反馈的正反教训，均已实测）：
      ① `wordWrap="CJK"` 必开（否则中文整段被当成一个"长单词"，断行失控）；
      ② 两端对齐**必须**与 ① 配套（无 CJK 断行的 justify 才会塞字间空隙）；
      ③ 衬线字体（西文 Times/Liberation Serif、中文宋体经 `_wrap()` 逐段承接）+ 黑色正文；
      ④ 正文 10pt/14.5 紧凑行距 —— 双倍行距版（12/24）实测被用户判"更差"，弃用。
    """
    styles = getSampleStyleSheet()
    return {
        'DocTitle': ParagraphStyle('DocTitle', parent=styles['Normal'], fontName=FONTB,
                                   fontSize=15, leading=21, textColor=colors.black,
                                   alignment=TA_LEFT, wordWrap='CJK', spaceAfter=8),
        'DocAuthors': ParagraphStyle('DocAuthors', parent=styles['Normal'], fontName=FONT,
                                     fontSize=10, leading=14, textColor=colors.black,
                                     alignment=TA_LEFT, wordWrap='CJK', spaceAfter=10),
        'SectionH1': ParagraphStyle('SectionH1', parent=styles['Normal'], fontName=FONTB,
                                    fontSize=12, leading=16, textColor=colors.black,
                                    wordWrap='CJK', spaceBefore=14, spaceAfter=5, keepWithNext=True),
        'SectionH2': ParagraphStyle('SectionH2', parent=styles['Normal'], fontName=FONTB,
                                    fontSize=10.5, leading=14, textColor=colors.black,
                                    wordWrap='CJK', spaceBefore=10, spaceAfter=3, keepWithNext=True),
        # 注：正文由 `kinsoku()` 预折行（`<br/>` 硬换行），硬换行后两端对齐失效，
        #     故这三个样式统一 TA_LEFT —— 与 docx 投稿稿（左对齐，用户确认"没问题"）一致。
        'Body': ParagraphStyle('Body', parent=styles['Normal'], fontName=FONT,
                               fontSize=10, leading=14.5, textColor=colors.black,
                               alignment=TA_LEFT, wordWrap='CJK', spaceAfter=5),
        'Abstract': ParagraphStyle('Abstract', parent=styles['Normal'], fontName=FONT,
                                   fontSize=9.5, leading=14, textColor=colors.black,
                                   alignment=TA_LEFT, wordWrap='CJK', spaceAfter=5),
        'FigureLegend': ParagraphStyle('FigureLegend', parent=styles['Normal'], fontName=FONT,
                                       fontSize=8.5, leading=12, textColor=colors.black,
                                       alignment=TA_LEFT, wordWrap='CJK',
                                       spaceBefore=2, spaceAfter=6),
        'Reference': ParagraphStyle('Reference', parent=styles['Normal'], fontName=FONT,
                                    fontSize=8.5, leading=12, textColor=colors.black,
                                    wordWrap='CJK',
                                    leftIndent=14, firstLineIndent=-14, spaceAfter=2),
    }


def verify_pdf(path, expect_cjk=True, min_cjk=50, max_boxes=50):
    """构建后自检（三条防线，逐条对应一次真实事故）：

    ① 字体须全为**嵌入型**（TrueType/Type0/CIDFontType*）——期刊硬性要求；
    ② 若期望中文，正文中文字符数须达标（回落 base-14 时会掉到 0）；
    ③ **像素级黑框检测**：字体缺字形时 ReportLab 画 `.notdef`，而 PDF 文本层**仍能抽取**
       该字符（用户 2026-09-14 反馈"部分黑框/黑块"即此）→ 只验文本层抓不到，必须渲染
       成像素后数"实心方块"。
    任一不满足即抛错，让 job 失败，不产出"看起来成功"的残缺 PDF。
    """
    try:
        import pypdf
    except ImportError:
        print("[排版] 自检跳过：pypdf 未安装")
        return
    rd = pypdf.PdfReader(path)
    txt = "".join((p.extract_text() or "") for p in rd.pages)
    n_cjk = len(re.findall(r"[\u4e00-\u9fff]", txt))
    subs = {(str(f.get_object().get("/Subtype")), str(f.get_object().get("/BaseFont")))
            for p in rd.pages for f in (p.get("/Resources", {}).get("/Font") or {}).values()}
    bad = [s for s in subs if s[0] not in ("/TrueType", "/Type0", "/CIDFontType2", "/CIDFontType0")]
    print(f"[排版] 自检：{len(rd.pages)} 页 | 中文字符 {n_cjk} | 字体 {sorted(subs)}")
    if bad:
        raise RuntimeError(f"PDF 含未嵌入字体（期刊多要求嵌入）：{bad}")
    if expect_cjk and n_cjk < min_cjk:
        raise RuntimeError(f"PDF 中文正文缺失（仅 {n_cjk} 个中文字符）→ 字体回落所致")
    n_box = _count_solid_boxes(path)
    if n_box is not None:
        print(f"[排版] 黑框检测：实心黑块 {n_box} 个（阈值 ≤{max_boxes}）")
        if n_box > max_boxes:
            raise RuntimeError(
                f"PDF 检出 {n_box} 个实心黑块（.notdef 黑框）→ 字体缺字形；"
                "检查字体覆盖或补字体")


def _count_solid_boxes(path, dpi=150, dark=50, lo=6, hi=26, fill=0.85):
    """渲染成像素后统计"实心黑块"数（.notdef 黑框的像素特征）；缺依赖则返回 None。

    判据标定（2026-09-14，三样本对照）：
      · 好版（WenQuanYiZenHei 交付件）→ 0 个；好版（本机 msyh 渲染）→ 1 个；
      · 坏版（base-14 Helvetica、中文全丢）→ **2095 个**。
    故取 `fill > 0.85`（近乎实心方块）；早期用 0.55 会把**笔画密集的中文字**误判为黑块
    （msyh 下假阳性 19 个，险些误伤），已收紧。
    """
    try:
        import pymupdf
        import numpy as np
        from scipy import ndimage
    except ImportError:
        print("[排版] 黑框检测跳过：缺 pymupdf/scipy")
        return None
    n = 0
    doc = pymupdf.open(path)
    for pg in doc:
        pix = pg.get_pixmap(dpi=dpi, colorspace=pymupdf.csGRAY)
        arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
        lab, _ = ndimage.label(arr < dark)
        for i, sl in enumerate(ndimage.find_objects(lab)):
            if sl is None:
                continue
            h = sl[0].stop - sl[0].start
            w = sl[1].stop - sl[1].start
            if lo <= w <= hi and lo <= h <= hi:
                if (lab[sl] == (i + 1)).sum() / float(w * h) > fill:
                    n += 1
    doc.close()
    return n


# ── 中文避头尾（kinsoku）────────────────────────────────────────────────────
# 行首禁出现的字符（收尾标点/闭括号）
_NO_LINE_START = "、，。；：！？）」』】》〉〕｝］,.!?:;)]}…～·—。！"
# 行尾禁出现的字符（起始标点/开括号）
_NO_LINE_END = "（「『【《〈〔｛［([{<"
_CJK_RE = re.compile(r"[\u2e80-\u9fff\u3000-\u303f\uff00-\uffef]")

# 正文可用宽度（版心宽，pt）；由 compile_manuscript_pdf 建立 doc 后写入
_AVAIL_W = 0.0


def _char_w(ch, size):
    from reportlab.pdfbase import pdfmetrics
    try:
        return pdfmetrics.stringWidth(ch, _font_name_for(ch) or FONT, size)
    except Exception:
        return size * 0.5


def kinsoku(text, style, avail_width):
    """中文**避头尾**预折行：按可用宽度自行折行，行间插 `<br/>`。

    问题（用户 2026-09-14 反馈"标点符号位置错误"，docx 正常、PDF 异常）：
    ReportLab 的 `wordWrap='CJK'` 会在**任意字符间**断行 → 中文标点（，。；：）等）
    可能落到**行首**，视觉上就是"标点位置错误"。docx 由 Word 排版，自带避头尾，故正常。

    做法：按字体实测宽度贪心折行，并施加禁则 ——
      ① 行首不出现 `_NO_LINE_START`；② 行尾不出现 `_NO_LINE_END`。
    冲突时优先"挤入"（允许 ≤6% 微量超出），否则"推出"（把本行末字符与标点一并下移）。
    """
    if not text or avail_width <= 0:
        return text
    # ① 切分不可分单元：标签整体 / 单个 CJK 字符 / 连续非 CJK 片段
    toks, i = [], 0
    while i < len(text):
        if text[i] == "<" and ">" in text[i:]:
            j = text.index(">", i) + 1
            toks.append(text[i:j]); i = j
        elif _CJK_RE.match(text[i]):
            toks.append(text[i]); i += 1
        else:
            j = i + 1
            while j < len(text) and text[j] != "<" and not _CJK_RE.match(text[j]):
                j += 1
            toks.append(text[i:j]); i = j
    # ② 超长片段（如长 URL / 长英文单词）再切细，避免整段溢出
    _fine = []
    for tk in toks:
        if tk.startswith("<") or _char_w(tk, style.fontSize) <= avail_width:
            _fine.append(tk)
        else:
            _buf = ""
            for c in tk:
                if _buf and _char_w(_buf + c, style.fontSize) > avail_width:
                    _fine.append(_buf); _buf = c
                else:
                    _buf += c
            if _buf:
                _fine.append(_buf)
    toks = _fine

    def _w(s):
        return 0.0 if s.startswith("<") else sum(_char_w(c, style.fontSize) for c in s)

    lines, cur, cur_w = [], [], 0.0
    pending_break = False                # 原文硬换行（<br/>）挂起：若下一 token 是禁则
    # 余量 3%：实测宽度略小于 ReportLab 实际渲染宽度（字距/bold 开销），
    # 片段一旦超框会被二次折行，把末尾标点甩成"孤标点行"（2026-09-14 实测：
    # 1.5% 仍残留 1 处摘要加粗标签后的"：" → 提到 3%）。
    limit = avail_width * 0.97
    for tk in toks:
        if tk.lower() in ("<br/>", "<br>"):
            pending_break = True
            continue
        if pending_break:
            if tk[:1] in _NO_LINE_START:                    # 并入本行行尾
                cur.append(tk); cur_w += _w(tk)
            lines.append("".join(cur)); cur, cur_w, pending_break = [], 0.0, False
            if tk[:1] in _NO_LINE_START:
                continue
        if not cur and tk[:1] in _NO_LINE_START and lines:
            lines[-1] = lines[-1] + tk          # 空行遇禁则标点 → 回挂上一行行尾
            continue
        w = _w(tk)
        if cur and cur_w + w > limit:
            if tk[:1] in _NO_LINE_START and len(cur) > 1:   # 禁则①：推出（末字符与标点一起下移）
                mv = cur.pop()
                # 末字符本身也是标点时须**整串标点一起下移**（否则下一行仍以标点开头，
                # 实测出现行首"）；"——2026-09-14）
                while len(cur) > 1 and mv[:1] in _NO_LINE_START:
                    mv = cur.pop() + mv
                lines.append("".join(cur))
                cur, cur_w = [mv, tk], _w(mv) + w
            elif cur[-1][-1:] in _NO_LINE_END and len(cur) > 1:   # 禁则②：开括号不下沉行尾
                mv = cur.pop()
                lines.append("".join(cur))
                cur, cur_w = [mv, tk], _w(mv) + w
            else:
                lines.append("".join(cur)); cur, cur_w = [tk], w
        else:
            cur.append(tk); cur_w += w
    if cur:
        lines.append("".join(cur))
    return "<br/>".join(lines)


def P(text, style, width=None):
    """构造 Paragraph：先按**可用宽度**做中文避头尾折行，再把缺字形字符交给备用字体。

    `width` 省略时用版心宽（正文）；表格单元格须传**列宽**，否则预折行的行宽与单元格
    不符，会被 ReportLab 二次折行，标点重新落到行首（2026-09-14 实测）。
    """
    return Paragraph(_wrap(kinsoku(text, style, _AVAIL_W if width is None else width)), style)


def _collect_text(md):
    """收集稿件中所有会进入版面的文本（供字形覆盖断言）。"""
    parts = [str(md.get(k, "")) for k in ("title", "authors", "abstract", "keywords")]
    for sec in md.get("sections", []):
        parts.append(str(sec.get("heading", "")))
        parts += [str(p) for p in sec.get("paragraphs", [])]
        t = sec.get("table")
        if t:
            parts.append(str(t.get("caption", "")))
            parts += [str(c) for row in t.get("data", []) for c in row]
        for f in sec.get("figures", []):
            parts += [str(f.get("id", "")), str(f.get("title", "")), str(f.get("legend", ""))]
    for k, v in md.get("declarations", []):
        parts += [str(k), str(v)]
    parts += [str(r) for r in md.get("references", [])]
    return "\n".join(parts)


def assert_glyph_coverage(md):
    """构建前断言：稿件每个字符都有**已注册字体**覆盖，否则报出具体缺字（防黑框）。

    背景（用户 2026-09-14 反馈"部分黑框/黑块"）：缺字形时 PDF **文本层仍可提取**，
    但绘制出来是 `.notdef` 方框 —— 单看"中文字符数/字体是否嵌入"抓不到这一类，
    必须按**字符集覆盖**判定。
    """
    miss = missing_glyphs(_collect_text(md))
    if miss:
        raise RuntimeError(
            "以下字符无任何已注册字体覆盖，会渲染成黑框（请补字体或改写字符）："
            + " ".join(f"{c}(U+{ord(c):04X})" for c in sorted(miss)))


def compile_manuscript_pdf(output_pdf_path, manuscript_data):
    """编译学术 PDF（规范 §四；增补声明节与可配置页眉）。"""
    global HEADER_TEXT, _AVAIL_W
    HEADER_TEXT = manuscript_data.get("running_header", HEADER_TEXT)
    doc = SimpleDocTemplate(output_pdf_path, pagesize=A4, leftMargin=MARGIN_PT, rightMargin=MARGIN_PT,
                            topMargin=MARGIN_PT, bottomMargin=MARGIN_PT,
                            title=manuscript_data.get("title", ""),
                            author=manuscript_data.get("authors", ""))
    _AVAIL_W = doc.width          # 版心宽：供 kinsoku 预折行使用
    st = setup_typography_styles()
    story = [P(manuscript_data['title'], st['DocTitle']),
             P(manuscript_data['authors'], st['DocAuthors']),
             HRFlowable(width="100%", thickness=1, color=colors.HexColor('#cbd5e1'),
                        spaceBefore=2, spaceAfter=10),
             P("<b>摘要 Abstract</b>", st['SectionH2']),
             P(manuscript_data['abstract'], st['Abstract']),
             P(f"<b>关键词 Keywords：</b> {manuscript_data['keywords']}", st['Abstract']),
             HRFlowable(width="100%", thickness=0.8, color=colors.HexColor('#cbd5e1'),
                        spaceBefore=6, spaceAfter=10)]
    for sec in manuscript_data['sections']:
        story.append(P(sec['heading'], st['SectionH1']))
        for para in sec.get('paragraphs', []):
            story.append(P(para, st['Body']))
        if 'table' in sec:
            t_def = sec['table']
            # 单元格含主字体缺字形字符时，必须转 Paragraph 才能逐字换字体（否则仍画黑框）；
            # 预折行**必须按列宽**算（此前用整版宽度 → 单元格内溢出被二次折行 → 标点落行首）
            _cw = t_def.get('col_widths') or [doc.width / max(1, len(t_def['data'][0]))] * len(t_def['data'][0])
            cells = [[P(str(c), st['Body'], _cw[j] - 8) if _needs_alt(str(c)) else c
                      for j, c in enumerate(row)] for row in t_def['data']]
            t_flowable = Table(cells, colWidths=t_def.get('col_widths'))
            t_flowable.setStyle(TableStyle([
                ('FONTNAME', (0, 0), (-1, 0), FONTB),
                ('FONTNAME', (0, 1), (-1, -1), FONT),
                ('FONTSIZE', (0, 0), (-1, -1), 7),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
                ('TOPPADDING', (0, 0), (-1, -1), 3),
                # 三线表（09/03 README §六 结构类规则：表格不画竖线）
                ('LINEABOVE', (0, 0), (-1, 0), 1.0, colors.black),
                ('LINEBELOW', (0, 0), (-1, 0), 0.5, colors.black),
                ('LINEBELOW', (0, -1), (-1, -1), 1.0, colors.black)]))
            story.append(KeepTogether([Spacer(1, 2),
                                       P(f"<b>{t_def['caption']}</b>", st['SectionH2']),
                                       t_flowable, Spacer(1, 6)]))
        for fig in sec.get('figures', []):
            story.append(KeepTogether([Spacer(1, 2),
                                       get_image_flowable(fig['path'], fig.get('width', 5.0 * inch)),
                                       P(f"<b>{fig['id']}. {fig['title']}.</b> {fig['legend']}",
                                         st['FigureLegend'])]))
        if sec.get('page_break_after'):
            story.append(PageBreak())
    abbrs = manuscript_data.get("abbreviations")
    if abbrs:
        story.append(P("缩写（Abbreviations）", st['SectionH1']))
        for _a in abbrs:
            story.append(P(_a, st['Body']))
    story.append(P("声明（Declarations）", st['SectionH1']))
    for k, v in manuscript_data.get('declarations', []):
        story.append(P(f"<b>{k}</b>", st['SectionH2']))
        story.append(P(v, st['Body']))
    story.append(P("参考文献 References", st['SectionH1']))
    for ref in manuscript_data.get('references', []):
        story.append(P(ref, st['Reference']))
    # 前置守卫一：稿件含中文但注册字体无 CJK 覆盖 → 立即失败（不产出"中文被丢"的残缺 PDF）
    _need_cjk = _has_cjk(str(manuscript_data))
    if _need_cjk and not FONT_CJK:
        raise RuntimeError("稿件含中文，但当前注册字体无 CJK 覆盖：请安装 CJK 字体后重跑")
    # 前置守卫二：逐字字形覆盖断言 —— 缺字形会画成黑框，必须构建前拦下
    assert_glyph_coverage(manuscript_data)
    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"成功编译 PDF：{output_pdf_path}")
    verify_pdf(output_pdf_path, expect_cjk=_need_cjk)


if __name__ == "__main__":
    # 字体自检（本机 / 云端均可随时复跑）：注册表 + 逐字回退 + 覆盖完备
    print("=" * 72)
    print("  typeset_engine 字体自检（防黑框/防丢字）")
    print("=" * 72)
    for _n, _p, _cov in _REGISTERED:
        print(f"  {_n:<6s} {os.path.basename(_p):<26s} 覆盖 {len(_cov)} 码位")
    _demo = "AUC ΔAUC χ² 0.11–0.16 风险↑ → ≥ 主要终点"
    _risk = "Δχ–↑→≥²"
    _saved = set(_REGISTERED[0][2])
    _REGISTERED[0][2].difference_update({ord(c) for c in _risk})   # 模拟主字体缺字形
    _w = _wrap(_demo)
    _plain = re.sub(r"<[^>]+>", "", _w)
    _ok = ('<font name="' in _w) and _plain == _demo
    print("\n[逐字回退] 模拟主字体缺字形 →", _w)
    print("[逐字回退]", "PASS" if _ok else "FAIL")
    _REGISTERED[0][2].clear()
    _REGISTERED[0][2].update(_saved)
    _miss = missing_glyphs(_demo + "摘要关键词声明参考文献")
    print("[覆盖完备]", "PASS（无缺字）" if not _miss else f"FAIL 缺字 {sorted(_miss)}")
    raise SystemExit(0 if (_ok and not _miss) else 1)
