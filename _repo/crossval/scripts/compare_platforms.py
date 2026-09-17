#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
compare_platforms.py —— 环境快照比对（跨平台差异归因）

════════════════════════════════════════════════════════════════
定位
────────────────────────────────────────────────────────────────
compare_runs.py   比的是**结果**（report.json 的数值）
compare_platforms.py 比的是**环境**（platform_snapshot.json）

两者配合才完整：
    结果不一致 → 先看环境差在哪 → 才能判断差异是否合理

举例：若 Windows 与 Linux 的 ΔAUC 差 1e-6，
    先查 numpy 版本是否同；若不同，则 1e-6 是可解释的浮点差异，
    不是框架 bug。反之若环境完全一致却仍有差异，那才是真问题。

════════════════════════════════════════════════════════════════
分级
────────────────────────────────────────────────────────────────
- [FATAL] 必然影响结果：Python 大版本、关键包缺失
- [WARN ] 可能影响结果：包版本差、中文字体不同
- [EXPECT] 预期差异，不算问题：OS 不同、FS 大小写、反斜杠语义

用法:
    python3 scripts/compare_platforms.py <其它平台快照.json> [更多快照.json ...]
"""

import os
import sys
# ── 控制台编码加固（v2.25）──────────────────────────────────────────────────
# 起因：中文 Windows 默认控制台 cp936(GBK) 无法编码 ▸/✓/✗ → UnicodeEncodeError。
try:
    if sys.stdout.isatty():
        sys.stdout.reconfigure(errors="replace")
    else:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(errors="replace")
except (AttributeError, ValueError):
    pass
import json

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BASE = os.path.join(ROOT, "results", "platform_snapshot.json")

# 这些包版本不同 → 数值可能有 1e-6 ~ 1e-3 级差异
NUMERIC_PKGS = ["numpy", "scipy", "sklearn", "pandas", "matplotlib"]


def _ver_tuple(v):
    try:
        return tuple(int(x) for x in str(v).split(".")[:3])
    except Exception:
        return None


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if not args:
        print("用法: python3 scripts/compare_platforms.py <其它平台快照.json> [...]")
        print("      （基线为本机 results/platform_snapshot.json）")
        return 2
    if not os.path.isfile(BASE):
        print("  ✗ 本机快照不存在，请先跑:")
        print("      python3 scripts/platform_check.py")
        return 2

    base = json.load(open(BASE, encoding="utf-8"))
    print("=" * 74)
    print("  环境快照比对")
    print("  基线: %s %s / Python %s" % (
        base["platform"]["system"], base["platform"]["release"],
        base["platform"]["python"]))
    print("=" * 74)

    rc = 0
    for path in args:
        if not os.path.isfile(path):
            print("\n  ✗ 文件不存在: %s" % path)
            rc = max(rc, 2)
            continue
        o = json.load(open(path, encoding="utf-8"))
        op = o.get("platform", {})
        print("\n" + "─" * 74)
        print("  ▸ %s" % os.path.basename(path))
        print("    %s %s (%s) / Python %s / %s" % (
            op.get("system"), op.get("release"), op.get("machine"),
            op.get("python"), op.get("implementation")))

        fatal, warn, expect = [], [], []

        # ── [EXPECT] 平台固有差异 ────────────────────────────────
        if op.get("system") != base["platform"]["system"]:
            expect.append("操作系统不同（%s vs %s）—— 本次测试的目的" % (
                op.get("system"), base["platform"]["system"]))

        bcs = base.get("paths", {}).get("case_sensitive_filesystem")
        ocs = o.get("paths", {}).get("case_sensitive_filesystem")
        if bcs != ocs:
            expect.append("文件系统大小写敏感性不同（基线 %s / 该平台 %s）"
                          "—— 隔离守卫已按此加固" % (bcs, ocs))

        bbs = base.get("paths", {}).get("backslash", {}).get("backslash_is_separator")
        obs = o.get("paths", {}).get("backslash", {}).get("backslash_is_separator")
        if bbs != obs:
            expect.append("反斜杠语义不同（基线 %s / 该平台 %s）"
                          "—— 隔离守卫 v2 已按此修复" % (bbs, obs))

        # ── [FATAL] Python 主版本 / 关键包缺失 ───────────────────
        bmaj = base["platform"]["python"].split(".")[:2]
        omaj = str(op.get("python", "")).split(".")[:2]
        if bmaj != omaj:
            fatal.append("Python 主版本不同（%s vs %s）—— 语法/行为可能不兼容" % (
                ".".join(bmaj), ".".join(omaj)))

        bp, opkg = base.get("packages", {}), o.get("packages", {})
        for k in ["numpy", "scipy", "sklearn", "pandas", "pypdf", "matplotlib"]:
            if bp.get(k) and not opkg.get(k):
                fatal.append("关键包缺失: %s（基线 %s）" % (k, bp[k]))

        # ── [WARN] 数值包版本差异 ────────────────────────────────
        for k in NUMERIC_PKGS:
            bv, ov = bp.get(k), opkg.get(k)
            if not bv or not ov:
                continue
            if bv != ov:
                bt, ot = _ver_tuple(bv), _ver_tuple(ov)
                level = "次版本" if (bt and ot and bt[:2] == ot[:2]) else "主/次版本"
                warn.append("%s 版本不同（%s vs %s，%s）—— "
                            "数值结果可能有 1e-6 级差异" % (k, bv, ov, level))

        # 中文字体
        bcjk = base.get("cjk_font", {})
        ocjk = o.get("cjk_font", {})
        if bcjk.get("chosen") != ocjk.get("chosen"):
            warn.append("实际选中的字体不同（%r vs %r）—— "
                        "生成的 PDF 元数据会不同，属已知正常差异" % (
                            bcjk.get("chosen"), ocjk.get("chosen")))

        # 时区
        bt = base.get("platform", {}).get("utc_offset_hours")
        ot = op.get("utc_offset_hours")
        if bt is not None and ot is not None and bt != ot:
            warn.append("时区偏移不同（%s vs %s）—— 时间戳会差若干小时" % (bt, ot))

        for tag, items in [("[FATAL ]", fatal), ("[WARN  ]", warn), ("[EXPECT]", expect)]:
            for it in items:
                print("      %s %s" % (tag, it))
        if not (fatal or warn or expect):
            print("      ✓ 环境与基线完全一致")

        if fatal:
            rc = max(rc, 1)
    print("\n" + "=" * 74)
    print("  说明: [EXPECT] 是本次测试要观察的对象，不是问题。")
    print("        [WARN] 可解释 1e-6 级数值差异；[FATAL] 需先排除再谈结果比对。")
    print("=" * 74)
    return rc


if __name__ == "__main__":
    sys.exit(main())
