"""
cloud_api.py - 云端通信模块
======================
功能：封装百度千帆 V2 接口能力和 API 网关语音识别
    1. OCR 文字识别 (paddleocr)
    2. 大模型对话 (ernie-5.0 等)
    3. 语音合成 TTS (文本→音频WAV)
    4. 语音识别 ASR (音频→文字) — 使用 API 网关 BCE 签名认证
    5. 完整云端对话闭环

架构位置：树莓派端，被 test_ocr.py 调用
"""

import requests
import json
import base64
import os
import hashlib
import hmac
from urllib.parse import urlparse, quote
from datetime import datetime, timezone

# ================= 配置区 =================
# 百度千帆万能钥匙（OCR / LLM / TTS）


API_KEY = os.getenv("BAIDU_API_KEY")
# 语音识别 API 网关凭证（ASR）
ASR_ACCESS_KEY = os.getenv("ASR_ACCESS_KEY")
ASR_APP_SECRET = os.getenv("ASR_APP_SECRET")
ASR_URL = "http://gwgp-3pxc5gqn8nl.n.bdcloudapi.com/voice_to_text/generate"


# ================= 模块一：视觉中枢 (OCR) =================
def extract_text_from_image(image_data, is_filepath=True):
    """
    通用 OCR 接口，支持两种输入方式：
    - is_filepath=True:  image_data 为本地图片路径
    - is_filepath=False: image_data 为图片二进制数据（来自 TCP 接收）
    
    返回识别的文本字符串，失败返回 None
    """
    print("[云端 OCR] 正在发送图像进行文字识别...")
    
    try:
        if is_filepath:
            with open(image_data, "rb") as f:
                base64_data = base64.b64encode(f.read()).decode('utf-8')
        else:
            base64_data = base64.b64encode(image_data).decode('utf-8')
    except Exception as e:
        print(f"[云端 OCR] 图片编码失败: {e}")
        return None

    url = "https://qianfan.baidubce.com/v2/ocr/paddleocr"
    payload = json.dumps({
        "model": "pp-structurev3",
        "file": base64_data,
        "fileType": 1,
        "useLayoutDetection": True,
        "visualize": False
    })
    
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {API_KEY}'
    }

    try:
        response = requests.post(url, headers=headers, data=payload, timeout=30)
        result = response.json()
        
        if "result" in result:
            extracted_text = ""
            parsing_list = result['result']['layoutParsingResults'][0]['prunedResult']['parsing_res_list']
            
            for block in parsing_list:
                label = block.get('block_label', '')
                content = block.get('block_content', '')
                if content and label not in ['image', 'header_image', 'footer_image']:
                    extracted_text += content.replace('## ', '') + "\n"
            
            print(f"[云端 OCR] 提取到 {len(extracted_text.strip())} 字符")
            return extracted_text.strip()
        else:
            print(f"[云端 OCR] 识别失败: {result}")
            return None
    except Exception as e:
        print(f"[云端 OCR] 请求异常: {e}")
        return None


# ================= 模块二：认知大脑 (ERNIE LLM) =================
def ask_smart_assistant_multimodal(prompt_text, image_base64=None, system_prompt=None, model="ernie-5.0"):
    """
    多模态大模型对话接口（支持图片输入）
    参数：
    prompt_text   : 用户输入文本
    image_base64  : 图片的 base64 编码字符串（不含 data:image 前缀）
    system_prompt : 系统人设（可选）
    model         : 模型名
    返回 AI 回答文本，失败返回 None
    """
    print(f"[云端 多模态LLM] 正在调用 {model} 模型...")
    if system_prompt is None:
        system_prompt = """你是一个智能助手。回答必须口语化、温暖且极度简洁。
字数控制在 50 字以内。如果不确定就说"我不确定"，不许瞎编。"""
    
    url = "https://qianfan.baidubce.com/v2/chat/completions"
    
    # 构建多模态 content
    content = []
    # 文本部分
    content.append({
        "type": "text",
        "text": prompt_text
    })
    # 图片部分
    if image_base64:
        content.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:image/jpeg;base64,{image_base64}"
            }
        })
    
    payload = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": content}
        ],
        "temperature": 0.3
    })
    
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {API_KEY}'
    }
    
    try:
        response = requests.post(url, headers=headers, data=payload, timeout=60)
        result = response.json()
        if "choices" in result:
            answer = result['choices'][0]['message']['content']
            print(f"[云端 多模态LLM] 得到回答: {answer[:60]}...")
            return answer
        else:
            print(f"[云端 多模态LLM] 处理失败: {result}")
            return None
    except Exception as e:
        print(f"[云端 多模态LLM] 请求异常: {e}")
        return None
