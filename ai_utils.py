"""
AI 工具模块 - 封装所有 AI 相关的功能
包括：OCR、解题、判卷、生成题目、聊天等
V5.1 - 模型优化 + LaTeX 增强版本
"""

import base64
import os
import re
from openai import OpenAI
from typing import Dict, List, Optional, Tuple
import json

# ==================== API 配置 ====================
# 优先从环境变量读取，支持 .env 文件加载
# 如果环境变量不存在，则使用默认值（兜底）

def _load_env_file():
    """从 .env 文件加载环境变量（如果尚未加载）"""
    env_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(env_file):
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = value

# 自动加载 .env 文件
_load_env_file()

# 默认值（仅 BASE_URL 和模型名可公开，API Key 必须从环境变量读取）
_DEFAULT_BASE_URL = "https://api.siliconflow.cn/v1"
_DEFAULT_OCR_MODEL = "Qwen/Qwen3-VL-32B-Instruct"
_DEFAULT_SOLVER_MODEL = "Qwen/Qwen2.5-32B-Instruct"

# API Key 必须通过环境变量或 Streamlit Secrets 配置，不再提供硬编码默认值
API_KEY = os.getenv("SILICONFLOW_API_KEY")
BASE_URL = os.getenv("SILICONFLOW_BASE_URL", _DEFAULT_BASE_URL)
OCR_MODEL = os.getenv("OCR_MODEL", _DEFAULT_OCR_MODEL)
SOLVER_MODEL = os.getenv("SOLVER_MODEL", _DEFAULT_SOLVER_MODEL)


def get_client():
    """获取 OpenAI 客户端"""
    if not API_KEY:
        raise RuntimeError(
            "API Key 未配置！\n"
            "本地开发：在项目根目录创建 .env 文件，写入 SILICONFLOW_API_KEY=你的Key\n"
            "线上部署：在 Streamlit Cloud 的 Secrets 中配置 SILICONFLOW_API_KEY"
        )
    return OpenAI(api_key=API_KEY, base_url=BASE_URL)


# ==================== LaTeX 清洗增强 ====================
def clean_latex(text: str) -> str:
    """
    清理 LaTeX 格式，修复乱码
    增强版：处理 \[ \] 和 \( \)，转换公式内的中文标点，清洗转义符
    
    主要功能：
    1. 将 \[ ... \] 替换为 $$ ... $$（独立公式）
    2. 将 \( ... \) 替换为 $ ... $（行内公式）
    3. 修复 OCR 转义错误（如 \\ 变 \，\ frac 变 \frac）
    4. 处理中文标点符号（公式内转英文半角）
    5. 处理 JSON 双反斜杠问题
    """
    if not text:
        return ""
    
    # 辅助函数：转换公式内的中文标点为英文半角
    def fix_punctuation_in_math(content: str) -> str:
        """转换公式内的中文标点为英文半角"""
        # 标点符号
        content = content.replace('，', ',').replace('。', '.').replace('：', ':')
        content = content.replace('；', ';').replace('？', '?').replace('！', '!')
        # 括号
        content = content.replace('（', '(').replace('）', ')')
        content = content.replace('【', '[').replace('】', ']')
        content = content.replace('《', '<').replace('》', '>')
        # 数学符号
        content = content.replace('＋', '+').replace('－', '-')
        content = content.replace('×', '\\times').replace('÷', '\\div')
        content = content.replace('＝', '=').replace('＜', '<').replace('＞', '>')
        content = content.replace('≤', '\\leq').replace('≥', '\\geq')
        content = content.replace('≠', '\\neq').replace('≈', '\\approx')
        return content
    
    # 0. 转义符清洗：将 JSON 字符串中的双反斜杠替换为单反斜杠（针对 LaTeX 命令）
    # 匹配 \\后跟字母的 LaTeX 命令（如 \\int, \\frac）
    def fix_latex_command(match):
        """修复转义的 LaTeX 命令"""
        return '\\' + match.group(1)
    
    text = re.sub(r'\\\\([a-zA-Z]+)', fix_latex_command, text)
    
    # 匹配 \\后跟特殊字符的 LaTeX 命令（如 \\{, \\}, \\[, \\]）
    text = re.sub(r'\\\\([{}\[\]()])', r'\\\1', text)
    
    # 修复常见的 OCR 转义错误：\ frac -> \frac, \ int -> \int 等
    text = re.sub(r'\\ ([a-zA-Z]+)', r'\\\1', text)
    
    # 1. 修复 LaTeX 分隔符：将 \[ ... \] 替换为 $$ ... $$
    def replace_display_math(match):
        content = match.group(1)
        content = fix_punctuation_in_math(content)
        return f'$${content}$$'
    
    # 使用非贪婪匹配，支持多行（DOTALL）
    text = re.sub(r'\\\[(.*?)\\\]', replace_display_math, text, flags=re.DOTALL)
    
    # 2. 修复 LaTeX 分隔符：将 \( ... \) 替换为 $ ... $
    def replace_inline_math(match):
        content = match.group(1)
        content = fix_punctuation_in_math(content)
        return f'${content}$'
    
    text = re.sub(r'\\\((.*?)\\\)', replace_inline_math, text, flags=re.DOTALL)
    
    # 3. 处理遗留的单个分隔符（如果还有的话）
    text = re.sub(r'\\\[', '$$', text)
    text = re.sub(r'\\\]', '$$', text)
    text = re.sub(r'\\\(', '$', text)
    text = re.sub(r'\\\)', '$', text)
    
    # 4. 修复已存在的 $...$ 格式公式内的中文标点
    def fix_inline_math_content(match):
        math_content = match.group(1)
        math_content = fix_punctuation_in_math(math_content)
        return f'${math_content}$'
    
    text = re.sub(r'\$([^$]+?)\$', fix_inline_math_content, text)
    
    # 5. 修复已存在的 $$...$$ 格式公式内的中文标点
    def fix_display_math_content(match):
        math_content = match.group(1)
        math_content = fix_punctuation_in_math(math_content)
        return f'$${math_content}$$'
    
    text = re.sub(r'\$\$(.*?)\$\$', fix_display_math_content, text, flags=re.DOTALL)
    
    return text


