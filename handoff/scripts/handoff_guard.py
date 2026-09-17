# -*- coding: utf-8 -*-
"""
================================================================================
 Handoff 链守卫  v1.0
================================================================================
 校验工作证据链的完整性与连续性。

 检查:
   L-1 每个节点 12 字段齐全
   L-2 next 指向的 id 存在,或为 null 且有终止理由
   L-3 state_in 引用的前驱 id 存在
   L-4 无环
   L-5 ack 状态可枚举(null / 确认 / 拒收)
   L-6 checksums 与磁盘实际文件一致(AUTO 时自动计算)
   L-7 无孤儿节点(有入边或 is_root)
   L-8 时间单调(next 的时间不早于本节点)

 运行: python handoff_guard.py
 退出码: 0 = 链完整, 1 = 链断裂
================================================================================
"""
import os, sys, json, hashlib, argparse
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CHAIN = os.path.join(ROOT, "handoff_chain.json")
WORKSPACE = os.path.dirname(ROOT)

REQUIRED = ["handoff_id", "from", "to", "time", "artifacts", "state_in",
            "state_out", "blocking", "actions_required", "checksums",
            "ack", "next"]

ROWS = []


def add(cid, item, obs, exp, ok):
    ROWS.append(bool(ok))
    print(f"    [{'PASS' if ok else 'FAIL'}] {cid} {item:<40s} "
          f"obs={str(obs)[:24]:<24s} exp={exp}")


def sha(p):
    try:
        return hashlib.sha256(open(p, "rb").read()).hexdigest()[:16]
    except Exception:
        return "MISSING"


