#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""run_units.py —— 功能单元执行器（一块一块跑，绿了才进下一块）

设计目标（用户 2026-09-12 提出）：
    "分成功能单元，一块一块的，一块完整运行 ok 无错后进入下一功能单元。"
    即：把一整坨验证拆成 **10 个功能单元**，每个单元有
      ① 独立入口（一条命令）
      ② 独立判定（gate：读台账，不靠人眼看末行文字）
      ③ 独立产物（落盘，可追溯）
    前一个单元的 gate 不过 → **立即停下**，不进入下一个。

与 build.py 的关系：
    build.py 是**构建交付物**的单一入口（13 步，产物 = 交付包）。
    本脚本是**跑验证单元**的入口（10 单元，产物 = 台账 + 单元报告）。
    二者顺序同源（见下方 ORDER 注释），但用途不同：上机执行用本脚本。

用法:
    python scripts/run_units.py                 # 全部单元，顺序执行，遇红即停
    python scripts/run_units.py --list          # 只列单元
    python scripts/run_units.py --only U3       # 只跑一个单元
    python scripts/run_units.py --from U5       # 从 U5 开始
    python scripts/run_units.py --keep-going    # 不因红而停（默认停）

退出码:
    0 = 全部单元 gate 通过
    1 = 某个单元 gate 未通过（已停下）
    2 = 环境错误（依赖缺失 / 解释器不对）—— 本结果无效
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time

# ── 控制台编码加固（与其余脚本同口径）──────────────────────────────────
try:
    if sys.stdout.isatty():
        sys.stdout.reconfigure(errors="replace")
    else:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(errors="replace")
except (AttributeError, ValueError):
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                    # crossval/
WS = os.path.dirname(ROOT)                      # 工作区根
RESULTS = os.path.join(ROOT, "results")
PY = sys.executable

# 台账路径（gate 只读这些文件，不读 stdout 汇总）
REPORT = os.path.join(RESULTS, "report.json")
LAYOUT = os.path.join(RESULTS, "layout_report.json")
WRITING = os.path.join(RESULTS, "writing_report.json")
EXPORT = os.path.join(RESULTS, "export_report.json")
MUTATION = os.path.join(RESULTS, "mutation_results.json")
SNAPSHOT = os.path.join(RESULTS, "platform_snapshot.json")


# ══════════════════════════════════════════════════════════════════════
# 工具
# ══════════════════════════════════════════════════════════════════════
def _env():
    e = dict(os.environ)
    e["PYTHONUTF8"] = "1"
    e["PYTHONIOENCODING"] = "utf-8"
    return e


def load_json(p):
    """读台账。读不到 → 返回 None（由 gate 判为未通过，不静默放过）。"""
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def latest_versioned(prefix):
    """取最新版本化文档（显式 > 最新 > 源文档 > None）。

    与 consistency_guard 的 main_doc() 同口径：不许把版本号写死。
    """
    cands = []
    for fn in os.listdir(WS):
        if fn.startswith(prefix) and fn.endswith(".md") and "_v" in fn:
            cands.append(fn)
    if cands:
        # 按 (版本号元组, 日期) 排序，取最新
        def key(fn):
            m = re.search(r"_v([\d.]+)_(\d{8})\.md$", fn)
            return (tuple(int(x) for x in m.group(1).split(".")),
                    m.group(2)) if m else ((0,), "")
        return os.path.join(WS, sorted(cands, key=key)[-1])
    src = os.path.join(WS, prefix + ".md")
    return src if os.path.isfile(src) else None


def p1_from_manuscript():
    """从合规样例稿派生 P1（摘要首句）。与 build.py 同口径，不硬编码猜值。"""
    p = os.path.join(ROOT, "demo", "manuscript_fixed.md")
    if not os.path.isfile(p):
        raise SystemExit("[run_units] 样例稿不存在: %s" % p)
    t = open(p, encoding="utf-8").read()
    m = re.search(r"##\s*摘要\s*\n+(.+)", t)
    if not m:
        raise SystemExit("[run_units] 无法派生 P1（缺 ## 摘要 节）—— 不兜底猜值")
    return re.split(r"(?<=。)", m.group(1).strip())[0]


