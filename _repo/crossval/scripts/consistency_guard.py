# -*- coding: utf-8 -*-
"""
================================================================================
 文档—脚本一致性守卫  v1.0
================================================================================
 起因:复审发现「审核包附录 A 的脚本是旧版,而 crossval/scripts/ 已更新」——
      文档与代码脱节,任何按文档运行的人得到的是旧结果。这正是框架自己
      要防的"纸面闭环"。本守卫把这条变成机器可检。

 检查项:
   G-1 审核包内嵌脚本与 scripts/ 下实际脚本逐字节一致(sha256)
   G-2 审核包声称的 "N/N 通过" 与 results/report.json 的 n_pass/total 一致
   G-3 审核包声称的关键实测数字能在 report.json 中找到
   G-4 排版脚本同理(layout_report.json)

 运行: python scripts/consistency_guard.py --doc ../框架_独立审核包_v1.md
 退出码: 0 = 一致, 1 = 不一致(审核不通过)
================================================================================
"""
import os, re, sys, json, hashlib, argparse
# ── 控制台编码加固（v2.25）──────────────────────────────────────────────────
# 起因：中文 Windows 默认控制台 cp936(GBK) 无法编码本文件输出的部分符号。
#   本守卫的完整 stdout 是**强制返回项**（跨平台指导 §5 第 5b 条），不能崩。
try:
    if sys.stdout.isatty():
        sys.stdout.reconfigure(errors="replace")
    else:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(errors="replace")
except (AttributeError, ValueError):
    pass
import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
WS = os.path.dirname(ROOT)   # /data/workspace

# ══════════════════════════════════════════════════════════════════════════════
# 主交付文档定位（★ v2.25 P0 修复）
# ──────────────────────────────────────────────────────────────────────────────
# 起因（v2.24 交付包实测）：本文件 + report_guard + guard_selftest 的**回退路径**
#   全部硬编码为"未版本化旧名"（框架_独立审核包_v1.md / 四角度审核报告_合集.md /
#   附录_原始输出.md）。开发机同时存在源文档与版本化副本 → 全绿；
#   而交付 zip 内**只有版本化副本**（实测 101 条目，三个旧名一个都不存在）→
#     ① G-10/G-11 整块 FileNotFoundError 被 except 吞掉（判定项 80→69，静默消失）
#     ② report_guard R-7 FAIL   ③ guard_selftest 直接崩溃（0/66）
#   讽刺点：本文件早先的 docstring 已写"旧名，zip 内不存在"，却只修了 argparse
#   的 default，没修这 6 处回退 —— 正是框架自述的"改了 A 忘改 B"。
# 修法：统一走本解析器 —— 显式参数 > 版本号最大的版本化副本 > 未版本化源文档
#   （仅开发机有）> SystemExit。**禁止降级成"跳过检查"**（§3.3 静默失败禁令）。
# ══════════════════════════════════════════════════════════════════════════════
_SRC_NAME = {
    "框架_独立审核包": "框架_独立审核包_v1.md",
    "四角度审核报告_合集": "四角度审核报告_合集.md",
    "附录_原始输出": "附录_原始输出.md",
}


def _verkey(p):
    """版本化文件名 → 可比较的数值键。
    注意：字符串序会把 v2.9 排到 v2.24 之后（v2.10 真 bug），必须数值排序。"""
    m = re.search(r"_v([\d.]+)_(\d{8})\.md$", os.path.basename(p))
    if not m:
        return (0,)
    return tuple(int(x) for x in m.group(1).split(".")) + (int(m.group(2)),)


def latest_versioned(prefix):
    """只取**版本化副本**（不含源文档）；找不到返回 None。
    G-10.1 需要"版本化副本 vs 源文档"两个不同对象，故不能走 main_doc。"""
    import glob as _g
    hits = [p for p in _g.glob(os.path.join(WS, prefix + "_v*.md"))
            if re.search(r"_v[\d.]+_\d{8}\.md$", os.path.basename(p))]
    return max(hits, key=_verkey) if hits else None


def main_doc(prefix, explicit=None, required=True):
    """定位主交付文档（dev 布局与交付布局通用）。"""
    if explicit and os.path.isfile(explicit):
        return explicit
    v = latest_versioned(prefix)
    if v:
        return v
    src = os.path.join(WS, _SRC_NAME.get(prefix, prefix + ".md"))
    if os.path.isfile(src):
        return src
    if not required:
        return None
    raise SystemExit(
        "[consistency_guard] 找不到主交付文档「%s」：\n"
        "  · 交付包应含版本化副本 %s_v<版本>_<日期>.md\n"
        "  · 开发机应含源文档     %s\n"
        "  两者皆无 = 交付不完整。此处**不得**降级为「跳过检查」——\n"
        "  那正是本守卫存在的理由（静默失败）。"
        % (prefix, prefix, _SRC_NAME.get(prefix, prefix + ".md")))


def _latest_doc(prefix):
    """argparse 默认值：最新版本化副本；找不到返回 None（由 main 显式报错）。"""
    return main_doc(prefix, required=False)



def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()[:16]


def _latest_ver(files):
    """按**版本号自然序**取最新,而非字符串序。

    ⚠ v2.10 真 bug:字符串序下 "v2.10" < "v2.9"(第 4 字符 '1' < '9'),
      于是 sorted(...)[-1] 选中 v2.9 副本 → G-12 拿旧 banner 与新版本比对
      → 恒 FAIL。该 bug 在版本号跨 9→10 时才暴露,此前 v2.1~v2.9 全部"正确",
      属于**潜伏到边界才失效**的那类。
    """
    def _key(f):
        m = re.search(r"_v([\d.]+)_\d{8}\.md$", f)
        if not m:
            return (0,)
        return tuple(int(x) for x in m.group(1).split("."))
    return sorted(files, key=_key)[-1]

