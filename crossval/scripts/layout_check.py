# -*- coding: utf-8 -*-
"""
================================================================================
 V5-T 排版层 · 可执行验证器  v1.0
 Layout & Typesetting Validator (dormant module of V5)
================================================================================
 归属   : 框架本体 V5 的条件子模块 V5-T —— 默认休眠,排版阶段激活
 两部分 : P 系列 = 排版执行规范(怎么做)   C 系列 = 排版检查(做得对不对)
 环境   : 跨平台,纯标准库(可选 pypdf 用于图件规格)。Windows 11 + PS7 可跑
 运行   : python layout_check.py              # 用内置合成稿件演示自检
          python layout_check.py --dir <稿件目录>

 核心防线(三条):
   C-1 图序/表序与正文引用一一对应(孤儿图 / 悬空引用)
   C-2 排版未改动数字(正文数字 vs 台账)
   C-3 排版未升级 claim(压缩字数不得删限定词)  ★ 最容易发生、最隐蔽

 所有数字均为 MVP 合成值·非项目实际值。
================================================================================
"""
import os, re, sys, json, argparse, hashlib
import yaml
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

DORMANT = ("不适用 + 理由:未进入排版阶段"
           "(目标期刊未定 或 未开始按该期刊模板排版)")

# 降级/限定词表 —— C-3 的核心。删掉这些词 = claim 升级
HEDGE_WORDS = [
    "候选", "探索性", "探索", "待验证", "尚需", "提示", "可能",
    "初步", "相关", "待独立验证", "事后", "描述性",
    "candidate", "exploratory", "preliminary", "suggest", "may",
    "warrants", "further validation", "hypothesis-generating",
]

# 升级标志词 —— 若压缩后新增这些,直接判违规
UPGRADE_WORDS = ["诊断标志物", "机制阐明", "首次发现", "显著改善临床决策",
                 "已证实", "外部验证", "可用于临床", "驱动",
                 "diagnostic biomarker", "external validation", "proven"]


_WARNINGS = []


def _warn(msg):
    _WARNINGS.append(msg)
    print(f"    [WARN] {msg}")


class R:
    def __init__(self):
        self.rows = []

    def add(self, cid, item, observed, expected, passed, detail=""):
        self.rows.append(dict(check=cid, item=item, observed=str(observed),
                              expected=str(expected), passed=bool(passed),
                              detail=detail))
        print(f"    [{'PASS' if passed else 'FAIL'}] {cid} {item:<40s} "
              f"obs={str(observed):<20s} exp={expected}")

    @property
    def npass(self): return sum(r["passed"] for r in self.rows)
    @property
    def nfail(self): return sum(not r["passed"] for r in self.rows)


# ============================================================ C-1 图表引用
def check_refs(text, figures, tables, supdir=None):
    """图序/表序与正文引用一一对应"""
    print("\n  ── C-1 图表引用完整性")
    r = R()
    cited_f = set(int(x) for x in re.findall(r"图\s*(\d+)", text))
    cited_t = set(int(x) for x in re.findall(r"表\s*(\d+)", text))
    have_f = set(figures)
    have_t = set(tables)

    orphan_f = sorted(have_f - cited_f)   # 有图但正文没引用
    dangling_f = sorted(cited_f - have_f) # 正文引用但没这个图
    orphan_t = sorted(have_t - cited_t)
    dangling_t = sorted(cited_t - have_t)

    r.add("C-1.1", "无孤儿图", orphan_f or "无", "无", not orphan_f)
    r.add("C-1.2", "无悬空图引用", dangling_f or "无", "无", not dangling_f)
    r.add("C-1.3", "无孤儿表", orphan_t or "无", "无", not orphan_t)
    r.add("C-1.4", "无悬空表引用", dangling_t or "无", "无", not dangling_t)

    # 图序连续性
    seq_ok = (sorted(have_f) == list(range(1, len(have_f) + 1))) if have_f else True
    r.add("C-1.5", "图序连续无缺号", sorted(have_f) or "无", "1..N 连续", seq_ok)

    # 修:原 C-1.6 恒为 True(空规)。改为:编号可解析 + 连续 + 文件存在
    sup_cited = sorted(int(x) for x in
                       re.findall(r"Supplementary\s*(?:Table|Figure)\s*S?(\d+)", text))
    seq_ok = (not sup_cited) or (sup_cited == list(range(1, len(set(sup_cited)) + 1)))
    r.add("C-1.6", "补充材料编号连续无缺号", sup_cited or "无引用", "1..N 连续", seq_ok)
    if supdir and os.path.isdir(supdir):
        have = set()
        for fn in os.listdir(supdir):
            m = re.search(r"S(\d+)", fn)
            if m: have.add(int(m.group(1)))
        missing = sorted(set(sup_cited) - have)
        r.add("C-1.7", "补充材料文件存在", missing or "无缺失", "无缺失", not missing,
              f"引用但文件缺失: S{missing}" if missing else "")
    return r, dict(orphan_fig=orphan_f, dangling_fig=dangling_f,
                   orphan_tab=orphan_t, dangling_tab=dangling_t,
                   sup_cited=sup_cited)


