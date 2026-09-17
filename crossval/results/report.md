# 交叉验证报告

生成时间: 2026-09-12 20:34:31
环境: Python 3.13.14 · Windows-11-10.0.26200-SP0

**判定 222/222 通过,失败 0 项,不适用 0 项,覆盖分支 21 个**

| 分支 | 项 | 实测 | 预期 | 结果 |
|---|---|---|---|---|
| 1 | 未校正产生假阳性(应>10) | 26 | >10 | PASS |
| 1 | BH 校正后应≈0 | 0 | <=2 | PASS |
| 1 | 校正必要性(未校正>BH) | True | True | PASS |
| 2 | ΔAUC 低于阈值 → 触发 F3 | 0.0397 | <0.05 → F3 | PASS |
| 2 | ΔAUC 为正但不足(典型陷阱) | True | True(易误判为有增量) | PASS |
| 3 | bootstrap 有效次数充足 | 1000 | >=950 | PASS |
| 3 | bootstrap 内嵌套 CV(不复用外层) | True | True | PASS |
| 3 | 训练内斜率恒≈1(陷阱) | 1.001 | 0.9~1.1 | PASS |
| 3 | CV 斜率偏离 1 | 0.841 | !=1 | PASS |
| 3 | T13b 判据(CI 覆盖1) | False | False → 不得用于个体风险预测 | PASS |
| 4 | 样本内准确率虚假完美(忘记CV的陷阱) | 1.0 | >0.90 | PASS |
| 4 | 高维过拟合样本外AUC崩塌(过拟合代价) | 0.544 | < 0.674 | PASS |
| 4 | 过拟合模型概率更极端(过度自信) | 0.991 | > 0.878 | PASS |
| 4 | 过拟合训练集准确率异常高(分离) | 1.0 | >0.90 | PASS |
| 4 | 已校准模型:全区间胜出率≥0.5 | True | True | PASS |
| 4 | 未校准模型:全区间胜出率<0.5 → 触发 F3 | 0.253 | <0.5 → F3 | PASS |
| 4 | 未校准:预注册区间内存在≥10点连续负区间 → 判不确定 → F3 | 21 | >=10 → F3 | PASS |
| 4 | 已校准:连续负区间应短于10点(不触发) | 8 | <10 | PASS |
| 4 | 新判据判别力:未校准连续负区间显著长于已校准 | 21 > 8 | 未校准>已校准 | PASS |
| 4 | 全区间勉强过线时,判据2仍可捕获(补漏检) | True | True | PASS |
| 4 | 边界情形:全区间≥0.5 时判据1不触发 | True | True(判据1失效) | PASS |
| 4 | 已校准模型 NB 差具临床量级(中位\|Δ\|≥0.01) | 0.0114 | >=0.01 | PASS |
| 4 | 报告预注册区间内 NB 差最小值(强制项) | -0.0273 | 已记录 | PASS |
| 4 | [自证]胜出率高≠临床有意义(绝对量级独立判据) | 中位0.0114/最小-0.0273 | 须与胜出率并列报告 | PASS |
| 4 | 边界情形:判据2仍能捕获(增量价值) | 13 | >=10 → F3 | PASS |
| 4 | [自证]最优子区间≈1.0 为构造性必然(故不作判据) | 1.0 | ≈1.0(无效指标) | PASS |
| 5 | 外部集方向相反 → R5 | False | False | PASS |
| 5 | 方向相反不可写'复现' | True | True | PASS |
| 6 | 重叠度构造正确(≈1/3) | 32.5% | 30%~36% | PASS |
| 6 | 换成员集漂移 >10% | 33.0 | >10% | PASS |
| 6 | 漂移普遍且巨大(多种子最小值仍>10%) | 16.3 | >10% | PASS |
| 6 | 漂移幅度远超旧称的 13.9%(旧值已作废) | 33.0 | >13.9 | PASS |
| 6 | **方向翻转为种子依赖,非必然** | 5/12=42% | 0<rate<1 → 不得称'且翻转' | PASS |
| 6 | 重叠度指标明确为 Jaccard(非相对重叠) | 19.4% | <=0.5 | PASS |
| 6 | [口径差异]相对重叠 vs Jaccard 数值不同(故须写明) | 32.5% vs 19.4% | 两者不等 → 条文须指定 | PASS |
| 6 | 实质变更:对称差占比 ≥0.5(排除'部分归零'中间态) | 80.6% | >=0.5 | PASS |
| 6 | 程序定义非稳健性参数(裁决依据) | 33.0 | >5% 即说明敏感 | PASS |
| 7 | sample_ok_truetype.pdf 判定 | 合规 | 合规 | PASS |
| 7 | sample_bad_bitmap.pdf 判定 | 不合规:位图/无文本层 | 不合规 | PASS |
| 7 | sample_bad_type3.pdf 判定 | 不合规:Type3非矢量字体 | 不合规 | PASS |
| 7 | sample_bad_notext.pdf 判定 | 不合规:无文本层 | 不合规 | PASS |
| 7 | sample_bad_page2_bitmap.pdf 判定 | 不合规:位图 | 不合规 | PASS |
| 7 | 位图检测不依赖 pdfimages(poppler) | True | True | PASS |
| 7 | Type3 与 TrueType 可区分 | True | True | PASS |
| 8 | 细胞级 p 极小(陷阱) | 4.2e-14 | <1e-6 | PASS |
| 8 | 患者级不显著 → 伪重复 | 0.28 | >0.05 | PASS |
| 8 | 推断单位必须为 donor | True | True | PASS |
| 8 | 泄露致 AUC 虚高 | 0.112 | >0.10 → 严重 | PASS |
| 8 | T10 筛选须在训练折内 | True | True | PASS |
| 8 | 两队列效应差 >1.0 | 1.85 | >1.0 | PASS |
| 8 | 合并前判据A:事件率差异 <15%(独立判据) | 12.7% | <15% | PASS |
| 8 | 合并前判据B:方向一致(效应符号相同) | OR_A=3.085, OR_B=1.238 | 同号 | PASS |
| 8 | 合并前判据C:终点等价性未通过 → 一票否决 | MoCA vs MMSE 不等价 | 不等价即禁合并 | PASS |
| 8 | I² 分层:>50% 强制报告异质性来源;>75% 禁合并主分析 | 96.6 | 本例>75 → 禁合并 | PASS |
| 8 | [自证]k=2 时 I² 不稳(df=1,Q 期望=1)→ 不得作唯一判据 | I2=96.6% 但 df=1 | 须配A/B/C | PASS |
| 8 | I² >50% → 禁止合并 | 96.6 | >50 | PASS |
| 8 | 合并 OR 居中(易误读为一致) | 1.834 | 介于两者之间 | PASS |
| T15 | 核/单核 mito% 分布显著不同 | 5.1% vs 0.9% | 差异显著 | PASS |
| T15 | 单阈值跨类型套用会失效(须分层) | 剔除率差 10.0% | >5% | PASS |
| T15 | 误用单细胞阈值(10%)→ 单核几乎不过滤 | 0.0% | <2% → 污染漏检 | PASS |
| T15 | 误用严格阈值(2%)→ 单核过度剔除 | 11.2% vs 宽松 0.0% | 严格>>宽松 → 双向失效 | PASS |
| T15 | 故阈值必须按细胞/核类型分层设定 | True | True | PASS |
| T16 | 细胞级 p 极小(伪重复陷阱) | 5.3e-08 | <1e-3 | PASS |
| T16 | donor 级不显著 → 伪重复被拦住 | 0.263 | >0.05 | PASS |
| T16 | 细胞数<10 的 donor-celltype 被排除 | 2 | >=1 被排除 | PASS |
| T16 | 稀有类型未达标 → 不做推断(非仅标注) | True | True | PASS |
| T17 | 倍数扰动未改变与结局的关联(故无对照价值) | 0.0 | ≈0 → 无对照价值 | PASS |
| T17 | 倍数扰动改变尺度(SD 比≈2,引入混淆) | 2.0 | ≈2.0 | PASS |
| T17 | 置换/分位数扰动使关联归零(干净零对照) | 0.02 | <0.05 | PASS |
| T17 | 置换保留边缘分布(SD 比≈1,无尺度混淆) | 1.0 | 0.9~1.1 | PASS |
| T17 | 计算扰动不构成功能验证 | True | True(措辞纪律) | PASS |
| 10 | 竞争事件比例>10% → 强制处理 | 47.3% | >10% | PASS |
| 10 | KM(忽略竞争)系统高估累积发生率 | 组0 +0.285, 组1 +0.136 | 两组均高估 | PASS |
| 10 | 忽略竞争会扭曲组间差异(非仅整体高估) | 0.148 | >0.01 → 结论可被改变 | PASS |
| 10 | 低EPV 乐观度显著大于充足EPV | 0.132 > 0.006 | 低EPV更乐观 | PASS |
| 10 | 低EPV 时 EPV<5(触发强制正则化) | True | True | PASS |
| 10 | 乐观度随 EPV 单调下降(判据可执行) | 0.132 > 0.058 > 0.006 | 单调下降 | PASS |
| 10 | 正常项目判 FEASIBLE | FEASIBLE | FEASIBLE | PASS |
| 10 | 多项不可行 → INFEASIBLE(可输出'数据不支持') | INFEASIBLE | INFEASIBLE | PASS |
| 10 | 无结局变量 → INFEASIBLE | INFEASIBLE | INFEASIBLE | PASS |
| 10 | 单因素可补救 → 降级而非停止 | FEASIBLE_WITH_DOWNGRADE | FEASIBLE_WITH_DOWNGRADE | PASS |
| 15 | Y6 含可判定要素(predicate/rubric) | True | True | PASS |
| 15 | Y6 标注输入或阶段标签 | True | True | PASS |
| 15 | Y6 声明不通过动作 | True | True | PASS |
| 15 | 空间 含可判定要素(predicate/rubric) | True | True | PASS |
| 15 | 空间 标注输入或阶段标签 | True | True | PASS |
| 15 | 空间 声明不通过动作 | True | True | PASS |
| 15 | MNAR 含可判定要素(predicate/rubric) | True | True | PASS |
| 15 | MNAR 标注输入或阶段标签 | True | True | PASS |
| 15 | MNAR 声明不通过动作 | True | True | PASS |
| 15 | TRIPOD 含可判定要素(predicate/rubric) | True | True | PASS |
| 15 | TRIPOD 标注输入或阶段标签 | True | True | PASS |
| 15 | TRIPOD 声明不通过动作 | True | True | PASS |
| 15 | T08 含可判定要素(predicate/rubric) | True | True | PASS |
| 15 | T08 标注输入或阶段标签 | True | True | PASS |
| 15 | T08 声明不通过动作 | True | True | PASS |
| 15 | 无空规(每条判据均有 predicate 或 rubric) | 无 | 无 | PASS |
| 16 | [T21] 文献17 Table1 RA(16 vs 4) | 实际=FAIL | 期望=FAIL | PASS |
| 16 | [T21] 文献17 Table1 T1D(10 vs 6) | 实际=灰区(不得判通过) | 期望=灰区(不得判通过) | PASS |
| 16 | [T21] 文献17 Table1 MS(99 vs 45) | 实际=PASS | 期望=PASS | PASS |
| 16 | [T21] 合规对照(50 vs 50) | 实际=PASS | 期望=PASS | PASS |
| 16 | [T22] 文献18 训练.666/验证.560 | 实际=FAIL | 期望=FAIL | PASS |
| 16 | [T22] 合规对照(0.80/0.78) | 实际=PASS | 期望=PASS | PASS |
| 16 | [T23] 文献19 QC(2.5/5/25%,有声明) | 实际=PASS | 期望=PASS | PASS |
| 16 | [T23] 文献19 变体(阈值不同,无声明) | 实际=FAIL | 期望=FAIL | PASS |
| 16 | [T23] 合规对照(统一2.5%) | 实际=PASS | 期望=PASS | PASS |
| 16 | [T24] 文献19 跨物种验证(mouse→human) | 实际=PASS | 期望=PASS | PASS |
| 16 | [T24] 同队列随机split(典型泄露) | 实际=FAIL | 期望=FAIL | PASS |
| 16 | [T25] 文献21 手动按位置选ROI | 实际=FAIL | 期望=FAIL | PASS |
| 16 | [T25] 文献19 盲法选区 | 实际=PASS | 期望=PASS | PASS |
| 16 | 灰区项数(T21 小样本临界,须声明) | 1 | >=1(夹具含 T1D 10v6) | PASS |
| 16 | 文献夹具全部按预期拦截/放行(无空规) | 全部符合 | 全部符合 | PASS |
| 17 | T26 真信号嵌入:应识别为信号 | pass\|sig_frac=0.643,median_p=0.002 | pass/warn | PASS |
| 17 | T26 弱信噪比嵌入:应降级(探索级) | fail\|sig_frac=0.207,median_p=0.067 | fail | PASS |
| 17 | T26 噪声冒充嵌入:应被拒(红) | fail\|sig_frac=0.003,median_p=0.505 | fail | PASS |
| 17 | T26 形状不匹配:应判不适用 | na | na | PASS |
| 17 | T27 微调合规(n_calib=30) | pass\|策略=微调,n_calib=30,overlap=0.72 | pass | PASS |
| 17 | T27 微调但 n_calib=8(<20) | fail\|策略=微调,n_calib=8,overlap=0.72 | fail | PASS |
| 17 | T27 零样本但调过参(泄漏) | fail\|策略=零样本迁移,overlap=0.60 | fail | PASS |
| 17 | T27 从头训练却声称'跨数据集复现' | fail\|策略=从头训练,overlap=0.60 | fail | PASS |
| 17 | T27 零样本合规 | pass\|策略=零样本迁移,overlap=0.65 | pass | PASS |
| 17 | T27 未提供批次诊断 | fail\|策略=零样本迁移 | fail/warn | PASS |
| 17 | T28 真实模块结构:扰动应可复现 | warn\|模块富集 p=0.0204,rho=0.412,对照rho=0.037 | pass/warn | PASS |
| 17 | T28 假阴性对照(同模块):应判特异性不成立 | fail\|模块富集 p=0.0204,rho=0.226,对照rho=0.762 | fail | PASS |
| 17 | T28 虚拟KO写'功能验证':应拦 | fail | fail | PASS |
| 17 | T29 完整举证:应通过 | pass\|子群体数=3,高风险群体=1,退出选项=True,隐私缺失已报告=True | pass | PASS |
| 17 | T29 声称充分却无子群样本量+未评风险却称可临床转化 | fail\|无举证 | fail | PASS |
| 17 | T29 纯方法学:应判不适用 | na | na | PASS |
| 17 | T29 N/A 空理由应抛错 | ValueError | raise | PASS |
| 17 | T30 完整声明:应通过 | pass\|流向=本地设备内,特征可见=True,可撤回=True,二次使用=仅限本研究,合同约束,匿名方法=差分隐私 | pass | PASS |
| 17 | T30 称匿名无方法 + GDPR无法条:应拦 | fail\|流向=本地,特征可见=True,可撤回=True,二次使用=仅限本研究 | fail | PASS |
| 17 | T30 公开二次数据:应判不适用 | na | na | PASS |
| 20 | [T31] 肺癌4基因(Wen 2022 BMC Cancer 22:193) | 实际=不通过 | 期望=不通过 | PASS |
| 20 | [T31] 卵巢癌2基因(Liang 2021 Front Oncol 11:711020) | 实际=不通过 | 期望=不通过 | PASS |
| 20 | [T31] ROMO1(Wang 2025 FIG 25:91) | 实际=不通过 | 期望=不通过 | PASS |
| 20 | [T31] 合规:嵌套 CV | 实际=通过 | 期望=通过 | PASS |
| 20 | [T31] 合规:独立选择集 | 实际=通过 | 期望=通过 | PASS |
| 20 | [T31] 声称 nested 但无折数 → 判不了 | 实际=不适用 | 期望=不适用 | PASS |
| 20 | [T31] 未声明选择位置 → 判不了 | 实际=不适用 | 期望=不适用 | PASS |
| 20 | [T31] 非建模研究 → N/A | 实际=不适用 | 期望=不适用 | PASS |
| 20 | [T31] WCMI:选了20个特征但完全未报冗余度 | 实际=不通过 | 期望=不通过 | PASS |
| 20 | [T31] \|r\|>0.9 占比 45% 未去冗余 | 实际=不通过 | 期望=不通过 | PASS |
| 20 | [T31] \|r\|>0.9 占比 12%(灰区) | 实际=通过 | 期望=通过 | PASS |
| 20 | [T31] \|r\|>0.9 占比 6%(可解释特征集) | 实际=通过 | 期望=通过 | PASS |
| 20 | [T32] ROMO1 two-sample MR(Wang 2025) | 实际=不通过 | 期望=不通过 | PASS |
| 20 | [T32] 弱工具变量 F=8 | 实际=不通过 | 期望=不通过 | PASS |
| 20 | [T32] 多效性存在但未用稳健方法 | 实际=不通过 | 期望=不通过 | PASS |
| 20 | [T32] two-sample 祖源不一致 | 实际=不通过 | 期望=不通过 | PASS |
| 20 | [T32] 措辞越界:证明因果 | 实际=不通过 | 期望=不通过 | PASS |
| 20 | [T32] 合规 MR | 实际=通过 | 期望=通过 | PASS |
| 20 | [T32] 非 MR 研究 → N/A | 实际=不适用 | 期望=不适用 | PASS |
| 20 | T31/T32 夹具全部按预期拦截或放行(无空规) | 全部符合 | 全部符合 | PASS |
| 20 | [T13b扩展] 合规:小样本+预注册 alpha | 实际=pass | 期望=pass | PASS |
| 20 | [T13b扩展] 事后调 alpha → R3 | 实际=fail | 期望=fail | PASS |
| 20 | [T13b扩展] 借用但无 alpha | 实际=fail | 期望=fail | PASS |
| 20 | [T13b扩展] 借用但无确定方法 | 实际=fail | 期望=fail | PASS |
| 20 | [T13b扩展] 声明未借用 | 实际=pass | 期望=pass | PASS |
| 20 | [T13b扩展] 小样本但未声明 → 判不了 | 实际=na | 期望=na | PASS |
| 20 | [T13b扩展] 大样本 → 不触发 | 实际=na | 期望=na | PASS |
| 20 | 数值反例:事后调 alpha 的偏差恒大于预注册 | 0.000→0.188,0.000→0.168,0.050→0.202 | 全部 偏差(事后调) > 偏差(预注册) | PASS |
| 21 | [T33] 5/10000 Treg 声称显著下降(Wilson CI) | 实际=不通过 | 期望=不通过 | PASS |
| 21 | [T33] 120/10000 Treg(比例仍<5%,CI 可辨) | 实际=通过 | 期望=通过 | PASS |
| 21 | [T33] MAF=0.5% 但未报 CI 且无 k/n | 实际=不适用 | 期望=不适用 | PASS |
| 21 | [T33] 2 年数据估 20 年一遇极端事件 | 实际=不通过 | 期望=不通过 | PASS |
| 21 | [T33] 2 年数据 + 已声明 GPD 外推 | 实际=不通过 | 期望=不通过 | PASS |
| 21 | [T33] 39 年数据估 20 年一遇(可解析) | 实际=通过 | 期望=通过 | PASS |
| 21 | [T33] n=50 估 <1% 频率 → 判不了 | 实际=不适用 | 期望=不适用 | PASS |
| 21 | [T33] 非稀有事件研究 → N/A | 实际=不适用 | 期望=不适用 | PASS |
| 21 | [T34] 只报平均 RMSE,无 per-sample 不确定性 | 实际=不通过 | 期望=不通过 | PASS |
| 21 | [T34] 有不确定性但未报与误差的关系 | 实际=不通过 | 期望=不通过 | PASS |
| 21 | [T34] corr=0.6 但未分层报告 | 实际=不通过 | 期望=不通过 | PASS |
| 21 | [T34] corr=0.6 且已分层 | 实际=通过 | 期望=通过 | PASS |
| 21 | [T34] 声称个体风险但 corr≈0(不确定性无信息) | 实际=不通过 | 期望=不通过 | PASS |
| 21 | [T34] 高不确定亚群未声明 | 实际=不通过 | 期望=不通过 | PASS |
| 21 | [T34] 非预测研究 → N/A | 实际=不适用 | 期望=不适用 | PASS |
| 21 | [T35] ROMO1:LDSC+MTAG,intercept 未报告 | 实际=不通过 | 期望=不通过 | PASS |
| 21 | [T35] LDSC intercept=1.2 未校正 | 实际=不通过 | 期望=不通过 | PASS |
| 21 | [T35] LDSC intercept=1.02(接近 1) | 实际=通过 | 期望=通过 | PASS |
| 21 | [T35] MTAG 循环论证 | 实际=不通过 | 期望=不通过 | PASS |
| 21 | [T35] coloc H4=0.9 但先验未声明 | 实际=不适用 | 期望=不适用 | PASS |
| 21 | [T35] coloc H4=0.9 + 先验已声明 | 实际=通过 | 期望=通过 | PASS |
| 21 | [T35] 未用多组学工具 → N/A | 实际=不适用 | 期望=不适用 | PASS |
| 21 | [V4MODAL] in silico + in vitro 却声称治疗有效 | 实际=不通过 | 期望=不通过 | PASS |
| 21 | [V4MODAL] in silico + in vitro 声称细胞模型活性 | 实际=通过 | 期望=通过 | PASS |
| 21 | [V4MODAL] 仅 in silico 声称候选 | 实际=通过 | 期望=通过 | PASS |
| 21 | [V4MODAL] 仅 in silico 却声称临床效用 | 实际=不通过 | 期望=不通过 | PASS |
| 21 | [V4MODAL] 全链条达成 L4 | 实际=通过 | 期望=通过 | PASS |
| 21 | [V4MODAL] 未报告任何验证证据 → 判不了 | 实际=不适用 | 期望=不适用 | PASS |
| 21 | [V4MODAL] 非跨模态研究 → N/A | 实际=不适用 | 期望=不适用 | PASS |
| 21 | T33/T34/T35/V4MODAL 夹具全部按预期拦截或放行(无空规) | 全部符合 | 全部符合 | PASS |
| 21 | 数值反例:短记录无法解析极端事件概率(1年→39年) | 4/5 个短记录无法解析 | 存在无法解析的短记录 | PASS |
| 21 | 数值反例:不确定性信息量(信息性 vs 无信息) | 信息性=0.892, 无信息=-0.031 | 信息性 > 0.3 且 无信息 < 0.1 | PASS |
| 21 | 数值反例:5/10000 稀有比例的 Wilson CI 宽度 | CI=[0.000214,0.00117] 相对宽度=1.913 上下界比=5.48 | 相对宽度 > 1.0 且 上下界比 > 2 | PASS |
| 21 | [T31冗余度] WCMI:选了20个特征但完全未报冗余度 | 实际=不通过 | 期望=不通过 | PASS |
| 21 | [T31冗余度] \|r\|>0.9 占比 45% 未去冗余 | 实际=不通过 | 期望=不通过 | PASS |
| 21 | [T31冗余度] \|r\|>0.9 占比 12%(灰区) | 实际=通过 | 期望=通过 | PASS |
| 21 | [T31冗余度] \|r\|>0.9 占比 6%(可解释特征集) | 实际=通过 | 期望=通过 | PASS |
| 22 | [T03] 合规:声明与执行一致(20000) | pass | pass | PASS |
| 22 | [T03] 声明全基因组却只校正 500 个:应拦 | fail | fail | PASS |
| 22 | [T03] 未声明家族:应判不适用 | na | na | PASS |
| 22 | [T09] 合规:声明 CV 概率 | pass | pass | PASS |
| 22 | [T09] 声明样本内概率:应拦 | fail | fail | PASS |
| 22 | [T09] 未声明来源:应判不适用 | na | na | PASS |
| 22 | [T12] 合规:落差 0.02 | pass | pass | PASS |
| 22 | [T12] 样本内 1.000 / 样本外 0.544:应警告 | warn | warn | PASS |
| 22 | [T12] 缺样本内指标:应判不适用 | na | na | PASS |
| 22 | [T18] 合规:4 个变体全报 | pass | pass | PASS |
| 22 | [T18] 预注册 4 个仅报 2 个:应拦 | fail | fail | PASS |
| 22 | [T18] 报告未预注册变体:应警告 | warn | warn | PASS |
| 22 | [T18] 未预注册:应判不适用 | na | na | PASS |
| 22 | T03/T09/T12/T18 夹具全部按预期拦截或放行(无空规) | 无偏差 | 无偏差 | PASS |
| 23 | [T36] ROMO1 多组学:只报全组件性能,无消融 → 应拦 | fail | fail | PASS |
| 23 | [T36] p53 四组学:缺 leave-one-out → 应拦 | fail | fail | PASS |
| 23 | [T36] 合规:三组件均有增量且 CI 不跨 0 | pass | pass | PASS |
| 23 | [T36] 一个组件 CI 跨 0 → 应警告 | warn | warn | PASS |
| 23 | [T36] 全部组件无增量 → 应拦(循环论证) | fail | fail | PASS |
| 23 | [T36] 单组件研究 → 应判不适用 | na | na | PASS |
| 23 | T36 夹具全部按预期拦截或放行(无空规) | 无偏差 | 无偏差 | PASS |
| E | 结论方向全部一致 | True | True | PASS |
| E | 点估计极差 >10% 须报告 | 0.312 | >0.10 → 报告 | PASS |
| P3 | 隔离守卫绕过测试(含 Win 反斜杠/大小写) | 7/7 通过 | 7/7 | PASS |
| P3 | 正式台账写入被拦截 | True | True | PASS |