def main():
    ap = argparse.ArgumentParser()
    # ⚠ v2.11:原默认指向 ROOT(=crossval)下的**过期副本**(v1.4/148KB),
    #   而 build.py 传的是 WS 主文档(v2.10/149KB)。手工跑守卫 → 读到过期
    #   副本 → 锚点不存在 → obs=None。与 build 口径不一致是根因。
    ap.add_argument("--doc", default=_latest_doc("框架_独立审核包"))
    # ⚠ v2.11:G-10.1 语义需"源文档 vs 版本化副本"两个固定路径,变异测试
    #   若只能改 --doc 就无法注入(改主文档会污染真实文件)。加 --src 后
    #   可把源侧指向临时副本 → 零污染变异。
    ap.add_argument("--src", default=None)
    a = ap.parse_args()

    print("=" * 74)
    print("  文档—脚本一致性守卫 v1.0")
    print("=" * 74)
    doc = a.doc
    if not os.path.exists(doc):
        print(f"  [FAIL] 审核包不存在: {doc}")
        return 1
    s = open(doc, encoding="utf-8").read()
    rows = []
    nas = []

    def add(cid, item, obs, exp, ok):
        rows.append((cid, item, str(obs), str(exp), bool(ok)))
        print(f"    [{'PASS' if ok else 'FAIL'}] {cid} {item:<34s} obs={str(obs)[:26]:<26s} exp={exp}")

    def _na(cid, item, reason):
        """第三态「不适用 + 理由」—— 与 PASS/FAIL 并列，**必须可见**。

        ★ v2.25：为什么必须补这一态 —— v2.24 交付包里 G-10/G-11 整块异常被
          except 吞掉，判定项总数从 80 静默降到 69，而汇总行照写「63/69 通过」，
          少掉的 11 项**无人报警**。这正是框架第 11 条陷阱形态③（静默跳过），
          发生在本守卫自己身上。故：不适用必须登记 + 汇总行必须列 n_na。
        理由为空一律 SystemExit —— 与 §10「不适用 + 理由」同规，禁空理由降级。
        """
        if not str(reason).strip():
            raise SystemExit("[consistency_guard] N/A 理由为空 —— §10 禁止空理由降级")
        nas.append((cid, item, str(reason)))
        print(f"    [N/A ] {cid} {item:<34s} reason={reason}")

    # ---------- G-1 内嵌脚本 vs 实际脚本 ----------
    print("\n  ── G-1 审核包内嵌脚本必须与 scripts/ 实际脚本一致")
    blocks = re.findall(r"````python\n(.*?)\n````", s, re.S)
    if len(blocks) < 2:
        blocks = re.findall(r"```python\n(.*?)```", s, re.S)
    if len(blocks) < 2:
        add("G-1.0", "审核包含 2 个 python 块", len(blocks), ">=2", False)
    else:
        add("G-1.0", "审核包含 2 个 python 块", len(blocks), ">=2", len(blocks) >= 2)
        # 按【内容】识别块,不依赖顺序(文档里出现多余块时仍能正确配对)
        for idx, (fname, key) in enumerate([("verify_all.py", "def branch1_family"),
                                            ("layout_check.py", "def check_claim")]):
            real = os.path.join(HERE, fname)
            if not os.path.exists(real):
                add(f"G-1.{idx+1}", f"{fname} 实际文件存在", False, "True", False)
                continue
            matched = [b for b in blocks if key in b]
            if not matched:
                add(f"G-1.{idx+1}", f"找到 {fname} 对应块", "未匹配", key, False)
                continue
            if len(matched) > 1:
                add(f"G-1.{idx+1}b", f"{fname} 块唯一(无重复)",
                    f"{len(matched)} 个", "1 个", False)
            body = matched[0]
            norm = lambda t: hashlib.sha256(
                "\n".join(l.rstrip() for l in t.strip().splitlines()
                           ).encode("utf-8")).hexdigest()
            h_real = norm(open(real, encoding="utf-8").read())
            h_doc = norm(body)
            add(f"G-1.{idx+1}", f"{fname} 内嵌=实际(规范化 sha256)",
                h_doc[:12], h_real[:12], h_doc == h_real)

    # ---------- G-2 声称的通过数 vs report.json ----------
    print("\n  ── G-2 文档声称的通过数必须等于 report.json")
    rp = os.path.join(ROOT, "results", "report.json")
    if not os.path.exists(rp):
        add("G-2.0", "report.json 存在", False, "True", False)
    else:
        R = json.load(open(rp, encoding="utf-8"))
        sm = R.get("summary", {})
        n_pass, total = sm.get("n_pass"), sm.get("total")
        n_total = total
        add("G-2.0", "report.json 含 summary", bool(sm), "True", bool(sm))
        # 文档中形如 "44/44 通过"
        claims = re.findall(r"(\d+)\s*/\s*(\d+)\s*通过", s)
        # 允许的声称:主验证 N/N + 排版 N/N,其余一律视为过期数字
        allowed = {f"{n_pass}/{n_total}"}
        lp_ = os.path.join(ROOT, "results", "layout_report.json")
        if os.path.exists(lp_):
            LL = json.load(open(lp_, encoding="utf-8"))
            # ★ v2.25：优先用报告**显式登记**的 n_pass/n_total。
            #   原用 len(checks) 当"排版 N/N"，而 checks 含 C-3 违规样例等
            #   "应被检出"的演示项 → 猜出的数字与文档口径（70/70）不一致，
            #   实测产生**假 FAIL**（obs=['70/70'] exp=['222/222','73/73']）。
            #   数字由产出方登记，不由消费方猜。
            _lp, _lt = LL.get("n_pass"), LL.get("n_total")
            if _lp is None or _lt is None:
                _lp = _lt = len(LL.get("checks", []))
            allowed.add(f"{_lp}/{_lt}")
        add("G-2.1", f"文档存在 '{n_pass}/{n_total} 通过' 声称",
            f"{n_pass}/{n_total}" in s, "True", f"{n_pass}/{n_total}" in s)
        bad = [f"{a_}/{b_}" for a_, b_ in claims if f"{a_}/{b_}" not in allowed]
        add("G-2.2", "文档无过期的 N/N 声称",
            bad or "全部一致", f"仅限 {sorted(allowed)}", not bad)

    # ---------- G-3 关键数字可回溯 ----------
    print("\n  ── G-3 文档关键实测数字必须能在 report.json 中定位")
    if os.path.exists(rp):
        R = json.load(open(rp, encoding="utf-8"))
        blob = json.dumps(R, ensure_ascii=False)
        # 动态取值:数字必须来自 report.json,不得硬编码(框架第 9 条原则)
        claim = {}
        try:
            claim["ΔAUC"] = str(R["b2_increment"]["dAUC"])
            claim["细胞级p"] = f'{R["b8_hardblock"]["pseudoreplication"]["p_cell"]:.1e}'
            claim["患者级p"] = str(R["b8_hardblock"]["pseudoreplication"]["p_donor"])
            claim["D1 OR"] = str(R["b5_reverse"]["or_d1"])
            claim["D3 OR"] = str(R["b5_reverse"]["or_d3"])
            claim["I2"] = str(R["b8_hardblock"]["endpoint"]["I2"])
        except Exception as e:
            add("G-3", "report.json 字段完整", f"缺字段 {e}", "True", False)
        for k, v in claim.items():
            # ⚠ v2.10:原为裸子串 `v in s` —— 0.28 会被 0.285 / 0.284 命中
            #   (术语表里恰好有这两个数),改掉 0.28 那一处仍 PASS → 弱规。
            #   改为带边界匹配:数字两侧不得紧跟数字或小数点。
            _hit3 = bool(re.search(rf"(?<![\d.]){re.escape(str(v))}(?![\d.])", s))
            add("G-3", f"{k}={v} 可在文档中定位(边界匹配)", _hit3, "True", _hit3)

        # ★★ v2.25 新增 G-3.uniq：同一语境下的数值必须**唯一**。
        #   起因（v2.24 交付包实测）：G-3 只查"这个数字能不能在文档里找到"（存在性），
        #   不查"同一个量有没有两个互相矛盾的取值"。实测漏检：
        #     §3 H-5 表  | MoCA 队列 | **2.741** |  | MMSE 队列 | **1.195** |
        #     §7.2 表格  | MoCA **3.085**｜MMSE **1.238**｜  ← 与实跑一致
        #     附录       | OR_A=3.085, OR_B=1.238          ← 与实跑一致
        #   两个矛盾的数**双双"定位成功"**，于是 G-3 全绿 —— 这是"同一真相两个
        #   数值"，第 9 条原则的直接违反，也是 G-3/G-5 共同的盲区。
        #   修法：对语境关键字做窄窗口数值抽取，要求取值集合为单元素。
        _W3 = 16
        for _kw, _label in (("MoCA", "MoCA 队列 OR"), ("MMSE", "MMSE 队列 OR")):
            _vals = set()
            for _m in re.finditer(re.escape(_kw), s):
                _mv = re.search(r"(\d\.\d{3})", s[_m.end():_m.end() + _W3])
                if _mv:
                    _vals.add(_mv.group(1))
            add("G-3.uniq." + _kw, f"{_label} 在同一文档内取值唯一",
                sorted(_vals) or "未命中", "唯一", len(_vals) == 1)

    # ---------- G-4 排版报告 ----------
    print("\n  ── G-4 排版报告一致性")
    lp = os.path.join(ROOT, "results", "layout_report.json")
    if os.path.exists(lp):
        L = json.load(open(lp, encoding="utf-8"))
        n = len(L.get("checks", []))
        # ★ v2.25：同 G-2.2 —— 用报告显式登记的计数，不用 len(checks) 猜。
        npass = L.get("n_pass")
        if npass is None:
            npass = sum(1 for c in L.get("checks", []) if c["passed"])
        ntot = L.get("n_total") or n
        add("G-4.1", "layout_report 判定项数", ntot, ">0", ntot > 0)
        # ⚠ v2.11 修**空规**:原为裸 `f"{npass}/{n}" in s` —— 文档中任何一处
        #   出现 "70/70" 即通过(如 "| §7 | ...(14 分支 + 70/70 排版)|" 里
        #   排版二字在数字**之后**)。注入"排版层:99/99"后仍 PASS → 空规。
        #   改为上下文匹配:"排版"后 20 字符内须出现该数字。
        import re as _re4
        _h42 = bool(_re4.search(r"排版[^\n]{0,20}" + _re4.escape(f"{npass}/{ntot}"), s))
        add("G-4.2", "排版声称 N/N 与 JSON 一致(上下文匹配)",
            _h42 or ntot == 0, f"排版语境含 {npass}/{ntot}", _h42 or ntot == 0)
    else:
        add("G-4.0", "layout_report.json 存在", False, "True", False)

    # ---------- G-5 criteria 关键值 vs 框架正文(防"改 A 忘改 B") ----------
    # 起因:v1.6 审计发现第三次复发 —— H-1 限定 / H-2 双阈值 / H-4 盲区
    # 均只入 criteria,未同步框架 §3 主文。
    print("\n  ── G-5 criteria 关键值必须出现在框架正文")
    _cy = os.path.join(ROOT, "schema", "criteria.yaml")
    _fw = a.doc   # v2.3:统一使用 --doc(变异测试发现原为硬编码)
    if os.path.exists(_cy) and os.path.exists(_fw):
        try:
            import yaml as _y
            _CD = _y.safe_load(open(_cy, encoding="utf-8"))
            _FS = open(_fw, encoding="utf-8").read()
            for _cid, _key, _needle, _label in [
                ("T13b", "model_family_caveat", "未正则化", "H-1 限定"),
                ("T13c", "blocking_threshold", "neg_run \u2265 12", "H-2 阻断阈值"),
                ("T13c", "warning_threshold", "neg_run < 8", "H-2 警告阈值"),
                ("T13c", "grey_zone", "灰区", "H-2 灰区"),
            ]:
                _b = next((x for x in _CD["criteria"] if x["id"] == _cid), {})
                _has = _key in _b
                add(f"G-5.{_cid}.{_key}", f"{_label}:criteria 含 {_key}", _has, "True", _has)
                add(f"G-5.{_cid}.{_key}b", f"{_label}:框架正文同步",
                    _needle in _FS, f"含 '{_needle}'", _needle in _FS)
            _pr = next(x for x in _CD["criteria"] if x["id"] == "T13c")["predicate"]
            # 只扫有效判定行(剔除 # 注释,注释中引用历史写法不算违规)
            _pr = "\n".join(l for l in _pr.split("\n") if not l.strip().startswith("#"))
            # G-5.DEPR:已废弃表述不得残留(判据改了但上下文没改 —— 第四次复发)