# ============================================================ C-2 数字一致
def check_numbers(text, ledger):
    """正文数字 vs 台账:排版不得改动数字"""
    print("\n  ── C-2 排版未改动数字(正文 vs 台账)")
    r = R()
    drift = []
    for key, val in ledger.items():
        # 台账值出现的次数
        hits = len(re.findall(re.escape(str(val)), text))
        if hits == 0:
            drift.append(f"{key}={val} 未在正文出现")
    r.add("C-2.1", "台账数字均可在正文定位",
          f"{len(ledger) - len(drift)}/{len(ledger)}",
          f"{len(ledger)}/{len(ledger)}", not drift,
          "; ".join(drift) if drift else "")

    # 检测"疑似被改过"的数字:同键不同值
    suspicious = re.findall(
        r"(?:OR|HR|RR|AUC|C-index|p|FDR|ORs|HRs)\s*[:：=]?\s*([0-9]+\.?[0-9]*)",
        text, re.I)
    uniq = sorted(set(suspicious))
    in_ledger = set(str(v) for v in ledger.values())
    alien = [u for u in uniq if u not in in_ledger]
    r.add("C-2.2", "无台账外数字", alien or "无", "无", not alien,
          f"正文出现但台账无: {alien}" if alien else "")
    return r, dict(missing=drift, alien=alien)


# ============================================================ C-3 claim 升级
def check_claim(before, after, limit_note=""):
    """排版压缩不得删除限定词 / 不得新增升级词"""
    print("\n  ── C-3 排版未升级 claim ★ 最隐蔽的违规")
    r = R()

    lost = [w for w in HEDGE_WORDS if w in before and w not in after]
    gained = [w for w in UPGRADE_WORDS if w not in before and w in after]

    r.add("C-3.1", "压缩未删除限定词", lost or "无丢失", "无丢失", not lost,
          f"被删: {lost}" if lost else "")
    r.add("C-3.2", "压缩未新增升级词", gained or "无新增", "无新增", not gained,
          f"新增: {gained}" if gained else "")

    # 限定词密度:压缩后不应显著下降
    def density(t):
        n = len(t)
        c = sum(t.count(w) for w in HEDGE_WORDS)
        return c / max(n, 1) * 1000
    d0, d1 = density(before), density(after)
    c0 = sum(before.count(w) for w in HEDGE_WORDS)
    c1 = sum(after.count(w) for w in HEDGE_WORDS)
    # 阈值在填槽阶段由 A 定;默认:密度降幅<40% 且绝对计数不减
    drop = d0 > 0 and (d1 / d0) < 0.6
    r.add("C-3.3", "限定词密度未崩塌(阈值可配)",
          f"{d0:.1f}→{d1:.1f}‰", "降幅<40%", not drop,
          "压缩后限定词密度显著下降,疑为腾字数删限定词" if drop else "")
    r.add("C-3.4", "限定词绝对计数未减少",
          f"{c0}→{c1}", f">={c0}", c1 >= c0,
          "绝对计数减少,即使密度上升也可能是删除所致" if c1 < c0 else "")
    return r, dict(lost_hedges=lost, gained_upgrades=gained,
                   density_before=round(d0, 2), density_after=round(d1, 2))


