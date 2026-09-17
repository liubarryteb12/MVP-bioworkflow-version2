#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build.py —— 交付构建单一入口（v2.6 新增）

════════════════════════════════════════════════════════════════
为什么需要这个文件
────────────────────────────────────────────────────────────────
v1.5 与 v2.5 犯了**同一个**错误，两次：

    修好守卫 → 拿到 52/52 → 但没重跑 gen_appendix
    → 附录 §G 的 stdout 停留在修复前的旧快照
    → 汇总（MANIFEST / §0.2）与原始输出（stdout）对不上

v1.5 的修法是"gen_appendix 必须最后跑"，但这条规则**只活在执行者的脑子里**，
第二次照样违反。规则写在文档里、记在脑子里，都不算数——只有写进代码、
由代码强制顺序，才算真修。

════════════════════════════════════════════════════════════════
核心设计：顺序由代码强制，不靠人记
────────────────────────────────────────────────────────────────
STAGES 列表的**定义顺序 = 执行顺序**。任一步 rc != 0 立即中断。

关键约束（本文件存在的唯一理由）：
    gen_appendix 必须最后跑 —— 它读前面所有守卫的 stdout 写入附录。
    若它不在最后，附录里的 stdout 就是过期快照，
    而 MANIFEST / §0.2 是新值 → "汇总覆盖原始"（第 11 条陷阱形态③）。

════════════════════════════════════════════════════════════════
用法
────────────────────────────────────────────────────────────────
    python3 build.py 2.6 20260911          # 完整构建
    python3 build.py 2.6 20260911 --check  # 只做顺序后置校验，不重跑
    python3 build.py 2.6 20260911 --from 5 # 从第 5 步开始（危险，仅调试用）
