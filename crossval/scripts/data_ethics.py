#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""数据正义与治理判据 T29/T30(branch17)。

来源:Braun & Hummel《Data justice and data solidarity》(Patterns 2, 100427)
     Boeschoten et al. PORT《Privacy-preserving local analysis》(Patterns 3, 100444)

★ 这两条是框架**此前完全缺失的新维度**:
  V5DECL 只检查"伦理批准/知情同意/数据共享"这些**形式声明是否存在**,
  不检查"数据背后的人是否被公平对待"。这是形式 vs 实质的区别 ——
  而框架反复强调"形式级无法区分'填了'与'对了'"。

铁律:允许判 N/A,但**不可跳过**;N/A 必须带理由(空理由 raise)。

T29 问:数据背后的人是否被公平对待?
T30 问:数据治理流程是否合规?
"""
import re

# ---------------------------------------------------------------- T29
# 数据正义三支柱(Taylor):(In)visibility / (Dis)engagement / Non-discrimination

T29_SENSITIVE = ("健康", "医疗", "金融", "位置", "基因", "人脸", "生物识别")
# "声称充分"的措辞 —— 出现即触发举证要求(不能只说,必须给数字)
T29_ADEQUACY_CLAIM = ("代表性充分", "具有代表性", "样本具有代表性",
                      "representative", " adequately represented")
T29_CLINICAL_CLAIM = ("可临床转化", "可用于临床", "clinical translation",
                      "可用于决策", "临床部署")


def check_T29(kind="人群数据", sensitive=False,
              subgroup_n=None, adequacy_claim=False,
              risk_asymmetry=None, clinical_claim=False,
              exit_option=None, privacy_absence_reported=None,
              na_reason=None):
    """T29 · 数据正义自查(必答,但可判 N/A)。

    必答项:
      (a) 哪些群体代表性不足?是否报告各子群体样本量?
      (b) 哪些群体可能因模型误差承担不对称风险?
      (c) 被采集者是否有真实退出选项?
      (d) 是否存在因隐私顾虑主动不参与的人群?其缺失是否报告?

    不通过:
      - 声称"代表性充分"但无子群体样本量 → R5 回退
      - 未做 (b) 但声称"可临床转化" → **硬阻断**
      - 未报告 (d) 但属敏感数据 → T29 不通过

    N/A:纯方法学(无人群数据) / 回顾性公共数据(无法追溯采集过程)
    """
    # N/A 出口
    if kind == "纯方法学":
        if not na_reason:
            raise ValueError("§10:N/A 必须给出理由")
        return "na", "纯方法学", na_reason
    if kind == "回顾性公共数据" and privacy_absence_reported is None:
        return "na", "回顾性公共数据", (
            "无法追溯采集过程 → N/A;须声明来源(已由 T30 覆盖)")

    detail, status = [], "pass"
    obs = []

    # (a) 代表性 + 子群体样本量
    if adequacy_claim and not subgroup_n:
        status = "fail"
        detail.append("声称'代表性充分'但未提供各子群体样本量 → R5 回退"
                      "(声称与举证不符,数据正义支柱一:(In)visibility)")
    if subgroup_n:
        obs.append(f"子群体数={len(subgroup_n)}")
        if min(subgroup_n.values()) == 0:
            status = "fail"
            detail.append("存在样本量为 0 的子群体 → 结构性不可见,必须显式报告")

    # (b) 不对称风险 —— 与临床声称绑定(硬阻断)
    if clinical_claim and risk_asymmetry is None:
        status = "fail"
        detail.append("声称'可临床转化'但未评估哪些群体承担不对称风险"
                      " → **硬阻断**(数据正义支柱三:Non-discrimination)")
    if risk_asymmetry:
        obs.append(f"高风险群体={len(risk_asymmetry)}")

    # (c) 退出选项
    if exit_option is None:
        status = "warn" if status == "pass" else status
        detail.append("未说明被采集者是否有真实退出选项"
                      "(数据正义支柱二:(Dis)engagement)")
    else:
        obs.append(f"退出选项={exit_option}")

    # (d) 隐私性缺失报告(敏感数据强制)
    if sensitive and privacy_absence_reported is None:
        status = "fail"
        detail.append(f"属敏感数据({'/'.join(T29_SENSITIVE)})但未报告"
                      f"'因隐私顾虑主动不参与的人群及其缺失' → T29 不通过")
    if privacy_absence_reported is not None:
        obs.append(f"隐私缺失已报告={privacy_absence_reported}")

    if not detail:
        detail.append("数据正义四项均已举证")
    return status, ",".join(obs) or "无举证", "; ".join(detail)


# ---------------------------------------------------------------- T30
# 数据治理(PORT:本地处理 + 特征可见性 + true informed consent + 撤回)

T30_ANON_CLAIM = ("匿名化", "anonymized", "脱敏", "去标识化")
# 具体的匿名化方法(没有方法名的"匿名化"是空声明)
T30_ANON_METHOD = ("k-anonymity", "k-匿名", "差分隐私", "differential privacy",
                   "DP", "泛化", "抑制", "l-diversity", "t-closeness")
T30_GDPR_HINT = ("欧盟", "EU", "GDPR", "欧洲", "EEA")


def check_T30(data_source="公开二次数据",
              data_flow=None, features_visible=None,
              withdraw=None, secondary_use=None,
              anon_claim=None, anon_method=None,
              gdpr_scope=None, gdpr_article=None,
              na_reason=None):
    """T30 · 数据治理声明(发布前必过,可判 N/A)。

    必答项:
      (a) 数据流向:原始数据存于何处?是否离开数据主体设备?
      (b) 特征提取的可见性:提取了哪些特征?被采集者能否审阅?
      (c) 撤回机制:能否要求删除已提取特征?
      (d) 二次使用:特征是否会被用于原定目的之外?

    不通过:
      - 声称"匿名化"但未说明方法 → 应报告方法(k-anonymity / DP 等)
      - 声称"仅用于本研究"但无具体约束机制 → R5 回退
      - 涉及 GDPR 覆盖人群 → 必须引用具体法条

    N/A:使用完全公开的二次数据(如 TCGA)→ N/A + 声明来源
    """
    if data_source == "公开二次数据" and data_flow is None:
        if not na_reason:
            na_reason = "使用完全公开二次数据,无本地采集流程"
        return "na", "公开二次数据", na_reason

    detail, status = [], "pass"
    obs = []

    if data_flow is None:
        status = "fail"
        detail.append("(a) 未说明数据流向(原始数据存于何处/是否离开数据主体设备)")
    else:
        obs.append(f"流向={data_flow}")

    if features_visible is None:
        status = "fail" if status == "pass" else status
        detail.append("(b) 未说明提取了哪些特征、被采集者能否审阅"
                      "(PORT 核心:true informed consent 的前提)")
    else:
        obs.append(f"特征可见={features_visible}")

    if withdraw is None:
        status = "fail" if status == "pass" else status
        detail.append("(c) 未说明撤回机制(被采集者能否要求删除已提取特征)")
    else:
        obs.append(f"可撤回={withdraw}")

    if secondary_use is None:
        status = "fail" if status == "pass" else status
        detail.append("(d) 未说明二次使用约束")
    else:
        obs.append(f"二次使用={secondary_use}")

    # 匿名化:声称必须有方法
    if anon_claim and not anon_method:
        status = "fail"
        detail.append("声称'匿名化/脱敏'但未说明具体方法"
                      f"(须为 {'/'.join(T30_ANON_METHOD[:4])} 等)")
    if anon_method:
        obs.append(f"匿名方法={anon_method}")

    # GDPR
    if gdpr_scope and not gdpr_article:
        status = "fail"
        detail.append("涉及 GDPR 覆盖人群但未引用具体法条")
    if gdpr_article:
        obs.append(f"法条={gdpr_article}")

    if not detail:
        detail.append("数据治理四项均已声明且有约束机制")
    return status, ",".join(obs) or "无声明", "; ".join(detail)
