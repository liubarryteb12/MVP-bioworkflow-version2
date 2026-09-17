"""探针 → 基因 symbol 映射框架（平台无关 / platform-agnostic）。

设计原则（来自用户要求）
------------------------
不同 GPL 平台的注释表，探针列、gene-symbol 列的位置**各不相同**；不同 GSE 表达
矩阵的探针列名也可能变化（ID_REF / ID / probe_id ...）。因此本模块刻意**不写死**
任何列序号或列名：

  * 框架只提供【通用读表 + 按“指定列”做 join + 多 symbol 处理 + 覆盖统计】能力；
  * 具体「哪一列是探针、哪一列是 symbol」由调用方（AI / 配置文件）**按数据集显式
    指定**——框架仅用 detect_*_columns() 给出启发式建议，但绝不替 AI 拍板；
  * 所有列定位决策都通过 resolve_report() 落盘，满足项目的可审计 / 可复现纪律。

典型调用（AI 先读表头 → 定列 → 映射 → 记录决策）：
    gpl_hdr, gpl_rows = read_gpl_annot(gpl_path)
    sug = detect_gpl_columns(gpl_hdr)                 # 建议，AI 可改
    probe2sym = build_probe2sym_from_rows(
        gpl_rows, probe_col=sug["probe_col"], symbol_col=sug["symbol_col"])
    gse_ids = get_gse_probe_ids(gse_path)             # 自动定位探针列
    syms = [probe2sym.get(p) for p in gse_ids]
"""
from __future__ import annotations
import gzip
import os
import re
from collections import Counter

# 视为“无 symbol”的占位（GEO 常用 --- / NA / ''）
_NULL_SYMBOLS = {"", "---", "na", "n/a", "none", "null", "nan", "?"}

# 多 symbol 分隔符（GEO 常见 ///，也有用 // 或 | 的）
_MULTI_SEPS = ["///", "//", "|", ";", ","]


# --------------------------------------------------------------------------- #
# 1. 通用读表：GPL 注释表 / GSE 表达矩阵
# --------------------------------------------------------------------------- #
def _open(path):
    """自动处理 .gz 与普通文本。"""
    if str(path).endswith(".gz"):
        return gzip.open(path, "rt", errors="replace")
    return open(path, "rt", encoding="utf-8", errors="replace")


def _read_block(path, begin_tag, end_tag):
    """读取 GEO SOFT 中以 !xxx_table_begin / !xxx_table_end 包裹的表格块。
    返回 (header: list[str], rows: list[list[str]])。header 为 begin 后的首行。"""
    header, rows = None, []
    with _open(path) as f:
        started = False
        for line in f:
            line = line.rstrip("\n").rstrip("\r")
            if line.startswith(begin_tag):
                started = True
                continue
            if not started:
                continue
            if line.startswith(end_tag):
                break
            parts = line.split("\t")
            if header is None:
                header = parts
            else:
                rows.append(parts)
    return header, rows


def read_gpl_annot(path):
    """读取平台注释表。返回 (header, rows)。"""
    return _read_block(path, "!platform_table_begin", "!platform_table_end")


def read_gse_matrix(path):
    """读取表达矩阵块。返回 (header, rows)，header[0] 通常为探针列。"""
    return _read_block(path, "!series_matrix_table_begin", "!series_matrix_table_end")


# --------------------------------------------------------------------------- #
# 2. 列名归一 + 启发式建议（仅建议，AI 负责最终指定）
# --------------------------------------------------------------------------- #
def norm_col(name: str) -> str:
    """列名归一：去引号、小写、空格/连字符→下划线。"""
    return name.strip().strip('"').strip("'").lower().replace(" ", "_").replace("-", "_")


