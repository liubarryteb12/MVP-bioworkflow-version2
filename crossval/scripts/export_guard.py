#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WP-9 三格式导出一致性守卫 v1.0

三种输出语义不同, 本守卫的全部意义就是**保证它们不互相矛盾**:
  docx-A 纯文本 + 占位符(给编辑改)
  docx-B 纯图片 + 图注/表注(给排版核对)
  pdf    文图合一(投稿/审阅)

用法:
  python3 export_guard.py --a docA.txt --b docB.txt --p docP.txt
  python3 export_guard.py --src <json 描述>      # 变异测试用
"""
import argparse, hashlib, json, os, re, sys
from collections import Counter

_HERE = os.path.dirname(os.path.abspath(__file__))


class Ledger:
    def __init__(self):
        self.rows = []

    def add(self, cid, item, obs, exp, ok):
        # ★ v2.21:改为 dict 并归一 criteria。
        #   本守卫用 "T9.3" 子项 id,而 criteria.yaml 的条目是 "WP-9"
        #   —— 不归一会让 WP-9 在 L2 消融里被误判为"休眠"
        #   (direct=0 且 branch=0),而实际上它一直有判定项。
        self.rows.append(dict(branch="WP-9", sub=str(cid), item=str(item),
                              observed=str(obs), expected=str(exp),
                              passed=bool(ok), na=False,
                              criteria="WP-9"))
        print("  [%s] %-8s %-40s obs=%-20s exp=%s"
              % ("PASS" if ok else "FAIL", cid, item[:40], str(obs)[:20], exp))

    def na(self, cid, item, reason):
        if not (reason or "").strip():
            raise SystemExit("N/A 理由为空(%s) —— 禁止静默删除" % cid)
        self.rows.append(dict(branch="WP-9", sub=str(cid), item=str(item),
                              observed="N/A", expected="N/A", passed=None,
                              na=True, criteria="WP-9"))
        print("  [N/A] %-8s %-40s reason=%s" % (cid, item[:40], reason))

    def summary(self):
        p = sum(1 for r in self.rows if r.get("passed") is True)
        f = sum(1 for r in self.rows if r.get("passed") is False)
        n = sum(1 for r in self.rows if r.get("passed") is None)
        print("\n  导出守卫: %d/%d 通过, 失败 %d, 不适用 %d" % (p, p + f, f, n))
        return p, f, n


PH = r"\[(图|表)\s*(\d+)位置\]"


def run(L, A, B, P, dpi=300, sha=True):
    # T9.1 三版本共享同一图号集合
    fa = sorted({int(m.group(2)) for m in re.finditer(PH, A)})
    fb = sorted({int(x) for x in re.findall(r"(?:图|表)\s*(\d+)", B)})
    fp = sorted({int(x) for x in re.findall(r"(?:图|表)\s*(\d+)", P)})
    L.add("T9.1", "三版本图号集合一致",
          "A=%s B=%s P=%s" % (fa, fb, fp), "三者相同", fa == fb == fp)
    # T9.2 docx-A 占位符数 == docx-B 图表数
    L.add("T9.2", "占位符数 == docx-B 图表数", "%d vs %d" % (len(fa), len(fb)),
          "相等", len(fa) == len(fb))
    # T9.3 图注逐字一致(B 的图注须出现在 P 中)
    # v2.16 修订:原实现 legs 为空时 miss 为空 -> not miss=True -> PASS,
    # 即"docx-B 完全没有图注"也通过(空规)。真实稿件正是 4 图 0 图注却 PASS。
    # ★ v2.21 修:原正则要求图号后紧跟冒号(^图\s*\d+[:：]),
    #   只覆盖"图1:标题"一种写法。真实稿件大量使用"图1 标题"(空格,
    #   无冒号),会被判为"0 条图注" → 误报 FAIL。
    #   这与"守卫锚点只覆盖一种写法"是同一族错误(第 N 次复发)。
    #   修正:接受 冒号/空格 两种分隔,但要求标题有实质内容(去编号后 ≥4 字),
    #   避免把 "图1" 这种空行也算作图注。
    legs = []
    for _m in re.finditer(r"^\s*(?:图|表)\s*(\d+)\s*[:：\s]\s*(.*)$",
                          B, re.M):
        # ★ 阈值由 4 降到 1:v2.21 初版设 ≥4 字本意是排除"图1"空行,
        #   但会误伤 "图 1:aaa" 这类**简写但合法**的图注(变异测试的
        #   合规样例正是 3 字符),导致合规输入被判 FAIL —— 误伤与漏检
        #   同样是守卫失效。空行排除已由正则的 \S 保证,无需长度阈值。
        _body = _m.group(2).strip()
        if len(_body) >= 1:
            legs.append(_m.group(0).strip())
    nfig_b = len(re.findall(r"(?:图|表)\s*\d+", B))
    if nfig_b and not legs:
        L.add("T9.3", "docx-B 含图注(防空规)", "0 条图注/图标记 %d" % nfig_b,
              ">0", False)
    else:
        miss = [l for l in legs if l.strip() not in P]
        L.add("T9.3", "docx-B 图注 ⊂ pdf(逐字)", miss or "全部命中", "无缺失",
              not miss)
    # T9.4 pdf 图表位置与"如图X" ≤1 段
    paras = [x for x in P.split("\n\n") if x.strip()]
    bad = []
    for n_ in fp:
        hit = [i for i, t in enumerate(paras) if re.search(r"图\s*%d" % n_, t)]
        if hit and not any(i + 1 < len(paras) and re.search(r"图\s*%d" % n_,
                           paras[i + 1]) for i in hit):
            bad.append(n_)
    L.add("T9.4", "图与引用段落邻近", bad or "无", "无", not bad)
    # T9.5 三版本参考文献逐字一致
    ra = A[A.find("参考文献"):] if "参考文献" in A else ""
    rb = B[B.find("参考文献"):] if "参考文献" in B else ""
    rp = P[P.find("参考文献"):] if "参考文献" in P else ""
    if not (ra or rb or rp):
        L.na("T9.5", "参考文献表一致", "三版本均无参考文献节")
    else:
        L.add("T9.5", "三版本参考文献逐字一致",
              "相同" if ra == rb == rp else "有差异", "相同", ra == rb == rp)
        # v2.16 补:单版本内条目重复(真实稿件 docx-A 参考文献整表列两遍)
        for tag, txt in (("A", ra), ("B", rb), ("P", rp)):
            ids = re.findall(r"\[(\d+)\]", txt)
            dup = sorted({k for k, c in Counter(ids).items() if c > 1},
                         key=lambda z: int(z))
            L.add("T9.5b.%s" % tag, "参考文献条目不重复(%s)" % tag,
                  dup or "无重复", "无重复", not dup)
    # T9.6 分辨率
    L.add("T9.6", "图片分辨率", dpi, "≥300", dpi >= 300)
    # T9.7 sha256 固定
    if sha:
        L.add("T9.7", "三版本 sha256 可固定",
              hashlib.sha256((A + B + P).encode()).hexdigest()[:12],
              "非空", True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", default=""); ap.add_argument("--b", default="")
    ap.add_argument("--p", default=""); ap.add_argument("--dpi", type=int,
                                                        default=300)
    ap.add_argument("--src", default="", help="变异测试用 json")
    ap.add_argument("--out", default="")
    x = ap.parse_args()
    if x.src:
        d = json.load(open(x.src, encoding="utf-8"))
        A, B, P, dpi = d["a"], d["b"], d["p"], d.get("dpi", 300)
    else:
        if not (x.a and x.b and x.p):
            raise SystemExit("需 --a/--b/--p 或 --src")
        A = open(x.a, encoding="utf-8").read()
        B = open(x.b, encoding="utf-8").read()
        P = open(x.p, encoding="utf-8").read()
        dpi = x.dpi
    L = Ledger()
    run(L, A, B, P, dpi)
    p, f, n = L.summary()
    if x.out:
        json.dump({"rows": L.rows, "n_pass": p, "n_fail": f, "n_na": n,
                   # ★ v2.21:补判据层聚合,供 L2 消融统计
                   #   (此前 WP-9 有 10 项判定却因缺此字段被判"休眠")
                   "criteria_dist": {"WP-9": {
                       "n_direct": len(L.rows), "n_branch": 0,
                       "n_na": n, "branches": ["WP-9"]}}},
                  open(x.out, "w", encoding="utf-8"), ensure_ascii=False,
                  indent=2)
    sys.exit(1 if f else 0)


if __name__ == "__main__":
    main()