# ============================================================ C-4 图件规格
# ============================================================ 工具契约
def detect_backend():
    """工具契约:返回【实际使用】的后端,而非仅"可用"的。
    本脚本为跨平台(含 Win11 无 poppler)统一用 pypdf;
    若 poppler 可用,另行标注但其结果不作为判定依据。"""
    import shutil
    try:
        import pypdf  # noqa
    except ImportError:
        return "fail"
    has_poppler = all(shutil.which(c) for c in ("pdffonts", "pdftotext", "pdfimages"))
    return "pypdf_recursive(跨平台主路径)" + (" +poppler可用" if has_poppler else "")


# 每项声明的多个可能表述 —— 单关键词匹配太脆弱(如"数据可在GEO获取"不含"数据共享")
DECL_PATTERNS = {
    "伦理批准": ["伦理", "ethics", "IRB", "批件"],
    "知情同意": ["知情同意", "informed consent", "同意书"],
    "数据共享": ["数据共享", "数据可在", "数据可用", "data availability",
              "GEO", "SRA", "公开获取"],
    "代码共享": ["代码", "code", "GitHub", "gitlab", "仓库"],
    "AI使用披露": ["AI", "人工智能", "LLM", "大语言模型", "生成式"],
    "利益冲突": ["利益冲突", "conflict of interest", "COI"],
    "作者贡献": ["作者贡献", "contribution", "CRediT"],
    "资助声明": ["资助", "基金", "funding", "grant", "supported by"],
}


def check_declarations(text, patterns=None):
    """V5DECL 声明与披露清单(缺口 9)—— 多关键词匹配,缺一即 V5 不通过"""
    if patterns is None:
        patterns = DECL_PATTERNS
    low = text.lower()
    found, missing = [], []
    for name, kws in patterns.items():
        hit = any(k.lower() in low for k in kws)
        (found if hit else missing).append(name)
    return found, missing


def _count_images(obj, seen, depth=0):
    """递归统计 XObject 中的图像(含 Form XObject 嵌套)"""
    if depth > 6 or obj is None:
        return 0
    try:
        o = obj.get_object()
    except Exception as _e:
        _warn(f"{type(_e).__name__}: {_e}")
        return 0
    key = id(o)
    if key in seen:
        return 0
    seen.add(key)
    n = 0
    try:
        res = o.get("/Resources", {}) or {}
        res = res.get_object()
    except Exception:
        res = {}
    try:
        if o.get("/Subtype") == "/Image":
            n += 1
    except Exception as e:
        _warn(f"{type(e).__name__}: {e}")
        pass
    try:
        for k, v in (res.get("/XObject", {}) or {}).items():
            n += _count_images(v, seen, depth + 1)
    except Exception as e:
        _warn(f"{type(e).__name__}: {e}")
        pass
    return n