def detect_gpl_columns(header):
    """启发式建议 GPL 注释表的探针列与 symbol 列索引。

    返回 {"probe_col": int|None, "probe_name": str,
          "symbol_col": int|None, "symbol_name": str}。
    ⚠️ 仅作建议：AI 应读表头确认，必要时覆盖本结果。"""
    n = [norm_col(h) for h in header]

    # --- 探针列：优先精确 'id'，其次含 probe/spot/id_ref 且不含 gene/symbol ---
    probe_candidates = []
    for i, h in enumerate(n):
        if h == "id":
            probe_candidates.append((0, i, header[i]))
        elif "id_ref" in h or "probe" in h or "spot" in h:
            probe_candidates.append((1, i, header[i]))
        elif h.endswith("_id") and "gene" not in h and "symbol" not in h:
            probe_candidates.append((2, i, header[i]))
    probe_col = min(probe_candidates, key=lambda x: x[0])[1] if probe_candidates else 0

    # --- symbol 列：含 'symbol'（最好同时含 'gene'）---
    sym_candidates = []
    for i, h in enumerate(n):
        if "symbol" in h:
            score = 0 if "gene" in h else 1
            sym_candidates.append((score, i, header[i]))
    symbol_col = min(sym_candidates, key=lambda x: x[0])[1] if sym_candidates else None

    return {
        "probe_col": probe_col,
        "probe_name": header[probe_col] if 0 <= probe_col < len(header) else "",
        "symbol_col": symbol_col,
        "symbol_name": header[symbol_col] if symbol_col is not None else "",
    }


def detect_gse_probe_col(header):
    """启发式建议 GSE 表达矩阵的探针列索引（默认 0）。"""
    n = [norm_col(h) for h in header]
    for i, h in enumerate(n):
        if h in ("id_ref", "probe_id", "probeid", "id") and "symbol" not in h:
            return i
    for i, h in enumerate(n):
        if "probe" in h or "spot" in h or "id_ref" in h:
            return i
    return 0


# --------------------------------------------------------------------------- #
# 3. 核心映射：按指定列做 join
# --------------------------------------------------------------------------- #
def _split_symbols(val: str):
    """把可能含多个 symbol 的字符串拆成列表（'///' 分隔等）。"""
    if val is None:
        return []
    v = val.strip()
    if not v or v.lower() in _NULL_SYMBOLS:
        return []
    for sep in _MULTI_SEPS:
        if sep in v:
            return [s.strip() for s in v.split(sep) if s.strip()]
    return [v]


def build_probe2sym_from_rows(rows, probe_col, symbol_col,
                              split_multi: bool = False,
                              keep_unmapped: bool = True):
    """由 GPL 注释行构建 探针→symbol 字典。

    probe_col / symbol_col：AI 显式指定的列索引（务必先读表头确认！）。
    split_multi=False：保留原始串（如 'A///B'），便于逐字落表；
    split_multi=True ：拆分为列表，便于按基因去重/富集。
    keep_unmapped=True：探针无 symbol 时映射到 None（仍计入统计）。
    返回 dict[probe_id] -> str | list[str] | None。
    """
    out = {}
    for parts in rows:
        if max(probe_col, symbol_col or 0) >= len(parts):
            continue  # 残缺行跳过
        pid = parts[probe_col].strip().strip('"')
        if not pid:
            continue
        raw = parts[symbol_col].strip().strip('"') if symbol_col is not None else ""
        if raw.lower() in _NULL_SYMBOLS:
            out[pid] = None
            continue
        if split_multi:
            out[pid] = _split_symbols(raw)   # list[str]
        else:
            out[pid] = raw                    # 原始串（可能含 '///'）
    return out


def build_probe2sym(gpl_path, probe_col=None, symbol_col=None, split_multi=False):
    """便捷封装：不传列则先 detect 再建（但仍建议 AI 显式指定）。"""
    header, rows = read_gpl_annot(gpl_path)
    if probe_col is None or symbol_col is None:
        sug = detect_gpl_columns(header)
        probe_col = sug["probe_col"] if probe_col is None else probe_col
        symbol_col = sug["symbol_col"] if symbol_col is None else symbol_col
    return build_probe2sym_from_rows(rows, probe_col, symbol_col, split_multi)


