from __future__ import annotations
import json
import re
from getpass import getpass
import requests
import base64
from pathlib import Path
from urllib.parse import urlparse
from PIL import Image, UnidentifiedImageError

YELLOW = "\033[93m"
RED = "\033[91m"
GREEN = "\033[92m"
ENDC = "\033[0m"

class SystemOne:
    '''
    SystemOne API
    '''
    _Providers_template = {
        "_": {
            "baseUrl": "_",
            "models": [
                "_"
            ]
        },
    }
    Providers = {        
        "typesafe": {
            "baseUrl": "https://api.typesafe.ai/v1/systemone",
            "models": [
                "jev-latest",
            ]
        },
        "ollama": {
            "baseUrl": "http://localhost:11434/v1/systemone",
            "models": [
                "tev1:0.8b",
                "tev1",
                "nimble",
                "clef-flash",
                "clef"
            ]
        }
    }

    def __init__(self, provider = None, model = None, apikey = None):
        '''
        初始化 SystemOne 对象
        Params:
            provider: SystemOne 提供商;
            model:    SystemOne 模型;
            apikey:   API Key;
        '''
        self._baseUrl: str = None
        self._model: str = None
        self._apikey: str = None
        self._response = None
        self._download_dir = Path("./.sopy/download")
            
        self.state = None
        self.images: list[dict] = []
        self.questions: dict = {}
        self.answers: dict = None

        if provider:
            self.use(provider, model, apikey)
    
    # -----------------------
    # Inside
    # -----------------------
    @staticmethod
    def _ensure_json_serializable(item) -> bool:
        '''
        校验能否 JSON 序列化
        Params:
            item: 校验对象;
        '''
        try:
            json.dumps(item, ensure_ascii=False)
        except (TypeError, ValueError) as e:
            return False
        return True
    
    @staticmethod
    def _count_words(text: str) -> int:
        '''
        统计文段的词数
        Params:
            text: 文段内容;
        '''
        # 按空白切分出西文词
        tokens = text.split()
        count = 0
        for tok in tokens:
            # 把 CJK 字符单独拆出来计数
            cjk = re.findall(r'[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]', tok)
            if cjk:
                count += len(cjk)
                # 去掉 CJK 后如果还剩西文，也算一个词
                rest = re.sub(r'[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]', '', tok).strip()
                if rest:
                    count += 1
            else:
                count += 1
        return count
    
    @staticmethod
    def _is_valid_format(image_path: Path) -> bool:
        '''
        判断是否为 PNG / JPEG / WebP
        Params:
            image_path: 本地图片路径;
        '''
        try:
            with Image.open(image_path) as im:
                fmt = (im.format or "").upper()
                return fmt in {"PNG", "JPEG", "WEBP"}
        except (UnidentifiedImageError, OSError):
            return False

    @staticmethod
    def _is_valid_image_base64(s: str) -> bool:
        """
        判断字符串是否为合法的图片 Base64 (PNG/JPEG/WebP) 字符串
        Params:
            s: 待检测的字符串;
        """
        if not isinstance(s, str) or not s.strip():
            return False

        # 1. 去掉所有空白字符（空格、换行、制表符等）
        cleaned = "".join(s.split())
        if not cleaned:
            return False

        # 2. API 要求纯 Base64，拒绝 data URL 前缀
        if cleaned.startswith("data:"):
            return False

        # 3. 补齐 Base64 的 padding（长度必须是 4 的倍数）
        padding = len(cleaned) % 4
        if padding:
            cleaned += "=" * (4 - padding)

        # 4. 严格 Base64 解码（validate=True 会拒绝非法字符）
        try:
            decoded = base64.b64decode(cleaned, validate=True)
        except Exception:
            return False

        # 5. 用 Pillow 检查解码后的字节是否为合法图片
        try:
            with Image.open(io.BytesIO(decoded)) as im:
                fmt = (im.format or "").upper()
                if fmt not in {"PNG", "JPEG", "WEBP"}:
                    return False
                # 可选：调用 im.verify() 验证完整性（会消耗对象，需重新打开）
        except (UnidentifiedImageError, OSError, Exception):
            return False

        return True

    @staticmethod
    def _image_to_base64(image_path: Path) -> str:
        '''
        将图片编码成纯 Base64 字符串
        Params:
            image_path: 本地图片路径;
        '''
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode("ascii")

    @staticmethod
    def _get_image_mime(image_path: Path) -> str:
        '''
        根据图片文件后缀返回 MIME 类型
        Params:
            image_path: 本地图片路径;
        '''
        ext = image_path.suffix.lower()
        mime_map = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
        }
        return mime_map.get(ext, "image/png")

    @staticmethod
    def _get_image_size_from_base64(image_base64: str) -> int:
        '''
        计算 Base64 字符串所代表的图片的原始字节大小
        Params:
            image_base64: 图片的 Base64 字符串;
        '''
        if not isinstance(image_base64, str):
            return -1

        # 1. 去除所有空白字符（空格、换行、制表符等）
        cleaned = "".join(image_base64.split())

        # 2. 如果带有 data URL 前缀，先去掉
        if cleaned.startswith("data:"):
            # 找到 base64, 后面的部分
            if "," in cleaned:
                cleaned = cleaned.split(",", 1)[1]

        # 3. 补齐 Base64 的 padding（长度必须是 4 的倍数）
        padding = len(cleaned) % 4
        if padding:
            cleaned += "=" * (4 - padding)

        # 4. 解码并返回字节数
        try:
            decoded = base64.b64decode(cleaned, validate=False)
            return len(decoded)
        except Exception:
            return -1
    
    @staticmethod
    def _format_size(size_bytes: int) -> str:
        '''
        可视化字节大小
        Params:
            size_bytes: 字节大小;
        '''
        if size_bytes < 0:
            return "Invalid"
        for unit in ["B", "KB", "MB", "GB"]:
            if size_bytes < 1024:
                return f"{size_bytes:.2f} {unit}"
            size_bytes /= 1024
        return f"{size_bytes:.2f} TB"

    def _download_image(self, image_url: str) -> Path | None:
        '''
        下载图片
        Params:
            image_url: 网络图片 URL;
        '''
        download_image_dir = self._download_dir / "images"
        try:
            download_image_dir.mkdir(parents=True, exist_ok=True)

            resp = requests.get(image_url, timeout=30)
            resp.raise_for_status()

            # 从 URL 推断文件名，尽量保留扩展名
            parsed = urlparse(image_url)
            name = Path(parsed.path).name or "image"
            if "." not in name:
                # 没有扩展名时，从 Content-Type 推断
                ctype = resp.headers.get("Content-Type", "").lower()
                ext_map = {
                    "image/png": ".png",
                    "image/jpeg": ".jpg",
                    "image/jpg": ".jpg",
                    "image/webp": ".webp",
                }
                for k, v in ext_map.items():
                    if k in ctype:
                        name += v
                        break

            save_path = download_image_dir / name

            # 防止重名覆盖
            counter = 1
            stem, suffix = save_path.stem, save_path.suffix
            while save_path.exists():
                save_path = download_image_dir / f"{stem}_{counter}{suffix}"
                counter += 1

            save_path.write_bytes(resp.content)
            return save_path
        except Exception as e:
            print(f"图片 [{image_url}] 下载失败: {e}")
            return None

    def _check_state(self) -> bool:
        '''
        检查 self.state
        '''        
        if self.state is not None:
            if not self._ensure_json_serializable(self.state):
                print("STATE 不可 JSON 序列化")
                return False
            return True
        else:
            print("state 为空")
            return False

    def _check_images(self) -> bool:
        '''
        检查 self.images
        '''
        if self.images:
            for image in self.images:
                if not self._is_valid_image_base64(image["base64"]):
                    return False
            return True
        return True

    def _check_question(self, question: dict) -> bool:
        '''
        检查问题格式
        Params:
            question: 问题字典对象;
        '''
        if not self._ensure_json_serializable(question):
            print("QUESTIONS 不可 JSON 序列化")
            return False
        qtype = question["type"]
        if qtype != "noul":
            criteria = question["criteria"]
            if qtype == "choice":
                if not isinstance(criteria, dict):
                    print("Criteria must be a dict")
                    return False
                if len(criteria) == 0:
                    print("Criteria must have at least 1 choice")
                    return False
            if qtype == "score":
                if not isinstance(criteria, list):
                    print("Criteria must be a list")
                    return False
                if len(criteria) < 2:
                    print("Criteria must have at least 2 levels")
                    return False
        return True

    def _check_questions(self) -> bool:
        '''
        检查 self.questions
        '''
        if self.questions:
            for question in self.questions:
                if not self._check_question(self.questions[question]):
                    return False
            return True
        else:
            print("questions 为空")
            return False

    # -----------------------
    # Out
    # -----------------------
    # USE
    def use(self, provider, model = None, apikey = None) -> bool:
        '''
        设置模型
        Params:
            provider: SystemOne 提供商;
            model:    SystemOne 模型;
            apikey:   API Key;
        '''
        if provider not in self.Providers:
            print(f"不存在 Provider: {provider}")
            return False
        for key in self._Providers_template["_"].keys():
            if key not in self.Providers[provider]:
                print(f"Provider: {provider} 未设置 {key}")
                return False
        if model is not None and model not in self.Providers[provider]["models"]:
            model_original = model
            model = self.Providers[provider]["models"][0]
            print(f"{provider} 不存在模型: {model_original}，已自动切换到 {model} 模型")
        self._baseUrl = self.Providers[provider]["baseUrl"]
        self._model = model if model else self.Providers[provider]["models"][0]
        self._apikey = apikey
        print(f"已使用 {provider}/{self._model}", end="\n" if self._apikey else "，未设置 API Key\n")
        return True

    def usei(self) -> bool:
        '''
        交互式设置模型
        '''
        while True:
            print("请选择 Provider:\n---")
            for i, provider in enumerate(self.Providers.keys()):
                print(f"{i}. {provider}")
            provider = input(">> ")
            try:
                provider = tuple(self.Providers.keys())[int(provider)]
            except (ValueError, IndexError) as e:
                print("请填写 Provider 序号")
            else:
                break
        while True:
            print("请选择 Model:\n---")
            for i, model in enumerate(self.Providers[provider]["models"]):
                print(f"{i}. {model}")
            model = input(">> ")
            try:
                model = self.Providers[provider]["models"][int(model)]
            except (ValueError, IndexError) as e:
                print("请填写 Model 序号")
            else:
                break
        apikey = getpass("输入 API Key:")
        return self.use(provider, model, apikey)        

    # STATE
    def set_state(self, state) -> bool:
        '''
        设置状态
        Params:
            state: 状态内容;
        '''
        if self._ensure_json_serializable(state):
            self.state = state
            return True
        else:
            print("STATE 不可 JSON 序列化")
            return False

    def add_image(self, image_path: str = None, image_url: str = None) -> bool:
        '''
        添加图片
        Params:
            image_path: 本地图片路径;
            image_url:  网络图片 URL;
        '''
        if image_path is None and image_url is None:
            print("未提供图片")
            return False
        if image_path is not None and image_url is not None:
            print("一次只能提供一张图片")
            return False

        if image_url is not None:
            downloaded = self._download_image(image_url)
            if downloaded is None:
                return False
            image_path = str(downloaded)

        path = Path(image_path)

        if not path.is_file():
            print(f"图片 [{path}] 不存在")
            return False

        # 4. 格式合法性校验（PNG / JPEG / WebP）
        if not self._is_valid_format(path):
            print(f"图片 [{path}] 格式不合法，仅支持 PNG / JPEG / WebP: ")
            return False

        # 5. 转 Base64 并追加
        try:
            b64 = self._image_to_base64(path)
        except Exception as e:
            print(f"图片 [{path}] Base64 编码失败: {e}")
            return False

        self.images.append({
            "name": path.name,
            "path": path,
            "mime": self._get_image_mime(path),
            "base64": b64,
            "size": self._get_image_size_from_base64(b64)
        })
        return True

    def show_images(self) -> None:
        '''
        查看图片
        '''
        image_num = len(self.images)
        for i, image in enumerate(self.images):
            print(f"{i:>{image_num}}. {image['name']} ({image['path']}) [ {self._format_size(image['size'])} ]")

    def pop_image(self, image_index: int) -> bool:
        '''
        删除图片
        Params:
            image_index: 图片索引;
        '''
        if image_index < 0 or image_index >= len(self.images):
            print(f"图片索引 {image_index} 超出范围")
            return False
        self.images.pop(image_index)
        return True

    def clear_images(self) -> bool:
        '''
        清空图片
        '''
        image_num = len(self.images)
        self.images = []
        print(f"已清空图片 ({image_num} 张)")
        return True

    # QUESTIONS
    def addq(self, instructions: str, criteria: list[str]|dict = None, label: str = None, qtype: str|int = None) -> bool:
        '''
        添加问题
        Params:
            instructions: 问题描述;
            criteria:     问题选项:
                type=choice:
                    criteria 为 dict, key (str) 为选项, value (str) 为选项描述, 至少 1 个选项;
                type=score:
                    criteria 为 list, 元素 (str) 为等级描述 (等级从低到高排列), 至少 2 个等级;
            label:        问题标签;
            qtype:        问题类型，可选 noul (是非), choice (选择), score (评分);
        '''
        if label is None:
            for qi in range(len(self.questions)+1):
                if f"Q{qi}" not in self.questions:
                    label = f"Q{qi}"
                    break

        qtypes = ("noul", "choice", "score")
        if qtype is None:
            if criteria is None:
                qtype = "noul"
            elif type(criteria) == dict:
                qtype = "choice"
            elif type(criteria) == list:
                qtype = "score"
            else:
                print("无法识别 Criteria")
                return False
        if qtype not in (*qtypes, *range(len(qtypes))) or isinstance(qtype, bool):
            print("Invalid question type")
            return False
        if type(qtype) == int:
            qtype = qtypes[qtype]
        if qtype == "noul":
            question = {
                "type": qtype,
                "instructions": instructions
            }
        else:
            question = {
                "type": qtype,
                "instructions": instructions,
                "criteria": criteria
            }
        if self._check_question(question):
            self.questions[label] = question
            return True
        else:
            return False

    def addqN(self, instructions: str, label: str = None) -> bool:
        '''
        添加 noul 类问题
        Params:
            instructions: 问题描述;
            label:        问题标签;
        '''
        return self.addq(instructions=instructions, label=label, qtype="noul")
    
    def addqC(self, instructions: str, criteria: dict = None, label: str = None) -> bool:
        '''
        添加 choice 类问题
        Params:
            instructions: 问题描述;
            criteria:     问题选项, key (str) 为选项, value (str) 为选项描述, 至少 1 个选项;
            label:        问题标签;
        '''
        return self.addq(instructions=instructions, criteria=criteria, label=label, qtype="choice")

    def addqS(self, instructions: str, criteria: list[str] = None, label: str = None) -> bool:
        '''
        添加 score 类问题
        Params:
            instructions: 问题描述;
            criteria:     问题选项, 元素 (str) 为等级描述 (等级从低到高排列), 至少 2 个等级;
            label:        问题标签;
        '''
        return self.addq(instructions=instructions, criteria=criteria, label=label, qtype="score")

    def showq(self) -> None:
        '''
        查看问题
        '''
        for question in self.questions:
            print(f"{question} · {self.questions[question]['type']}")
            print(f"INSTRUCTIONS: [+{self._count_words(self.questions[question]['instructions'])} words]")
            if self.questions[question]["type"] == "choice":
                criteria_num = len(self.questions[question]['criteria'])
                if criteria_num == 0:
                    print(f"CRITERIA:     Empty")
                elif criteria_num == 1:
                    print(f"CRITERIA:     [+1 choice]")
                else:
                    print(f"CRITERIA:     [+{criteria_num} choices]")
            if self.questions[question]["type"] == "score":
                criteria_num = len(self.questions[question]['criteria'])
                if criteria_num == 0:
                    print(f"CRITERIA:     Empty")
                elif criteria_num == 1:
                    print(f"CRITERIA:     [+1 level]")
                else:
                    print(f"CRITERIA:     [+{criteria_num} levels]")
            print()

    def popq(self, label: str) -> bool:
        '''
        删除问题
        Params:
            label: 问题标签;
        '''
        if label not in self.questions:
            print(f"问题 {label} 不存在")
            return False
        self.questions.pop(label)
        return True

    def clearq(self) -> bool:
        '''
        清空问题
        '''
        question_num = len(self.questions)
        self.questions = {}
        print(f"已清空问题 ({question_num} 项)")
        return True

    # RUN
    def run(self) -> dict | bool:
        '''
        运行 SystemOne 模型，返回结果
        '''
        if not self._baseUrl or not self._model:
            print("未选择模型")
            return False
        if not self._check_state():
            return False
        if not self._check_questions():
            return False
        if not self._check_images():
            return False
        
        headers = {
            "Content-Type": "application/json"
        }
        if self._apikey:
            headers["Authorization"] = f"Bearer {self._apikey}"
        payload = {
            "model": self._model,
            "state": self.state,
            "questions": self.questions,
        }
        if len(self.images) > 0:
            payload["images"] = [image["base64"] for image in self.images]
            # payload["images"] = [f"data:{image['mime']};base64,{image['base64']}" for image in self.images] # 带 data:image/...;base64, 前缀的 Data URL

        try:
            response = requests.post(self._baseUrl, headers = headers, data = json.dumps(payload), timeout = 30)
            response.raise_for_status()
            self._response = response.json()
        except Exception as e:
            print(f"网络 / HTTP 异常: {e}")
            return False
            
        if "answers" in self._response:
            self.answers = self._response["answers"]
            return self.answers
        else:
            print(f"请求返回格式错误: {self._response}")
            return False

    # STATUS
    def status(self) -> None:
        '''
        查看状态
        '''
        stats = {
            "model": True if self._baseUrl and self._model else False,
            "apikey": True if self._apikey else False,
            "state": True if self._check_state() else False,
            "images": -1 if self._check_images() else len(self.images),
            "questions": -1 if self._check_questions() and len(self.questions) != 0 else len(self.questions),
            "answers": True if self.answers else False
        }
        if stats["model"]:
            if stats["state"]:
                print(f"{GREEN}STATE:     OK{ENDC}")
            else:
                print(f"{RED}STATE:     Empty{ENDC}")
            
            if stats["images"] == -1:
                print(f"{RED}IMAGES:    Invalid{ENDC}")
            elif stats["images"] == 0:
                pass
            elif stats["images"] == 1:
                print(f"{GREEN}IMAGES:    [+{stats['images']} image]{ENDC}")
            else:
                print(f"{GREEN}IMAGES:    [+{stats['images']} images]{ENDC}")

            if stats["questions"] == -1:
                print(f"{RED}QUESTIONS: Invalid{ENDC}")
            elif stats["questions"] == 0:
                print(f"{RED}QUESTIONS: Empty{ENDC}")
            elif stats["questions"] == 1:
                print(f"{GREEN}QUESTIONS: [+{stats['questions']} question]{ENDC}")
            else:
                print(f"{GREEN}QUESTIONS: [+{stats['questions']} questions]{ENDC}")
            
            if stats["answers"]:
                print()
                print("The answer is ready.")

            if not stats["apikey"]:
                print()
                print(f"{YELLOW}[Warning] No API Key{ENDC}")
        else:
            print("Not select model yet.")
    
    # ANSWER
    def show_ans(self) -> bool:
        '''
        打印结果
        '''
        if not self.answers:
            print("The result is not available yet, please run the model first.")
            return False
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
        return True