def ocr_extract_text(image_data: bytes) -> str:
    """
    Stage 1: OCR 识别 - 从图片中提取题目文本和 LaTeX 公式
    
    参数:
        image_data: 图片的二进制数据
    
    返回:
        识别到的题目文本（LaTeX 格式）
    """
    image_base64 = base64.b64encode(image_data).decode('utf-8')
    client = get_client()
    
    ocr_prompt = """请尽可能精准地识别图片中的数学题目，将所有公式转换为标准的 LaTeX 格式。
要求：
1. 行内公式用单美元符号 $ 包裹
2. 独立公式用双美元符号 $$ 包裹
3. 直接输出题目内容，不要包含任何解题过程或多余的话"""
    
    response = client.chat.completions.create(
        model=OCR_MODEL,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": ocr_prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}
                    }
                ]
            }
        ],
        max_tokens=1000,
        temperature=0.1,
        timeout=60
    )
    
    return response.choices[0].message.content


def parse_imperfect_json(text: str) -> Dict:
    """
    解析不完美的 JSON 文本，处理因 LaTeX 公式导致 json.loads 失败的情况
    
    参数:
        text: 可能包含 JSON 的文本（可能包含 Markdown 标记、未转义的 LaTeX 等）
    
    返回:
        解析后的字典，包含 analysis, answer, subject, topic, knowledge_points 字段
    """
    if not text:
        return {"analysis": "", "answer": "", "subject": "未分类", "topic": "未标注", "knowledge_points": []}
    
    # 第一步：清洗 - 去除文本首尾的 Markdown 标记
    cleaned = text.strip()
    # 移除开头的 ```json 或 ```
    cleaned = re.sub(r'^```(?:json)?\s*\n?', '', cleaned, flags=re.MULTILINE)
    # 移除结尾的 ```
    cleaned = re.sub(r'\n?```\s*$', '', cleaned, flags=re.MULTILINE)
    cleaned = cleaned.strip()
    
    # 第二步：标准尝试 - 使用 json.loads
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    
    # 第三步：正则修正 - 手动提取字段（处理 LaTeX 未转义的情况）
    result = {
        "analysis": "",
        "answer": "",
        "subject": "未分类",
        "topic": "未标注",
        "knowledge_points": []
    }
    
    # 提取 subject（学科）
    subject_match = re.search(r'"subject"\s*:\s*"([^"]*)"', cleaned, re.IGNORECASE)
    if not subject_match:
        subject_match = re.search(r'"subject"\s*:\s*"((?:[^"\\]|\\.)*)"', cleaned, re.IGNORECASE)
    if subject_match:
        subject = subject_match.group(1)
        subject = subject.replace('\\"', '"').replace('\\n', '\n').replace('\\\\', '\\')
        result["subject"] = subject.strip() if subject.strip() else "未分类"
    
    # 提取 topic（主题）
    topic_match = re.search(r'"topic"\s*:\s*"([^"]*)"', cleaned, re.IGNORECASE)
    if not topic_match:
        topic_match = re.search(r'"topic"\s*:\s*"((?:[^"\\]|\\.)*)"', cleaned, re.IGNORECASE)
    if topic_match:
        topic = topic_match.group(1)
        topic = topic.replace('\\"', '"').replace('\\n', '\n').replace('\\\\', '\\')
        result["topic"] = topic.strip() if topic.strip() else "未标注"
    
    # 提取 analysis（解析）
    analysis_start = re.search(r'"analysis"\s*:\s*"', cleaned, re.IGNORECASE)
    if analysis_start:
        start_pos = analysis_start.end()
        analysis_content = ""
        i = start_pos
        while i < len(cleaned):
            if cleaned[i] == '"':
                if i > start_pos and cleaned[i-1] == '\\':
                    analysis_content += cleaned[i]
                    i += 1
                    continue
                next_chars = cleaned[i+1:].lstrip()
                if next_chars.startswith(',') or next_chars.startswith('}'):
                    break
            analysis_content += cleaned[i]
            i += 1
        
        if analysis_content:
            analysis_content = analysis_content.replace('\\"', '"').replace('\\n', '\n').replace('\\\\', '\\')
            result["analysis"] = analysis_content.strip()
    
    if not result["analysis"]:
        analysis_patterns = [
            r'"analysis"\s*:\s*"((?:[^"\\]|\\.)*)"',
            r'"analysis"\s*:\s*"(.*?)(?:"\s*[,}])',
        ]
        for pattern in analysis_patterns:
            analysis_match = re.search(pattern, cleaned, re.IGNORECASE | re.DOTALL)
            if analysis_match:
                analysis = analysis_match.group(1)
                analysis = analysis.replace('\\"', '"').replace('\\n', '\n').replace('\\\\', '\\')
                result["analysis"] = analysis.strip()
                break
    
    # 提取 answer（答案）
    answer_match = re.search(r'"answer"\s*:\s*"([^"]*)"', cleaned, re.IGNORECASE)
    if not answer_match:
        answer_match = re.search(r'"answer"\s*:\s*"((?:[^"\\]|\\.)*)"', cleaned, re.IGNORECASE)
    if answer_match:
        answer = answer_match.group(1)
        answer = answer.replace('\\"', '"').replace('\\n', '\n').replace('\\\\', '\\')
        result["answer"] = answer.strip()
    
    # 提取 knowledge_points（知识点数组）
    kp_match = re.search(r'"knowledge_points"\s*:\s*\[(.*?)\]', cleaned, re.IGNORECASE | re.DOTALL)
    if kp_match:
        kp_content = kp_match.group(1).strip()
        if kp_content:
            kp_items = re.findall(r'"([^"]*)"', kp_content)
            if kp_items:
                result["knowledge_points"] = [item.strip() for item in kp_items if item.strip()]
            else:
                kp_items = re.findall(r'"((?:[^"\\]|\\.)*)"', kp_content)
                result["knowledge_points"] = [
                    item.replace('\\"', '"').replace('\\n', '\n').replace('\\\\', '\\').strip()
                    for item in kp_items if item.strip()
                ]
    
    if result["subject"] != "未分类" or result["analysis"]:
        return result
    
    # 第四步：兜底 - 如果所有方法都失败，返回包含原始文本的默认字典
    return {
        "analysis": cleaned,
        "answer": "",
        "subject": "未分类",
        "topic": "未标注",
        "knowledge_points": []
    }


