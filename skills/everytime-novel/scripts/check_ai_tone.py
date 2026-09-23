#!/usr/bin/env python3
"""网文去 AI 味检测脚本（融合版）

依据 deai-rules-webnovel.md 的 R1-R14 逐条扫描草稿，输出「规则编号 + 行号 + 原文片段」，
供 deai 子代理按单改写，也供人直接定位。

用法：
    python3 check_ai_tone.py <文件或目录> [<文件或目录> ...]
    python3 check_ai_tone.py --test                 # 内置自测，不需要任何输入文件
    python3 check_ai_tone.py 草稿.md --report r.md  # 附带 markdown 报告

设计原则（来自 lieflat-less-ai-tone 的思想，非代码）：
  1. 每条规则必须能落成可定位的字面形态，不做"读起来像 AI"的语感判断；
  2. 段落层指标的分母是段数，词汇层指标的分母是字数，两者不混用；
  3. 对话、引文、列表、系统面板一律豁免句读类规则（R1/R2 除外）。

阈值与词表集中在本文件头部【可调常量区】。要改哪个阈值，告诉笛子改哪个，不要自己动手改脚本。
"""

import re
import sys
import tempfile
from pathlib import Path

# ============================== 可调常量区 ==============================

BANNED_WORDS = [
    "与此同时", "从而", "于是", "因此", "值得注意的是", "综上所述", "不言而喻",
    "毋庸置疑", "赋能", "闭环", "重塑", "未来可期", "意义重大", "深刻剖析",
    "系统性", "应运而生", "众所周知", "发人深省", "总而言之", "璀璨", "瑰丽",
    "绚烂", "心潮澎湃", "热血沸腾", "令人不安", "令人窒息", "非常震惊",
    "令人震惊", "令人惊叹", "难以置信", "顺滑", "丝滑", "值得一提的是",
    "不可或缺", "由此可见", "打造", "引人注目", "一气呵成", "仿佛", "宛如",
    "骤然", "缓缓", "淡淡", "如同", "瞬间",
]

# 叙事语域里这些连接词同样出戏，与 writer-rules 保持一致
NARRATIVE_CONNECTORS = ["首先", "其次", "再次", "然后", "最后", "而且", "并且", "因而", "此外"]

# R3 句式上限（每章）
PATTERN_LIMITS = {
    "翻案腔(不是A是B)": (re.compile(r"不是[^，。！？]{1,20}[，、](?:而是|是)"), 3),
    "像是": (re.compile(r"像是|好像是"), 3),
    "微微": (re.compile(r"微微"), 2),
    "没有立刻回答": (re.compile(r"没有(?:立刻|马上|立即)回答"), 2),
    "沉默了几秒": (re.compile(r"沉默了(?:几秒|片刻|一会儿)"), 2),
    "点了点头": (re.compile(r"点了点头|点点头"), 3),
    "睁眼闭眼深吸气": (re.compile(r"睁开眼睛|闭上眼睛|睁眼|闭眼|深吸一口气"), 2),
}

# R4 起手式
STARTERS = ["说白了", "说穿了", "先说结论", "众所周知", "值得注意的是", "不难看出", "总而言之"]

# R7 段首评论语 / 回指成分
COMMENT_HEAD = re.compile(
    r"^(?:听起来|看起来|看上去|听上去|说到底|换句话说|意味着|值得注意|不难看出|"
    r"细看|再看|回过头看|问题在于|原因在于|结果是|有意思的是|更重要的是|"
    r"关键在于|真正的|显然|显然的是)"
)
ANAPHOR_HEAD = re.compile(
    r"^(?:这|那|其|此|上面|前面|刚才|以上|该|它|他|她|它们|他们|同样|类似|"
    r"相比|反过来|但|不过|所以|因此|于是|而|另|除此|与此|这时候|那一刻)"
)

# R8 名词化
NOMINALIZATION = re.compile(r"(?:完成了对|实现了|进行了|作出了|做出了|做了对)[^，。！？]{0,12}的")

# R9 拟人化喻体：像/相当于 + 一个/一位 + 职业角色（+ 褒义修饰）
PERSONA_ROLES = "导师|秘书|助手|顾问|管家|审查员|实习生|教练|向导|守卫|管家|伙伴|战友|老师|医生|律师|会计|助理"
PERSONA_METAPHOR = re.compile(
    r"(?:像|就像|好比|相当于|宛如|如同)(?:是)?(?:一个|一位|一名|个)(?:[^，。！？]{0,8})" + f"(?:{PERSONA_ROLES})"
)
PERSONA_PRAISE = re.compile(r"智慧|永不|不疲倦|全能|贴心|忠诚|完美|细致|耐心|不知疲倦|秒级|24小时")

