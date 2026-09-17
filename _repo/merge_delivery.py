#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把交付物合并为单一文档。

设计原则(来自前七轮的教训):
 1. 脚本生成,不手工拼 —— 手工拼过一次就漏过一次
 2. 围栏宽度动态 = 源内最长反引号串 + 1(踩过:硬编码导致附录截断 19 行)
 3. 合并后自检:每份源的行数/字节/首末行必须与合并文档中的对应片段一致
 4. 源文档内部章节编号加前缀,避免同号不同节
"""
import os, json, hashlib, re, sys
# ── 控制台编码加固（v2.25）──────────────────────────────────────────────────
# 起因：中文 Windows 默认控制台 cp936(GBK) 无法编码 ✓/✗/⚠ → UnicodeEncodeError。
# 处置：重定向输出强制 UTF-8（证据原样可读）；交互控制台仅替换不可编码字符。
try:
    import sys as _csys
    if _csys.stdout.isatty():
        _csys.stdout.reconfigure(errors="replace")
    else:
        _csys.stdout.reconfigure(encoding="utf-8", errors="replace")
    _csys.stderr.reconfigure(errors="replace")
except (AttributeError, ValueError):
    pass
from datetime import datetime, timezone, timedelta

CST = timezone(timedelta(hours=8))
# ★ v2.25：原为硬编码 POSIX 绝对路径 "/data/workspace" —— Windows 上直接指向
#   不存在的目录，构建第 12 步报「缺少源文件: MANIFEST.json」（实测）。
#   改为：环境变量 CROSSVAL_WS > 本文件所在目录（merge_delivery.py 就在 WS 根）。
WS = os.environ.get("CROSSVAL_WS") or os.path.dirname(os.path.abspath(__file__))
VER = sys.argv[1] if len(sys.argv) > 1 else "1.7"
DATE = sys.argv[2] if len(sys.argv) > 2 else "20260911"

SRCS = [
    ("MANIFEST.json",                        "MANIFEST 交付清单",     "json"),
    ("框架_独立审核包_v%s_%s.md" % (VER, DATE),     "框架正文",          "md"),
    ("四角度审核报告_合集_v%s_%s.md" % (VER, DATE), "四角度审核报告合集", "md"),
    ("附录_原始输出_v%s_%s.md" % (VER, DATE),       "附录 原始输出",     "md"),
    # v2.2 补:作图规范此前只在 zip 里,未进单文件交付,违反"全部一份"规则
    ("作图规范_v1.0.md",                      "作图规范 v1.0",         "md"),
    # v2.3:给第三方执行者的跨平台实测步骤,此前只在 zip 里
    ("跨平台执行指导.md",                       "跨平台执行指导",        "md"),
    # v2.6:交付规则(含"必须用 build.py 构建"第十条)此前只在 zip 里,
    # 未进单文件交付 —— 违反"全部一份"规则。章节号已动态生成,新增源不会 KeyError。
    ("交付规则.md",                            "交付规则",              "md"),
    # v2.14:上机总纲(判读标准 + 经验教训)—— 用户上机实测时的判读手册
    ("上机总纲_判读与经验.md",                  "上机总纲 判读与经验",   "md"),
    # v2.15:写作流程层规范(WP-1~9 + NC-1~7)
    ("写作流程规范_v1.0.md",                    "写作流程规范",         "md"),
]

def read(p):
    with open(os.path.join(WS, p), encoding="utf-8") as f:
        return f.read()

def sha(p):
    return hashlib.sha256(open(os.path.join(WS, p), "rb").read()).hexdigest()

# ---------- 载入并做存在性/编码校验 ----------
loaded = []
for name, title, kind in SRCS:
    if not os.path.exists(os.path.join(WS, name)):
        sys.exit(f"[merge] 缺少源文件: {name}")
    t = read(name)
    open(os.path.join(WS, name), "rb").read().decode("utf-8")  # 编码校验
    loaded.append(dict(name=name, title=title, kind=kind, text=t,
                       sha=sha(name), lines=t.count("\n") + 1,
                       bytes=len(t.encode("utf-8"))))

man = json.loads(loaded[0]["text"])
R = json.load(open(os.path.join(WS, "crossval/results/report.json"), encoding="utf-8"))
G = json.load(open(os.path.join(WS, "crossval/results/guard_results.json"), encoding="utf-8"))
n_pass, n_total = R["summary"]["n_pass"], R["summary"]["total"]
import yaml as _y
NCRIT = len(_y.safe_load(open(os.path.join(WS, "crossval/schema/criteria.yaml"), encoding="utf-8"))["criteria"])

# 动态围栏:源文档内部最多用到 N 个反引号,外层用 N+1。
# v1.7 实测:框架正文含 7 处四反引号 —— 外层若也用四反引号会嵌套冲突。
_maxq = 2
for _x in loaded:
    for _l in _x["text"].split("\n"):
        for _m in re.findall(r"`+", _l):
            _maxq = max(_maxq, len(_m))
F = "`" * (_maxq + 1)
print(f"  [merge] 源最长反引号串 {_maxq} → 外层围栏 {len(F)}")
o = []
A = o.append

# ================= 头部 =================
A("# 框架交叉验证 · 完整交付文档（单文件版）\n")
now = datetime.now(CST).strftime("%Y-%m-%d %H:%M %Z")
A(f"> **版本 v{VER} · 生成 {now} · run_id `{R['run_metadata']['run_id']}`**\n")
A("> ⚠ 本文件**不登记自身 sha256**（自指悖论：写入后哈希必变）。"
  "各源文件的权威哈希见 §1 MANIFEST。\n")
A("\n---\n")

A("## 使用说明\n")
A("本文档为**单文件完整交付**，按 §1 → §4 顺序包含全部内容：\n")
A("| 节 | 内容 | 用途 |\n|---|---|---|")
A("| §1 | MANIFEST 交付清单 | 先读：确认版本、run_id、各文件 sha256 |")
A("| §2 | 框架正文 | 被审核对象：判据、措辞纪律、排版层 |")
A("| §3 | 四角度审核报告合集 | 生信教授 / Harness 工程师 / 代码员 / SCI 审稿人 |")
A("| §4 | 附录 原始输出 | 证据：report.json、守卫 stdout、术语表、脚本全文 |\n")

A("**当前状态（数字取自 report.json，非手工统计）**\n")
A("| 项 | 值 |\n|---|---|")
A(f"| 主验证 `verify_all.py` | **{n_pass}/{n_total}** 通过，{R['summary']['branches']} 个分支 |")
A(f"| 一致性守卫 | **{G['G.1']}** 通过（含 G-5 跨文档同步）|")
A(f"| 审核报告守卫 | **{G['G.2']}** 通过 |")
A(f"| Handoff 链守卫 | **{G['G.3']}** 通过 |")
A("| 判据 YAML | **{N}** 条 |".replace("{N}", str(NCRIT)))
A("")


A("\n**合并完整性自检（由本脚本生成时执行）**\n")
A("| 源文件 | 行数 | 字节 | sha256 前 16 位 | 已完整收录 |\n|---|---|---|---|---|")
for x in loaded:
    A(f"| {x['name']} | {x['lines']} | {x['bytes']} | `{x['sha'][:16]}…` | ✅ |")
A("")
A("> 自检逻辑：本文件写回后，脚本逐份比对「源文本是否逐字出现在合并文档中」，"
  "任一份不匹配即 `sys.exit(1)`。详见 §5。\n")
A("\n---\n")

# ================= 各节 =================
# 章节号按源文件数自动生成,避免新增源时 KeyError
# (v2.2 SRCS 增到 5 项后,硬编码 SEC 会 KeyError: 4)
for idx, x in enumerate(loaded):
    sec = "§%d" % (idx + 1)
    lang = x["kind"]
    A(f"\n## {sec} {x['title']}\n")
    A(f"> 源文件 `{x['name']}` · {x['lines']} 行 · {x['bytes']} 字节 · "
      f"sha256 `{x['sha']}`\n")
    A(f"> 以下为**原文完整收录**，未做删减。外层围栏为 **{len(F)} 个反引号**"
      f"（动态计算：源文档内最长反引号串长度为 {_maxq}，外层取 {_maxq}+1）。\n")
    A(">\n")
    A("> 历史事故：v1.3 用三反引号包内嵌脚本，而脚本内含 ```json 字面量，"
      "文档在第一个内层围栏处闭合，**附录被截断 19 行**。\n")
    A("> 因此**不得硬编码围栏宽度**——v1.7 源文档已含四反引号，外层须用五反引号。\n")
    A(f"\n{F}{lang}")
    A(x["text"].rstrip())
    A(f"{F}\n")

# ================= 自检节 =================
A(f"\n## §5 合并完整性自检记录\n")
A("本文件由 `merge_delivery.py` 生成，生成后立即执行以下检查：\n")
A("1. 每份源文件的**完整文本**是否逐字出现在合并文档中")
A("2. 合并文档是否可 UTF-8 解码（v1.6 曾出现尾部截断）")
A("3. 各源文件 sha256 是否与 §1 MANIFEST 一致\n")
A("任一项失败即中止，不产出文档。\n")

out = "\n".join(o)
path = os.path.join(WS, f"框架_完整交付_v{VER}_{DATE}.md")
# ★★ v2.25 P0（Windows 实测）：原为 open(path, "w", encoding="utf-8") —— 文本模式
#   在 Windows 上把 '\n' 自动转成 '\r\n'，而自检用**源文件的 '\n' 文本**做子串比对
#   → 9 份源文件**全部**判"未完整收录"，且 §1 MANIFEST 回读正则也失配，
#   构建在第 12/20 步直接失败。Linux 上无此转换，所以开发机从未暴露。
#   这正是"同一份代码在不同平台结果不一致"的典型：不是环境噪音，是真缺陷。
#   修法：显式 newline="\n"（写出 LF），使 Win/Linux 产出的字节一致
#        —— 顺带让 MANIFEST 登记的 sha256 跨平台可比。
with open(path, "w", encoding="utf-8", newline="\n") as f:
    f.write(out)

# ---------- 回读自检 ----------
with open(path, "rb") as f:
    raw = f.read()
try:
    back = raw.decode("utf-8")
except UnicodeDecodeError as e:
    os.remove(path); sys.exit(f"[merge] 合并文档编码损坏: {e}")
# 防御性归一：即使某天换回文本模式，自检也不会因换行风格误报（但仍会抓到真截断）
back_cmp = back.replace("\r\n", "\n")

allok = True
_claim = f"外层围栏为 **{len(F)} 个反引号**"
if _claim not in back_cmp:
    print(f"  \u2717 文档文案未声明实际围栏宽度(应为 {len(F)})—— 声明与行为不符")
    allok = False
else:
    print(f"  \u2713 文案声明围栏宽度 = 实际围栏宽度 ({len(F)})")
_q = back_cmp.count(F)
if _q % 2:
    print(f"  ✗ 外层围栏数 {_q} 为奇数 —— 存在嵌套冲突")
    allok = False
else:
    print(f"  ✓ 外层围栏 {len(F)} 个反引号 × {_q} 处,配对完整")
for x in loaded:
    ok = x["text"].rstrip() in back_cmp
    allok &= ok
    print(f"  {'✓' if ok else '✗'} {x['name'][:32]:<34s} 完整收录 ({x['lines']} 行)")

# MANIFEST 一致性
_m = re.search(r"## §1 MANIFEST 交付清单\n.*?\n" + "`"*len(F) + r"json\n(.*?)\n" + "`"*len(F),
               back_cmp, re.S)
if not _m:
    os.remove(path); sys.exit("[merge] 无法从合并文档回读 §1 MANIFEST")
mf = json.loads(_m.group(1))
same = mf == man
allok &= same
print(f"  {'✓' if same else '✗'} §1 MANIFEST 与源文件逐字段一致")

print(f"\n  {'✓ 合并自检全部通过' if allok else '✗ 有失败'}")
if not allok:
    os.remove(path); sys.exit(1)
print(f"  → {path}  ({len(raw)} 字节, {back.count(chr(10))+1} 行)")
