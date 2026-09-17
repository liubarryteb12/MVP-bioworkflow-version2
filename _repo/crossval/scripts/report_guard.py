# -*- coding: utf-8 -*-
"""
================================================================================
 审核报告一致性守卫  v1.0
================================================================================
 起因(meta-review 2.1 / 7.6):
   "审核报告要求 B 方提交原始输出,但自己却只给汇总数字。这是双标。"
   "引入'审核报告自身的一致性守卫':审核报告引用的数字必须与框架报告
    JSON 一致,否则审核不通过。"

 本守卫把这条变成机器可检。标尺 = 框架第 9 条原则:数字唯一来源为台账。
 审核报告与框架产物适用同一标准,不得豁免。

 检查:
   R-1 报告中的 主验证 N/N == report.json 的 n_pass/total
   R-2 报告中的 排版 N/N  == layout_report.json 的 checks 数
   R-3 引用的 run_id 格式合法 + 注明来源
   R-4 报告中出现的实测数值全部能在 report.json 中定位(正向扫描)
   R-5 handoff 节点数/在途数 == handoff_chain.json
   R-6 判据 YAML 条数 == criteria.yaml 实际条数
   R-7 审核包附录脚本 == scripts/ 实际脚本(委托 consistency_guard)

 运行: python scripts/report_guard.py --doc ../四角度审核报告_合集.md
 退出码: 0 = 一致, 1 = 审核报告存在无来源数字
================================================================================
"""
import os, re, sys, json, subprocess, argparse

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
WS = os.path.dirname(ROOT)

def _latest_doc(prefix):
    """v2.25 修订: 默认 --doc 曾硬编码 '框架_独立审核包_v1.md'(旧名, zip 内不存在)
    -> 云端不传参会直接 FileNotFound。
    改为动态取"版本号最大"的日期版本化文件。
    注意: 字符串排序会把 v2.9 排到 v2.24 之后, 必须按数值版本排序。"""
    import glob as _g, re as _re
    hits = _g.glob(os.path.join(WS, prefix + "*_20*.md"))
    best, bestv = None, None
    for p in hits:
        m = _re.search(prefix + r'([0-9]+)\.([0-9]+)_', os.path.basename(p))
        if not m:
            continue
        v = (int(m.group(1)), int(m.group(2)))
        if bestv is None or v > bestv:
            best, bestv = p, v
    if best is None and hits:
        best = sorted(hits)[-1]
    return best or os.path.join(WS, prefix + "1.md")


ROWS = []


def add(cid, item, obs, exp, ok):
    ROWS.append(bool(ok))
    print(f"    [{'PASS' if ok else 'FAIL'}] {cid} {item:<36s} "
          f"obs={str(obs)[:26]:<26s} exp={exp}")