def ask_smart_assistant(prompt_text, system_prompt=None, model="ernie-5.0"):
    """
    大模型对话接口
    参数：
        prompt_text   : 用户输入文本
        system_prompt : 系统人设（可选），默认简洁口语化助手
        model         : 模型名，可选 ernie-5.0 / ernie-4.0 / ernie-lite / ernie-5.0
    返回 AI 回答文本，失败返回 None
    """
    print(f"[云端 LLM] 正在调用 {model} 模型...")
    
    if system_prompt is None:
        system_prompt = """你是一个智能助手。回答必须口语化、温暖且极度简洁。
字数控制在 50 字以内。如果不确定就说"我不确定"，不许瞎编。"""

    url = "https://qianfan.baidubce.com/v2/chat/completions"
    
    payload = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt_text}
        ],
        "temperature": 0.3
    })
    
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {API_KEY}'
    }

    try:
        response = requests.post(url, headers=headers, data=payload, timeout=30)
        result = response.json()
        
        if "choices" in result:
            answer = result['choices'][0]['message']['content']
            print(f"[云端 LLM] 得到回答: {answer[:60]}...")
            return answer
        else:
            print(f"[云端 LLM] 处理失败: {result}")
            return None
    except Exception as e:
        print(f"[云端 LLM] 请求异常: {e}")
        return None


# ================= 模块三：发音嘴巴 (TTS) =================
def text_to_speech_bytes(text):
    """
    文本转语音，直接返回 WAV 音频二进制数据
    适合直接通过 TCP 发送给 RA8D1 播放
    """
    print(f"[云端 TTS] 正在合成语音(字节模式)...")
    
    url = "https://tsn.baidu.com/text2audio"
    
    payload = {
        'tex': text,
        'cuid': 'raspberry_pi_assistant',
        'ctp': '1',
        'lan': 'zh',
        'per': '5003',          # 度小童 - 情感儿童声
        'aue': '6',             # 6=WAV 格式
        'vol': '9',
        'spd': '5',
        'pit': '5',
    }
    
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded',
        'Authorization': f'Bearer {API_KEY}'
    }

    try:
        response = requests.post(url, headers=headers, data=payload, timeout=30)
        
        if response.headers.get('Content-Type') == 'audio/wav':
            print(f"[云端 TTS] 合成成功，大小: {len(response.content)} 字节")
            return response.content
        else:
            print(f"[云端 TTS] 合成失败: {response.text}")
            return None
    except Exception as e:
        print(f"[云端 TTS] 请求异常: {e}")
        return None


def text_to_speech(text, output_path="/tmp/voice_output.wav"):
    """文本转语音，保存到文件后返回路径"""
    audio_bytes = text_to_speech_bytes(text)
    if audio_bytes:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "wb") as f:
            f.write(audio_bytes)
        print(f"[云端 TTS] 保存至 {output_path}")
        return output_path
    return None