# R12 前置话题壳 / 当…时 / 过长前置定语
TOPIC_SHELL = re.compile(r"^(?:对于[^，。！？]{1,20}(?:来说|而言)|对[^，。！？]{1,20}而言|就[^，。！？]{1,20}而言|关于[^，。！？]{1,20}|在[^，。！？]{1,10}方面)")
WHEN_CLAUSE = re.compile(r"当[^，。！？]{4,40}时[，。！？]")

# R13 章首禁止模式 / 章尾禁止模式
OPEN_BAN = re.compile(r"^(?:天亮了|清晨|凌晨|黄昏|傍晚|深夜|零点|半夜|第二天|翌日|三日后|多年后)")
OPEN_BAN2 = re.compile(r"^(?:[^\s]{0,6}(?:很安静|十分安静|一片寂静|低鸣|昏黄|静悄悄))")
OPEN_BAN3 = re.compile(r"^(?:他站在|她站在|他坐在|她坐在|他躺|她躺|他闭着眼睛|她闭着眼睛|他睁开眼睛|她睁开眼睛|他不知道|她不知道|他想不通|她想不通)")
END_BAN = re.compile(r"(?:闭上了眼睛|闭上眼|两人对视|四目相对|相视一笑|很安静|一片寂静|不需要说出来|不必多说|无需多言|意味深长)$")

# 章内阈值（超过即判定不通过）
THRESHOLDS = {
    "R1": 0, "R2": 0, "R4": 0, "R5": 2, "R8": 1, "R9": 0, "R11": 0, "R12": 2, "R14": 0,
}
# R6 用「连续三句同构」判定：连续两句在网文短段落里太常见（人类侧本身就有 4.81/百段），
# 拿来判不通过会满屏误报；三句同构才指向真正的填表感（AI 0.84 / 人类 0.41）。
ISO3_PER_100P = 1.5     # R6 连续三句同构：每百段上限
ZERO_ANAPHOR_PCT = 0.5  # R7 段首零回指占非首段百分比上限

# ============================== 文本处理 ==============================

QUOTED = re.compile(r'"[^"]*"|"[^"]*"|\'[^\']*\'|「[^」]*」|『[^』]*』')
SENT_SPLIT = re.compile(r"[。！？；]")
HAN = re.compile(r"[\u4e00-\u9fa5]")

SKIP_PREFIX = ("#", "|", "```", ">", "- ", "* ", "![", "【")


def strip_dialogue(text):
    """剥离对话与引文内容，句读类规则只在剩下的叙述文本上跑。"""
    return QUOTED.sub("", text)


def paragraphs(text):
    """按空行切段，剔除标题/表格/代码块/引用/列表/图片行。"""
    out = []
    for block in re.split(r"\n\s*\n", text):
        lines = [l.strip() for l in block.split("\n") if l.strip()]
        if not lines:
            continue
        if any(l.startswith(SKIP_PREFIX) for l in lines):
            continue
        joined = "".join(lines)
        if len(HAN.findall(joined)) < 8:
            continue
        out.append((joined, lines[0]))
    return out


def sentences(text):
    return [s.strip() for s in SENT_SPLIT.split(text) if len(s.strip()) >= 4]


