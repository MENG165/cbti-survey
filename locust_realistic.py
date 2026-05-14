"""CBTI 真实用户行为模拟 — 模拟真人答题场景

行为模拟：
  1. 用户先打开首页（浏览页面）
  2. 加载题库
  3. 逐题阅读（每题 3-15 秒）
  4. 填写信息（5-20 秒）
  5. 最后提交
  6. 查询结果（部分用户会查看历史）

真实用户平均耗时：3-10 分钟
"""

import random
import json
from locust import HttpUser, task, between, events
from locust.runners import MasterRunner

PERSONALITIES = [
    "消息黑洞", "流程护法", "天选牛马", "单机战神", "群聊气氛组",
    "饼饼粉碎机", "Ctrl+Z 终身成就奖得主", "急急国王", "扛把子", "锅の传人"
]

REGIONS = ["华南", "华北", "华东", "华中", "西南", "西北", "东北"]
DEPT_NAMES = ["技术部", "产品部", "设计部", "市场部", "销售部", "人事部", "财务部", "运营部"]

PATTERN_SETS = {
    "消息黑洞": ["B"] * 21,
    "饼饼粉碎机": ["C"] * 21,
    "锅の传人": ["A"] * 21,
    "流程护法": ["B","B","B","B","B","C","B","B","C","B","B","C","B","B","B","B","B","B","B","B","C"],
    "天选牛马": ["B","C","C","C","B","B","B","C","B","C","B","C","B","B","B","C","B","B","C","C","B"],
    "单机战神": ["C","C","C","B","C","B","B","C","C","C","C","B","C","B","C","B","C","C","B","C","B"],
    "急急国王": ["A","A","C","C","C","A","A","A","A","C","A","C","C","C","C","C","C","A","C","C","C"],
    "扛把子":   ["A","A","A","C","C","A","A","A","C","A","A","C","C","C","A","C","A","A","A","C","C"],
    "群聊气氛组": ["C","B","C","C","C","B","C","C","C","C","C","C","C","B","C","C","C","C","C","C","B"],
    "Ctrl+Z 终身成就奖得主": ["A","C","C","C","C","C","C","A","C","C","C","C","A","C","C","C","C","A","C","C","C"],
}


class RealisticCBTIUser(HttpUser):
    """模拟真实用户的测评行为"""

    # 用户启动间隔 — 模拟用户陆续进入
    # wait_time 在 on_start 之后生效
    wait_time = between(3, 15)

    def on_start(self):
        """用户进入测评页面"""

        # 1. 模拟打开首页 (1-3 秒浏览)
        with self.client.get("/", name="[浏览] 首页", catch_response=True) as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f"首页加载失败: {resp.status_code}")

        # 2. 加载题库 (模拟翻看题目)
        with self.client.get("/api/quiz-data", name="[浏览] 加载题库", catch_response=True) as resp:
            if resp.status_code != 200:
                resp.failure(f"题库加载失败: {resp.status_code}")
                self.quiz_loaded = False
                return
            else:
                self.quiz_loaded = True
                resp.success()

        # 3. 预生成本次答题数据（但模拟逐题阅读）
        self.personality = random.choice(PERSONALITIES)
        pattern = list(PATTERN_SETS[self.personality])

        # 加入随机噪音（10-30%）
        noise_level = random.uniform(0.1, 0.3)
        for i in range(21):
            if random.random() < noise_level:
                pattern[i] = random.choice(["A", "B", "C"])

        # 计算分数
        pts = {"A": 3, "B": 1, "C": 2}
        self.total_score = sum(pts.get(ch, 1) for ch in pattern)

        self.guess_name = "消息黑洞"
        bands = [
            (21, 24, "消息黑洞"), (25, 29, "流程护法"), (30, 33, "天选牛马"),
            (34, 37, "单机战神"), (38, 41, "群聊气氛组"), (42, 45, "饼饼粉碎机"),
            (46, 49, "Ctrl+Z 终身成就奖得主"), (50, 53, "急急国王"),
            (54, 57, "扛把子"), (58, 63, "锅の传人"),
        ]
        for lo, hi, nm in bands:
            if lo <= self.total_score <= hi:
                self.guess_name = nm
                break

        # 生成用户身份
        self.emp_id = f"EMP{random.randint(10000, 99999)}"
        self.user_name = f"用户{random.randint(1, 500000)}"
        self.dept = random.choice(DEPT_NAMES)
        self.region = random.choice(REGIONS)

        self.answers = {}
        for i in range(21):
            self.answers[f"Q{i+1}"] = pattern[i]

        # 用户启动后先"思考"一段时间再答题
        # 模拟用户犹豫要不要开始（5-30 秒）

    @task(3)
    def real_submit(self):
        """模拟真实用户完整答题流程"""
        if not self.quiz_loaded:
            return

        # 模拟逐题阅读并选择答案 —— 每题 3-15 秒思考时间
        # 实际不会每步都发请求，但通过 time.sleep 模拟耗时
        import time

        # 模拟填写个人信息（姓名、工号、部门、区域）耗时 5-20 秒
        think_time = random.uniform(5, 20)
        time.sleep(think_time)

        # 逐题模拟"思考" — 21 题，每题 3-15 秒
        # 但为缩短总时间，只模拟部分题目的思考
        total_think = 0
        steps = random.randint(3, 8)  # 中间停顿 3-8 次
        for _ in range(steps):
            t = random.uniform(3, 15)
            total_think += t
            time.sleep(t)

        # 提交答卷
        payload = {
            "name": self.user_name,
            "dept": self.dept,
            "empId": self.emp_id,
            "region": self.region,
            "result": self.guess_name,
            "haming": 0,
            "answers": self.answers,
            "totalScore": self.total_score,
        }

        with self.client.post(
            "/api/submit",
            json=payload,
            name="[提交] 测评结果",
            catch_response=True,
            timeout=60
        ) as resp:
            if resp.status_code == 200:
                data = resp.json()
                if data.get("ok"):
                    resp.success()
                else:
                    resp.failure(f"提交被拒: {data.get('message')}")
            else:
                resp.failure(f"HTTP {resp.status_code}")

    @task(1)
    def query_result(self):
        """模拟用户查看测评结果（30% 比例）"""
        if not self.quiz_loaded:
            return

        # 模拟输入姓名工号查询（2-8 秒）
        import time
        time.sleep(random.uniform(2, 8))

        # 部分用当前用户身份查，部分用随机身份
        name = self.user_name if random.random() < 0.5 else f"用户{random.randint(1, 500000)}"
        emp_id = self.emp_id if random.random() < 0.5 else f"EMP{random.randint(10000, 99999)}"

        with self.client.post(
            "/api/query",
            json={"name": name, "empId": emp_id},
            name="[查询] 测评结果",
            catch_response=True,
            timeout=30
        ) as resp:
            if resp.status_code in (200, 404):
                resp.success()
            else:
                resp.failure(f"HTTP {resp.status_code}")


@events.init_command_line_parser.add_listener
def _(parser):
    parser.add_argument(
        "--real-mode",
        type=bool,
        default=True,
        help="真实用户模式：包含思考延迟（默认开启）"
    )