def solve_problem_text(ocr_text: str, target_subjects: Optional[List[str]] = None, 
                       user_identity: Optional[str] = None) -> Tuple[str, List[str], Optional[str], Optional[str]]:
    """
    Stage 2: 解题 - 基于识别到的文本进行详细解题，并提取知识点、学科和主题
    
    参数:
        ocr_text: OCR 识别到的题目文本
        target_subjects: 目标学科列表
        user_identity: 用户身份（用于精确分类）
    
    返回:
        (solution, knowledge_points, subject, topic) - 解题过程、知识点列表、学科、主题
    """
    client = get_client()
    
    subject_hint = ""
    if target_subjects:
        identity_note = f"用户身份是{user_identity}。" if user_identity else ""
        subject_list = "、".join(target_subjects)
        subject_hint = f"{identity_note}请必须将题目归类为以下列表中的一项：{subject_list}。\n"
        if "大学" in (user_identity or ""):
            subject_hint += "例如：如果是经济学题目，且用户是大学生，请归类为'专业课(经管)'，**绝不要**归类为'高等数学'或'语文'。如果是法学、管理学相关题目，请选择对应学科，不要归类为专业课(其他)。\n"
    
    subject_list_str = "、".join(target_subjects) if target_subjects else "任意学科"
    
    # 优化后的 System Prompt
    system_prompt = """你是一个高效的数学解题助手。请直接输出解题步骤和 JSON 结果，不要进行寒暄，不要输出"好的"等废话。"""
    
    # 用户 Prompt - 强调 JSON 格式、LaTeX 规范和分行格式（无步骤编号）
    solver_prompt = f"""请分析并解决以下题目：{ocr_text}

要求：
1. 思路清晰，步骤严谨
2. **所有数学公式必须使用 LaTeX 格式，且严格遵循以下规则：**
   - 独立公式（单独成行）必须用 $$ 包裹，例如：$$x = \\frac{{-b \\pm \\sqrt{{b^2-4ac}}}}{{2a}}$$
   - 行内公式（在文本中）必须用 $ 包裹，例如：根据公式 $E = mc^2$ 可得
   - **绝对禁止使用** `\\[` 和 `\\]` 或 `\\(` 和 `\\)`格式
   - **绝对禁止在公式内使用中文标点符号**（如：，、。、：等），必须使用英文半角标点
3. **解题步骤必须分行显示，每个逻辑步骤单独成段，格式要求：**
   - 不要添加"步骤1"、"步骤2"等编号标签
   - 每个解题步骤之间用两个换行符 \\n\\n 分隔
   - 直接陈述解题过程，自然流畅
4. 最后给出明确的答案
5. 判断题目所属的学科
6. 提取题目的主题/标签
7. 列出涉及的知识点
{subject_hint}

**重要：你必须只输出一个纯 JSON 对象，不要包含任何 Markdown 代码块标记（如 ```json 或 ```），不要包含任何其他文字说明。**

JSON 格式必须严格如下：
{{
    "analysis": "第一个解题步骤的内容...\\n\\n第二个解题步骤的内容...\\n\\n第三个解题步骤的内容...\\n\\n**答案：** xxx",
    "answer": "最终答案",
    "subject": "学科名称（必须从以下列表中选择：{subject_list_str}）",
    "topic": "主题标签",
    "knowledge_points": ["知识点1", "知识点2", "知识点3"]
}}

注意：
- analysis 字段必须按逻辑步骤分段，每段之间用 \\n\\n 分隔，不要添加步骤编号
- answer 字段是最终答案
- subject 字段必须是字符串，从给定的学科列表中选择
- topic 字段是主题标签（字符串）
- knowledge_points 字段是字符串数组

现在请直接输出 JSON，不要任何其他内容："""
    
    response = client.chat.completions.create(
        model=SOLVER_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": solver_prompt}
        ],
        max_tokens=3000,
        temperature=0.1,
        timeout=90
    )
    
    raw_content = response.choices[0].message.content.strip()
    
    # 使用增强的 JSON 解析函数
    parsed_data = parse_imperfect_json(raw_content)
    
    if parsed_data and isinstance(parsed_data, dict):
        analysis = parsed_data.get("analysis", "")
        answer = parsed_data.get("answer", "")
        subject = parsed_data.get("subject")
        topic = parsed_data.get("topic")
        knowledge_points = parsed_data.get("knowledge_points", [])
        
        if isinstance(knowledge_points, str):
            knowledge_points = [kp.strip() for kp in knowledge_points.replace('，', ',').split(',') if kp.strip()]
        elif not isinstance(knowledge_points, list):
            knowledge_points = []
        
        solution = analysis
        if answer and answer not in analysis:
            solution += f"\n\n**答案：**\n{answer}"
        
        return solution, knowledge_points, subject, topic
    
    # 回退到文本解析
    solution = raw_content
    knowledge_points = []
    subject = None
    topic = None
    
    lines = solution.split('\n')
    for i, line in enumerate(lines):
        line_clean = line.strip()
        if ("学科" in line_clean or "Subject" in line_clean) and not subject:
            if '：' in line_clean:
                subject_text = line_clean.split('：', 1)[-1]
            elif ':' in line_clean:
                subject_text = line_clean.split(':', 1)[-1]
            else:
                continue
            subject = subject_text.strip().replace('**', '').replace('*', '').strip()
            if subject.endswith('：') or subject.endswith(':'):
                subject = subject[:-1].strip()
        
        elif ("主题" in line_clean or "Topic" in line_clean) and not topic:
            if '：' in line_clean:
                topic_text = line_clean.split('：', 1)[-1]
            elif ':' in line_clean:
                topic_text = line_clean.split(':', 1)[-1]
            else:
                continue
            topic = topic_text.strip().replace('**', '').replace('*', '').strip()
            if topic.endswith('：') or topic.endswith(':'):
                topic = topic[:-1].strip()
        
        elif ("知识点" in line_clean or "Knowledge" in line_clean or "涉及的知识点" in line_clean) and not knowledge_points:
            if '：' in line_clean:
                kp_text = line_clean.split('：', 1)[-1]
            elif ':' in line_clean:
                kp_text = line_clean.split(':', 1)[-1]
            else:
                continue
            kp_text = kp_text.strip().replace('**', '').replace('*', '').strip()
            knowledge_points = [kp.strip() for kp in kp_text.replace('，', ',').split(',') if kp.strip()]
            if not knowledge_points:
                knowledge_points = [kp.strip() for kp in kp_text.split('、') if kp.strip()]
            break
    
    return solution, knowledge_points, subject, topic