def run_cmd(argv, cwd=ROOT, timeout=1800):
    t0 = time.time()
    try:
        p = subprocess.run(argv, cwd=cwd, env=_env(), timeout=timeout,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        out = p.stdout.decode("utf-8", errors="replace")
        rc = p.returncode
    except subprocess.TimeoutExpired:
        return 124, "[run_units] 超时 %ds" % timeout, time.time() - t0
    return rc, out, time.time() - t0


# ══════════════════════════════════════════════════════════════════════
# 各单元的 gate —— 只读台账，返回 (ok, detail)
# ══════════════════════════════════════════════════════════════════════
def gate_ledger(path, name, need_na_zero=False):
    """通用：n_pass/n_fail(/n_na) 三态判定。"""
    d = load_json(path)
    if d is None:
        return False, "%s 未生成或不可解析" % os.path.basename(path)
    np_, nf = d.get("n_pass"), d.get("n_fail")
    nn = d.get("n_na")
    if np_ is None or nf is None:
        return False, "%s 缺 n_pass/n_fail 字段" % os.path.basename(path)
    tot = d.get("n_total", (np_ + nf + (nn or 0)))
    ok = (nf == 0) and (np_ == tot)
    if need_na_zero and nn:
        ok = False
    det = "%s %d/%d 通过, 失败 %d" % (name, np_, tot, nf)
    if nn is not None:
        det += ", 不适用 %d" % nn
    return ok, det


# ══════════════════════════════════════════════════════════════════════
# 单元定义
# ──────────────────────────────────────────────────────────────────────
# 顺序与 build.py 的 STAGES 同源：
#   环境 → 主验证 → 排版 → 写作 → 导出 → handoff → pytest
#        → 跨文档一致性 → 变异(守卫自证) → 消融
# 依赖方向：U2 产出 report.json，U8 的守卫要读它 → U2 必须在前。
# ══════════════════════════════════════════════════════════════════════
def unit_defs():
    p1 = p1_from_manuscript()
    frame = latest_versioned("框架_独立审核包")
    rep = latest_versioned("四角度审核报告_合集")

    U = []

    def add(uid, name, goal, cmds, gate, on_fail):
        U.append(dict(id=uid, name=name, goal=goal, cmds=cmds,
                      gate=gate, on_fail=on_fail))

    # ── U1 ──
    def g_env(ctx):
        rc, out, _ = ctx["last"]
        if rc != 0:
            return False, "依赖导入失败（见上方输出）"
        if not os.path.isfile(SNAPSHOT):
            return False, "platform_snapshot.json 未生成"
        return True, "依赖可导入 · 环境快照已落盘"

    add("U1", "环境与依赖",
        "确认解释器能导入全部依赖，并落盘环境基线（供跨平台差异归因）",
        [[PY, "-c",
          "import numpy,scipy,sklearn,matplotlib,pandas,pypdf,yaml,pytest;"
          "print('deps OK')"],
         [PY, os.path.join(HERE, "platform_check.py")]],
        g_env,
        "缺包 → `pip install -r requirements.txt`；仍失败说明解释器选错了")

    # ── U2 ──
    def g_verify(ctx):
        d = load_json(REPORT)
        if d is None:
            return False, "report.json 未生成或不可解析"
        s = d.get("summary") or {}
        np_ = s.get("n_pass"); nf = s.get("n_fail")
        nn = s.get("n_na"); tot = s.get("total"); br = s.get("branches")
        if None in (np_, nf, nn, tot, br):
            return False, "report.json.summary 字段不全"
        ok = (nf == 0) and (np_ == tot) and (br > 0)
        return ok, "判定项 %d/%d 通过 · 失败 %d · 不适用 %d · 分支 %d" % (
            np_, tot, nf, nn, br)

    add("U2", "判据主验证",
        "跑 21 个分支的全部判定项，产出数字唯一来源 report.json",
        [[PY, os.path.join(HERE, "verify_all.py")]],
        g_verify,
        "判据项 FAIL = 高价值发现，**如实记录并回报，不要改脚本让它变绿**")

    # ── U3 ──
    add("U3", "排版与作图",
        "检查图件规格 / 结构 / 参考文献 / claim 升级（V5-P + V5-C）",
        [[PY, os.path.join(HERE, "layout_check.py"),
          "--figdir", os.path.join(ROOT, "figures", "demo")]],
        lambda ctx: gate_ledger(LAYOUT, "排版"),
        "V5-P/C 默认休眠；未进入排版阶段时「不适用」是合法的，须带非空理由")

    # ── U4 ──
    add("U4", "写作层",
        "WP-1~9 + NC-1~7：从数据到稿件的顺序、措辞越级、文献防幻觉",
        [[PY, os.path.join(HERE, "writing_guard.py"),
          "--doc", os.path.join(ROOT, "demo", "manuscript_fixed.md"),
          "--p1", p1,
          "--skill", os.path.join(ROOT, "demo",
                                  "research_survey_skill_demo.json"),
          "--out", WRITING]],
        lambda ctx: gate_ledger(WRITING, "写作", need_na_zero=True),
        "出现「不适用」即视为未通过（N/A 不是失败，但也不能算通过）；"
        "P1 必须来自稿件派生，手工编造会造成假失败")

    # ── U5 ──
    add("U5", "三格式导出",
        "同一稿件的纯文 / 纯图 / 合一三版本必须互相一致",
        [[PY, os.path.join(HERE, "export_guard.py"),
          "--a", os.path.join(ROOT, "demo", "export", "docA.txt"),
          "--b", os.path.join(ROOT, "demo", "export", "docB.txt"),
          "--p", os.path.join(ROOT, "demo", "export", "docP.txt"),
          "--out", EXPORT]],
        lambda ctx: gate_ledger(EXPORT, "导出", need_na_zero=True),
        "图号集合 / 占位符数 / 图注归属 / 参考文献逐字一致，逐项看")

    # ── U6 ──
    def g_handoff(ctx):
        rc, out, _ = ctx["last"]
        if rc != 0:
            return False, "守卫返回 rc=%d（链结构有断点）" % rc
        m = re.search(r"(\d+)/(\d+) 通过", out)
        det = ("链守卫 %s" % m.group(0)) if m else "rc=0"
        if "PENDING" in out or "ack=null" in out:
            det += " · 仍有交接未确认（如实报告，不算失败）"
        return True, det

    add("U6", "工作证据链",
        "14 个交接节点的完整性 + 接收确认位（谁→谁、什么状态、对方收到没）",
        [[PY, os.path.join(WS, "handoff", "scripts", "handoff_guard.py")]],
        g_handoff,
        "出现 PENDING 属**原有事实**，如实报告；链断裂才是真 FAIL")

    # ── U7 ──
    def g_pytest(ctx):
        rc, out, _ = ctx["last"]
        if rc != 0:
            return False, "pytest rc=%d" % rc
        m = re.search(r"(\d+) passed", out)
        return True, ("%s passed" % m.group(1)) if m else "rc=0"

    add("U7", "单元测试",
        "边界 / 参数化 / 空输入 —— 抓的是脚本自身的实现 bug",
        [[PY, "-m", "pytest", os.path.join(ROOT, "tests"), "-q"]],
        g_pytest,
        "pytest 报错往往指向真 bug（历史：check_colors([]) 空序列）")

    # ── U8 ──
    def g_docs(ctx):
        bad = []
        for rc, out, _ in ctx["runs"]:
            if rc != 0:
                bad.append(rc)
        if bad:
            return False, "有守卫返回非 0（%s）" % bad
        gr = load_json(os.path.join(RESULTS, "guard_results.json")) or {}
        return True, "一致性 %s · 报告 %s" % (gr.get("G.1", "?"),
                                             gr.get("G.2", "?"))

    cmds8 = []
    if frame:
        cmds8.append([PY, os.path.join(HERE, "consistency_guard.py"),
                      "--doc", frame])
    if rep:
        cmds8.append([PY, os.path.join(HERE, "report_guard.py"), "--doc", rep])
    add("U8", "跨文档一致性",
        "文档声称的数字 / 版本 / 锚点 必须与台账一致（G-1~G-14 + R-1~R-8）",
        cmds8,
        g_docs,
        "文档路径用「最新版本化副本」，不写死版本号；读不到即报错，不许跳过")

    # ── U9 ──
    def g_mut(ctx):
        rc, out, _ = ctx["last"]
        if rc == 2 or "环境错误" in out:
            ctx["env_error"] = True
            return False, ("**环境错误**：子守卫没跑起来 → 本轮无效。"
                           "不要当「空规」上报")
        if rc != 0:
            return False, "退出码 %d（= 存在空规，高价值发现）" % rc
        d = load_json(MUTATION) or {}
        np_, tot = d.get("n_pass"), d.get("total")
        cov = d.get("coverage")
        ee = d.get("env_error_count", 0)
        if ee:
            return False, "mutation_results.json 记有 %d 个环境错误" % ee
        return True, "守卫 %s/%s 生效 · 家族覆盖 %s" % (np_, tot, cov)

    add("U9", "守卫自证（变异测试）",
        "现场注入已知违规，验证每个守卫抓得到 —— 抓不到 = 空规",
        [[PY, os.path.join(HERE, "guard_selftest.py")]],
        g_mut,
        "退出码三态：0 全绿 / 1 真空规 / **2 环境错误（先修环境）**")

    # ── U10 ──
    def g_abl(ctx):
        for rc, out, _ in ctx["runs"]:
            if rc != 0:
                return False, "消融或自测返回非 0"
        return True, "消融 PASS · 自测 C-1~C-4 全生效"

    add("U10", "判据消融",
        "51 条判据里哪几条在干活；骨架/休眠比例 + 消融器自身的自测",
        [[PY, os.path.join(HERE, "ablation.py")],
         [PY, os.path.join(HERE, "ablation.py"), "--self-test"]],
        g_abl,
        "自测 C-4 证明 T37 判定层不是空规；若某条判据 direct=0 要显式说明")
    return U


# ══════════════════════════════════════════════════════════════════════
# 主流程
# ══════════════════════════════════════════════════════════════════════
def main():
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("--list", action="store_true", help="只列出单元")
    ap.add_argument("--only", default=None, help="只跑指定单元，如 U3")
    ap.add_argument("--from", dest="frm", default=None, help="从指定单元开始")
    ap.add_argument("--keep-going", action="store_true",
                    help="gate 不过也继续（默认停下）")
    a = ap.parse_args()

    units = unit_defs()
    if a.list:
        print("功能单元（按执行顺序）")
        for u in units:
            print("  %-4s %-14s %s" % (u["id"], u["name"], u["goal"]))
        return 0

    todo = units
    if a.only:
        todo = [u for u in units if u["id"] == a.only]
        if not todo:
            raise SystemExit("[run_units] 无此单元: %s" % a.only)
    elif a.frm:
        ids = [u["id"] for u in units]
        if a.frm not in ids:
            raise SystemExit("[run_units] 无此单元: %s" % a.frm)
        todo = units[ids.index(a.frm):]

    print("=" * 74)
    print("  功能单元执行器 · 共 %d 个单元待跑" % len(todo))
    print("  规则：前一个单元的 gate 通过后，才进入下一个")
    print("  PY  = %s" % PY)
    print("=" * 74)

    results, env_error = [], False
    for i, u in enumerate(todo, 1):
        print("\n" + "─" * 74)
        print("  ▸ %s %s（%d/%d）" % (u["id"], u["name"], i, len(todo)))
        print("    目标：%s" % u["goal"])
        ctx = dict(runs=[])
        if not u["cmds"]:
            print("    ✗ 本单元无可用命令（前置文档未找到）")
            results.append((u["id"], u["name"], False, "无可用命令"))
            break
        for argv in u["cmds"]:
            print("    $ %s" % " ".join(os.path.basename(x) if x == PY else x
                                        for x in argv))
            rc, out, dt = run_cmd(argv)
            ctx["runs"].append((rc, out, dt))
            ctx["last"] = (rc, out, dt)
            tail = [l for l in out.strip().split("\n") if l.strip()][-3:]
            for l in tail:
                print("      | " + l[:150])
            print("      rc=%d  %.1fs" % (rc, dt))
        ok, det = u["gate"](ctx)
        if ctx.get("env_error"):
            env_error = True
        print("    %s GATE %s —— %s" % ("✓" if ok else "✗", u["id"], det))
        results.append((u["id"], u["name"], ok, det))
        if not ok:
            print("    失败处置：%s" % u["on_fail"])
            if not a.keep_going:
                print("\n  ⛔ 停在 %s —— 未进入下一个功能单元。" % u["id"])
                break

    print("\n" + "=" * 74)
    print("  单元结果")
    print("=" * 74)
    for uid, name, ok, det in results:
        print("  %s %-4s %-16s %s" % ("✓" if ok else "✗", uid, name, det))
    n_ok = sum(1 for r in results if r[2])
    print("  —— %d/%d 单元通过" % (n_ok, len(results)))

    # 落盘（自指规避：不登记自身哈希）
    try:
        os.makedirs(RESULTS, exist_ok=True)
        json.dump({"n_pass": n_ok, "total": len(results),
                   "env_error": env_error,
                   "units": [{"id": i, "name": n, "pass": bool(o), "gate": d}
                             for i, n, o, d in results]},
                  open(os.path.join(RESULTS, "units_report.json"), "w",
                       encoding="utf-8", newline="\n"),
                  ensure_ascii=False, indent=2)
        print("  已写入 results/units_report.json")
    except OSError:
        pass

    if env_error:
        return 2
    return 0 if n_ok == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