def check_figure_spec(figdir, single_col_pt=252.0, double_col_pt=523.0,
                      max_bytes=10 * 1024 * 1024):
    """图件规格:矢量/字体/文本层/分栏宽度/体积"""
    print("\n  ── C-4 图件规格(引用 M11–M18 判据)")
    r = R()
    if not os.path.isdir(figdir):
        r.add("C-4.0", "图目录存在", False, "True", False)
        return r, {}
    try:
        from pypdf import PdfReader
    except ImportError:
        print("    [SKIP] pypdf 未安装,跳过图件内部结构检查")
        r.add("C-4.0", "pypdf 可用", False, "True", False)
        return r, {}

    out = {}
    for fn in sorted(os.listdir(figdir)):
        if not fn.lower().endswith(".pdf"):
            continue
        p = os.path.join(figdir, fn)
        try:
            # 修:原只读 pages[0],多页 PDF 后续页全部漏检。改为遍历所有页 + 递归 XObject
            rd = PdfReader(p)
            ft, nimg, txts = set(), 0, []
            w_pt = h_pt = 0.0
            for pg in rd.pages:
                try:
                    res = pg.get("/Resources", {}) or {}
                    res = res.get_object()
                except Exception:
                    res = {}
                try:
                    for k, v in (res.get("/Font", {}) or {}).items():
                        ft.add(str(v.get_object().get("/Subtype")))
                except Exception as e:
                    _warn(f"{type(e).__name__}: {e}")
                    pass
                try:
                    for k, v in (res.get("/XObject", {}) or {}).items():
                        nimg += _count_images(v, set())
                except Exception as e:
                    _warn(f"{type(e).__name__}: {e}")
                    pass
                txts.append((pg.extract_text() or "").strip())
                try:
                    w_pt = max(w_pt, float(pg.mediabox.width))
                    h_pt = max(h_pt, float(pg.mediabox.height))
                except Exception as e:
                    _warn(f"{type(e).__name__}: {e}")
                    pass
            txt = "".join(txts)
            sz = os.path.getsize(p)

            bad = []
            if nimg > 0: bad.append("位图")
            if "/Type3" in ft: bad.append("Type3字体")
            if len(txt) < 10: bad.append("无文本层")
            if w_pt > double_col_pt + 1: bad.append("超双栏宽度")
            if sz > max_bytes: bad.append("超体积上限")
            verdict = "不合规:" + "/".join(bad) if bad else "合规"
            # 样本命名约定: bad_* = 已知违规样本,应被检出; ok_* = 已知合规样本
            if "bad_" in fn:
                expect, ok = "不合规", bool(bad)      # 检出违规才算通过
            elif "ok_" in fn:
                expect, ok = "合规", not bad
            else:
                expect, ok = "合规", not bad          # 真实稿件一律期望合规
            out[fn] = dict(width_pt=round(w_pt, 1), height_pt=round(h_pt, 1),
                           images=nimg, fonts=sorted(ft),
                           textlen=len(txt), bytes=sz,
                           verdict=verdict, expect=expect)
            r.add("C-4", f"{fn[:30]:<30s}", verdict, expect, ok)
        except Exception as e:
            _warn(f"图件读取失败 {fn}: {type(e).__name__}: {e}")
            out[fn] = dict(error=str(e))
            r.add("C-4", fn[:30], f"读取失败 {e}", "可读", False)
    return r, out


