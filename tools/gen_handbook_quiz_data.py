#!/usr/bin/env python3
"""根据《CBTI 完整手册》V4.0 生成 static/quiz-data.json（手册题库 + 区间 + 模式串）。"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "static", "quiz-data.json")

# 手册原文 208 行为 22 字符，取前 21 位与题库一致；锅の传人 257 行 20 字符，末尾补 A 至 21 位
PATTERNS_FIX = {
    # 手册 22 位截断后总分易落出区间；本串 21 位、总分 25，落在 25–29 且与手册串差异最小
    "流程护法": "BBBBBCBBCBBCBBBBBBBBC",
    "锅の传人": "AAAAAAAAAACAAACCACAAA",
}

QUESTIONS = [
    {
        "id": "Q1",
        "title": "周一早上，领导突然丢给你一个急活，你的反应是？",
        "options": [
            {"key": "A", "text": "直接开怼，「这需求不合理，做不了！」"},
            {"key": "B", "text": "默默流泪，打开电脑开始改"},
            {"key": "C", "text": "表面答应，实则摸鱼到DDL"},
        ],
    },
    {
        "id": "Q2",
        "title": "同事总让你帮忙做杂活，你会？",
        "options": [
            {"key": "A", "text": "冷笑，「你手断了？自己干！」"},
            {"key": "B", "text": "不敢拒绝，但心里骂了一万遍"},
            {"key": "C", "text": "避而不答，「我在忙老板的活，要不你问问TA优先级？」"},
        ],
    },
    {
        "id": "Q3",
        "title": "新来的实习生问你一个很基础的问题，但你正在赶deadline，你会？",
        "options": [
            {"key": "A", "text": "放下手头工作，花几分钟先给TA讲清楚"},
            {"key": "B", "text": "给TA指一个教程链接，说「你先看看，不懂再问我」"},
            {"key": "C", "text": "让TA问旁边的同事，说我这边比较忙"},
        ],
    },
    {
        "id": "Q4",
        "title": "同事请你帮忙检查一份紧急的方案，但你自己的活也堆成山了，你会？",
        "options": [
            {"key": "A", "text": "先放下自己的活，帮TA看完再说"},
            {"key": "B", "text": "说明自己手头紧，问TA能不能等半小时"},
            {"key": "C", "text": "抱歉说现在实在没空，TA找别人看看吧"},
        ],
    },
    {
        "id": "Q5",
        "title": "部门要选一个人去参加高强度的外部培训（占用周末），你会？",
        "options": [
            {"key": "A", "text": "主动报名，觉得是多学东西的好机会"},
            {"key": "B", "text": "如果不忙的话可以去，但不会主动争取"},
            {"key": "C", "text": "不报名，周末是我自己的时间"},
        ],
    },
    {
        "id": "Q6",
        "title": "你对面的同事每天中午外放刷短视频声音很大，你会？",
        "options": [
            {"key": "A", "text": "直接跟TA说「戴耳机吧，声音有点影响我午休」"},
            {"key": "B", "text": "自己戴上降噪耳机，或者换个地方午休"},
            {"key": "C", "text": "在群里匿名吐槽，但不当面说"},
        ],
    },
    {
        "id": "Q7",
        "title": "领导让你做一个你完全不认同的决策的执行者，你会？",
        "options": [
            {"key": "A", "text": "直接跟领导表达不认同，阐明理由和风险"},
            {"key": "B", "text": "先执行，但留好过程记录和风险备忘"},
            {"key": "C", "text": "嘴上不说，执行时打折扣按自己想法来"},
        ],
    },
    {
        "id": "Q8",
        "title": "你的一个跨部门对接人总是隔3天才回复消息，你会？",
        "options": [
            {"key": "A", "text": "直接打电话给TA，把事情说清楚尽快推进"},
            {"key": "B", "text": "发消息提醒TA，并在消息里标注紧急程度"},
            {"key": "C", "text": "等TA回复，反正急的不是我"},
        ],
    },
    {
        "id": "Q9",
        "title": "遇到无意义的加班要求，你的态度是？",
        "options": [
            {"key": "A", "text": "接受并争取利益，「加班可以，给钱！不然免谈！」"},
            {"key": "B", "text": "叹气接受，但工作效率降到10%"},
            {"key": "C", "text": "人到心不到，带薪刷手机"},
        ],
    },
    {
        "id": "Q10",
        "title": "老板在群里@你「在吗」，你会？",
        "options": [
            {"key": "A", "text": "已读不回，假装没看见"},
            {"key": "B", "text": "秒回，「在的老板」，然后焦虑等消息"},
            {"key": "C", "text": "半小时后回，「刚在开会，您说？」"},
        ],
    },
    {
        "id": "Q11",
        "title": "你最习惯的工作节奏是？",
        "options": [
            {"key": "A", "text": "多线程并行，同时推进几个任务效率更高"},
            {"key": "B", "text": "按优先级一件一件来，做完一件再做下一件"},
            {"key": "C", "text": "看状态，状态好就猛干，状态差就摸鱼"},
        ],
    },
    {
        "id": "Q12",
        "title": "你有一个很擅长但很耗时的工作技能，愿意教给别人吗？",
        "options": [
            {"key": "A", "text": "非常乐意，教别人的过程也能帮我自己巩固提升"},
            {"key": "B", "text": "会先问TA哪里不懂，判断值得花时间再教"},
            {"key": "C", "text": "不太愿意，教会徒弟饿死师傅"},
        ],
    },
    {
        "id": "Q13",
        "title": "领导发了一个红包在群里，你会？",
        "options": [
            {"key": "A", "text": "秒抢，然后刷一屏表情包感谢老板"},
            {"key": "B", "text": "随缘抢，抢到了就说声谢谢"},
            {"key": "C", "text": "看到了但不想抢，觉得没必要"},
        ],
    },
    {
        "id": "Q14",
        "title": "你的一个提案被采纳了，但你发现执行中有个细节你低估了难度，你会？",
        "options": [
            {"key": "A", "text": "主动在项目群里同步风险，提出调整方案"},
            {"key": "B", "text": "先自己想办法克服，实在不行再汇报"},
            {"key": "C", "text": "等出了问题时再说，反正提案已经通过了"},
        ],
    },
    {
        "id": "Q15",
        "title": "你离职后最有可能被前同事怎样评价？",
        "options": [
            {"key": "A", "text": "「TA在的时候团队氛围都好很多」"},
            {"key": "B", "text": "「TA做事很靠谱，交给TA的事不用担心」"},
            {"key": "C", "text": "「TA好像没什么存在感」"},
        ],
    },
    {
        "id": "Q16",
        "title": "你的一项工作成果被客户高度认可，客户点名要你参与后续项目，你会？",
        "options": [
            {"key": "A", "text": "欣然接受，这是对自己能力的肯定"},
            {"key": "B", "text": "感谢客户认可，同时表示需要跟公司确认资源安排"},
            {"key": "C", "text": "有点压力，怕接下来做得不好反而砸了口碑"},
        ],
    },
    {
        "id": "Q17",
        "title": "以下哪句话最接近你的职场信条？",
        "options": [
            {"key": "A", "text": "「事在人为，只要想做就没有做不成的事」"},
            {"key": "B", "text": "「不求有功，但求无过，稳稳当当最重要」"},
            {"key": "C", "text": "「打工而已，别太当真，开心就好」"},
        ],
    },
    {
        "id": "Q18",
        "title": "领导画大饼说「明年涨薪」，你心想？",
        "options": [
            {"key": "A", "text": "「放屁！去年的饼还没消化呢！」"},
            {"key": "B", "text": "「虽然不信，但不敢拆穿…」"},
            {"key": "C", "text": "「哦，那明年再说吧~」"},
        ],
    },
    {
        "id": "Q19",
        "title": "写周报时，你的内容策略是？",
        "options": [
            {"key": "A", "text": "把「支撑」「赋能」「落地」排列组合，看起来做了很多事"},
            {"key": "B", "text": "只列交付物和数据，干的事一条一条写清楚"},
            {"key": "C", "text": "用AI写初稿然后改改，觉得这个流程本身就很浪费时间"},
        ],
    },
    {
        "id": "Q20",
        "title": "你理想的工作状态是？",
        "options": [
            {"key": "A", "text": "进攻型，谁惹我我怼谁，绝不委屈自己"},
            {"key": "B", "text": "咸鱼型，安安静静摸鱼，别找我麻烦"},
            {"key": "C", "text": "伪装型，平时装乖，关键时刻掀桌"},
        ],
    },
    {
        "id": "Q21",
        "title": "你的工位状态更像以下哪一种？",
        "options": [
            {"key": "A", "text": "各种便签和截止日期贴满屏幕边框，桌面堆着技术书和草稿纸"},
            {"key": "B", "text": "咖啡零食数据线混在一起，乱中有序，只有自己知道每样在哪"},
            {"key": "C", "text": "极简风——一台电脑、一个水杯、一盆植物，同事以为你离职了"},
        ],
    },
]

# 手册顺序（总分从低到高）；键名与前端 IMG_MAP / 展示一致
PATTERNS_RAW = [
    ("消息黑洞", "BBBBBBBBBBBBBBBBBBBBB"),
    ("流程护法", "BBBBBCBBCBBCBBCBBBBBBC"),
    ("天选牛马", "BCCCBBBCBCBCBBBCBBCCB"),
    ("单机战神", "CCCBCBBCCCCBCBCBCCBCB"),
    ("群聊气氛组", "CBCCCBCCCCCCCBCCCCCCB"),
    ("饼饼粉碎机", "CCCCCCCCCCCCCCCCCCCCC"),
    ("Ctrl+Z 终身成就奖得主", "ACCCCCCACCCCACCCCACCC"),
    ("急急国王", "AACCCAAAACACCCCCCACCC"),
    ("扛把子", "AAACCAAACAACCCACAAACC"),
    ("锅の传人", "AAAAAAAAAACAAACCACAA"),
]

SCORE_BANDS = [
    {"name": "消息黑洞", "min": 21, "max": 24, "center": 21},
    {"name": "流程护法", "min": 25, "max": 29, "center": 26},
    {"name": "天选牛马", "min": 30, "max": 33, "center": 30},
    {"name": "单机战神", "min": 34, "max": 37, "center": 34},
    {"name": "群聊气氛组", "min": 38, "max": 41, "center": 38},
    {"name": "饼饼粉碎机", "min": 42, "max": 45, "center": 42},
    {"name": "Ctrl+Z 终身成就奖得主", "min": 46, "max": 49, "center": 46},
    {"name": "急急国王", "min": 50, "max": 53, "center": 50},
    {"name": "扛把子", "min": 54, "max": 57, "center": 54},
    {"name": "锅の传人", "min": 58, "max": 63, "center": 59},
]


def norm_pattern(name: str, pat: str) -> str:
    if name in PATTERNS_FIX:
        return PATTERNS_FIX[name]
    if len(pat) != 21:
        raise ValueError(f"{name} pattern len {len(pat)}")
    return pat


def build_matrix():
    """A/B/C 对应手册 3/1/2 分，映射到结果页三维条形 1-5。"""
    m = {}
    for q in QUESTIONS:
        qid = q["id"]
        m[qid] = {
            "A": [5, 4, 4],
            "B": [2, 2, 3],
            "C": [3, 3, 3],
        }
    return m


PERSONALITY_TEXTS = {
    "消息黑洞": '### 消息黑洞\n**—— "深藏功与名，事了拂衣去"**\n\n你在团队里存在感不高，但这种"不高"是故意的。你专注自己的事，不抢风头、不站队、不刷存在感。你的产出永远准时、永远靠谱、永远不需要人催。\n\n> **安慰：** 不被看见不等于不被需要。偶尔也可以在群里冒个泡，让同事知道进度一直在推进。',
    "流程护法": '### 流程护法\n**—— "程序正义高于一切，流程是我的护身符"**\n\n你是那个"PPT必须用公司模板、文件名必须带版本号、周报必须按格式填"的人。你不会创新，但你让一切井井有条。你害怕冲突，遇到不公平的事会选择先执行、留好记录。\n\n> **安慰：** 规则是铠甲，偶尔也要透透气。',
    "天选牛马": '### 天选牛马\n**—— "任劳任怨，但心里早已看清一切"**\n\n你是团队里的"老黄牛"——活没少干，锅没少背，但从不主动喊冤。你清楚职场的本质是交换，用体力换薪水，用时间换安稳。你偶尔也会反抗，但方式很温和：摸鱼、拖延、阳奉阴违。\n\n> **安慰：** 清醒不是懒，是尊严。',
    "单机战神": '### 单机战神\n**—— "一个人就是一支队伍，但不想带任何人"**\n\n你是技术流的代表，喜欢一个人闷头干大事。你相信"能者多劳"，但你只想"能者多劳自己"，不想带人、不想开会、不想写文档。你对专业能力有绝对自信，但对人际沟通能省则省。\n\n> **安慰：** 独来独往也可以是极致效率。',
    "群聊气氛组": '### 群聊气氛组\n**—— "职场社交牛逼症，人脉是我的核心竞争力"**\n\n你是群里的表情包之王，是团建必到的气氛担当。你可能不是业务能力最强的，但你是让团队氛围变好的人。领导发红包你秒抢、刷表情包感谢、在群里活跃得像客服。\n\n> **安慰：** 气氛组是团队的氧气。',
    "饼饼粉碎机": '### 饼饼粉碎机\n**—— "全选C，人间清醒"**\n\n你是职场里的"清醒者"——全选C是你的标签，但不是你的全部。你看透了职场的一切套路：画饼、KPI、OKR、团队建设……你选择用一种温和但坚定的方式保持自我。\n\n> **安慰：** 大智若愚，也是力量。',
    "Ctrl+Z 终身成就奖得主": '### Ctrl+Z 终身成就奖得主\n**—— "承认错误的速度比犯错的速度还快"**\n\n你是那个"错了就改，改了再错，错了再改"的人。你行动力很强，但偶尔会有点毛躁。你发现方向错了会立刻调整，绝不硬撑。你会在项目群里主动同步风险，在发现低估难度时第一时间提出调整方案。\n\n> **安慰：** 精益求精是手艺人的尊严，也要给发际线留活路。',
    "急急国王": '### 急急国王\n**—— "效率就是生命，拖延就是犯罪"**\n\n你是"10分钟内必须出结果"的人。你发消息对方3小时没回？你会直接打电话。领导画饼？你直接拆穿。你受不了慢节奏与无意义的等待。\n\n> **安慰：** 鲶鱼效应本人，偶尔也让别人喘口气。',
    "扛把子": '### 扛把子\n**—— "我不扛谁来扛？这个团队我罩了"**\n\n你是团队真正的核心——不是Title上的Leader，而是大家心里那个"有事找TA准没错"的人。你会主动承担责任，敢于跟领导说"不"，也会在同事需要时伸出援手。\n\n> **安慰：** 你扛的不只是事，还有情绪；也要有人接你的力。',
    "锅の传人": '### 锅の传人\n**—— "这个锅我来背——我选的，我认"**\n\n你是极少数敢全选A的人。你不怕冲突，不怕得罪人，不怕背锅。你相信："与其委屈求全，不如痛快干一场。"你对不合理的事直说"做不了"，对同事的杂活冷笑拒绝。\n\n> **安慰：** 敢于推动改变的人，也要记得问一句加班费。',
}

# 展示用三维（主动性、社交性、规则性）1-5，与手册人格画像粗对齐
PERSONALITY_DIMS = {
    "消息黑洞": [2, 2, 5],
    "流程护法": [3, 3, 5],
    "天选牛马": [3, 3, 3],
    "单机战神": [4, 2, 4],
    "群聊气氛组": [3, 5, 3],
    "饼饼粉碎机": [2, 4, 4],
    "Ctrl+Z 终身成就奖得主": [4, 3, 5],
    "急急国王": [5, 3, 3],
    "扛把子": [5, 4, 4],
    "锅の传人": [5, 4, 3],
}

# 从 blueprint 复制的五维质心与题目权重（与 docs 整合说明一致）
with open(os.path.join(ROOT, "static", "cbti-v2-blueprint.json"), encoding="utf-8") as f:
    bp = json.load(f)
hv = bp["handbookV4"]
HANDBOOK_FIVE_D = {
    "boundaryMarginPoints": hv["boundaryMarginPoints"],
    "questionDimensionWeights": hv["questionDimensionWeights"],
    "personalityCentroids": bp["personalityCentroids"],
}


def main():
    patterns = {name: list(norm_pattern(name, pat)) for name, pat in PATTERNS_RAW}
    for name, seq in patterns.items():
        assert len(seq) == 21, name

    pack = {
        "version": "handbook-v4",
        "questions": QUESTIONS,
        "matrix": build_matrix(),
        "personalityTexts": PERSONALITY_TEXTS,
        "personalityDims": PERSONALITY_DIMS,
        "patterns": patterns,
        "scoring": {"optionPoints": {"A": 3, "B": 1, "C": 2}},
        "scoreBands": SCORE_BANDS,
        "handbookFiveD": HANDBOOK_FIVE_D,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(pack, f, ensure_ascii=False, separators=(",", ":"))
    print("written", OUT)


if __name__ == "__main__":
    main()
