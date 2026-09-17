#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
判据消融(L2)/N-A 出口消融(L2')/组件增益(L3) —— v2.21 新增

起因(审核对 v2.20 的裁定):
    "v2.20 花 60 个变异用例证明『守卫会抓』,但从没花 5 分钟统计
     『46 条判据里哪几条在干活』。前者是 L1 消融的完美实现,后者的
     完全空白 —— 而 v2.20 把判据从 42 涨到 46、判定项从 160 涨到 201,
     让这个空白比 v2.19 时更值钱了。"

本脚本回答三个此前**完全无法回答**的问题:

  L2  判据消融   —— 46 条判据里,哪些在贡献判定项,哪些只是名义存在?
  L2' N/A 出口   —— 声称有 na_when 的判据,是否真的能走到 N/A?
  L3  组件增益   —— 多组件整合是否真的带来增益(而非只报全组件性能)?

设计纪律(与框架既有纪律一致):
  1. 三档判定,不是二值:骨架 / 冗余 / 休眠(与 H-2 双阈值同构)
  2. 空规自检:每个新增检查必须能构造 FAIL(先红后绿)
  3. 禁止静默 except
  4. 两种口径分开报(direct 精确 / branch 粗粒度),不混加
"""
import os
import re
import sys
# ── 控制台编码加固（v2.25）──────────────────────────────────────────────────
# 起因：中文 Windows 默认控制台 cp936(GBK) 无法编码 ⚠ → UnicodeEncodeError，
#   在接近终点处崩溃、台账不落盘。处置：重定向强制 UTF-8；控制台替换不可编码字符。
try:
    if sys.stdout.isatty():
        sys.stdout.reconfigure(errors="replace")
    else:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(errors="replace")
except (AttributeError, ValueError):
    pass
import json
import argparse
import collections

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RES = os.path.join(ROOT, "results")

# 非 criteria.yaml 的伪判据(框架内部机制,不是科学判据)
PSEUDO = {"HARDBLOCK", "SEEDROBUST", "ISOLATION", "WP-CORE", "GLOBAL"}

# ── T37 阈值(v2.23)──────────────────────────────────────────────
# 三态,与 H-2 双阈值同构:不是二值,中间态是 warn 而非"通过"。
T37_FAIL = 0.20      # 休眠率 >= 20% → fail(判"判据膨胀")
MONOPOLY = 0.40      # 单条判据 n_direct/总判定项 > 40% → warn(垄断)
GLOBAL_MAX = 0.10    # GLOBAL 占比 >= 10% → warn(归因稀释)
META_EXEMPT = {"T37"}  # ★ 自指豁免:T37 不统计自己(见 criteria invariants)
# ★ v2.22:GLOBAL = 跨判据的全局自检项(如"夹具全部按预期拦截")。
#   它不专属任何单条判据 —— 硬塞给某条会**虚增该判据贡献**,制造
#   虚假归因。与第 11 条同源:宁可单独列为"非判据",不可粉饰覆盖率。


def _load():
    rep_p = os.path.join(RES, "report.json")
    cri_p = os.path.join(ROOT, "schema", "criteria.yaml")
    if not os.path.isfile(rep_p):
        raise SystemExit(f"[FATAL] 缺 {rep_p};先跑 verify_all.py")
    if not os.path.isfile(cri_p):
        raise SystemExit(f"[FATAL] 缺 {cri_p}")
    rep = json.load(open(rep_p, encoding="utf-8"))
    cri = yaml.safe_load(open(cri_p, encoding="utf-8"))
    return rep, cri


def _load_all():
    rep, cri = _load()
    counts = {}
    dist = _dist(rep)
    dist, has_wp = _merge_writing(dist, counts)
    return rep, cri, dist, has_wp, counts


def _merge_writing(dist, counts=None):
    """并入写作层(writing_guard)判定项。

    ★ v2.21:初版消融器只读 verify_all.py 的 report.json,把 WP-1~WP-9
      全部误判为"休眠" —— 实际上它们由 writing_guard.py 验证,
      只是**结果在另一份台账里**。这是消融器自身的覆盖盲区,
      与"守卫扫错文档"同族(第 8 次复发)。
    """
    # WP-1~WP-8 来自 writing_guard,WP-9 来自 export_guard(独立脚本)
    merged = False
    for fn in ("writing_report.json", "export_report.json"):
        p = os.path.join(RES, fn)
        if os.path.isfile(p):
            _merge_one(dist, p)
            merged = True
            if counts is not None:
                w = json.load(open(p, encoding="utf-8"))
                counts[fn] = len(w.get("rows", []))
    return dist, merged


def _merge_one(dist, p):
    w = json.load(open(p, encoding="utf-8"))
    for cid, v in (w.get("criteria_dist") or {}).items():
        d = dist.setdefault(cid, {"n_direct": 0, "n_branch": 0,
                                  "n_na": 0, "branches": []})
        d["n_direct"] += v.get("n_direct", 0)
        d["n_branch"] += v.get("n_branch", 0)
        d["n_na"] += v.get("n_na", 0)
        for b in v.get("branches", []):
            if b not in d["branches"]:
                d["branches"].append(b)


def _dist(rep):
    """兼容两种 report:新版带 criteria_dist,旧版现算。"""
    d = rep.get("summary", {}).get("criteria_dist")
    if d:
        return d
    out = collections.defaultdict(lambda: {"n_direct": 0, "n_branch": 0,
                                           "n_na": 0, "branches": set()})
    for r in rep.get("ledger", []):
        raw = str(r.get("criteria") or "")
        src = r.get("criteria_src", "branch")
        precise = src in ("item", "explicit", "branch_single")
        for cid in [x.strip() for x in raw.split(",") if x.strip()]:
            out[cid]["n_direct" if precise else "n_branch"] += 1
            if r.get("na"):
                out[cid]["n_na"] += 1
            out[cid]["branches"].add(str(r.get("branch")))
    return {k: {"n_direct": v["n_direct"], "n_branch": v["n_branch"],
                "n_na": v["n_na"], "branches": sorted(v["branches"])}
            for k, v in out.items()}


def _classify(dist, cri_ids):
    """三档分类:
       骨架判据 —— direct >= 1(判定项由 item 前缀直接归因,不可替代)
       粗粒判据 —— direct = 0 但 branch >= 1(仅分支级归因,粒度待提升)
       休眠判据 —— direct = 0 且 branch = 0(从未被任何判定项触发)
    """
    rows = []
    for cid in cri_ids:
        d = dist.get(cid, {"n_direct": 0, "n_branch": 0, "n_na": 0,
                           "branches": []})
        nd, nb = d["n_direct"], d["n_branch"]
        if nd >= 1:
            tier, why = "骨架", f"direct={nd}"
        elif nb >= 1:
            tier, why = "粗粒", "仅分支级归因,direct=0"
        else:
            tier, why = "休眠", "无任何判定项归因"
        rows.append(dict(id=cid, tier=tier, n_direct=nd, n_branch=nb,
                         n_na=d["n_na"], branches=d.get("branches", []),
                         why=why))
    # 报告里出现但 criteria.yaml 没有的(伪判据单独列出,不混入)
    extra = [dict(id=k, tier="伪判据", n_direct=v["n_direct"],
                  n_branch=v["n_branch"], n_na=v["n_na"],
                  branches=v.get("branches", []), why="非科学判据(机制自检)")
             for k, v in dist.items() if k in PSEUDO]
    return rows, extra


def _t37(dist, cri_ids, total, exempt=META_EXEMPT):
    """T37 · 判据体系的骨架/休眠比例(L2 消融的**判定层**)。

    ★ v2.23 补最后一层:v2.22 有了 criteria_dist(体温表),却没有一条
      判据来读这张表并下诊断。骨架/休眠比例此前**可以自我声明**,
      无独立检查 —— 这是第 11 条陷阱在判据层的残留形态。

    三态(与 H-2 双阈值同构,禁止压缩为二值):
      休眠率 == 0       → pass
      0 < 休眠率 < 20%  → warn(须逐条声明休眠原因)
      休眠率 >= 20%     → fail(判"判据膨胀")

    ★ 自指口径:T37 自身从分子分母**均排除**。若计入,等于 T37 用
      "自己给自己打的分数"判定自己 —— 与 report_guard 不计入自身
      合法集、链文件不登记自身 sha256 同规。
    """
    scope = [c for c in cri_ids if c not in exempt]
    dormant = []
    for cid in scope:
        d = dist.get(cid, {})
        if d.get("n_direct", 0) == 0 and d.get("n_branch", 0) == 0:
            dormant.append(cid)
    n_total = len(scope)
    rate = len(dormant) / max(1, n_total)

    n_global = dist.get("GLOBAL", {}).get("n_direct", 0)
    pct_g = n_global / max(1, total)
    mono = []
    for cid in scope:
        nd = dist.get(cid, {}).get("n_direct", 0)
        if total and nd / total > MONOPOLY:
            mono.append((cid, nd))

    if rate >= T37_FAIL:
        verdict = "fail"
    elif rate > 0 or pct_g >= GLOBAL_MAX or mono:
        verdict = "warn"
    else:
        verdict = "pass"
    return dict(verdict=verdict, rate=round(rate, 4), n_total=n_total,
                dormant=sorted(dormant), pct_global=round(pct_g, 4),
                monopoly=mono, n_global=n_global)


def _l2_na_check(cri):
    """L2' N/A 出口检查:声称有 na_when 的判据,是否有 N/A 判定项佐证。

    v2.20 的 summary 是 n_na = 0 —— 主 run 从未走到任何 N/A。
    这与第 11 条陷阱同源:**规则从未跑到过应触发的输入**。
    本检查不判 FAIL(主 run 本就该全触发),但**必须如实暴露**。
    """
    declared = []
    for c in cri.get("criteria", []):
        txt = json.dumps(c, ensure_ascii=False)
        if "na_when" in txt or "N/A" in txt or "不适用" in txt:
            declared.append(c.get("id"))
    return declared


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true", help="只输出 JSON")
    ap.add_argument("--self-test", action="store_true",
                    help="变异自检:构造违规,验证本脚本能 FAIL")
    a = ap.parse_args()

    if a.self_test:
        return _self_test()

    rep, cri, dist, has_wp, counts = _load_all()
    cri_ids = [c.get("id") for c in cri.get("criteria", []) if c.get("id")]
    # ★ v2.23:T37 的判定项由**本脚本**产生 —— 它读 criteria_dist 下诊断,
    #   若在 verify_all 内实现则"统计自己的分布会改变分布"(自指)。
    #   合并进 dist 使 _classify 看见 T37 有判定项(判为骨架),避免
    #   报表出现"休眠 1: T37"而与 A-7 的"休眠 0/50"自相矛盾。
    #   注意:合并只影响**分类口径**;休眠率统计仍排除 T37(META_EXEMPT),
    #   故不构成"自己给自己打分"。
    _d37 = dist.setdefault("T37", {"n_direct": 0, "n_branch": 0,
                                   "n_na": 0, "na_tested": 0, "branches": []})
    _d37["n_direct"] += 1
    rows, extra = _classify(dist, cri_ids)
    # implement 有判定项但 criteria.yaml 未声明 → 声明 vs 实现不一致
    declared = set(cri_ids)
    undeclared = sorted(k for k in dist
                        if k not in declared and k not in PSEUDO)

    # ★ v2.22 口径修复:初版分子含写作层(42)+导出层(10),分母却只有
    #   主 run(222)→ 覆盖率 110.8% > 100%,是不可能值。三源必须同口径。
    total_main = rep.get("summary", {}).get("total", len(rep.get("ledger", [])))
    total_wp = counts.get("writing_report.json", 0)
    total_ex = counts.get("export_report.json", 0)
    total = total_main + total_wp + total_ex
    # 分子亦须含 PSEUDO(它们也是真实判定项),否则分子分母仍不同口径
    n_direct_all = sum(v.get("n_direct", 0) for v in dist.values())
    n_direct = sum(r["n_direct"] for r in rows)   # 仅科学判据(报表用)
    n_branch = sum(r["n_branch"] for r in rows)

    skel = [r for r in rows if r["tier"] == "骨架"]
    coarse = [r for r in rows if r["tier"] == "粗粒"]
    dormant = [r for r in rows if r["tier"] == "休眠"]

    pct_dorm = len(dormant) / max(1, len(rows))
    # 判定:休眠 >= 20% → 判据体系膨胀(审核建议的阈值)
    verdict_dorm = "FAIL" if pct_dorm >= 0.20 else "PASS"
    # 判定:direct 覆盖率(有多少判定项能精确到判据)
    cov_direct = n_direct_all / max(1, total)
    verdict_cov = "FAIL" if cov_direct < 0.50 else "PASS"

    # ★ v2.22 新增 A-6:归因错配检测。
    #   反证发现:把分支10 三条判定项从 T06 改判 GLOBAL 后,
    #   **direct 覆盖率仍是 100%** —— 该指标只衡量"有没有归因",
    #   不衡量"归给谁"。真正能抓"归因错对象"的是休眠/骨架分类。
    #   故补一条:GLOBAL 占比异常升高 = 归因被稀释,不是健康信号。
    n_global = dist.get("GLOBAL", {}).get("n_direct", 0)
    pct_global = n_global / max(1, total)
    ok_global = pct_global < 0.10
    checks_extra = [dict(
        id="A-6", name="归因未稀释(GLOBAL 占比 <10%)",
        observed=f"{n_global}/{total} ({pct_global:.1%})",
        expected="<10%", passed=ok_global,
        note="GLOBAL=跨判据全局自检项;占比突增说明判定项被推给兜底标签")]
    na_declared = _l2_na_check(cri)
    n_na = rep.get("summary", {}).get("n_na", 0)

    # ★ v2.23:T37 —— L2 消融的**判定层**。
    #   此前 ablation 只"产出数据"(休眠/骨架分布),没有一条判据读它
    #   并下诊断 → 结构健康度可自我声明。T37 补上这一层。
    #   三态:pass / warn / fail。warn 不导致整体 FAIL(它要求"逐条声明
    #   休眠原因",不是失败),但 fail 必须 FAIL。
    t37 = _t37(dist, cri_ids, total)
    # ★ 自指口径校验:若 T37 被计入,等于自己给自己打分 → 必须排除
    assert "T37" not in t37["dormant"] or "T37" not in cri_ids, \
        "[FATAL] T37 不得统计自身(自指)"

    out = dict(
        version="v2.21",
        total_items=total,
        n_criteria=len(rows),
        n_direct=n_direct, n_branch=n_branch,
        n_direct_all=n_direct_all,
        total_main=total_main, total_writing=total_wp, total_export=total_ex,
        direct_coverage=round(cov_direct, 4),
        tiers=dict(骨架=len(skel), 粗粒=len(coarse), 休眠=len(dormant)),
        dormant_ids=[r["id"] for r in dormant],
        coarse_ids=[r["id"] for r in coarse],
        dormant_pct=round(pct_dorm, 4),
        writing_merged=has_wp,
        undeclared_in_criteria=undeclared,
        na_declared_count=len(na_declared),
        na_actual=n_na,
        rows=rows, extra=extra,
        checks=[
            dict(id="A-1", name="休眠判据占比 < 20%",
                 observed=f"{pct_dorm:.1%}",
                 expected="<20%", passed=verdict_dorm == "PASS"),
            dict(id="A-2", name="direct 归因覆盖率 >= 50%",
                 observed=f"{cov_direct:.1%}",
                 expected=">=50%", passed=verdict_cov == "PASS"),
            dict(id="A-3", name="N/A 出口已声明(存在 na_when)",
                 observed=str(len(na_declared)), expected=">=1",
                 passed=len(na_declared) >= 1),
            dict(id="A-5", name="implement 与 criteria 声明一致",
                 observed=(str(len(undeclared)) +
                           ("(" + ",".join(undeclared[:4]) + "...)"
                            if undeclared else "")),
                 expected="0", passed=len(undeclared) == 0),
            # ★ 如实暴露,不判 FAIL 也不掩饰:主 run 天然全触发
            *checks_extra,
            # ★ v2.23 A-7 = T37 判定层:读 criteria_dist 并下诊断
            dict(id="A-7", name="T37 判据体系健康度(休眠率三态)",
                 observed=(f"{t37['verdict']} rate={t37['rate']:.1%} "
                           f"休眠={len(t37['dormant'])}/{t37['n_total']}"),
                 expected="pass(休眠率=0 且 GLOBAL<10% 且无垄断)",
                 passed=t37["verdict"] != "fail",
                 note=("fail→判据膨胀;warn→须逐条声明休眠原因。"
                       "阈值 fail>=20% / 垄断>40% / GLOBAL>=10%")),
            dict(id="A-4", name="[暴露] 主 run N/A 数",
                 observed=n_na, expected="主 run 本就全触发,故为 0",
                 passed=True,
                 note=("N/A 出口是否真能走到,需由 --self-test 的 N/A 夹具验证;"
                       "★ v2.23 新增 na_tested 字段区分『未测』与『测过但记 PASS』")),
        ],
        t37=t37,
    )
    ok = all(c["passed"] for c in out["checks"])
    out["verdict"] = "PASS" if ok else "FAIL"

    if a.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0 if ok else 1

    print("=" * 78)
    print("  L2 判据消融 · 判据触发分布")
    print("=" * 78)
    print(f"    判定项总数 {total}   判据数 {len(rows)}   "
          f"(写作层已并入:{'是' if has_wp else '否'})")
    if undeclared:
        print(f"    ⚠ criteria.yaml 未声明但 implement 有判定项:"
              f"{', '.join(undeclared)}")
    print(f"    判定项:主 run {total_main} + 写作 {total_wp} + 导出 {total_ex} = {total}")
    print(f"    direct 归因 {n_direct_all}/{total} ({cov_direct:.1%})   "
          f"branch 归因 {n_branch}(粗粒度,会重复计)")
    print()
    print(f"    骨架判据 {len(skel)}   粗粒判据 {len(coarse)}   "
          f"休眠判据 {len(dormant)}")
    if dormant:
        print(f"    ⚠ 休眠(从未被任何判定项触发):{', '.join(r['id'] for r in dormant)}")
    if coarse:
        print(f"    ⚠ 粗粒(仅分支级归因):{', '.join(r['id'] for r in coarse)}")
    print()
    print("    触发分布 Top-10(direct):")
    for r in sorted(rows, key=lambda x: -x["n_direct"])[:10]:
        print(f"      {r['id']:10s} direct={r['n_direct']:3d} "
              f"branch={r['n_branch']:3d}  {r['tier']}")
    print()
    print("    检查项:")
    for c in out["checks"]:
        flag = "PASS" if c["passed"] else "FAIL"
        print("      [%s] %-4s %-34s obs=%-22s exp=%s"
              % (flag, c["id"], c["name"], str(c["observed"])[:22],
                 c["expected"]))
    print()
    print(f"  结论: {out['verdict']}")
    return 0 if ok else 1


# ------------------------------------------------------------ 变异自检
def _self_test():
    """构造违规 → 本脚本必须 FAIL。证明消融器本身不是空规。"""
    import tempfile, shutil
    global RES
    bak = RES
    cases = []

    def _run_with(mutate):
        global RES
        tmp = tempfile.mkdtemp(prefix="abl_")
        shutil.copytree(bak, tmp, dirs_exist_ok=True)
        RES = tmp
        try:
            mutate(tmp)
            import io, contextlib
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = main_impl()
            return rc
        finally:
            RES = bak
            shutil.rmtree(tmp, ignore_errors=True)

    def _mutate_report(fn):
        p = os.path.join(bak, "report.json")
        d = json.load(open(p, encoding="utf-8"))
        fn(d)
        def _w(tmp):
            json.dump(d, open(os.path.join(tmp, "report.json"), "w",
                              encoding="utf-8"), ensure_ascii=False)
        return _w

    # C-1 清空 ledger → direct 覆盖率 0 → A-2 应 FAIL
    def _clear(d):
        d["ledger"] = []
        d["summary"]["total"] = 0
        d["summary"]["criteria_dist"] = {}
    rc = _run_with(_mutate_report(_clear))
    cases.append(("C-1 清空台账 → direct 覆盖率归零", rc == 1, rc))

    # C-2 抽掉 >20% 判据的归因 → 休眠占比越线,应 FAIL。
    #    ★ 教训:初版只抽 1 条(T21),休眠占比 1/50=2% < 20% 阈值,
    #      rc=0 —— 是用例设计错,不是检测失效。变异用例必须**真的越线**。
    def _drop(d):
        cd = d.get("summary", {}).get("criteria_dist", {})
        victims = [k for k in cd if k not in PSEUDO][:11]
        for k in victims:
            cd[k]["n_direct"] = 0
            cd[k]["n_branch"] = 0
    rc = _run_with(_mutate_report(_drop))
    cases.append(("C-2 抽掉 11 条判据归因 → 休眠越线", rc == 1, rc))

    # C-3 把 GLOBAL 占比灌到 50% → A-6 应 FAIL(归因稀释)
    def _flood(d):
        cd = d.get("summary", {}).get("criteria_dist", {})
        cd.setdefault("GLOBAL", {"n_direct": 0, "n_branch": 0})
        cd["GLOBAL"]["n_direct"] = 500
    rc = _run_with(_mutate_report(_flood))
    cases.append(("C-3 GLOBAL 占比灌至 >100% → A-6 应 FAIL", rc == 1, rc))

    # C-4 ★ v2.23:T37 **判定层自身**的变异测试(先红后绿)。
    #   C-1~C-3 验证的是 ablation 的既有检查;T37 是**新判据**,必须
    #   单独证明它能从非 fail 翻到 fail —— 否则"有数据、无诊断"这个
    #   缺口只是被搬了个位置,并没有真正补上(第 11 条形态①)。
    rep0 = json.load(open(os.path.join(bak, "report.json"), encoding="utf-8"))
    cri0 = yaml.safe_load(open(os.path.join(ROOT, "schema", "criteria.yaml"),
                               encoding="utf-8"))
    dist0 = _dist(rep0)
    dist0, _ = _merge_writing(dist0)
    ids0 = [c.get("id") for c in cri0.get("criteria", []) if c.get("id")]
    total0 = rep0.get("summary", {}).get("total", 0)
    t_base = _t37(dist0, ids0, total0)

    scope = [c for c in ids0 if c not in META_EXEMPT and c not in PSEUDO]
    n_freeze = max(1, int(len(scope) * 0.30))   # 冻结 30% → 休眠率 30% ≥ 20%
    dist_f = {k: dict(v) for k, v in dist0.items()}
    for cid in scope[:n_freeze]:
        dist_f[cid] = {"n_direct": 0, "n_branch": 0, "n_na": 0, "branches": []}
    t_fail = _t37(dist_f, ids0, total0)

    cases.append((
        f"C-4 T37 判定层:基线={t_base['verdict']} → "
        f"冻结 {n_freeze} 条后={t_fail['verdict']}(须 fail)",
        t_fail["verdict"] == "fail" and t_base["verdict"] != "fail",
        0 if t_fail["verdict"] == "fail" else 1))

    print("  [变异自检] L2 消融器")
    for name, ok, rc in cases:
        print(f"    [{'PASS' if ok else 'FAIL'}] {name}  rc={rc}")
    allok = all(c[1] for c in cases)
    print(f"  变异自检:{'全部生效' if allok else '存在空规'}")
    return 0 if allok else 1


def main_impl():
    """供 self_test 调用的非 argparse 版本(口径与 main 严格一致)。"""
    rep, cri, dist, _, counts = _load_all()
    cri_ids = [c.get("id") for c in cri.get("criteria", []) if c.get("id")]
    # ★ v2.23:与 main 同口径 —— 合并 T37 判定项(仅影响分类,不影响休眠率)
    _d37 = dist.setdefault("T37", {"n_direct": 0, "n_branch": 0,
                                   "n_na": 0, "na_tested": 0, "branches": []})
    _d37["n_direct"] += 1
    rows, _ = _classify(dist, cri_ids)
    total_main = rep.get("summary", {}).get("total", len(rep.get("ledger", [])))
    total = (total_main + counts.get("writing_report.json", 0)
             + counts.get("export_report.json", 0))
    n_direct_all = sum(v.get("n_direct", 0) for v in dist.values())
    cov = n_direct_all / max(1, total) if total else 0.0
    pct_dorm = len([r for r in rows if r["tier"] == "休眠"]) / max(1, len(rows))
    n_global = dist.get("GLOBAL", {}).get("n_direct", 0)
    pct_g = n_global / max(1, total)
    # ★ v2.23:T37 判定层纳入(与 main 口径严格一致)
    t37 = _t37(dist, cri_ids, total)
    ok = ((pct_dorm < 0.20) and (cov >= 0.50) and (pct_g < 0.10)
          and t37["verdict"] != "fail")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