# ============================================================ C-5 期刊条目
def check_journal_limits(text, n_fig, n_tab, n_ref,
                         max_words=3500, max_fig=8, max_tab=4, max_ref=60):
    """按目标期刊 Guide for Authors 核对条目数与字数"""
    print("\n  ── C-5 期刊条目与字数上限(数值在填槽阶段按期刊定死)")
    r = R()
    # 中文按字符计,英文按词计
    words = len(re.findall(r"[A-Za-z]+", text)) + len(re.findall(r"[\u4e00-\u9fff]", text))
    # ---------- C-6 图内容规范(作图规范 v1.0) ----------
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import figure_kit as FK
        _spec = FK.load_spec()
        _figdir = os.path.join(ROOT, "figures", "demo")
        _steps = set()
        try:
            _fy = yaml.safe_load(open(os.path.join(ROOT, "schema", "criteria.yaml"),
                                      encoding="utf-8"))
            for _c in _fy.get("criteria", []):
                if _c.get("stage_tag"):
                    _steps.add(_c["stage_tag"])
        except Exception:
            _steps = set()
        _files = sorted(os.listdir(_figdir)) if os.path.isdir(_figdir) else []
        if not _files:
            r.add("C-6.0", "图目录含图件", 0, ">0", False)
        for _fn in _files:
            if not _fn.lower().endswith((".pdf", ".tiff", ".tif", ".png", ".jpg", ".jpeg")):
                continue
            _kind = "vector" if _fn.lower().endswith((".pdf", ".eps")) else "raster"
            for _cid, _lab, _obs, _exp, _ok in FK.check_file(
                    os.path.join(_figdir, _fn), _spec, _kind):
                r.add("C-6", f"{_fn[:24]:<24s} {_lab}", _obs, _exp, _ok)
            for _cid, _lab, _obs, _exp, _ok in FK.check_name(_fn, _spec, _steps or None):
                r.add("C-6", f"{_fn[:24]:<24s} {_lab}", _obs, _exp, _ok)
        # 色板与图注(用规范内置样例做守卫自证)
        for _cid, _lab, _obs, _exp, _ok in FK.check_colors(
                _spec["palettes"]["wong2011"][:6], _spec):
            r.add("C-6", f"规范自证 {_lab}", _obs, _exp, _ok)
    except Exception as _e:
        r.add("C-6.0", "C-6 图内容检查可执行", f"异常 {_e}", "无异常", False)

    r.add("C-5.1", f"正文字数 <= {max_words}", words, f"<={max_words}", words <= max_words)
    r.add("C-5.2", f"图数量 <= {max_fig}", n_fig, f"<={max_fig}", n_fig <= max_fig)
    r.add("C-5.3", f"表数量 <= {max_tab}", n_tab, f"<={max_tab}", n_tab <= max_tab)
    r.add("C-5.4", f"参考文献 <= {max_ref}", n_ref, f"<={max_ref}", n_ref <= max_ref)
    return r, dict(words=words, n_fig=n_fig, n_tab=n_tab, n_ref=n_ref)


# ============================================================ 演示数据
DEMO_BEFORE = """
本研究在发现集中鉴定出一个候选标志物程序。该程序评分与卒中后认知障碍
呈现初步相关,提示其可能参与神经免疫过程。此为探索性结果,尚需独立
队列进一步验证。当前证据不支持其作为诊断标志物使用。
"""

DEMO_AFTER_BAD = """
本研究鉴定出一个标志物程序。该程序评分与卒中后认知障碍显著相关,
参与神经免疫过程。结果稳健,外部验证支持其临床效用。
可作为诊断标志物使用。
"""

DEMO_AFTER_GOOD = """
本研究在发现集中鉴定出一个候选标志物程序。该程序评分与卒中后认知
障碍呈现初步相关,提示其可能参与神经免疫过程。此为探索性结果,
尚需独立队列进一步验证。
"""

DEMO_TEXT = """
结果如图 1 所示,程序评分与 PSCI 相关。表 1 给出基线特征。
图 2 展示敏感性分析结果。图 3 为决策曲线,见 Supplementary Table S1。
主要终点 OR = 1.645,AUC = 0.698。
"""

