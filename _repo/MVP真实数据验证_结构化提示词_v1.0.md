# MVP 真实数据验证 · 结构化执行提示词 v1.0

> 适用：Windows 11 / PowerShell 7 **或** Linux 沙箱
> 配套：`框架交叉验证包_v2.14_20260911.zip`
> 性质：**给执行 Agent 的完整作业指导**，无需任何框架背景即可执行
> 设计原则：**宁停勿猜** —— 任何不确定处停下报告，不得自行假设

---

# AIM · 目标

## 主目标（一句话）

用**真实公开数据**替换框架 `verify_all.py` 的合成数据，**只换数据源、不改任何统计逻辑与阈值**，回答一个问题：

> **框架的判据在真实数据上，是"能跑通"还是"拦得住"？**

## 具体目标（可判定）

| # | 目标 | 判定方式 |
|---|---|---|
| A1 | 主验证能加载真实数据并产出 `report.json` | 文件存在且可解析 |
| A2 | 判定项数是否仍为 101 | 与基线比对（允许差异，需报告） |
| A3 | 哪些判定项 PASS→FAIL / FAIL→PASS / 出现 N/A | 逐项列出 |
| A4 | 守卫在真实数据上是否仍生效 | `guard_selftest.py` 全绿 |
| A5 | 框架的「不适用 + 理由」降级路径是否可用 | N/A 项必须带非空理由 |

## 非目标（明确不做）

- ❌ 不修改任何统计方法、阈值、守卫逻辑
- ❌ 不对真实数据做"让它通过"的预处理
- ❌ 不重跑合成数据来"补"缺失判定项
- ❌ 不因某个分支报错而跳过它（必须记录为 N/A + 理由）
- ❌ 不优化模型性能（这不是建模任务）

## 判断标准（最重要）

> **真实数据上 FAIL 不是失败，是框架被发现不足。**
> **如果所有项仍全 PASS，反而需要警惕** —— 说明框架对合成数据过拟合，或真实数据触发的分支太少。

---

# TERM · 术语表

> 术语先行，避免"同一词多种理解"导致执行偏差。

| 术语 | 定义 | 易混淆点 |
|---|---|---|
| **基线** | 本仓库 `crossval/results/report.json`（Linux 合成数据结果） | 不是"正确答案"，是比对参照 |
| **判定项** | `report.json` 中每一项 PASS/FAIL/N/A 记录 | 不等于"分支" |
| **分支** | `verify_all.py` 中的一组相关判定项（如分支 8 = 硬阻断） | 一个分支含多个判定项 |
| **N/A（第三态）** | 判据对该数据不适用，**必须带非空理由** | **不是"跳过"，必须计入台账** |
| **降级** | 判据因数据不适用而走 N/A 路径 | 与"通过"完全不同 |
| **变异测试** | `guard_selftest.py` 注入违规，验证守卫抓得到 | 验证的是**守卫**，不是判据 |
| **空规** | 该触发时从未触发过的规则 | 与"通过"外观相同，实质相反 |
| **先红后绿** | 守卫先 FAIL、修复后 PASS —— 唯一能证明有效的方法 | 一直 PASS 反而是可疑信号 |
| **handoff** | 阶段间交接，须留痕（谁→谁、产物、状态） | 交接未完成 ≠ 任务完成 |
| **STOP** | 停下并报告，不自行决策 | 与"失败"不同，STOP 是正确行为 |

---

# TERM-GATEWAY · 准入网关

> **每个阶段开始前必须通过；不通过则 STOP，不得进入下一阶段。**

| Gate | 条件 | 不通过时 |
|---|---|---|
| **G0 环境** | `python --version` ≥ 3.9；`pip install -r requirements.txt` 无致命错 | STOP，报告 `platform_snapshot.json` |
| **G1 数据就位** | 目标数据集文件存在且可解压 | STOP，报告缺失文件 |
| **G2 分组可判读** | 每个样本的分组归属**明确且无歧义** | **STOP，不得猜测**（见 §分组专章） |
| **G3 基线存在** | `crossval/results/report.json` 存在 | 先跑一次合成基线 |
| **G4 守卫生效** | `guard_selftest.py` 全绿 | STOP —— 守卫不生效，后续 PASS 全不可信 |

---

# TERM-TASKLIST · 任务清单

## T0 · 环境快照（⓪）

```bash
python scripts/platform_check.py
```

产出 `results/platform_snapshot.json`。
**目的**：若后续与基线有差异，这是唯一归因依据。

## T1 · 合成基线（对照）

```bash
python scripts/verify_all.py
cp results/report.json results/report_baseline.json
```

## T2 · 真实数据准备

见 §数据集专章。产出 count 矩阵 + 分组表。

