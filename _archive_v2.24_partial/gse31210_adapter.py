#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gse31210_adapter.py —— GSE31210 系列矩阵适配器

GSE31210: 226 例肺腺癌 + 20 例癌旁正常, Affymetrix GPL570 芯片
文件格式: GSE31210_series_matrix.txt.gz (单文件,含元数据+矩阵)

返回结构与 realdata_adapter.load() 同构,供 verify_all.py 统一消费。
"""
import os, re, gzip, json
from collections import defaultdict


def parse_matrix_gz(gz_path):
    """解析 GEO 系列矩阵 .txt.gz -> (gsm_ids, characteristics, probe_rows)"""
    with gzip.open(gz_path, "rt", encoding="utf-8") as f:
        raw = f.read()
    lines = raw.split("\n")

    # ① 提取所有 !Sample_* 行 (每列对应一个 GSM)
    gsm_ids = []
    char_fields = defaultdict(list)  # field_prefix -> [val_per_gsm]
    for ln in lines:
        if not ln.startswith("!Sample_"):
            continue
        parts = [p.strip().strip('"') for p in ln.split("\t")]
        key = parts[0]  # "!Sample_geo_accession" 等
        vals = parts[1:]
        if key == "!Sample_geo_accession" and not gsm_ids:
            gsm_ids = [v for v in vals if v]
        elif key == "!Sample_characteristics_ch1":
            # 每行一个 characteristics 字段,值为 "field_name: value"
            for v in vals:
                if ":" in v:
                    fk, fv = v.split(":", 1)
                    char_fields[fk.strip()].append(fv.strip())

    # ② 找矩阵起始行
    row_start = None
    for i, ln in enumerate(lines):
        if ln.startswith("!") or ln.startswith("^") or not ln.strip():
            continue
        parts = ln.split("\t")
        if len(parts) > 200 and any(x.replace(".", "").replace("-", "").isdigit() for x in parts[1:5]):
            row_start = i
            break

    if row_start is None:
        raise ValueError(f"无法在 {gz_path} 中找到矩阵行")

    # ③ 读矩阵
    probe_ids = []
    counts = []
    for ln in lines[row_start:]:
        if ln.startswith("!") or not ln.strip():
            continue
        parts = ln.split("\t")
        if len(parts) < 2:
            continue
        pid = parts[0].strip().strip('"')
        vals = []
        for v in parts[1:]:
            try:
                vals.append(float(v))
            except ValueError:
                vals.append(0.0)
        if len(vals) > len(gsm_ids):
            vals = vals[:len(gsm_ids)]
        elif len(vals) < len(gsm_ids):
            vals.extend([0.0] * (len(gsm_ids) - len(vals)))
        probe_ids.append(pid)
        counts.append(vals)

    # ④ 构建 per-GSM 元数据 dict
    meta_by_gsm = {}
    for i, g in enumerate(gsm_ids):
        meta_by_gsm[g] = {}
        for field, values in char_fields.items():
            if i < len(values) and values[i]:
                v = values[i]
                if ":" in v:
                    fk, fv = v.split(":", 1)
                    meta_by_gsm[g][fk.strip()] = fv.strip()
                else:
                    meta_by_gsm[g][field] = v

    return dict(
        gsm_ids=gsm_ids,
        probe_ids=probe_ids,
        counts=counts,
        meta_by_gsm=meta_by_gsm,
    )


def build_meta(matrix, verbose=True):
    """从 parsed matrix 构建 adapter 输出 dict。"""
    gsm_ids = matrix["gsm_ids"]
    meta_by_gsm = matrix["meta_by_gsm"]

    def get_val(gsm, *keys):
        m = meta_by_gsm.get(gsm, {})
        for k in keys:
            if k in m:
                return m[k]
        return None

    # gene alteration status
    gene_alter = defaultdict(list)
    for g in gsm_ids:
        v = get_val(g, "gene alteration status")
        if v:
            gene_alter[v].append(g)

    # relapse / death
    relapse_status = {}
    death_status = {}
    days_to_event = {}
    for g in gsm_ids:
        m = meta_by_gsm.get(g, {})
        rel = m.get("relapse", "")
        dep = m.get("death", "")
        dbe = m.get("days before death/censor", "")
        relapse_status[g] = rel
        death_status[g] = dep
        if dbe:
            try:
                days_to_event[g] = float(dbe)
            except ValueError:
                pass

    # pathological stage
    stage = {}
    for g in gsm_ids:
        v = get_val(g, "pathological stage")
        stage[g] = v if v else "unknown"

    # tissue
    tumor_gsms = [g for g in gsm_ids if get_val(g, "tissue") == "primary lung tumor"]
    normal_gsms = [g for g in gsm_ids if get_val(g, "tissue") == "normal lung"]

    # exclude
    exclude = set()
    for g in gsm_ids:
        v = get_val(g, "exclude for prognosis analysis due to incomplete resection or adjuvant therapy")
        if v == "exclude":
            exclude.add(g)

    prognos_gsms = [g for g in tumor_gsms if g not in exclude]

    if verbose:
        print(f"    [GSE31210] 总样本 {len(gsm_ids)} 个")
        print(f"    [GSE31210] 肿瘤 {len(tumor_gsms)}, 正常 {len(normal_gsms)}")
        print(f"    [GSE31210] 预后可用 {len(prognos_gsms)} 例 (排除 {len(exclude)})")
        print(f"    [GSE31210] 基因改变: {dict((k, len(v)) for k,v in gene_alter.items())}")
        n_ev = sum(1 for g in prognos_gsms if death_status.get(g) == "dead")
        print(f"    [GSE31210] 死亡事件 {n_ev} / {len(prognos_gsms)}")

    return dict(
        assay_type="mRNA_array",
        species="Homo sapiens",
        platform="GPL570",
        features=matrix["probe_ids"],
        counts=matrix["counts"],
        sample_ids=gsm_ids,
        groups=[get_val(g, "gene alteration status") or "unknown" for g in gsm_ids],
        unparsed=[],
        meta=dict(
            geo="GSE31210",
            assay_type="mRNA_array",
            species="Homo sapiens",
            n_sample=len(gsm_ids),
            n_feature=len(matrix["probe_ids"]),
            n_tumor=len(tumor_gsms),
            n_normal=len(normal_gsms),
            n_prognos=len(prognos_gsms),
            design="226 tumor + 20 normal, Affymetrix U133 Plus 2.0",
            has_clinical_outcome=True,
            has_pathway_annotation=False,
            is_single_cell=False,
            scale="log2_expression (原 MAS5, 取 log2(x+1) 转换)",
            gene_alteration=dict((k, len(v)) for k, v in gene_alter.items()),
            prognos_gsms=prognos_gsms,
            tumor_gsms=tumor_gsms,
            normal_gsms=normal_gsms,
            exclude_gsms=list(exclude),
            death_status=death_status,
            relapse_status=relapse_status,
            days_to_event=days_to_event,
            stage=stage,
        ),
    )


def load(datadir, verbose=True):
    """加载 GSE31210_series_matrix.txt.gz -> 同构 dict。"""
    gz_path = None
    for f in os.listdir(datadir):
        if "series_matrix" in f.lower() and f.endswith(".gz"):
            gz_path = os.path.join(datadir, f)
            break
    if not gz_path:
        raise FileNotFoundError(
            f"{datadir} 下未找到 series_matrix*.gz。"
            f"请确认 GSE31210_series_matrix.txt.gz 已就位。")

    if verbose:
        print(f"    [GSE31210] 加载 {gz_path}")
    matrix = parse_matrix_gz(gz_path)
    return build_meta(matrix, verbose)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--datadir", required=True)
    ap.add_argument("--json", default="")
    a = ap.parse_args()
    D = load(a.datadir)
    out = {k: v for k, v in D.items() if k not in ("counts", "features")}
    out["meta"]["prognos_n"] = out["meta"]["n_prognos"]
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    if a.json:
        full = {k: v for k, v in D.items()}
        json.dump(full, open(a.json, "w", encoding="utf-8"),
                  ensure_ascii=False, default=str)
        print(f"-> {a.json}")