DEMO_LEDGER = {
    "OR_perSD": "1.645",
    "AUC_full": "0.698",
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="", help="稿件目录")
    ap.add_argument("--figdir", default="", help="图目录")
    a = ap.parse_args()

    print("=" * 78)
    print("  V5-T 排版层 · 可执行验证器 v1.0")
    print("  归属:框架 V5 条件子模块 · 默认休眠 · 排版阶段激活")
    print("=" * 78)

    if not a.dir:
        print(f"\n  [休眠态] {DORMANT}")
        print("  未指定 --dir,以下为内置合成稿件的自检演示。\n")

    # 工具契约:显式报告后端,不可用则失败(禁止静默通过)
    be = detect_backend()
    if be == "fail":
        print("  [工具契约] PDF 检测后端 = 不可用")
        print("  [FAIL] 无 PDF 检测工具 → 按契约目检级判'判不了',不得降级为通过")
    else:
        note = ("权威路径" if be.startswith("poppler")
                else "跨平台主路径(须在报告中标注 detection_backend)")
        print(f"  [工具契约] PDF 检测后端 = {be}  —— {note}")

    allr = []
    R1, o1 = check_refs(DEMO_TEXT, figures=[1, 2, 3], tables=[1])
    allr += R1.rows
    R2, o2 = check_numbers(DEMO_TEXT, DEMO_LEDGER)
    allr += R2.rows

    print("\n  ── C-3 演示:压缩摘要的两种做法")
    Rb, ob = check_claim(DEMO_BEFORE, DEMO_AFTER_BAD)
    print(f"      [违规样例] 删限定词={ob['lost_hedges']} 新增升级词={ob['gained_upgrades']}")
    Rg, og = check_claim(DEMO_BEFORE, DEMO_AFTER_GOOD)
    print(f"      [合规样例] 删限定词={og['lost_hedges']} 新增升级词={og['gained_upgrades']}")
    allr += Rg.rows   # 只把合规样例计入通过项

    # 违规样例必须被抓到
    caught = bool(ob["lost_hedges"] or ob["gained_upgrades"])
    print(f"\n    [{'PASS' if caught else 'FAIL'}] C-3.9 违规压缩可被检出  "
          f"obs={caught} exp=True")

    if a.figdir:
        R4, o4 = check_figure_spec(a.figdir)
        allr += R4.rows
    else:
        here = os.path.dirname(os.path.abspath(__file__))
        cand = os.path.join(os.path.dirname(here), "figures", "samples")
        if os.path.isdir(cand):
            R4, o4 = check_figure_spec(cand)
            allr += R4.rows
        else:
            print("\n  ── C-4 图件规格 [SKIP] 无图目录")

    R5, o5 = check_journal_limits(DEMO_TEXT, n_fig=3, n_tab=1, n_ref=42)
    allr += R5.rows

    # V5DECL 声明与披露清单
    print("\n  ── V5DECL 声明与披露清单(缺口 9)")
    Rd = R()
    DEMO_DECL = """伦理批准(批件号 XXX)。所有参与者签署知情同意。数据可在 GEO 获取。
代码见 GitHub(DOI:xxx)。本研究使用 AI 辅助生成初稿,全部数字由作者核实。
作者声明无利益冲突。作者贡献按 CRediT 分类。本工作受 XXX 基金资助。"""
    found, missing = check_declarations(DEMO_DECL)
    Rd.add("V5DECL", f"声明项已覆盖 {len(found)}/{len(found)+len(missing)}",
           len(found), f"={len(found)+len(missing)}", not missing,
           f"缺失: {missing}" if missing else "")
    _, miss2 = check_declarations(DEMO_TEXT)
    Rd.add("V5DECL", "缺声明的稿件可被检出(反向验证)",
           f"缺 {len(miss2)} 项", ">0 项被抓", len(miss2) > 0)
    allr += Rd.rows

    npass = sum(1 for x in allr if x["passed"])
    nfail = sum(1 for x in allr if not x["passed"])
    print("\n" + "=" * 78)
    print(f"  V5-T 判定: {npass}/{npass + nfail} 通过,失败 {nfail} 项")
    print("  (C-3 违规样例为『应被检出』演示,不计入失败项)")
    print("=" * 78)

    out = dict(module="V5-T", dormant_reason=DORMANT, warnings=_WARNINGS,
              checks=allr,
              # ★ v2.25：显式登记三态计数。
              #   原先报告只有 checks 列表，消费方（consistency_guard G-2.2/G-4.2）
              #   只能用 len(checks) 猜"排版 N/N"；而 checks 含 C-3 违规样例等
              #   "应被检出"的演示项 → 猜出来的数字与文档口径不一致 →
              #   实测产生假 FAIL（obs=['70/70'] exp=['222/222','73/73']）。
              #   数字必须由产出方登记，不得由消费方猜（第 9 条原则）。
              n_pass=npass, n_fail=nfail, n_total=npass + nfail,
              demo_violation_caught=caught,
              demo_violation_detail=ob,
              note="MVP 合成值·非项目实际值")
    rp = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "results", "layout_report.json")
    os.makedirs(os.path.dirname(rp), exist_ok=True)
    json.dump(out, open(rp, "w", encoding="utf-8"), indent=1,
              ensure_ascii=False, default=str)
    print(f"  报告: {rp}")
    return 0 if nfail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