def get_gse_probe_ids(gse_path, probe_col=None):
    """读取 GSE 表达矩阵的探针 ID 列表（按 AI 指定或自动定位的探针列）。"""
    header, rows = read_gse_matrix(gse_path)
    if probe_col is None:
        probe_col = detect_gse_probe_col(header)
    return [r[probe_col].strip().strip('"') for r in rows if r and r[probe_col].strip()]


# --------------------------------------------------------------------------- #
# 4. 映射决策落盘（可审计 / 可复现）
# --------------------------------------------------------------------------- #
def resolve_report(gpl_path, gse_path=None, probe_col=None, symbol_col=None,
                   split_multi=False):
    """执行映射并返回一份决策报告 dict（供写入台账 / 审计文件）。

    若列未指定，先用启发式 detect（并在报告中标注 suggested=True 提醒 AI 复核）。
    """
    gpl_hdr, gpl_rows = read_gpl_annot(gpl_path)
    sug = detect_gpl_columns(gpl_hdr)
    suggested = (probe_col is None) or (symbol_col is None)
    if probe_col is None:
        probe_col = sug["probe_col"]
    if symbol_col is None:
        symbol_col = sug["symbol_col"]

    probe2sym = build_probe2sym_from_rows(gpl_rows, probe_col, symbol_col, split_multi)

    n_total = len(probe2sym)
    n_mapped = sum(1 for v in probe2sym.values() if v)
    n_multi = sum(1 for v in probe2sym.values()
                  if isinstance(v, str) and any(s in v for s in _MULTI_SEPS))
    rep = {
        "gpl_path": os.path.basename(gpl_path),
        "probe_col": probe_col,
        "probe_name": gpl_hdr[probe_col] if 0 <= probe_col < len(gpl_hdr) else "",
        "symbol_col": symbol_col,
        "symbol_name": gpl_hdr[symbol_col] if symbol_col is not None else "",
        "split_multi": split_multi,
        "suggested_columns": suggested,   # True=AI 未显式指定，需复核
        "n_probes_total": n_total,
        "n_probes_mapped": n_mapped,
        "n_probes_unmapped": n_total - n_mapped,
        "n_probes_multi_symbol": n_multi,
        "coverage_pct": round(100.0 * n_mapped / n_total, 1) if n_total else 0.0,
    }
    if gse_path:
        ids = get_gse_probe_ids(gse_path)
        rep["gse_n_probes"] = len(ids)
        rep["gse_n_mapped"] = sum(1 for p in ids if probe2sym.get(p))
        rep["gse_coverage_pct"] = round(100.0 * rep["gse_n_mapped"] / len(ids), 1) if ids else 0.0
    return rep, probe2sym


# --------------------------------------------------------------------------- #
# 自检：用本仓库真实文件跑一遍
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    base = os.path.dirname(here)
    gpl = os.path.join(here, "assets", "GPL570.annot.gz")
    gse = os.path.join(base, "GSE31210_series_matrix.txt.gz")

    print(">>> 启发式建议（AI 应先读这份，再决定要不要覆盖）")
    gh, _ = read_gpl_annot(gpl)
    print("  GPL detect:", detect_gpl_columns(gh))

    print("\n>>> AI 显式指定列后做映射（GPL570: probe=0 'ID', symbol=2 'Gene symbol'）")
    rep, p2s = resolve_report(gpl, gse, probe_col=0, symbol_col=2)
    for k, v in rep.items():
        print(f"  {k}: {v}")

    print("\n>>> 抽样校验")
    sample = list(p2s.items())[:5]
    for pid, sym in sample:
        print(f"  {pid} -> {sym!r}")
    # 找一个多 symbol 探针
    multi = [(p, s) for p, s in p2s.items() if s and any(sep in s for sep in _MULTI_SEPS)]
    print("  多 symbol 示例:", multi[:3])