## 关键指标

```json
{
 "note": "MVP 合成值·非项目实际值",
 "b1_family": {
  "raw_hits": 26,
  "bh_hits": 0,
  "ngene": 500
 },
 "b2_increment": {
  "auc_base": 0.6346,
  "auc_full": 0.6743,
  "dAUC": 0.0397,
  "f3_triggered": true
 },
 "b3_calibration": {
  "slope_insample": 1.001,
  "slope_cv": 0.841,
  "ci": [
   0.656,
   0.947
  ],
  "covers_one": false
 },
 "b4_interval": {
  "calibrated": {
   "win_pre": 0.72,
   "win_all": 0.717,
   "min_diff_pre": -0.0273,
   "min_at": 0.58,
   "max_neg_run": 8,
   "best_sub_rate": 1.0,
   "best_sub": [
    0.24,
    0.33
   ],
   "conflict": false
  },
  "uncalibrated": {
   "win_pre": 0.44,
   "win_all": 0.253,
   "min_diff_pre": -0.0175,
   "min_at": 0.6,
   "max_neg_run": 21,
   "best_sub_rate": 1.0,
   "best_sub": [
    0.42,
    0.51
   ],
   "conflict": false
  },
  "borderline_s1.6": {
   "win_all": 0.505,
   "max_neg_run": 13,
   "min_diff": -0.0288
  }
 },
 "b5_reverse": {
  "or_d1": 1.627,
  "or_d3": 0.737,
  "same_direction": false,
  "r5_triggered": true
 },
 "b6_flip": {
  "or_v1": 1.55,
  "or_v2": 1.038,
  "drift_pct": 33.0,
  "direction_flip": false,
  "drift_min": 16.3,
  "drift_max": 37.8,
  "drift_median": 21.0,
  "flip_rate": 0.417,
  "flip_n": 5,
  "n_seed": 12
 },
 "b7_figures": {
  "sample_ok_truetype.pdf": {
   "fonts": [
    "/Type0"
   ],
   "images": 0,
   "images_direct": 0,
   "images_inline": 0,
   "textlen": 85,
   "verdict": "合规",
   "expected": "合规"
  },
  "sample_bad_bitmap.pdf": {
   "fonts": [],
   "images": 1,
   "images_direct": 1,
   "images_inline": 0,
   "textlen": 0,
   "verdict": "不合规:位图/无文本层",
   "expected": "不合规"
  },
  "sample_bad_type3.pdf": {
   "fonts": [
    "/Type3"
   ],
   "images": 0,
   "images_direct": 0,
   "images_inline": 0,
   "textlen": 52,
   "verdict": "不合规:Type3非矢量字体",
   "expected": "不合规"
  },
  "sample_bad_notext.pdf": {
   "fonts": [],
   "images": 0,
   "images_direct": 0,
   "images_inline": 0,
   "textlen": 0,
   "verdict": "不合规:无文本层",
   "expected": "不合规"
  },
  "sample_bad_page2_bitmap.pdf": {
   "fonts": [
    "/Type0"
   ],
   "images": 2,
   "images_direct": 2,
   "images_inline": 0,
   "textlen": 57,
   "verdict": "不合规:位图",
   "expected": "不合规"
  }
 },
 "b8_hardblock": {
  "pseudoreplication": {
   "p_cell": 4.229e-14,
   "p_donor": 0.28
  },
  "leakage": {
   "auc_leak": 0.975,
   "auc_clean": 0.864,
   "inflation": 0.112
  },
  "endpoint": {
   "or_A": 3.085,
   "or_B": 1.238,
   "or_merged": 1.834,
   "I2": 96.6,
   "p_het": 0.0
  }
 },
 "b9_conditional": {
  "T15": {
   "mito_cell_mean": 5.1,
   "mito_nuc_mean": 0.92,
   "rej_cell": 0.1,
   "rej_nuc": 0.0,
   "over_reject_if_strict": 0.112
  },
  "T16": {
   "p_cell": 5.34e-08,
   "p_donor": 0.263,
   "below_threshold": 2
  },
  "T17": {
   "corr_original": 0.615,
   "corr_multiplicative": 0.615,
   "corr_permuted": -0.02,
   "sd_ratio_multiplicative": 2.0,
   "sd_ratio_permuted": 1.0
  }
 },
 "b10_stats": {
  "competing_risk": {
   "n_competing": 947,
   "prop": 0.473,
   "cif_km_g0": 0.538,
   "cif_correct_g0": 0.253,
   "cif_km_g1": 0.674,
   "cif_correct_g1": 0.537,
   "diff_km": 0.135,
   "diff_correct": 0.284
  },
  "epv": {
   "低EPV": {
    "epv": 0.9,
    "n_sample": 60,
    "n_var": 20,
    "n_events_train": 18,
    "auc_train": 1.0,
    "auc_test": 0.868,
    "optimism": 0.132
   },
   "中EPV": {
    "epv": 3.0,
    "n_sample": 200,
    "n_var": 20,
    "n_events_train": 60,
    "auc_train": 0.989,
    "auc_test": 0.931,
    "optimism": 0.058
   },
   "充足EPV": {
    "epv": 30.0,
    "n_sample": 2000,
    "n_var": 20,
    "n_events_train": 600,
    "auc_train": 0.941,
    "auc_test": 0.936,
    "optimism": 0.006
   }
  },
  "feasibility": {
   "正常项目": "FEASIBLE",
   "独立性存疑+低EPV": "INFEASIBLE",
   "无结局变量": "INFEASIBLE",
   "关键协变量大量缺失": "FEASIBLE_WITH_DOWNGRADE"
  }
 },
 "b15_doctrine": null,
 "b16_literature": [
  [
   "文献17 Table1 RA(16 vs 4)",
   "T21",
   "fail",
   "fail",
   "min=4,max=16,ratio=4.00",
   "最小组 n=4 < 6(功效不足)",
   true
  ],
  [
   "文献17 Table1 T1D(10 vs 6)",
   "T21",
   "warn",
   "warn",
   "min=6,max=10,ratio=1.67",
   "最小组 n=6 落在灰区[6,10),须声明小样本并做敏感性分析,不得直接判通过",
   true
  ],
  [
   "文献17 Table1 MS(99 vs 45)",
   "T21",
   "pass",
   "pass",
   "min=45,max=99,ratio=2.20",
   "样本量与平衡性充足",
   true
  ],
  [
   "合规对照(50 vs 50)",
   "T21",
   "pass",
   "pass",
   "min=50,max=50,ratio=1.00",
   "样本量与平衡性充足",
   true
  ],
  [
   "文献18 训练.666/验证.560",
   "T22",
   "fail",
   "fail",
   "train=0.666,ext=0.56,drop=0.106",
   "落差 0.106 > 0.1(泛化衰减过大); 外部验证 AUC 0.56 < 0.6(接近随机)",
   true
  ],
  [
   "合规对照(0.80/0.78)",
   "T22",
   "pass",
   "pass",
   "train=0.8,ext=0.78,drop=0.020",
   "泛化稳定",
   true
  ],
  [
   "文献19 QC(2.5/5/25%,有声明)",
   "T23",
   "pass",
   "pass",
   "不同阈值=[2.5, 5.0, 25.0]",
   "阈值不同但已声明理由:不同模态(snRNA vs scRNA)",
   true
  ],
  [
   "文献19 变体(阈值不同,无声明)",
   "T23",
   "fail",
   "fail",
   "不同阈值=[2.5, 5.0, 25.0]",
   "阈值不同([2.5, 5.0, 25.0])且未声明理由",
   true
  ],
  [
   "合规对照(统一2.5%)",
   "T23",
   "pass",
   "pass",
   "统一=2.5",
   "阈值统一",
   true
  ],
  [
   "文献19 跨物种验证(mouse→human)",
   "T24",
   "pass",
   "pass",
   "独立队列/跨物种",
   "验证集独立于训练集",
   true
  ],
  [
   "同队列随机split(典型泄露)",
   "T24",
   "fail",
   "fail",
   "同队列 split",
   "验证集与训练集同队列(存在数据泄露风险)",
   true
  ],
  [
   "文献21 手动按位置选ROI",
   "T25",
   "fail",
   "fail",
   "manually selected by location/非盲",
   "ROI 选择为'manually selected by location'且未盲法、未预注册(选择偏倚风险)",
   true
  ],
  [
   "文献19 盲法选区",
   "T25",
   "pass",
   "pass",
   "blinded region selector/盲法",
   "ROI 选择采用盲法",
   true
  ]
 ],
 "b17_conclusion": true,
 "b20_selection_causal": null,
 "b21_rare_uncertainty": null,
 "b22_dormant": "分支 22 · 休眠判据激活(T03/T09/T12/T18)",
 "b23_integration": "分支 23 · 多组件整合增量消融(T36)",
 "extra_seed": {
  "seeds": [
   20260910,
   20260101,
   20260315,
   20260707
  ],
  "ors": [
   1.627,
   1.8,
   1.488,
   1.582
  ],
  "same_direction": true,
  "range": 0.312
 },
 "extra_guard": {
  "ledger/x.json": "已拦截",
  "results/x.json": "放行",
  "synthetic/x.json": "放行",
  "bypass_tests": "7/7 通过"
 },
 "summary": {
  "n_pass": 222,
  "n_fail": 0,
  "n_na": 0,
  "total": 222,
  "branches": 21,
  "criteria_dist": {
   "T13c": {
    "n_direct": 16,
    "n_branch": 0,
    "n": 16,
    "n_na": 0,
    "na_tested": 0,
    "branches": [
     "4"
    ]
   },
   "T31": {
    "n_direct": 16,
    "n_branch": 0,
    "n": 16,
    "n_na": 0,
    "na_tested": 0,
    "branches": [
     "20",
     "21"
    ]
   },
   "T13b": {
    "n_direct": 13,
    "n_branch": 0,
    "n": 13,
    "n_na": 0,
    "na_tested": 0,
    "branches": [
     "20",
     "3"
    ]
   },
   "HARDBLOCK": {
    "n_direct": 13,
    "n_branch": 0,
    "n": 13,
    "n_na": 0,
    "na_tested": 0,
    "branches": [
     "8"
    ]
   },
   "T33": {
    "n_direct": 10,
    "n_branch": 0,
    "n": 10,
    "n_na": 0,
    "na_tested": 0,
    "branches": [
     "21"
    ]
   },
   "B03A": {
    "n_direct": 9,
    "n_branch": 0,
    "n": 9,
    "n_na": 0,
    "na_tested": 0,
    "branches": [
     "6"
    ]
   },
   "T34": {
    "n_direct": 8,
    "n_branch": 0,
    "n": 8,
    "n_na": 0,
    "na_tested": 0,
    "branches": [
     "21"
    ]
   },
   "V5DECL": {
    "n_direct": 7,
    "n_branch": 0,
    "n": 7,
    "n_na": 0,
    "na_tested": 0,
    "branches": [
     "7"
    ]
   },
   "T32": {
    "n_direct": 7,
    "n_branch": 0,
    "n": 7,
    "n_na": 0,
    "na_tested": 0,
    "branches": [
     "20"
    ]
   },
   "T35": {
    "n_direct": 7,
    "n_branch": 0,
    "n": 7,
    "n_na": 0,
    "na_tested": 0,
    "branches": [
     "21"
    ]
   },
   "V4MODAL": {
    "n_direct": 7,
    "n_branch": 0,
    "n": 7,
    "n_na": 0,
    "na_tested": 0,
    "branches": [
     "21"
    ]
   },
   "T36": {
    "n_direct": 7,
    "n_branch": 0,
    "n": 7,
    "n_na": 0,
    "na_tested": 1,
    "branches": [
     "23"
    ]
   },
   "T08": {
    "n_direct": 6,
    "n_branch": 0,
    "n": 6,
    "n_na": 0,
    "na_tested": 0,
    "branches": [
     "15"
    ]
   },
   "T27": {
    "n_direct": 6,
    "n_branch": 0,
    "n": 6,
    "n_na": 0,
    "na_tested": 0,
    "branches": [
     "17"
    ]
   },
   "T15": {
    "n_direct": 5,
    "n_branch": 0,
    "n": 5,
    "n_na": 0,
    "na_tested": 0,
    "branches": [
     "T15"
    ]
   },
   "T17": {
    "n_direct": 5,
    "n_branch": 0,
    "n": 5,
    "n_na": 0,
    "na_tested": 0,
    "branches": [
     "T17"
    ]
   },
   "GLOBAL": {
    "n_direct": 5,
    "n_branch": 0,
    "n": 5,
    "n_na": 0,
    "na_tested": 0,
    "branches": [
     "15",
     "16",
     "20",
     "21",
     "22"
    ]
   },
   "T21": {
    "n_direct": 5,
    "n_branch": 0,
    "n": 5,
    "n_na": 0,
    "na_tested": 0,
    "branches": [
     "16"
    ]
   },
   "T16": {
    "n_direct": 4,
    "n_branch": 0,
    "n": 4,
    "n_na": 0,
    "na_tested": 0,
    "branches": [
     "T16"
    ]
   },
   "B02S": {
    "n_direct": 4,
    "n_branch": 0,
    "n": 4,
    "n_na": 0,
    "na_tested": 0,
    "branches": [
     "10"
    ]
   },
   "T26": {
    "n_direct": 4,
    "n_branch": 0,
    "n": 4,
    "n_na": 0,
    "na_tested": 1,
    "branches": [
     "17"
    ]
   },
   "T29": {
    "n_direct": 4,
    "n_branch": 0,
    "n": 4,
    "n_na": 0,
    "na_tested": 1,
    "branches": [
     "17"
    ]
   },
   "T18": {
    "n_direct": 4,
    "n_branch": 0,
    "n": 4,
    "n_na": 0,
    "na_tested": 1,
    "branches": [
     "22"
    ]
   },
   "T01": {
    "n_direct": 3,
    "n_branch": 0,
    "n": 3,
    "n_na": 0,
    "na_tested": 0,
    "branches": [
     "1"
    ]
   },
   "T06": {
    "n_direct": 3,
    "n_branch": 0,
    "n": 3,
    "n_na": 0,
    "na_tested": 0,
    "branches": [
     "10"
    ]
   },
   "B01A": {
    "n_direct": 3,
    "n_branch": 0,
    "n": 3,
    "n_na": 0,
    "na_tested": 0,
    "branches": [
     "10"
    ]
   },
   "Y6": {
    "n_direct": 3,
    "n_branch": 0,
    "n": 3,
    "n_na": 0,
    "na_tested": 0,
    "branches": [
     "15"
    ]
   },
   "T19": {
    "n_direct": 3,
    "n_branch": 0,
    "n": 3,
    "n_na": 0,
    "na_tested": 0,
    "branches": [
     "15"
    ]
   },
   "T20": {
    "n_direct": 3,
    "n_branch": 0,
    "n": 3,
    "n_na": 0,
    "na_tested": 0,
    "branches": [
     "15"
    ]
   },
   "T23": {
    "n_direct": 3,
    "n_branch": 0,
    "n": 3,
    "n_na": 0,
    "na_tested": 0,
    "branches": [
     "16"
    ]
   },
   "T28": {
    "n_direct": 3,
    "n_branch": 0,
    "n": 3,
    "n_na": 0,
    "na_tested": 0,
    "branches": [
     "17"
    ]
   },
   "T30": {
    "n_direct": 3,
    "n_branch": 0,
    "n": 3,
    "n_na": 0,
    "na_tested": 1,
    "branches": [
     "17"
    ]
   },
   "T03": {
    "n_direct": 3,
    "n_branch": 0,
    "n": 3,
    "n_na": 0,
    "na_tested": 1,
    "branches": [
     "22"
    ]
   },
   "T09": {
    "n_direct": 3,
    "n_branch": 0,
    "n": 3,
    "n_na": 0,
    "na_tested": 1,
    "branches": [
     "22"
    ]
   },
   "T12": {
    "n_direct": 3,
    "n_branch": 0,
    "n": 3,
    "n_na": 0,
    "na_tested": 1,
    "branches": [
     "22"
    ]
   },
   "T13a": {
    "n_direct": 2,
    "n_branch": 0,
    "n": 2,
    "n_na": 0,
    "na_tested": 0,
    "branches": [
     "2"
    ]
   },
   "T14": {
    "n_direct": 2,
    "n_branch": 0,
    "n": 2,
    "n_na": 0,
    "na_tested": 0,
    "branches": [
     "5"
    ]
   },
   "T22": {
    "n_direct": 2,
    "n_branch": 0,
    "n": 2,
    "n_na": 0,
    "na_tested": 0,
    "branches": [
     "16"
    ]
   },
   "T24": {
    "n_direct": 2,
    "n_branch": 0,
    "n": 2,
    "n_na": 0,
    "na_tested": 0,
    "branches": [
     "16"
    ]
   },
   "T25": {
    "n_direct": 2,
    "n_branch": 0,
    "n": 2,
    "n_na": 0,
    "na_tested": 0,
    "branches": [
     "16"
    ]
   },
   "SEEDROBUST": {
    "n_direct": 2,
    "n_branch": 0,
    "n": 2,
    "n_na": 0,
    "na_tested": 0,
    "branches": [
     "E"
    ]
   },
   "ISOLATION": {
    "n_direct": 2,
    "n_branch": 0,
    "n": 2,
    "n_na": 0,
    "na_tested": 0,
    "branches": [
     "P3"
    ]
   }
  },
  "n_unmapped": 0,
  "elapsed": 50.6
 },
 "warnings": [],
 "run_metadata": {
  "run_id": "0b7e75ffc4a5dbdc",
  "parent_run_id": null,
  "seed": 20260910,
  "python": "3.13.14",
  "platform": "Windows-11-10.0.26200-SP0",
  "script_hashes": {
   "ablation.py": "510999a04317f535",
   "applicability_gate.py": "9f333de26bdbd32e",
   "compare_platforms.py": "4bfff98d4331cd8f",
   "compare_runs.py": "16eac8b4cd1587b5",
   "component_ablation.py": "32dd4417f398ec90",
   "conclusion_branch.py": "a0c9dd820de3047d",
   "conclusion_guard.py": "d8a636116c401bc6",
   "consistency_guard.py": "84a41df64031697f",
   "data_ethics.py": "deecc6899f926bd2",
   "dormant_check.py": "8b9b31bc679addb4",
   "export_guard.py": "8e7b77197d2a95d0",
   "figure_kit.py": "b0dd42c07a933c22",
   "gen_appendix.py": "7e4ab7defa323760",
   "guard_selftest.py": "506b43d8d9b8f37c",
   "layout_check.py": "2261864587620ea5",
   "literature_gap.py": "2173fc68097c7842",
   "platform_check.py": "e1d4f8094921302a",
   "rare_uncertainty.py": "a950f1c59331480f",
   "realdata_adapter.py": "290892ddb9c8981e",
   "report_guard.py": "9d33f137991a0569",
   "run_units.py": "4b3fbb28b2ad17f0",
   "selection_causal.py": "afc836b05a6007dc",
   "tl_bee.py": "0a0f8330cbbf94c7",
   "verify_all.py": "1305b6ad4278e24d",
   "writing_guard.py": "a91be4dea7be244d"
  },
  "env_snapshot": {
   "cloudpickle": "3.1.2",
   "colorama": "0.4.6",
   "contourpy": "1.4.0",
   "cycler": "0.12.1",
   "fonttools": "4.65.0",
   "iniconfig": "2.3.0",
   "joblib": "1.6.0",
   "kiwisolver": "1.5.1",
   "matplotlib": "3.11.0",
   "narwhals": "2.26.0",
   "numpy": "2.5.0",
   "packaging": "26.3",
   "pandas": "3.0.5",
   "pillow": "12.3.0",
   "pluggy": "1.6.0",
   "Pygments": "2.21.0",
   "pyparsing": "3.3.2",
   "pypdf": "6.18.0",
   "pytest": "9.1.1",
   "python-dateutil": "2.9.0.post0",
   "PyYAML": "6.0.3",
   "scikit-learn": "1.9.1",
   "scipy": "1.18.1",
   "six": "1.17.0",
   "threadpoolctl": "3.6.0",
   "tzdata": "2026.3"
  },
  "input_hash": "d8ac2a843faa33e1"
 }
}
```

> MVP 合成值·非项目实际值