## T3 · 主验证（真实数据）

```bash
python scripts/verify_all.py --datasource real --datadir <数据目录>
```

## T4 · 守卫复验

```bash
python scripts/guard_selftest.py
```

## T5 · 差异比对

```bash
python scripts/compare_runs.py results/report_baseline.json results/report.json
```

## T6 · 报告与 handoff

产出观察报告 + 交接记录。

---

# TERM-CHECKPOINT · 检查点

| CP | 时点 | 检查内容 | 不通过 |
|---|---|---|---|
| CP1 | T0 后 | 快照含 numpy/scipy/sklearn/pandas 版本 | STOP |
| CP2 | T1 后 | 判定项数 = 101，分支 = 15 | 与基线不符则 STOP |
| CP3 | T2 后 | 矩阵非空；分组无 `unparsed` | **STOP，不得猜分组** |
| CP4 | T3 后 | `report.json` 可解析；N/A 项**均有非空理由** | 记录并报告 |
| CP5 | T4 后 | 变异测试全绿 | **STOP** —— 守卫不生效 |
| CP6 | T5 后 | 差异表已生成 | 报告 |

---

# RECHECK-POINT · 复核点

> 完成后回头查，防止"跑完就忘"。

| RP | 复核什么 | 方法 |
|---|---|---|
| RP1 | 是否**偷偷改过**框架代码 | `git diff`（或对比 `crossval/scripts/` 与 zip 内原始） |
| RP2 | 真实数据是否**真被读取**（而非仍用合成） | 检查 `report.json` 的 `data_source` 字段 |
| RP3 | N/A 项是否**被静默删除** | 判定项总数 = PASS + FAIL + N/A |
| RP4 | 是否有 `except: pass` 吞掉的错误 | 检查 stdout 无异常堆栈被吞 |
| RP5 | 数字是否被**转述** | 只贴原始输出，不写摘要 |

---

# HOOK · 钩子

> 事件触发时**自动执行**，不依赖记忆。

| Hook | 触发条件 | 自动动作 |
|---|---|---|
| **H-SUSPECT-ZERO** | 某判定项数值为 0 或空 | 标记为可疑，必须人工确认是"真为 0"还是"没跑到" |
| **H-ALL-PASS** | 真实数据下**全部** PASS | **告警**：可能过拟合或分支未激活，必须写专门说明 |
| **H-NA-EMPTY** | 出现理由为空的 N/A | 直接报错（框架已实现 `raise`），记录为缺陷 |
| **H-CRASH** | 任一脚本非零退出 | **继续跑下一条**，记录全部，不中断整体流程 |
| **H-STALE-COPY** | 发现同名文档副本 | STOP，确认哪份是权威（G-14 已覆盖） |
| **H-VERSION-DRIFT** | 文档版本 ≠ MANIFEST.version | STOP，重新索取正确版本 |

---

# LOOP · 循环

```
┌─ LOOP START ─────────────────────────────────┐
│                                               │
│  1. 执行一个 TASK                              │
│  2. 过对应 CHECKPOINT                          │
│  3. 不通过 → STOP + 报告（不自行修复）           │
│  4. 通过 → 记录 handoff-tick                   │
│  5. 还有 TASK？ → 回到 1                        │
│     否则 → 进入 ENDCHECKMARK                   │
│                                               │
└───────────────────────────────────────────────┘
```

**关键约束**：
- **禁止在 LOOP 内修改框架代码** —— 发现框架问题 → 记录，不修
- **禁止跳过失败的 TASK** —— 记录为 N/A + 理由，继续下一个
- 每轮 LOOP 结束必须有一个 handoff-tick

---

# HANDOFF-TICK · 交接节拍

> 每个阶段交接时**必须**记录，缺一即视为交接未完成。

```
[handoff-tick]
  from      : <上一阶段>
  to        : <下一阶段>
  artifact  : <产物路径>
  status    : 完成 / 在途 / 阻塞
  checksum  : <sha256 前 16 位>
  ack       : 接收方确认（未确认 = 在途，不是完成）
  next      : <后继节点 id>
```

**`ack=null` 不算交接完成。**

---

# WORKFLOW-ALLPOINT-CHECKLIST · 全流程检查清单

执行完毕后逐项打勾：

