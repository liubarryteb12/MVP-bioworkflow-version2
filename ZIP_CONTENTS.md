# ZIP_CONTENTS.md —— 交付包内容清单（v2.26 · 20260912）

> **用途**：审核方/云端执行方据此逐项核对收到的文件是否完整。
> 与 `MANIFEST.json` 的 `files` 字段互为交叉索引（MANIFEST 只登记交付文档
> 与关键脚本；本清单覆盖 zip 内**全部**文件）。

> **自指规避**：本清单不登记自身的 sha256（写回后必然失效）。
> 故下表条数 = zip 内文件数 − 1。

| 项 | 值 |
|---|---|
| 生成时间 | 2026-09-12 20:35:37 +0800 |
| zip 文件名 | 框架交叉验证包_v2.26_20260912.zip |
| 下表条数 | 101 |
| zip 内文件总数（含本文件） | 102 |

| # | 路径 | 字节 | sha256（前 16） |
|---|---|---|---|
| 1 | `MANIFEST.json` | 43839 | `3b4be77a1d8a6db7…` |
| 2 | `MVP真实数据验证_结构化提示词_v1.0.md` | 12187 | `ca7a2ba12d3c0c4d…` |
| 3 | `build.py` | 91611 | `0cd64815f0726c2c…` |
| 4 | `crossval/INVARIANTS.md` | 2995 | `88bc8e2ed257a16c…` |
| 5 | `crossval/README.md` | 12674 | `c9c6680e04aa764e…` |
| 6 | `crossval/demo/export/docA.txt` | 340 | `89dd43f23caf30c8…` |
| 7 | `crossval/demo/export/docB.txt` | 448 | `55c0263119d90511…` |
| 8 | `crossval/demo/export/docP.txt` | 671 | `bbb48957a3533184…` |
| 9 | `crossval/demo/manuscript_demo.md` | 1473 | `86504f3c5c7ab038…` |
| 10 | `crossval/demo/manuscript_fixed.md` | 9094 | `3f0c3b29734f36e3…` |
| 11 | `crossval/demo/research_survey_skill_demo.json` | 3782 | `0a950df4548d8467…` |
| 12 | `crossval/figures/demo/01_qc_violin_mito.jpg` | 71510 | `06401c021fd8e816…` |
| 13 | `crossval/figures/demo/01_qc_violin_mito.pdf` | 14822 | `1953d51f82a8ed0a…` |
| 14 | `crossval/figures/demo/01_qc_violin_mito.png` | 48143 | `0ec876ebb13ddb0a…` |
| 15 | `crossval/figures/demo/01_qc_violin_mito.tiff` | 255288 | `16903dc89b0fbd94…` |
| 16 | `crossval/figures/demo/02_deg_volcano.jpg` | 54215 | `c5ba0d18e823c8ad…` |
| 17 | `crossval/figures/demo/02_deg_volcano.pdf` | 8690 | `1a42c21ed55fed37…` |
| 18 | `crossval/figures/demo/02_deg_volcano.png` | 27876 | `9e1c4bed200b7d14…` |
| 19 | `crossval/figures/demo/02_deg_volcano.tiff` | 264000 | `902945ca2c3e3513…` |
| 20 | `crossval/figures/samples/sample_bad_bitmap.pdf` | 13759 | `c8b01c6ad5af85b4…` |
| 21 | `crossval/figures/samples/sample_bad_notext.pdf` | 1427 | `c5993240f253ffa5…` |
| 22 | `crossval/figures/samples/sample_bad_page2_bitmap.pdf` | 23755 | `93f36aa51531f082…` |
| 23 | `crossval/figures/samples/sample_bad_type3.pdf` | 14117 | `01a8ae6867c510e9…` |
| 24 | `crossval/figures/samples/sample_ok_truetype.pdf` | 11745 | `16bda7c9fa925a61…` |
| 25 | `crossval/framework/A2C_S03_通用框架核定与规则定稿_v1.md` | 48621 | `eb44eef0ee459e8a…` |
| 26 | `crossval/framework/A2C_S07_v1.4复核与判据定稿_v1.md` | 37437 | `d22c68d9fceb7374…` |
| 27 | `crossval/framework/A2C_S13_回执确认与G6前置准备_v1.md` | 20153 | `d6012d9d450ba1f5…` |
| 28 | `crossval/framework/S15-A_判据闭合条文_已实跑验证.md` | 9454 | `34c9156f7e6e4936…` |
| 29 | `crossval/framework/S15-B_全量修订包_已实跑验证.md` | 11092 | `b224857aaee4b99d…` |
| 30 | `crossval/framework/S15-C_v1.8落盘条文库_可直接替换.md` | 10435 | `2f0e73f44bbfe2bb…` |
| 31 | `crossval/framework/S15-D_v1.8落盘校验清单.md` | 3685 | `b95067ac73fd5bc4…` |
| 32 | `crossval/framework/S15-E_全修复状态对账.md` | 3059 | `f585160366a87b71…` |
| 33 | `crossval/framework/S16_断电恢复包_v1.md` | 6739 | `31a31accac319722…` |
| 34 | `crossval/framework/S17_V5-T排版检查层_整合条文.md` | 7921 | `6afdaabce8fd18ca…` |
| 35 | `crossval/framework/S18_排版层整合条文_V5-P与V5-C.md` | 8234 | `866eb0d646bd97ae…` |
| 36 | `crossval/framework/S19_T13c修订条文_子区间操纵.md` | 6302 | `c88e2e4aff126402…` |
| 37 | `crossval/framework/S20_复审响应与T13c终稿.md` | 6811 | `c5b55bb0203e7599…` |
| 38 | `crossval/framework/S21-A_统计方法学缺口条文.md` | 7784 | `a119d8398cdc055c…` |
| 39 | `crossval/framework/S21-B_组学专属缺口条文.md` | 8863 | `f6347af98737a224…` |
| 40 | `crossval/framework/S21-C_报告规范与工程化条文.md` | 9304 | `a8e136fcf23cfcf7…` |
| 41 | `crossval/framework/判据权威版本.md` | 2321 | `517ed09a84e3b9f7…` |
| 42 | `crossval/framework/审核报告1_生物信息学教授视角.md` | 5813 | `a229586f0cd40a98…` |
| 43 | `crossval/framework/审核报告2_AI_Harness工程师视角.md` | 6081 | `924fa8f6018e7c9f…` |
| 44 | `crossval/framework/审核报告3_资深代码员视角.md` | 6549 | `7f60fe1fd4d8e930…` |
| 45 | `crossval/framework/审核报告4_SCI资深审稿人视角.md` | 5775 | `651d4eb573481b27…` |
| 46 | `crossval/requirements.txt` | 2207 | `de514cc33041775b…` |
| 47 | `crossval/results/build_version.json` | 156 | `05c360076459e659…` |
| 48 | `crossval/results/export_report.json` | 2651 | `d04447856cf44301…` |
| 49 | `crossval/results/guard_results.json` | 60 | `4c60dc38738cb118…` |
| 50 | `crossval/results/layout_report.json` | 16048 | `48898f068ede6289…` |
| 51 | `crossval/results/mutation_results.json` | 10483 | `a89e458dc98e5ee9…` |
| 52 | `crossval/results/platform_snapshot.json` | 1387 | `63aec844ce8c407e…` |
| 53 | `crossval/results/pytest_results.json` | 32 | `c8b76347b567678d…` |
| 54 | `crossval/results/report.json` | 85799 | `657eadb879e7ff32…` |
| 55 | `crossval/results/report.md` | 35267 | `b3c3f01937fb8ebc…` |
| 56 | `crossval/results/units_report.json` | 1505 | `f97309aa8e48c1f1…` |
| 57 | `crossval/results/writing_report.json` | 11628 | `0b052fd2040ee88d…` |
| 58 | `crossval/schema/criteria.yaml` | 42463 | `3433c1dc06b8e9a1…` |
| 59 | `crossval/scripts/ablation.py` | 23330 | `510999a04317f535…` |
| 60 | `crossval/scripts/applicability_gate.py` | 7657 | `9f333de26bdbd32e…` |
| 61 | `crossval/scripts/compare_platforms.py` | 7604 | `4bfff98d4331cd8f…` |
| 62 | `crossval/scripts/compare_runs.py` | 5826 | `16eac8b4cd1587b5…` |
| 63 | `crossval/scripts/component_ablation.py` | 6704 | `32dd4417f398ec90…` |
| 64 | `crossval/scripts/conclusion_branch.py` | 9606 | `a0c9dd820de3047d…` |
| 65 | `crossval/scripts/conclusion_guard.py` | 19081 | `d8a636116c401bc6…` |
| 66 | `crossval/scripts/consistency_guard.py` | 54096 | `84a41df64031697f…` |
| 67 | `crossval/scripts/data_ethics.py` | 7985 | `deecc6899f926bd2…` |
| 68 | `crossval/scripts/dormant_check.py` | 8802 | `8b9b31bc679addb4…` |
| 69 | `crossval/scripts/export_guard.py` | 7617 | `8e7b77197d2a95d0…` |
| 70 | `crossval/scripts/figure_kit.py` | 15886 | `b0dd42c07a933c22…` |
| 71 | `crossval/scripts/gen_appendix.py` | 26036 | `7e4ab7defa323760…` |
| 72 | `crossval/scripts/guard_selftest.py` | 47601 | `506b43d8d9b8f37c…` |
| 73 | `crossval/scripts/layout_check.py` | 22715 | `2261864587620ea5…` |
| 74 | `crossval/scripts/literature_gap.py` | 10415 | `2173fc68097c7842…` |
| 75 | `crossval/scripts/platform_check.py` | 7897 | `e1d4f8094921302a…` |
| 76 | `crossval/scripts/rare_uncertainty.py` | 35575 | `a950f1c59331480f…` |
| 77 | `crossval/scripts/realdata_adapter.py` | 8304 | `290892ddb9c8981e…` |
| 78 | `crossval/scripts/report_guard.py` | 16521 | `9d33f137991a0569…` |
| 79 | `crossval/scripts/run_units.py` | 19001 | `4b3fbb28b2ad17f0…` |
| 80 | `crossval/scripts/selection_causal.py` | 18933 | `afc836b05a6007dc…` |
| 81 | `crossval/scripts/tl_bee.py` | 6611 | `0a0f8330cbbf94c7…` |
| 82 | `crossval/scripts/verify_all.py` | 89730 | `1305b6ad4278e24d…` |
| 83 | `crossval/scripts/writing_guard.py` | 21768 | `a91be4dea7be244d…` |
| 84 | `crossval/spec/figure_spec.yaml` | 3904 | `98f3ac1914d32328…` |
| 85 | `crossval/spec/writing_spec.yaml` | 4423 | `753a1e88edf2170f…` |
| 86 | `crossval/tests/test_core.py` | 5158 | `dbef0d15618d8b2d…` |
| 87 | `crossval/tests/test_na_state.py` | 4798 | `315443a61fdc76f2…` |
| 88 | `handoff/00_HANDOFF规范.md` | 2876 | `8c951a75a60e8fb4…` |
| 89 | `handoff/handoff_chain.json` | 8226 | `2ea976d86925fc36…` |
| 90 | `handoff/scripts/handoff_guard.py` | 8621 | `256def87a0c14108…` |
| 91 | `merge_delivery.py` | 10450 | `4d3749f599f18ceb…` |
| 92 | `上机总纲_判读与经验.md` | 10063 | `7b45cdf811f4cff9…` |
| 93 | `云端服务器执行提示词_v1.0.md` | 27121 | `e27000c460d4c212…` |
| 94 | `交付规则.md` | 8079 | `7360b0f5d70330bd…` |
| 95 | `作图规范_v1.0.md` | 13182 | `c33ea773e2a04ede…` |
| 96 | `写作流程规范_v1.0.md` | 8585 | `895ffbf8430ac85c…` |
| 97 | `四角度审核报告_合集_v2.26_20260912.md` | 46386 | `cc693a6399038f3a…` |
| 98 | `框架_完整交付_v2.26_20260912.md` | 502441 | `3b4ad7777091154c…` |
| 99 | `框架_独立审核包_v2.26_20260912.md` | 171067 | `178af7c2a5f67656…` |
| 100 | `跨平台执行指导.md` | 12759 | `eaa148e7a3ee22aa…` |
| 101 | `附录_原始输出_v2.26_20260912.md` | 180215 | `247197f6890f8c98…` |

---

**核对方法（无需联网）**：

```bash
# Linux / macOS
sha256sum -c <(awk -F'|' '/^\| [0-9]+ \|/ {gsub(/[`… ]/,"",$4); print $4"  "$3}' ZIP_CONTENTS.md)

# 或逐项肉眼核对前 16 位（下表已给）
```

> 若某文件字节数或哈希不符 → **STOP 并报告**，不要继续执行（可能是传输损坏或包被改动）。
