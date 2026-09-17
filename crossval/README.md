# 生物信息学分析框架 · 交叉验证包

给第二个 agent 独立复跑，验证框架判据是否真的拦得住它宣称要防的错。

> **数字纪律**：本文件**不自行维护数字**。下文所有计数均派生自
> `results/report.json` / `results/guard_results.json` / `results/mutation_results.json`，
> 权威值见 `../MANIFEST.json` 的 `verification` 与 `guards` 字段。
> v2.26 修订：本文件此前长期停留在 v1.x 时代（33/33、8 个分支、scripts/ 只有
> 1 个脚本），是包内**最容易被执行方第一眼读到**却最不准的文档。

---

## 一、快速开始（Windows 11 + PowerShell 7 或 Linux）

```bash
# 1 进入目录
cd <解压目录>/crossval

# 2 建虚拟环境（推荐，避免污染）
python -m venv .venv          # Windows
python3 -m venv .venv         # Linux
# Windows: .\.venv\Scripts\Activate.ps1
# Linux  : source .venv/bin/activate

# 3 装依赖
pip install -r requirements.txt

# 4 跑全套验证（约 1–2 分钟）
python scripts/verify_all.py

# ★ 推荐入口：按"功能单元"一块一块跑（绿了才进下一块）
python scripts/run_units.py                 # 全部 10 单元，遇红即停
python scripts/run_units.py --list          # 只看单元清单
python scripts/run_units.py --only U3       # 只跑一个单元
python scripts/run_units.py --from U5       # 从第 5 块开始

# 只想看某一组
python scripts/verify_all.py --only 8     # 只跑分支 8
python scripts/verify_all.py --quick      # 跳过耗时项
```

## 一·A 功能单元（推荐用法）

| 单元 | 名称 | 一句话目标 | 通过判定（gate 自动读台账） |
|---|---|---|---|
| U1 | 环境与依赖 | 解释器能导入全部依赖 + 环境快照落盘 | 快照生成 |
| U2 | 判据主验证 | 21 分支全部判定项 → `report.json` | 222/222 · 失败 0 |
| U3 | 排版与作图 | 图件规格 / 结构 / 参考文献 / claim 升级 | 70/70 |
| U4 | 写作层 | WP-1~9 + NC-1~7 | 43/43 · 不适用 0 |
| U5 | 三格式导出 | 纯文 / 纯图 / 合一三版本互相一致 | 10/10 · 不适用 0 |
| U6 | 工作证据链 | 14 个交接节点 + 接收确认位 | 11/11 |
| U7 | 单元测试 | 抓脚本自身实现 bug | 全 passed |
| U8 | 跨文档一致性 | 文档声称 == 台账 | 77/77 · 10/10 |
| U9 | 守卫自证 | 变异测试，抓不到 = 空规 | 66/66 · 家族 21/21 |
| U10 | 判据消融 | 哪条判据在干活 | PASS + 自测 C-1~C-4 |

> **遇到红就停**：默认在第一个 gate 不过的单元停下，并打印"失败处置"提示。
> 这是刻意的 —— 一口气跑完十块再回头找，比一块一块排除难得多。

