# -*- coding: utf-8 -*-
"""
================================================================================
 原始输出附录生成器  v1.0
================================================================================
 起因(对《附录_原始输出.md》的审核):
   - "附录与合集数字不一致(5 处)"
   - "F/G 节重复"
   - "缺 criteria.yaml"
   - "G-3 只检查 6/70 个数字"

 根因:**附录是手工拼装的,与脚本/报告无强制同步**。
 修法:**附录改为脚本生成**,每次运行都从当前 results/ 与 schema/ 读取,
 杜绝"附录说 70、合集说 72"这类漂移。

 生成内容:
   A report.json summary + run_metadata
   B 判定项按分支分布(含 changelog)
   C 完整判定台账(逐项,全量)
   D 排版判定项(逐项,全量)
   E handoff 链摘要
   F criteria.yaml 全文(审计指出缺失)
   G 三个守卫原始 stdout(单次,不重复)

 运行: python scripts/gen_appendix.py
================================================================================
"""
import os, re, json, sys, subprocess, argparse
# ── 控制台编码加固（v2.25）──────────────────────────────────────────────────
# 起因：中文 Windows 默认控制台 cp936(GBK) 无法编码 ₀/₁/₂/✗ → UnicodeEncodeError。
try:
    if sys.stdout.isatty():
        sys.stdout.reconfigure(errors="replace")
    else:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(errors="replace")
except (AttributeError, ValueError):
    pass
from collections import Counter
from datetime import datetime, timezone, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
WS = os.path.dirname(ROOT)
OUT = os.path.join(WS, "附录_原始输出.md")
CST = timezone(timedelta(hours=8))