```
环境
[ ] ⓪ platform_snapshot.json 已产出
[ ] 依赖版本已记录

基线
[ ] ① 合成基线 report_baseline.json 已保存
[ ] 基线判定项数 = 101，分支 = 15

数据
[ ] ② 真实数据文件已就位
[ ] 分组表无 unparsed 项
[ ] 分组信息有权威来源（GEO 页面/元数据表），非推测

执行
[ ] ③ 真实数据主验证已跑，report.json 产出
[ ] stdout 完整保存（含所有 [PASS]/[FAIL]/[N/A] 行）
[ ] 未修改任何框架代码（RP1 已确认）

守卫
[ ] ④ guard_selftest.py 全绿
[ ] 若有守卫未生效 → 已记录，且后续结论标注"守卫未验证"

比对
[ ] ⑤ 差异表已生成
[ ] PASS→FAIL 项已逐项列出（这是最有价值的部分）
[ ] FAIL→PASS 项已逐项列出
[ ] N/A 项已逐项列出且理由非空

复核
[ ] RP1 未改代码
[ ] RP2 data_source 确为真实数据
[ ] RP3 判定项总数 = PASS+FAIL+N/A（无静默删除）
[ ] RP4 无被吞异常
[ ] RP5 返回的是原始输出，非摘要

收尾
[ ] 四个文件齐全（见下）
[ ] 每个 handoff-tick 已记录
```

---

# ENDCHECKMARK · 结束标记

完成时**必须**输出以下可机读块：

```
=== ENDCHECKMARK ===
status          : COMPLETE / STOPPED / PARTIAL
stop_reason     : <若 STOPPED，说明在哪一步、为什么>
tasks_done      : <n>/6
baseline_items  : <n>
realdta_items   : <n>
delta_pass2fail : <n>
delta_fail2pass : <n>
na_items        : <n>
na_with_reason  : <n>/<n>
mutation        : <n>/<n>
code_modified   : NO / YES(列出)
=== ENDMARK ===
```

**`code_modified: YES` 时结果作废** —— 这不再是"只换数据源"的测试。

---

# END-CONFIRM · 结束确认

以下四项**全部返回**才算完成：

| # | 文件 | 要求 |
|---|---|---|
| 1 | `results/report.json` | **全文**，不摘要 |
| 2 | `verify_all.py` 完整 stdout | 含每行 `[PASS]/[FAIL]/[N/A]` |
| 3 | `guard_selftest.py` 完整 stdout | 证明守卫在本机生效 |
| 4 | `results/platform_snapshot.json` | 环境基线，用于归因 |

**外加一段观察**（人工撰写，不可由脚本生成）：

> 真实数据暴露了哪些合成数据掩盖的问题？

---

# 附录 A · 数据集专章（GSE250167）

## A.1 基本信息

| 项 | 值 |
|---|---|
| GEO | GSE250167 |
| 物种 | *Arabidopsis thaliana*（拟南芥） |
| 类型 | 小 RNA 测序（ncRNA-Seq，10–60 nt） |
| 样本 | 8 个 GSM |
| 分组 | WT-0h / WT-3h / rns2-0h / rns2-3h |
| 格式 | `.txt.gz`，两列：sequence + raw count |

## A.2 ⚠ 关键约束：每组 n=2

8 样本 ÷ 4 组 = **每组 2 个生物学重复**。

- 主比较 "WT-3h vs WT-0h" 是 **2 vs 2**
- 框架 T02 要求**每组 ≥3** → **不满足**
- n=2 vs 2 的 t 检验自由度极低，**几乎无统计功效**

**执行要求**：

> 遇到此约束时 **STOP，不要自行决定**。
> 可选路径（均需执行方在报告中说明，但**不得自行选择**）：
> 1. 主比较 2v2 → 判据应输出 N/A + "n<3，无统计功效"
> 2. 重组为处理效应 0h(4) vs 3h(4) → 基因型成混杂，触发 T07 协变量预注册要求
> 3. 换数据集

**路径 1 才是对框架的正确压力测试**：看它能否识别 n 不足并降级，而不是硬算出一个 p 值。

## A.3 分组获取（禁止推测）

分组必须来自权威来源：
- GEO 页面样本标题（含基因型与处理条件）
- 或 GSE 矩阵文件的元数据表

`realdata_adapter.py` 已实现**宁停勿猜**：文件名无法解析 → 报错退出。

## A.4 命令

```bash
mkdir -p ~/mvp_test/data && cd ~/mvp_test/data
wget "https://ftp.ncbi.nlm.nih.gov/geo/series/GSE250nnn/GSE250167/suppl/GSE250167_RAW.tar"
tar -xvf GSE250167_RAW.tar
cd crossval
python scripts/verify_all.py --datasource real --datadir ~/mvp_test/data
```

---

# 附录 B · 执行铁律

1. **不改代码让它通过** —— 你是来照镜子的，不是来修东西的
2. **报错不中断** —— 记录后继续下一条
3. **必须贴完整 stdout** —— 只给 JSON 会重蹈"FAIL 被汇总写成 PASS"
4. **分组不猜** —— 不确定就 STOP
5. **N/A 必须带理由** —— 无理由的 N/A 是框架禁止的静默删除