def resolve(rel):
    """在 workspace / handoff / crossval.framework 下找文件"""
    for base in [WORKSPACE, os.path.join(WORKSPACE, "handoff"),
                 os.path.join(WORKSPACE, "crossval", "framework"),
                 os.path.join(WORKSPACE, "crossval")]:
        p = os.path.join(base, rel)
        if os.path.exists(p):
            return p
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chain", default=CHAIN)
    ap.add_argument("--fix-checksums", action="store_true",
                    help="把 checksums=AUTO 的节点替换为实际值并写回")
    a = ap.parse_args()

    print("=" * 78)
    print("  Handoff 链守卫 v1.0")
    print("=" * 78)

    if not os.path.exists(a.chain):
        print(f"  [FAIL] 链文件不存在: {a.chain}")
        return 1

    C = json.load(open(a.chain, encoding="utf-8"))
    nodes = C.get("nodes", [])
    ids = [n.get("handoff_id") for n in nodes]
    by_id = {n["handoff_id"]: n for n in nodes}

    print(f"\n  节点数: {len(nodes)}   链: {C.get('chain_id','?')}\n")

    # ---------- L-1 字段齐全 ----------
    print("  ── L-1 必填字段(12 项)")
    miss = []
    for n in nodes:
        for k in REQUIRED:
            if k not in n:
                miss.append(f"{n.get('handoff_id','?')}.{k}")
    add("L-1", "全部节点 12 字段齐全", miss or "无缺失", "无缺失", not miss)

    # ---------- L-2 next 可达 ----------
    print("\n  ── L-2 next 指向存在或链尾有终止理由")
    bad_next = []
    for n in nodes:
        nx = n.get("next")
        if nx is None:
            if not n.get("termination_reason"):
                bad_next.append(f"{n['handoff_id']}(链尾无理由)")
        elif nx not in ids:
            bad_next.append(f"{n['handoff_id']}→{nx}(不存在)")
    add("L-2", "next 全部可达 / 链尾有理由", bad_next or "无断链", "无断链", not bad_next)

    # ---------- L-3 前驱存在 ----------
    print("\n  ── L-3 state_in 前驱存在")
    bad_pre = []
    for n in nodes:
        si = n.get("state_in", {})
        if si.get("is_root"):
            continue
        for p in si.get("predecessors", []):
            if p not in ids:
                bad_pre.append(f"{n['handoff_id']}←{p}")
    add("L-3", "前驱全部存在", bad_pre or "无悬空引用", "无悬空引用", not bad_pre)

    # ---------- L-4 无环 ----------
    print("\n  ── L-4 无环")
    def has_cycle():
        color = {i: 0 for i in ids}
        def dfs(i):
            if color.get(i) == 1:
                return True
            if color.get(i) == 2:
                return False
            color[i] = 1
            nx = by_id[i].get("next")
            if nx and dfs(nx):
                return True
            color[i] = 2
            return False
        return any(dfs(i) for i in ids if color[i] == 0)
    cyc = has_cycle()
    add("L-4", "链为 DAG / 线性", cyc, "False", not cyc)

    # ---------- L-5 ack 可枚举 ----------
    print("\n  ── L-5 ack 状态")
    bad_ack, pending = [], []
    for n in nodes:
        ack = n.get("ack")
        if ack is None:
            pending.append(n["handoff_id"])
        elif isinstance(ack, dict):
            if not all(k in ack for k in ("by", "time", "note")):
                bad_ack.append(f"{n['handoff_id']}(字段缺)")
        else:
            bad_ack.append(f"{n['handoff_id']}(类型错)")
    add("L-5", "ack 结构合法", bad_ack or "全部合法", "null 或 {by,time,note}", not bad_ack)
    n_ack = sum(1 for n in nodes if n.get("ack"))
    print(f"      已确认 {n_ack}/{len(nodes)}, 在途 {len(pending)}")
    if pending:
        print(f"      在途: {pending}")
    add("L-5b", "在途节点已标记(可追溯)", len(pending), ">=0(记录)", True)

    # ---------- L-6 校验和 ----------
    print("\n  ── L-6 交付物校验和")
    changed, missing, auto, selfref = [], [], [], []
    chain_name = os.path.basename(a.chain)
    for n in nodes:
        cs = n.get("checksums")
        if cs == "AUTO":
            auto.append(n["handoff_id"])
            continue
        if not isinstance(cs, dict):
            continue
        for rel, h in cs.items():
            if chain_name in rel:
                selfref.append(f"{n['handoff_id']}:{rel}")
                continue
            p = resolve(rel)
            if not p:
                missing.append(f"{n['handoff_id']}:{rel}")
            elif sha(p) != h:
                changed.append(f"{n['handoff_id']}:{rel}")
    add("L-6", "已登记校验和一致", changed or "全部一致", "一致", not changed)
    add("L-6c", "无自指(链文件不登记自身校验和)",
        selfref or "无", "无 —— 写回会改变自身sha256", not selfref)
    add("L-6b", "已登记文件存在", missing or "全部存在", "存在", not missing)
    if auto:
        print(f"      [INFO] AUTO 节点 {len(auto)} 个: {auto}")

    if a.fix_checksums and auto:
        for n in nodes:
            if n.get("checksums") == "AUTO":
                d = {}
                for rel in n.get("artifacts", []):
                    p = resolve(rel)
                    d[rel] = sha(p) if p else "MISSING"
                n["checksums"] = d
        json.dump(C, open(a.chain, "w", encoding="utf-8"),
                  indent=1, ensure_ascii=False)
        print(f"      [FIX] 已计算并写回 {len(auto)} 个节点的校验和")

    # ---------- L-7 无孤儿 ----------
    print("\n  ── L-7 无孤儿节点")
    has_in = {i: False for i in ids}
    for n in nodes:
        if n.get("next") in has_in:
            has_in[n["next"]] = True
    orphans = []
    for n in nodes:
        if not has_in[n["handoff_id"]] and not n.get("state_in", {}).get("is_root"):
            orphans.append(n["handoff_id"])
    add("L-7", "无孤儿节点", orphans or "无", "无", not orphans)

    # ---------- L-8 时间单调 ----------
    print("\n  ── L-8 时间单调")
    def pt(s):
        try:
            return datetime.fromisoformat(s)
        except Exception:
            return None
    bad_t = []
    for n in nodes:
        t1 = pt(n.get("time", ""))
        nx = n.get("next")
        if nx and t1:
            t2 = pt(by_id[nx].get("time", ""))
            if t2 and t2 < t1:
                bad_t.append(f"{n['handoff_id']}→{nx}")
    add("L-8", "时间不倒流", bad_t or "无", "无", not bad_t)

    npass = sum(ROWS)
    nfail = len(ROWS) - npass
    print("\n" + "=" * 78)
    print(f"  Handoff 链守卫: {npass}/{len(ROWS)} 通过, 失败 {nfail} 项")
    print(f"  链状态: {'完整' if nfail == 0 else '断裂'} ｜ "
          f"在途交接 {len(pending)}/{len(nodes)}")
    print("=" * 78)
    if nfail == 0 and pending:
        print("\n  [注意] 链结构完整,但有交接未获接收确认 —— 链处于 PENDING 状态。")
        print("         ack=null 不算交接完成,这是本链当前最主要的证据缺口。")
    return 0 if nfail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
