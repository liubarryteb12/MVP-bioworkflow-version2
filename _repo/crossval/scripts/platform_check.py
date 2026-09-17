#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
platform_check.py —— 跨平台环境探测与快照

════════════════════════════════════════════════════════════════
为什么需要这个文件
────────────────────────────────────────────────────────────────
跨平台实测要回答的问题是："同一份代码在不同环境下，结果是否一致？"

但"环境"本身是个黑箱。若两台机器跑出不同结果，必须先知道
**它们到底差在哪** —— 是 numpy 版本？是中文字体？还是文件系统
大小写敏感性？否则"数值有 1e-6 差异"只能归因于猜。

本脚本把环境**快照化**，让差异可比对、可归因。

════════════════════════════════════════════════════════════════
设计要点
────────────────────────────────────────────────────────────────
1. **只探测，不改环境** —— 只读，不安装、不修改任何配置。
2. **缺失项不算失败** —— 字体缺了、包没装，如实记录为 null/false，
   不抛异常。环境差异正是要观察的对象，不能因探测失败而中断。
3. **输出结构化 JSON** —— 供 compare_platforms.py 逐字段比对。

用法:
    python3 scripts/platform_check.py [--out 环境快照.json]
"""

import os
import sys
import json
import platform
import subprocess
from datetime import datetime, timezone, timedelta

CST = timezone(timedelta(hours=8))
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# 关心的依赖：这些包的版本差异是数值差异的首要嫌疑
WATCH = ["numpy", "scipy", "sklearn", "pandas", "matplotlib",
         "pypdf", "yaml", "pytest", "PIL"]


def _pip(name):
    """读包版本。失败返回 None（不算错误）。"""
    try:
        mod = __import__(name)
        return getattr(mod, "__version__", "unknown")
    except Exception:
        return None


def _cjk_fonts():
    """探测可用的中文字体 + 脚本实际会选中哪一个。

    为什么要测"实际选中"：verify_all.py 里字体选择是一条 fallback 链
    (WenQuanYi Micro Hei → DejaVu Sans → Microsoft YaHei → SimHei)。
    纯净 Linux 上会退到 DejaVu Sans（无中文字形），虽不报错，
    但生成的 PDF 元数据与装了中文字体的机器不同。
    """
    out = {"available": [], "chosen": None, "cjk_count": 0}
    try:
        import matplotlib
        matplotlib.use("Agg")
        from matplotlib import font_manager as fm
        names = sorted(set(f.name for f in fm.fontManager.ttflist))
        cjk = [n for n in names
               if any(k in n for k in ("CJK", "Hei", "Song", "YaHei",
                                       "WenQuanYi", "Noto Sans SC"))]
        out["available"] = cjk
        out["cjk_count"] = len(cjk)
        for f in ["WenQuanYi Micro Hei", "DejaVu Sans",
                  "Microsoft YaHei", "SimHei"]:
            try:
                fm.findfont(f, fallback_to_default=False)
                out["chosen"] = f
                break
            except Exception:
                # 预期:候选字体不存在。继续试下一个,非错误。
                continue
    except Exception as e:
        out["error"] = "%s: %s" % (type(e).__name__, str(e)[:120])
    return out


def _fs_casesensitive():
    """实测文件系统大小写敏感性（Windows 不敏感 / Linux 敏感）。

    为什么实测而非看 platform.system()：
    隔离守卫 v2 靠大小写折叠防御 Windows 上的绕过
    (ROOT/LEDGER/x.json 与 ROOT/ledger/x.json 在 Windows 是同一个文件)。
    该防御是否必要，取决于目标 FS 到底敏不敏感 —— 必须实测。
    """
    p = os.path.join(ROOT, ".case_probe_tmp")
    try:
        open(p, "w").write("x")
        upper = os.path.join(ROOT, ".CASE_PROBE_TMP")
        sensitive = not os.path.exists(upper)
        return sensitive
    except Exception:
        return None
    finally:
        try:
            os.remove(p)
        except Exception:
            # 预期:探测文件可能已被清理。非错误,不记录。
            pass


def _sep_behavior():
    """测反斜杠路径在当前平台是否会被当作目录分隔符。

    POSIX 下 "a\\b" 是一个文件名；Windows 下是两级目录。
    这正是隔离守卫 v1 在 Windows 上失效的根因
    (abspath 不转换分隔符 → 字符串里没有 "/ledger/" → 放行)。
    """
    d = os.path.join(ROOT, "figures")
    if not os.path.isdir(d):
        d = ROOT
    probe = os.path.join(d, "probe\\sub")
    try:
        open(probe, "w").write("x")
        existed = os.path.exists(probe)
        os.remove(probe)
        # 能创建成功 = 反斜杠不是分隔符（POSIX 行为）
        return {"backslash_is_separator": not existed, "probe": "creatable"}
    except Exception:
        return {"backslash_is_separator": True, "probe": "not_creatable"}


def main():
    snap = {
        "schema": "platform_snapshot/v1",
        "generated_at": datetime.now(CST).isoformat(),
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "python": platform.python_version(),
            "implementation": platform.python_implementation(),
            "filesystem_encoding": sys.getfilesystemencoding(),
            "default_encoding": sys.getdefaultencoding(),
        },
        "paths": {
            "sep": os.sep,
            "altsep": os.altsep,
            "pathsep": os.pathsep,
            "case_sensitive_filesystem": _fs_casesensitive(),
            "backslash": _sep_behavior(),
        },
        "packages": {k: _pip(k) for k in WATCH},
        "cjk_font": _cjk_fonts(),
        "env": {
            "TZ": os.environ.get("TZ"),
            "LANG": os.environ.get("LANG"),
            "PYTHONHASHSEED": os.environ.get("PYTHONHASHSEED"),
            "MPLBACKEND": os.environ.get("MPLBACKEND"),
        },
    }

    # 时区偏移：影响时间戳，v1.6 曾因此出现同一脚本两处时间差 8 小时
    try:
        off = datetime.now(CST).utcoffset()
        snap["platform"]["utc_offset_hours"] = off.total_seconds() / 3600 if off else None
    except Exception:
        snap["platform"]["utc_offset_hours"] = None

    out = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else \
        os.path.join(ROOT, "results", "platform_snapshot.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    json.dump(snap, open(out, "w", encoding="utf-8"),
              indent=2, ensure_ascii=False)

    print("=" * 70)
    print("  跨平台环境快照")
    print("=" * 70)
    p = snap["platform"]
    print("  系统      : %s %s (%s)" % (p["system"], p["release"], p["machine"]))
    print("  Python    : %s / %s" % (p["python"], p["implementation"]))
    print("  FS 大小写敏感: %s" % snap["paths"]["case_sensitive_filesystem"])
    print("  反斜杠作分隔符: %s" % snap["paths"]["backslash"]["backslash_is_separator"])
    print("  中文字体  : %d 个可用，实际选中 %r"
          % (snap["cjk_font"]["cjk_count"], snap["cjk_font"]["chosen"]))
    print("  关键包    :")
    for k, v in snap["packages"].items():
        print("      %-12s %s" % (k, v if v else "（未安装）"))
    print("\n  已写入: %s" % out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