def fingerprint(sent):
    """句子结构指纹：逗号数、有无冒号、有无括号、长度档。用于 R6。"""
    return (sent.count("，"), "：" in sent, ("（" in sent or "(" in sent), len(sent) // 12)


def iter_markdown(targets):
    files = []
    for t in targets:
        p = Path(t)
        if p.is_file() and p.suffix in (".md", ".txt"):
            files.append(p)
        elif p.is_dir():
            files.extend(sorted(p.rglob("*.md")))
    return files


# ============================== 规则实现 ==============================

def check_file(path):
    raw = path.read_text(encoding="utf-8", errors="ignore")
    lines = raw.split("\n")
    hits = {f"R{i}": [] for i in range(1, 15)}
    body = "\n".join(l for l in lines if not l.strip().startswith(SKIP_PREFIX))
    paras = paragraphs(raw)

    # ---- R1 禁用词（含对话，无豁免）----
    for idx, line in enumerate(lines, 1):
        for w in BANNED_WORDS + NARRATIVE_CONNECTORS:
            if w in line:
                hits["R1"].append((idx, w, line.strip()[:60]))

    # ---- R2 破折号（含对话，无豁免）----
    for idx, line in enumerate(lines, 1):
        n = line.count("——")
        if n:
            hits["R2"].append((idx, f"—— ×{n}", line.strip()[:60]))

    # ---- 叙述文本（剥离对话）----
    narrative_lines = [(i, strip_dialogue(l)) for i, l in enumerate(lines, 1)]
    narrative = "\n".join(t for _, t in narrative_lines)

    # ---- R3 句式上限 ----
    for name, (pat, limit) in PATTERN_LIMITS.items():
        n = len(pat.findall(narrative))
        if n > limit:
            for idx, text in narrative_lines:
                if pat.search(text):
                    hits["R3"].append((idx, f"{name}({n}/{limit})", text.strip()[:60]))

    # ---- R4 起手式 ----
    for idx, text in narrative_lines:
        for s in STARTERS:
            if text.strip().startswith(s):
                hits["R4"].append((idx, s, text.strip()[:60]))

    # ---- R5 顿号罗列过密（>=3 顿号即 >=4 项）----
    for idx, text in narrative_lines:
        for sent in sentences(text):
            n = sent.count("、")
            if n >= 3:
                hits["R5"].append((idx, f"顿号×{n}", sent.strip()[:60]))

    # ---- R6 相邻句同构（段落层，分母=段数）----
    iso2 = iso3 = 0
    for joined, _ in paras:
        ptext = strip_dialogue(joined)
        sents = [s for s in sentences(ptext) if len(s) >= 10]
        for i in range(len(sents) - 1):
            a, b = fingerprint(sents[i]), fingerprint(sents[i + 1])
            if a == b and a[0] >= 1:
                iso2 += 1
        for i in range(len(sents) - 2):
            sigs = [fingerprint(s) for s in sents[i:i + 3]]
            if all(s == sigs[0] for s in sigs) and sigs[0][0] >= 1:
                iso3 += 1
                hits["R6"].append(
                    (0, "连续三句同构", sents[i][:30] + " || " + sents[i + 1][:30] + " || " + sents[i + 2][:30])
                )
    n_paras = max(len(paras), 1)
    iso_rate = iso3 / n_paras * 100
    iso2_rate = iso2 / n_paras * 100

    # ---- R7 段首零回指（段落层）----
    nonfirst = 0
    zero = 0
    for i, (joined, _) in enumerate(paras):
        head = strip_dialogue(joined).strip()
        if not head:
            continue
        if i == 0:
            continue
        nonfirst += 1
        if COMMENT_HEAD.match(head) and not ANAPHOR_HEAD.match(head):
            zero += 1
            hits["R7"].append((0, "段首零回指", head[:60]))
    zero_pct = zero / nonfirst * 100 if nonfirst else 0.0

    # ---- R8 名词化 ----
    for idx, text in narrative_lines:
        m = NOMINALIZATION.search(text)
        if m:
            hits["R8"].append((idx, m.group(0), text.strip()[:60]))

    # ---- R9 拟人化喻体 ----
    for idx, text in narrative_lines:
        m = PERSONA_METAPHOR.search(text)
        if m and (PERSONA_PRAISE.search(text) or "不仅" in text):
            hits["R9"].append((idx, m.group(0), text.strip()[:60]))

    # ---- R10 序数词小标题 ----
    seq = 0
    for idx, line in enumerate(lines, 1):
        ls = line.strip()
        if ls.startswith("#") or (ls.startswith("**") and ls.endswith("**")):
            if re.match(r"^#*\s*[一二三四五六七八九十]+[、.]", ls) or re.match(r"^#*\s*第[一二三四五六七八九十]+[、，]", ls):
                seq += 1
                hits["R10"].append((idx, "编号小标题", ls[:60]))
    if seq < 3:
        hits["R10"] = []  # 未构成通篇编号，不算问题

    # ---- R11 空转句引出列表 ----
    for idx in range(len(lines) - 1):
        cur, nxt = lines[idx].strip(), lines[idx + 1].strip()
        if cur.endswith("：") or cur.endswith(":"):
            if re.match(r"^[-*]\s|^\d+\.\s", nxt):
                hits["R11"].append((idx + 1, "空转句引出列表", cur[:60]))

    # ---- R12 翻译腔 ----
    for idx, text in narrative_lines:
        t = text.strip()
        if TOPIC_SHELL.match(t):
            hits["R12"].append((idx, "前置话题壳", t[:60]))
        if WHEN_CLAUSE.search(t):
            hits["R12"].append((idx, "当…时从句", t[:60]))
        de_count = t.count("的")
        first_de = t.find("的")
        if de_count >= 3 and first_de >= 15:
            hits["R12"].append((idx, f"过长前置定语(的×{de_count})", t[:60]))

    # ---- R13 章首 / 章尾 ----
    if paras:
        first_head = strip_dialogue(paras[0][0]).strip()
        if OPEN_BAN.match(first_head) or OPEN_BAN2.match(first_head) or OPEN_BAN3.match(first_head):
            hits["R13"].append((1, "章首格式(时间/氛围/静止)", first_head[:60]))
        last_para = strip_dialogue(paras[-1][0]).strip()
        last_sent = sentences(last_para)[-1] if sentences(last_para) else last_para
        if END_BAN.search(last_sent):
            hits["R13"].append((len(lines), "章尾格式(静止/氛围/留白)", last_sent[:60]))

    # ---- R14 省略号格式 ----
    for idx, line in enumerate(lines, 1):
        if "......" in line or "······" in line or re.search(r"(?<!\.)\.{3}(?!\.)", line):
            hits["R14"].append((idx, "非标准省略号", line.strip()[:60]))

    stats = {
        "字数": len(HAN.findall(raw)),
        "段数": n_paras,
        "三句同构/百段": round(iso_rate, 2),
        "零回指%/非首段": round(zero_pct, 2),
        "两句同构/百段(参考)": round(iso2_rate, 2),
    }
    return hits, stats


# ============================== 报告 ==============================

TITLES = {
    "R1": "禁用词(零容忍)", "R2": "破折号(零容忍)", "R3": "句式次数上限",
    "R4": "起手式", "R5": "顿号罗列过密", "R6": "相邻句同构",
    "R7": "段首零回指", "R8": "名词化结构", "R9": "拟人化喻体",
    "R10": "序数词小标题", "R11": "空转句引出列表", "R12": "翻译腔",
    "R13": "章首/章尾格式", "R14": "省略号格式",
}


def verdict(key, hits, stats):
    if key == "R6":
        return stats["三句同构/百段"] <= ISO3_PER_100P
    if key == "R7":
        return stats["零回指%/非首段"] <= ZERO_ANAPHOR_PCT
    if key == "R10":
        return len(hits) == 0 or len(hits) < 3
    if key in THRESHOLDS:
        return len(hits) <= THRESHOLDS[key]
    return len(hits) == 0


def render(path, hits, stats, out):
    out.append(f"\n=== {path} ===")
    out.append("字数 {字数} · 段数 {段数} · 三句同构 {三句同构/百段}/百段 · 零回指 {零回指%/非首段}%".format(**stats))
    total_bad = 0
    for i in range(1, 15):
        key = f"R{i}"
        items = hits[key]
        ok = verdict(key, items, stats)
        flag = "OK " if ok else "!! "
        if not ok:
            total_bad += 1
        limit = THRESHOLDS.get(key, "-")
        extra = ""
        if key == "R6":
            extra = f"(阈值 {ISO3_PER_100P}/百段)"
        elif key == "R7":
            extra = f"(阈值 {ZERO_ANAPHOR_PCT}%)"
        elif key == "R3":
            extra = "(见各项上限)"
        elif key == "R10":
            extra = "(连续≥3才计)"
        else:
            extra = f"(阈值 {limit})"
        out.append(f"{flag}[{key} {TITLES[key]}] 命中 {len(items)} {extra}")
        for idx, tag, snip in items[:8]:
            loc = f"行{idx}" if idx else "段内"
            out.append(f"      {loc} · {tag} · {snip}")
        if len(items) > 8:
            out.append(f"      …另有 {len(items) - 8} 处")
    out.append(f"--> 未通过项：{total_bad}")


# ============================== 自测 ==============================

DIRTY = """# 第001章：开局

天亮了，林昭站在院子里。

与此同时，他感受到了一股暖流。这股暖流不是别的，而是系统激活的征兆——它像一位智慧的导师，不仅指引方向，更照亮前路。

团队完成了对流程的优化，实现了效率的提升，进行了全面的调整。

这个功能上线后用户反馈很好。团队的开发效率提升明显。下一步的优化方向已经确定。

他把刀收进鞘里，转身往回走。她把水壶挂上肩，跟上他的脚步。风从坡上下来，吹得衣角翻起。

她微微皱眉，微微摇头，微微叹气。他点了点头，她也点了点头，老周点了点头，陈砚点了点头。

对于林昭来说，招人是最难的事。

值得注意，配置数据本来就分层放着。

采集、存储、展示、分析、归档、分发。

我见过的几种典型场景：
- 第一种
- 第二种

说白了，这个项目没有足够的预算。

他买了苹果、香蕉、橘子、梨子、葡萄、桃子。

当所有人都能用 AI 写文章时，内容本身就不再是竞争优势。

这是一个能够让团队在不增加人力的情况下显著提升审核速度的工具。

他闭上了眼睛。
"""

CLEAN = """# 第002章：进山

林昭把镰刀别在腰后，跨过门槛。

"今天去后山。"她说。

陈砚没接话，蹲下来系紧鞋带，指节在麻绳上压出一道白印。山道上的霜还没化，踩下去咯吱一声。

"你带上那个布袋子。"她回头看了他一眼，"去年采的菌子就装这个。"

他嗯了一声，把袋子甩到肩上。日头刚过山脊，照在霜上晃眼。

走到半坡，陈砚停住脚，指着一处石缝："这儿有。"

林昭蹲下去，用镰刀柄把枯叶拨开。褐色的菌盖挤成一排，还带着霜。她伸手捏住菌柄，转了半圈，整朵摘下来放进布袋。

"够了。"她说，"再多拿不动。"

两人往下走。陈砚走在前面，用镰刀砍掉挡路的枝子。
"""


def self_test():
    # 自测样本落系统临时目录：路径稳定（自测之间不冲突），且不写进 skill 包。
    # 写在包内会被发布工具当成正式文件一起上传（打包排除表只认 .git/__pycache__ 那几项）。
    tmp = Path(tempfile.gettempdir()) / "everytime-novel-selftest-ai-tone"
    tmp.mkdir(parents=True, exist_ok=True)
    dirty_p, clean_p = tmp / "dirty.md", tmp / "clean.md"
    dirty_p.write_text(DIRTY, encoding="utf-8")
    clean_p.write_text(CLEAN, encoding="utf-8")

    d_hits, d_stats = check_file(dirty_p)
    c_hits, c_stats = check_file(clean_p)

    checks = [
        ("脏样例 R1 禁用词命中", len(d_hits["R1"]) > 0),
        ("脏样例 R2 破折号命中", len(d_hits["R2"]) > 0),
        ("脏样例 R3 句式上限命中", len(d_hits["R3"]) > 0),
        ("脏样例 R5 顿号过密命中", len(d_hits["R5"]) > 0),
        ("脏样例 R6 三句同构命中", len(d_hits["R6"]) > 0),
        ("脏样例 R7 段首零回指命中", len(d_hits["R7"]) > 0),
        ("脏样例 R8 名词化命中", len(d_hits["R8"]) > 0),
        ("脏样例 R9 拟人化喻体命中", len(d_hits["R9"]) > 0),
        ("脏样例 R12 翻译腔命中", len(d_hits["R12"]) > 0),
        ("脏样例 R13 章首/章尾命中", len(d_hits["R13"]) > 0),
        ("干净样例 R1 为零", len(c_hits["R1"]) == 0),
        ("干净样例 R2 为零", len(c_hits["R2"]) == 0),
        ("干净样例 R8 为零", len(c_hits["R8"]) == 0),
        ("干净样例 R14 为零", len(c_hits["R14"]) == 0),
        ("对话豁免生效(干净样例 R5/R6 不误报)", len(c_hits["R5"]) == 0 and len(c_hits["R6"]) == 0),
        ("字数统计可用", d_stats["字数"] > 100 and c_stats["字数"] > 100),
    ]
    print("=== 自测 ===")
    failed = 0
    for name, ok in checks:
        print(f"{'PASS' if ok else 'FAIL'}  {name}")
        if not ok:
            failed += 1
    print(f"\n通过 {len(checks) - failed}/{len(checks)}")
    print("脏样例统计：" + " · ".join(f"{k} {v}" for k, v in d_stats.items()))
    print("干净样例统计：" + " · ".join(f"{k} {v}" for k, v in c_stats.items()))
    return failed


# ============================== 主流程 ==============================

def main():
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    if args[0] == "--test":
        return 1 if self_test() else 0

    report_path = None
    if "--report" in args:
        i = args.index("--report")
        report_path = args[i + 1]
        args = args[:i] + args[i + 2:]

    files = iter_markdown(args)
    if not files:
        print("没有找到 .md / .txt 文件。传文件路径或目录路径。")
        return 1

    out = []
    for f in files:
        hits, stats = check_file(f)
        render(f.name, hits, stats, out)
    text = "\n".join(out)
    print(text)

    if report_path:
        Path(report_path).write_text("# 去AI味检测报告\n\n```\n" + text + "\n```\n", encoding="utf-8")
        print(f"\n报告已写入 {report_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
