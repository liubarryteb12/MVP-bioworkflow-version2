# _archive_v2.24_partial · 旧版残缺骨架归档

本目录保存仓库最初的 v2.24 时代文件（2026-09-12 归档），**已被完整 v2.26 官方交付包替换**。

| 归档文件 | 说明 |
|---|---|
| `gse31210_real.yml` | 旧 workflow：引用了 `crossval/requirements.txt`、`layout_check.py`、`ablation.py`、`consistency_guard.py`、`tests/`、`figures/`、`make_paper_gse31210.py` 等当时**并不存在于仓库**的文件，且守卫调用用的是未版本化旧名 `框架_独立审核包_v1.md`（正是 v2.24 审查报告 P0-1 揪出的硬编码陷阱）——跑起来必崩，故归档 |
| `run_gse31210.py` | 自研 GSE31210 真实数据分析脚本（scipy/sklearn 生存分析实现）。**有价值，待评审**：后续走 U00→U03 流水线接真实数据时可复用/改造 |
| `gse31210_adapter.py` | series matrix 解析适配器（同上，待评审） |

归档原因详见主仓库根 `README.md` 与 `框架_独立审核包_v2.26_20260912.md`。