def solve_problem_text_stream(ocr_text: str, target_subjects: Optional[List[str]] = None, 
                              user_identity: Optional[str] = None):
    """
    Stage 2: 解题 - 流式版本，逐字返回解题过程
    
    参数:
        ocr_text: OCR 识别到的题目文本
        target_subjects: 目标学科列表
        user_identity: 用户身份（用于精确分类）
    
    返回:
        Generator[str] - 逐块返回解题过程文本
    """
    client = get_client()
    
    subject_hint = ""
    if target_subjects:
        identity_note = f"用户身份是{user_identity}。" if user_identity else ""
        subject_list = "、".join(target_subjects)
        subject_hint = f"{identity_note}请必须将题目归类为以下列表中的一项：{subject_list}。\n"
        if "大学" in (user_identity or ""):
            subject_hint += "例如：如果是经济学题目，且用户是大学生，请归类为'专业课(经管)'，**绝不要**归类为'高等数学'或'语文'。如果是法学、管理学相关题目，请选择对应学科，不要归类为专业课(其他)。\n"
    
    subject_list_str = "、".join(target_subjects) if target_subjects else "任意学科"
    
    # 优化后的 System Prompt
    system_prompt = """你是一个高效的数学解题助手。请直接输出解题步骤和 JSON 结果，不要进行寒暄，不要输出"好的"等废话。"""
    
    # 用户 Prompt - 强调 JSON 格式、LaTeX 规范和分行格式（无步骤编号）
    solver_prompt = f"""请分析并解决以下题目：{ocr_text}

要求：
1. 思路清晰，步骤严谨
2. **所有数学公式必须使用 LaTeX 格式，且严格遵循以下规则：**
   - 独立公式（单独成行）必须用 $$ 包裹，例如：$$x = \\frac{{-b \\pm \\sqrt{{b^2-4ac}}}}{{2a}}$$
   - 行内公式（在文本中）必须用 $ 包裹，例如：根据公式 $E = mc^2$ 可得
   - **绝对禁止使用** `\\[` 和 `\\]` 或 `\\(` 和 `\\)`格式
   - **绝对禁止在公式内使用中文标点符号**（如：，、。、：等），必须使用英文半角标点
3. **解题步骤必须分行显示，每个逻辑步骤单独成段，格式要求：**
   - 不要添加"步骤1"、"步骤2"等编号标签
   - 每个解题步骤之间用两个换行符 \\n\\n 分隔
   - 直接陈述解题过程，自然流畅
4. 最后给出明确的答案
5. 判断题目所属的学科
6. 提取题目的主题/标签
7. 列出涉及的知识点
{subject_hint}

**重要：你必须只输出一个纯 JSON 对象，不要包含任何 Markdown 代码块标记（如 ```json 或 ```），不要包含任何其他文字说明。**

JSON 格式必须严格如下：
{{
    "analysis": "第一个解题步骤的内容...\\n\\n第二个解题步骤的内容...\\n\\n第三个解题步骤的内容...\\n\\n**答案：** xxx",
    "answer": "最终答案",
    "subject": "学科名称（必须从以下列表中选择：{subject_list_str}）",
    "topic": "主题标签",
    "knowledge_points": ["知识点1", "知识点2", "知识点3"]
}}

注意：
- analysis 字段必须按逻辑步骤分段，每段之间用 \\n\\n 分隔，不要添加步骤编号
- answer 字段是最终答案
- subject 字段必须是字符串，从给定的学科列表中选择
- topic 字段是主题标签（字符串）
- knowledge_points 字段是字符串数组

现在请直接输出 JSON，不要任何其他内容："""
    
    try:
        stream = client.chat.completions.create(
            model=SOLVER_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": solver_prompt}
            ],
            max_tokens=3000,
            temperature=0.1,
            timeout=90,
            stream=True  # 启用流式输出
        )
        
        for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
    except Exception as e:
        yield f"\n\n❌ 解析失败：{str(e)}"