"""

import os
import sys
import tempfile
# ── 控制台编码加固（v2.25）──────────────────────────────────────────────────
# 起因：中文 Windows 默认控制台为 cp936(GBK)，本脚本 print 的 ✓/✗/⚠/▸ 等字符
#   无法编码 → UnicodeEncodeError。实测 verify_all.py 在**已输出 8294 行、
#   最接近终点处**崩溃，report.json 未落盘，整轮证据作废。
#   这不是"字体差异/已知正常差异"，是崩溃；两份执行指导此前均未给规避手段。
# 处置：① 输出被重定向（证据采集场景）→ 强制 UTF-8，保证原样可读；
#      ② 交互式控制台 → 保留本机编码，仅把不可编码字符换成 '?'，不中断。
try:
    import sys as _csys
    if _csys.stdout.isatty():
        _csys.stdout.reconfigure(errors="replace")
    else:
        _csys.stdout.reconfigure(encoding="utf-8", errors="replace")
    _csys.stderr.reconfigure(errors="replace")
except (AttributeError, ValueError):
    pass      # 极旧解释器/被包装的流：保持原样。不吞其它异常。
import json
import re
import time
import shutil
import hashlib
import subprocess
from datetime import datetime, timezone, timedelta

CST = timezone(timedelta(hours=8))
# ★ v2.25：原为硬编码 POSIX 绝对路径 "/data/workspace" —— 与本文件自称
#   "build.py 是平台无关的，Win/Linux 通用"直接矛盾（Windows 上指向不存在的目录）。
#   改为：环境变量 CROSSVAL_WS > 本文件所在目录（build.py 就放在 WS 根）。
WS = os.environ.get("CROSSVAL_WS") or os.path.dirname(os.path.abspath(__file__))
CROSSVAL = os.path.join(WS, "crossval")
SCRIPTS = os.path.join(CROSSVAL, "scripts")
HANDOFF = os.path.join(WS, "handoff")
RESULTS = os.path.join(CROSSVAL, "results")

VER = sys.argv[1] if len(sys.argv) > 1 else "2.6"
DATE = sys.argv[2] if len(sys.argv) > 2 else "20260911"
CHECK_ONLY = "--check" in sys.argv

# 允许从中间步骤开始（仅调试；默认必须从头跑，否则顺序保证失效）
# ★ v2.18 修 bug:原默认 _start=1,而步骤循环用 `if no < _start: continue`
#   → STAGES 里 step_no=0 的「同步内嵌脚本」被**永久跳过**(0 < 1 恒成立),
#   日志里它连"步骤 1/17"都不显示。后果:改了 verify_all.py 后内嵌块
#   停在旧版(1439 行 vs 实际 1445 行),G-1.1 持续 FAIL 却看不出哪步失手。
#   这是"步骤声明了但从未执行"——第 11 条陷阱在**构建流程层**的形态。
#   改为 0:除非显式 --from,否则所有步骤(含 step_no=0)都执行。
_start = 0
if "--from" in sys.argv:
    _start = int(sys.argv[sys.argv.index("--from") + 1])

# 三份文档：源文档 → 版本化副本
VERSIONED = {
    "框架_独立审核包_v1.md": "框架_独立审核包_v%s_%s.md" % (VER, DATE),
    "四角度审核报告_合集.md": "四角度审核报告_合集_v%s_%s.md" % (VER, DATE),
    "附录_原始输出.md": "附录_原始输出_v%s_%s.md" % (VER, DATE),
}

_FAILED = []


def _now():
    from datetime import datetime, timedelta, timezone
    return datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%dT%H:%M:%S+08:00')

def log(msg):
    print(msg, flush=True)


def _child_env():
    """子进程环境：强制 UTF-8 输出。

    ★ v2.25：子脚本已改为「输出被重定向 → 强制 UTF-8」（防 GBK 控制台崩溃），
      父进程必须**同口径解码**，否则中文判定行会变乱码或抛 UnicodeDecodeError。
      父进程 default 用 locale(cp936) 解码，这在中文 Windows 上必然错位。
    """
    e = dict(os.environ)
    e["PYTHONUTF8"] = "1"
    e["PYTHONIOENCODING"] = "utf-8"
    return e


def _ensure_pytest():
    """pytest 预检。

    沙盒环境会在工具调用之间重置 pip 包 —— pytest 曾 "No module named"，
    导致构建在第 3 步中断。这里先探测，缺失则就地安装，使 build.py 自包含。
    """
    probe = subprocess.run([sys.executable, "-c", "import pytest"],
                           capture_output=True, encoding="utf-8",
                           errors="replace", env=_child_env())
    if probe.returncode == 0:
        return
    log("    ⚠ pytest 缺失，尝试 pip install（沙盒环境会被重置）…")
    r = subprocess.run([sys.executable, "-m", "pip", "install", "-q", "pytest"],
                       capture_output=True, encoding="utf-8",
                       errors="replace", env=_child_env())
    if r.returncode != 0:
        log("    ✗ pytest 安装失败：%s" % (r.stderr or "")[:200])
        sys.exit(1)
    log("    ✓ pytest 已安装")


def run(name, cmd, cwd=None, critical=True, pre=None):
    """执行一步。critical=True 时 rc != 0 立即中断整个构建。

    pre: 执行前调用的可调用对象（用于依赖预检等前置准备）。
    """
    if pre:
        pre()
    log("\n" + "─" * 70)
    log("  ▸ %s" % name)
    log("    $ %s" % (" ".join(cmd) if isinstance(cmd, list) else cmd))
    t0 = time.time()
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, encoding="utf-8",
                       errors="replace", env=_child_env(),
                       shell=isinstance(cmd, str))
    dt = time.time() - t0
    out = (r.stdout + r.stderr).rstrip()
    # 只打尾部，避免刷屏；完整输出已由各脚本自行落盘
    if out:
        tail = out.split("\n")[-6:]
        for line in tail:
            log("      %s" % line[:120])
    if r.returncode != 0:
        _FAILED.append(name)
        log("    ✗ 失败 rc=%d  (%.1fs)" % (r.returncode, dt))
        if critical:
            log("\n" + "=" * 70)
            log("  ✗ 构建中断：%s 失败。后续步骤依赖它，不再继续。" % name)
            log("=" * 70)
            sys.exit(1)
    else:
        log("    ✓ 通过 (%.1fs)" % dt)
    return r


def _current_run_id():
    """读当前 report.json 的 run_id(banner 同步用)。失败返回占位串。"""
    try:
        # ⚠ 审计 v2.7 抓到：原写 ROOT（本文件未定义该名）→ NameError 被
        #   下面的 except 吞掉 → 静默返回 "unknown" → banner 写成
        #   "run_id `unknown`"，格式合法但内容无意义。
        #   这正是"静默 except 掩盖真错误"的实例：异常发生了，却被降级成
        #   一个看起来正常的字符串。改为：读不到就硬失败，不许兜底。
        R = json.load(open(os.path.join(CROSSVAL, "results", "report.json"),
                           encoding="utf-8"))
        rid = R.get("run_metadata", {}).get("run_id")
        if not rid:
            raise SystemExit("[build] report.json 无 run_id —— 无法确定 banner run_id")
        return rid
    except SystemExit:
        raise
    except Exception as e:
        raise SystemExit("[build] 读取 run_id 失败(%s: %s) —— 不兜底为 unknown"
                         % (type(e).__name__, str(e)[:120]))


def _current_input_hash():
    """读 report.json 的 input_hash —— G-12 的**稳定锚**。

    ★ v2.25：G-12 原以 run_id 为跨制品锚，而 run_id 每次运行必变（框架 §5
      自己声明），于是重跑一次 verify_all（T4 就要求这么做）后该守卫必然 FAIL。
      input_hash = sha256(SEED|len(D1)|len(D3))，同代码同输入下稳定。
    读不到即硬失败 —— 不兜底（§3.3 静默失败禁令）。
    """
    R = json.load(open(os.path.join(CROSSVAL, "results", "report.json"),
                       encoding="utf-8"))
    ih = (R.get("run_metadata") or {}).get("input_hash")
    if not ih:
        raise SystemExit("[build] report.json 无 input_hash —— 无法同步 banner 稳定锚")
    return ih


def step_version(only=None):
    """把源文档复制为版本化副本。

    注意：附录的版本化必须在 gen_appendix 之后（它会重新生成附录源文档），
    所以这个 step 会被调用两次 —— 一次在守卫前（框架/合集），一次在
    gen_appendix 后（附录）。only 参数控制本次复制哪几份。
    """
    targets = VERSIONED if only is None else {k: v for k, v in VERSIONED.items() if k in only}
    for src, dst in targets.items():
        sp, dp = os.path.join(WS, src), os.path.join(WS, dst)
        if not os.path.isfile(sp):
            log("    ✗ 源文档不存在: %s" % src)
            _FAILED.append("版本化 %s" % src)
            sys.exit(1)
        txt = open(sp, encoding="utf-8").read()
        # ★ 审计 v2.6 P0-C:原实现只改文件名、不改 banner 版本号,
        #   导致文件名 v2.6 而 banner 写 v2.5、run_id 仍是上一轮的。
        #   更糟的是 P-6 的 _strip 显式剔除含"版本 v"/"run_id"的行,
        #   所以这条差异是完全的盲区 —— 抓不到,直到审计肉眼发现。
        #   修法:版本化时同步改写 banner,让"文件名版本==banner版本"
        #   由代码保证,而非靠记得改。
        rid = _current_run_id()
        new_txt, n1 = re.subn(r"版本 v[\d.]+", "版本 v%s" % VER, txt)
        new_txt, n2 = re.subn(r"run_id `[0-9a-f]{8,}`", "run_id `%s`" % rid, new_txt)
        # ★ v2.9(审计 P0-E 延伸):banner 同步后,§0.2 状态表里的
        #   "| run_id(取自 report.json) | `xxx` |" 仍是上一轮的 ——
        #   run_id 每次构建都变,硬编码必然滞后。G-12.rid-all 已抓到。
        #   与 banner 同理:版本化时一并同步,由代码保证。
        new_txt, n3 = re.subn(
            r"(\|\s*run_id\([^|]*\)\s*\|\s*)`[0-9a-f]{8,}`",
            lambda m: m.group(1) + "`%s`" % rid, new_txt)
        # ★ v2.25：新增 input_hash 同步（G-12 的稳定锚，见 _current_input_hash）。
        #   与 run_id 同理由代码保证，不靠记得改。
        _ih = _current_input_hash()
        new_txt, _n5 = re.subn(r"input_hash `[0-9a-f]{8,}`",
                               "input_hash `%s`" % _ih, new_txt)
        new_txt, _n6 = re.subn(
            r"(\|\s*input_hash\([^|]*\)\s*\|\s*)`[0-9a-f]{8,}`",
            lambda m: m.group(1) + "`%s`" % _ih, new_txt)
        if _n5 or _n6:
            log("      ↳ input_hash 同步: banner %d 处 / §0.2 %d 处 → %s" % (_n5, _n6, _ih))
        n3 += _n6
        if n3:
            log("      ↳ §0.2 状态表 run_id 同步: %d 处 → %s…" % (n3, rid[:16]))
        # ★ v2.10:R-8 抓到合集里 "59/59" 过期(守卫已增至 64 项)。
        #   守卫计数**每次新增检查项都会变**,手工同步必然滞后 ——
        #   与 banner / run_id 完全同族,故同样交由代码同步。
        #   注:用当前 guard_results.json(上一轮值)。若本轮新增了检查项,
        #   值会暂时过期 → R-8 FAIL → 再跑一次即收敛(此时已是新值)。
        _gp = os.path.join(RESULTS, "guard_results.json")
        if os.path.isfile(_gp):
            _G = json.load(open(_gp, encoding="utf-8"))
            _MAP = [("一致性守卫", "G.1"), ("审核报告守卫", "G.2"),
                    ("Handoff 链守卫", "G.3")]
            _lines = new_txt.split("\n")
            _n4 = 0
            for _i, _ln in enumerate(_lines):
                for _lbl, _k in _MAP:
                    if _lbl in _ln and "**" in _ln and _G.get(_k):
                        _ln2 = re.sub(r"\*\*\d+/\d+\*\*",
                                      "**%s**" % _G[_k], _ln, count=1)
                        if _ln2 != _ln:
                            _lines[_i] = _ln2
                            _n4 += 1
                        break
            if _n4:
                new_txt = "\n".join(_lines)
                log("      ↳ 守卫计数同步: %d 处(取自 guard_results.json)" % _n4)
        if n1 or n2:
            log("      ↳ banner 同步: 版本 %d 处, run_id %d 处 → v%s / %s…"
                % (n1, n2, VER, rid[:16]))
        # newline="\n"：避免 Windows 文本模式把 '\n' 变成 '\r\n'，
        # 使版本化副本在 Win/Linux 上字节一致（MANIFEST 的 sha256 才跨平台可比）。
        open(dp, "w", encoding="utf-8", newline="\n").write(new_txt)
        # v2.7 审查2发现:上面只改副本 banner,源文档 banner 仍停留在 v2.5。
        #   虽然 G-10.1 的 _strip 剔除 banner 行所以不会 FAIL,但源文档过期本身
        #   就是"改 A 忘改 B"的温床 —— 下次谁再生成副本,基准又不对了。
        #   改为:源与副本同步改写,二者 banner 恒等。
        if n1 or n2 or n3:
            open(sp, "w", encoding="utf-8", newline="\n").write(new_txt)
            log("      ↳ 源文档 已同步(banner + §0.2 run_id)")
        log("    ✓ %s → %s (%d B)" % (src[:28], dst[:36], os.path.getsize(dp)))


# 除三份版本化文档外,一并向审核方公开哈希的交付物
MANIFEST_EXTRA = ["作图规范_v1.0.md", "跨平台执行指导.md", "交付规则.md",
                  "上机总纲_判读与经验.md",
                  "写作流程规范_v1.0.md",
                  "MVP真实数据验证_结构化提示词_v1.0.md",
                  "云端服务器执行提示词_v1.0.md",
                  "build.py", "merge_delivery.py"]


# ══════════════════════════════════════════════════════════════════════
# 打包清单单一来源（★ v2.25 新增）
# ──────────────────────────────────────────────────────────────────────
# 起因：v2.24 的 v24_fixes 声称「新增 ZIP_CONTENTS.md + ZIP_CONTENTS.json」，
#   但 build.py 里**根本没有这一步**（STAGES 到 13 结束），zip 内也没有该文件 ——
#   而云端提示词 CP-2 把它列为「必须存在，缺任一 STOP」，于是守规矩的云端
#   执行方**第一步就死锁**。这是"声称改了 vs 实际改了"不符（第 11 条陷阱
#   形态③），与 v2.24 fixes 里自己记的那次事故（声称交付但文件不存在）同族复发。
#   修法：清单与实际打包**共用同一个函数**，杜绝两处维护必然不同步。
# 另：原清单含 Win11_Agent_测试指令.md（v2.3 时代文档，已被跨平台执行指导取代），
#   已移入 _archive_过期副本/ 并加入 G-14 的过期副本模式表。
# ══════════════════════════════════════════════════════════════════════
ROOT_FILES = [
    "MANIFEST.json",
    "框架_完整交付_v%s_%s.md" % (VER, DATE),
    "交付规则.md", "merge_delivery.py", "build.py",
    "作图规范_v1.0.md", "跨平台执行指导.md",
    "上机总纲_判读与经验.md",
    "写作流程规范_v1.0.md",
    "MVP真实数据验证_结构化提示词_v1.0.md",
    "云端服务器执行提示词_v1.0.md",
    "ZIP_CONTENTS.md",
]
_SKIP_DIRS = ("__pycache__", ".venv", ".pytest_cache", ".git", "_archive_过期副本")


def _ship_list():
    """待打包文件的**相对路径清单**（POSIX 分隔符，已排序）。

    ZIP_CONTENTS 生成与 _step_zip 共用本函数 —— 单一来源。
    """
    items = [f for f in ROOT_FILES if os.path.isfile(os.path.join(WS, f))]
    items += [d for d in VERSIONED.values()]
    for d in ("crossval", "handoff"):
        sp = os.path.join(WS, d)
        if not os.path.isdir(sp):
            continue
        for root, dirs, fs in os.walk(sp):
            dirs[:] = [x for x in dirs if x not in _SKIP_DIRS]
            for fn in fs:
                if fn.endswith((".pyc", ".pyo")):
                    continue
                items.append(os.path.relpath(os.path.join(root, fn), WS)
                             .replace(os.sep, "/"))
    return sorted(set(items))


def _step_zip_contents():
    """生成 ZIP_CONTENTS.md / ZIP_CONTENTS.json —— 交付包逐文件清单。

    自指规避：清单**不登记自身的 sha256**（写回后必然失效），
    与 MANIFEST 不写自身哈希、handoff 不登记自身同规。
    """
    rows, meta = [], {}
    for rel in _ship_list():
        if rel == "ZIP_CONTENTS.md":
            continue
        fp = os.path.join(WS, rel.replace("/", os.sep))
        if not os.path.isfile(fp):
            raise SystemExit("[build] 清单文件不存在: %s —— 不静默跳过" % rel)
        h, b = sha(fp), os.path.getsize(fp)
        rows.append((rel, b, h))
        meta[rel] = {"bytes": b, "sha256": h}
    import zipfile as _zf
    zp = os.path.join(WS, "框架交叉验证包_v%s_%s.zip" % (VER, DATE))
    total = len(rows) + 1          # +1 = ZIP_CONTENTS.md 自身
    lines = [
        "# ZIP_CONTENTS.md —— 交付包内容清单（v%s · %s）" % (VER, DATE),
        "",
        "> **用途**：审核方/云端执行方据此逐项核对收到的文件是否完整。",
        "> 与 `MANIFEST.json` 的 `files` 字段互为交叉索引（MANIFEST 只登记交付文档",
        "> 与关键脚本；本清单覆盖 zip 内**全部**文件）。",
        "",
        "> **自指规避**：本清单不登记自身的 sha256（写回后必然失效）。",
        "> 故下表条数 = zip 内文件数 − 1。",
        "",
        "| 项 | 值 |",
        "|---|---|",
        "| 生成时间 | %s |" % datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S %z"),
        "| zip 文件名 | %s |" % os.path.basename(zp),
        "| 下表条数 | %d |" % len(rows),
        "| zip 内文件总数（含本文件） | %d |" % total,
        "",
        "| # | 路径 | 字节 | sha256（前 16） |",
        "|---|---|---|---|",
    ]
    for i, (rel, b, h) in enumerate(rows, 1):
        lines.append("| %d | `%s` | %d | `%s…` |" % (i, rel, b, h[:16]))
    lines += ["", "---", "",
              "**核对方法（无需联网）**：",
              "",
              "```bash",
              "# Linux / macOS",
              "sha256sum -c <(awk -F'|' '/^\\| [0-9]+ \\|/ "
              "{gsub(/[`… ]/,\"\",$4); print $4\"  \"$3}' ZIP_CONTENTS.md)",
              "",
              "# 或逐项肉眼核对前 16 位（下表已给）",
              "```",
              "",
              "> 若某文件字节数或哈希不符 → **STOP 并报告**，不要继续执行"
              "（可能是传输损坏或包被改动）。",
              ""]
    open(os.path.join(WS, "ZIP_CONTENTS.md"), "w", encoding="utf-8",
         newline="\n").write("\n".join(lines))
    json.dump({"_note": "ZIP_CONTENTS.json —— 机器可读版；不登记自身哈希",
               "version": VER, "date": DATE, "n_files_excluding_self": len(rows),
               "n_files_in_zip": total, "files": meta},
              open(os.path.join(WS, "ZIP_CONTENTS.json"), "w", encoding="utf-8",
                   newline="\n"),
              ensure_ascii=False, indent=2)
    log("    ✓ ZIP_CONTENTS.md / .json（%d 项；不含自身哈希，自指规避）" % len(rows))


# ★ v2.10:vXX_fixes 此前靠**手工**追加,build.py 从不写入 ——
#   v2.8 / v2.9 的 fixes 因此从未进入 MANIFEST,G-6.0 对这两版 FAIL。
#   与"gen_appendix 最后跑"同理:写进文档不管用,必须由代码写入。
FIXES_BY_VERSION = {
    "2.26": [
        "★★ 本轮为**上机前优化轮**：只修\"会在云端跑不通 / 会误导执行方\"的缺陷，"
        "**51 条判据、9 条硬阻断、全部阈值一字未动**（延续 v2.25 的边界）。",
        "",
        "★ A1【硬缺陷·本轮最重要】guard_selftest 硬编码 `python3` 启动子守卫",
        "  实证：Windows 的 venv **不生成 python3.exe**（只有 python.exe/pythonw.exe），",
        "  故在 Win11 + venv（本框架自己推荐的执行方式）下，`python3` 落到 PATH 上",
        "  另一个**没装依赖**的解释器 → 子进程 ImportError → 输出里一个判定行都没有",
        "  → **_line_is_fail() 恒 False** → **18 个守卫家族被报成「空规」**、",
        "  家族覆盖率 85%、退出码 1。实测先红：36/66。",
        "  · 这是第 11 条陷阱的**镜像形态**：把**环境故障**误报成**规则失效**，",
        "    会把审核方引去查根本不存在的空规，比漏报更坏。",
        "  修：① 7 处 `python3` → `sys.executable`（父子同解释器，平台无关）；",
        "      ② run_guard 检测\"子进程未产出任何 [PASS]/[FAIL]\"→ 显式标注环境错误；",
        "      ③ 退出码扩为三态：0 全绿 / 1 真空规 / **2 环境错误（本次结果无效）**；",
        "      ④ mutation_results.json 增 env_error / env_error_count 字段。",
        "  先红后绿：36/66·85% → **66/66·100%**（见 验收证据_优化轮/）",
        "",
        "★ A2 `crossval/requirements.txt` 缺 pyyaml / pytest（第三次复发）",
        "  按该文件 `pip install -r` 后，ablation(T6)/guard_selftest(T7)/",
        "  consistency_guard/layout_check/writing_guard(T8)/pytest(T9) 全部 ImportError",
        "  → 连续失败 → 网关 G3 STOP。",
        "  · 与审查报告 P1-5/P1-7 **同一缺口的第三次复发**：前两次只改了执行指导；",
        "    v2.25 声称\"已补 pyyaml/pytest\"，**实际只改了文档、没改本文件**。",
        "  修：补 pyyaml==6.0.3 / pytest==9.1.1；并把版本口径统一为**跑出基线的那一套**",
        "  （原三处互不相同：本文件 `>=`、执行指导 `==2.2.6` 一套、实跑 2.5.0 一套）。",
        "  两份执行指导的 pip 行改为 `pip install -r requirements.txt` —— 依赖清单**只有一处**。",
        "",
        "★ A3 verify_all.py 的 Markdown 汇总行硬编码分母 → report.md 写「覆盖 21/8 分支」",
        "  控制台那行 v2.18 已改动态，Markdown 这一行漏改（改 A 忘 B）。",
        "  report.md 随包交付，云端执行方会直接读到这个不可能的分式。",
        "  修：`{nb}/8` → `覆盖分支 {nb} 个`，与控制台同口径。",
        "",
        "★ A4 crossval/ 下残留**同名不同内容**的指令副本 → 同一指令两个真相",
        "  `crossval/云端服务器执行提示词_v1.0.md`（第二代 587 行 / 21652 B）与根目录现行版",
        "  （645 行 / 24863 B）**被打进同一个 zip**（ZIP_CONTENTS 第 86 与第 92 项），",
        "  执行方 cd crossval 第一眼看到的就是旧那份。",
        "  · v2.25 P1-5 只归档了乱码旧版（530 行），漏了这一份 ——",
        "    因为 G-14 的 _ME 前缀表当时只有 3 个前缀 + 1 个已废文档名。",
        "  修：移入 _archive_过期副本/ 并做**三代版本对照表**；",
        "  G-14 的 _ME 扩为**全部交付文档名**（枚举式白名单必然漏，一次补齐）。",
        "",
        "★ B1 crossval/README.md 是包内**最容易被第一眼读到**却最不准的文档",
        "  数字停在 v1.x（33/33、8 个分支、10/8），且\"包内容\"一节说 scripts/ 只有",
        "  verify_all.py —— 实际 **24 个脚本**。此前的处置是让执行方\"忽略它\"。",
        "  修：整篇重写为现行口径（222/222 · 21 分支 · 66/66 · 70/70 · 24 脚本），",
        "  并声明\"本文件不自行维护数字，权威值见 MANIFEST.json\"。",
        "",
        "★ B2/B3 两份执行指导同步：删掉\"README 数字过时、忽略\"的批注（README 已修对）；",
        "  依赖安装行改为指向 requirements.txt；CP-7 / §7 增设 guard_selftest 三态退出码说明。",
        "",
        "★ B4 INVARIANTS.md 的**无法验证的声明**：原文写\"由 criteria.yaml 派生、",
        "  **不由人工维护**\"，而 build.py / gen_appendix.py 里都没有这一步生成。",
        "  改为如实描述（人工维护，须与 criteria.yaml 对齐），并写明恢复自动派生的前提。",
        "",
        "★ C1 新增功能单元执行器 scripts/run_units.py（用户 2026-09-12 提出）",
        "  需求原话：\"分成功能单元，一块一块的，一块完整运行 ok 无错后进入下一功能单元\"",
        "  修：把验证拆成 **10 个功能单元**，每个单元 ① 独立入口 ② 独立判定（gate）",
        "      ③ 独立产物；**前一个 gate 不过 → 立即停下，不进入下一个**。",
        "  · 单元顺序与 build.py 的 STAGES 同源：环境→主验证→排版→写作→导出→",
        "    handoff→pytest→跨文档一致性→变异(守卫自证)→判据消融",
        "  · gate **只读台账**（report.json / layout_report.json / writing_report.json /",
        "    export_report.json / mutation_results.json），不靠人眼看末行文字；",
        "    读不到或字段不全 → 判未通过，不静默放过",
        "  · U9 复用 v2.26 的三态退出码：rc==2 → 判「环境错误」并显式提示",
        "    「不要当空规上报」（与 A1 的教训闭环）",
        "  · 文档路径用 latest_versioned() 取最新版本化副本，不写死版本号",
        "  · 支持 --list / --only U3 / --from U5 / --keep-going；落盘 results/units_report.json",
        "  · 定位：build.py 管**构建交付物**，run_units.py 管**上机跑验证**；",
        "    二者顺序同源但用途不同，互不替代",
        "  实测：本机 10/10 单元 gate 全绿，退出码 0（验收证据_优化轮/UNITS_run1.txt）",
        "",
        "边界（明确**没有**做）：",
        "  · 未改任何判据、阈值、措辞规则；",
        "  · 未新增生信判据（审查 §6.3 的五条建议仍留给领域专家定阈值）；",
        "  · 未接真实数据（GSE31210 仍在 生信test/）。",
        "  · **未做物理目录重组**：scripts/ 仍是平铺 25 个 .py，根目录仍是平铺交付文档。",
        "    原因：build.py / consistency_guard / gen_appendix / 框架正文内嵌脚本 都按",
        "    现有路径锚定，挪文件会让「自证装置」整体失效，收益小于风险。若要重组，",
        "    须先改 build.py 的路径常量 + 三道守卫 + 内嵌同步，作为一个独立轮次来做。",
    ],
    "2.25": [
        "★★ 本轮由**独立审查**驱动（审查方在交付包上原样复现全部命令后提交报告）",
        "★ P0-1 交付包「自证装置」全线失效 —— 根因：未版本化文件名硬编码",
        "  实证：consistency_guard 63/69(6 FAIL)、report_guard 9/10、guard_selftest 崩溃(0/66)",
        "  而随包台账与附录却记 80/80 / 10/10 / 66/66 —— 开发机全绿、交付包全红",
        "  · 6 处回退路径（consistency_guard:399/539/551/562、report_guard:280、",
        "    guard_selftest:101/105/119）原硬编码未版本化旧名，而 zip 内只有版本化副本",
        "  · 讽刺点：consistency_guard 的 docstring 早已写「旧名，zip 内不存在」，",
        "    却只修了 argparse 的 default —— 「改了 A 忘改 B」第 N 次复发",
        "  修：新增统一解析器 main_doc() / latest_versioned()（显式 > 最新版本化 >",
        "  源文档 > SystemExit），禁止降级为「跳过检查」",
        "★ P0-2 ZIP_CONTENTS.md 缺失 → 云端 CP-2 第一步死锁",
        "  v24_fixes 声称「已新增 ZIP_CONTENTS.md + ZIP_CONTENTS.json」，但 build.py",
        "  **没有这一步**（STAGES 到 13 结束）—— 「声称改了 vs 实际改了」不符",
        "  修：新增 STAGES 12.5 由代码生成，并与 _step_zip 共用 _ship_list() 单一来源",
        "★ P0-3 G-12 拿「每次必变」的 run_id 当一致性锚（设计层自相矛盾）",
        "  框架 §5 自己声明「run_id 每次运行必然不同」，而 G-12 判 doc banner == report.json",
        "  → 任何人重跑 verify_all（T4 就要求这么做）后 4 项必然 FAIL，与平台无关",
        "  修：跨制品锚改用 input_hash（sha256(SEED|len(D1)|len(D3))，稳定）；",
        "  run_id 只查文档内部自洽；banner/§0.2 同步登记 input_hash（由 build 代码保证）",
        "★ P0-4 附录「原始输出」不可复现 → 新增 build 后置校验 P-8",
        "  在**打包后的交付布局**里重跑三道守卫 + 变异测试，全绿才算构建成功；",
        "  P-1~P-7 只盯开发机现场，一条都没抓到 —— 这正是本框架设计跨平台验证要找的东西",
        "★ P0-5 中文 Windows(cp936) 下 verify_all.py 崩溃（非「字体差异」，是崩溃）",
        "  实证：已输出 8294 行、在最接近终点的分支 8C 抛 UnicodeEncodeError(I²)，",
        "  exit 3、report.json 未落盘、整轮证据作废；两份执行指导均未给规避手段",
        "  修：9 个脚本内建编码加固（重定向→强制 UTF-8；控制台→替换不可编码字符）；",
        "  5 处 subprocess 调用统一 UTF-8 同口径解码；跨平台指导 §3.1 增设 $env:PYTHONUTF8",
        "★ P1-1 写作层基线三处不一致，且「不给输入 = 自动通过」",
        "  · build 从不传 --p1 → 3 项判 N/A；--skill 恒缺 → WP-3.1 永久 N/A（N/A 不是失败）",
        "  · 实测：不传 --p1 得 38 通过 + 4 N/A，而汇总写「38/38 通过」（缺口不可见）",
        "  修：build 传真实 P1（从稿件派生，不硬编码）+ 新增 demo skill 夹具；",
        "  WP-3.1 硬化（未提供 --skill → FAIL）；汇总分母改为三态之和",
        "★ P1-2 新增 G-3.uniq：同一语境取值必须唯一（先红后绿已验证）",
        "  实证漏检：MoCA 队列 OR 在 §3 H-5 写 **2.741**、在 §7.2 与附录写 **3.085**",
        "  （实跑值 3.085）—— G-3 只查「数字能否定位」，两个矛盾值双双 PASS",
        "  已修 H-5 的 2.741/1.195 → 3.085/1.238",
        "★ P1-3 G-13 自相矛盾修复：原要求「至少命中 1 处硬编码」→ 修干净反而 FAIL",
        "  （等于强迫代码保留违规）改为 G-13.pat（合成样本自证模式有效）+",
        "  G-13.clean（真实源码未受保护硬编码数必须为 0）",
        "★ P1-4 G-2.2/G-4.2 用 len(checks) 猜排版通过数 → 产生假 FAIL",
        "  修：layout_check.py 显式登记 n_pass/n_fail/n_total，消费方不再猜",
        "★ P1-5 包内混入过期文档与未登记文件",
        "  · Win11_Agent_测试指令.md（v2.3 时代，101 项/15 分支）移入 _archive_过期副本/",
        "  · 乱码名条目 Σ║æτ£…（UTF-8 字节被按 GBK 解读）为**旧版 530 行**，",
        "    与现行 587 行并存 = 同一指令两个真相 → 一并归档",
        "  · MANIFEST.files 补登 云端服务器执行提示词；_ship_list 单一来源覆盖全部交付文件",
        "★ P1-6 build.py / merge_delivery.py 自身不可移植：",
        "  WS 硬编码「/data/workspace」、STAGE 硬编码「/tmp/」—— 与",
        "  「build.py 是平台无关的，Win/Linux 通用」直接矛盾",
        "  实测：Windows 上构建第 12 步报「[merge] 缺少源文件: MANIFEST.json」",
        "  修：WS 由 __file__ 派生（可由 CROSSVAL_WS 覆盖）+ STAGE 用 tempfile",
        "★ P1-7 云端提示词依赖清单缺 pyyaml / pytest（T6/T7/T9 会 ImportError → G3 STOP）",
        "★ 新增一致性守卫第三态：_na() 登记 + 汇总行给出 不适用 N 项",
        "  起因：v2.24 里 G-10/G-11 整块异常被 except 吞掉，判定项 80→69 静默消失，",
        "  汇总照写「63/69 通过」—— 第 11 条陷阱形态③发生在本守卫自己身上",
        "★ P0-6 merge_delivery.py 在 Windows 写出 CRLF → 合并自检 9/9 误报未收录",
        "  文本模式写文件把 LF 翻成 CRLF，而自检用源文件的 LF 文本做子串比对",
        "  → 构建第 20 步「合并交付」直接失败，且 §1 MANIFEST 回读正则同样失配。",
        "  Linux 不做该转换，故开发机从未暴露 —— 又一个「只在一侧平台成立」的缺陷。",
        "  修：显式指定 LF 换行 + 自检前归一化 CRLF；",
        "  并同步给 版本化副本 / MANIFEST / ZIP_CONTENTS / 附录 的写入点加 LF，",
        "  使 Win/Linux 产出的字节一致（MANIFEST 登记的 sha256 才跨平台可比）",
        "★ 本轮变更清单的**唯一存放处**是 MANIFEST.json 的 v225_fixes 字段",
        "  （由 build.py 写入，不再复制进附录 —— 两处各存一份必然不同步，",
        "   这正是本框架栽过多次的『同一事物两个真相』）",
    ],
    "2.20": [
        "★ 本轮补的是**已有判据的对称面**,不是扩展边界(建议文档原话)",
        "  T16 管细胞数下限 → T33 管**比例估计的 CI**",
        "  T12/T13b 管群体层 CI → T34 管**per-sample 不确定性**",
        "  T32 管 MR → T35 管 LDSC / MTAG / colocalization",
        "  V4 管主张-证据匹配 → V4MODAL 管**跨模态强度阶梯**",
        "T33 稀有/极端事件概率的样本量下限,stage_tag=rare_event",
        "  · 实测 Wilson CI:5/10000 → CI [2.14e-4,1.17e-3],相对宽度 1.913>1.0,",
        "    上下界差 5.48 倍 → **硬阻断**(T16 只看细胞数下限会放过)",
        "  · 可解析下界 1/n:1年(2.74e-3)>目标 1.37e-4 无法解析;",
        "    39年(7.02e-5)可解析 —— 复现 Dowling/Amonkar 短记录系统性低估尾部",
        "T34 预测不确定性分层报告,stage_tag=prediction",
        "  · 实测 corr:信息性 0.892 vs 无信息 -0.031",
        "    → 把'声称精确预测但 corr<0.1 则无信息'从断言变为可复现证据",
        "  · corr>0.3 必须分层(低/高不确定组 AUC、校准、Brier 分别列)",
        "T35 多组学整合工具已知偏倚,stage_tag=multiomics",
        "  · MTAG **循环论证**:用其输出声称遗传相关性高 = 用联合估计的定义自证",
        "  · LDSC intercept 偏离 1 (>0.1) 未校正 → 遗传相关性系统高估",
        "  · coloc H4>0.8 但先验未声明 → 判'判不了'(后验对先验敏感)",
        "  · 实证锚点:ROMO1(Wang 2025)用 LDSC+MTAG 实测中招",
        "V4MODAL 跨模态验证强度分级(L1→L2→L3a→L3b→L4),stage_tag=validation",
        "  · 铁律**不得跨级主张**:in silico+in vitro ≠ '治疗有效'",
        "T31 扩展**冗余度维度**(WCMI 启示):选择位置正确 ≠ 特征集可用",
        "  · |r|>0.9 占比 >30% → 冗余过高须去冗余;10%~30% 灰区",
        "新增 rare_uncertainty.py(T33/T34/T35/V4MODAL, 29 条双向夹具)",
        "新增 branch21;判据 42→46 条;主验证 160→201 项;分支 18→19",
        "★ 修 3 处**判据自身**的 bug(均由夹具'先红后绿'暴露):",
        "  1. T33:k/n 推导 prop 写在 `if prop is not None` 块**内部** →",
        "     prop 为 None 时整块跳过,判据直接放行(第11条形态①)",
        "  2. T34:未报相关系数时只 append detail 不改 status → 判'通过'",
        "  3. V4MODAL:词表**有重叠**('候选'同属 L1/L2 上限)→ L1 达成",
        "     却声称'候选'被误判跨级;改为每词只归属一个等级",
        "★ 变异用例 +9(T33×2/T34×3/T35×2/V4MODAL×2),MUST_COVER 覆盖 21/21",
    ],
    "2.19": [
        "★ 覆盖度复查(非建议文档直接给出):grep 全库 '特征选择'/'嵌套'/'CV 内' 命中 **0**",
        "  → 框架此前**完全没有特征选择泄露判据**,这是生信预后模型头号 AUC 虚高源",
        "  T09 只管'性能评估不得用样本内概率',**不管特征选择本身用了全数据集**",
        "T31 特征选择与超参必须在评估折叠内(选择泄露),stage_tag=modeling",
        "  · 未声明选择位置 → 判'判不了'(**不得默认 nested**,默认放行即空规)",
        "  · 全数据集一次性选择 → 不通过;nested 须给出外层/内层折数否则视为未声明",
        "  · 实证锚点:肺癌4基因/卵巢癌2基因/ROMO1 三篇**同一结构**全部中招",
        "T32 孟德尔随机化工具变量假设,stage_tag=causal",
        "  ★ 建议 §0 写'有 MR 但无判据' —— grep 'MR'/'孟德尔'/'mendel' 均 **0 次**,",
        "    框架此前**根本没有 MR**(不是'有而缺判据'),建议此处事实有误,已记录",
        "  · F<10 弱工具变量 / 多效性须检验 / two-sample 祖源不匹配→硬阻断",
        "  · 措辞:MR 只能'提示/支持因果',禁'证明/证实因果'",
        "T13b small_sample_extension 补**脚本验证**(此前只有条文 = 空规风险)",
        "  · 新增 tl_bee.py:声明检查 7 夹具 + alpha 事后调的**数值反例**",
        "  · 数值反例把'alpha 事后调→R3'从断言变为证据:偏差 0.000-0.050 → 0.168-0.202",
        "★ 调和建议文档两处自相矛盾:§0 标 WCMI/药物重定位为'缺口',§4 说'不吸收'",
        "  → 结论:**不吸收方法,但吸收其暴露的防错点**(WCMI 暴露的正是 T31)",
        "新增 selection_causal.py(T31/T32, 15 条双向夹具 + 7 变异用例全生效)",
        "新增 tl_bee.py(T13b 扩展, 7 夹具)",
        "判据 40→42 条;主验证 136→160 项;分支 17→18",
        "★ 修 mutation_results.json 覆盖率算法:json 用 len(covered)/len(allfam)"
        "  而控制台用交集 —— 同一指标两套算法,json 算出 181%(不可能>100%)",
        "  covered 含 T26-T30/WP-* 等不在 allfam 口径内的家族所致",
        "  统一为交集口径 → 100%(21/21),并新增 coverage_declared_extra 字段",
        "  暴露 17 个有用例但不在 allfam 统计口径的家族(T26-T30 + WP-*)",
    ],
    "2.16": [
        "★ 文献驱动:23篇已发表论文提取5条实证判据 T21-T25(branch16)",
        "T21 组别样本量下限与平衡(三态)|文献17 Table1 RA 16v4 对照仅4例",
        "T22 训练-外部验证性能落差|文献18 训练AUC .666/验证 .560 落差.106",
        "T23 多数据集QC阈值一致性(须声明)|文献19 2.5% vs 5%/25% 不同模态",
        "T24 验证集独立性(同队列split=数据泄露)|文献19 跨物种验证优先",
        "T25 空间/ROI选择盲法|文献21手动按位置选区 vs 文献19盲法选区",
        "T21 二值→三态修订:n=6 恰卡下界被判PASS(夹具 T1D 10v6 暴露)",
        "  小样本是连续风险非阈值开关,灰区[6,10)须声明小样本+敏感性分析",
        "branch16 文献夹具13条:违规项应拦/合规项应放行(双向验证,防空规)",
        "fix: import literature_gap 缺失致 NameError 被静默吞(同类第9次)",
        "判据 30→35 条;主验证 101→116 项;分支 15→16",
    ],
    "2.18": [
        "★ 结论守卫:13篇论文驱动新增 T26-T30(branch17),框架从'流程守卫'升级为'结论守卫'",
        "★ 编号冲突:建议的 T21-T25 与 v2.16 已占用编号冲突,改用 T26-T30 并在 criteria.yaml 记录",
        "T26 嵌入信号-噪声定量分离(EMBEDR)|marginal resampling 零假设 + per-sample p 值",
        "T27 跨数据集泛化条件匹配声明(DAISM-DNN/EpiTopics)|n_calib>=20 + 迁移策略措辞上限",
        "T28 计算扰动可复现流程(scTenifoldKnk)|模块富集 p<0.05 + rho>=0.5 + 阴性对照",
        "T29 数据正义自查(Braun&Hummel)|四支柱举证,声称必须有举证,可判 N/A",
        "T30 数据治理声明(PORT)|流向/特征可见/撤回/二次使用 + 匿名方法 + GDPR 法条",
        "T14 扩展:方法层迁移策略维度(结果层 AND 方法层,缺 T27 则 T14 无效)",
        "T13b 扩展:n<50 须声明源域信息与相关度 |alpha|,事后调参 → R3",
        "T26 修方向 bug:celltype p 中位数判定写反(真信号 p=0.002 被判'不得用于下结论')",
        "T26 修 EES:距离值分布对结构不敏感 → 改用邻居**身份**分布(重叠度 0.144 vs 0.136 无区分)",
        "T26 修 n_embed:对确定性 PCA 三次算同一嵌入 → 改子样本拟合产生真随机性",
        "T26 修夹具:各向同性噪声无低维流形 → 改用低维流形投影,实测 sig_frac 随信噪比单调 0.76→0.003",
        "T28 修 np.math.erfc(numpy 2.x 已移除)→ math.erfc",
        "criteria.yaml 修 YAML 缩进:判据列表是顶层序列,追加段落须缩进 0(误用 2 致解析失败)",
        "criteria.yaml 修追加位置:文件末尾有 tools/invariants 顶层键 → 须插入 criteria 列表内",
        "变异测试扩展:MUST_COVER 支持函数级用例(T26-T30 无法用文档变异验证)",
        "分支数 15 → 16(branch17),同步 verify_all 汇总硬编码",
    ],
    "2.8": [
        "MUST_COVER 强制:新增守卫必须声明变异用例,缺则 G-COV FAIL",
        "附录 banner 增加版本号字段(避免版本号同步负担)",
        "build_version.json 作为版本权威源(在遍历前写入)",
    ],
    "2.9": [
        "G-11.3 正则锚点错位修复:枚举多形态全量匹配(原只搜 'N 条判据')",
        "G-12 run_id 正则允许括号间隔 + 全量校验(rid-all/rid-cov)",
        "变异测试按 expect_id 前缀分发(原按文档类型,送错守卫)",
        "G-11 漏修 --doc(第三次复发),改为以 --doc 为准",
        "框架 §2 声称改为 G-11 真实覆盖范围(多形态)",
    ],
    "2.10": [
        "G-11.3 命中数改为按位置计数(原按值去重,掩盖覆盖广度)",
        "MANIFEST.verification 改为派生(mutation 原硬编码 6/6 已过期)",
        "vXX_fixes 由 build.py 写入(原手工维护,v2.8/v2.9 缺失)",
        "guard_selftest 落盘 results/mutation_results.json",
    ],    "2.13": [
        "真实数据压力测试准备:GSE250167 适配器 + §10 适用性闸门",
        "★ 预演发现:§10「不适用+理由」在主验证脚本中**零代码落点**",
        "  → 101 项只有 PASS/FAIL 二态,sRNA 数据进来只能强行套用或崩溃",
        "新增 Ledger.add_na() 第三态出口(理由为空即 raise)",
        "新增 applicability_gate.py:按数据特征声明判定 9 条判据适用性",
        "新增 realdata_adapter.py:读 GSE250167 格式,宁停勿猜(不猜测分组)",
        "verify_all.py 加 --datasource real / --datadir 参数",
        "★ 修 3 次同类 bug:引入第三态后 npass/nna/total 在 None 上崩溃或漏计",
        "  · npass 仍用 sum(passed) → 0+None TypeError",
        "  · nna 用了 r.get('na') → None 求和 TypeError",
        "  · total=npass+nfail 漏掉 N/A(§10 禁止的静默删除)",
        "★ 修适用性闸门自身 bug:_need_singlecell 逻辑反向,把非单细胞误判适用",
        "  · 判错方向是最危险的「过度适用」→ 会对 sRNA 强行套单细胞规则",
        "★ 修 applicability_gate 静默 except 吞 KeyError(理由残留 {assay_type})",
        "  · 讽刺点:本框架明令禁止静默 except,此处正是该错误的实例",
        "新增 tests/test_na_state.py 7 项(三态计数/空理由/闸门反向/占位符)",
        "GSE250167 场景预演:9 条判据中 8 条不适用,仅 T01 适用",
    ],
    "2.12": [
        "G-13.lint 多模式扫描(join/concat/pathlib),措辞收窄为已枚举模式",
        "G-13 扫描范围收窄为 *guard*.py 且排除 selftest(两度误伤生成器/测试器)",
        "G-14 改递归扫描 os.walk(原只扫根目录)",
        "G-14 递归立即抓出真问题:crossval/framework/ 下两份严重过期同名副本",
        "  · 四角度审核报告_合集.md 少 8789B、附录_原始输出.md 少 78328B",
        "  · 已移入 _archive_过期副本/ 并加 README 声明禁用",
        "附录新增 §G.5 变异测试原始输出(mutation_results.json + 逐用例表)",
        "mutation_results.json 补 cases/coverage 字段(原只有 n_pass/total)",
        "附录 §G.5 澄清覆盖率粒度:家族级 100%,非子检查级",
        "清 §8 陷阱清单「6/6」过期值 → 29/29 并标注轮次",
        "新增 G-13.scope / G-13.lint / G-14.cov 三项覆盖度自检",
    ],
    "2.11": [
        "G-13 源码级守卫:守卫不得硬编码主交付文档路径(源码层防忽略 --doc 复发)",
        "G-14:crossval/ 不得残留主交付文档副本(消除同一文档两个真相)",
        "修 G-11.2 空规(第 7 次忽略 --doc:注入条数 99 仍报 obs=21)",
        "修 G-10 / R-7 忽略 --doc(第 5、6 次)",
        "修 G-12 忽略 --doc(第 8 次,放宽为 basename 前缀匹配)",
        "默认 --doc 由 ROOT 改为 WS(过期副本 v1.4 致 G-11.2 报 None 的根因)",
        "变异判定防伪绿:_line_is_fail 按行判定(原 expect_id in out and FAIL in out)",
        "变异用例 +8(G-10/G-4/G-6/R-2/R-3/R-4/R-5/R-7)+ G-13/G-14 源码与 fs 变异",
        "G-4.2 空规修复(裸 in s → 排版语境上下文匹配)",
        "R-5 变异用例锚点覆盖两种写法(| Handoff 链 | 14 节点 与 handoff/:14 节点)",
        "新增 --src / --frame 参数,支持零污染变异(不必改主文档)",
        "变异覆盖率 57%→100%(21/21 家族),29/29 用例全生效",
    ],    "2.14": [
        "陷阱清单标题条数修正:§8 标题与目录原写 10 条,实际 11 条(声明 vs 实际)",
        "新增《上机总纲_判读与经验.md》:判读三档 + 已知正常差异 + 经验教训 + 方法论",
        "上机总纲纳入单文件交付(merge_delivery SRCS)、zip 打包与 MANIFEST_EXTRA",
        "MANIFEST.files 由 8 份增至 9 份(含上机总纲)",
        "FIXES_BY_VERSION 缺条目时由静默跳过改为构建前显式 SystemExit",
    ],    "2.15": [
        "新增 §12 写作流程层:WP-1~9 九节点 + NC-1~7 叙事约束(写作流程规范_v1.0.md)",
        "新增 writing_guard.py(WP-1~8) 与 export_guard.py(WP-9 三格式一致性)",
        "新增 spec/writing_spec.yaml 词表/阈值配置 + 词表类型自检(防';'拼接空规)",
        "修 WP-5a.1:显著标注窗口由固定50字符跨句改为同句内(变异测试暴露)",
        "criteria.yaml 判据 21 → 30 条(新增 WP-1/2/3/5a/5c/6/7/8/9)",
        "变异测试 29 → 42 项,WP-1~9 全部纳入 MUST_COVER(覆盖率100%)",
        "WP-3 支持第三态:research_survey_skill 返 0 篇判 N/A 而非 AI 生成",
    ],
    "2.24": [
        "★★ 自伤事故(本轮最严重):上一轮声称「v2.24 构建完成,四项 P0 + 七项 P1"
        "  全部闭环」并给出 media_info —— **但文件根本不存在**",
        "  实测:框架_完整交付_v2.24_*.md 与 框架交叉验证包_v2.24_*.zip 均为 0 字节/不存在;",
        "  最新真实存在的只有 v2.23。用户两次反馈「你没发给我」后才发现",
        "  · 性质:第 11 条陷阱形态③的现实版 —— **声称完成 vs 实际产出**不符",
        "  · 与此前「MANIFEST 手工填」「FAIL 被写成 PASS」同族,但发生在交付终点",
        "  · 教训:media_info 的 path 必须指向**校验过存在的文件**,不得凭构建日志声称",
        "★ P0-1 zip 内容清单缺失 → 新增 ZIP_CONTENTS.md + ZIP_CONTENTS.json",
        "  逐文件列 路径/字节/sha256,与 MANIFEST.files 互为交叉索引",
        "  审核反推:上机需 scripts/24py、tests/、schema/、spec/、handoff/、",
        "  figures/demo/、demo/、requirements.txt、INVARIANTS.md,此前**全部未登记**",
        "★ P0-2 判定标准数字过期 → 101 项/15 分支 改为 222 项/21 分支",
        "  · 首检曾报「过期数字 0 处」→ **检测规则与文档实际形态错位**(第 N 次复发):",
        "    脚本只认旧写法,文档已改新写法,匹配不到就报 0",
        "  · 修形态后真抓到 4 处字面残留(框架正文 2、指导 1、branches=15 1)",
        "★ P0-3 ablation.py 无执行出口 → 跨平台指导插入步骤 4.5",
        "  T37 的判定项由 ablation.py 产生(不在 verify_all 的 ledger 里),",
        "  缺此步则上机后 T37 判定永久缺失;返回清单新增「必须贴 ablation stdout」",
        "★ P0-4 INVARIANTS.md 三处矛盾 → 判定:**文件确实存在**(2169 字节)",
        "  v24_fixes 正确、MANIFEST.files 漏登记、报告二 §3.2 的「不存在」为过期陈述",
        "  已补入 files 与 zip 清单,三处表述统一",
        "★ P1 七项:两个守卫默认 --doc 指向版本化文档(不再静默读 v1 旧名);",
        "  layout_check 的 C-6 尊重 --figdir(否则「我的图都通过」是假象);",
        "  跨平台指导开头加「解压后目录结构」;报告二 §0.1/§0.2 内部矛盾已更新;",
        "  requirements.txt 归属明确;所有相对路径强调 cwd=crossval/",
    ],
    "2.23": [
        "★ 用户:补最后一层 —— v2.22 产出了 criteria_dist(体温表),但没有一条"
        "判据来读这张表并下诊断;骨架/休眠比例可自我声明,无独立检查",
        "新增判据 **T37 判据体系的骨架/休眠比例**(L2 消融的判定层),51 条判据",
        "  · 三态(与 H-2 双阈值同构):休眠率=0 → pass;0<r<20% → warn;r>=20% → fail",
        "  · 附加:GLOBAL 占比 >=10% → warn(归因稀释);单判据 n_direct/总判定项 >40% → warn(垄断)",
        "  · 实跑:休眠率 0/50 = 0% → pass;GLOBAL 5/274=1.8%;T13c 16/274=5.8%(无垄断)",
        "★ 自指口径决策(重点):T37 **排除自身**(分子分母均排除,META_EXEMPT)",
        "  与既有自指处理同规:report_guard 不计入自身合法集、链文件不登记自身"
        "  sha256、MANIFEST 不写自身哈希 —— 若计入,等于「自己给自己打分」",
        "  ★ 但**分类口径**仍合并 T37 判定项(n_direct=1),否则报表出现"
        "    「休眠 1: T37」与 A-7「休眠 0/50」自相矛盾。两个口径已统一:骨架 51/休眠 0",
        "★ 新增 na_tested 字段(审核 §4):主 run 的 n_na 恒为 0,因为应判 N/A 的"
        "  输入(expect='na')通过了判定 → **记为 PASS 而非 N/A**,N/A 出口"
        "  在统计上完全不可见。na_tested 统计「测过 N/A 出口的判定项数」",
        "  实测:na_tested 合计 8(T03/T09/T12/T18 各 1 等),而 n_na 合计 0 ——"
        "  ★ 这 8 项正是 dormant_check 的 N/A 夹具,此前**完全不可见**",
        "★ 先红后绿(C-4):T37 判定层自身的变异用例 —— 基线 pass → 冻结 15 条"
        "  判据归因(30%)后 fail。证明 T37 不是空规(并非只是把缺口搬了个位置)",
        "纳入 build:ablation.py 已在 STAGES 8.5/8.6,T37 随之进入构建流程",
    ],
    "2.22": [
        "★ 用户选择 A:逐个映射剩余归因(继续诚实化) —— 不是新增判据,是把"
        "「哪条判据在干活」从**不可回答**变成**可回答**",
        "逐个映射 23 条判定项的显式归因(非推断):",
        "  · 分支10 三条判据共享分支 → 逐条判:T06(竞争风险3)/B01A(EPV3)/B02S(可行性4)",
        "  · 分支15 中文类别名「空间」→ T19(_ITEM_CRI_BARE 只认 A-Z 开头,此前落兜底)",
        "  · 分支16/21 数值反例 → T21/T13b/T33/T34(此前被记为四条判据共享)",
        "区分「单判据分支的分支级归因」(branch_single,无歧义 → 计精确)与"
        "「多判据分支的分支级归因」(branch,真粗粒) —— 前者曾致 9 条被误标粗粒",
        "新增 GLOBAL 标签:5 条跨判据全局自检项(如「夹具全部按预期拦截」)",
        "  · 不专属任何单条判据,硬塞会**虚增该判据贡献**→ 单列为非判据",
        "★ 修覆盖率口径 bug:分子含写作层42+导出层10,分母只有主run222 → 110.8%",
        "  (不可能值)。三源同口径后 274/274 = 100%",
        "新增 A-6 归因稀释检测(GLOBAL 占比 ≥10% 即报警)",
        "★ 修流程缺口:写作层/导出层守卫**不在构建流程里**,52 项判定是手工产物",
        "  → 固定为 build STAGES 2.5/2.6,与主验证同等受控",
        "消融与自测固定为 STAGES 8.5/8.6(此前靠手工跑)",
        "消融自测补 C-2/C-3 用例;C-2 初版只抽 1 条(2%<20%阈值)未越线,用例设计错",
        "结果:粗粒 13→0,休眠 0,direct 归因 274/274(100%),骨架 50/50",
        "★ 自伤事故:为给构建提供合规样例,把 manuscript_fixed.md 覆盖到"
        "  demo/manuscript_demo.md —— 而后者是变异测试的**注入锚点源**",
        "  → 11 个 WP 用例报「锚点缺失」(55/66)。已从 v2.20 zip 恢复。",
        "  教训:合规样例与变异样例必须**分开存放**,不可共用一个路径。",
        "  现:demo/manuscript_demo.md(变异锚点) / manuscript_fixed.md(构建样例)",
    ],

}


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


# ══════════════════════════════════════════════════════════════════
# STAGES：定义顺序 = 执行顺序
# ══════════════════════════════════════════════════════════════════
# 每个元素: (step_no, 名称, 可调用对象)
# 顺序是本文件存在的理由，重排即改变语义，请勿随意调整。
# ══════════════════════════════════════════════════════════════════

STAGES = [
    # v2.8 step 0:版本权威源。MANIFEST 在第 11 步才写,拿它当基准必然滞后
    #   (G-12.ver 刚因此 FAIL: banner 已 v2.8 而 MANIFEST 仍 v2.7)。
    #   版本是 build 的入参,从一开始就知道 —— 立刻落盘,全员从它派生。
    # ★ v2.10:内嵌脚本由代码同步(原手工嵌入 → 改了脚本忘记重嵌则 G-1 FAIL)
    (0, "同步内嵌脚本(框架正文附录)",
     lambda: _step_sync_scripts()),
    (1, "主验证 verify_all.py",
     lambda: run("主验证", [sys.executable, "verify_all.py"], cwd=SCRIPTS)),

    # ★ v2.18 修顺序 bug:本步原为 (0.5),排在 verify_all **之前** ——
    #   但它同步的是"主验证 N/N·分支数"这类数字,来源是 report.json,
    #   而 report.json 恰由步骤 (1) 生成 → 同步用的永远是**上一轮**台账。
    #   平时判据数不变看不出来;本次判据 35→40 且 report.json 曾被
    #   `verify_all --only 17` 污染(只剩 20/20),G-2.1/G-2.2/G-11.2/
    #   G-11.3 五项同时 FAIL 才暴露。故移到 verify_all 之后。
    (1.5, "同步派生数字(主验证N/N·分支·判据条数)",
     lambda: _step_sync_derived_numbers()),

    # ★ v2.6 首次运行抓到的真 bug：figdir 原为相对路径 "figures/demo"，
    #   而 cwd=SCRIPTS → 实际指向 scripts/figures/demo（不存在）
    #   → 少 1 项判定且误报失败(68/69)。
    #   手动测试时 cwd=crossval，路径恰好正确，把这个 bug 藏住了 —— 正说明
    #   单一入口的价值：它用**统一的** cwd 跑，暴露被手动测试掩盖的路径依赖。
    #   修法：脚本与 figdir 一律用绝对路径，cwd 不再影响结果。
    (2, "排版检查 layout_check.py",
     lambda: run("排版",
                 [sys.executable, os.path.join(SCRIPTS, "layout_check.py"),
                  "--figdir", os.path.join(CROSSVAL, "figures", "demo")], cwd=CROSSVAL)),

    # ★ v2.22:写作层/导出层守卫此前**不在构建流程里** —— results/ 下的
    #   writing_report.json 与 export_report.json 是手工产物,每次构建
    #   不会重新生成,只会被消融器当作既成事实读进来。
    #   这与"改了代码忘重跑"同族,只是发生在**产物层**:构建号称全绿,
    #   而其中 52 项判定(写作42+导出10)可能停在任意旧状态。
    #   固定为构建步骤后,它们与主验证同等受控。
    (2.5, "写作层守卫 writing_guard.py",
     lambda: run("写作守卫",
                 [sys.executable, "writing_guard.py", "--doc",
                  os.path.join(CROSSVAL, "demo", "manuscript_fixed.md"),
                  "--p1", _p1_from_manuscript(),
                  # ★ v2.25：必须显式提供 skill 输出。WP-3.1 已硬化为
                  #   "未提供 --skill → FAIL"，故构建流程须真的给一份，
                  #   否则该判据永远无法执行（原来判 N/A = 默认放行）。
                  "--skill", os.path.join(CROSSVAL, "demo",
                                          "research_survey_skill_demo.json"),
                  "--out", os.path.join(RESULTS, "writing_report.json")],
                 cwd=SCRIPTS)),

    (2.6, "导出层守卫 export_guard.py",
     lambda: run("导出守卫",
                 [sys.executable, "export_guard.py",
                  "--a", os.path.join(CROSSVAL, "demo", "export", "docA.txt"),
                  "--b", os.path.join(CROSSVAL, "demo", "export", "docB.txt"),
                  "--p", os.path.join(CROSSVAL, "demo", "export", "docP.txt"),
                  "--out", os.path.join(RESULTS, "export_report.json")],
                 cwd=SCRIPTS)),

    (3, "单元测试 pytest",
     lambda: _run_pytest()),

    (4, "Handoff 链守卫",
     lambda: run("链守卫", [sys.executable, os.path.join(HANDOFF, "scripts", "handoff_guard.py")])),

    # v2.6 新增：平台环境快照。跨平台实测要回答"同一份代码在不同环境是否一致"，
    # 但若结果不同，必须先知道环境差在哪（numpy 版本？中文字体？FS 大小写？），
    # 否则只能靠猜。本步把环境快照化，供 compare_platforms.py 归因。
    (4.5, "平台环境快照 platform_check.py",
     lambda: run("平台快照", [sys.executable, os.path.join(SCRIPTS, "platform_check.py")])),

    # ★ 关键：版本化必须在守卫之前。
    #   G-10.1 检查「版本化副本 == 源文档」，若副本是上一轮的，必然 FAIL。
    (5, "版本化（框架 + 合集）",
     lambda: step_version(only=["框架_独立审核包_v1.md", "四角度审核报告_合集.md"])),

    # ★ v2.15:附录由 gen_appendix 在第 9 步生成(需含守卫 stdout),
    #   但 G-11.1 在第 6 步就要读附录里的判据条数 —— 永远滞后一轮。
    #   解法:守卫前**预生成**一次附录(此时 stdout 段为上一轮,但判据段已是最新);
    #   第 9 步再生成最终版。判据条数这类"静态内容"由预跑保证不滞后。
    (5.5, "附录预生成(供守卫读判据条数)",
     lambda: run("gen_appendix(预)", [sys.executable, "gen_appendix.py"],
                 cwd=SCRIPTS, critical=False)),

    (6, "一致性守卫 consistency_guard",
     lambda: run("一致性守卫",
                 [sys.executable, "consistency_guard.py", "--doc",
                  os.path.join(WS, "框架_独立审核包_v1.md")], cwd=SCRIPTS)),

    (7, "审核报告守卫 report_guard",
     lambda: run("报告守卫",
                 [sys.executable, "report_guard.py", "--doc",
                  os.path.join(WS, "四角度审核报告_合集.md")], cwd=SCRIPTS)),

    (8, "变异测试 guard_selftest（证明守卫非空规）",
     lambda: run("变异测试", [sys.executable, "guard_selftest.py"], cwd=SCRIPTS)),

    # ★★★ 核心约束：gen_appendix 必须是倒数第二步 ★★★
    #   它读步骤 6/7/8 的 stdout 写入附录 §G。若把它提前，
    #   附录里的 stdout 就是过期快照 → 汇总与原始对不上（形态③）。
    # ★ v2.22:L2 判据消融。回答"50 条判据里哪几条在干活"。
    #   必须在写作层(2.5)/导出层(2.6)之后 —— 消融要读它们的 criteria_dist;
    #   必须在 gen_appendix(9)之前 —— 附录要收录消融结论。
    #   同时跑 --self-test:证明消融器自身不是空规(变异用例 C-1~C-3)。
    (8.5, "L2 判据消融 ablation.py",
     lambda: run("判据消融", [sys.executable, "ablation.py"], cwd=SCRIPTS)),

    (8.6, "消融器自测(--self-test:C-1~C-3 必须全部生效)",
     lambda: run("消融自测", [sys.executable, "ablation.py", "--self-test"],
                 cwd=SCRIPTS)),

    (9, "生成附录 gen_appendix.py（必须最后）",
     lambda: run("gen_appendix", [sys.executable, "gen_appendix.py",
                                  "--version", VER], cwd=SCRIPTS)),

    # 附录源文档刚被重写，副本必须在此之后重新复制
    (10, "版本化（附录，gen_appendix 之后）",
     lambda: step_version(only=["附录_原始输出.md"])),

    (11, "更新 MANIFEST（guards 派生自 guard_results.json）",
     lambda: _step_manifest()),

    (12, "合并为单文件 merge_delivery.py",
     lambda: run("合并交付", [sys.executable, "merge_delivery.py", VER, DATE], cwd=WS)),

    # ★ v2.25 新增：交付包内容清单。必须在 merge_delivery 之后（单文件交付
    #   已在其中）、打包之前（清单要被包进去）。原 STAGES 到这里直接打包，
    #   于是 v24_fixes 声称的 ZIP_CONTENTS.md 从未生成 —— 云端 CP-2 死锁。
    (12.5, "生成 ZIP_CONTENTS.md / .json（交付包逐文件清单）",
     lambda: _step_zip_contents()),

    (13, "打包 zip（UTF-8 标志位）",
     lambda: _step_zip()),
]



def _p1_from_manuscript():
    """从合规样例稿**派生** P1（摘要首句），不硬编码、不兜底猜值。

    ★ v2.25：原构建流程**根本不传 --p1** → WP-CORE / WP-2.1 / WP-6.1 三项判
      N/A，而 N/A 不算失败 → "写作层里 4 项从未执行"被汇总掩盖。与 WP-3.1
      同族：**不提供输入 = 检查自动通过**。故改为由脚本从稿件派生（稿件一改
      自动跟随），并在 derivation 失败时硬失败。
    """
    p = os.path.join(CROSSVAL, "demo", "manuscript_fixed.md")
    if not os.path.isfile(p):
        raise SystemExit("[build] 合规样例稿不存在: %s" % p)
    t = open(p, encoding="utf-8").read()
    m = re.search(r"##\s*摘要\s*\n+(.+)", t)
    if not m:
        raise SystemExit("[build] 无法从 manuscript_fixed.md 派生 P1（缺 ## 摘要 节）"
                         " —— 不兜底猜值")
    return re.split(r"(?<=。)", m.group(1).strip())[0]


def _run_pytest():
    """跑 pytest 并落盘结果,供 MANIFEST.verification 派生。

    v2.10:原 MANIFEST 里 pytest 是硬编码 "30 passed"。与 mutation "6/6"
    同期发现 —— 汇总不该有手工数字。
    """
    _ensure_pytest()
    r = subprocess.run([sys.executable, "-m", "pytest", "tests/", "-q"],
                       cwd=CROSSVAL, capture_output=True, encoding="utf-8",
                       errors="replace", env=_child_env())
    sys.stdout.write(r.stdout)
    # 解析 "N passed"
    import re as _re
    _m = _re.search(r"(\d+) passed", r.stdout)
    _n = int(_m.group(1)) if _m else 0
    try:
        json.dump({"passed": _n, "rc": r.returncode},
                  open(os.path.join(RESULTS, "pytest_results.json"), "w"),
                  indent=2)
    except Exception:
        pass
    return r.returncode


def _step_sync_scripts():
    """用 scripts/ 下的实际脚本,重建框架正文里的内嵌附录。

    ★ v2.10:G-1 要求"内嵌脚本 == 实际脚本",但内嵌块一直是**手工嵌入**的。
      一旦改了 verify_all.py / layout_check.py 而忘记重新嵌入 → G-1 FAIL,
      且失败原因只是"忘了同步",与代码正确性无关。
      这是"手工同步易漏"的又一处 —— 解法同 build.py 本身:由代码保证。
    """
    import re as _re
    doc = os.path.join(WS, "框架_独立审核包_v1.md")
    if not os.path.isfile(doc):
        log("    ✗ 框架正文不存在"); sys.exit(1)
    s = open(doc, encoding="utf-8").read()
    # 与 consistency_guard G-1 相同的识别方式:四反引号 python 块 + key
    PAIRS = [("verify_all.py", "def branch1_family"),
             ("layout_check.py", "def check_claim")]
    n = 0
    for fname, key in PAIRS:
        real = os.path.join(SCRIPTS, fname)
        if not os.path.isfile(real):
            log("    ✗ 实际脚本缺失: %s" % fname); sys.exit(1)
        body = open(real, encoding="utf-8").read().rstrip("\n")
        # ★ v2.16:原正则写死四反引号,但动态围栏后源文档内嵌块已升为
        #   五/六反引号 → 匹配不到 → "未找到内嵌块" → 静默跳过 → G-1.1 FAIL。
        #   改为 N>=4 且开闭一致(反向引用),与实际围栏无关。
        _pat = _re.compile(r"(`{4,})python\n(.*?)\n\1", _re.S)
        # ★ v2.18 修静默失败:原用 str.replace(拼接围栏+旧内容)定位,
        #   一旦原文块首尾有额外空白/换行差异就**匹配不上**,
        #   而 str.replace 找不到时**不报错也不替换** → 内嵌停留在旧版,
        #   G-1.1 持续 FAIL 却看不出哪一步失手(实测:内嵌 1439 行 vs
        #   实际 1446 行,差异首行正是新增的 import conclusion_branch)。
        #   改为用 match.span() 切片替换,并在替换后**回读校验**。
        _done = False
        for _m in _pat.finditer(s):
            if key not in _m.group(2):
                continue
            _fence = _m.group(1)
            if _m.group(2).rstrip("\n") == body:
                _done = True               # 已一致
                break
            s = (s[:_m.start()] + _fence + "python\n" + body + "\n" + _fence
                 + s[_m.end():])
            n += 1
            _done = True
            break
        if not _done:
            log("    ⚠ 未找到 %s 的内嵌块(key=%s),跳过" % (fname, key))
            continue
        # 回读校验:替换后重新解析,确认该块确实等于实际脚本
        _chk = [(_m.group(2).rstrip("\n") == body)
                for _m in _pat.finditer(s) if key in _m.group(2)]
        if not _chk or not any(_chk):
            log("    ✗ %s 同步后校验失败:内嵌仍与实际不一致" % fname)
            sys.exit(1)
    if n:
        open(doc, "w", encoding="utf-8", newline="\n").write(s)
    log("    ✓ 内嵌脚本同步: 更新 %d 处, %d 处已一致"
        % (n, len(PAIRS) - n))
    return 0


def _step_sync_derived_numbers():
    """把"派生数字"从台账同步进文档(框架正文 + 合集)。

    ★ v2.16:判据 30→35、主验证 101→116、分支 15→16 后,文档里的旧数字
      无人同步 → G-2.1/G-2.2/G-11.2/G-11.3 全 FAIL。
      根因与"手工填 MANIFEST"同族:**派生数字被手工留在文档里**。
      解法同:由代码从 report.json / criteria.yaml 派生,文档只作呈现。
      用通用正则(不硬编码旧值),下次数值再变仍自动同步。
    """
    import re as _re, json as _json, yaml as _yaml
    rp = os.path.join(RESULTS, "report.json")
    cy = os.path.join(SCRIPTS, "..", "schema", "criteria.yaml")
    if not os.path.isfile(rp):
        log("    ✗ report.json 缺失"); return 1
    d = _json.load(open(rp, encoding="utf-8"))
    sm = d.get("summary", {})
    total = sm.get("total") or (sm.get("n_pass", 0) + sm.get("n_fail", 0))
    npass = sm.get("n_pass", 0)
    nbr = sm.get("branches", 0)
    ncrit = len(_yaml.safe_load(open(cy, encoding="utf-8")).get("criteria", []))
    log("    ↳ 派生值: 主验证 %s/%s, 分支 %s, 判据 %s 条"
        % (npass, total, nbr, ncrit))

    targets = [os.path.join(WS, "框架_独立审核包_v1.md"),
               os.path.join(WS, "四角度审核报告_合集.md")]
    # (正则, 替换模板, 说明)
    RULES = [
        # ★ v2.16:合集里 N/N 被 ** 包裹("**101/101** 通过"),原正则未考虑
        #   → 只同步了框架、未同步合集 → R-1/R-8 FAIL。改为可选 (**)。
        (r"(\*\*)?(\d+)/(\d+)(\*\*)?\s*通过[,，]\s*覆盖\s*(\d+)\s*个分支",
         lambda m: "%s%s/%s%s 通过,覆盖 %s 个分支"
         % (m.group(1) or "", npass, total, m.group(4) or "", nbr), "主验证N/N+分支"),
        (r"(\*\*)?(\d+)/(\d+)(\*\*)?\s*通过,\s*(\d+)\s*个分支",
         lambda m: "%s%s/%s%s 通过,%s 个分支"
         % (m.group(1) or "", npass, total, m.group(4) or "", nbr), "主验证N/N+分支(紧凑)"),
        (r"判据 YAML\s*\|\s*\*\*(\d+)\*\*\s*条",
         lambda m: "判据 YAML | **%s** 条" % ncrit, "合集判据条数"),
        (r"判据 YAML\s*\*\*(\d+)\*\*\s*条",
         lambda m: "判据 YAML **%s** 条" % ncrit, "框架判据条数"),
        (r"(\d+)\s*条判据五元组",
         lambda m: "%s 条判据五元组" % ncrit, "判据五元组条数"),
        # ★ v2.20:框架附录 A 头部"判定项 101 项 / 15 分支"长期未同步
        #   (实际已 201/19)。与上面同族 —— 派生数字留在文档里必然滞后。
        (r"判定项\s*(\d+)\s*项\s*/\s*(\d+)\s*分支",
         lambda m: "判定项 %s 项 / %s 分支" % (total, nbr), "附录A判定项/分支"),
    ]
    nchg = 0
    for t in targets:
        if not os.path.isfile(t):
            continue
        txt = open(t, encoding="utf-8").read()
        orig = txt
        for pat, rep, label in RULES:
            def _r(m, _rep=rep, _lb=label):
                new = _rep(m)
                return new if new != m.group(0) else m.group(0)
            txt2, cnt = _re.subn(pat, _r, txt)
            if cnt:
                log("      ↳ %s: %s 处 → %s" % (
                    os.path.basename(t), label, cnt))
            txt = txt2
            nchg += cnt
        if txt != orig:
            open(t, "w", encoding="utf-8", newline="\n").write(txt)
    log("    ✓ 派生数字同步: 更新 %d 处" % nchg)

    # ★★ v2.25：把**构建期**的 run_id / input_hash 固化进 build_version.json。
    #   它是 G-12 的权威锚（文档 banner 与它比对）。
    #   为什么不用 report.json 直接比：run_id 每次运行必变（框架 §5 自己声明），
    #   而云端按 T4 重跑 verify_all 会刷新 report.json —— 拿它当基准，
    #   守卫**必然**FAIL（v2.24 实测：4 项 FAIL，与平台、与操作者都无关）。
    #   build_version.json 只在构建时写，重跑主验证不会动它，因此：
    #     · 构建期：文档 == build_version == report.json（三者一致）
    #     · 用户重跑主验证后：文档仍 == build_version（守卫正确保持绿色）
    #     · 有人手改 banner：文档 != build_version → **抓到**（先红后绿仍成立）
    _R = _json.load(open(rp, encoding="utf-8"))["run_metadata"]
    _bvp = os.path.join(RESULTS, "build_version.json")
    _bv = (_json.load(open(_bvp, encoding="utf-8"))
           if os.path.isfile(_bvp) else {})
    _bv.update({"run_id": _R.get("run_id"), "input_hash": _R.get("input_hash")})
    _json.dump(_bv, open(_bvp, "w", encoding="utf-8", newline="\n"),
               ensure_ascii=False, indent=2)
    log("      ↳ build_version.json 固化 run_id=%s… input_hash=%s（G-12 权威锚）"
        % (str(_R.get("run_id"))[:16], _R.get("input_hash")))
    return 0


def _derived_layout():
    """排版判定项数 —— 从 layout_report.json 派生。"""
    try:
        p = os.path.join(RESULTS, "layout_report.json")
        return len(json.load(open(p, encoding="utf-8"))["checks"])
    except Exception as e:
        log("    ✗ layout_report.json 不可读: %s" % e)
        sys.exit(1)


def _derived_pytest():
    """pytest 结果 —— 从 results/pytest_results.json 派生(step 3 落盘)。"""
    try:
        p = os.path.join(RESULTS, "pytest_results.json")
        d = json.load(open(p, encoding="utf-8"))
        return "%d passed" % d["passed"]
    except Exception:
        return None   # 非阻塞:pytest 失败会由 step 3 中断


def _derived_mutation():
    """变异测试结果 —— 从 results/mutation_results.json 派生(v2.10 新增落盘)。"""
    try:
        p = os.path.join(RESULTS, "mutation_results.json")
        d = json.load(open(p, encoding="utf-8"))
        return "%d/%d" % (d["n_pass"], d["total"])
    except Exception:
        return None   # 非阻塞:变异失败会由 step 8 中断


def _step_manifest():
    """更新 MANIFEST.json。

    铁律：guards 字段必须派生自 results/guard_results.json（后者由
    gen_appendix 从 stdout 解析），禁止手工填。
    """
    gp = os.path.join(RESULTS, "guard_results.json")
    rp = os.path.join(RESULTS, "report.json")
    if not os.path.isfile(gp):
        log("    ✗ guard_results.json 不存在 —— gen_appendix 未跑或未落盘")
        sys.exit(1)
    G = json.load(open(gp, encoding="utf-8"))
    R = json.load(open(rp, encoding="utf-8"))
    mp = os.path.join(WS, "MANIFEST.json")
    m = json.load(open(mp, encoding="utf-8")) if os.path.isfile(mp) else {}

    m.update({
        "version": VER,
        "generated_at": datetime.now(CST).isoformat(),
        "run_id": R["run_metadata"]["run_id"],
        # ★ v2.10:原 layout/pytest/mutation 均为**硬编码**,
        #   且 mutation "6/6" 在变异用例增至 12 后已过期 —— 汇总撒谎。
        #   改为全部从结果文件派生;读不到就报错,不回落硬编码。
        "verification": {
            "n_pass": R["summary"]["n_pass"],
            "n_total": R["summary"]["total"],
            "branches": R["summary"]["branches"],
            "layout": _derived_layout(),
            "pytest": _derived_pytest(),
            "mutation": _derived_mutation(),
        },
        # ★ 派生，不手工填
        "guards": {
            "consistency_guard": G.get("G.1"),
            "report_guard": G.get("G.2"),
            "handoff_guard": G.get("G.3"),
        },
        "guards_source": "results/guard_results.json ← gen_appendix 从 stdout 解析",
        # v2.7 补齐:原只登记 VERSIONED 三份,作图规范/跨平台指导/交付规则/
        #   build.py/merge_delivery.py 的哈希无处可查,审核方无法从 MANIFEST
        #   单点确认。改为登记全部交付文件(含脚本)。
        "files": dict(
            {
                dst: {"sha256": sha(os.path.join(WS, dst)),
                      "bytes": os.path.getsize(os.path.join(WS, dst))}
                for dst in VERSIONED.values()
            },
            **{
                n: {"sha256": sha(os.path.join(WS, n)),
                      "bytes": os.path.getsize(os.path.join(WS, n))}
                for n in MANIFEST_EXTRA if os.path.isfile(os.path.join(WS, n))
            },
        ),
    })
    # ★ v2.10:由代码写入本轮 fixes(原手工维护 → v2.8/v2.9 缺失)
    _fk = "v%s_fixes" % VER.replace(".", "")
    if VER in FIXES_BY_VERSION:
        m[_fk] = FIXES_BY_VERSION[VER]
    elif _fk not in m:
        log("    ⚠ 未定义 v%s 的 fixes,且 MANIFEST 无 %s —— G-6.0 将 FAIL"
            % (VER, _fk))
    json.dump(m, open(mp, "w", encoding="utf-8", newline="\n"),
              indent=2, ensure_ascii=False)
    log("    ✓ MANIFEST v%s | run_id %s…" % (VER, R["run_metadata"]["run_id"][:16]))
    log("      verification(派生): %s" % m["verification"])
    log("      guards(派生): %s" % m["guards"])


def _step_zip():
    """打包。zipfile 需置 flag_bits |= 0x800，否则 Win11 解压中文名乱码。

    ★ v2.25 两处修改：
      ① 由 `_ship_list()` **单一来源**驱动（原为手工复制清单 + 手工 os.walk，
         与 ZIP_CONTENTS 两处维护 → 必然不同步）；
      ② STAGE 原为硬编码 "/tmp/stage_build"（Windows 上不存在的路径），
         改用 tempfile.gettempdir()。
    """
    import zipfile
    OUT = os.path.join(WS, "框架交叉验证包_v%s_%s.zip" % (VER, DATE))
    if os.path.exists(OUT):
        os.remove(OUT)
    STAGE = os.path.join(tempfile.gettempdir(), "stage_build_%s_%s" % (VER, DATE))
    if os.path.exists(STAGE):
        shutil.rmtree(STAGE)
    os.makedirs(STAGE)

    for rel in _ship_list():
        src = os.path.join(WS, rel.replace("/", os.sep))
        if not os.path.isfile(src):
            # 不静默跳过：清单说有、实际没有 = 交付不完整（v2.24 就是这么丢掉
            # ZIP_CONTENTS.md 的）。
            raise SystemExit("[build] 待打包文件不存在: %s —— 不静默跳过" % rel)
        dst = os.path.join(STAGE, rel.replace("/", os.sep))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy(src, dst)

    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
        for root, _, fs in os.walk(STAGE):
            for f in fs:
                fp = os.path.join(root, f)
                rel = os.path.relpath(fp, STAGE).replace(os.sep, "/")
                zi = zipfile.ZipInfo(rel)
                zi.flag_bits |= 0x800          # ★ UTF-8 文件名标志位
                zi.compress_type = zipfile.ZIP_DEFLATED
                z.writestr(zi, open(fp, "rb").read())
    log("    ✓ %s (%d 文件, %d B)" % (
        os.path.basename(OUT), len(zipfile.ZipFile(OUT).namelist()), os.path.getsize(OUT)))


# ══════════════════════════════════════════════════════════════════
# 后置校验：证明"顺序真的按预期执行了"
# ══════════════════════════════════════════════════════════════════
def postcheck():
    """流程层硬自检。

    解析层已有硬自检（stdout 含 [FAIL] 却解析为 N/N 相等 → 中断），
    本函数补的是**流程层**：证明 gen_appendix 确实在守卫之后跑。
    这是 v2.5 失手的地方 —— 那次解析层没撒谎，是流程顺序错了。
    """
    log("\n" + "=" * 70)
    log("  后置校验（流程层硬自检）")
    log("=" * 70)
    ok = True

    # P-1 附录 mtime 必须晚于所有守卫输入产物
    app = os.path.join(WS, "附录_原始输出.md")
    app_m = os.path.getmtime(app)
    for f in ["report.json", "guard_results.json", "layout_report.json"]:
        fp = os.path.join(RESULTS, f)
        if not os.path.isfile(fp):
            continue
        m = os.path.getmtime(fp)
        c = app_m >= m
        ok &= c
        log("  %s P-1 附录晚于 %-22s  %s" % (
            "✓" if c else "✗", f,
            "OK" if c else "附录是旧快照！gen_appendix 没最后跑"))

    # P-2 MANIFEST.guards == guard_results.json（派生一致）
    G = json.load(open(os.path.join(RESULTS, "guard_results.json"), encoding="utf-8"))
    M = json.load(open(os.path.join(WS, "MANIFEST.json"), encoding="utf-8"))
    for k, key in [("G.1", "consistency_guard"), ("G.2", "report_guard"), ("G.3", "handoff_guard")]:
        c = (G.get(k) == M["guards"].get(key))
        ok &= c
        log("  %s P-2 %-18s stdout=%-8s MANIFEST=%-8s" % (
            "✓" if c else "✗", key, G.get(k), M["guards"].get(key)))

    # P-3 版本化副本 sha256 == MANIFEST
    for dst, meta in M["files"].items():
        fp = os.path.join(WS, dst)
        if not os.path.isfile(fp):
            log("  ✗ P-3 缺副本 %s" % dst)
            ok = False
            continue
        c = (sha(fp) == meta["sha256"])
        ok &= c
        log("  %s P-3 %-40s %s…" % ("✓" if c else "✗", dst[:40], sha(fp)[:16]))

    # P-4 附录中真实 [FAIL] 行数为 0（排除源码里的 print 字符串）
    txt = open(app, encoding="utf-8").read()
    real_fail = [l for l in txt.split("\n") if "[FAIL]" in l and 'print(f"' not in l]
    c = len(real_fail) == 0
    ok &= c
    log("  %s P-4 附录真实 [FAIL] 行 = %d" % ("✓" if c else "✗", len(real_fail)))

    # P-7 跨平台执行指导：两个平台的步骤必须一一对应
    #   §9 里向执行者承诺："若你发现 §3 与 §4 步骤数量不一致，请报告"。
    #   既然承诺了，就让代码来保证 —— 否则承诺本身也是纸面。
    xdoc = os.path.join(WS, "跨平台执行指导.md")
    if os.path.isfile(xdoc):
        t = open(xdoc, encoding="utf-8").read()
        # 抓取 §3（Windows）与 §4（Linux）块内的 ⓪①②...⑦ 步骤标记
        def _steps(section):
            i = t.find(section)
            if i < 0:
                return []
            # ⚠ 边界坑(首次运行抓到):截到下一个 "###" 会漏掉圈码 ——
            #   圈码在 ### 3.3 执行 里,而第一个 ### 是 3.1,
            #   于是 blk 只到 3.1、抓到 0 个,误报"不同步"。
            #   必须截到下一个**二级**标题 (## ),而非三级标题。
            j = t.find("\n## ", i + 10)
            blk = t[i:j] if j > 0 else t[i:]
            return [c for c in "⓪①②③④⑤⑥⑦" if c in blk]
        w_step, l_step = _steps("## 三、Windows"), _steps("## 四、Linux")
        c = (len(w_step) == len(l_step) == 8)
        ok &= c
        log("  %s P-7 跨平台指导双平台步骤数 Win=%d Linux=%d %s" % (
            "✓" if c else "✗", len(w_step), len(l_step),
            "(应为 8：⓪~⑦)" if c else "—— 不同步！"))
    else:
        log("  ⚠ P-7 跨平台执行指导.md 不存在，跳过")

    # P-6 源文档 vs 版本化副本（去 banner）必须一致
    #   补 G-10.1 的盲区：G-10.1 只在 consistency_guard 里跑，
    #   若有人改了源文档却**没重跑守卫**，G-10.1 根本不会执行。
    #   --check 模式正是为这种"改了没构建"的场景设计的，
    #   所以这里独立再查一次 —— 让 P-6 在两种入口下都生效。
    def _strip(t):
        return "\n".join(l for l in t.split("\n")
                         if "版本 v" not in l and "run_id" not in l)
    for src, dst in VERSIONED.items():
        sp, dp = os.path.join(WS, src), os.path.join(WS, dst)
        if not (os.path.isfile(sp) and os.path.isfile(dp)):
            continue
        c = _strip(open(sp, encoding="utf-8").read()) == _strip(open(dp, encoding="utf-8").read())
        ok &= c
        log("  %s P-6 源≈副本 %-34s %s" % (
            "✓" if c else "✗", src[:34], "一致" if c else "源文档已改动但未重建！"))

    # P-5 zip 内 sha 与 MANIFEST 一致
    zp = os.path.join(WS, "框架交叉验证包_v%s_%s.zip" % (VER, DATE))
    if os.path.isfile(zp):
        import zipfile
        z = zipfile.ZipFile(zp)
        bad = [n for n in z.namelist()
               if n.endswith((".md", ".py", ".yaml", ".json"))
               and _bad_utf8(z, n)]
        c = len(bad) == 0
        ok &= c
        log("  %s P-5 zip 内文件 UTF-8 可解码 (%d 个异常)" % ("✓" if c else "✗", len(bad)))
        if bad:
            log("      异常: %s" % bad[:3])

    # ══ P-8 交付布局自检（★ v2.25 新增 —— 本次修复里最关键的一条）══════════
    #   起因：v2.24 交付包**在开发机全绿、在交付包内全红** —— 3 个脚本的回退路径
    #   指向只有开发机才有的未版本化文件名（框架_独立审核包_v1.md 等），而 zip 内
    #   只有版本化副本 → consistency_guard 63/69(6 FAIL)、report_guard 9/10、
    #   guard_selftest 直接崩溃（0/66）。
    #   P-1~P-7 **全部只看开发机现场**，所以一条都没抓到；开发侧"全绿"依赖了
    #   特定环境特征 —— 这正是框架设计跨平台验证要找的东西，却在构建期无检查。
    #   本检查：把 zip 解到临时目录，在**交付布局**里跑三道守卫 + 变异测试，
    #   全绿才算构建成功。
    zp8 = os.path.join(WS, "框架交叉验证包_v%s_%s.zip" % (VER, DATE))
    if os.path.isfile(zp8):
        import zipfile as _zf8
        import tempfile as _tf8
        import shutil as _sh8
        _pkg = os.path.join(_tf8.gettempdir(),
                            "pkg_selfcheck_%s_%s" % (VER, DATE))
        if os.path.exists(_pkg):
            _sh8.rmtree(_pkg, ignore_errors=True)
        os.makedirs(_pkg)
        _zf8.ZipFile(zp8).extractall(_pkg)
        _sc = os.path.join(_pkg, "crossval", "scripts")
        _env8 = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
        for _nm, _cmd in [
            ("一致性守卫(交付布局)",
             [sys.executable, "consistency_guard.py", "--doc",
              os.path.join(_pkg, "框架_独立审核包_v%s_%s.md" % (VER, DATE))]),
            ("报告守卫(交付布局)",
             [sys.executable, "report_guard.py", "--doc",
              os.path.join(_pkg, "四角度审核报告_合集_v%s_%s.md" % (VER, DATE))]),
            ("变异测试(交付布局)",
             [sys.executable, "guard_selftest.py"]),
        ]:
            _r8 = subprocess.run(_cmd, cwd=_sc, capture_output=True,
                                 encoding="utf-8", errors="replace", env=_env8)
            _c = (_r8.returncode == 0)
            ok &= _c
            _tl = [l.strip() for l in (_r8.stdout or "").split("\n")
                   if "通过" in l or "[FAIL]" in l][-2:]
            log("  %s P-8 %-20s rc=%d %s" % (
                "✓" if _c else "✗", _nm, _r8.returncode,
                "| " + " / ".join(_tl) if _tl else ""))
        _sh8.rmtree(_pkg, ignore_errors=True)
    else:
        log("  ✗ P-8 zip 不存在，无法做交付布局自检")
        ok = False

    log("\n  %s" % ("✓ 后置校验全部通过 —— 顺序由代码保证" if ok else "✗ 后置校验失败"))
    return ok


def _bad_utf8(z, n):
    try:
        z.read(n).decode("utf-8")
        return False
    except Exception:
        return True


def main():
    log("=" * 70)
    log("  交付构建 build.py · v%s · %s" % (VER, DATE))
    log("  顺序由代码强制（STAGES 定义顺序 = 执行顺序），任一步失败即中断")
    log("=" * 70)

    if CHECK_ONLY:
        return 0 if postcheck() else 1

    if _start > 1:
        log("\n  ⚠ --from %d：从第 %d 步开始。顺序保证部分失效，仅调试用。" % (_start, _start))

    # ★ v2.8:版本权威源必须在遍历前写 —— 放在 STAGES 里会被 --from 跳过,
    #   且它必须在任何守卫之前存在,否则 G-12 又拿滞后的 MANIFEST 当基准。
    _bv = os.path.join(CROSSVAL, "results", "build_version.json")
    json.dump({"version": VER, "date": DATE, "built_at": _now()},
              open(_bv, "w", encoding="utf-8", newline="\n"),
              ensure_ascii=False, indent=2)
    log("  ✓ 版本权威源: %s (v%s)" % (_bv, VER))

    # ★ v2.11 修**同版本重复构建死锁**:
    #   G-6.0 要求"MANIFEST 含 vXX_fixes",但 MANIFEST 在第 11 步才完整写入,
    #   而守卫第 6 步就要读 —— 首轮构建时 MANIFEST 版本还是旧版,G-6 走
    #   "待写入"分支侥幸 PASS;**同版本第二次构建**时 MANIFEST 版本已等于
    #   当前版本 → 走 else 分支 → 找不到 vXX_fixes → FAIL 且无法自愈。
    #   解法同 build_version.json:在遍历前把 fixes 预置进 MANIFEST。
    _mp0 = os.path.join(WS, "MANIFEST.json")
    if VER not in FIXES_BY_VERSION:
        raise SystemExit(
            "build.py 未定义 v" + VER + " 的 FIXES_BY_VERSION 条目 —— G-6.0 将 FAIL;"
            " 请在 FIXES_BY_VERSION 补上该版本后重新构建"
        )
    if True:
        try:
            _m0 = json.load(open(_mp0, encoding="utf-8")) \
                if os.path.isfile(_mp0) else {}
        except Exception:
            _m0 = {}
        _fk0 = "v%s_fixes" % VER.replace(".", "")
        _m0["version"] = VER
        _m0[_fk0] = FIXES_BY_VERSION[VER]
        json.dump(_m0, open(_mp0, "w", encoding="utf-8", newline="\n"),
                  indent=2, ensure_ascii=False)
        log("  ✓ MANIFEST 预置 %s (%d 条)—— 供第 6 步守卫读取"
            % (_fk0, len(FIXES_BY_VERSION[VER])))
    for _i, (no, name, fn) in enumerate(STAGES):
        if no < _start:
            continue
        # 显示用连续序号（4.5 这类中间步骤若直接打印会显示 "步骤 4.5/14"）
        log("\n【步骤 %d/%d】%s" % (_i + 1, len(STAGES), name))
        fn()

    ok = postcheck()
    log("\n" + "=" * 70)
    if ok and not _FAILED:
        log("  ✓ 构建完成 v%s" % VER)
        log("    交付：框架_完整交付_v%s_%s.md" % (VER, DATE))
        log("    打包：框架交叉验证包_v%s_%s.zip" % (VER, DATE))
    else:
        log("  ✗ 构建完成但有失败：%s" % _FAILED)
    log("=" * 70)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
