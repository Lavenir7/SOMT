import json
import requests

class SystemOne:
    """
    SystemOne API
    """
    Providers = {
        "typesafe": {
            "baseUrl": "https://api.typesafe.ai/v1/systemone",
            "models": [
                "jev-latest",
            ]
        }
    }

    def __init__(self):
        self.baseUrl = None
        self.model = None
        self.api_key = None
        self.state = None
        self.questions = {}
        self.result = None
        self.answers = None
    
    @staticmethod
    def ensure_json_serializable(state) -> None:
        try:
            json.dumps(state, ensure_ascii=False)
        except TypeError as e:
            raise ValueError(f"state 不可 JSON 序列化：{e}") from e

    def use(self, provider, model = None, api_key = None) -> None:
        '''
        provider: SystemOne 提供商；
        model: SystemOne 模型；
        api_key: API 密钥。
        '''
        self.baseUrl = self.Providers[provider]["baseUrl"]
        self.model = model if model else self.Providers[provider]["models"][0]
        self.api_key = api_key

    def run(self) -> dict:
        '''
        运行 SystemOne 模型，返回结果。
        '''
        if self.state:
            self.ensure_json_serializable(self.state)
        else:
            raise ValueError("state 为空")
        if self.questions:
            self.check_questions()
        else:
            raise ValueError("questions 为空")
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": self.model,
            "state": self.state,
            "questions": self.questions,
        }
        response = requests.post(self.baseUrl, headers = headers, data = json.dumps(payload), timeout = 30)
        response.raise_for_status()

        self.result = response.json()
        self.answers = self.result["answers"]
        return self.answers

    @staticmethod
    def check_question(question: dict) -> None:
        qtype = question["type"]
        if qtype == "noul":
            pass
        else:
            criteria = question["criteria"]
            if qtype == "choice" and not isinstance(criteria, dict):
                raise ValueError("Criteria must be a dict")
            if qtype == "score":
                if not isinstance(criteria, list):
                    raise ValueError("Criteria must be a list")
                if len(criteria) < 2:
                    raise ValueError("Criteria must have at least 2 elements")
        
    def check_questions(self) -> None:
        for question in self.questions:
            self.check_question(self.questions[question])

    def addq(self, question: str, instructions: str, qtype: str, criteria: list[str]|dict = None) -> bool:
        '''
        question: 问题标签；
        instructions: 问题描述；
        qtype: 问题类型，可选 noul（是非），choice（选择），score（评分）；
        criteria: 问题选项：
                type=choice 时，criteria 为 dict，key 为选项，value 为选项描述；
                type=score 时，criteria 为 长度大于 1 的 list，元素按从低到高的顺序排列，每个元素描述一个等级。
        '''
        if qtype not in ("noul", "choice", "score"):
            raise ValueError("Invalid question type")
        if qtype == "noul":
            question_v = {
                "type": qtype,
                "instructions": instructions
            }
        else:
            question_v = {
                "type": qtype,
                "instructions": instructions,
                "criteria": criteria
            }
        self.check_question(question_v)
        self.questions[question] = question_v
        return True

    def print_answers(self) -> None:
        '''
        输出结果。
        '''
        tab = "  "
        for ans in self.answers:
            print(f"# {ans} ({self.answers[ans]['type']}):", end = "")
            if self.answers[ans]["type"] == "noul":
                print(f"{tab}Yes: {round(self.answers[ans]['noul']*100)}% | No: {round((1-self.answers[ans]['noul'])*100)}%")
            elif self.answers[ans]["type"] == "choice":
                print(f"{tab}{self.answers[ans]['choice']} ({round(self.answers[ans]['confidence']*100)}%)")
                print()
                for choice in self.answers[ans]["probabilities"]:
                    print(f"{tab}· {choice}: {round(self.answers[ans]['probabilities'][choice]*100)}%")
            elif self.answers[ans]["type"] == "score":
                print(f"{tab}{self.answers[ans]['score']} ({round(self.answers[ans]['confidence']*100)}%)")
                print()
                for legend in self.answers[ans]["legend"]:
                    print(f"{tab}· {legend}-{self.answers[ans]['legend'][legend]}: {round(self.answers[ans]['probabilities'][legend]*100)}%")
            else:
                raise ValueError("Invalid answer type")
            print()