def extract_answer_from_solution(solution: str) -> str:
    """
    从解题过程中提取标准答案
    
    参数:
        solution: 解题过程和答案
    
    返回:
        标准答案文本
    """
    client = get_client()
    
    prompt = f"""请从以下解题过程中提取标准答案（最终答案部分）。

解题过程：
{solution}

请只输出最终答案，不要包含解题步骤。如果答案在"答案："、"Answer："等标记后，请提取该部分。

只输出答案，不要有其他文字。"""
    
    try:
        response = client.chat.completions.create(
            model=SOLVER_MODEL,
            messages=[
                {"role": "system", "content": "你是一个高效的答案提取助手。直接输出答案，不要寒暄。"},
                {"role": "user", "content": prompt}
            ],
            max_tokens=200,
            temperature=0.1,
            timeout=30
        )
        return response.choices[0].message.content.strip()
    except:
        lines = solution.split('\n')
        for i, line in enumerate(lines):
            if '答案' in line or 'Answer' in line.lower():
                answer_lines = []
                for j in range(i, min(i + 3, len(lines))):
                    answer_lines.append(lines[j])
                return '\n'.join(answer_lines)
        return solution[:200]


def refine_preview_content(current_payload: Dict, user_instruction: str,
                           target_subjects: Optional[List[str]] = None) -> Tuple[Dict, str]:
    """
    根据用户反馈微调题目信息，返回更新后的内容和 AI 回复
    """
    client = get_client()
    
    subject_hint = ""
    if target_subjects:
        subject_hint = f"学科必须从以下列表中选择：{', '.join(target_subjects)}。"
    
    prompt = f"""请根据用户的修正指令更新题目信息。
现有题目 JSON：
{json.dumps(current_payload, ensure_ascii=False)}

用户修正：
{user_instruction}

{subject_hint}

请输出 JSON（不要额外文本），包含以下字段：
question_text, solution, answer, subject, topic, knowledge_points

knowledge_points 用数组返回。如果某个字段未修改，请保留原值。"""
    
    response = client.chat.completions.create(
        model=SOLVER_MODEL,
        messages=[
            {"role": "system", "content": "你是一个高效的题目编辑助手。直接输出 JSON，不要寒暄。"},
            {"role": "user", "content": prompt}
        ],
        temperature=0.2,
        max_tokens=1200
    )
    
    content = response.choices[0].message.content
    updated_payload = current_payload.copy()
    try:
        parsed = json.loads(content)
        for key in ["question_text", "solution", "answer", "subject", "topic", "knowledge_points"]:
            if key in parsed and parsed[key]:
                updated_payload[key] = parsed[key]
        if isinstance(updated_payload.get("knowledge_points"), str):
            updated_payload["knowledge_points"] = [
                item.strip() for item in updated_payload["knowledge_points"].replace('，', ',').split(',')
                if item.strip()
            ]
    except Exception:
        pass
    
    assistant_reply = "已根据您的反馈更新题目信息。" if content else "调整完成。"
    return updated_payload, assistant_reply


