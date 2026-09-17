#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
compare_runs.py —— 跨平台结果比对

════════════════════════════════════════════════════════════════
判定三档(审核 §7.3):
  ① 通过        :计数一致,数值差 ≤ atol
  ② 通过但有差异:计数一致,数值差 > atol  → 需人工核查来源
  ③ 真发现问题  :计数或分支数变化         → 最有价值,不是失败

v2.6 扩展:支持**多方**比对(基线 vs Win11 vs Linux沙箱 vs ...)，
一次给出全部平台的横向结果，避免两两比对时"基线"被反复切换导致口径不一。

用法:
    python3 scripts/compare_runs.py <其它平台report.json> [更多.json ...]
"""

import os
import sys
# ── 控制台编码加固（v2.25）──────────────────────────────────────────────────
# 起因：中文 Windows 默认控制台 cp936(GBK) 无法编码 ▸/⚠/✓/✗ → UnicodeEncodeError。
try:
    if sys.stdout.isatty():
        sys.stdout.reconfigure(errors="replace")
    else:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(errors="replace")
except (AttributeError, ValueError):
    pass
import json

ATOL = 1e-3   # 数值容差(Harness P1):浮点在 numpy/scipy 版本间有 1e-6 级差异
HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.join(HERE, "..", "results", "report.json")


def flat(o, pre=""):
    """展平为 {路径: 值},只留数值与布尔"""
    out = {}
    if isinstance(o, dict):
        for k, v in o.items():
            out.update(flat(v, f"{pre}.{k}" if pre else k))
    elif isinstance(o, list):
        for i, v in enumerate(o):
            out.update(flat(v, f"{pre}[{i}]"))
    elif isinstance(o, bool):
        out[pre] = o
    elif isinstance(o, (int, float)):
        out[pre] = o
    return out


def compare_one(base, other, label):
    """比对一对，返回 (档位, 明细)。档位 1/2/3，0 表示完全一致。"""
    sb = base.get("summary", {})
    so = other.get("summary", {})
    if (sb.get("total"), sb.get("branches")) != (so.get("total"), so.get("branches")):
        return 3, [("计数", sb.get("total"), so.get("total")),
                   ("分支", sb.get("branches"), so.get("branches"))]
    fb, fo = flat(base), flat(other)
    diffs, big = [], []
    for k in sorted(set(fb) & set(fo)):
        vb, vo = fb[k], fo[k]
        if isinstance(vb, bool) or isinstance(vo, bool):
            if vb != vo:
                diffs.append((k, vb, vo, "bool"))
        elif isinstance(vb, (int, float)) and isinstance(vo, (int, float)):
            d = abs(float(vb) - float(vo))
            if d > 0:
                (big if d > ATOL else diffs).append((k, vb, vo, d))
    if big:
        return 2, big
    if diffs:
        return 1, diffs
    return 0, []


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if not args:
        print("用法: python3 scripts/compare_runs.py <其它平台report.json> [更多.json ...]")
        print("      （基线为本机 results/report.json）")
        return 2

    b = json.load(open(BASE, encoding="utf-8"))
    sb = b.get("summary", {})
    print("=" * 74)
    print("  跨平台结果比对（多方）")
    print("  基线: %d/%d 项, %d 分支, run=%s" % (
        sb.get("n_pass", 0), sb.get("total", 0), sb.get("branches", 0),
        str(b.get("run_metadata", {}).get("run_id", "?"))[:16]))
    print("=" * 74)

    worst = 0
    for path in args:
        if not os.path.isfile(path):
            print("\n  ✗ 文件不存在: %s" % path)
            worst = max(worst, 3)
            continue
        o = json.load(open(path, encoding="utf-8"))
        so = o.get("summary", {})
        # 用文件名推断平台：含 win/windows 视作 Windows
        low = os.path.basename(path).lower()
        label = "Windows" if ("win" in low) else \
                ("Linux" if ("linux" in low) else os.path.basename(path))
        level, detail = compare_one(b, o, label)
        worst = max(worst, level)

        print("\n" + "─" * 74)
        print("  ▸ %s   %s/%s 项, %s 分支" % (
            label, so.get("n_pass"), so.get("total"), so.get("branches")))
        if level == 3:
            print("     ⚠ 第三档【真发现问题】:判定项数或分支数变化")
            for k, vb, vo in detail:
                print("       %-10s 基线=%s  该平台=%s" % (k, vb, vo))
        elif level == 2:
            print("     ⚠ 第二档【通过但有差异】:%d 项数值差 > atol=%s" % (len(detail), ATOL))
            for k, vb, vo, d in detail[:20]:
                print("       %-50s %s vs %s  Δ=%.6g" % (k[:50], vb, vo, d))
        elif level == 1:
            print("     ✓ 第一档【通过】:%d 项有差异但均在容差内(≤%s)" % (len(detail), ATOL))
            for k, vb, vo, d in detail[:10]:
                print("       %-50s %s vs %s  Δ=%.3g" % (k[:50], vb, vo, d))
        else:
            print("     ✓ 第一档【通过】:与基线完全一致(容差 %s 内)" % ATOL)

    print("\n" + "=" * 74)
    print("  汇总档位: %s" % {0: "全部一致", 1: "全部通过(容差内差异)",
                             2: "存在 >atol 差异，需核查",
                             3: "★ 存在真问题：计数/分支变化 —— 最有价值的发现"}.get(worst, "?"))
    print("  提示: 数值差异先跑 compare_platforms.py 查环境差异，再谈是否为框架问题。")
    print("=" * 74)
    return 0 if worst <= 1 else (2 if worst == 2 else 3)


if __name__ == "__main__":
    sys.exit(main())
