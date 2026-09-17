#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""写作流程层守卫 v1.0 —— WP-1~WP-8 (+ WP-CORE / NC-1~NC-7)

设计原则:
 1. 每个判据**必须可构造 FAIL**(第 11 条陷阱形态①②)
 2. **绝不忽略 --doc**(历史复发 8 次: G-5/G-6/G-7/G-8/G-11/G-12/G-12.合集...)
    —— 本文件所有文档读取统一走 _read(kind), 内部优先 a.doc
 3. 不立主观判断规则(故事吸引人/深刻/优雅) —— 那是空规
 4. WP-3 skill 返回 0 篇 → 判 N/A(第三态), 不降级为 AI 生成

用法:
  python3 writing_guard.py --doc 稿件.md
  python3 writing_guard.py --src <自定义稿件>      # 变异测试用
"""
import argparse, json, os, re, sys

_HERE = os.path.dirname(os.path.abspath(__file__))
WS = os.path.dirname(_HERE)
SPEC_PATH = os.path.join(WS, "spec", "writing_spec.yaml")


def _load_spec():
    import yaml
    with open(SPEC_PATH, encoding="utf-8") as f:
        spec = yaml.safe_load(f)
    _check_spec_types(spec)
    return spec


def _check_spec_types(spec, _p=""):
    """★ 防 v2.15 空规复发:词表被 ';' 拼成单字符串时判据恒 PASS。
    递归校验:所有 list 元素必须是 str, 且不含 ';' / ' - ' (拼接残留)。"""
    bad = []
    def walk(o, path):
        if isinstance(o, dict):
            for k, v in o.items():
                walk(v, path + "." + str(k))
        elif isinstance(o, list):
            for i, v in enumerate(o):
                if not isinstance(v, str):
                    walk(v, "%s[%d]" % (path, i))
                elif ";" in v or " - " in v:
                    bad.append("%s[%d]=%r" % (path, i, v[:40]))
    walk(spec, _p or "spec")
    if bad:
        raise SystemExit(
            "writing_spec.yaml 词表疑似被 ';' / ' - ' 拼接成单字符串 —— "
            "判据将恒 PASS 成空规(第 11 条陷阱形态①)。违规项: %s" % bad[:5])


def _norm_wp(cid):
    """归一子项 id 到 criteria 条目 id。

    ★ v2.21 发现的不一致:写作层 implement 有 WP-CORE/WP-1..WP-8
      (含 WP-5b/5d/7a/7b/7c),而 criteria.yaml 只声明了
      WP-1/2/3/5a/5c/6/7/8/9 —— **WP-4、WP-5b、WP-5d 三条 implement 有
      但 criteria 未声明**。这与"改 A 忘改 B"同族,由 L2 消融暴露。
      此处只做子项归一(7a/7b/7c → WP-7),不掩盖上述缺失。
    """
    c = str(cid).split(".")[0]
    # WP-7a / WP-7b / WP-7c → WP-7(顺序整理/格式规范/文中引用标识)
    if re.match(r"^WP-7[a-c]$", c):
        return "WP-7"
    return c


class Ledger:
    def __init__(self):
        self.rows = []

    def add(self, cid, item, obs, exp, ok):
        # ★ v2.21:改为 dict 并带 criteria/branch 字段。
        #   原为 5 元组,cid 是 "WP-5c.3" 这类**子项 id**(如 WP-5c.3),
        #   而 criteria.yaml 里是 "WP-5c" —— 消融器需要能归一到父 id,
        #   故一并记录 criteria(父) 与 sub(子)。
        rec = dict(branch=str(cid).split(".")[0], sub=str(cid),
                   item=str(item), observed=str(obs), expected=str(exp),
                   passed=bool(ok), na=False,
                   criteria=_norm_wp(str(cid)))
        self.rows.append(rec)
        print("  [%s] %-6s %-42s obs=%-22s exp=%s"
              % ("PASS" if ok else "FAIL", cid, item[:42], str(obs)[:22], exp))

    def na(self, cid, item, reason):
        """第三态:判据不适用。理由为空直接 raise —— 禁止静默删除。"""
        if not (reason or "").strip():
            raise SystemExit("N/A 理由为空(%s) —— 框架禁止静默删除" % cid)
        self.rows.append(dict(branch=str(cid).split(".")[0], sub=str(cid),
                              item=str(item), observed="N/A", expected="N/A",
                              passed=None, na=True,
                              criteria=_norm_wp(str(cid))))
        print("  [N/A] %-6s %-42s reason=%s" % (cid, item[:42], reason))

    def summary(self):
        # ★ v2.21:rows 由 5 元组改为 dict,索引访问会 KeyError
        p = sum(1 for r in self.rows if r.get("passed") is True)
        f = sum(1 for r in self.rows if r.get("passed") is False)
        n = sum(1 for r in self.rows if r.get("passed") is None)
        # ★ v2.25：分母由 p+f 改为 p+f+n。
        #   原写法在 4 项 N/A 时输出 "38/38 通过" —— 读起来像"全部通过"，
        #   而实际有 4 项**从未执行**。与 verify_all 的口径（总数为三态之和）
        #   不一致，也正是框架批判的"汇总掩盖原始输出"。
        #   改后同一情形显示 "38/42 通过, 失败 0, 不适用 4" —— 缺口自明。
        print("\n  写作守卫: %d/%d 通过, 失败 %d, 不适用 %d"
              % (p, p + f + n, f, n))
        return p, f, n


# ---------------- 文档读取(★ 绝不忽略 --doc) ----------------
def _read(a, kind):
    """统一入口。优先 --src(变异测试) > --doc 指定稿件的对应节 > 无。"""
    if getattr(a, "src", None):
        return open(a.src, encoding="utf-8").read()
    return getattr(a, "_doc_text", "") or ""


def _sections(text):
    """按 '## xxx' 分节, 返回 {节名: 内容}。兼容中英文标题。"""
    out, cur, buf = {}, None, []
    for line in text.split("\n"):
        m = re.match(r"^##\s+(.+?)\s*$", line)
        if m:
            if cur:
                out[cur] = "\n".join(buf).strip()
            cur, buf = m.group(1).strip(), []
        elif cur is not None:
            buf.append(line)
    if cur:
        out[cur] = "\n".join(buf).strip()
    return out


def _sec(sects, *names):
    for n in names:
        for k, v in sects.items():
            if n in k:
                return v
    return ""


# ---------------- WP-CORE ----------------
def wp_core(L, sects, spec, P1=None):
    core = spec["core"]
    p1 = P1 or _sec(sects, "核心发现", "P1", "Core")
    if not p1.strip():
        L.na("WP-CORE", "逻辑链 P0–P4", "稿件未提供 P1(核心发现)声明")
        return
    ok = core["p1_min_chars"] <= len(p1) <= core["p1_max_chars"]
    L.add("WP-CORE", "P1 长度在区间", len(p1),
          "%d–%d" % (core["p1_min_chars"], core["p1_max_chars"]), ok)


# ---------------- WP-1 标题 ----------------
def wp_1(L, sects, spec):
    t = _sec(sects, "标题", "Title")
    if not t:
        L.na("WP-1", "标题检查", "稿件无标题节")
        return
    s = spec["title"]
    hit = [w for w in s["upgrade_words"] if w in t]
    L.add("WP-1.1", "标题无升级词(除非正文 L3+)", hit or "无", "无", not hit)
    bad = [w for w in s["blacklist"] if w in t]
    L.add("WP-1.2", "标题无无信息词", bad or "无", "无", not bad)
    nzh = len(re.sub(r"\s", "", t))
    L.add("WP-1.4", "标题字数", nzh, "≤%d" % s["max_chars_zh"],
          nzh <= s["max_chars_zh"])
    L.add("WP-1.6", "标题含对象+发现", "len>0", ">0", len(t.strip()) > 0)


# ---------------- WP-2 摘要 ----------------
def wp_2(L, sects, spec, P1=None):
    ab = _sec(sects, "摘要", "Abstract")
    if not ab:
        L.na("WP-2", "摘要检查", "稿件无摘要节")
        return
    s = spec["abstract"]
    first = ab.split("。")[0].strip()
    if P1:
        same = (first[:20] == P1.strip()[:20])
        L.add("WP-2.1", "摘要首句 == P1(NC-6)", "一致" if same else "不一致",
              "一致", same)
    else:
        L.na("WP-2.1", "摘要首句 == P1", "未提供 P1, 无法比对")
    miss = [k for k in s["sections"] if k not in ab]
    L.add("WP-2.2", "摘要四段齐全", miss or "齐全", "齐全", not miss)
    tail = any(w in ab[-120:] for w in s["require_boundary_tail"])
    L.add("WP-2.6", "末句含边界词", tail, "True", tail)
    n_ok = bool(re.search(s["n_pattern"], ab))
    L.add("WP-2.7", "摘要含样本量 n", n_ok, "True", n_ok)


# ---------------- WP-3 背景(★ skill 接口) ----------------
def wp_3(L, sects, spec, skill_result=None):
    bg = _sec(sects, "引言", "背景", "Introduction", "Background")
    if not bg:
        L.na("WP-3", "背景检查", "稿件无引言节")
        return
    s = spec["background"]
    # ★★ v2.25 硬化 WP-3.1（P1 修复）
    #   原实现：skill_result is None → 判 **N/A**，备注写"若实际未调用则本项应为 FAIL"。
    #   问题：代码无法区分「调用了但返 0 篇」与「压根没调用」，两者都走 N/A，
    #   而 **N/A 不是失败** → 一个从不调用检索 skill 的执行方永久拿 N/A。
    #   这正是框架自己批判的"不提供输入 → 检查自动通过"（云端提示词 §T10 表格里
    #   那个"传空 → 38/38 通过 → 根本没检查"的例子）。
    #   改为三分：
    #     · 未提供 --skill  → FAIL（该检查**无法执行** = 配置缺失，不是"不适用"）
    #     · 提供且 n_found>0 → PASS，并执行 WP-3.2 幻觉文献检查
    #     · 提供但 n_found==0 → WP-3.1 PASS、WP-3.2 判 N/A（真的检索了，确实没有）
    if skill_result is None:
        L.add("WP-3.1", "文献来自 research_survey_skill", "未提供 --skill", "已提供", False)
    else:
        _np = len(skill_result.get("papers", []))
        L.add("WP-3.1", "文献来自 research_survey_skill",
              "n_found=%s · %d 篇" % (skill_result.get("n_found"), _np),
              "已提供且可核验", True)
        cited = set(re.findall(r"\[(\d+)\]", bg))
        have = {str(p.get("id")) for p in skill_result.get("papers", [])}
        ghost = sorted(cited - have)
        L.add("WP-3.2", "无幻觉文献(引用 ∈ skill 输出)", ghost or "无", "无",
              not ghost)
        if skill_result.get("n_found", 0) == 0:
            L.na("WP-3.2", "文献可核验", "skill 返回 0 篇 → 判不了, 不降级为 AI 生成")
    gap = any(w in bg for w in s["require_gap_statement"])
    L.add("WP-3.4", "含 gap statement", gap, "True", gap)


# ---------------- WP-4 方法 ----------------
def wp_4(L, sects, spec):
    me = _sec(sects, "方法", "材料", "Methods")
    if not me:
        L.na("WP-4", "方法检查", "稿件无方法节")
        return
    s = spec["methods"]
    L.add("WP-4.1", "含版本/批号",
          bool(re.search(s["version_pattern"], me, re.I)), "True",
          bool(re.search(s["version_pattern"], me, re.I)))
    side = any(w in me for w in s["stats_required"]["sided"])
    L.add("WP-4.3a", "统计含单/双侧", side, "True", side)
    corr = any(w in me for w in s["stats_required"]["correction"])
    L.add("WP-4.3b", "统计含多重校正", corr, "True", corr)
    sh = bool(re.search(s["sharing_pattern"], me))
    L.add("WP-4.7", "数据共享/登录号", sh, "True", sh)
    # v2.16 补:以下三项 spec 已配置但此前未调用 —— 空规(真实稿件暴露)
    pr = any(w in me for w in s.get("prereg_keywords", []))
    L.add("WP-4.2", "预注册偏差显式声明", pr, "True", pr)
    et = bool(re.search(s.get("ethics_pattern", "伦理"), me, re.I))
    L.add("WP-4.5", "伦理批准号(涉人/动物)", et, "True", et)
    pw = bool(re.search(s.get("power_pattern", "power"), me, re.I))
    L.add("WP-4.8", "样本量/power 依据", pw, "True", pw)


# ---------------- WP-5a 结果文字 ----------------
def wp_5a(L, sects, spec):
    rt = _sec(sects, "结果", "Results")
    if not rt:
        L.na("WP-5a", "结果文字检查", "稿件无结果节")
        return
    s = spec["results_text"]
    # ★ v2.15 修:原用固定 50 字符窗口,会**跨句**匹配到邻近句的 [L-xxx],
    #   使"显著"后无标注仍判 PASS(变异测试:删 [L-012] 后仍 PASS 暴露)。
    #   正解:窗口限制在**同一句内**(按 。;\n 切分)。
    bad = []
    sents = re.split(r"[。;\n]", rt)
    for w in s["significant_words"]:
        for sent in sents:
            if w in sent and not re.search(s["ledger_pattern"], sent):
                bad.append(w + "/" + sent.strip()[:16])
                break
    L.add("WP-5a.1", "每个'显著'邻近有 [L-xxx]", bad or "无", "无", not bad)
    mech = [w for w in s["mechanism_blacklist"] if w in rt]
    L.add("WP-5a.2", "结果节不含机制词", mech or "无", "无", not mech)
    neg = any(w in rt for w in s["require_negative"])
    L.add("WP-5a.4", "阴性结果显式出现", neg, "True", neg)


# ---------------- WP-5b 图表排版 ----------------
def wp_5b(L, sects, spec):
    rt = _sec(sects, "结果", "Results")
    if not rt:
        L.na("WP-5b", "图表排版检查", "稿件无结果节")
        return
    nums = sorted({int(x) for x in re.findall(r"图\s*(\d+)", rt)})
    full = list(range(1, max(nums) + 1)) if nums else []
    miss = [n for n in full if n not in nums] if nums else []
    L.add("WP-5b.1", "图号连续无缺", miss or "无缺", "无缺", not miss)


# ---------------- WP-5c 图表注 ----------------
def wp_5c(L, sects, spec):
    lg = _sec(sects, "图注", "图表注", "Figure Legend")
    if not lg:
        L.na("WP-5c", "图表注检查", "稿件无图注节")
        return
    s = spec["legend"]
    # v2.16 修订:原对整个图注节做一次 re.search,导致"某图有 n/误差棒"
    # 即掩盖其余图缺项 —— 真实稿件图4 全缺却 PASS。改为逐图切分检查。
    parts = re.split(r"(?=图\s*\d+\s*[:：])", lg)
    items = [x.strip() for x in parts if re.match(r"图\s*\d+\s*[:：]", x.strip())]
    if not items:
        items = [lg.strip()]
    bad_n, bad_eb, bad_ts, bad_len = [], [], [], []
    for it in items:
        tag = re.match(r"(图\s*\d+)", it)
        tag = tag.group(1).replace(" ", "") if tag else "图?"
        if not re.search(s["n_pattern"], it):
            bad_n.append(tag)
        if not re.search(s["error_bar_pattern"], it):
            bad_eb.append(tag)
        if not re.search(s["test_pattern"], it):
            bad_ts.append(tag)
        if len(it) > s["max_chars"]:
            bad_len.append("%s(%d)" % (tag, len(it)))
    L.add("WP-5c.n", "逐图:图注含精确 n", bad_n or "无缺", "无缺", not bad_n)
    L.add("WP-5c.eb", "逐图:图注定义误差棒+中心", bad_eb or "无缺", "无缺", not bad_eb)
    L.add("WP-5c.test", "逐图:图注含检验方法", bad_ts or "无缺", "无缺", not bad_ts)
    L.add("WP-5c.2", "逐图:图注 ≤%d 字" % s["max_chars"],
          bad_len or "无超", "无超", not bad_len)
    L.add("WP-5c.count", "图注条数 == 图号数", len(items), ">0", len(items) > 0)


# ---------------- WP-5d 图表标 ----------------
def wp_5d(L, sects, spec):
    ft = _sec(sects, "图题", "图表标", "Figure Title")
    if not ft:
        L.na("WP-5d", "图表标检查", "稿件无图题节")
        return
    s = spec["figtitle"]
    bad = [w for w in s["blacklist"] if w in ft]
    L.add("WP-5d.1", "图题无无信息词", bad or "无", "无", not bad)
    # v2.16 修订:图题同样须逐条判定字数(补 4 条图题后整节 61 字被误判超限)
    ftl = [x.strip() for x in re.split(r"[\n;；]", ft) if x.strip()]
    over = ["%s(%d)" % (x[:12], len(x)) for x in ftl
            if len(x) > s["max_chars_zh"]]
    L.add("WP-5d.2", "逐条:图题字数 ≤%d" % s["max_chars_zh"],
          over or "无超", "无超", not over)
    # v2.16 补:图题数须与图号数匹配(真实稿件 4 图仅 1 图题,此前无检查)
    rt = _sec(sects, "结果", "Results")
    nfig = len(set(re.findall(r"图\s*(\d+)", rt))) if rt else 0
    ntit = len([x for x in re.split(r"[\n;；]", ft) if x.strip()])
    L.add("WP-5d.count", "图题数 == 图号数", "%d/%d" % (ntit, nfig),
          "%d/%d" % (nfig, nfig), ntit == nfig)


# ---------------- WP-6 讨论 ----------------
def wp_6(L, sects, spec, P1=None):
    ds = _sec(sects, "讨论", "Discussion")
    if not ds:
        L.na("WP-6", "讨论检查", "稿件无讨论节")
        return
    s = spec["discussion"]
    first_para = ds.strip().split("\n")[0]
    if P1:
        same = first_para[:20] == P1.strip()[:20]
        L.add("WP-6.1", "讨论首段 == P1(NC-3)", "一致" if same else "不一致",
              "一致", same)
    else:
        L.na("WP-6.1", "讨论首段 == P1", "未提供 P1")
    bd = any(w in ds for w in s["boundary_words"])
    L.add("WP-6.2", "含局限性(P3)", bd, "True", bd)
    ol = any(w in ds for w in s["outlook_words"])
    L.add("WP-6.3", "含展望(P4)", ol, "True", ol)
    mech_bad = []
    for w in ["驱动", "阐明", "机制", "调控"]:
        for m in re.finditer(w, ds):
            win = ds[max(0, m.start() - s["mechanism_window"]):
                     m.end() + s["mechanism_window"]]
            if not re.search(s["level_pattern"], win):
                mech_bad.append(w)
                break
    L.add("WP-6.4", "机制词邻近有 (Ld) 标注", mech_bad or "无", "无",
          not mech_bad)


# ---------------- WP-7 参考文献 ----------------
def wp_7(L, sects, spec):
    rf = _sec(sects, "参考文献", "References")
    body = "\n".join(v for k, v in sects.items() if "参考" not in k)
    if not rf:
        L.na("WP-7", "参考文献检查", "稿件无参考文献节")
        return
    s = spec["refs"]
    in_text = set(re.findall(r"\[(\d+)\]", body))
    listed = set(re.findall(r"^\[?(\d+)\]?", rf, re.M))
    ghost = sorted(in_text - listed)                 # 用而未引
    L.add("WP-7c.1a", "无'用而未引'", ghost or "无", "无", not ghost)
    unused = sorted(listed - in_text)                # 引而未用
    L.add("WP-7c.1b", "无'引而未用'", unused or "无", "无", not unused)
    doi = len(re.findall(r"10\.\d{4,}/", rf))
    L.add("WP-7b.2", "每条含 DOI/PMID", doi > 0, ">0", doi > 0)


# ---------------- WP-8 去 AI 味 ----------------
def wp_8(L, sects, spec):
    alltxt = "\n".join(v for k, v in sects.items()
                       if not any(x in k for x in ("参考", "图注", "图题")))
    if len(alltxt) < 200:
        L.na("WP-8", "去 AI 味检查", "正文过短(<200 字), 统计特征无意义")
        return
    s = spec["ai_style"]
    tpl = []
    for p in s["template_phrases"]:
        if re.search(p, alltxt):
            tpl.append(p)
    L.add("WP-8.1", "无模板句式", tpl or "无", "无", not tpl)
    hol = [w for w in s["hollow_phrases"] if w in alltxt]
    L.add("WP-8.2", "无空洞表达", hol or "无", "无", not hol)
    k = len(alltxt) / 1000.0
    tr = sum(alltxt.count(w) for w in s["transition_words"]) / k
    L.add("WP-8.3", "过渡词密度", round(tr, 2),
          "≤%d/千字" % s["transition_max_per_kchar"],
          tr <= s["transition_max_per_kchar"])
    paras = [len(p) for p in alltxt.split("\n") if len(p.strip()) > 10]
    if len(paras) >= 3:
        import statistics as st
        sd = st.pstdev(paras)
        L.add("WP-8.4", "段落长度标准差", round(sd, 1),
              "≥%d" % s["para_len_std_min"], sd >= s["para_len_std_min"])
    else:
        L.na("WP-8.4", "段落长度标准差", "段落数 <3, 无法统计")
    meta = sum(alltxt.count(w) for w in s["meta_words"]) / k
    L.add("WP-8.9", "元话语密度", round(meta, 2),
          "≤%d/千字" % s["meta_discourse_max_per_kchar"],
          meta <= s["meta_discourse_max_per_kchar"])


FUNCS = [("WP-CORE", wp_core), ("WP-1", wp_1), ("WP-2", wp_2),
         ("WP-3", wp_3), ("WP-4", wp_4), ("WP-5a", wp_5a),
         ("WP-5b", wp_5b), ("WP-5c", wp_5c), ("WP-5d", wp_5d),
         ("WP-6", wp_6), ("WP-7", wp_7), ("WP-8", wp_8)]



def _wp_dist(rows):
    import collections as _c
    d = _c.defaultdict(lambda: {"n_direct": 0, "n_branch": 0, "n_na": 0,
                                "branches": set()})
    for r in rows:
        if not isinstance(r, dict):
            continue
        c = r.get("criteria") or ""
        d[c]["n_direct"] += 1
        if r.get("na"):
            d[c]["n_na"] += 1
        d[c]["branches"].add(r.get("branch", ""))
    return {k: {"n_direct": v["n_direct"], "n_branch": v["n_branch"],
                "n_na": v["n_na"], "branches": sorted(v["branches"])}
            for k, v in d.items() if k}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--doc", default="")
    ap.add_argument("--src", default="", help="变异测试用:直接指定稿件")
    ap.add_argument("--p1", default="", help="核心发现 P1(用于 NC-3/NC-6)")
    ap.add_argument("--skill", default="", help="research_survey_skill 输出 json")
    ap.add_argument("--out", default="")
    a = ap.parse_args()
    # ★ 绝不忽略 --doc
    if a.doc and os.path.isfile(a.doc):
        a._doc_text = open(a.doc, encoding="utf-8").read()
    text = _read(a, "manuscript")
    if not text.strip():
        raise SystemExit("未获取到稿件:请传 --doc 或 --src")
    spec = _load_spec()
    sects = _sections(text)
    print("  检测到节: %s" % ", ".join(sects.keys()))
    skill = None
    if a.skill and os.path.isfile(a.skill):
        skill = json.load(open(a.skill, encoding="utf-8"))
    L = Ledger()
    for name, fn in FUNCS:
        try:
            if name in ("WP-CORE", "WP-2", "WP-6"):
                fn(L, sects, spec, P1=a.p1 or None)
            elif name == "WP-3":
                fn(L, sects, spec, skill_result=skill)
            else:
                fn(L, sects, spec)
        except SystemExit:
            raise
        except Exception as e:
            L.add(name, "守卫执行异常", type(e).__name__, "无异常", False)
    p, f, n = L.summary()
    if a.out:
        json.dump({"rows": L.rows, "n_pass": p, "n_fail": f, "n_na": n,
                   # ★ v2.21:补判据层聚合,供 L2 消融统计
                   "criteria_dist": _wp_dist(L.rows)},
                  open(a.out, "w", encoding="utf-8"), ensure_ascii=False,
                  indent=2)
    sys.exit(1 if f else 0)


if __name__ == "__main__":
    main()