def judge_answer(question_text: str, standard_solution: str, 
                 user_answer: str, user_answer_image: Optional[bytes] = None) -> Dict:
    """
    AI 判卷：对比用户答案和标准答案
    
    参数:
        question_text: 题目文本
        standard_solution: 标准答案和解析
        user_answer: 用户提交的文本答案（可选）
        user_answer_image: 用户提交的手写答案图片（可选）
    
    返回:
        {
            "is_correct": bool,
            "feedback": str,
            "key_point_missed": str,
            "score": float
        }
    """
    client = get_client()
    
    # Step 1: 处理用户输入
    user_content = ""
    if user_answer_image:
        try:
            user_content = ocr_extract_text(user_answer_image)
        except Exception as e:
            return {
                "is_correct": False,
                "feedback": f"无法识别图片内容，请重试。错误：{str(e)}",
                "key_point_missed": "",
                "score": 0.0
            }
    elif user_answer:
        user_content = user_answer
    else:
        return {
            "is_correct": False,
            "feedback": "未提供答案",
            "key_point_missed": "",
            "score": 0.0
        }
    
    # Step 2: 从 solution 中提取标准答案
    standard_answer = extract_answer_from_solution(standard_solution)
    
    # Step 3: 构建严格的判卷提示词
    judge_prompt = f"""你是一名极其严格的考研阅卷老师。

题目：{question_text}

标准答案是：{standard_answer}

学生的回答是：{user_content}

请严格对比两者。要求：
1. 如果学生的回答与标准答案不一致，必须判定为错误（is_correct = false）
2. 如果学生回答错误、胡乱回答、不完整或模糊不清，必须判定为错误
3. 只有当学生的回答与标准答案完全一致或等价时，才能判定为正确
4. 请以纯 JSON 格式返回，不要包含任何 Markdown 标记：

{{
    "is_correct": false,
    "reason": "简短评语，说明为什么对或错"
}}

注意：
- is_correct 必须是布尔值 true 或 false
- 如果不确定，默认判定为 false（保守策略）
- 只输出纯 JSON，不要有任何前缀、后缀或 Markdown 符号"""
    
    try:
        response = client.chat.completions.create(
            model=SOLVER_MODEL,
            messages=[
                {"role": "system", "content": "你是一个严格的阅卷老师。直接输出 JSON 判卷结果，不要寒暄。"},
                {"role": "user", "content": judge_prompt}
            ],
            max_tokens=500,
            temperature=0.1,
            timeout=60
        )
        
        result_text = response.choices[0].message.content.strip()
        
        # 移除可能的 markdown 代码块标记
        if result_text.startswith("```"):
            result_text = result_text.split("```")[1]
            if result_text.startswith("json"):
                result_text = result_text[4:]
        result_text = result_text.strip()
        
        try:
            result = json.loads(result_text)
            is_correct = bool(result.get("is_correct", False))
            reason = result.get("reason", result.get("comment", "无法判断"))
            
            return {
                "is_correct": is_correct,
                "feedback": reason,
                "key_point_missed": "" if is_correct else "答案与标准答案不一致",
                "score": 1.0 if is_correct else 0.0
            }
        except json.JSONDecodeError:
            return {
                "is_correct": False,
                "feedback": f"判卷结果解析失败。AI 返回：{result_text[:100]}",
                "key_point_missed": "",
                "score": 0.0
            }
    except Exception as e:
        return {
            "is_correct": False,
            "feedback": f"判卷失败：{str(e)}",
            "key_point_missed": "",
            "score": 0.0
        }


