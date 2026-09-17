#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
realdata_adapter.py —— 真实 GEO 数据适配器(GSE250167)

════════════════════════════════════════════════════════════════════════
设计原则(与框架的"不改统计逻辑"约束一致)
────────────────────────────────────────────────────────────────────────
本适配器**只负责把真实数据读成与合成数据同构的矩阵**,不触碰任何
统计检验、阈值、守卫逻辑。verify_all.py 以 `--datasource real` 调用它,
其余流程完全不变。这样才能保证"只换数据源"这一变量控制成立。

源数据特征(GSE250167)
────────────────────────────────────────────────────────────────────────
  物种     : Arabidopsis thaliana(模式植物,非人类)
  测序类型 : ncRNA-Seq 小 RNA(10-60 nt),**非 mRNA**
  样本数   : 8(GSM),4 组 × 2 重复
  分组     : WT-0h / WT-3h / rns2-0h / rns2-3h
  文件格式 : GSM*.txt.gz,两列 tab 分隔(sequence, raw count)
  关键差异 : "基因"实为 **sRNA 序列**,无 mRNA 式 log2FC 语义,
             无标准通路注释(MSigDB/GO 人类中心),无临床随访结局。

这正是选此数据集做压力测试的原因:**物种与数据类型双重不匹配**,
用于检验框架的 §10「不适用 + 理由」分支是否真能优雅降级。

用法
────────────────────────────────────────────────────────────────────────
    python scripts/realdata_adapter.py --datadir <dir> [--json out.json]

    或由 verify_all.py 内部调用:
        from realdata_adapter import load
        D = load(datadir)
"""

import os
import re
import gzip
import json
import sys

# ── 分组解析:从 GSM 文件名提取元数据 ────────────────────────────────
# 典型文件名: GSM7974940_rns2-3h-2.txt.gz
#   下划线后形如 <genotype>-<time>h-<rep>
_GSM_RE = re.compile(
    r"(?P<gsm>GSM\d+).*?(?P<genotype>wt|rns2|rns2-\d)[-_]?"
    r"(?P<time>\d+)h[-_]?(?P<rep>\d+)",
    re.IGNORECASE,
)


def parse_sample_name(fname):
    """从 GSM 文件名解析 (gsm, genotype, timepoint, rep)。

    ★ 框架的硬约束(用户明确要求):"如果某样本的分组归属不明确,
      先停下来报告,不要猜测。"
    故解析失败时返回 None,由调用方**显式报错并列出未识别文件**,
    绝不按序号或顺序隐式分组。
    """
    m = _GSM_RE.search(fname)
    if not m:
        return None
    d = m.groupdict()
    gt = d["genotype"].lower()
    # 归一化:rns2 / rns2-1 / rns2-2 均视为 rns2 突变体
    if gt.startswith("rns2"):
        gt = "rns2"
    return dict(gsm=d["gsm"], genotype=gt,
                timepoint=int(d["time"]), rep=int(d["rep"]),
                group=f"{gt.upper() if gt=='wt' else 'rns2'}-{d['time']}h")


def read_gsm(path, min_count=1):
    """读单个 GSM 文件 → {sequence: count}。

    仅做两件事:解压、按 tab 取两列。不做任何过滤/归一化 ——
    那属于分析步骤,不是适配器的职责(避免"让它通过"的预处理)。
    """
    out = {}
    opener = gzip.open if path.endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8", errors="replace") as fh:
        for i, line in enumerate(fh):
            line = line.rstrip("\n\r")
            if not line:
                continue
            parts = line.split("\t")
            if len(parts) < 2:
                parts = line.split()      # 兼容空格分隔
            if len(parts) < 2:
                continue
            seq, cnt = parts[0].strip(), parts[1].strip()
            try:
                c = float(cnt)
            except ValueError:
                continue                   # 表头行
            if c >= min_count:
                out[seq] = out.get(seq, 0) + c
    return out


def load(datadir, verbose=True):
    """读取目录下所有 GSM*.txt.gz → 与合成数据同构的 dict。

    返回结构(字段命名与 verify_all.py 的合成数据保持一致):
        {
          "assay_type":  "srna_count",
          "species":     "Arabidopsis thaliana",
          "features":    [...],           # sRNA 序列(= "基因"位)
          "counts":      [[...]],         # features × samples
          "sample_ids":  [...],
          "groups":      [...],           # 每样本分组标签
          "meta":        {...},
          "unparsed":    [...],           # ★ 未识别文件(必须为空)
        }
    """
    if not os.path.isdir(datadir):
        raise FileNotFoundError(f"数据目录不存在: {datadir}")

    files = sorted(f for f in os.listdir(datadir)
                   if f.startswith("GSM") and f.endswith((".txt", ".txt.gz")))
    if not files:
        raise FileNotFoundError(
            f"{datadir} 下未找到 GSM*.txt.gz。请先下载并解压 "
            f"GSE250167_RAW.tar")

    # ── ① 元数据解析:宁停勿猜 ──
    samples, unparsed = [], []
    for f in files:
        info = parse_sample_name(f)
        if info is None:
            unparsed.append(f)
        else:
            info["file"] = f
            samples.append(info)

    if unparsed:
        raise ValueError(
            "以下文件无法从文件名解析分组(框架要求:不猜测,先报告):\n  "
            + "\n  ".join(unparsed)
            + "\n请核对 GEO 页面元数据后手工指定分组映射。")

    # ── ② 读矩阵:按 sequence 取并集 ──
    per_sample = {}
    for s in samples:
        per_sample[s["gsm"]] = read_gsm(os.path.join(datadir, s["file"]))

    all_seq = set()
    for d in per_sample.values():
        all_seq.update(d.keys())
    features = sorted(all_seq)

    idx = {s: i for i, s in enumerate(features)}
    counts = [[0.0] * len(samples) for _ in features]
    for j, s in enumerate(samples):
        for seq, c in per_sample[s["gsm"]].items():
            counts[idx[seq]][j] = c

    if verbose:
        print(f"    [real-data] 样本 {len(samples)} 个, "
              f"sRNA 特征 {len(features)} 条")
        from collections import Counter
        print(f"    [real-data] 分组: {dict(Counter(s['group'] for s in samples))}")

    return dict(
        assay_type="srna_count",
        species="Arabidopsis thaliana",
        platform="GPL13222",
        features=features,
        counts=counts,
        sample_ids=[s["gsm"] for s in samples],
        groups=[s["group"] for s in samples],
        unparsed=unparsed,
        meta=dict(
            geo="GSE250167",
            assay_type="srna_count",   # ★ v2.13:适用性闸门理由模板要用
            species="Arabidopsis thaliana",
            n_sample=len(samples),
            n_feature=len(features),
            design="4 组 × 2 重复 (WT-0h/WT-3h/rns2-0h/rns2-3h)",
            main_contrast="WT-3h vs WT-0h",
            samples=samples,
            # ★ 关键声明:告知下游哪些维度缺失(触发 §10 不适用分支)
            has_clinical_outcome=False,
            has_pathway_annotation=False,
            is_single_cell=False,
            scale="raw_count",
        ),
    )


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--datadir", required=True)
    ap.add_argument("--json", default="")
    a = ap.parse_args()
    D = load(a.datadir)
    print(json.dumps({k: v for k, v in D.items()
                      if k not in ("counts", "features")},
                     ensure_ascii=False, indent=2))
    print(f"(counts 矩阵 {len(D['features'])} × {len(D['sample_ids'])}, "
          f"已省略输出)")
    if a.json:
        json.dump(D, open(a.json, "w", encoding="utf-8"),
                  ensure_ascii=False)
        print("→ " + a.json)