# 数字变化 changelog —— 审计要求"列出每次变化及原因"
CHANGELOG = [
 ("44/44 → 33/33", "首轮审核发现 44/44 是手工统计,脚本实际 33 项。改为动态取自 report.json。"),
 ("33 → 45", "修复竞争风险 bug(KM 与 CIF 算法相同)、EPV 重构、多页 PDF 扫描、每分支独立种子。"),
 ("45 → 69", "补分支 T15/T16/T17(条件启动判据,此前从未验证)+ 分支 10(竞争风险/EPV/可行性)。"),
 ("69 → 70", "隔离守卫升 v2:新增绕过回归测试 7 项合并计 1 项判定。"),
 ("70 → 72", "将 s=1.6 边界情形正式纳入脚本(此前该数字仅存在于探索阶段与报告中,\n"
             "     无台账来源 —— 违反第 9 条原则,已补为正式判据 2 项)。"),
 ("72 → 74", "分支 6 重写:漂移公式统一为 |ΔOR|/OR₁,并新增多种子漂移区间与翻转率判定。"),
 ("13.9% → 33.0%", "分支 6 重构两次(重叠度 50%→32.5%;信号基因由噪音改为真实携带程序活性)。\n"
                   "     旧值 13.9% 作废。同时:**'且方向翻转'经 12 种子验证仅 5/12 发生,\n"
                   "     属种子依赖,已改为概率表述**,不再写成确定性结论。"),
 ("handoff 10 → 11", "新增 L-6c(无自指检查)。合集曾写 10/10,未同步。"),
    ("v1.7 判定项 74 → 85", "P1 七条修复:分支 4 绝对量级 +3、分支 6 Jaccard +3、分支 8 合并辅助判据 +5。"),
    ("v1.7 一致性守卫 14 → 29", "新增 G-5(criteria 关键值必须在框架正文出现),首次运行即抓出 4 项不同步。"),
    ("v1.8 一致性守卫 29 → 32", "新增 G-5.DEPR(已废弃表述不得未标注残留),首次运行抓出 1 项。"),
    ("v1.9 审核报告守卫 9 → 10", "新增 R-8(报告中所有守卫 N/N 必须可回溯至 guard_results.json)。"),
    ("v1.9 §0.2 一致性守卫 14/14", "审计发现:该数字自 G-5 建立后从未更新(G-5 建前值),存活多轮未被任何守卫发现。"),
    ("v1.9 R-8 另行抓出 3 处", "3/3(隔离守卫旧拦截值,现 7/7)、74/74(旧主验证值,现 85/85)—— 均为过期残留,已修。"),
      ("v2.7 判据条数 0 → 21",
       "gen_appendix 统计用旧正则(依赖前导空格),safe_dump 输出无缩进 → "
       "数出 0。同一脚本内两套算法并存。"),
      ("v2.7 G-11 / G-12 新增",
       "判据条数(附录/框架/合集三处)与 banner 版本号/run_id 一致性;"
       "均纳入 MUST_COVER 变异测试。"),
      ("v2.8 MUST_COVER 强制",
       "新增守卫必须带变异用例,否则 G-COV FAIL(代码强制,非流程约定)。"
       "覆盖率可见化:守卫家族 19 个,已覆盖 7。"),
      ("v2.8 附录 banner 加版本",
       "加版本与 run_id;版本由 build --version 传入,不读滞后的 MANIFEST。"),
      ("v2.9 G-11.3 正则锚点修正",
       "原只匹配叙述句;合集 §0.2 状态表写「判据 YAML **19** 条」→ "
       "不匹配 = 空规。改多形态全量匹配 + 新增 G-11.3-cov。"),
      ("v2.10 MANIFEST.verification 改为派生",
       "原 layout/pytest/mutation 三项**硬编码**;mutation 写 '6/6' 而实际已 "
       "12/12 —— 汇总撒谎(第 11 条陷阱形态③)。改为全部从结果文件派生。"),
      ("v2.10 vXX_fixes 由 build.py 写入",
       "原靠手工追加 → v2.8/v2.9 的 fixes 从未进入 MANIFEST,G-6.0 对这两版 "
       "FAIL。与'gen_appendix 最后跑'同理:写进文档不管用,必须由代码写入。"),
      ("v2.10 变异用例扩充(覆盖率 36%→57%)",
       "新增 G-1 / G-3 / R-6 文档变异 + G-7 文件系统变异(fs 变异带残留检测)。"
       "覆盖率统计改为**仅计实际抓到的用例**,禁止无条件添加 —— 否则覆盖率虚高, "
       "与'守卫一直通过=空规'是同一种自欺。"),
      ("v2.10 G-11.3 命中数按位置计数",
       "原按**值**去重 → 两处都写 21 时只报 1 处,覆盖广度不可见。"),
      ("v2.10 消除静默 except",
       "gen_appendix 的 ImportError: pass 会静默跳过 criteria 自检 → 改为 "
       "fail loudly;platform_check 两处为预期路径,补注释说明。"),
      ("v2.9 G-12 正则锚点修正",
       "原要求 run_id 紧跟反引号;§0.2 隔着括号 → 不匹配 = 空规。"
       "改允许间隔 + 全量校验 + 新增 rid-all / rid-cov。"),
      ("v2.9 G-11 忽略 --doc",
       "第三次复发(v2.3 G-5/6/7/8、v2.7 G-12 已修,G-11 漏修)。"),
      ("v2.9 变异测试分发 bug",
       "原按文档类型分发(合集→report_guard),但 G-11.3/G-12.合集.* 在 "
       "consistency_guard → 恒未抓到 → 误判空规。改按 expect_id 前缀。")
  ]


# 术语表:符号 -> (定义, 实测, 易混淆对象)。实测值动态取自 report.json。
def build_terms(R):
    b10 = R.get("b10_stats", {}).get("competing_risk", {})
    b6 = R.get("b6_flip", {})
    b8 = R.get("b8_hardblock", {})
    ep = b8.get("endpoint", {}); lk = b8.get("leakage", {}); pr = b8.get("pseudoreplication", {})
    g0 = b10.get("cif_km_g0", 0) - b10.get("cif_correct_g0", 0)
    g1 = b10.get("cif_km_g1", 0) - b10.get("cif_correct_g1", 0)
    return [
      ("diff_km", "KM 法(忽略竞争)的**组间差** CIF₁−CIF₀",
       f"{b10.get('diff_km', 0):.3f}", "与 overestimate_g0 数值接近,**不是同一个量**"),
      ("diff_correct", "CIF 法(正确处理竞争)的**组间差**",
       f"{b10.get('diff_correct', 0):.3f}", "同上"),
      ("overestimate_g0", "组0 的 KM 相对 CIF 的**高估量**",
       f"{g0:+.3f}", "**不是**组间差"),
      ("overestimate_g1", "组1 的 KM 相对 CIF 的**高估量**",
       f"{g1:+.3f}", "**不是**组间差"),
      ("distortion", "扭曲量 = |diff_km − diff_correct|",
       f"{abs(b10.get('diff_km',0)-b10.get('diff_correct',0)):.3f}", "衡量忽略竞争的净后果"),
      ("drift_pct", "程序定义漂移 = |OR₂−OR₁|/OR₁",
       f"{b6.get('drift_pct', 0):.1f}%", "种子依赖,非固定值"),
      ("flip_rate", "换成员集后**方向翻转**的多种子发生率",
       f"{b6.get('flip_n', 0)}/{b6.get('n_seed', 0)}", "**概率,非必然**;禁写'且翻转'"),
      ("inflation", "泄露导致的 AUC 虚高 = AUC_leak − AUC_clean",
       f"+{lk.get('inflation', 0):.3f}", "'虚高'是差值,不是 AUC 本身"),
      ("I2", "终点合并异质性", f"{ep.get('I2', 0)}%",
       "k=2 时不稳定,**须配辅助判据**"),
      ("p_cell / p_donor", "伪重复:细胞级 vs 患者级检验 p 值",
       f"{pr.get('p_cell', 0):.1e} / {pr.get('p_donor', 0)}", "两者不可互换"),
    ]


