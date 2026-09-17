#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
guard_selftest.py —— 守卫有效性变异测试(mutation testing)

起因(审计第八轮):
    "一个从未 FAIL 过的守卫,和没有守卫,在证明力上是等价的。"
    "每个新增守卫首次运行必须能构造出 FAIL;不能构造 → 规则未生效。"

为什么不用"记录首次运行是否曾 FAIL":
    那依赖历史,换个环境重跑历史就没了 —— 不可复现,本身就是纸面证据。
    变异测试是可复现的:**每次都现场注入违规,当场验证守卫抓得到**。

原理:
    对每个守卫,构造一个含已知违规的副本 → 运行守卫 → 期望 FAIL。
    抓不到 = 空规(规则没跑到过应触发的输入)。

运行: python scripts/guard_selftest.py
退出码: 0 = 所有守卫均能抓到注入的违规
        1 = 存在空规（且子进程都正常跑起来了）
        2 = **环境错误** —— 子守卫没跑起来，本次结果无效（v2.26 新增）

★ v2.26 平台修正：
    子守卫原先以硬编码 `python3` 启动。Windows 的 venv **不生成 python3.exe**
    （只有 python.exe / pythonw.exe），故在 Win11 + venv（即本框架自己推荐的
    执行方式）下，`python3` 会落到 PATH 上另一个**没装依赖**的解释器
    → 子进程 ImportError → 无任何判定行 → 18 个守卫家族被误报为「空规」。
    现改用 sys.executable，保证父子同解释器；并把「环境错误」单列为退出码 2。
