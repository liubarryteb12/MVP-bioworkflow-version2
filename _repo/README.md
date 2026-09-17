# mvp-bioframework-test · 云端验证仓库

> 内容：**生信分析 + SCI 写作元框架 v2.26 完整交付包**（平铺在仓库根）+
> GSE31210 原始数据。用于在 GitHub Actions 上完成框架的云端自证（官方 T1–T11 流程）。

## 结构

```
├── .github/workflows/crossval_verify.yml   ← 云端验证工作流（手动触发）
├── MANIFEST.json / ZIP_CONTENTS.md          ← v2.26 交付台账（版本/基线/sha256）
├── 框架_独立审核包_v2.26_20260912.md 等 8 份交付文档
├── crossval/                                ← 24 个验证脚本 + tests + spec + schema + figures
├── handoff/                                 ← 交接链 + handoff_guard
├── GSE31210_series_matrix.txt.gz            ← 真实数据（57MB，待 U00→U01 流水线接入）
└── _archive_v2.24_partial/                  ← 旧版残缺骨架归档（含自研 MVP 脚本，待评审）
```

## 怎么跑

Actions → `crossval-verify-T1-T11` → Run workflow。
两个并行 job：**框架自证 T1–T11**（约 5–10 分钟）+ **GSE31210 数据预检**（约 1 分钟）。
跑完下载 Artifacts：`crossval-outputs`（全部原始 stdout + JSON 台账）与 `gse31210-preflight`。

## 铁律

1. 不修改 `crossval/` 内任何框架代码（改了本次验证作废）。
2. FAIL 是结果不是故障，不重试（只有崩溃/依赖失败重试 1 次）。
3. 判读看完整 stdout，不看汇总。