def judge_answer_stream(question_text: str, standard_solution: str,
                        user_answer: str, user_answer_image: Optional[bytes] = None):
    """
    流式判卷：逐字返回评语（优化版 - 更快响应）
    """
    client = get_client()
    
    # Step 1: 处理用户输入
    user_content = ""
    if user_answer_image:
        try:
            user_content = ocr_extract_text(user_answer_image)
        except Exception as e:
            yield json.dumps({"is_correct": False, "reason": f"OCR失败：{str(e)}"})
            return
    elif user_answer:
        user_content = user_answer.strip()
    else:
        yield json.dumps({"is_correct": False, "reason": "未提供答案"})
        return
    
    # Step 2: 快速提取标准答案（优化：只提取关键答案部分）
    standard_answer = ""
    # 尝试从解析中快速提取答案
    if "答案" in standard_solution:
        answer_start = standard_solution.rfind("答案")
        if answer_start != -1:
            standard_answer = standard_solution[answer_start:answer_start+200]
    if not standard_answer:
        standard_answer = standard_solution[-300:] if len(standard_solution) > 300 else standard_solution
    
    # Step 3: 极简提示词（减少token消耗，加快响应）
    judge_prompt = f"""标准答案：{standard_answer}
学生回答：{user_content}

判断学生回答是否正确。输出JSON：{{"is_correct": true/false, "reason": "一句话评语"}}"""
    
    try:
        stream = client.chat.completions.create(
            model=SOLVER_MODEL,
            messages=[
                {"role": "system", "content": "你是判卷助手。只输出JSON，不解释。"},
                {"role": "user", "content": judge_prompt}
            ],
            max_tokens=150,  # 减少最大token数
            temperature=0.0,  # 降低温度提高确定性
            timeout=30,  # 缩短超时时间
            stream=True
        )
        
        for chunk in stream:
            if chunk.choices[0].delta.content:
                content = chunk.choices[0].delta.content
                yield content
    except Exception as e:
        yield json.dumps({"is_correct": False, "reason": f"判卷失败：{str(e)}"})


def qa_assistant_stream(question_text: str, solution: str, user_message: str):
    """
    AI 答疑助手（流式版本）- 用于智能录题页面的问答
    """
    client = get_client()
    
    system_prompt = f"""你是AI答疑助手。当前题目：{question_text}
解析：{solution}
请回答用户疑问，或根据纠错指令输出修正内容。所有数学公式使用 $ 和 $$ 格式。"""
    
    stream = client.chat.completions.create(
        model=SOLVER_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ],
        max_tokens=1000,
        temperature=0.3,
        timeout=60,
        stream=True
    )
    
    for chunk in stream:
        if chunk.choices[0].delta.content:
            yield chunk.choices[0].delta.content


def generate_similar_question(question_text: str, knowledge_points: List[str], 
                             difficulty: str = "中等") -> Dict:
    """
    生成相似题目（举一反三）
    """
    client = get_client()
    
    kp_str = "、".join(knowledge_points)
    
    prompt = f"""请根据以下题目，生成一道新的同类练习题。

**原题目：**
{question_text}

**涉及的知识点：**
{kp_str}

**要求：**
1. 新题目必须与原题目不同，但考察相同的知识点
2. 难度：{difficulty}
3. 题目要完整、清晰
4. **所有数学公式必须使用 LaTeX 格式：**
   - 独立公式用 $$ 包裹，如：$$x = \\frac{{1}}{{2}}$$
   - 行内公式用 $ 包裹，如：$x^2 + y^2 = 1$
   - **绝对禁止使用** \\[ \\] 或 \\( \\) 格式
   - **绝对禁止使用** 中文标点符号在公式内
5. 解题步骤要分行显示，每个步骤单独一段，不要添加"步骤1"等编号

请按照以下纯 JSON 格式输出（不要包含任何 Markdown 标记）：
{{
    "question": "新题目的完整内容（使用 $ 和 $$ 格式的公式）",
    "solution": "详细的解题步骤（分段显示，使用 $ 和 $$ 格式的公式）",
    "answer": "最终答案"
}}"""
    
    response = client.chat.completions.create(
        model=SOLVER_MODEL,
        messages=[
            {"role": "system", "content": "你是题目生成助手。直接输出 JSON，不要寒暄。所有数学公式必须用 $ 或 $$ 包裹，禁止使用 \\[ \\] 或 \\( \\) 格式。"},
            {"role": "user", "content": prompt}
        ],
        max_tokens=2000,
        temperature=0.7,
        timeout=60
    )
    
    result_text = response.choices[0].message.content.strip()
    
    if result_text.startswith("```"):
        result_text = result_text.split("```")[1]
        if result_text.startswith("json"):
            result_text = result_text[4:]
    result_text = result_text.strip()
    
    try:
        result = json.loads(result_text)
        # 对所有字段应用 clean_latex 处理
        return {
            "question": clean_latex(result.get("question", "")),
            "solution": clean_latex(result.get("solution", "")),
            "answer": clean_latex(result.get("answer", ""))
        }
    except:
        return {
            "question": clean_latex(result_text),
            "solution": "",
            "answer": ""
        }