**若 PowerShell 报"禁止运行脚本"**：
```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

> ⚠ **中文 Windows 必做**：`$env:PYTHONUTF8='1'`（Linux：`export PYTHONUTF8=1`）。
> 缺这一步，`verify_all.py` 可能在最接近终点处因 GBK 无法编码 `I²` 而崩溃、
> `report.json` 不落盘、整轮证据作废。

---

## 二、会看到什么

跑完输出 `results/report.json` 与 `results/report.md`。

**通过的样子**：
```
判定项 222/222 通过, 失败 0 项, 不适用 0 项, 覆盖分支 21 个
```

**若出现 FAIL** —— 不要急着改脚本，先看是哪种：

| 情况 | 含义 | 怎么办 |
|---|---|---|
| 判据项 FAIL | **框架判据可能有问题**，这是交叉验证的价值 | 记录实测值并回报 |
| 环境项 MISS | 依赖没装 | `pip install -r requirements.txt` |
| 随机波动致 FAIL | 种子固定，理论上不应发生 | 回报，可能是平台差异 |

> **重要**：本套件固定了随机种子（20260910），**同代码不同平台结果应完全一致**。
> 若出现数值差异，说明存在平台相关的非确定性，这本身就是一个值得回报的发现。

### 2.1 守卫有效性（**不要省这一步**）

```bash
python scripts/guard_selftest.py
```

它向文档 / 源码 / 图目录**现场注入已知违规**，验证守卫抓得到。当前基线：
**66 项变异用例全部生效，家族覆盖 21/21**。

**退出码有三态，必须分清**（v2.26 新增第 3 态）：

| 码 | 含义 | 处置 |
|---|---|---|
| 0 | 全部守卫均证明过自己能抓到违规 | 正常 |
| 1 | 存在空规（规则从没跑到过应触发的输入） | 真发现，回报 |
| **2** | **环境错误** —— 子守卫没跑起来，本次结果无效 | 先修环境，**别当空规报** |

> **为什么加第 3 态**：子守卫原以硬编码 `python3` 启动，而 Windows 的 venv
> **不生成 `python3.exe`**（只有 `python.exe`），于是 `python3` 会落到 PATH 上
> 另一个没装依赖的解释器 → ImportError → 输出里一个判定行都没有 →
> **18 个守卫家族被误报为"空规"**。这是「守卫没跑」与「规则没生效」的混淆，
> 会把审核方引去查根本不存在的空规。现改用 `sys.executable`，并把两者分开报。

---

## 三、包内容

```
crossval/
├─ README.md                     本文件
├─ requirements.txt              依赖（单一来源，钉实测版本）
├─ INVARIANTS.md                 全局不变量（每次调用必须注入）
├─ scripts/                      25 个脚本
│   ├─ run_units.py              ★ 功能单元执行器（10 单元，遇红即停）
│   ├─ verify_all.py             ★ 主验证入口（21 分支 → report.json）
│   ├─ guard_selftest.py         ★ 变异测试（守卫是否空规）
│   ├─ consistency_guard.py      跨文档一致性（G-1 ~ G-14）
│   ├─ report_guard.py           审核报告守卫（R-1 ~ R-8）
│   ├─ layout_check.py           排版 / 作图 / 期刊条目检查
│   ├─ writing_guard.py          写作层 WP-1~9 + NC-1~7
│   ├─ export_guard.py           三格式导出一致性
│   ├─ ablation.py               判据消融（哪条判据在干活）
│   ├─ gen_appendix.py           生成附录（**必须最后跑**）
│   ├─ platform_check.py         环境快照（跨平台差异归因）
│   ├─ compare_runs.py           结果比对
│   ├─ compare_platforms.py      环境比对
│   ├─ figure_kit.py             四格式导出 + 色盲模拟
│   ├─ applicability_gate.py     适用性闸门（不适用 + 理由）
│   ├─ realdata_adapter.py       真实数据适配（宁停勿猜）
│   ├─ conclusion_guard.py       结论守卫 T26–T30
│   ├─ rare_uncertainty.py       稀有事件 / 不确定性 T33–T35
│   ├─ selection_causal.py       选择泄露 / 孟德尔随机化 T31–T32
│   ├─ component_ablation.py     组件增量消融 T36
│   ├─ dormant_check.py          休眠判据激活用例
│   ├─ data_ethics.py            数据正义 / 治理 T29–T30
│   ├─ literature_gap.py         文献驱动判据 T21–T25
│   ├─ conclusion_branch.py      分支 17 结论层
│   └─ tl_bee.py                 迁移学习小样本 T13b 扩展
├─ schema/criteria.yaml          ★ 51 条判据的唯一权威源
├─ spec/                         figure_spec.yaml / writing_spec.yaml
├─ tests/                        单元测试（pytest）
├─ demo/                         合规样例稿 + 变异注入锚点 + 导出夹具
├─ figures/{demo,samples}/       图件样本（目检用）
├─ framework/                    框架演进过程文档（T01–T37 定稿证据链）
└─ results/                      输出目录（台账在此，是数字唯一来源）
```

> `handoff/` 与三份版本化交付文档在**上一级目录**，不在 `crossval/` 内。

> **注意**：`framework/` 下是**过程文档**（S15–S21、A2C 回执、四份视角审核报告），
> 供追溯"判据为什么这么定"，**不是执行依据**。执行依据是
> `schema/criteria.yaml` + `framework/判据权威版本.md`。冲突消解顺序：
> 判据权威版本 > S20/S21 > S15-C > S19（已废弃）> A2C 早期文档。

---

## 四、覆盖的 21 个分支（要点）

| # | 分支 | 验什么 | 关键预期 |
|---|---|---|---|
| 1 | 阈值漏检 | 多重检验家族 | 未校正命中 > 10 → BH 后 ≈ 0 |
| 2 | F3 无增量 | ΔAUC < 0.05 | 正但不足 → 触发 F3 |
| 3 | 校准不合格 | 训练内 vs CV | 训练内恒 ≈ 1（陷阱），CV 不覆盖 1 |
| 4 | 区间冲突 | DCA 全区间 | 未校准时区间内 vs 全区间胜出率分歧 |
| 5 | R5 方向相反 | 外部集 | 两数据集 OR 方向相反 |
| 6 | F1 方向不一致 | 程序定义 | 换成员集漂移 > 10% |
| 7 | 目检不合规 | 4 类 PDF | 位图 / Type3 / 无文本层 全检出 |
| 8 | 硬阻断 | 三类 | 伪重复 / 泄露 / 终点不等价 |
| 9–14 | 预测、缺失、批次、单细胞、报告规范、空间组学 | T06 / T08 / Y6 / T15–T20 | 各带双向夹具 |
| 15 | 条文可执行性 | 纯条文是否含可判定要素 | 三者缺一即空规 |
| 16 | 文献驱动 | T21–T25 | 违规项应拦 / 合规项应放行 |
| 17 | 结论守卫 | T26–T30 | 13 篇论文驱动的实证判据 |
| 18 | 选择泄露 / MR | T31–T32 | 未声明选择位置 → 判"判不了"，**不默认 nested** |
| 19 | 预测不确定性 | T34 | 信息性 corr 0.892 vs 无信息 −0.031 |
| 20 | 多组学整合 | T35 | MTAG 循环论证 / LDSC intercept 偏离未校正 |
| 21 | 稀有事件 | T33 | Wilson CI 上下界差 5.48 倍 → 硬阻断 |

外加：**种子稳健性**、**合成值隔离守卫**、**判据消融（T37 骨架 / 休眠比例）**。

---

## 五、给验证方的三句话

1. **你不需要懂这个框架** —— 跑脚本看 PASS/FAIL 就行，每个判定项都写了预期值。
2. **FAIL 是有效结果，不是你的错** —— 尤其分支判据 FAIL，那是这次交叉验证的目的。
3. **所有数字都是合成值**，标记 `MVP 合成值·非项目实际值`，不得用于任何真实结论。

---

## 六、重点复核建议

若时间有限，优先看这 5 项（最可能暴露框架问题）：

1. **分支 3** —— 训练内校准斜率是否真的恒 ≈ 1（若不是，该判据的依据就错了）
2. **分支 4** —— 区间冲突能否复现（若不能，全区间强制报告的必要性存疑）
3. **分支 7** —— Type3 与 TrueType 在你的环境能否区分（字体可用性差异可能影响）
4. **分支 8C** —— I² 是否 > 50%（这是"禁止合并"判据的实证基础）
5. **分支 6** —— 漂移是否 > 10%（这是"程序定义移出敏感性矩阵"裁决的依据）

---

## 七、已知平台差异（**这些不算失败，不要修**）

| 项 | 说明 |
|---|---|
| 中文字体 | Windows 用 Microsoft YaHei，Linux 用 WenQuanYi Micro Hei，脚本自动探测；都没有则回退 DejaVu Sans。**属预期** |
| PDF 检测 | **纯 pypdf 解析，不调用 poppler**，Win11 无需装任何额外工具 |
| 目检样本 | 首次运行自动生成到 `figures/samples/`，删掉可重生成 |
| 路径分隔符 | 代码已处理 `\` 与 `/`；若发现**新的**路径错误，那是真问题，请报告 |
| FS 大小写 | Windows 不敏感、Linux 敏感。相关守卫已按此加固 |
| matplotlib 后端 | 保持 `Agg`，**不要**改成 `TkAgg` |
| 控制台编码 | **不属于"正常差异"**。未设 `PYTHONUTF8=1` 可能输出被替换的字符；若抛 `UnicodeEncodeError` → 真问题，请报告 |

---

> 所有数字均为 `MVP 合成值·非项目实际值`，禁止进入真实台账或稿件。

---

## 八、排版层 V5-P / V5-C

```bash
python scripts/layout_check.py --figdir figures/demo
```

**默认休眠**，排版阶段激活。两块：
- **V5-P** 排版执行规范（怎么做：图件规格、结构、参考文献、三条禁令）
- **V5-C** 排版检查（做得对不对：引用完整性、数字一致、claim 未升级、图件规格、期刊条目）

基线 **70/70**（见 `results/layout_report.json`）。核心是 **C-3 claim 升级检出** ——
压缩摘要时删掉"候选 / 探索性 / 待验证"腾字数，是最隐蔽的违规，必须逐词比对。

> 先跑 `python scripts/verify_all.py` 生成图样本，再跑 layout_check 可验 C-4。

---

## 九、要改代码吗

**不要。** 你是来照镜子的，不是来修东西的。
若某条命令报错，**原样贴出完整 stdout 并继续跑下一条** ——
报错本身是有价值的结果，它说明这套代码在该平台上存在可移植性问题。

完整回报格式见 `../跨平台执行指导.md` §5，或 `../云端服务器执行提示词_v1.0.md` §5。