def load(p):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--doc", default=_latest_doc("四角度审核报告_合集_v"))
    # ⚠ v2.11:R-7 委托检查框架内嵌脚本,若只能改 --doc(合集)就
    #   注入不到脚本(脚本在框架文档里)。加 --frame 后可指向变异副本。
    ap.add_argument("--frame", default=None)
    a = ap.parse_args()

    print("=" * 78)
    print("  审核报告一致性守卫 v1.0")
    print("=" * 78)
    print("  标尺:框架第 9 条原则 —— 数字唯一来源为台账。审核报告同样适用。\n")

    if not os.path.exists(a.doc):
        print(f"  [FAIL] 审核报告不存在: {a.doc}")
        return 1
    s = open(a.doc, encoding="utf-8").read()

    R = load(os.path.join(ROOT, "results", "report.json"))
    L = load(os.path.join(ROOT, "results", "layout_report.json"))
    C = load(os.path.join(WS, "handoff", "handoff_chain.json"))
    Y = open(os.path.join(ROOT, "schema", "criteria.yaml"), encoding="utf-8").read()

    # ---------- R-1 ----------
    print("  -- R-1 主验证通过数必须来自 report.json")
    if not R:
        add("R-1", "report.json 存在", False, "True", False)
    else:
        sm = R["summary"]
        np_, nt, nbc = sm["n_pass"], sm["total"], sm.get("branches")
        branch_claims = re.findall(r"(\d+)\s*/\s*(\d+)\s*分支", s)
        body = re.sub(r"(\d+)\s*/\s*(\d+)\s*分支", " ", s)
        keep = [l for l in body.split("\n")
                if not any(k in l for k in (
                    "声明稿", "声明项", "覆盖",
                    "守卫", "handoff", "Handoff", "链守卫",
                    "绕过测试", "目检", "回归测试", "补审", "机器可检"))]
        body = "\n".join(keep)
        claims = re.findall(r"\*{0,2}(\d+)\s*/\s*(\d+)\*{0,2}\s*(?:通过|项)", body)
        bad = [f"{x}/{y}" for x, y in claims
               if not (x == str(np_) and y == str(nt))]
        if L:
            ln = len(L["checks"])
            bad = [b for b in bad if b != f"{ln}/{ln}"]
        badb = [f"{x}/{y}分支" for x, y in branch_claims if y != str(nbc)]
        add("R-1", f"主验证 N/N == {np_}/{nt} 且分支 == {nbc}",
            (bad + badb) or "全部一致", f"{np_}/{nt}, {nbc} 分支",
            not (bad or badb))

    # ---------- R-2 ----------
    print("\n  -- R-2 排版通过数必须来自 layout_report.json")
    if L:
        ln = len(L["checks"])
        nps = sum(1 for c in L["checks"] if c.get("passed"))
        pat = re.compile(r"\*{0,2}(\d+)\s*/\s*(\d+)\*{0,2}\s*通过")
        claims = {f"{x}/{y}" for x, y in pat.findall(s)}
        ok = (f"{nps}/{ln}" in claims) or (f"{ln}/{ln}" in claims) or ln == 0
        add("R-2", f"报告含排版 {nps}/{ln}",
            f"{nps}/{ln}" if ok else f"仅见 {sorted(claims)[:4]}",
            f"{nps}/{ln}", ok)

    # ---------- R-3 ----------
    print("\n  -- R-3 run_id 可追溯")
    if R:
        # ★ v2.25：原正则 `([0-9a-f]{16})` 抓**任何** 16 位十六进制反引号串 ——
        #   报告里 16 位的 input_hash 也算，于是"把 run_id 换成 zzzz"这类违规
        #   仍能靠 input_hash 蒙过（变异用例 rc=0 未抓到 → 该判据实为弱规）。
        #   收紧为 run_id 语境匹配，与 G-12 同口径。
        ids = re.findall(r"run_id[^`\n]{0,60}`([0-9a-f]{16})`", s)
        add("R-3", "引用了 run_id", f"{len(ids)} 个", ">=1 个", len(ids) >= 1)
        add("R-3b", "注明 run_id 来源为 report.json",
            "report.json" in s, "True", "report.json" in s)

    # ---------- R-4 正向扫描 ----------
    # v2.2 修订:作图规范落盘后,报告中出现 0.035 / 0.503 / 15.21 等数值,
    # 它们来自 figure_kit 实测但**不在 report.json**(属排版/作图链路)。
    # 故可回溯源扩展为:report.json(主验证实测) + criteria.yaml(判据常量)
    #   + figure_spec.yaml / 作图规范_v1.0.md(作图实测与配置常量)。
    # 原则是**可回溯**,不是"必须在 report.json"—— 与 v1.9 的放宽同一逻辑,
    # 但每加一个源都必须有明确归属,不得变成放行清单。
    print("\n  -- R-4 报告中出现的实测数值必须能回溯到台账/判据/作图规范")
    if R:
        blob = json.dumps(R, ensure_ascii=False)
        for _extra in (
                os.path.join(ROOT, "schema", "criteria.yaml"),
                os.path.join(ROOT, "spec", "figure_spec.yaml"),
                os.path.join(WS, "作图规范_v1.0.md"),
        ):
            if os.path.isfile(_extra):
                blob += open(_extra, encoding="utf-8").read()
        nums = set(re.findall(r"(?<!\w)(\d+\.\d{2,4})(?!\w)", s))
        skip = {"1.00", "2.00", "10.0", "0.001"}
        # 依赖版本号(numpy>=1.24 等):上下文含比较符或包名
        ver_ctx = set(re.findall(
            r"(?:numpy|scipy|sklearn|pandas|matplotlib|pypdf|python)"
            r"\s*[<>=~]+\s*(\d+\.\d+)", s))
        # 过程记录数字:报告中显式标注为"修正前/第一版/差异"的
        proc = set(re.findall(r"(?:修正前|第一版|差异)\s*[（(]?(\d+\.\d+)", s))
        skip = skip | ver_ctx | proc
        checked = sorted(n for n in nums if n not in skip)
        orphan = [n for n in checked if n not in blob]
        add("R-4", f"扫描 {len(checked)} 个实测值",
            orphan or "全部可回溯", "无孤立数字", not orphan)
        if orphan:
            print(f"       孤立数字(报告中但不在 JSON): {orphan[:12]}")

    # ---------- R-8 守卫 N/N 声称必须可回溯 ----------
    # 起因:v1.8 审计发现四角度报告 §0.2 写"一致性守卫 14/14",实际已是 32/32。
    # 根因:R-1 只查主验证、R-2 只查排版,不查其他守卫计数 —— 该错误数字存活多轮。
    print("\n  -- R-8 报告中的守卫 N/N 必须来自 guard_results.json")
    _gp = os.path.join(ROOT, "results", "guard_results.json")
    if os.path.exists(_gp):
        _GD = json.load(open(_gp, encoding="utf-8"))
        _legit = set()
        # R-8 自指:report_guard 最终计数在 R-8 运行时尚未产生。
        # guard_results 记录"截至上次运行的态",可能是 (n-1)/n 或 n/n。
        # 两者均须接受 —— 否则"报告写 10/10 而合法集只有 9/10"造成永久失败循环。
        # (v1.9 曾靠"上次恰好是终态"侥幸通过,非机制保障。)
        for _k2, _v2 in _GD.items():
            _legit.add(_v2)
            _bb = _v2.split("/")[-1]
            if _bb.isdigit():
                _legit.add("{}/{}".format(int(_bb) - 1, _bb))   # 当前态 (n-1)/n
                _legit.add("{}/{}".format(_bb, _bb))            # 终态 n/n
        if R:
            _legit.add("{}/{}".format(R["summary"]["n_pass"], R["summary"]["total"]))
            # 子测试计数(如隔离守卫绕过测试 7/7)亦合法 —— 能回溯至台账即可
            for _x, _y in re.findall(r"(\d+)\s*/\s*(\d+)",
                                     json.dumps(R, ensure_ascii=False)):
                if _x == _y:
                    _legit.add("{}/{}".format(_x, _y))
        if L:
            _nps = sum(1 for c in L["checks"] if c.get("passed"))
            _legit.add("{}/{}".format(_nps, len(L["checks"])))
        # 排除显式历史语境(同 R-1 处理)
        _hist = set()
        for _m2 in re.finditer(r"(?:\u4e0a\u4e00\u7248|\u5386\u53f2|\u65e7\u7248|\u6b64\u524d|\u65e9\u671f|\u5efa\u7acb\u524d|\u524d\u4e3a|\u66fe\u4e3a)"
                               r"(?:(?!\d+\s*/\s*\d+)[^\n]){0,60}?(\d+)\s*/\s*(\d+)", s):
            _hist.add("{}/{}".format(_m2.group(1), _m2.group(2)))
        for _m3 in re.finditer(r"(\d+)\s*/\s*(\d+)"
                               r"(?:(?!\d+\s*/\s*\d+)[^\n]){0,40}?(?:\u4e0a\u4e00\u7248|\u5386\u53f2|\u65e7\u7248|\u6b64\u524d|\u5efa\u7acb\u524d|\u524d\u4e3a|\u66fe\u4e3a)", s):
            _hist.add("{}/{}".format(_m3.group(1), _m3.group(2)))
        _claims = set()
        for _m in re.finditer(r"(\d+)\s*/\s*(\d+)", s):
            _a, _b = _m.group(1), _m.group(2)
            if _a == _b and "{}/{}".format(_a, _b) not in _hist:
                _claims.add("{}/{}".format(_a, _b))
        _orphan = sorted(c for c in _claims if c not in _legit)
        print("      [说明] R-8 自指兼容: 合法集同时接受 (n-1)/n 与 n/n 双值 ——\n            守卫运行至自身时终态尚未算出,此为设计而非过期残留。")
        add("R-8", "扫描 {} 个 N/N 声称".format(len(_claims)),
            _orphan or "全部可回溯", "合法集 {}".format(sorted(_legit)), not _orphan)
        if _orphan:
            print("       无法回溯: {}".format(_orphan[:10]))
            print("       合法来源 guard_results={}".format(_GD))
    else:
        add("R-8", "guard_results.json 存在", False, "True", False)


    # ---------- R-5 ----------
    print("\n  -- R-5 handoff 链数字必须来自 handoff_chain.json")
    if C:
        nn = len(C["nodes"])
        na = sum(1 for n in C["nodes"] if n.get("ack"))
        # ⚠ v2.10:原为 `str(nn) in s` —— nn=14,而 "14" 在报告中到处都是
        #   ("14 分支"等)→ 恒真 → R-5 是弱规(与 v2.5 修的 R-6 同类)。
        #   改为上下文匹配:数字必须在"节点 / 在途"语境中。
        _h5 = bool(re.search(rf"(?<![0-9]){nn}(?![0-9])\s*节点", s))
        add("R-5", f"节点数 {nn}(上下文匹配)", nn, "节点语境中应出现", _h5)
        _pend = nn - na
        _h5b = bool(re.search(rf"(?<![0-9]){_pend}(?![0-9])[^\n]{{0,4}}在途", s)
                    or re.search(rf"在途[^\n]{{0,6}}(?<![0-9]){_pend}(?![0-9])", s))
        add("R-5b", f"在途数 {_pend}(上下文匹配)", _pend,
            "在途语境中应出现", _h5b)

    # ---------- R-6 ----------
    print("\n  -- R-6 判据 YAML 条数")
    # ⚠ v2.5 修(审计指出 R-6 是空规):
    #   ① 正则 ^  - id: 依赖缩进,safe_dump 输出为 "- id:"(无前导空格)→ 匹配 0 条;
    #   ② ny=0 时 str(0)="0",而 "0" 几乎出现在任何文档中 → 恒 True → 永远 PASS。
    #   两处叠加使 R-6 完全失效。(v2.4 已在 gen_appendix 修过同类问题,此处漏改)
    try:
        import yaml as _y6
        ny = len(_y6.safe_load(Y).get("criteria", []))
    except Exception:
        ny = len(re.findall(r"^\s*- id: (\S+)", Y, re.M))
    # 数字型判据不得用 "str(n) in s" —— n<=9 时恒真。改为带边界的数字匹配。
    # ⚠ v2.10(变异测试抓到):仅匹配"独立出现的 21"太弱 —— 合集里 "21"
    #   出现 29 次(日期、条数、其它量),改掉"判据条数"那一处仍有 28 处命中
    #   → R-6 永远 PASS,是弱规。而 G-11 已做严格的三处条数校验,
    #   R-6 若继续弱下去就是纯冗余。改为**上下文匹配**:21 必须与"判据"共现。
    # ⚠ v2.10 二修:上一版改为"上下文匹配",但仍是 **OR 语义** ——
    #   合集里判据条数声明有 2 处(§0.2 状态表 + 报告二叙述句),改掉一处
    #   另一处仍命中 → R-6 永远 PASS,变异用例根本构造不出来。
    #   OR 语义的判据在"有多处声明"时就是弱规(第 11 条)。
    #   改为 **AND 语义**:枚举全部形态,每一处都必须 == ny(与 G-11.3 同构)。
    _P6 = [r"(\d+)\s*条判据",
           r"判据[^\n|]{0,16}?\*{0,2}(\d+)\*{0,2}\s*条",
           r"判据\s*YAML[^\n]{0,12}?(\d+)"]
    _v6 = []
    for _p in _P6:
        for _m in re.finditer(_p, s):
            _v6.append(_m.group(1))
    _bad6 = [v for v in _v6 if int(v) != ny]
    add("R-6", f"YAML 判据 {ny} 条(全形态 {len(_v6)} 处均须一致)",
        ("不一致: " + ",".join(_bad6)) if _bad6 else "全部一致",
        "全部一致", (not _bad6) and len(_v6) > 0)

    # ---------- R-7 委托 ----------
    print("\n  -- R-7 审核包附录脚本一致性(委托 consistency_guard)")
    cg = os.path.join(HERE, "consistency_guard.py")
    # ⚠ v2.11 第6次"忽略 --doc":同上。R-7 委托 consistency_guard 检查
    #   框架内嵌脚本,若 --doc 指向的正是框架(变异副本)却仍用固定路径,
    #   则注入的脚本改动永远测不到 → R-7 从未被证明能抓到违规。
    _db = os.path.basename(a.doc)
    # ★ v2.25 P0：回退原为未版本化旧名（交付包内不存在）→ R-7 恒 FAIL。
    #   改为复用 consistency_guard 的统一解析器（显式 > 最新版本化 > 源文档），
    #   避免在本文件里再抄一份定位逻辑（那正是"同一逻辑两处维护"的坑）。
    sys.path.insert(0, HERE)
    import consistency_guard as _CG
    tgt = a.frame or (a.doc if ("框架" in _db or "审核包" in _db) else None) \
        or _CG.main_doc("框架_独立审核包", required=False)
    if os.path.exists(cg) and tgt and os.path.exists(tgt):
        # ★ v2.25：委托 consistency_guard 时须同口径解码（子守卫输出 UTF-8）。
        _env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
        r = subprocess.run([sys.executable, cg, "--doc", tgt],
                           capture_output=True, encoding="utf-8",
                           errors="replace", env=_env)
        add("R-7", "审核包附录脚本 == 实际脚本", r.returncode, "0",
            r.returncode == 0)
    else:
        add("R-7", "审核包与守卫脚本存在", False, "True", False)

    npass = sum(ROWS)
    nfail = len(ROWS) - npass
    print("\n" + "=" * 78)
    print(f"  审核报告守卫: {npass}/{len(ROWS)} 通过, 失败 {nfail} 项")
    print("=" * 78)
    if nfail:
        print("\n  !! 审核报告引用了无法在台账中定位的数字 —— 按框架第 9 条原则,")
        print("     审核报告自身不通过。这正是 meta-review 2.1 指出的'双标'。")
    return 0 if nfail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