def chat_with_ai(question_text: str, solution: str, knowledge_points: List[str],
                 review_history: List[Dict], user_message: str) -> str:
    """
    错题专属 AI 助教聊天（非流式版本）
    """
    client = get_client()
    
    kp_str = "、".join(knowledge_points)
    history_str = ""
    if review_history:
        history_str = "\n**历史作答情况：**\n"
        for log in review_history[-3:]:
            history_str += f"- {log.get('review_time', '')}: {log.get('review_result', '')} - {log.get('ai_feedback', '')}\n"
    
    system_prompt = f"""你是一位专业的数学私教，正在帮助学生理解一道错题。

**当前题目：**
{question_text}

**标准解析：**
{solution}

**涉及的知识点：**
{kp_str}
{history_str}

请根据以上信息，针对性地回答学生的问题。回答要：
1. 结合当前题目的具体内容
2. 解释清晰，步骤详细
3. 使用 $ 和 $$ 格式表示数学公式
4. 语气友好、鼓励"""
    
    response = client.chat.completions.create(
        model=SOLVER_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ],
        max_tokens=1500,
        temperature=0.3,
        timeout=60
    )
    
    return response.choices[0].message.content


def chat_with_ai_stream(question_text: str, solution: str, knowledge_points: List[str],
                        review_history: List[Dict], user_message: str):
    """
    错题专属 AI 助教聊天（流式版本）
    """
    client = get_client()
    
    kp_str = "、".join(knowledge_points)
    history_str = ""
    if review_history:
        history_str = "\n**历史作答情况：**\n"
        for log in review_history[-3:]:
            history_str += f"- {log.get('review_time', '')}: {log.get('review_result', '')} - {log.get('ai_feedback', '')}\n"
    
    system_prompt = f"""你是一位专业的数学私教，正在帮助学生理解一道错题。

**当前题目：**
{question_text}

**标准解析：**
{solution}

**涉及的知识点：**
{kp_str}
{history_str}

请根据以上信息，针对性地回答学生的问题。回答要：
1. 结合当前题目的具体内容
2. 解释清晰，步骤详细
3. 使用 $ 和 $$ 格式表示数学公式
4. 语气友好、鼓励"""
    
    stream = client.chat.completions.create(
        model=SOLVER_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ],
        max_tokens=1500,
        temperature=0.3,
        timeout=60,
        stream=True
    )
    
    for chunk in stream:
        if chunk.choices[0].delta.content:
            yield chunk.choices[0].delta.content


def generate_similar_question_stream(question_text: str, knowledge_points: List[str], 
                                    difficulty: str = "中等"):
    """
    生成相似题目（流式版本）
    """
    client = get_client()
    
    kp_str = "、".join(knowledge_points)
    
    prompt = f"""请根据以下题目，生成一道新的同类练习题。

**原题目：**
{question_text}

**涉及的知识点：**
{kp_str}

**要求：**
1. 新题目必须与原题目不同，但考察相同的知识点
2. 难度：{difficulty}
3. 题目要完整、清晰
4. **所有数学公式必须使用 LaTeX 格式：**
   - 独立公式用 $$ 包裹，如：$$x = \\frac{{1}}{{2}}$$
   - 行内公式用 $ 包裹，如：$x^2 + y^2 = 1$
   - **绝对禁止使用** \\[ \\] 或 \\( \\) 格式
   - **绝对禁止使用** 中文标点符号在公式内
5. 解题步骤要分行显示，每个步骤单独一段，不要添加"步骤1"等编号

请按照以下纯 JSON 格式输出（不要包含任何 Markdown 标记）：
{{
    "question": "新题目的完整内容（使用 $ 和 $$ 格式的公式）",
    "solution": "详细的解题步骤（分段显示，使用 $ 和 $$ 格式的公式）",
    "answer": "最终答案"
}}"""
    
    stream = client.chat.completions.create(
        model=SOLVER_MODEL,
        messages=[
            {"role": "system", "content": "你是题目生成助手。直接输出 JSON，不要寒暄。所有数学公式必须用 $ 或 $$ 包裹，禁止使用 \\[ \\] 或 \\( \\) 格式。"},
            {"role": "user", "content": prompt}
        ],
        max_tokens=2000,
        temperature=0.7,
        timeout=60,
        stream=True
    )
    
    for chunk in stream:
        if chunk.choices[0].delta.content:
            yield chunk.choices[0].delta.content


def extract_knowledge_points_from_solution(solution: str) -> List[str]:
    """
    从解题过程中提取知识点（JSON 格式）
    """
    client = get_client()
    
    prompt = f"""请从以下解题过程中提取知识点，并以纯 JSON 数组格式输出。

**解题过程：**
{solution}

请输出格式：
["知识点1", "知识点2", "知识点3"]

重要：只输出 JSON 数组，不要包含任何 Markdown 标记。"""
    
    try:
        response = client.chat.completions.create(
            model=SOLVER_MODEL,
            messages=[
                {"role": "system", "content": "你是知识点提取助手。直接输出 JSON 数组，不要寒暄。"},
                {"role": "user", "content": prompt}
            ],
            max_tokens=500,
            temperature=0.1,
            timeout=30
        )
        
        result_text = response.choices[0].message.content.strip()
        
        if result_text.startswith("```"):
            result_text = result_text.split("```")[1]
            if result_text.startswith("json"):
                result_text = result_text[4:]
        result_text = result_text.strip()
        
        knowledge_points = json.loads(result_text)
        if isinstance(knowledge_points, list):
            return knowledge_points
    except:
        pass
    
    return []