APPENDIX_VERSION = ""
_RUN_ID = "unknown"

def main():
    REPORT_DOC = os.environ.get("REPORT_DOC",
                             os.path.join(WS, "四角度审核报告_合集.md"))
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", default="")
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args()
    # v2.8:版本由 build 传入(--version),不读 MANIFEST(滞后派生物);
    # run_id 取 report.json(权威源)。二者写入 banner 供 G-12/G-11 核验。
    global APPENDIX_VERSION, _RUN_ID
    if a.version:
        APPENDIX_VERSION = a.version
    try:
        _rp = os.path.join(ROOT, "results", "report.json")
        _RUN_ID = str(json.load(open(_rp, encoding="utf-8"))
                      .get("run_metadata", {}).get("run_id", ""))[:16]
    except Exception:
        _RUN_ID = "unknown"

    R = json.load(open(os.path.join(ROOT, "results", "report.json"), encoding="utf-8"))
    L = json.load(open(os.path.join(ROOT, "results", "layout_report.json"), encoding="utf-8"))
    C = json.load(open(os.path.join(WS, "handoff", "handoff_chain.json"), encoding="utf-8"))
    TERMS = build_terms(R)
    Y = open(os.path.join(ROOT, "schema", "criteria.yaml"), encoding="utf-8").read()
    # 自检:重复顶层键(第四轮审计 §5 发现 tools:/invariants: 各出现两次,
    # safe_load 会静默后者覆盖前者 → 行为不确定)
    _dup = [k for k in ("criteria:", "tools:", "invariants:")
            if Y.count("\n" + k) > 1]
    if _dup:
        raise SystemExit(f"[gen_appendix] criteria.yaml 存在重复顶层键 {_dup} —— 先修再生成")
    try:
        import yaml as _y
        _d = _y.safe_load(Y)
        _n = len(_d["criteria"])
        assert _n >= 19, f"criteria 条数异常 {_n}(不应少于 19)"
        _ids = [c.get("id") for c in _d["criteria"]]
        assert len(_ids) == len(set(_ids)), f"criteria id 重复: {_ids}"
        assert all(isinstance(x, str) for x in _d["invariants"]), "invariants 含非字符串"
    except ImportError:
        # ⚠ v2.10:原为静默 pass —— yaml 不可用时**整段断言被跳过**,
        #   而后续多处依赖 yaml。静默跳过等于"自检消失但不报错"。
        #   改为 fail loudly:依赖缺失是致命的,不是可降级的。
        raise SystemExit("[gen_appendix] PyYAML 不可用 —— criteria.yaml "
                         "自检无法执行,拒绝生成附录(请先 pip install pyyaml)")

    sm = R["summary"]
    n_pass, n_total, n_branch = sm["n_pass"], sm["total"], sm["branches"]
    run_id = R["run_metadata"]["run_id"]

    o = []
    A = o.append
    A("# 附录 · 原始输出(证据)\n")
    A("> **版本 v%s · 本文件由 `crossval/scripts/gen_appendix.py` 自动生成,请勿手工编辑 · run_id `%s`**" % (APPENDIX_VERSION, _RUN_ID))
    A("> 起因:对上一版附录的审核发现 5 处数字与合集不一致、F/G 节重复、缺 criteria.yaml。")
    A("> **根因是手工拼装无强制同步**;改为脚本生成后,数字一律读自当前 `results/` 与 `schema/`。\n")
    A(f"> 脚本运行时间(UTC+8):{datetime.now(CST).strftime('%Y-%m-%d %H:%M:%S')}")
    A(f"> 本次 run_id:`{run_id}`\n")
    A("---\n")

    # ---------- 0 changelog ----------
    A("## 0. 数字变化 changelog(审计 §7 要求)\n")
    A("| 变化 | 原因 |")
    A("|---|---|")
    for k, v in CHANGELOG:
        A(f"| {k} | {v} |")
    A("")
    A("> **说明**:run_id 每次运行都会变化(它由 seed + 时间戳 + 脚本哈希导出),")
    A("> 这是**预期行为**,不是不一致。核对时应比对**同一份 report.json**,而非跨 run 的 run_id。\n")

    # ---------- A ----------
    A("## A. `results/report.json`\n")
    A("### A.1 summary\n")
    A("```json")
    A(json.dumps(sm, indent=2, ensure_ascii=False))
    A("```\n")
    A("### A.2 run_metadata\n")
    rm = R["run_metadata"]
    A("```json")
    A(json.dumps({k: v for k, v in rm.items() if k != "env_snapshot"},
                 indent=2, ensure_ascii=False))
    A("```\n")
    # env_snapshot 单独完整输出(上版在 "p" 处被截断 —— 因 json.dumps 后切片 3000 字符)
    A("### A.3 env_snapshot(完整,不截断)\n")
    es = rm.get("env_snapshot", {})
    A(f"共 **{len(es)}** 个包。\n")
    A("| 包 | 版本 |")
    A("|---|---|")
    for k in sorted(es):
        A(f"| `{k}` | {es[k]} |")
    A("")

    # ---------- B ----------
    c = Counter(r["branch"] for r in R["ledger"])
    A("## B. 判定项按分支分布\n")
    A(f"总计 **{n_total}** 项,通过 **{n_pass}** 项,唯一分支 **{n_branch}** 个。\n")
    A("| 分支 | 判定项数 | 说明 | 对应 criteria id |")
    A("|---|---|---|---|")
    DESC = {
        "1": ("多重检验家族", "T01"), "2": ("ΔAUC 增量", "T13a"),
        "3": ("校准(须用 CV 概率)", "T13b"), "4": ("DCA 曲线形状", "T13c"),
        "5": ("复现方向一致性", "T14"), "6": ("程序定义漂移", "B03A"),
        "7": ("目检 M11–M18", "V5DECL?见 M11–M18"), "8": ("硬阻断三类", "硬阻断9条"),
        "E": ("种子稳健性", "G-E"), "P3": ("合成值隔离守卫", "P3"),
        "T15": ("单细胞 QC 阈值", "T15"), "T16": ("推断单位/pseudobulk", "T16"),
        "T17": ("计算扰动", "T17"), "10": ("竞争风险/EPV/可行性", "T06/B01A/B02S"),
    }
    for b in sorted(c):
        d, cid = DESC.get(str(b), ("", ""))
        A(f"| 分支 {b} | {c[b]} | {d} | `{cid}` |")
    A(f"| **合计** | **{sum(c.values())}** | | |")
    A("")
    A("> 分支 id 为 `1..8 / E / P3 / T15 / T16 / T17 / 10`。早期报告称\"分支 9\"不精确,")
    A("> 实际 T15/T16/T17 是三个独立 id。已更正。\n")

    # ---------- C 全量 ----------
    A("## C. 完整判定台账(全量,非抽样)\n")
    A("| # | 分支 | criteria id | 判据 | 实测 | 期望 | 结果 |")
    A("|---|---|---|---|---|---|---|")
    for i, r in enumerate(R["ledger"], 1):
        obs = str(r.get("observed", ""))[:40].replace("|", "\\|")
        exp = str(r.get("expected", ""))[:24].replace("|", "\\|")
        cid = {str(k): v[1] for k, v in DESC.items()}.get(str(r["branch"]), "")
        A(f"| {i} | {r['branch']} | `{cid}` | {str(r.get('item', ''))[:36]} | "
          f"{obs} | {exp} | {'PASS' if r['passed'] else 'FAIL'} |")
    A("")

    # ---------- D ----------
    A("## D. 排版判定项(全量)\n")
    A(f"总计 **{len(L['checks'])}** 项。\n")
    A("| # | 编号 | 判据 | 实测 | 结果 |")
    A("|---|---|---|---|---|")
    for i, ck in enumerate(L["checks"], 1):
        A(f"| {i} | `{ck.get('check', '')}` | {str(ck.get('item', ''))[:40]} | "
          f"{str(ck.get('observed', ''))[:26]} | {'PASS' if ck.get('passed') else 'FAIL'} |")
    A("")

    # ---------- E ----------
    nnode = len(C["nodes"])
    nack = sum(1 for n in C["nodes"] if n.get("ack"))
    A("## E. Handoff 链摘要\n")
    A(f"节点 **{nnode}**,已确认 **{nack}**,在途 **{nnode - nack}**。\n")
    A("| # | handoff_id | 交付→接收 | 输出状态 | ack |")
    A("|---|---|---|---|---|")
    for i, n in enumerate(C["nodes"], 1):
        ack = "已确认" if n.get("ack") else "**在途**"
        A(f"| {i} | {n['handoff_id']} | {n['from']}→{n['to']} | "
          f"{str(n.get('state_out', ''))[:28]} | {ack} |")
    A("")
    A("> 链原始 JSON:`handoff/handoff_chain.json`(48 项字段,此处为摘要)。\n")

    # ---------- F criteria.yaml(审计指出缺失) ----------
    A("## F. `schema/criteria.yaml` 全文(审计 §9 要求补齐)\n")
    # ⚠ 审计 v2.6 P0-A:原用正则 r"^  - id:"(要求前导两空格),
    #   而 safe_dump 输出的列表项是 "- id:"(无前导空格)→ 数出 0,
    #   与同一脚本上方 safe_load 算出的 21 自相矛盾。
    #   讽刺的是上面第 113 行已正确算出 len(_d["criteria"])=21,
    #   这里却另写一套正则 —— 同一脚本内两套算法,与 v1.6
    #   "同一脚本两套时间"属同一族错误。改为复用 safe_load。
    try:
        import yaml as _y2
        _ny = len(_y2.safe_load(Y)["criteria"])
    except Exception:
        _ny = 0
    assert _ny >= 19, f"[gen_appendix] 判据条数异常 {_ny} —— 不应少于 19"
    A(f"判据条数:**{_ny}**\n")
    A("````yaml")
    A(Y.rstrip())
    A("````\n")

    # ---------- G 守卫 stdout(单次,不重复) ----------
    A("## G. 三个守卫的原始 stdout(单次捕获)\n")
    guards = [
        ("G.1 一致性守卫 `consistency_guard.py`",
         [sys.executable, "scripts/consistency_guard.py", "--doc",
          os.path.join(WS, "框架_独立审核包_v1.md")], ROOT),
        ("G.2 审核报告守卫 `report_guard.py`",
         [sys.executable, "scripts/report_guard.py", "--doc", REPORT_DOC], ROOT),
        ("G.3 Handoff 链守卫 `handoff_guard.py`",
         [sys.executable, "scripts/handoff_guard.py"], os.path.join(WS, "handoff")),
    ]
    guard_results = {}
    for title, cmd, cwd in guards:
        A(f"### {title}\n")
        A("```")
        # ★ v2.25：子守卫在中文 Windows(cp936) 上输出 UTF-8（被重定向时），
        #   父进程必须同口径解码，否则 [PASS]/[FAIL] 行里的中文会乱码。
        _env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, encoding="utf-8",
                           errors="replace", env=_env)
        out = (r.stdout + r.stderr).rstrip()
        A(out)
        A("```\n")
        # 从 stdout 解析 N/N —— MANIFEST 必须派生自原始输出,禁止手工填
        # 只认守卫自己的汇总行(形如 "一致性守卫: 14/14 通过"),
        # 否则会误抓 stdout 中出现的 "主验证 85/85 通过"
        mm = re.search(r"守卫[:：]\s*(\d+)\s*/\s*(\d+)\s*通过", out)
        if not mm:
            mm = re.search(r"链守卫[:：]\s*(\d+)\s*/\s*(\d+)", out)
        _key = title.split()[0]
        _val = (f"{mm.group(1)}/{mm.group(2)}" if mm
                else f"未解析(rc={r.returncode})")
        _nfail = len(re.findall(r"\[FAIL\]", out))
        if mm and mm.group(1) == mm.group(2) and _nfail > 0:
            print(f"  ✗ 硬自检:{_key} stdout 含 {_nfail} 个 [FAIL],却解析为 {_val}(全通过) —— 中断")
            raise SystemExit(2)
        guard_results[_key] = _val
    # 落盘守卫结果,供 MANIFEST 读取(杜绝"汇总覆盖原始")
    json.dump(guard_results,
              open(os.path.join(ROOT, "results", "guard_results.json"), "w",
                   encoding="utf-8"), indent=2, ensure_ascii=False)
    # 派生中间产物 + 守卫源码(审计要求:声称存在的东西必须可见)
    A("### G.4 守卫结果派生说明\n")
    _gp = os.path.join(ROOT, "results", "guard_results.json")
    if os.path.exists(_gp):
        A("**中间产物 `results/guard_results.json`(由本脚本从上述 stdout 解析并落盘):**\n")
        A("```json")
        A(open(_gp, encoding="utf-8").read().rstrip())
        A("```\n")
    A("**守卫源码(可被审核方独立审阅,确认派生逻辑无硬编码):**\n")
    for _g in ("consistency_guard.py", "report_guard.py"):
        A(f"<details><summary>{_g}</summary>\n")
        A("```python")
        try:
            A(open(os.path.join(ROOT, "scripts", _g), encoding="utf-8").read().rstrip())
        except Exception as e:
            A(f"# 读取失败: {e}")
        A("```\n")
        A("</details>\n")

    A("> `MANIFEST.json` 的 `guards` 字段**由本节的 stdout 解析得出**,不手工填写。")
    A("> 起因:v1.5 的附录 stdout 显示 12/14、7/9,而 MANIFEST 与正文写 14/14、9/9 ——")
    A("> 汇总覆盖了原始输出,正是框架第 9 条要防的错。\n")
    A("| 守卫 | 结果(解析自 stdout) |")
    A("|---|---|")
    for k, v in guard_results.items():
        A(f"| {k} | **{v}** |")
    A("")

    # ---- G.5 变异测试原始输出(审计 v2.11 P1-C) ----
    # 起因:MANIFEST.verification.mutation 写 "29/29",但附录里
    #   既无 mutation_results.json 内容,也无 guard_selftest 的 stdout ——
    #   该数字**无可核验来源**,正是第 11 条陷阱形态③(汇总无 stdout 支撑)。
    #   与 §G.1–G.3 展示三道守卫 stdout 同构处理。
    A("### G.5 变异测试原始输出(守卫有效性自证)\n")
    _mp = os.path.join(ROOT, "results", "mutation_results.json")
    if os.path.exists(_mp):
        try:
            _mr = json.load(open(_mp, encoding="utf-8"))
            A("**中间产物 `results/mutation_results.json`(由 `guard_selftest.py` 落盘):**\n")
            A("| 项 | 值 |")
            A("|---|---|")
            for _k in ("n_pass", "total", "coverage"):
                if _k in _mr:
                    A(f"| {_k} | **{_mr[_k]}** |")
            if "families" in _mr:
                A(f"| 守卫家族总数 | **{len(_mr['families'])}** |")
            if "covered" in _mr:
                A(f"| 已覆盖家族 | **{len(_mr['covered'])}** |")
                _unc = sorted(set(_mr["families"]) - set(_mr["covered"]))
                A(f"| 未覆盖 | {_unc or '无'} |")
            A("")
            if "cases" in _mr:
                A("<details><summary>逐用例结果(共 %d 项)</summary>\n" % len(_mr["cases"]))
                A("| 用例 | 期望触发 | 是否抓到 |")
                A("|---|---|---|")
                for _c in _mr["cases"]:
                    # ★ v2.12 二次修正:guard_selftest 的 add(cid, item, ...)
                    #   中 cid=显示名(如"G-1 内嵌脚本")、item=描述句
                    #   (如"注入违规后应触发 G-1.1")。首版按字面取 →
                    #   用例名与期望 ID 两列**完全颠倒**。改为显式提取。
                    _nm = _c.get("name", "")
                    _eid = _c.get("expect_id", "")
                    _m_eid = re.search(r"触发\s+([A-Z]-\S+)", _nm)
                    if _m_eid:
                        _real_eid, _real_nm = _m_eid.group(1), _eid
                    else:
                        _real_eid, _real_nm = _eid, _nm
                    A("| %s | `%s` | %s |" % (_real_nm, _real_eid,
                                              "抓到" if _c.get("caught")
                                              else "**未抓到(空规)**"))
                A("\n</details>\n")
        except Exception as _e:
            A(f"> ⚠ mutation_results.json 解析失败: {_e}\n")
    else:
        A("> ⚠ 未找到 `results/mutation_results.json` —— 变异测试结果无来源。\n")

    # 守卫家族 → 用例 映射(审计 P2:澄清"覆盖率 100%"的粒度)
    A("**覆盖率粒度澄清** —— 「100%」指**守卫家族级**:每个家族至少有 1 个\n"
      "变异用例证明其能抓到违规;**不代表**该家族每个子检查都有独立用例。\n")
    # 家族→用例映射:从 guard_selftest 源码解析 CASES,避免手工维护两份
    _sp = os.path.join(ROOT, "scripts", "guard_selftest.py")
    _fam_map = {}
    try:
        _ss = open(_sp, encoding="utf-8").read()
        for _m in re.finditer(r'\(\s*"([^"]+)"\s*,\s*(?:FRAME|REPORT|APPENDIX)[^)]*?\)\s*,',
                              _ss):
            _nm = _m.group(1)
            _fam = _nm.split()[0]
            _fam_map[_fam] = _fam_map.get(_fam, 0) + 1
    except Exception:
        pass
    if _fam_map:
        A("| 守卫家族 | 变异用例数 |")
        A("|---|---|")
        for _f in sorted(_fam_map):
            A(f"| {_f} | {_fam_map[_f]} |")
        A("")
    A("> 逐家族详情见 `scripts/guard_selftest.py` 的 `CASES` 与 `MUST_COVER`;\n"
      "> **新增守卫必须登记进 `MUST_COVER`**,缺用例则 `G-COV` FAIL。\n")

    # ---- P0① 术语表(第四轮审计 §7.① 根因修复) ----
    A("## H. 术语定义表(防同名/近名误读)\n")
    A("> 起因:审计方曾把「组0高估量 0.285」误读为「CIF 组间差」——")
    A("> 二者数值巧合接近(0.285 vs 0.284),且指向同一组原始数据的不同导出量。\n")
    A("| 符号 | 定义 | 本次实测 | 易混淆对象 |")
    A("|---|---|---|---|")
    for sym, dfn, val, conf in TERMS:
        A(f"| `{sym}` | {dfn} | {val} | {conf} |")
    A("")
    A("> **规则**:报告中引用任一数字,必须同时写出其符号(如 `diff_correct=0.284`),")
    A("> 禁止只写裸露数值。术语表由本脚本生成,与 `report.json` 字段一一对应。\n")

    # newline="\n"：避免 Windows 文本模式产生 CRLF，使附录在 Win/Linux 字节一致
    # （附录会被 merge_delivery 逐字收录，换行风格不一致会导致"未完整收录"误报）。
    open(a.out, "w", encoding="utf-8", newline="\n").write("\n".join(o))
    print(f"已生成 {a.out}")
    # ⚠ v2.4 修:原用正则 ^  - id: 计数,依赖 yaml 缩进格式;
    #   safe_dump 输出为 "- id:"(无前导空格),正则数出 0 —— 显示错误。
    #   同类问题此前已犯过一次(v1.4 用正则把 invariants 里的 4 条也数进 "19 条")。
    #   正解:用 safe_load 直接取 criteria 列表长度,不依赖文本格式。
    try:
        import yaml as _y2
        _ny2 = len(_y2.safe_load(Y).get("criteria", []))
    except Exception:
        _ny2 = len(re.findall(r"^\s*- id: (\S+)", Y, re.M))
    print("  主验证 {} / {} · 分支 {} · 排版 {} · 链 {} 节点 · YAML {} 条".format(n_pass, n_total, n_branch, len(L["checks"]), nnode, _ny2))


if __name__ == "__main__":
    main()
