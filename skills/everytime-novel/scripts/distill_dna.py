#!/usr/bin/env python3
"""本书风格 DNA 蒸馏脚本（网文版 L1 + L2 可统计部分）

用法：
    python3 distill_dna.py <语料目录或文件> [...]
    python3 distill_dna.py <语料目录> --report settings/本书语言DNA-L1.md
    python3 distill_dna.py --test              # 内置自测，不需要输入文件

只做能自动统计的部分：
  L1 句长分布 / 对话占比 / 段落节奏 / 标点习惯 / 语气词 / 人称视角 / 常用搭配
  L2 开头类型分布 / 结尾类型分布
L3 叙事习惯（主角行为逻辑、冲突处理、金手指节奏等）需要子代理深度归纳，脚本不做，
提纲见 dna-rules.md 第四节。

阈值与词表集中在【可调常量区】。要改哪个，告诉笛子改哪个，不要自己动手改脚本。
"""

import re
import sys
import tempfile
from collections import Counter
from pathlib import Path

# ============================== 可调常量区 ==============================

SHORT_SENT = 15     # 短句上限（字）
LONG_SENT = 50      # 长句下限（字）
MODAL = ["啊", "吧", "呢", "嘛", "哦", "嗯", "哎", "嘿", "呀", "啦", "喽", "呗"]
STOP_BI = {
    "的的", "了了", "一一", "不不", "是是", "他他", "她她", "我我", "这这", "那那",
    "的就", "的了", "的他", "的了", "一个", "什么", "怎么", "自己", "他们", "我们",
    "不是", "就是", "还是", "但是", "因为", "所以", "如果", "可以", "这个", "那个",
}
# 注意：不要把「说」放进动作动词——它是对话标志，放进去会把对话开头的章误判成动作开头
ACTION_VERBS = ["走", "跑", "拿", "放", "抓", "推", "拉", "转", "抬", "低", "站", "坐",
                "蹲", "跨", "甩", "捏", "拨", "砍", "系", "摘", "指", "看", "回"]
SKIP_PREFIX = ("#", "|", "```", ">", "- ", "* ", "![", "【")

# ============================== 文本处理 ==============================

HAN = re.compile(r"[\u4e00-\u9fa5]")
QUOTED = re.compile(r'"[^"]*"|"[^"]*"|「[^」]*」|『[^』]*』')
SENT_SPLIT = re.compile(r"[。！？；…]+")


def han_count(t):
    return len(HAN.findall(t))


def sentences(t):
    return [s.strip() for s in SENT_SPLIT.split(t) if len(s.strip()) >= 2]


def paragraphs(text, min_han=5):
    """按空行切段，剔除标题/表格/代码块/引用/列表行。

    min_han 默认 5：网文里「"你来了。"他说。」这类短段很常见，
    阈值定太高会把短对话段整段丢掉（章首判定就会取错段）。
    """
    out = []
    for block in re.split(r"\n\s*\n", text):
        lines = [l.strip() for l in block.split("\n") if l.strip()]
        if not lines or any(l.startswith(SKIP_PREFIX) for l in lines):
            continue
        joined = "".join(lines)
        if han_count(joined) < min_han:
            continue
        out.append(joined)
    return out


def dialogue_chars(t):
    return sum(han_count(m.group(0)) for m in QUOTED.finditer(t))


def bigrams(t):
    h = "".join(HAN.findall(t))
    return [h[i:i + 2] for i in range(len(h) - 1)]


def classify_open(text):
    """章首类型：对话 / 动作 / 其他。

    用 min_han=1 取首段：章首判定不该受段落长度过滤影响，
    否则「"你来了。"」这种短对话开场会被跳过、误判成下一段的动作。
    """
    first = ""
    for p in paragraphs(text, min_han=1):
        first = p
        break
    if not first:
        return "其他"
    if QUOTED.search(first[:20]):
        return "对话"
    if any(v in first[:12] for v in ACTION_VERBS):
        return "动作"
    return "其他"


def classify_end(text):
    paras = paragraphs(text, min_han=1)
    if not paras:
        return "其他"
    last = paras[-1]
    if QUOTED.search(last):
        return "对话"
    if any(v in last for v in ACTION_VERBS):
        return "动作"
    return "其他"