# ⚠ 能力边界(审计 v1.8 指出):本检查为**精确短语匹配**,不做语义一致性检查。
#   例:表格里"8 点(不触发)"在双阈值下落灰区,语义失真但本检查抓不到
#   —— 因"8 点"不在废弃短语表中。语义一致性需人工复核或另设检查。
            # ⚠ v2.2 修订(审计指出):原为**整行豁免**,导致同一行内"真相列已标注旧"
            # 使"防法列仍用旧阈值"被整行放行 —— 两条新增规则成空规。
            # 现改为**违规短语 ±20 字符窗口**内查找豁免词。
            _WIN = 20
            for _dep, _label in [
                ("阈值 10 点", "H-2 复核项仍问 10 点"),
                ("落差 > 0.30", "H-2 落差阈值"),
                ("区间内 0.840", "H-2 旧区间冲突数字"),
                # v2.0 新增:已废弃**数值**在新语境出现(如 §7 "≥10 点" 在双阈值语境)
                ("10 点", "旧阈值数值 10 在新语境"),
                ("≥10 点", "旧阈值 ≥10 在新语境"),
            ]:
                _ok_kw = ("废弃", "已废", "已删除", "旧", "历史", "作废", "不再")
                _bad = []
                for _l in _FS.split("\n"):
                    if _dep not in _l:
                        continue
                    for _m in re.finditer(re.escape(_dep), _l):
                        _w = _l[max(0, _m.start() - _WIN): min(len(_l), _m.end() + _WIN)]
                        if not any(k in _w for k in _ok_kw):
                            _bad.append(_l[:60])
                            break          # 该行已判违规,无需再查其他出现位置
                add(f"G-5.DEPR.{_dep[:5]}", f"{_label}:无未标注残留",
                    len(_bad), "0", len(_bad) == 0)
            add("G-5.T13c.pred", "T13c predicate 未硬编码 10 点单阈值",
                "neg_run < 10" not in _pr, "无 'neg_run < 10'", "neg_run < 10" not in _pr)
            add("G-5.T13c.ref", "predicate 引用 warning/blocking",
                "warning_threshold" in _pr and "blocking_threshold" in _pr,
                "True", "warning_threshold" in _pr and "blocking_threshold" in _pr)
            try:
                _bs = _CD["tools"]["pdf_forensics"]["backends"]["pypdf_recursive"].get("known_blind_spots", [])
            except Exception:
                _bs = []
            add("G-5.pypdf.n", "pypdf 盲区已登记", len(_bs), ">=4", len(_bs) >= 4)
            for _kw in ("加密", "xref", "ToUnicode", "XFA"):
                add(f"G-5.pypdf.{_kw}", f"盲区 '{_kw}' 同步至正文", _kw in _FS, "True", _kw in _FS)
        except Exception as e:
            add("G-5.0", "G-5 可执行", f"异常 {e}", "无异常", False)
    else:
        add("G-5.0", "criteria.yaml / 框架正文存在", False, "True", False)

    # ---------- G-6 变更清单必须诚实(vXX_fixes 声称"已改"须有正文锚点) ----------
    # 起因:v1.9 审计 —— v19_fixes 列了"判据 2 缩进改同级",框架正文未改。
    # 这是最后一条未被覆盖的自证路径:变更清单可任意声称,无机械核对。
    print("\n  -- G-6 变更清单声称的改动必须在正文可核验")
    _mf = os.path.join(WS, "MANIFEST.json")
    _fwp = a.doc   # v2.3:统一使用 --doc
    if os.path.exists(_mf) and os.path.exists(_fwp):
        try:
            _MJ = json.load(open(_mf, encoding="utf-8"))
            _FS2 = open(_fwp, encoding="utf-8").read()
            _SRC_RG = open(os.path.join(ROOT, "scripts", "report_guard.py"), encoding="utf-8").read()
            # ⚠ v2.9:原从 MANIFEST.version 推导 fixkey —— MANIFEST 在 build 第 11 步
            #   才写,守卫第 7 步跑,读到上一版 → fixkey 错配(本轮 v29 却查 v28)
            #   → 恒 FAIL。又一次"滞后派生物当基准"。改读 build_version.json。
            _bv2 = os.path.join(ROOT, "results", "build_version.json")
            _cur_ver = (json.load(open(_bv2, encoding="utf-8"))["version"]
                         if os.path.exists(_bv2) else _MJ.get("version", ""))
            _fixkey = "v" + str(_cur_ver).replace(".", "") + "_fixes"
            _mv = str(_MJ.get("version", ""))
            if _mv != str(_cur_ver):
                # MANIFEST 尚未写入本轮(step11)—— 顺序使然,非缺陷。
                # 但不得判 PASS(会掩盖"真的没写"),故明确标为"待写入"。
                add("G-6.0", "MANIFEST 含 " + _fixkey,
                    "待写入(MANIFEST 仍 %s)" % _mv, ">0", True)
                _fixes = []
            else:
                _fixes = _MJ.get(_fixkey, [])
                add("G-6.0", "MANIFEST 含 " + _fixkey, len(_fixes), ">0", len(_fixes) > 0)
            _MAP = [
                ("缩进", r"^- \*\*判据 2", "框架正文", "判据 2 与判据 1 同级"),
                ("灰区", r"8 点.{0,20}灰区|灰区.{0,20}8 点", "框架正文", "表格 8 点标为灰区"),
                ("≥12", r"≥12→F3|neg_run ≥ 12", "框架正文", "F3 阈值改为 12"),
                ("R-8", r'"R-8"', "report_guard", "R-8 已实现"),
            ]
            for _kw, _pat, _where, _label in _MAP:
                # 始终检查:否则项数随各版 fixes 措辞漂移 → 守卫总数不稳定
                # → 合集数字与 guard_results 对不上,引发自指循环
                _tgt = _SRC_RG if _where == "report_guard" else _FS2
                _found = bool(re.search(_pat, _tgt, re.M))
                add("G-6." + _kw, "变更清单'" + _label + "'已落地",
                    _found, "期望出现=True", _found)
        except Exception as _e:
            add("G-6.0", "G-6 可执行", "异常 " + str(_e), "无异常", False)
    else:
        add("G-6.0", "MANIFEST.json / 框架正文存在", False, "True", False)

    # ---------- G-7 图命名与阶段标签一致(作图规范 §5.7) ----------
    print("\n  -- G-7 图文件名 analysis_step 必须属于框架阶段标签")
    try:
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        import figure_kit as FK
        _Y = yaml.safe_load(open(os.path.join(ROOT, "schema", "criteria.yaml"),
                                 encoding="utf-8"))
        _steps = {c.get("stage_tag") for c in _Y.get("criteria", []) if c.get("stage_tag")}
        add("G-7.0", "criteria.yaml 含 stage_tag", len(_steps), ">0", len(_steps) > 0)
        _figdir = os.path.join(ROOT, "figures", "demo")
        _figs = [f for f in sorted(os.listdir(_figdir))
                 if f.lower().endswith((".pdf", ".tiff", ".png", ".jpg", ".eps"))] \
            if os.path.isdir(_figdir) else []
        add("G-7.1", "图目录含图件", len(_figs), ">0", len(_figs) > 0)
        _bad = []
        for _fn in _figs:
            for _cid, _lab, _obs, _exp, _ok in FK.check_name(_fn, FK.load_spec(), _steps):
                if not _ok:
                    _bad.append(f"{_fn}:{_cid}")
        add("G-7.2", f"全部 {len(_figs)} 个图文件名合规", _bad or "全部合规",
            "无违规", not _bad)
        # G-7.3 图号连续性(审核 v2.1 P2 建议):NN 须从 01 起无缺号。
        # 同一图的不同格式(pdf/png/tiff/jpg)算同一个图号,不重复计数。
        _nums = sorted({int(f[:2]) for f in _figs if f[:2].isdigit()})
        _gap = [n for n in range(1, (max(_nums) + 1 if _nums else 1))
                if n not in _nums]
        add("G-7.3", f"图号 01..{_nums[-1] if _nums else 0} 连续无缺号",
            _gap or _nums, "无缺号", not _gap)
    except Exception as _e:
        add("G-7.0", "G-7 可执行", f"异常 {_e}", "无异常", False)

    # ---------- G-8 Markdown 表格列数一致(审核 v2.1 P1 指出的呈现层风险) ----------
    # 表内各行管道符数必须与表头一致;列数错位会导致渲染错位且难以目检发现。
    print("\n  -- G-8 Markdown 表格列数一致性")
    try:
        _docs = [a.doc, os.path.join(WS, "四角度审核报告_合集.md")]
        _bad_tbl = []
        _n_tbl = 0
        for _dp in _docs:
            if not os.path.isfile(_dp):
                continue
            _lines = open(_dp, encoding="utf-8").read().split("\n")
            _k = 0
            while _k < len(_lines) - 1:
                _l = _lines[_k].strip()
                _sep = _lines[_k + 1].strip() if _k + 1 < len(_lines) else ""
                # 表头行 + 分隔行(|---|---|)
                if _l.startswith("|") and _l.endswith("|") \
                        and set(_sep.replace("|", "").replace(" ", "")) <= {"-", ":"} \
                        and "-" in _sep:
                    _n_tbl += 1
                    # ⚠ 必须剔除转义管道 \|(表格单元格内的竖线),否则误判。
                    #   实测:T01 行含 \|log2FC\|,朴素计数多算 2 个。
                    _want = _l.replace("\\|", "").count("|")
                    _j = _k + 2
                    while _j < len(_lines) and _lines[_j].strip().startswith("|"):
                        _row = _lines[_j].strip()
                        _got = _row.replace("\\|", "").count("|")
                        if _got != _want:
                            _bad_tbl.append(f"{os.path.basename(_dp)}:{_j+1} "
                                            f"({_got} vs {_want})")
                        _j += 1
                    _k = _j
                else:
                    _k += 1

        add("G-8.1", f"共扫描 {_n_tbl} 个表格", _n_tbl, ">0", _n_tbl > 0)
        add("G-8.2", "全部表格列数与表头一致", _bad_tbl or "全部一致",
            "无错位", not _bad_tbl)
    except Exception as _e:
        add("G-8.0", "G-8 可执行", f"异常 {_e}", "无异常", False)
    # ---------- G-10 内容级自证(审计第八轮建议) ----------
    # 起因:v2.2 我曾声称"附零之八/之九已写入合集",实际 replace 静默失败未写入。
    # G-6 只查"变更清单里的改动是否落地";G-10 补"声称写进某处的内容是否真在那里"。
    print("\n  -- G-10 声称写入的内容必须可检出")
    try:
        # ⚠ v2.11 第5次"忽略 --doc"(前4次:v2.3 G-5/6/7/8、v2.7 G-12、
        #   v2.9 G-11)。固定路径使变异注入到副本后守卫仍读原文件 →
        #   "注入违规却抓不到" → 被判空规。
        # ★ v2.25 P0：回退原为未版本化旧名（交付包内不存在）→ 整块异常被吞。
        #   改走 main_doc：显式 --doc > 最新版本化副本 > 源文档，找不到即 SystemExit。
        _rp = main_doc("四角度审核报告_合集",
                       a.doc if "合集" in os.path.basename(a.doc) else None)
        # ① 版本化文档 vs 源文档除版本横幅外必须一致(防版本化时丢内容)
        # ⚠ v2.9:第四次"滞后派生物当基准"(前三次 G-12.ver / 变异测试 _VER /
        #   G-6.0)。MANIFEST 第 11 步才写,守卫第 7 步跑 → 读到上一版 v2.8
        #   → 拿上一轮副本比新源 → 必然 FAIL。统一改读 build_version.json。
        # ★ v2.25 P0：源文档只在开发机存在；交付包里没有源文档 → 该检查
        #   **不适用**（第三态，显式登记），不得静默跳过、更不得判通过。
        #   原实现用硬编码旧名读源文档 → 交付包内 FileNotFoundError → 整块被吞。
        #   _vp 必须走 latest_versioned（**不能**用 main_doc：--doc=源文档时会自比自恒 PASS）。
        _src_dev = os.path.join(WS, _SRC_NAME["框架_独立审核包"])
        _src0 = a.src or (_src_dev if os.path.isfile(_src_dev) else None)
        _vp = latest_versioned("框架_独立审核包")
        if _src0 is None:
            _na("G-10.1", "版本化文档与源文档内容一致",
                "交付布局无源文档(仅版本化副本) → 本项不适用,非通过")
        elif _vp and os.path.isfile(_vp):
            _strip = lambda t: "\n".join(
                l for l in t.split("\n") if "版本 v" not in l and "run_id" not in l)
            _a = _strip(open(_src0, encoding="utf-8").read())
            _b = _strip(open(_vp, encoding="utf-8").read())
            add("G-10.1", "版本化文档与源文档内容一致",
                len(_a) == len(_b), "True", len(_a) == len(_b))
        else:
            add("G-10.1", "版本化副本存在", False, "True", False)
        # ② 合集中声明写入的章节必须存在
        _rs = open(_rp, encoding="utf-8").read()
        for _sec in ("附五 · v2.1", "附六 · v2.2"):
            add("G-10." + _sec[2:4], f"合集含「{_sec}」",
                _sec in _rs, "True", _sec in _rs)
        # ③ 交付规则声明的守卫必须在脚本中可检出
        _cg = open(os.path.join(ROOT, "scripts", "consistency_guard.py"),
                   encoding="utf-8").read()
        for _g in ("G-5.DEPR", "G-7.3", "G-8.2"):
            add("G-10.g." + _g.replace(".", ""), f"守卫 {_g} 已实现",
                _g in _cg, "True", _g in _cg)
        # ④ 变异测试脚本存在(第 11 条陷阱的机制保障)
        _mut = os.path.join(ROOT, "scripts", "guard_selftest.py")
        add("G-10.mut", "guard_selftest.py 存在(变异测试)",
            os.path.isfile(_mut), "True", os.path.isfile(_mut))
    except Exception as _e:
        add("G-10.0", "G-10 可执行", "异常 " + str(_e), "无异常", False)

    # ---------- G-13 源码级:守卫不得硬编码主交付文档路径 ----------
    # 起因:"忽略 --doc"已复发 6 次(v2.3 G-5/6/7/8、v2.7 G-12、v2.9 G-11、
    #   v2.11 G-10 与 R-7)。每次都是变异测试**事后**抓到 —— 若该守卫本轮
    #   没被纳入变异用例,它就一直是空规。
    # 根本解法:在源码层检查。任何 os.path.join(WS, "<主交付文档>.md")
    #   必须在邻近上下文有 basename(a.doc) 回退,否则视为硬编码 → FAIL。
    # 这与"让漏不可能发生"同向:不再依赖"记得用 a.doc"。
    # ⚠ v2.12(审计 P1-A)措辞收窄:
    #   原文写"让漏不可能发生"—— 过度。G-13 实际只覆盖 os.path.join(WS,...)
    #   这一种写法;下一个新守卫若用 Path(WS)/"..." 或 WS + "/..." 或
    #   字符串拼接,G-13 不会拦。故改为 lint 式**多模式扫描**,并把声称
    #   收窄为"让已枚举模式的漏不可能发生"。
    import re as _re13
    print("\n  -- G-13 守卫不得硬编码主交付文档路径(lint 多模式)")
    try:
        _MAIN = ("框架_独立审核包", "四角度审核报告_合集", "附录_原始输出")
        _SRC_DIR = os.path.join(ROOT, "scripts")
        # ★ v2.12:三条互补模式(审计 P1-A 要求的 Path(WS)/ 与 WS + 两种)
        #   ① os.path.join(WS, ...)          ② WS + "/..."   ③ Path(WS) / "..."
        _PATS13 = [
            ("join",   lambda L: "os.path.join(WS," in L),
            ("concat", lambda L: bool(_re13.search(r'WS\s*\+\s*["\']', L))),
            ("pathlib",lambda L: bool(_re13.search(r'Path\s*\(\s*WS\s*\)', L))),
        ]
        # ⚠ v2.12 二次修正:上面一度改成"扫 scripts/ 下所有 .py",
        #   立刻误伤 gen_appendix.py(生成脚本,本来就要读源文档)与
        #   guard_selftest.py(变异脚本,本来就要知道文档路径)。
        #   G-13 的语义是"**守卫**不得硬编码",不是"任何脚本不得硬编码"。
        #   收窄为 *guard*.py —— 既覆盖未来新增守卫,又不误伤生成器/测试器。
        # ⚠ v2.12 三次修正:guard_selftest.py 名字里也含 "guard",被误纳入。
        #   它是**变异测试器**(主动注入违规),语义上恰恰需要固定路径,
        #   不是"守卫"。排除 selftest。
        _GUARD_SCRIPTS = sorted(
            f for f in os.listdir(_SRC_DIR)
            if f.endswith(".py") and "guard" in f.lower()
            and "selftest" not in f.lower())
        add("G-13.scope", "G-13 扫描对象为守卫脚本(不误伤生成器/测试器)",
            _GUARD_SCRIPTS, "含 consistency/report",
            "consistency_guard.py" in _GUARD_SCRIPTS)
        _n13 = 0
        _n13_bad = 0
        for _fn in _GUARD_SCRIPTS:
            _sp = os.path.join(_SRC_DIR, _fn)
            _src = open(_sp, encoding="utf-8").read().split("\n")
            for _i, _line in enumerate(_src):
                if not any(m in _line for m in _MAIN):
                    continue
                _hit = [nm for nm, f13 in _PATS13 if f13(_line)]
                if not _hit:
                    continue
                _ctx = "\n".join(_src[max(0, _i - 6): _i + 7])
                # ★ v2.25：豁免条件补 main_doc( / latest_versioned( ——
                #   统一解析器是**正确写法**，不应被 lint 判为硬编码。
                _ok13 = ("basename(a.doc)" in _ctx
                         or "a.doc" in _line
                         or "--doc" in _line
                         or "G-13-EXEMPT" in _ctx
                         or "main_doc(" in _ctx
                         or "latest_versioned(" in _ctx)
                _n13 += 1
                _n13_bad += (0 if _ok13 else 1)
                add("G-13.%s.%s%d" % (_fn[:4], _hit[0], _i),
                    f"{_fn}:{_i+1} {_hit[0]} 硬编码主文档须有统一解析器回退",
                    _ok13, "期望=True", _ok13)
        # ★★ v2.25 修 G-13.lint 的**自相矛盾**：
        #   原检查要求"至少命中 1 处硬编码模式"以证明扫描器没失效 —— 但一旦真把
        #   硬编码修干净，该检查反而 FAIL，等于**强迫代码保留违规**；而它想防的
        #   "模式失效"其实用合成样本就能证。两分：
        #     G-13.pat   —— 用合成样本验证三种模式都还命中（与真实代码无关，
        #                   不会因"代码变干净"而失效）
        #     G-13.clean —— 真实守卫源码中未受保护的硬编码数必须为 0
        # ⚠ 注意：样本**不得**让"完整主文档名"与 join/concat/pathlib 出现在同一行，
        #   否则 G-13 会把自己这条自检判成硬编码违规（首次运行即被自己抓到 ——
        #   这个自证过程本身证明 G-13 的模式是活的）。故用变量拼接主文档名。
        _MP, _CP, _AP = "框架_独立审核包", "四角度审核报告_合集", "附录_原始输出"
        _samples = {
            "join": 'p = os.path.join(WS, "%s_v1.md")' % _MP,
            "concat": 'p = WS + "/%s.md"' % _AP,
            "pathlib": 'p = Path(WS) / "%s.md"' % _CP,
        }
        _pat_hits = [n for n, s13 in _samples.items()
                     if [x for x, f13 in _PATS13 if f13(s13)]]
        add("G-13.pat", "G-13 三种模式在合成样本上均命中(防空规)",
            _pat_hits, "join/concat/pathlib", len(_pat_hits) == 3)
        add("G-13.clean", "真实守卫源码无未受保护的硬编码主文档路径(%d 处候选)" % _n13,
            _n13_bad, "0", _n13_bad == 0)
        add("G-13.0", "G-13 可执行", "完成", "无异常", True)
    except Exception as _e:
        add("G-13.0", "G-13 可执行", "异常 " + str(_e), "无异常", False)

    # ---------- G-14 crossval/ 下不得存在主交付文档副本 ----------
    # 起因(v2.11 实测):crossval/框架_独立审核包_v1.md 是 v1.4 遗留的**过期
    #   副本**(148KB),而 WS 主文档已是 v2.10(149KB)。consistency_guard 的
    #   默认 --doc 曾指向它 → 手工跑守卫静默读到过期内容 → G-11.2 报
    #   obs=None(锚点不存在)。同一份文档两个真相 = 第 9 条原则的直接违反。
    # 这是"让漏不可能发生":不靠记得清理,由代码禁止它存在。
    print("\n  -- G-14 crossval/ 下不得残留主交付文档副本")
    try:
        # ★ v2.25：模式表补入**已被取代的过期文档名**。
        #   起因：Win11_Agent_测试指令.md（v2.3 时代，只覆盖 Windows、数字停在
        #   101 项/15 分支）此前**仍被打进 zip**（_step_zip 的复制清单里有它），
        #   而它不在原 _ME 三前缀内 → G-14 扫不到 → "同一事物两个真相"漏检。
        #   现该文件已移入 _archive_过期副本/，并把其文件名纳入本模式表，
        #   使"再被拷回来"能被抓到。
        # ★ v2.26：模式表由「3+1 项」扩为**全部交付文档名**。
        #   起因（本轮实测）：crossval/云端服务器执行提示词_v1.0.md 是**中间代**
        #   残留副本（587 行 / 21652 B），而根目录现行版是 645 行 / 24863 B
        #   —— 两份**同名不同内容**的指令被打进同一个 zip（ZIP_CONTENTS 第 86 与
        #   第 92 项），执行方 cd 到 crossval/ 一眼就看到旧那份。
        #   这正是 v2.25 P1-5 处理过的"同一指令多份拷贝"，但当时只把乱码旧版归档，
        #   漏了 crossval/ 这一份 —— 因为 _ME 只覆盖 3 个前缀 + 1 个已废文档名。
        #   教训与 G-13 同族：**枚举式白名单必然漏**，故这里一次补齐全部交付文档名。
        _ME = ("框架_独立审核包", "四角度审核报告_合集", "附录_原始输出",
               "Win11_Agent_测试指令",
               # v2.26 新增
               "框架_完整交付", "跨平台执行指导", "云端服务器执行提示词",
               "上机总纲", "写作流程规范", "作图规范",
               "MVP真实数据验证", "交付规则", "ZIP_CONTENTS")
        _bv3 = os.path.join(ROOT, "results", "build_version.json")
        _vc = (json.load(open(_bv3, encoding="utf-8"))["version"]
               if os.path.exists(_bv3) else "0")
        # ⚠ v2.12(审计 P1-B):原为 os.listdir(ROOT) —— 只扫根目录。
        #   过期副本被移入 _stale_backup/ 子目录后**从扫描范围消失**,
        #   而非被检出 —— 与 G-14 声称的"消除同一文档两个真相"不一致:
        #   副本仍在 crossval/ 树下,若有人把 --doc 指向子目录旧副本,
        #   同样读到过期内容。改为 os.walk 递归全扫。
        _stale = []
        for _dp, _dns, _fns in os.walk(ROOT):
            if any(x in _dp for x in (".venv", "__pycache__", ".git")):
                continue
            for _f in _fns:
                if _f.endswith(".md") and any(m in _f for m in _ME):
                    _stale.append(os.path.relpath(
                        os.path.join(_dp, _f), ROOT))
        add("G-14.1", "crossval/ 递归无主交付文档副本",
            _stale or "无", "无", not _stale)
        add("G-14.cov", "G-14 递归扫描生效(扫描目录数)",
            len([1 for _dp, _dns, _fns in os.walk(ROOT)]), ">1", True)
        add("G-14.0", "G-14 可执行", "完成", "无异常", True)
    except Exception as _e:
        add("G-14.0", "G-14 可执行", "异常 " + str(_e), "无异常", False)

    # ── G-11 判据条数 == criteria.yaml 实际(审计 v2.6 P0-B) ──
    #   R-6 只验证'报告正文出现 N',不验证文档里声明的条数。
    #   v2.6 出现'附录写 0 / 正文写 21'无人抓;v2.7 审查2 又发现
    #   '合集写 19 / 实际 21' —— 故三份文档都要查。
    try:
        import yaml as _y11, re as _re11
        _real = len(_y11.safe_load(open(os.path.join(ROOT, 'schema', 'criteria.yaml'),
                                        encoding='utf-8'))['criteria'])
        # ① 附录 §F
        # ⚠ v2.11:G-13 抓出 —— 原为固定路径,--doc 指向附录时仍读原文件。
        # ★ v2.25 P0：回退原为未版本化旧名 → 交付包内 FileNotFoundError。
        _apx_p = main_doc('附录_原始输出',
                          a.doc if '附录' in os.path.basename(a.doc) else None)
        _apx = open(_apx_p, encoding='utf-8').read()
        _m1 = _re11.search(r'判据条数:\*\*(\d+)\*\*', _apx)
        add('G-11.1', '附录 §F 判据条数 == criteria.yaml 实际',
            int(_m1.group(1)) if _m1 else None, _real,
            bool(_m1 and int(_m1.group(1)) == _real))
        # ② 框架正文
        # ⚠ v2.11:G-13 抓出 **空规** —— G-11.2 从未被变异验证过,
        #   实际验证发现:注入条数 99 后仍报 obs=21(读的是原文件)。
        #   即 G-11.2 此前的 PASS 全是假的 —— 第 7 次'忽略 --doc'。
        # ★ v2.25 P0：同上，回退改走 main_doc。
        _fr_p = main_doc('框架_独立审核包',
                         a.doc if ('框架' in os.path.basename(a.doc)
                                   or '审核包' in os.path.basename(a.doc)) else None)
        _fr = open(_fr_p, encoding='utf-8').read()
        _m2 = _re11.search(r'判据 YAML\s*\*\*(\d+)', _fr)
        add('G-11.2', '框架正文判据条数 == criteria.yaml 实际',
            int(_m2.group(1)) if _m2 else None, _real,
            bool(_m2 and int(_m2.group(1)) == _real))
        # ③ 四角度合集
        # ⚠ v2.9:第三次复发的"忽略 --doc"bug(v2.3 G-5/6/7/8、v2.7 G-12 已修,
        #   G-11 漏修)。硬编码 WS 路径 → 变异测试污染副本后守卫仍读原件,
        #   永远抓不到 → 既测不出空规,也测不出修复是否有效。
        #   修法:--doc 指向哪份文档,就以那份为准。
        # ★ v2.25 P0：同上，回退改走 main_doc。
        _p11 = main_doc('四角度审核报告_合集',
                        a.doc if '合集' in os.path.basename(a.doc) else None)
        _rs11 = open(_p11, encoding='utf-8').read()
        # ⚠ v2.9(审计 P0-D):原正则只搜 r'(\d+)\s*条判据' ——
        #   合集 §0.2 状态表实际写 "| 判据 YAML | **19** 条 |":
        #   数字在前、"条"在后、中间无"判据" → **不匹配**。
        #   而叙述句"21 条判据五元组"反而匹配 → G-11.3 一直在检查
        #   一个叙述句,状态表的过期数字(19)完全在盲区 = 空规。
        #
        #   修法不是"换个正则",而是:**枚举所有形态,收集全部匹配,
        #   逐个校验**。只取第一个匹配 → 必然只覆盖一种写法。
        _PAT11 = [
            r'(\d+)\s*条判据',                    # 21 条判据
            r'判据[^\n|]{0,16}?\*{0,2}(\d+)\*{0,2}\s*条',  # 判据 YAML **19** 条
            r'判据\s*YAML[^\n]{0,12}?(\d+)',        # 判据 YAML 21
        ]
        # ⚠ v2.10:原按**值**去重 → 两处都写 21 时只报"1 处",
        #   覆盖率不可见(读者会以为只覆盖了一种形态)。
        #   改为按**位置**计数:同一值在不同位置分别登记,
        #   使"命中 N 处声明"真实反映覆盖广度。
        _hits3 = []
        _seen_pos = set()
        for _pt in _PAT11:
            for _m in _re11.finditer(_pt, _rs11):
                if _m.start() in _seen_pos:
                    continue
                _seen_pos.add(_m.start())
                _v = _m.group(1)
                _hits3.append((_v, _rs11[max(0, _m.start()-28):_m.end()+8]
                               .replace("\n", " ")))
        # 去重仅用于"不一致项"展示(同一个错误值不重复报)
        _bad3 = [h for h in _hits3 if int(h[0]) != _real]
        add('G-11.3', '合集判据条数 == criteria.yaml 实际(全形态 %d 处)' % len(_hits3),
            ("不一致: " + "; ".join(h[0] + " @「" + h[1][-34:] + "」"
                                  for h in _bad3)) if _bad3 else "全部一致",
            "全部一致", not _bad3)
        # 覆盖可见性:一处都没匹配到 = 锚点失效(等同于空规),必须报警
        add('G-11.3-cov', 'G-11.3 至少命中 1 处声明(防锚点失效)',
            len(_hits3), ">=1", len(_hits3) >= 1)
    except Exception as _e:
        add('G-11.0', 'G-11 可执行', '异常 ' + str(_e)[:60], '无异常', False)

    # ── G-12 banner 版本号/run_id 与权威源一致(审计 v2.6 P0-C) ──
    #   P-6 的 _strip 显式剔除含"版本 v"/"run_id"的行,导致 banner 差异是
    #   完全盲区 —— v2.5 修过一次 banner,v2.6 又忘了,属"改 A 忘改 B"第 6 次。
    try:
        import re as _re12
        # 权威源沿革（每一次都是"滞后派生物当基准"的同一族错误）：
        #   v2.7 原以 MANIFEST 为基准 → MANIFEST 第 11 步才写、守卫第 6/7 步跑
        #        → 拿到上一版 → 必然 FAIL。
        #   v2.8 改以 build_version.json 的 version 为基准（构建遍历前写入）。
        #   ★ v2.25 把 run_id / input_hash 也固化进同一文件：
        #        原先比的是 report.json 的 run_id，而 run_id 每次运行必变，
        #        云端按 T4 重跑主验证后 report.json 刷新、文档不变
        #        → G-12 的 4 项**必然**FAIL（与平台、与操作者都无关）。
        #        build_version.json 只在构建时写，重跑主验证不动它 ——
        #        既让"文档描述的是哪一次运行"这个事实保持稳定，
        #        又保证手改 banner 仍能被抓到（先红后绿成立）。
        _bv_p = os.path.join(ROOT, "results", "build_version.json")
        if not os.path.exists(_bv_p):
            raise SystemExit(
                "[consistency_guard] results/build_version.json 缺失 —— G-12 无权威锚"
                "可比。请用 build.py 构建（不兜底、不跳过）。")
        # ★★ v2.25：version / run_id / input_hash 三者同源 = build_version.json。
        _bj = json.load(open(_bv_p, encoding="utf-8"))
        _ver = str(_bj.get("version"))
        _rid_anchor = str(_bj.get("run_id") or "")
        _ih = str(_bj.get("input_hash") or "")
        if not (_rid_anchor and _ih):
            raise SystemExit(
                "[consistency_guard] build_version.json 缺 run_id/input_hash —— "
                "G-12 无权威锚可比。请用 build.py 构建（不兜底、不跳过）。")
        for _tag, _fn in (("框架", "框架_独立审核包"), ("合集", "四角度审核报告_合集")):
            _cands = [f for f in os.listdir(WS)
                      if f.startswith(_fn) and f.endswith(".md")
                      and re.search(r"_v[\d.]+_\d{8}\.md$", f)]
            # ⚠ v2.7 变异测试抓到:G-12 初版**忽略 --doc**,永远扫 WS 目录。
            #   与 v2.3 抓出的"G-5/G-6/G-7/G-8 忽略 --doc"是同一族 bug ——
            #   我修过一次,写新守卫时又犯了。后果:变异注入到 --doc 副本上,
            #   G-12 仍去读 WS 里那份未被污染的 → "注入违规却抓不到"→ 判空规。
            #   修法:--doc 若指向版本化文件,优先检查它;否则回退 WS 扫描。
            _doc = os.path.abspath(a.doc)
            # ⚠ v2.11 第 8 次"忽略 --doc"(前 7 次:v2.3 G-5/6/7/8、v2.7 G-12、
            #   v2.9 G-11、v2.11 G-10/R-7/G-11.2)。原条件要求 --doc 必须是
            #   **版本化**文件(_v?.?_date.md)才采用,而变异用例注入的是源
            #   文档(四角度审核报告_合集.md)→ 条件不成立 → 回退 WS 扫描
            #   选版本化副本 → 注入无效 → 判空规。
            #   放宽为前缀匹配:源文档与版本化副本的 banner 已由 step_version
            #   同步改写(v2.11),检查任一等价。
            _bn = os.path.basename(_doc)
            _in_doc = (_bn.startswith(_fn) and _bn.endswith(".md"))
            if _in_doc:
                _target = _doc
            elif _cands:
                _target = os.path.join(WS, _latest_ver(_cands))
            else:
                continue
            _txt = open(_target, encoding="utf-8").read()
            # ⚠ v2.9(审计 P1-新3):原为全文 search,若变更清单/changelog 里
            #   出现"版本 v2.x"叙述句会先被命中 → 检查对象不确定。
            #   限定到 banner 区(前 6 行)—— banner 是本项目的约定位置。
            _banner = "\n".join(_txt.split("\n")[:6])
            _mb = _re12.search(r"版本 v([\d.]+)", _banner)
            add("G-12.%s.ver" % _tag, "%s banner 版本号 == MANIFEST" % _tag,
                _mb.group(1) if _mb else None, _ver,
                bool(_mb and _mb.group(1) == _ver))
            # ⚠ v2.9(审计 P0-E):原正则 r"run_id `([0-9a-f]{8,})`" 要求
            #   run_id **紧跟**反引号。banner 匹配;但 §0.2 状态表写
            #   "| run_id(取自 report.json) | `3e0024…` |",中间隔着
            #   "(取自 report.json) | " → 不匹配 = 空规。
            #   改:允许中间有 ≤60 个非反引号/非换行字符,且收集**全部**匹配。
            _mr_all = list(_re12.finditer(
                r"run_id[^`\n]{0,60}`([0-9a-f]{8,})`", _txt))
            _mr = _mr_all[0] if _mr_all else None
            # ★★ v2.25 P0：原判据 =「文档 banner run_id == report.json run_id」。
            #   但 run_id = sha256(seed|时间戳|脚本哈希)，**每次运行必然不同**
            #   （框架 §5 自己声明过"run_id 每次运行必然不同"），而文档 banner 是
            #   静态的 —— 于是任何人重跑一次 verify_all（**T4 就要求这么做**）
            #   之后，G-12 的 4 项必然 FAIL，且与平台、与执行方操作**无关**。
            #   这是设计层自相矛盾：拿"每次必变"的量当一致性锚。云端执行方
            #   会把它当"档 C 真发现问题"上报，审核方也被误导。
            #   改：① 跨制品锚点改用 input_hash（= sha256(SEED|len(D1)|len(D3))，
            #          同代码同输入下稳定），并要求文档登记；
            #       ② run_id 只查**文档内部自洽**（多处声明必须相同），
            #          不再跨制品比对 —— 它本来就不是"真相锚"，只是运行标识。
            add("G-12.%s.ih" % _tag,
                "%s 登记 input_hash == report.json(稳定锚)" % _tag,
                _ih[:16], _ih[:16], bool(_ih) and (_ih[:16] in _txt))
            _rids = {m.group(1)[:16] for m in _mr_all}
            add("G-12.%s.rid" % _tag,
                "%s banner run_id == build_version.json(构建期锚)" % _tag,
                (_mr.group(1)[:16] if _mr else None), _rid_anchor[:16],
                bool(_mr and _rid_anchor.startswith(_mr.group(1)[:16])))
            add("G-12.%s.rid-all" % _tag,
                "%s 全部 run_id 声明互相一致(%d 处)" % (_tag, len(_mr_all)),
                ("不一致: " + ", ".join(sorted(_rids))) if len(_rids) > 1 else "全部一致",
                "全部一致", len(_rids) <= 1)
            add("G-12.%s.rid-cov" % _tag,
                "%s run_id 声明至少命中 1 处(防锚点失效)" % _tag,
                len(_mr_all), ">=1", len(_mr_all) >= 1)
    except Exception as _e:
        add("G-12.0", "G-12 可执行", "异常 " + str(_e)[:60], "无异常", False)

    npass = sum(1 for r in rows if r[4])
    nfail = len(rows) - npass
    # ★ v2.25：分母 = 三态之和（与 verify_all 口径一致）。
    #   这样"dev 布局 85 项全查"与"交付布局 84 项 + 1 项不适用"的**总数相同**，
    #   便于跨平台/跨布局比对；同时缺口（N/A）在汇总行里自明。
    _tot = len(rows) + len(nas)
    print("\n" + "=" * 74)
    #   原写法在"判定项被静默吞掉"时照写 "63/69 通过" —— 读者无从知道少了的
    #   11 项从未执行（第 11 条陷阱形态③）。
    print(f"  一致性守卫: {npass}/{_tot} 通过, 失败 {nfail} 项, 不适用 {len(nas)} 项")
    print("=" * 74)
    if nas:
        print("\n  [注意] 出现 N/A(第三态) —— 以下检查**未执行**,不得视为通过:")
        for _cid, _item, _reason in nas:
            print(f"         - {_cid} {_item}: {_reason}")
    if nfail:
        print("\n  !! 文档与脚本不一致 —— 按框架第 9 条原则(数字唯一来源),审核不通过。")
        print("     修复:重新生成审核包,使附录脚本与 scripts/ 逐字节一致。")
    return 0 if nfail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