# ================= 模块四：语音识别 (ASR) =================
def _bce_sign(method, url, params, headers_to_sign=None):
    """
    BCE 签名算法，生成 Authorization 头
    参考百度 API 网关签名规范
    """
    parsed = urlparse(url)
    host = parsed.hostname
    path = parsed.path

    # 生成时间戳
    now = datetime.now(timezone.utc)
    timestamp = now.strftime('%Y-%m-%dT%H:%M:%SZ')
    expiry = 1800

    # auth_string = bce-auth-v1/{access_key}/{timestamp}/{expiry}
    auth_string = f"bce-auth-v1/{ASR_ACCESS_KEY}/{timestamp}/{expiry}"

    # signing_key = SHA256(app_secret, auth_string)
    signing_key = hmac.new(
        ASR_APP_SECRET.encode('utf-8'),
        auth_string.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()

    # 构建规范请求字符串
    # 1. 规范 URI
    canonical_uri = path

    # 2. 规范查询字符串（按键排序、URL编码）
    sorted_keys = sorted(params.keys()) if params else []
    canonical_query = '&'.join(
        [f"{quote(k, safe='')}={quote(params[k], safe='')}" for k in sorted_keys]
    ) if sorted_keys else ''

    # 3. 规范请求头
    if headers_to_sign is None:
        headers_to_sign = {'host': host}
    else:
        headers_to_sign.setdefault('host', host)

    signed_headers_list = sorted(headers_to_sign.keys())
    canonical_headers = '\n'.join(
        [f"{k.lower()}:{headers_to_sign[k].strip().lower()}" for k in signed_headers_list]
    )
    signed_headers = ';'.join(signed_headers_list)

    # 4. 规范请求字符串
    request_str = f"{method}\n{canonical_uri}\n{canonical_query}\n{canonical_headers}\n{signed_headers}"

    # 签名
    signature = hmac.new(
        signing_key.encode('utf-8'),
        request_str.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()

    # 最终 Authorization
    authorization = f"bce-auth-v1/{ASR_ACCESS_KEY}/{timestamp}/{expiry}/{signed_headers}/{signature}"

    return {
        'Authorization': authorization,
        'X-Bce-Date': timestamp,
        'Host': host
    }


def speech_to_text(audio_bytes, audio_format="pcm"):
    """
    语音识别（音频->文字）
    使用百度短语音识别标准版 API（Bearer 鉴权）
    """
    print(f"[云端 ASR] 正在识别语音，收到 {len(audio_bytes)} 字节")
    try:
        speech_b64 = base64.b64encode(audio_bytes).decode('utf-8')
        audio_len = len(audio_bytes)
        
        url = "https://vop.baidu.com/server_api"
        payload = json.dumps({
            "format": audio_format,
            "rate": 8000,
            "dev_pid": 1537,
            "channel": 1,
            "cuid": "raspberry_pi_assistant",
            "len": audio_len,
            "speech": speech_b64
        })
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {API_KEY}'
        }
        
        response = requests.post(url, headers=headers, data=payload, timeout=30)
        result = response.json()
        
        if result.get("err_no") == 0:
            text = result.get("result", [""])[0]
            print(f"[云端 ASR] 识别结果: {text}")
            return text
        else:
            print(f"[云端 ASR] 识别失败: {result}")
            return None
            
    except Exception as e:
        print(f"[云端 ASR] 请求异常: {e}")
        return None

# ================= 模块五：完整云端对话闭环 =================
def cloud_dialogue(audio_bytes=None, text_input=None, image_bytes=None):
    """
    完整的云端对话函数 - 一次完成 ASR->LLM->TTS 全流程
    
    参数：
        audio_bytes : 音频二进制数据（可选）
        text_input  : 文字输入（可选）
        image_bytes : 图片二进制数据（可选）
    
    返回 (回答文字, 音频WAV二进制数据)
    """
    # 步骤1：输入处理（音频->文字）
    if audio_bytes:
        user_text = speech_to_text(audio_bytes)
        if not user_text:
            return "语音识别失败", None
    elif text_input:
        user_text = text_input
    else:
        return "没有输入内容", None
    
    # 步骤2：如果有图片，先分析图片内容
    if image_bytes:
        ocr_text = extract_text_from_image(image_bytes, is_filepath=False)
        if ocr_text:
            prompt = f"以下是从图片中提取的文字内容：\n{ocr_text}\n\n用户问题：{user_text}"
        else:
            prompt = user_text
    else:
        prompt = user_text
    
    # 步骤3：LLM 对话
    answer = ask_smart_assistant(prompt)
    if not answer:
        return "AI 处理失败", None
    
    # 步骤4：TTS 合成语音
    audio_data = text_to_speech_bytes(answer)
    
    return answer, audio_data


# ================= 场景函数 =================

def ocr_and_llm(image_bytes, question):
    """场景A：图片OCR + LLM 问答（模式1 的核心）
    返回 (ai回答文本, ocr提取的文字)
    """
    ocr_text = extract_text_from_image(image_bytes, is_filepath=False)
    if not ocr_text:
        return "图片中未识别到文字", ""
    prompt = f"以下是从图片中提取的文字内容：\n{ocr_text}\n\n用户问题：{question}"
    answer = ask_smart_assistant(prompt)
    return answer, ocr_text


# ================= 模块六：AI 关键词提取与智能分类 =================

CATEGORIES = ["医药", "运动", "日常", "学习", "科技", "其他"]

def extract_keywords_with_llm(user_text, ocr_text):
    """
    用 AI 大模型从用户文本 + OCR识别文本中提取关键词语
    返回关键词列表（去掉无意义的虚词），用于词云展示
    """
    combined = user_text
    if ocr_text:
        combined += "\n" + ocr_text[:500]  # 控制长度
    
    prompt = f"""请从以下内容中提取最重要的 3~8 个关键词（名词或短语）。

要求：
- 提取真正有意义的实词（名词、专业术语、核心概念）
- 过滤掉"的、了、是、在、有、和、就、不、人、都、一、一个、上、也、很、到、说、要、去、你、会、着、没有、看、好、自己、这"等无意义虚词
- 每个关键词 2~6 个字为佳
- 按重要性从高到低排列，用中文逗号分隔
- 只输出关键词本身，不要序号和多余文字

内容：{combined}

关键词："""

    result = ask_smart_assistant(
        prompt_text=prompt,
        system_prompt="你是一个关键词提取工具。只输出用中文逗号分隔的关键词列表。",
        model="ernie-lite"
    )
    
    if not result:
        # 兜底：用简单分词
        words = [w for w in combined.split() if len(w) > 1]
        return words[:8]
    
    # 解析逗号分隔的关键词
    keywords = [k.strip() for k in result.replace("，", ",").split(",") if k.strip()]
    # 过滤单个字的脏数据
    keywords = [k for k in keywords if len(k) >= 2]
    return keywords[:10]


def classify_with_llm(user_text, ocr_text, keywords):
    """
    调用大语言模型（ernie-5.0）进行文本分类
    结合用户文本、OCR识别文字、AI提取的关键词，综合判断最合适的分类
    
    返回分类名称列表（可能1~2个），如 ["医药"] 或 ["医药", "学习"]
    """
    kw_str = "，".join(keywords) if keywords else "（无）"
    ocr_show = ocr_text[:200] if ocr_text else "（无）"
    
    prompt = f"""你是一个严格的文本分类专家。请根据以下输入的三个维度，判断它最属于什么类别。

【用户提问】{user_text}
【图片OCR文字】{ocr_show}
【提取关键词】{kw_str}

请从以下类别中选择最匹配的1个（最多2个），并只输出类别名称：

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
类别 │ 判断依据（包含以下关键词时倾向该类别）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
医药 │ 药品名（阿莫西林、布洛芬、头孢等）、疾病名（感冒、发烧、咳嗽等）、医疗术语（剂量、禁忌、处方、服用、症状、治疗等）
运动 │ 运动项目（跑步、游泳、篮球等）、健身术语（深蹲、肌肉、训练等）、体育相关
日常 │ 食物（苹果、米饭等）、家居（电视、沙发等）、交通（公交、开车等）、服装、天气、生活用品
学习 │ 教育（老师、学校等）、考试、书籍、编程（Python、Java等）、学术、数学、英语、知识类
科技 │ 电子产品（手机、电脑等）、软件、AI人工智能、互联网、代码开发、硬件
其他 │ 以上类别都不明显匹配时
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

示例：
- 输入"阿莫西林胶囊禁忌" → 医药
- 输入"Python入门教程" → 学习,科技
- 输入"跑步机使用方法" → 运动,日常
- 输入"今天天气真好" → 日常

请只输出1~2个类别名称，用英文逗号分隔，不要任何多余文字。"""

    result = ask_smart_assistant(
        prompt_text=prompt,
        system_prompt="你是一个精准的多分类文本分类器。只输出类别名称，不要多余文字。",
        model="ernie-5.0"
    )
    
    if not result:
        return ["其他"]
    
    # 从结果中匹配已知类别
    matched = []
    for cat in ["医药", "运动", "日常", "学习", "科技"]:
        if cat in result:
            matched.append(cat)
    
    return matched if matched else ["其他"]


def voice_dialogue(audio_bytes):
    """场景B：纯语音对话（模式2 的核心）"""
    return cloud_dialogue(audio_bytes=audio_bytes)


# ================= 自测入口 =================
if __name__ == "__main__":
    print("\n" + "=" * 50)
    print("   云端通信模块自测")
    print("=" * 50)
    
    # 测试 LLM 对话
    answer = ask_smart_assistant("你好，请做个自我介绍", model="ernie-5.0")
    print(f"回答: {answer}")
    
    print("\n模块加载完成")

    #pip install bce-python-sdk  # 如果需要使用官方 SDK 进行更复杂的签名和请求，可以安装这个包
    #