# ============================== 统计 ==============================

def distill(texts):
    total_han = 0
    sent_lens = []
    para_lens, para_sents = [], []
    dlg_chars = 0
    punct = Counter()
    modal = Counter()
    person = Counter()
    bi = Counter()
    opens, ends = Counter(), Counter()

    for t in texts:
        total_han += han_count(t)
        dlg_chars += dialogue_chars(t)

        for s in sentences(t):
            n = han_count(s)
            if n >= 2:
                sent_lens.append(n)
        for p in paragraphs(t):
            para_lens.append(han_count(p))
            para_sents.append(len(sentences(p)))

        for ch in "。……——！？：、，":
            punct[ch] += t.count(ch)
        for m in MODAL:
            c = t.count(m)
            if c:
                modal[m] += c
        person["我"] += t.count("我")
        person["他"] += t.count("他")
        person["她"] += t.count("她")
        for g in bigrams(t):
            bi[g] += 1
        opens[classify_open(t)] += 1
        ends[classify_end(t)] += 1

    n = max(total_han, 1)
    sents = sent_lens or [0]
    short = sum(1 for x in sents if x <= SHORT_SENT) / len(sents) * 100
    long_ = sum(1 for x in sents if x >= LONG_SENT) / len(sents) * 100
    top_bi = [(g, c) for g, c in bi.most_common(200) if g not in STOP_BI][:30]

    return {
        "章数": len(texts),
        "总字数": total_han,
        "平均句长": round(sum(sents) / len(sents), 1),
        "短句占比%": round(short, 1),
        "长句占比%": round(long_, 1),
        "对话占比%": round(dlg_chars / n * 100, 1),
        "平均段字数": round(sum(para_lens) / max(len(para_lens), 1), 1),
        "平均段句数": round(sum(para_sents) / max(len(para_sents), 1), 1),
        "省略号/千字": round(punct["……"] / n * 1000, 2),
        "破折号/千字": round(punct["——"] / n * 1000, 2),
        "感叹号/千字": round(punct["！"] / n * 1000, 2),
        "问号/千字": round(punct["？"] / n * 1000, 2),
        "顿号/千字": round(punct["、"] / n * 1000, 2),
        "语气词": ", ".join(f"{k}{v}" for k, v in modal.most_common(6)) or "无",
        "人称(我/他/她)": f"{person['我']}/{person['他']}/{person['她']}",
        "开头类型": dict(opens),
        "结尾类型": dict(ends),
        "常用搭配Top30": ", ".join(g for g, _ in top_bi[:30]) or "样本不足",
    }


def render(r, out):
    out.append(f"章数 {r['章数']} · 总字数 {r['总字数']}")
    out.append("")
    out.append("【L1 表层语言】")
    for k in ["平均句长", "短句占比%", "长句占比%", "对话占比%", "平均段字数", "平均段句数",
              "省略号/千字", "破折号/千字", "感叹号/千字", "问号/千字", "顿号/千字",
              "语气词", "人称(我/他/她)"]:
        out.append(f"  {k}: {r[k]}")
    out.append(f"  常用搭配Top30: {r['常用搭配Top30']}")
    out.append("")
    out.append("【L2 章节结构（可统计部分）】")
    out.append(f"  开头类型分布: {r['开头类型']}")
    out.append(f"  结尾类型分布: {r['结尾类型']}")
    out.append("")
    out.append("【L3 叙事习惯】需子代理按 dna-rules.md 第四节提纲归纳，脚本不做")


# ============================== 自测 ==============================

DIALOGUE_HEAVY = """# 第001章

"今天去后山。"她说。

陈砚没接话，蹲下来系紧鞋带。

"你带上那个布袋子。"她回头看了他一眼，"去年采的菌子就装这个。"

他嗯了一声，把袋子甩到肩上。

"够了。"她说，"再多拿不动。"

两人往下走。陈砚走在前面，用镰刀砍掉挡路的枝子。

"小心脚下。"他说。

她笑了一声："知道了，啰嗦。"
"""