"""
import os, re, sys, json, shutil, tempfile, subprocess
# ── 控制台编码加固（v2.25）──────────────────────────────────────────────────
# 起因：中文 Windows 默认控制台 cp936(GBK) 无法编码 ⚠ → UnicodeEncodeError。
try:
    if sys.stdout.isatty():
        sys.stdout.reconfigure(errors="replace")
    else:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(errors="replace")
except (AttributeError, ValueError):
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
WS = os.path.dirname(ROOT)

# ★ v2.26:子守卫必须用**当前解释器**启动，不得硬编码 python3。
#   实证：Windows venv 只生成 python.exe / pythonw.exe，**没有 python3.exe**
#   → `python3 scripts/xxx_guard.py` 会落到 PATH 上另一个没装依赖的解释器
#   → 子进程 ImportError → 无判定行 → 被误判为「空规」。
#   用 sys.executable 保证「跑变异测试的解释器」== 「跑子守卫的解释器」，
#   依赖必然可用，且 Win/Linux/macOS 一致。
PYEXE = '"%s"' % sys.executable

# 判定行形态：子守卫每项输出的 [PASS] / [FAIL]
_RE_JUDGE_LINE = re.compile(r"\[(PASS|FAIL)\]")

# 子进程异常标记（用于把"环境错误"与"空规"分开，见 run_guard）
ENV_ERR_MARK = "[guard_selftest·环境错误]"

# 本次运行中「子进程未产出判定行」的用例名
_ENV_BROKEN = set()

ROWS = []


def add(cid, item, ok, detail=""):
    # ★ v2.12:同步记录明细供 mutation_results.json 落盘(附录 §G.5 展示)
    try:
        main._ROWS.append({"name": item, "eid": cid, "caught": bool(ok)})
    except Exception:
        pass
    ROWS.append(bool(ok))
    print(f"    [{'PASS' if ok else 'FAIL'}] {cid} {item:<40s} {detail}")
    return ok


def _line_is_fail(out, eid):
    """该检查 ID 所在的行是否本身为 FAIL(而非输出中别处有 FAIL)"""
    for ln in out.split("\n"):
        if eid in ln:
            if "[FAIL]" in ln:
                return True
    return False


def _child_env():
    """★ v2.25：子守卫改为「被重定向即输出 UTF-8」，父进程须同口径解码，
    否则中文判定行在中文 Windows(cp936) 上会乱码或抛 UnicodeDecodeError。"""
    e = dict(os.environ)
    e["PYTHONUTF8"] = "1"
    e["PYTHONIOENCODING"] = "utf-8"
    return e


def run_guard(cmd, cwd=None):
    """返回 (exit_code, stdout)

    ★ v2.26：必须区分「子守卫抓到违规」与「子守卫根本没跑起来」。
      实证（成交付方复现）：Windows venv 里**不存在 python3.exe**（只有 python.exe），
      而本函数原先硬编码 `python3 ...` → 落到 PATH 上另一个**没装依赖**的解释器
      → ImportError → 子进程输出里一个 [PASS]/[FAIL] 都没有
      → _line_is_fail() 恒 False → 18 个守卫家族被报成「空规」。
      这是**第 11 条陷阱的镜像形态**：守卫没跑，却被判为"规则没生效"，
      会把审核方引去查根本不存在的空规。故此处显式标注环境错误。

      修法二合一：① 解释器改用 sys.executable（与父进程同一环境，平台无关）；
      ② 子进程输出中若无任何判定行，追加显式标记，由调用方按「环境错误」处理。
    """
    p = subprocess.run(cmd, shell=True, cwd=cwd or ROOT,
                       capture_output=True, encoding="utf-8",
                       errors="replace", env=_child_env())
    out = p.stdout + p.stderr
    if not _RE_JUDGE_LINE.search(out):
        out += ("\n" + ENV_ERR_MARK + " 子进程未产出任何 [PASS]/[FAIL] 行 —— "
                "这不是「空规」，而是子守卫根本没跑起来"
                "（解释器 / 依赖 / 路径错误）。\n")
    return p.returncode, out


def mutated_fs(figdir, bad_name):
    """★ v2.10:G-7 检查的是**图目录里的真实文件**,文档变异对它无效。

    因此在图目录现场创建一个违规命名的临时文件。
    风险:若中途崩溃会留下垃圾文件 → G-7 永久 FAIL。
    防护:调用方必须在 finally 中清理,且结束后做**残留检测**。
    """
    p = os.path.join(figdir, bad_name)
    if os.path.exists(p):
        return None
    open(p, "wb").write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    return p


def mutated(doc_path, old, new, tmpdir, count=1):
    """复制文档并注入违规,返回副本路径;注入失败返回 None(锚点不存在)。

    count=-1 表示**全部替换**。
    ★ v2.10:同一数字常在文档多处出现(如 0.28 在 §6.2 表与 §7 陷阱各一处)。
      只替换第一处 → 守卫仍 PASS → 用例"通过"但守卫未被验证(伪绿)。
      故对"让某数字彻底消失"型用例必须 count=-1。
    """
    s = open(doc_path, encoding="utf-8").read()
    if old == "":          # v2.11:追加模式(G-10.1 需在末尾加行)
        s = s + new
        dst = os.path.join(tmpdir, os.path.basename(doc_path))
        open(dst, "w", encoding="utf-8").write(s)
        return dst
    if old not in s:
        return None
    if s.count(old) > 1 and count == 1:
        print("      ⚠ 锚点出现 %d 处(仅替换第一处,守卫可能仍 PASS): %s…"
              % (s.count(old), old[:40]))
    dst = os.path.join(tmpdir, os.path.basename(doc_path))
    open(dst, "w", encoding="utf-8").write(s.replace(old, new, count))
    return dst


def main():
    main._ROWS = []   # ★ v2.12:变异用例明细(供落盘)
    print("=" * 78)
    print("  守卫有效性变异测试 —— 注入已知违规,验证守卫抓得到")
    print("=" * 78)

    # ★ v2.25 P0：原为硬编码未版本化旧名（**交付 zip 内不存在**）→
    #   第一个用到 FRAME 的变异用例直接 FileNotFoundError 崩溃，实测 0/66。
    #   改为：未版本化源文档（开发机）→ 最新版本化副本（交付布局）。
    #   找不到时 **SystemExit**，不"跳过"—— 跳过即空规（第 11 条陷阱形态①）。
    def _pick(plain, prefix):
        if os.path.isfile(plain):
            return plain
        import glob as _g, re as _re
        hits = [p for p in _g.glob(os.path.join(WS, prefix + "_v*.md"))
                if _re.search(r"_v[\d.]+_\d{8}\.md$", os.path.basename(p))]
        if not hits:
            raise SystemExit(
                "[guard_selftest] 找不到主交付文档「%s」：既无未版本化源文档，"
                "也无版本化副本 —— 变异测试不能在缺失对象上「跳过」。" % prefix)
        def _k(p):
            m = _re.search(r"_v([\d.]+)_(\d{8})\.md$", os.path.basename(p))
            return tuple(int(x) for x in m.group(1).split(".")) + (int(m.group(2)),)
        return max(hits, key=_k)

    FRAME = _pick(os.path.join(WS, "框架_独立审核包_v1.md"), "框架_独立审核包")

    MANU = os.path.join(ROOT, "demo", "manuscript_demo.md")
    P1 = "损伤处理 3 小时后叶片小 RNA 表达谱发生显著改变。"
    REPORT = _pick(os.path.join(WS, "四角度审核报告_合集.md"), "四角度审核报告_合集")

    # ⚠ v2.4 修:锚点原为硬编码字符串(如 "主验证:85/85 通过")。
    #   文档数字一同步(85→101),锚点立即失效 → 报"无法测试" → 假空规。
    #   这使**变异测试自身**成为空规:它证明不了任何东西,却报 FAIL 引人误判。
    #   正解:锚点从 report.json 动态派生,与文档同步无关。
    _rp_j = os.path.join(ROOT, "results", "report.json")
    _R = json.load(open(_rp_j, encoding="utf-8"))
    _NP = _R["summary"]["n_pass"]
    _NT = _R["summary"]["total"]
    _NB = _R["summary"]["branches"]
    print(f"  (锚点动态取自 report.json: {_NP}/{_NT} · {_NB} 分支)")
    # v2.7 新增锚点:G-11 / G-12 的动态来源(同样禁止硬编码,
    # 否则文档一同步锚点就失效 —— 见上方 v2.4 教训)
    APPENDIX = _pick(os.path.join(WS, "附录_原始输出.md"), "附录_原始输出")
    # G-12 检查的是**版本化副本**(G-12 内部用 sorted(_cands)[-1]),
    # 因此变异必须注入到副本上 —— 注入源文档会因锚点(v2.5)不匹配而
    # 报"无法测试",那不是空规,是测错了对象。
    import glob as _g_m
    _cv = list(_g_m.glob(os.path.join(WS, "框架_独立审核包_v*_2*.md")))
    # ⚠ v2.10:同上,字符串序 "v2.10" < "v2.9" → 选中旧副本 → 锚点不匹配。
    def _vk(f):
        m = re.search(r"_v([\d.]+)_\d{8}\.md$", f)
        return tuple(int(x) for x in m.group(1).split(".")) if m else (0,)
    FRAME_V = sorted(_cv, key=_vk)[-1] if _cv else FRAME
    import re as _re_m, yaml as _y_m
    _NY = len(_y_m.safe_load(open(os.path.join(ROOT, "schema", "criteria.yaml"),
                                  encoding="utf-8"))["criteria"])
    # ⚠ v2.8:原读 MANIFEST.json —— 它在 build 第 11 步才更新,变异测试在
    #   第 8 步跑,拿到的是上一版(v2.7)→ 锚点"版本 v2.7"在新 banner 中
    #   找不到 → 报"无法测试"。又一次**滞后派生物当基准**。
    #   权威源:results/build_version.json(build 遍历前写入)。
    _bvp = os.path.join(ROOT, "results", "build_version.json")
    _VER = json.load(open(_bvp, encoding="utf-8"))["version"] \
        if os.path.exists(_bvp) else \
        json.load(open(os.path.join(WS, "MANIFEST.json"),
                       encoding="utf-8"))["version"]
    # ★★ v2.25：run_id 锚点必须取自 build_version.json，**不能**取 report.json。
    #   起因（交付布局实测）：用户在云端按 T4 先跑一次 verify_all，report.json 的
    #   run_id 随之改变，而文档 banner 保持构建时的值 → 变异用例的锚点
    #   「run_id `<值>`」在文档里找不到 → 报"锚点缺失(无法测试)"→ 2 个用例 FAIL
    #   （实测 64/66，而开发布局是 66/66）。与 G-12 是同一族"拿易变量当基准"。
    #   build_version.json 只在构建时写，重跑主验证不动它 —— 锚点因此稳定。
    _RID = json.load(open(_bvp, encoding="utf-8"))["run_id"] \
        if os.path.exists(_bvp) else _R["run_metadata"]["run_id"]
    print(f"  (G-11/G-12 锚点: 判据 {_NY} 条 · 版本 v{_VER} · run_id {_RID[:16]}…)")

    # ── ★ v2.8:新增守卫必须同时提交变异用例(采纳审计建议,做成代码强制) ──
    #   审计原话:"这是流程约定不是代码,需要你确认"。
    #   但若只写进文档 → 就是 v2.5 的翻版(把"gen_appendix 最后跑"写进文档
    #   照样违反)。故:MUST_COVER 里每个守卫家族必须有对应用例,缺 → FAIL。
    #   流程:新增守卫时把它的 ID 前缀加进 MUST_COVER;忘了加用例就构建失败。
    MUST_COVER = [
        "G-5.DEPR",   # v2.1 整行豁免致空规
        "G-5.pypdf",  # 跨文档锚点
        "G-2.2",      # 过期 N/N
        "R-1",        # 报告主验证数字
        "R-8",        # 守卫计数可回溯
        "G-8",        # 表格列数
        "G-11",       # v2.7 附录/正文/合集判据条数
        "G-12",       # v2.7 banner 版本号/run_id
        "G-11.3-cov", # ★ v2.9:防锚点失效(命中 0 处即报警)
        # ★ v2.10:覆盖率长期停在 36%(7/19 家族)。未被变异验证的守卫
        #   与"没有守卫"证明力等价(第 11 条)。下列为高频/曾出事的家族。
        "G-1",        # 内嵌脚本 == 实际脚本(v1.4 核心,从未经变异验证)
        "G-3",        # 关键数字可在 report.json 定位
        "R-6",        # 判据条数(v2.5 曾因正则失效成空规)
        "G-7",        # 图命名与阶段标签
            "WP-1", "WP-2", "WP-3", "WP-4", "WP-5a", "WP-5b", "WP-5c",
        "WP-5d", "WP-6", "WP-7c", "WP-8", "WP-9",
        # ★ v2.18 结论守卫 T26–T30:这五条是**函数级判据**(输入是数据与声明,
        #   不是文档文本),无法用文档字符串变异验证 —— 改用函数级用例:
        #   直接调用 check_* 传入违规输入,断言其判 fail。
        #   若不加进 MUST_COVER,就出现"新增判据无变异用例"的缺口,
        #   与 MUST_COVER 当初要防的"守卫写了但没验证"是同一类洞。
        "T26", "T27", "T28", "T29", "T30",
        # ★ v2.20 对称面判据 T33 稀有事件 / T34 不确定性 / T35 多组学偏倚
        #   / V4MODAL 跨模态强度。同样是**函数级判据**(输入为数据与声明),
        #   用函数级用例验证;不声明就逃过 MUST_COVER,故必须显式加入。
        "T33", "T34", "T35", "V4MODAL",
        # ★ v2.21 两批新判据:
        #   ① 休眠判据激活 T03/T09/T12/T18 —— 由 L2 判据消融发现
        #      "在 criteria.yaml 里有 predicate、有 on_fail,但从未被任何
        #      判定项触发"。激活后必须补变异用例,否则激活本身不可信。
        #   ② T36 多组件整合增量消融(审核 §3 P0)。
        "T03", "T09", "T12", "T18", "T36",
]

    # ---- 变异用例:(守卫, 违规注入点 old, 变异后 new, 期望触发的检查 ID) ----
    #
    # ⚠ v2.9 教训:用例注入的**形态**必须等于文档真实写法。
    #   v2.8 的 G-11.3/G-12 用例注入的是 banner 形态,而真实违规在
    #   §0.2 状态表形态("| 判据 YAML | **19** 条 |")—— 用例 PASS 而
    #   守卫实为空规。故下面两条用例**刻意使用状态表写法**。
    # 判据条数权威源(锚点动态派生用)
    try:
        import yaml as _y
        N_CRIT = len(_y.safe_load(
            open(os.path.join(ROOT, "schema", "criteria.yaml"),
                 encoding="utf-8"))["criteria"])
    except Exception as e:
        raise SystemExit("读 criteria.yaml 失败(不许兜底): %s" % e)

    CASES = [
        # ★ v2.10 覆盖率补充:G-1 / G-3 / R-6 / G-7 从未被变异验证过。
        #   它们各自都曾出过事(G-1 是 v1.4 核心;R-6 在 v2.5 因正则失效
        #   成空规),但"能抓到违规"从未被证明 —— 按第 11 条,等于没有。
        # ── ★ v2.15 写作流程层 WP-1~8 变异用例 ──
        #   每个用例注入一种真实会发生的写作违规,验证守卫**确实抓得到**。
        ("WP-1.1 标题升级词", MANU, "## 标题\n拟南芥叶片",
         "## 标题\n拟南芥叶片揭示", "WP-1.1"),
        ("WP-2.1 摘要首句非P1", MANU, "损伤处理 3 小时后",
         "本研究旨在探讨相关", "WP-2.1"),
        ("WP-3.4 缺gap", MANU,
         "然而,目前缺乏对 rns2 在损伤响应中作用的研究。该领域进展有限,但具体机制仍不清楚。",
         "已有研究对 rns2 在损伤响应中作用进行了探索。该领域进展有限。",
         "WP-3.4"),
        ("WP-4.3a 缺双侧", MANU, "双侧检验", "统计检验", "WP-4.3a"),
        ("WP-5a.1 显著缺台账", MANU, "显著富集 [L-012]", "显著富集", "WP-5a.1"),
        ("WP-5b.1 图号跳号", MANU, "如图 1 和图 2 所示", "如图 1 和图 3 所示",
         "WP-5b.1"),
        ("WP-5c 图注缺n", MANU, "n = 8,误差棒", "误差棒", "WP-5c.n"),
        ("WP-5d.1 图题无信息词", MANU, "## 图题\n差异 sRNA",
         "## 图题\n主要结果:差异 sRNA", "WP-5d.1"),
        ("WP-6.1 讨论首段非P1", MANU, "## 讨论\n损伤处理 3 小时后",
         "## 讨论\n本研究背景如下", "WP-6.1"),
        ("WP-7c.1a 用而未引", MANU, "相关通路存在。",
         "相关通路存在 [99]。", "WP-7c.1a"),
        ("WP-8.1 模板句式", MANU, "然而,目前缺乏", "近年来,目前缺乏", "WP-8.1"),
        # ── 原有用例 ──
        ("G-1 内嵌脚本", FRAME,
         "20260910\n\nos.makedirs(RES, exist_ok=True)",
         "20260911\n\nos.makedirs(RES, exist_ok=True)",
         "G-1.1"),
        # ⚠ v2.10:原锚点 4.2e-14 在文档中**出现 2 处**,而 mutated() 只替换
        #   第一处 → 另一处仍在 → 守卫仍 PASS → 误判"抓到"(实为未覆盖)。
        #   教训同 G-5.pypdf:**注入锚点必须唯一**,否则用例通过而守卫未验证。
        #   改用 0.28(全文仅 1 处)。
        # count=-1:0.28 在 §6.2 表与 §7 陷阱表各出现一处,须全部替换
        ("G-3 关键数字", FRAME,
         "0.28", "0.99", "G-3", -1),
        # ★ v2.15:锚点原硬编码 "21 条判据五元组"。判据由 21 增至 30 后
        #   锚点消失 → 报"注入锚点缺失" → 变异测试失败(与 v2.4 同族)。
        #   正解:条数从 criteria.yaml 动态派生。
        ("R-6 判据条数", REPORT,
         "%d 条判据五元组" % N_CRIT, "99 条判据五元组",
         "R-6"),
        # ★ v2.9 状态表形态用例(必须最先)
        #   v2.8 教训:用例注入 banner 形态 → 用例 PASS 而守卫实为空规,
        #   真实违规在 §0.2 状态表 "| 判据 YAML | **19** 条 |"。
        ("G-11.3", REPORT,
         "| 判据 YAML | **%d** 条 |" % N_CRIT,
         "| 判据 YAML | **19** 条 |",
         "G-11.3"),
        ("G-12.state", REPORT,
         "| run_id(取自 report.json) | `",
         "| run_id(取自 report.json) | `0000000000000000` |",
         "G-12.合集.rid-all"),
        # G-5.DEPR:注入未标注的旧阈值表述 —— v2.1 曾因整行豁免成为空规
        ("G-5.DEPR", FRAME,
         "**报告全区间胜出率 + 区间内最长连续负区间",
         "**报告全区间胜出率(≥10 点即判不确定)",
         "G-5.DEPR.≥10"),
        # G-5 跨文档:删掉正文里的 pypdf 盲区锚点
        # 锚点必须唯一:正文里"加密"出现 3 处,只替换第一处不足以让守卫 FAIL
        # 锚点须唯一:正文"加密"出现 3 处,只换第一处不足以让守卫 FAIL。
        # 改用 XFA 整行 —— 它是 G-5.pypdf.XFA 的唯一锚点
        ("G-5.pypdf", FRAME,
         "| 4 | **XFA 表单** | XFA 内图像/字体,pypdf 递归不覆盖 | 漏检 |",
         "| 4 | **其它表单** | 内图像/字体,pypdf 递归不覆盖 | 漏检 |",
         "G-5.pypdf.XFA"),
        # G-2.2 过期 N/N:注入一个不存在的声称
        # count=-1:该声称在文档出现 2 处,只换第一处会让守卫仍 PASS(伪绿)
        ("G-2.2 过期N/N", FRAME,
         f"主验证:{_NP}/{_NT} 通过", f"主验证:{_NT+1}/{_NT+1} 通过",
         "G-2.2", -1),
        # R-1 报告主验证数字:注入过期值
        # count=-1:该声称在合集出现 2 处(§0.2 与报告正文),须全换
        ("R-1 主验证", REPORT,
         f"**{_NP}/{_NT}** 通过,{_NB} 个分支", f"**{_NT-1}/{_NT-1}** 通过,{_NB} 个分支",
         "R-1", -1),
        # R-8 守卫计数:注入一个无法回溯的计数
        # count=-1:同上
        ("R-8 守卫计数", REPORT,
         "Handoff 链守卫 | **11/11**", "Handoff 链守卫 | **88/88**",
         "R-8", -1),
        # G-8 表格列数:删掉一个单元格分隔符
        ("G-8 表格列数", FRAME,
         "| **严重泄露** | 泄露 AUC=", "| **严重泄露**  泄露 AUC=",
         "G-8.2"),
         # ★ v2.7 新增 G-11 / G-12(理由:必须由变异测试固定,不能靠手工反证)
         ("G-11 附录条数", APPENDIX,
          f"判据条数:**{_NY}**", "判据条数:**0**",
          "G-11.1"),
         ("G-12 banner版本", FRAME_V,
          f"版本 v{_VER} ·", "版本 v0.1 ·",
          "G-12.框架.ver"),
         ("G-12 banner run_id", FRAME_V,
          f"run_id `{_RID}`", "run_id `deadbeefdeadbeef`",
          "G-12.框架.rid"),
         # ★ v2.11 覆盖率补漏:G-10 / G-4 / G-6 / R-2 / R-3 / R-4 / R-5 / R-7
        #   这 8 个家族此前从未经变异验证 —— 按第 11 条,等于"没有守卫"。
        #   G-10.1:追加一行(源副本变长)→ 与版本化副本不一致 → 应 FAIL
        ("G-10.1 版本化一致", FRAME, "", "\n# 变异注入行 v211\n",
         "G-10.1", 1, "SRC=self"),
        #   G-4.2:排版声称改错 → 与 layout_report.json 不符
        ("G-4 排版声称", FRAME, "排版层:70/70 通过", "排版层:99/99 通过",
         "G-4.2", -1),
        #   G-6:判据 2 缩进破坏(^ - **判据 2 锚点消失)
        ("G-6 变更清单", FRAME, "- **判据 2(补漏检", "  - **判据 2(补漏检",
         "G-6.缩进", 1),
        ("R-2 排版N/N", REPORT,
         "| 排版 `layout_check.py` | **70/70** 通过 |",
         "| 排版 `layout_check.py` | **88/88** 通过 |",
         "R-2", -1),
        #   R-3:把 run_id 换成非 hex → ids=0 → 不满足 >=1
        ("R-3 run_id", REPORT, f"`{_RID}`", "`zzzzzzzzzzzzzzzz`", "R-3", -1),
        #   R-4:插入台账中不存在的数字
        ("R-4 孤立数字", REPORT, "### 0.2 本轮实测状态",
         "### 0.2 本轮实测状态 9.8765", "R-4", 1),
        # ⚠ v2.11:合集中"14 节点"有两种写法(| Handoff 链 | 14 节点 与
        #   handoff/:14 节点),只替换前者 → 后者仍在 → R-5 仍 PASS(伪绿)。
        ("R-5 handoff节点", REPORT, "14 节点", "99 节点", "R-5", -1),
        #   R-7:框架内嵌脚本改动 → 委托 consistency_guard 的 G-1 失败
        ("R-7 附录脚本", FRAME,
         "20260910\n\nos.makedirs(RES, exist_ok=True)",
         "20260911\n\nos.makedirs(RES, exist_ok=True)", "R-7", 1),
        # ★ v2.7 新增 G-11 / G-12。理由:这两个守卫上一轮是我**手工反证**的,
         #   手工反证不可复现 —— 换台机器重跑就没了。按第 11 条陷阱,
         #   必须由变异测试固定下来,否则它们随时可能再变成空规。
    ]

    tmp = tempfile.mkdtemp(prefix="mut_")
    try:
        for _c in CASES:
            name, doc, old, new, expect_id = _c[:5]
            _cnt = _c[5] if len(_c) > 5 else 1
            _ex = _c[6] if len(_c) > 6 else ""
            d = mutated(doc, old, new, tmp, count=_cnt)
            if d is None:
                add(name, f"注入锚点缺失(无法测试)", False,
                    f"锚点: {old[:34]}…")
                continue
            # ⚠ v2.9:原按文档类型分发(合集→report_guard)。但 consistency_guard
            #   现在也检查合集(G-11.3 / G-12.合集.*)→ 这两条用例被送进
            #   report_guard,里面没有 G-11.3 → 恒'未抓到' → 误判空规。
            #   改:按期望触发的**检查 ID 前缀**分发(R- → report,G- → consistency)。
            _cli = f'--doc "{d}"'
            if _ex == "SRC=self":
                _cli += f' --src "{d}"'
            if expect_id.startswith("R-"):
                rc, out = run_guard(
                    f'{PYEXE} scripts/report_guard.py {_cli}')
            elif expect_id.startswith("WP-"):
                rc, out = run_guard(
                    f'{PYEXE} scripts/writing_guard.py {_cli} --p1 "{P1}"')
            else:
                rc, out = run_guard(
                    f'{PYEXE} scripts/consistency_guard.py {_cli}')
            # ⚠ v2.11 修**判定伪绿**:原为 `expect_id in out and "FAIL" in out`
            #   —— 只要输出里同时出现该 ID 和 "FAIL" 字样即算抓到,
            #   但 FAIL 可能属于**别的检查**。例:G-4.2 用例改 70/70→99/99
            #   会同时触发 G-2.2;若 G-4.2 自身 PASS,原判定仍报"抓到"。
            #   正解:定位 expect_id 所在行,判断该行本身是否 FAIL。
            hit = _line_is_fail(out, expect_id)
            # ★ v2.26：区分「空规」与「子进程没跑起来」。
            #   若不区分，解释器/依赖错误会被报成"18 个守卫是空规"——
            #   这是第 11 条陷阱的镜像：把**环境故障**诬告成**规则失效**。
            _broken = ENV_ERR_MARK in out
            if _broken and not hit:
                _ENV_BROKEN.add(name)
            add(name, f"注入违规后应触发 {expect_id}", hit,
                f"rc={rc} " + ("抓到" if hit else
                               ("子进程异常(非空规)" if _broken
                                else "未抓到(空规!)")))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # ── ★ v2.15 WP-9 三格式导出变异(json 构造,非文档变异) ──
    #   三版本的语义不同(纯文/纯图/合一),本用例验证**它们矛盾时会被抓到**。
    _wp9_good = {
        "a": "正文内容 [图1位置] [图2位置]\n\n参考文献\n[1] x",
        "b": "图 1:aaa\n图 2:bbb\n\n参考文献\n[1] x",
        "p": "正文 如图1\n\n图 1:aaa\n\n如图2\n\n图 2:bbb\n\n参考文献\n[1] x",
        "dpi": 300,
    }
    _wp9_bad = dict(_wp9_good)
    _wp9_bad["a"] = (_wp9_good["a"] + "\n[图6位置]")   # A 多一个占位符
    for _tag, _d, _exp in (("合规", _wp9_good, False), ("占位符不一致", _wp9_bad, True)):
        # ⚠ 本段位于 try/finally **之后**,tmp 已被 rmtree —— 用独立目录
        os.makedirs(tmp, exist_ok=True)
        _f = os.path.join(tmp, "wp9_%s.json" % ("good" if not _exp else "bad"))
        json.dump(_d, open(_f, "w", encoding="utf-8"), ensure_ascii=False)
        _rc, _out = run_guard(f'{PYEXE} scripts/export_guard.py --src "{_f}"')
        _fail = "FAIL" in _out
        add("WP-9 三格式(%s)" % _tag,
            "应报 FAIL" if _exp else "应全 PASS",
            (_fail == _exp), "rc=%d" % _rc)

    # ── ★ v2.10:文件系统变异(G-7 系列) ──
    #   文档变异测不到 G-7,必须现场造一个违规命名的图文件。
    _figdir = os.path.join(ROOT, "figures", "demo")
    _fs_name = "99_badstep_mutation_probe.pdf"
    _fs_path = mutated_fs(_figdir, _fs_name) if os.path.isdir(_figdir) else None
    _fs_ok = False
    if _fs_path:
        try:
            rc, out = run_guard(
                f'{PYEXE} scripts/consistency_guard.py --doc "{FRAME}"')
            hit = "G-7.2" in out and "FAIL" in out
            add("G-7 图命名(fs变异)", "注入违规图名后应触发 G-7.2",
                hit, f"rc={rc} {'抓到' if hit else '未抓到(空规!)'}")
            _fs_ok = hit
        finally:
            try:
                os.remove(_fs_path)
            except OSError:
                pass
        # 残留检测:清理失败会让 G-7 永久 FAIL,必须显式报警
        add("G-7 残留检测", "变异临时图文件已清理",
            not os.path.exists(_fs_path),
            "残留!" if os.path.exists(_fs_path) else "已清理")
    else:
        add("G-7 图命名(fs变异)", "图目录存在", False, "True", False)

    # ── ★ v2.11:源码级 / 文件系统级变异(G-13 / G-14) ──
    #   这两类守卫检查的不是"文档内容"而是"脚本源码 / 目录内容",
    #   文档变异对它们完全无效 —— 必须现场造违规再还原。
    #   G-14:在 crossval/ 下放一个主交付文档副本 → 应触发 G-14.1
    covered = set()   # v2.11:供源码/文件系统级变异用例登记覆盖
    _stale = os.path.join(ROOT, "框架_独立审核包_v1.md")
    _made = False
    if not os.path.exists(_stale):
        open(_stale, "w", encoding="utf-8").write("# 变异:过期副本\n")
        _made = True
    try:
        rc, out = run_guard(
            f'{PYEXE} scripts/consistency_guard.py --doc "{FRAME}"')
        _h14 = _line_is_fail(out, "G-14.1")
        add("G-14 过期副本", "放置过期副本后应触发 G-14.1",
            _h14, f"rc={rc} {'抓到' if _h14 else '未抓到(空规!)'}")
        if _h14:
            covered.add("G-14")
    finally:
        if _made and os.path.exists(_stale):
            try:
                os.remove(_stale)
            except OSError:
                pass
    add("G-14 残留检测", "变异临时副本已清理",
        not os.path.exists(_stale),
        "残留!" if os.path.exists(_stale) else "已清理")

    #   G-13:在守卫源码末尾追加一行无 a.doc 回退的硬编码 → 应触发 G-13.*
    _src = os.path.join(ROOT, "scripts", "consistency_guard.py")
    _bak = _src + ".bak_mut"
    _orig = open(_src, encoding="utf-8").read()
    shutil.copy(_src, _bak)
    try:
        with open(_src, "a", encoding="utf-8") as _f:
            _f.write('\n_x13_probe = os.path.join(WS, "框架_独立审核包_v1.md")\n')
        rc, out = run_guard(
            f'{PYEXE} scripts/consistency_guard.py --doc "{FRAME}"')
        _h13 = _line_is_fail(out, "G-13.")
        add("G-13 硬编码主文档", "源码注入硬编码后应触发 G-13.*",
            _h13, f"rc={rc} {'抓到' if _h13 else '未抓到(空规!)'}")
        if _h13:
            covered.add("G-13")
    finally:
        shutil.move(_bak, _src)
    add("G-13 源码恢复", "守卫源码已还原",
        open(_src, encoding="utf-8").read() == _orig,
        "未还原!" if open(_src, encoding="utf-8").read() != _orig else "已还原")

    # ── 覆盖率:枚举守卫源码里所有 add() 的检查 ID,与已覆盖用例比对 ──
    #   目的:让"哪些守卫从没被验证过"可见,而不是藏在 59 项检查里。
    covered = covered | {c[4].split(".")[0] for c in CASES}
    # WP-9 用独立 json 变异段(不在 CASES 内),需显式计入覆盖
    covered = covered | {"WP-9"}
    # ⚠ v2.10:不得无条件把 G-7 塞进 covered —— 那会让覆盖率虚高,
    #   与"守卫一直通过=空规"是同一种自欺。只有 fs 用例**真的抓到**才算。
    if _fs_ok:
        covered.add("G-7")
    allfam = set()
    SCRIPTS = os.path.join(ROOT, "scripts")
    for _fn in ("consistency_guard.py", "report_guard.py"):
        _p = os.path.join(SCRIPTS, _fn)
        try:
            _src = open(_p, encoding="utf-8").read()
        except OSError:
            continue
        for _m in re.finditer(r'add\(\s*["\']([A-Za-z\-]+\d*)', _src):
            allfam.add(_m.group(1).split(".")[0])
    untested = sorted(allfam - covered)
    print(f"\n  守卫家族总数 {len(allfam)} · 已覆盖 {len(allfam & covered)} "
          f"· 覆盖率 {len(allfam & covered) * 100 // max(1, len(allfam))}%")
    if untested:
        print("  ⚠ 未覆盖(从未经变异验证): " + ", ".join(untested[:14]))
        if len(untested) > 14:
            print(f"    …等 {len(untested)} 个")

    # ── 函数级用例(T26–T30 结论守卫)─────────────────────────────────
    #    文档变异只对"扫文本的守卫"有效;T26–T30 的输入是数据与声明字典,
    #    故直接构造**违规输入**,断言 check_* 判 fail(即"抓得到")。
    #    每条都对应 branch17 中的一个夹具,此处的意义是让 MUST_COVER
    #    对函数级判据同样生效 —— 声明了就必须证明能抓到。
    try:
        import numpy as _np
        import conclusion_guard as _CG
        import data_ethics as _DE

        def _noise_embed():
            _rng = _np.random.default_rng(1)
            _X = _rng.normal(0, 1.0, size=(200, 40))
            _Y, _ = _CG._pca(_X, 2)
            return _CG.check_T26(_X, _Y, n_embed=2, n_null=2, seed=0,
                                 embed_fn=_CG._pca_bootstrap)[0]

        def _weak_embed():
            _rng = _np.random.default_rng(0)
            _lab = _rng.integers(0, 3, 200)
            _c2 = _rng.normal(0, 4.0, size=(3, 2))
            _L2 = _c2[_lab] + _rng.normal(0, 0.6, size=(200, 2))
            _A = _rng.normal(0, 1.0, size=(2, 40))
            _X = _L2 @ _A + _rng.normal(0, 0.8, size=(200, 40))
            _Y, _ = _CG._pca(_X, 2)
            return _CG.check_T26(_X, _Y, n_embed=2, n_null=2, seed=0,
                                 embed_fn=_CG._pca_bootstrap)[0]

        def _t28_module():
            _rng = _np.random.default_rng(7)
            _mods = {i: f"M{i // 8}" for i in range(24)}
            _base = _rng.normal(0, 1, size=(120, 3))
            _X = _np.hstack([_base[:, [m]] @ _rng.normal(0, 1, size=(1, 8))
                             + _rng.normal(0, 0.35, size=(120, 8)) for m in range(3)])
            # 假阴性对照:同模块基因 → 扰动谱应高度相关 → 特异性不成立
            return _CG.check_T28(_X, _mods, ko_gene_idx=5, neg_ctrl_idx=6,
                                 seed=7, n_subsample=4)[0]

        _fn_cases = [
            ("T26", "随机噪声冒充真实嵌入 → 应判 fail", _noise_embed, "fail"),
            ("T26", "弱信噪比嵌入 → 应降级(判 fail)", _weak_embed, "fail"),
            ("T27", "零样本迁移却在目标上调参 → 应判 fail",
             lambda: _CG.check_T27(strategy="零样本迁移", ever_tuned_on_target=True,
                                   batch_overlap=0.6)[0], "fail"),
            ("T27", "从头训练却声称跨数据集复现 → 应判 fail",
             lambda: _CG.check_T27(strategy="从头训练", batch_overlap=0.6,
                                   claim="实现跨数据集复现")[0], "fail"),
            ("T27", "微调但 n_calib=8(<20) → 应判 fail",
             lambda: _CG.check_T27(strategy="微调", n_calib=8, gt_source="FACS",
                                   batch_overlap=0.7)[0], "fail"),
            ("T28", "假阴性对照(同模块) → 应判 fail", _t28_module, "fail"),
            ("T28", "虚拟KO写'功能验证' → 应判 fail",
             lambda: _CG.check_T28(
                 _np.random.default_rng(3).normal(0, 1, size=(80, 24)),
                 {i: f"M{i // 8}" for i in range(24)}, ko_gene_idx=5,
                 seed=3, n_subsample=3, claim="完成功能验证")[0], "fail"),
            ("T29", "声称代表充分却无子群样本量 → 应判 fail",
             lambda: _DE.check_T29(kind="人群数据", sensitive=True,
                                   adequacy_claim=True, clinical_claim=True)[0],
             "fail"),
            ("T30", "声称匿名化却无方法 + GDPR 无法条 → 应判 fail",
             lambda: _DE.check_T30(data_source="本地采集", data_flow="本地",
                                   features_visible=True, withdraw=True,
                                   secondary_use="仅本研究", anon_claim=True,
                                   gdpr_scope=True)[0], "fail"),
        ]
        for _fid, _desc, _fn, _exp in _fn_cases:
            try:
                _got = _fn()
                _ok = (_got == _exp)
                _det = f"判为 {_got}(期望 {_exp})"
            except Exception as _e:
                _ok, _det = False, f"用例异常 {type(_e).__name__}: {_e}"
            add(f"{_fid} 变异", f"{_fid} 应抓到:{_desc}", _ok, _det)
            if _ok:
                covered.add(_fid)
    except Exception as _e:
        add("T26-T30 变异", "函数级用例段可执行", False,
            f"导入或执行失败:{type(_e).__name__}: {_e}")

    # ── 函数级用例(v2.20 对称面:T33/T34/T35/V4MODAL)────────────────
    #    这四条与 T26–T30 同构:输入是数据与声明字典,文档变异无效,
    #    必须构造**违规输入**并断言 check_* 判 fail。
    #    ★ 每条都对应 rare_uncertainty.py 的一个夹具。
    try:
        import numpy as _np2
        import rare_uncertainty as _RU

        def _t33_rare():
            # 5/10000 Treg 声称显著下降:Wilson CI 上下界差 5.48 倍 → 硬阻断
            return _RU.check_T33(k=5, n_total=10000, claim="Treg 显著下降")[0]

        def _t33_short():
            # 2 年数据估 20 年一遇:1/n 无法解析目标概率 → fail
            return _RU.check_T33(target_prob=1 / (20 * 365), n_obs=2 * 365)[0]

        def _t34_no_unc():
            # 只报平均性能,声称精确预测 → 硬阻断
            return _RU.check_T34(claim="精确预测")[0]

        def _t34_uninformative():
            # 有不确定性但与误差无关,却声称个体风险 → fail
            _rng = _np2.random.default_rng(1)
            _u = _np2.linspace(0.05, 0.5, 200)
            _e = _np2.full(200, 0.3) + _rng.normal(0, 0.15, 200)
            return _RU.check_T34(per_sample_uncertainty=list(_u),
                                 abs_error=list(_e),
                                 claim="个体风险预测")[0]

        def _t34_no_strat():
            # corr 高(不确定性有信息)却未分层 → fail
            _rng = _np2.random.default_rng(0)
            _u = _np2.linspace(0.05, 0.5, 200)
            _e = 0.9 * _u + _rng.normal(0, 0.06, 200)
            return _RU.check_T34(per_sample_uncertainty=list(_u),
                                 abs_error=list(_e))[0]

        def _t35_mtag_circular():
            # MTAG 循环论证:用其输出声称遗传相关性高
            return _RU.check_T35(uses_multiomics_tool=True, tools=["MTAG"],
                                 tool_versions="mtag 1.0",
                                 mtag_vs_single_gwas_declared=True,
                                 mtag_genetic_corr_claim="遗传相关性高")[0]

        def _t35_ldsc():
            # LDSC intercept=1.2 未校正 → 遗传相关性系统高估
            return _RU.check_T35(uses_multiomics_tool=True, tools=["LDSC"],
                                 tool_versions="ldsc 1.0.1",
                                 ldsc_intercept=1.2)[0]

        def _v4_overclaim():
            # in silico + in vitro 却用 L4 措辞 → 跨级主张
            return _RU.check_V4_modal(in_silico=True, in_vitro=True,
                                      claim="治疗有效")[0]

        def _v4_overclaim3():
            # 仅 in silico 声称临床效用 → 跨 3 级
            return _RU.check_V4_modal(in_silico=True, claim="临床效用")[0]

        _fn_cases2 = [
            ("T33", "5/10000 稀有比例声称变化(CI 跨 5.48 倍)→ 应判 fail",
             _t33_rare, "fail"),
            ("T33", "2年数据估20年一遇(1/n 无法解析)→ 应判 fail",
             _t33_short, "fail"),
            ("T34", "只报平均性能却声称精确预测 → 应判 fail",
             _t34_no_unc, "fail"),
            ("T34", "不确定性无信息却声称个体风险 → 应判 fail",
             _t34_uninformative, "fail"),
            ("T34", "corr 高却未分层报告 → 应判 fail", _t34_no_strat, "fail"),
            ("T35", "MTAG 循环论证 → 应判 fail", _t35_mtag_circular, "fail"),
            ("T35", "LDSC intercept=1.2 未校正 → 应判 fail", _t35_ldsc, "fail"),
            ("V4MODAL", "in silico+in vitro 声称治疗有效 → 应判 fail",
             _v4_overclaim, "fail"),
            ("V4MODAL", "仅 in silico 声称临床效用 → 应判 fail",
             _v4_overclaim3, "fail"),
        ]
        # ── ★ v2.21 休眠判据激活用例(T03/T09/T12/T18)──
        #   这四条此前 direct=0 且 branch=0(L2 消融实测),即"从未拦过任何
        #   东西"。branch22 只是**写了夹具**,是否真能拦到违规必须由
        #   本变异用例证明 —— 否则激活本身就是新的纸面闭环。
        import dormant_check as _DC

        def _t03_shrink():
            # 声明全基因组校正,实际只校正 500 个假设 → 校正范围被缩小
            return _DC.check_T03([0.01] * 100, declared_family=20000,
                                 actual_family=500)[0]

        def _t09_insample():
            # 用样本内概率做校准 —— 训练内斜率恒≈1,判据形同虚设
            return _DC.check_T09("insample", declared=True)[0]

        def _t12_overfit():
            # 样本内 1.000 / 样本外 0.544 → 须强制标注(blocking=False → warn)
            return _DC.check_T12(1.000, 0.544)[0]

        def _t18_selective():
            # 预注册 4 个变体仅报 2 个 → 选择性报告(硬阻断)
            return _DC.check_T18(["A", "B", "C", "D"], ["A", "B"])[0]

        # ── ★ v2.21 T36 多组件整合增量消融 ──
        import component_ablation as _CA

        def _t36_no_ablation():
            # ROMO1 式:只报全组件性能,无 leave-one-out → 应拦
            return _CA.check_T36(components=["转录组", "蛋白组", "MR"],
                                 perf_full=0.812,
                                 perf_single={"转录组": 0.74},
                                 perf_loo={})[0]

        def _t36_circular():
            # 全部组件无增量却声称整合有用 → 循环论证,硬阻断
            return _CA.check_T36(components=["A", "B"], perf_full=0.70,
                                 perf_single={"A": 0.69, "B": 0.68},
                                 perf_loo={"A": 0.698, "B": 0.699},
                                 ci_lo={"A": -0.005, "B": -0.006},
                                 ci_hi={"A": 0.007, "B": 0.008})[0]

        _fn_cases3 = [
            ("T03", "声明全基因组却只校正 500 个 → 应判 fail",
             _t03_shrink, "fail"),
            ("T09", "用样本内概率做校准 → 应判 fail", _t09_insample, "fail"),
            ("T12", "样本内 1.000/样本外 0.544 → 应判 warn",
             _t12_overfit, "warn"),
            ("T18", "预注册 4 个仅报 2 个 → 应判 fail",
             _t18_selective, "fail"),
            ("T36", "只报全组件性能无消融 → 应判 fail",
             _t36_no_ablation, "fail"),
            ("T36", "全部组件无增量却声称整合有用 → 应判 fail",
             _t36_circular, "fail"),
        ]
        for _fid, _desc, _fn, _exp in _fn_cases3:
            try:
                _got = _fn()
                _ok = (_got == _exp)
                _det = f"判为 {_got}(期望 {_exp})"
            except Exception as _e:
                _ok, _det = False, f"用例异常 {type(_e).__name__}: {_e}"
            add(f"{_fid} 变异", f"{_fid} 应抓到:{_desc}", _ok, _det)
            if _ok:
                covered.add(_fid)

        for _fid, _desc, _fn, _exp in _fn_cases2:
            try:
                _got = _fn()
                _ok = (_got == _exp)
                _det = f"判为 {_got}(期望 {_exp})"
            except Exception as _e:
                _ok, _det = False, f"用例异常 {type(_e).__name__}: {_e}"
            add(f"{_fid} 变异", f"{_fid} 应抓到:{_desc}", _ok, _det)
            if _ok:
                covered.add(_fid)
    except Exception as _e:
        add("T33-T35/V4MODAL 变异", "函数级用例段可执行", False,
            f"导入或执行失败:{type(_e).__name__}: {_e}")

    # ★ MUST_COVER 强制:声明了却无用例 → 直接失败
    missing = [g for g in MUST_COVER if g.split(".")[0] not in covered]
    # 注意 add(cid, item, ok, detail) —— 第 3 位是 bool,不是 observed 值
    add("G-COV", "MUST_COVER 声明的守卫均有变异用例",
        not missing,
        ("缺: " + ", ".join(missing)) if missing else "齐全")

    n = len(ROWS); k = sum(ROWS)
    print(f"\n  变异测试: {k}/{n} 个守卫生效")
    # ★ v2.10:落盘供 MANIFEST 派生。此前 MANIFEST.verification.mutation
    #   是**硬编码 "6/6"**,而实际已增至 12/12 —— 汇总与原始输出不符,
    #   正是第 11 条陷阱形态③。修法同 guards:让汇总从原始结果派生。
    try:
        _mp = os.path.join(ROOT, "results", "mutation_results.json")
        # ★ v2.12(审计 P1-C):补 cases 明细与 coverage。
        #   此前只落 n_pass/total —— 附录 §G.5 想展示"逐用例是否抓到"时
        #   无数据可依,汇总又成了无源数字(第 11 条形态③)。
        _cases = [{"name": _r.get("name", ""),
                   "expect_id": _r.get("eid", ""),
                   "caught": bool(_r.get("caught"))}
                  for _r in getattr(main, "_ROWS", [])] if hasattr(main, "_ROWS") else []
        json.dump({"n_pass": k, "total": n,
                   # ★ v2.26：环境错误单列。空规与环境错误是**不同的事**，
                   #   合并计数会让"18 个守卫是空规"这种诬告进入台账。
                   "env_error": sorted(_ENV_BROKEN),
                   "env_error_count": len(_ENV_BROKEN),
                   "families": sorted(allfam), "covered": sorted(covered),
                   # ★ v2.19 修:原用 len(covered)/len(allfam) —— 未取交集。
                   #   covered 含 T26-T30/WP-* 等**不在 allfam 内**的家族
                   #   (allfam 只从两个 guard 脚本的 add( 调用扫得),
                   #   故比值达 181%。而控制台输出用的是交集,两者不一致 ——
                   #   同一指标两套算法 = 汇总掩盖原始输出(第11条形态③)。
                   "coverage": "%d%%" % round(
                       100.0 * len(allfam & covered) / max(1, len(allfam))),
                   "coverage_family": len(allfam & covered),
                   "coverage_declared_extra": sorted(covered - allfam),
                   "cases": _cases},
                  open(_mp, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    except Exception:
        pass
    # ★ v2.26：环境错误必须与"空规"分开报，且**优先**。
    #   若子进程根本没跑起来却报"存在空规"，审核方会去查 18 条并不存在的空规；
    #   而真实原因（解释器/依赖）反被掩盖 —— 这正是本框架最反对的"汇总撒谎"。
    if _ENV_BROKEN:
        print(f"\n  ✗ 环境错误：{len(_ENV_BROKEN)} 个用例的子进程未产出任何判定行")
        print("    这不是「空规」。真实原因是子守卫没跑起来（解释器/依赖/路径）。")
        print("    已发生的用例（前 6 个）：" + "、".join(sorted(_ENV_BROKEN)[:6]))
        print("    请先确认：`python -c \"import yaml,numpy\"` 在你**当前**解释器下成功。")
        print("=" * 78)
        return 2
    if k < n:
        print("  ⚠ 存在空规 —— 该守卫从未证明过自己能抓到违规")
    print("=" * 78)
    return 0 if k == n else 1


if __name__ == "__main__":
    sys.exit(main())