NARRATION_HEAVY = """# 第002章

山道上的霜还没化，踩下去咯吱一声。日头刚过山脊，照在霜上晃眼，把枯枝的影子拉得很长。

陈砚走在前面，用镰刀砍掉挡路的枝子。刀刃过处，断口露出新鲜的白色，很快又被风吹干。

走到半坡，他停住脚，指着一处石缝。林昭蹲下去，用镰刀柄把枯叶拨开。褐色的菌盖挤成一排，还带着霜。她伸手捏住菌柄，转了半圈，整朵摘下来放进布袋。

布袋渐渐沉了。两人往下走，脚步比上山时慢。
"""


def self_test():
    # 自测样本落系统临时目录：路径稳定（自测之间不冲突），且不写进 skill 包。
    # 写在包内会被发布工具当成正式文件一起上传（打包排除表只认 .git/__pycache__ 那几项）。
    tmp = Path(tempfile.gettempdir()) / "everytime-novel-selftest-dna"
    tmp.mkdir(parents=True, exist_ok=True)
    a, b = tmp / "dlg.md", tmp / "nar.md"
    a.write_text(DIALOGUE_HEAVY, encoding="utf-8")
    b.write_text(NARRATION_HEAVY, encoding="utf-8")

    ra = distill([a.read_text(encoding="utf-8")])
    rb = distill([b.read_text(encoding="utf-8")])
    both = distill([a.read_text(encoding="utf-8"), b.read_text(encoding="utf-8")])

    checks = [
        ("对话密集稿 对话占比 > 25%", ra["对话占比%"] > 25),
        ("叙述密集稿 对话占比 < 5%", rb["对话占比%"] < 5),
        ("对话占比能区分两种语料", ra["对话占比%"] > rb["对话占比%"] + 20),
        ("平均句长在合理区间(5-60)", 5 < ra["平均句长"] < 60 and 5 < rb["平均句长"] < 60),
        ("章数统计正确(2章)", both["章数"] == 2),
        ("总字数累加正确", both["总字数"] == ra["总字数"] + rb["总字数"]),
        ("开头类型可判定", set(ra["开头类型"]) <= {"对话", "动作", "其他"} and len(ra["开头类型"]) >= 1),
        ("对话开场的章判为「对话」", ra["开头类型"].get("对话", 0) == 1),
        ("景物开场的章不判为「对话」", rb["开头类型"].get("对话", 0) == 0),
        ("短句+长句占比不超100", ra["短句占比%"] + ra["长句占比%"] <= 100),
        ("常用搭配非空", ra["常用搭配Top30"] != "样本不足"),
    ]
    print("=== 自测（风格DNA蒸馏）===")
    failed = 0
    for name, ok in checks:
        print(f"{'PASS' if ok else 'FAIL'}  {name}")
        if not ok:
            failed += 1
    print(f"\n通过 {len(checks) - failed}/{len(checks)}")
    print(f"对话密集稿：对话占比 {ra['对话占比%']}% · 平均句长 {ra['平均句长']} · 开头 {ra['开头类型']}")
    print(f"叙述密集稿：对话占比 {rb['对话占比%']}% · 平均句长 {rb['平均句长']} · 开头 {rb['开头类型']}")
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

    files = []
    for t in args:
        p = Path(t)
        if p.is_file() and p.suffix in (".md", ".txt"):
            files.append(p)
        elif p.is_dir():
            files.extend(sorted(p.rglob("*.md")))
    if not files:
        print("没有找到 .md / .txt 语料。传 ≥20 章的目录。")
        return 1

    texts = []
    for f in files:
        try:
            texts.append(f.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, OSError):
            continue
    if not texts:
        print("语料读取失败。")
        return 1

    r = distill(texts)
    out = []
    render(r, out)
    if r["章数"] < 20:
        out.append("")
        out.append(f"⚠️ 语料只有 {r['章数']} 章，少于 20 章，统计不稳。够 20 章再蒸。")
    text = "\n".join(out)
    print(text)

    if report_path:
        p = Path(report_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("# 本书语言 DNA · L1 统计\n\n```\n" + text + "\n```\n", encoding="utf-8")
        print(f"\n报告已写入 {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
