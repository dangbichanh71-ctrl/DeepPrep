"""
DeepPrep V5.0 - 全学段通用备考平台
重构目标：
1. 多图并发处理 + 重试机制
2. AI 答疑助手（替代协作修正）
3. 精准学科分类体系
4. 流式判卷 + 性能优化
5. 同类题生成 + 语境化追问
"""

import base64
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import plotly.express as px
import streamlit as st

from db_manager import (
    init_database,
    add_question,
    get_all_questions,
    get_question_by_id,
    get_questions_due_for_review,
    update_question_mastery,
    archive_question,
    get_review_logs,
    create_user,
    verify_user,
    get_user_by_id,
    delete_question,
    add_mastered_knowledge,
    get_mastered_knowledge,
    get_knowledge_stats_by_subject,
    get_questions_by_knowledge_point,
)
from ai_utils import (
    clean_latex,
    friendly_error,
    ocr_extract_text,
    solve_problem_text,
    solve_problem_text_stream,
    extract_answer_from_solution,
    judge_answer,
    judge_answer_stream,
    qa_assistant_stream,
    generate_similar_question_stream,
    chat_with_ai_stream,
    parse_imperfect_json,
)

# ==================== 常量配置 ====================
IDENTITY_SUBJECT_MAP: Dict[str, List[str]] = {
    "小学生": ["语文", "数学", "英语", "科学", "道德与法治"],
    "初中生": ["语文", "数学", "英语", "物理", "化学", "生物", "历史", "地理", "道德与法治"],
    "高中生": ["数学", "英语", "物理", "化学", "生物", "历史", "地理", "政治", "语文"],
    "大学生": ["高等数学", "线性代数", "概率论", "大学英语", "专业课(理工)", "专业课(经管)", "专业课(文史)"],
}

PAGE_OPTIONS = ["🏠 首页", "🔍 智能搜题", "🗂️ 错题库", "🔄 沉浸式复习", "🧠 知识图谱", "📊 学习统计"]

THEME_PRESETS = {
    "极简白": {
        "background": "#FFFFFF",
        "card": "#FFFFFF",
        "border": "#E5E7EB",
        "text": "#1F2937",
        "muted": "#6B7280",
        "accent": "#2563EB",
    },
    "护眼绿": {
        "background": "#F0F9F4",
        "card": "#FFFFFF",
        "border": "#D1FAE5",
        "text": "#1C3D27",
        "muted": "#3F7059",
        "accent": "#2F855A",
    },
    "清新蓝": {
        "background": "#F0F9FF",
        "card": "#FFFFFF",
        "border": "#BAE6FD",
        "text": "#0C4A6E",
        "muted": "#0369A1",
        "accent": "#0284C7",
    },
    "淡雅紫": {
        "background": "#FAF5FF",
        "card": "#FFFFFF",
        "border": "#E9D5FF",
        "text": "#581C87",
        "muted": "#7C3AED",
        "accent": "#8B5CF6",
    },
    "温暖米": {
        "background": "#FFFBEB",
        "card": "#FFFFFF",
        "border": "#FDE68A",
        "text": "#78350F",
        "muted": "#D97706",
        "accent": "#F59E0B",
    },
}

SESSION_DEFAULTS = {
    "is_logged_in": False,
    "user_id": None,           # 真实用户 ID（数据库中的 id）
    "username": None,          # 用户名
    "phone_number": "",        # 保留兼容
    "identity": "",
    "target_subjects": [],
    "current_page": PAGE_OPTIONS[0],
    "theme_choice": "极简白",
    "upload_preview": None,
    "upload_chat": {},
    "upload_results": [],
    "upload_current_index": 0,  # 智能搜题分页索引
    "review_inputs": {},
    "focus_question_id": None,
    "current_question_index": 0,  # 单题分页索引
    "review_question_list": [],  # 当前复习题目列表（ID列表）
    "current_review_qid": None,  # 强制锁定当前正在复习的题目 ID（防止刷新跳题）
    "review_stage": "answering",  # 双阶段状态机：'answering' | 'feedback'
    "current_result": None,  # 当前题目的判卷结果
    "temp_chat_history": {},  # 当前题目的临时聊天记录（按 qid 存储）
    "temp_similar_q": {},  # 当前题目的临时同类题（按 qid 存储）
    "temp_similar_data": {},  # 当前题目的临时同类题完整数据（包含question, solution, answer）
    "temp_similar_answer": {},  # 同类题的答案（按 qid 存储）
    "temp_similar_result": {},  # 同类题的判卷结果（按 qid 存储）
    "temp_similar_chat_history": {},  # 同类题的聊天记录（按 qid 存储）
    "similar_expander_expanded": {},  # 同类题展开器状态（按 qid 存储）
    "feedback_updated": {},  # 标记是否已更新数据库（按 qid 存储，避免重复更新）
}


# ==================== 基础工具函数 ====================
def init_session_state() -> None:
    """初始化所有需要的 session_state 变量"""
    for key, default in SESSION_DEFAULTS.items():
        if key not in st.session_state:
            st.session_state[key] = default
    
    # 强制检查 feedback_updated 必须是字典类型
    if not isinstance(st.session_state.get("feedback_updated"), dict):
        st.session_state.feedback_updated = {}


def format_math_text(text: str) -> str:
    """
    修复 LaTeX 渲染（调用 clean_latex）
    同时处理换行符，确保解析步骤分行显示
    """
    if not text:
        return ""
    
    # 先清理 LaTeX
    cleaned = clean_latex(text)
    
    # 处理换行符：将 \n 转换为 HTML 的 <br>，确保步骤分行显示
    # 但要注意不要破坏 LaTeX 公式内的内容
    import re
    
    # 分割文本，保留公式块
    # 先标记所有公式块
    formula_blocks = []
    formula_pattern = r'\$\$.*?\$\$|\$[^$]+\$'
    
    def replace_formula(match):
        idx = len(formula_blocks)
        formula_blocks.append(match.group(0))
        return f"__FORMULA_{idx}__"
    
    # 临时替换公式块
    text_with_placeholders = re.sub(formula_pattern, replace_formula, cleaned, flags=re.DOTALL)
    
    # 处理换行符：将连续的换行符转换为 <br><br>，单个换行符转换为 <br>
    text_with_placeholders = re.sub(r'\n\n+', '<br><br>', text_with_placeholders)
    text_with_placeholders = re.sub(r'\n', '<br>', text_with_placeholders)
    
    # 恢复公式块
    for idx, formula in enumerate(formula_blocks):
        text_with_placeholders = text_with_placeholders.replace(f"__FORMULA_{idx}__", formula)
    
    return text_with_placeholders


def clean_json_text(raw: str) -> str:
    """清洗 AI 返回的原始文本：去除 Markdown 代码块，提取 JSON 对象"""
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        parts = cleaned.split("```")
        if len(parts) >= 2:
            cleaned = parts[1]
            if cleaned.startswith("json"):
                cleaned = cleaned[4:]
            cleaned = cleaned.strip()
    first_brace = cleaned.find("{")
    last_brace = cleaned.rfind("}")
    if first_brace >= 0 and last_brace > first_brace:
        cleaned = cleaned[first_brace:last_brace + 1]
    return cleaned


def parse_judge_result(full_response: str) -> Tuple[bool, str]:
    """
    解析判卷流式输出，返回 (is_correct, feedback_text)。
    保守策略：解析失败默认判错。
    """
    judge_json = ""
    # 尝试从流式输出中提取 JSON
    if "{" in full_response:
        try:
            start = full_response.find("{")
            end = full_response.rfind("}") + 1
            if start >= 0 and end > start:
                judge_json = full_response[start:end]
                parsed = json.loads(judge_json)
                return parsed.get("is_correct") is True, parsed.get("reason", full_response)
        except Exception:
            pass
    # 兜底：无法解析
    return False, full_response or "无法解析判卷结果"


def stream_display(text: str, with_cursor: bool = True) -> str:
    """格式化流式输出文本，可选光标效果"""
    formatted = format_math_text(clean_latex(text))
    return formatted + "▌" if with_cursor else formatted


def parse_iso_datetime(value: Optional[str]) -> Optional[datetime]:
    """安全解析 ISO 时间"""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", ""))
    except Exception:
        return None


def format_next_review(value: Optional[str]) -> str:
    """格式化下次复习时间"""
    dt = parse_iso_datetime(value)
    if not dt:
        return "未安排"
    return dt.strftime("%Y-%m-%d %H:%M")


def describe_interval(minutes: int) -> str:
    """将分钟间隔转换为可读文本"""
    m = int(minutes)
    if m < 60:
        return str(m) + " 分钟"
    d = m // 1440
    h = (m % 1440) // 60
    if h == 0:
        return str(d) + " 天"
    return str(d) + " 天 " + str(h) + " 小时"


def build_theme_css(theme_name: str) -> str:
    """根据主题生成 CSS - 清新简洁风格，确保整个界面背景都能变化"""
    palette = THEME_PRESETS.get(theme_name, THEME_PRESETS["极简白"])
    
    # 统一使用纯色背景，确保整个界面都能应用
    return f"""
    <style>
    /* 主应用背景 - 确保整个界面都应用 */
    .stApp {{
        background-color: {palette['background']} !important;
        color: {palette['text']};
    }}
    
    /* 主内容区域背景 */
    .main .block-container {{
        background-color: {palette['background']} !important;
    }}
    
    /* 所有主要内容块 */
    div[data-testid="stVerticalBlock"] {{
        background-color: {palette['background']} !important;
    }}
    
    /* 侧边栏背景 */
    [data-testid="stSidebar"] {{
        background-color: {palette['card']} !important;
    }}
    
    /* 侧边栏内容区域 */
    [data-testid="stSidebar"] .block-container {{
        background-color: {palette['card']} !important;
    }}
    
    /* 卡片样式 */
    .app-card {{
        background: {palette['card']} !important;
        border: 1px solid {palette['border']} !important;
        border-radius: 12px;
        padding: 1.5rem;
        margin-bottom: 1.2rem;
    }}
    
    /* 主要按钮 */
    .stButton > button[kind="primary"] {{
        background-color: {palette['accent']} !important;
        color: #FFFFFF !important;
        border-radius: 8px;
        border: none;
        font-weight: 500;
    }}
    
    .stButton > button[kind="primary"]:hover {{
        background-color: {palette['accent']} !important;
        opacity: 0.9;
    }}
    
    /* 次要文本 */
    .muted-text {{
        color: {palette['muted']};
        font-size: 0.9rem;
    }}
    
    /* 警告框 */
    .stAlert {{
        border-radius: 8px;
    }}
    
    /* 输入框 */
    .stTextInput > div > div > input {{
        border: 1px solid {palette['border']} !important;
        border-radius: 8px;
    }}
    
    .stTextInput > div > div > input:focus {{
        border-color: {palette['accent']} !important;
    }}
    
    /* 选择框 */
    .stSelectbox > div > div {{
        border: 1px solid {palette['border']} !important;
        border-radius: 8px;
    }}
    </style>
    """


def encode_image(image_bytes: bytes) -> str:
    """将图片编码为 base64"""
    return base64.b64encode(image_bytes).decode("utf-8")


def decode_image(image_b64: str) -> bytes:
    """解码 base64 图片（增强错误处理）"""
    if not image_b64 or not isinstance(image_b64, str):
        raise ValueError("图片数据无效")
    
    try:
        # 移除可能的前缀（如 data:image/jpeg;base64,）
        if ',' in image_b64:
            image_b64 = image_b64.split(',')[-1]
        
        decoded = base64.b64decode(image_b64, validate=True)
        
        # 限制图片大小（防止内存问题）
        if len(decoded) > 10 * 1024 * 1024:  # 10MB
            raise ValueError("图片过大 (" + str(round(len(decoded) / 1024 / 1024, 1)) + "MB)，超过 10MB 限制")
        
        return decoded
    except Exception as e:
        raise ValueError("图片解码失败: " + str(e))


# ==================== 登录与主题 ====================
def render_login_view() -> None:
    """渲染登录/注册页面（真实用户鉴权）- 简洁清新风格"""
    st.markdown(
        """
        <style>
        [data-testid="stSidebar"] {display: none;}
        
        /* 简洁清新的背景 */
        .stApp {
            background-color: #F9FAFB !important;
        }
        
        /* 登录内容居中容器 - 无背景框 */
        .login-container {
            max-width: 420px;
            width: 100%;
            margin: 0 auto;
            padding: 2rem 1rem;
        }
        
        .login-header {
            text-align: center;
            margin-bottom: 2rem;
        }
        
        .login-title {
            font-size: 1.75rem;
            font-weight: 600;
            color: #1F2937;
            margin: 0.5rem 0;
        }
        
        .login-subtitle {
            color: #6B7280;
            font-size: 0.9rem;
            margin-top: 0.25rem;
        }
        
        /* 输入框 - 简洁风格 */
        .stTextInput > div > div > input {
            border-radius: 8px !important;
            border: 1px solid #E5E7EB !important;
            padding: 10px 14px !important;
            font-size: 0.95rem !important;
        }
        
        .stTextInput > div > div > input:focus {
            border-color: #2563EB !important;
            box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.1) !important;
        }
        
        /* 按钮 - 简洁风格 */
        .stButton > button[kind="primary"] {
            background-color: #2563EB !important;
            border: none !important;
            border-radius: 8px !important;
            padding: 10px 20px !important;
            font-weight: 500 !important;
            font-size: 0.95rem !important;
        }
        
        .stButton > button[kind="primary"]:hover {
            background-color: #1D4ED8 !important;
        }
        
        /* Tab 样式 - 简洁风格 */
        .stTabs [data-baseweb="tab-list"] {
            gap: 4px;
            background: #F3F4F6;
            padding: 4px;
            border-radius: 8px;
        }
        
        .stTabs [data-baseweb="tab"] {
            border-radius: 6px !important;
            font-weight: 500 !important;
        }
        
        .stTabs [aria-selected="true"] {
            background: white !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    
    # 登录内容容器 - 无背景框，直接显示在背景上
    st.markdown('<div class="login-container">', unsafe_allow_html=True)
    
    # Header - 简洁版本（带产品价值主张）
    st.markdown("""
    <div class="login-header">
        <div style="font-size: 3rem; margin-bottom: 0.5rem;">📚</div>
        <div class="login-title">DeepPrep</div>
        <div class="login-subtitle">智能备考平台 · 拍照搜题，AI 秒解</div>
    </div>
    <div style="max-width: 420px; margin: 0 auto 1.5rem auto; display: flex; justify-content: space-around; font-size: 0.8rem; color: #6B7280;">
        <span>📷 拍照搜题</span>
        <span>🤖 AI 解析</span>
        <span>🔄 间隔复习</span>
        <span>📊 知识图谱</span>
    </div>
    """, unsafe_allow_html=True)
    
    # 使用 tabs 切换登录/注册
    tab_login, tab_register = st.tabs(["🔐 登录", "📝 注册"])
    
    with tab_login:
        login_username = st.text_input("👤 用户名", key="login_username", placeholder="请输入用户名")
        login_password = st.text_input("🔒 密码", type="password", key="login_password", placeholder="请输入密码")
        login_identity = st.selectbox("🎓 学习身份", list(IDENTITY_SUBJECT_MAP.keys()), key="login_identity")
        
        st.markdown("<br>", unsafe_allow_html=True)
        
        if st.button("立即登录", key="btn_login", use_container_width=True, type="primary"):
            if not login_username or not login_password:
                st.warning("请输入用户名和密码")
            else:
                user_info = verify_user(login_username, login_password)
                if user_info:
                    st.session_state.is_logged_in = True
                    st.session_state.user_id = user_info["user_id"]
                    st.session_state.username = user_info["username"]
                    st.session_state.phone_number = user_info["username"]
                    st.session_state.identity = login_identity
                    st.session_state.target_subjects = IDENTITY_SUBJECT_MAP.get(login_identity, [])
                    st.success("✅ 登录成功，正在进入系统...")
                    st.rerun()
                else:
                    st.error("❌ 用户名或密码错误")
    
    with tab_register:
        reg_username = st.text_input("👤 用户名", key="reg_username", placeholder="3-20个字符")
        reg_password = st.text_input("🔒 密码", type="password", key="reg_password", placeholder="至少6个字符")
        reg_password_confirm = st.text_input("🔒 确认密码", type="password", key="reg_password_confirm", placeholder="再次输入密码")
        reg_identity = st.selectbox("🎓 学习身份", list(IDENTITY_SUBJECT_MAP.keys()), key="reg_identity")
        
        st.markdown("<br>", unsafe_allow_html=True)
        
        if st.button("立即注册", key="btn_register", use_container_width=True, type="primary"):
            if not reg_username or not reg_password:
                st.warning("请输入用户名和密码")
            elif len(reg_username) < 3 or len(reg_username) > 20:
                st.warning("用户名长度应为3-20个字符")
            elif len(reg_password) < 6:
                st.warning("密码长度至少6个字符")
            elif reg_password != reg_password_confirm:
                st.error("两次输入的密码不一致")
            else:
                if create_user(reg_username, reg_password):
                    st.success("✅ 注册成功！请切换到登录标签页进行登录")
                else:
                    st.error("❌ 注册失败，用户名可能已被使用")
    
    st.markdown("</div>", unsafe_allow_html=True)


def render_sidebar() -> None:
    """渲染侧边栏：导航 + 主题设置 + 用户信息"""
    # 获取侧边栏数据（缓存避免重复查询）
    current_user_id = st.session_state.get("user_id")
    current_user = st.session_state.username or "未知用户"
    identity = st.session_state.identity or "未设置"

    # 计算使用天数：从用户注册日期算起
    days_used = 1
    if current_user_id:
        try:
            user_info = get_user_by_id(current_user_id)
            if user_info and user_info.get("created_at"):
                try:
                    created = datetime.fromisoformat(user_info["created_at"].replace("Z", ""))
                    days_used = max(1, (datetime.now() - created).days + 1)
                except Exception:
                    pass
        except Exception:
            pass

    # 查询统计数据
    error_count = 0
    mastered_count = 0
    if current_user_id:
        try:
            questions = get_all_questions(user_id=current_user_id)
            active_qs = [q for q in questions if q.get("archived", 0) == 0]
            error_count = len(active_qs)
            mastered_kps = get_mastered_knowledge(current_user_id)
            mastered_count = len(mastered_kps)
        except Exception:
            pass

    with st.sidebar:
        # Logo 和标题
        st.markdown("""
        <div style="text-align: center; padding: 1rem 0;">
            <span style="font-size: 2.5rem;">📚</span>
            <h2 style="margin: 0.5rem 0 0 0; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; font-weight: 700;">DeepPrep</h2>
        </div>
        """, unsafe_allow_html=True)

        # 显示当前用户信息卡片
        st.markdown(
            '<div style="background: linear-gradient(135deg, #667eea20 0%, #764ba220 100%); padding: 12px 15px; border-radius: 10px; margin-bottom: 1rem;">'
            '<div style="font-size: 0.9rem; margin-bottom: 4px;"><strong>' + current_user + '</strong> · ' + identity + '</div>'
            '<div style="display: flex; gap: 12px; font-size: 0.75rem; color: #6B7280;">'
            '<span>📅 ' + str(days_used) + ' 天</span>'
            '<span>📋 ' + str(error_count) + ' 道错题</span>'
            '<span>✅ ' + str(mastered_count) + ' 个掌握</span>'
            '</div>'
            '</div>',
            unsafe_allow_html=True,
        )
        # 优化导航，避免卡顿
        try:
            current_index = PAGE_OPTIONS.index(st.session_state.current_page) if st.session_state.current_page in PAGE_OPTIONS else 0
        except:
            current_index = 0
        
        selected_page = st.radio(
            "功能导航",
            PAGE_OPTIONS,
            index=current_index,
            key="nav_radio"
        )
        
        if selected_page != st.session_state.current_page:
            st.session_state.current_page = selected_page
            st.rerun()

        st.markdown("---")
        st.subheader("🎨 主题设置")
        st.session_state.theme_choice = st.selectbox(
            "配色方案",
            list(THEME_PRESETS.keys()),
            index=list(THEME_PRESETS.keys()).index(st.session_state.theme_choice),
        )
        st.caption("💡 切换配色方案将改变整个界面的背景颜色")
        
        # 退出登录按钮
        st.markdown("---")
        if st.button("🚪 退出登录", key="logout", use_container_width=True):
            # 清除所有用户相关的 session state
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()


# ==================== 首页 Dashboard ====================
def _get_dashboard_data(current_user_id: int):
    """获取首页所需的所有数据（单次查询，减少 DB 调用）"""
    questions = get_all_questions(user_id=current_user_id)
    active = [q for q in questions if q.get("archived", 0) == 0]
    now = datetime.now()

    today_due = [
        q for q in active
        if parse_iso_datetime(q.get("next_review_time")) and parse_iso_datetime(q.get("next_review_time")) <= now
    ]
    today_due_count = len(today_due)

    # 按学科分组统计
    subject_counts = {}
    for q in active:
        s = q.get("subject") or "未分类"
        subject_counts[s] = subject_counts.get(s, 0) + 1

    # 已掌握知识点数
    mastered = get_mastered_knowledge(current_user_id)
    mastered_count = len(mastered)

    # 使用天数
    user_info = get_user_by_id(current_user_id)
    days_used = 1
    if user_info and user_info.get("created_at"):
        try:
            created = datetime.fromisoformat(user_info["created_at"].replace("Z", ""))
            days_used = max(1, (now - created).days + 1)
        except Exception:
            pass

    return {
        "active_count": len(active),
        "today_due_count": today_due_count,
        "mastered_count": mastered_count,
        "days_used": days_used,
        "subject_counts": subject_counts,
        "total_questions": len(questions),
        "total_reviews": sum(q.get("review_count", 0) for q in questions),
    }


def _kg_safe_init():
    """安全初始化：清理复习模式残留状态，防止知识图谱页面卡死"""
    review_keys = [
        "current_review_qid", "last_question_id",
        "current_result", "current_question_index", "review_question_list"
    ]
    for key in review_keys:
        if key in st.session_state:
            if key == "review_question_list":
                st.session_state[key] = []
            else:
                st.session_state[key] = None
    if st.session_state.get("review_stage") != "answering":
        st.session_state["review_stage"] = "answering"
    if st.session_state.get("upload_processing"):
        st.session_state["upload_processing"] = False


def render_dashboard() -> None:
    """渲染首页仪表盘"""
    current_user_id = st.session_state.get("user_id")
    if not current_user_id:
        st.warning("请先登录")
        return

    username = st.session_state.username or "同学"
    identity = st.session_state.identity or "未设置"
    data = _get_dashboard_data(current_user_id)

    # ====== 欢迎区 ======
    greeting = (
        "早上好" if datetime.now().hour < 12
        else "下午好" if datetime.now().hour < 18
        else "晚上好"
    )
    st.markdown("""
    <div style="text-align: center; padding: 1.5rem 0 0.5rem 0;">
        <span style="font-size: 3rem;">📚</span>
        <h1 style="margin: 0.5rem 0 0.2rem 0; font-weight: 700; font-size: 1.8rem;">
            """ + greeting + """，""" + username + """
        </h1>
        <p style="color: #6B7280; font-size: 0.95rem; margin: 0;">""" + identity + """ · 已使用 """ + str(data['days_used']) + """ 天</p>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("---")

    # ====== 核心数据卡片 ======
    cols = st.columns(4)
    palette = THEME_PRESETS.get(st.session_state.theme_choice, THEME_PRESETS["极简白"])

    # 卡片样式模板
    card_template = (
        '<div style="text-align: center; padding: 1.2rem 0.8rem; background: ' + palette["card"] +
        '; border: 1px solid ' + palette["border"] + '; border-radius: 12px;">'
        '<div style="font-size: 2rem;">{{icon}}</div>'
        '<div style="font-size: 1.6rem; font-weight: 700; color: ' + palette["accent"] + '; margin: 0.3rem 0;">{{value}}</div>'
        '<div style="font-size: 0.8rem; color: ' + palette["muted"] + ';">{{label}}</div>'
        '</div>'
    )

    cards = [
        ("📋", str(data["active_count"]), "活跃错题"),
        ("📌", str(data["today_due_count"]), "今日待复习"),
        ("🧠", str(data["mastered_count"]), "已掌握知识点"),
        ("📊", str(data["total_reviews"]), "累计复习次数"),
    ]
    for col, (icon, value, label) in zip(cols, cards):
        with col:
            st.markdown(
                card_template.replace("{{icon}}", icon).replace("{{value}}", value).replace("{{label}}", label),
                unsafe_allow_html=True,
            )

    st.markdown("<br>", unsafe_allow_html=True)

    # ====== 快捷入口 ======
    st.markdown("### 🚀 快速开始")
    qc1, qc2, qc3, qc4 = st.columns(4)

    shortcuts = [
        ("🔍", "智能搜题", "拍照上传，AI 秒解", "🔍 智能搜题", "search"),
        ("🗂️", "错题库", str(data['active_count']) + " 道错题待攻克", "🗂️ 错题库", "vault"),
        ("🔄", "沉浸式复习", "今日 " + str(data['today_due_count']) + " 题待复习", "🔄 沉浸式复习", "review"),
        ("🧠", "知识图谱", str(data['mastered_count']) + " 个知识点已掌握", "🧠 知识图谱", "graph"),
    ]

    for col, (icon, title, desc, page_name, key) in zip([qc1, qc2, qc3, qc4], shortcuts):
        with col:
            btn_label = icon + "\n" + title
            if st.button(btn_label, key=f"quick_{key}", use_container_width=True, type="primary"):
                st.session_state.current_page = page_name
                st.rerun()
            st.caption(desc)

    st.markdown("---")

    # ====== 学科分布 ======
    left, right = st.columns([1, 1])
    with left:
        st.markdown("### 📊 学科分布")
        if data["subject_counts"]:
            subjects = sorted(data["subject_counts"].items(), key=lambda x: x[1], reverse=True)
            total = sum(v for _, v in subjects)
            bars_html = ""
            for s, cnt in subjects[:8]:
                pct = cnt / total * 100 if total > 0 else 0
                bar_color = palette["accent"]
                bars_html += (
                    '<div style="margin-bottom: 8px;">'
                    '<div style="display: flex; justify-content: space-between; font-size: 0.85rem; margin-bottom: 2px;">'
                    '<span>' + s + '</span><span style="color: #6B7280;">' + str(cnt) + ' 题</span>'
                    '</div>'
                    '<div style="background: #E5E7EB; border-radius: 6px; height: 8px;">'
                    '<div style="background: ' + bar_color + '; width: ' + str(pct) + '%; height: 8px; border-radius: 6px;"></div>'
                    '</div></div>'
                )
            st.markdown(bars_html, unsafe_allow_html=True)
        else:
            st.info("暂无错题数据，去搜题页上传题目吧！")

    with right:
        st.markdown("### 💡 学习建议")
        if data["today_due_count"] >= 5:
            st.warning("📌 今天有 " + str(data['today_due_count']) + " 道题目等待复习，建议现在开始！")
        elif data["active_count"] == 0:
            st.info("🎉 暂无需要复习的题目，去上传新题吧！")
        else:
            st.success("✅ 复习进度良好，继续保持！")

        if data["mastered_count"] == 0:
            st.info("🧠 还没有已掌握的知识点，完成复习达到 3 次答对即可点亮。")

        st.markdown(
            '<div style="font-size: 0.85rem; color: #6B7280; margin-top: 12px; padding: 12px; background: #F9FAFB; border-radius: 8px;">'
            '<strong>间隔重复学习法</strong><br>'
            '答错 → 10 分钟后复习<br>'
            '第 1 次答对 → 1 天后复习<br>'
            '第 2 次答对 → 7 天后复习<br>'
            '第 3 次答对 → 15 天后归档 ✅<br>'
            '</div>',
            unsafe_allow_html=True,
        )


# ==================== 智能搜题 ====================
def process_single_image(image_bytes: bytes, filename: str, target_subjects: List[str], 
                        user_identity: str, display_placeholder=None, max_retries: int = 1) -> Dict:
    """
    处理单张图片（带重试机制，支持流式显示）
    
    参数:
        display_placeholder: Streamlit 的 empty 占位符，用于实时显示流式输出
    """
    for attempt in range(max_retries + 1):
        try:
            # OCR
            if display_placeholder:
                display_placeholder.markdown(f"**📷 [{filename}]** 正在识别图片文字...")
            ocr_text = ocr_extract_text(image_bytes)
            if not ocr_text or len(ocr_text.strip()) < 10:
                if attempt < max_retries:
                    continue
                return {"success": False, "filename": filename, "error": "OCR 返回空结果"}
            
            # 立即清理OCR文本中的LaTeX乱码
            ocr_text = clean_latex(ocr_text)
            
            # 流式解题与分析
            if display_placeholder:
                display_placeholder.markdown(f"**📷 [{filename}]** 🤔 正在解析题目，AI 正在思考...\n\n")
            
            # 收集流式输出，实时提取并显示解题步骤（而不是原始JSON）
            full_response = ""
            last_displayed_length = 0  # 记录上次显示的文本长度，避免重复处理
            
            for chunk in solve_problem_text_stream(ocr_text, target_subjects, user_identity):
                full_response += chunk
                
                # 实时提取analysis字段内容进行显示（每10个字符更新一次）
                if display_placeholder and len(full_response) - last_displayed_length >= 10:
                    displayed_text = ""
                    
                    # 方法：从流式输出中智能提取analysis字段的内容
                    # 查找 "analysis" 字段的位置
                    analysis_key = '"analysis"'
                    analysis_idx = full_response.find(analysis_key)
                    
                    if analysis_idx >= 0:
                        # 找到analysis字段，提取其值
                        # 跳过 "analysis" 和冒号，找到值的开始位置
                        value_start = full_response.find(':', analysis_idx) + 1
                        if value_start > 0:
                            # 跳过空白字符
                            while value_start < len(full_response) and full_response[value_start] in ' \t\n\r':
                                value_start += 1
                            
                            # 查找值的开始引号
                            if value_start < len(full_response) and full_response[value_start] == '"':
                                content_start = value_start + 1
                                # 提取从引号后到当前文本末尾的内容
                                partial_content = full_response[content_start:]
                                
                                # 智能处理：查找下一个未转义的引号（可能是字段结束或下一个字段开始）
                                # 但要注意转义字符
                                end_pos = len(partial_content)
                                for i in range(len(partial_content)):
                                    if partial_content[i] == '"' and (i == 0 or partial_content[i-1] != '\\'):
                                        # 检查这是否是下一个字段的开始（后面跟着冒号）
                                        if i + 1 < len(partial_content) and partial_content[i+1] in ': \t\n':
                                            end_pos = i
                                            break
                                
                                # 提取内容并处理转义字符
                                extracted = partial_content[:end_pos]
                                displayed_text = extracted.replace('\\n', '\n').replace('\\"', '"').replace('\\t', '\t').replace('\\r', '\r')
                    
                    # 显示提取的解题步骤，或显示友好提示
                    if displayed_text and len(displayed_text.strip()) > 5:
                        display_text = format_math_text(clean_latex(displayed_text)) + "▌"
                    else:
                        # 如果还没找到analysis字段，显示友好的提示
                        display_text = "🤔 AI 正在思考解题思路...▌"
                    
                    # 流式显示解析过程（不重复显示文件名，因为expander标题已经显示了）
                    display_placeholder.markdown(
                        f"{display_text}",
                        unsafe_allow_html=True
                    )
                    last_displayed_length = len(full_response)
            
            # 最终解析并显示完整的格式化解题步骤
            if display_placeholder:
                json_text = clean_json_text(full_response)
                parsed_data = parse_imperfect_json(json_text)

                if parsed_data and isinstance(parsed_data, dict):
                    analysis = parsed_data.get("analysis", "")
                    answer = parsed_data.get("answer", "")
                    # 显示格式化的解题步骤
                    solution_text = analysis
                    if answer and answer not in analysis:
                        solution_text += f"\n\n**答案：**\n{answer}"
                    # 解析完成，显示简洁的完成提示和解题步骤
                    display_placeholder.markdown(
                        f"**✅ 解析完成**\n\n"
                        f"{format_math_text(clean_latex(solution_text))}",
                        unsafe_allow_html=True
                    )
                else:
                    # 解析失败，显示原始文本
                    display_placeholder.markdown(
                        f"**✅ 解析完成**\n\n"
                        f"{format_math_text(clean_latex(full_response))}",
                        unsafe_allow_html=True
                    )
            
            # 解析 JSON（统一清洗）
            json_text = clean_json_text(full_response)
            parsed_data = parse_imperfect_json(json_text)

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
            else:
                # 回退到文本解析
                solution = raw_content
                knowledge_points = []
                subject = None
                topic = None
                
                # 尝试从文本中提取信息
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
            
            if not solution:
                if attempt < max_retries:
                    continue
                return {"success": False, "filename": filename, "error": "解析返回空结果"}
            
            # 提取答案
            try:
                answer = extract_answer_from_solution(solution)
            except Exception:
                answer = "暂未提取"
            
            # 完全信任AI返回的值，不做任何验证或覆盖
            # 如果AI返回空值，使用默认值，但绝不根据用户身份猜测
            if not subject:
                subject = "未分类"
            if not topic:
                topic = "未标注"
            if not knowledge_points:
                knowledge_points = []
            
            return {
                "success": True,
                "filename": filename,
                "image_base64": encode_image(image_bytes),
                "question_text": ocr_text,
                "question_text_clean": clean_latex(ocr_text),  # 清洗后的题目文本
                "solution": solution,
                "answer": answer,
                "subject": subject,
                "topic": topic,
                "knowledge_points": knowledge_points,
            }
        except Exception as e:
            if display_placeholder:
                display_placeholder.error(f"**📷 [{filename}]** ❌ {friendly_error(e)}")
            if attempt < max_retries:
                continue
            return {"success": False, "filename": filename, "error": friendly_error(e)}
    
    return {"success": False, "filename": filename, "error": "处理失败（已重试）"}


def render_smart_upload() -> None:
    st.title("🔍 智能搜题")
    st.caption("支持多图并发处理 | OCR → AI 解题 → AI 答疑 → 入库")

    uploaded_files = st.file_uploader(
        "上传题目照片（支持多选，最多10张）", 
        type=["png", "jpg", "jpeg"],
        accept_multiple_files=True
    )
    
    # 限制最多10张图片
    if uploaded_files and len(uploaded_files) > 10:
        st.warning("⚠️ 最多支持10张图片，已自动截取前10张")
        uploaded_files = uploaded_files[:10]
    
    # 检查是否正在处理
    is_processing = st.session_state.get("upload_processing", False)
    
    if st.button("🚀 开始解析", disabled=not uploaded_files or is_processing):
        if not uploaded_files:
            st.warning("请先上传图片")
        elif is_processing:
            st.warning("⚠️ 正在处理中，请等待完成...")
        else:
            st.session_state.upload_results = []
            st.session_state.upload_current_index = 0  # 重置分页索引
            st.session_state.upload_processing = True  # 标记正在处理
            st.session_state.upload_progress_expanded = {}  # 记录每个题目的展开状态
            
            # 为每张图片创建可折叠的实时显示区域
            st.markdown("### 📊 实时解析进度")
            
            # 注意：解析过程中不显示控制按钮，避免中断处理
            
            # 为每张图片创建可折叠的显示区域
            display_placeholders = {}
            status_placeholders = {}  # 用于显示状态
            expanders = {}
            
            # 初始化状态字典
            if "upload_file_status" not in st.session_state:
                st.session_state.upload_file_status = {}
            
            for idx, f in enumerate(uploaded_files):
                # 初始化状态
                if f.name not in st.session_state.upload_file_status:
                    st.session_state.upload_file_status[f.name] = "等待中"
                
                # 默认展开当前正在处理的题目，其他折叠
                default_expanded = idx == 0
                if f.name not in st.session_state.upload_progress_expanded:
                    st.session_state.upload_progress_expanded[f.name] = default_expanded
                
                # 使用简单的标题（因为expander标题无法动态更新，状态在内部显示）
                expander_title = f"📷 {f.name}"
                
                expander = st.expander(
                    expander_title,
                    expanded=st.session_state.upload_progress_expanded.get(f.name, default_expanded)
                )
                expanders[f.name] = expander
                with expander:
                    # 状态显示区域（在内容上方）
                    status_placeholders[f.name] = st.empty()
                    display_placeholders[f.name] = st.empty()
                    
                    # 初始化状态显示
                    current_status = st.session_state.upload_file_status.get(f.name, "等待中")
                    if current_status == "等待中":
                        status_placeholders[f.name].info(f"⏸️ **等待处理...** ({idx + 1}/{len(uploaded_files)})")
                    elif current_status == "正在处理":
                        status_placeholders[f.name].info(f"🔄 **正在处理中...** ({idx + 1}/{len(uploaded_files)})")
                    elif current_status == "解析完成":
                        status_placeholders[f.name].success(f"✅ **解析完成** ({idx + 1}/{len(uploaded_files)})")
                    elif current_status == "处理失败":
                        status_placeholders[f.name].error(f"❌ **处理失败** ({idx + 1}/{len(uploaded_files)})")
            
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            # 顺序处理多张图片（支持流式显示）
            total = len(uploaded_files)
            completed = 0
            
            for idx, f in enumerate(uploaded_files):
                # 更新状态为"正在处理"
                st.session_state.upload_file_status[f.name] = "正在处理"
                
                # 更新状态显示和内容
                with expanders[f.name]:
                    status_placeholders[f.name].info(f"🔄 **正在处理中...** ({idx + 1}/{total})")
                    display_placeholders[f.name].markdown(f"**准备开始解析...**")
                
                # 处理图片
                result = process_single_image(
                    f.read(),
                    f.name,
                    st.session_state.target_subjects,
                    st.session_state.identity,
                    display_placeholder=display_placeholders.get(f.name)
                )
                
                # 更新结果和状态
                st.session_state.upload_results.append(result)
                completed += 1
                progress_bar.progress(completed / total)
                status_text.text(f"已处理 {completed}/{total} 张图片...")
            
                # 根据处理结果更新状态
                if result.get("success"):
                    st.session_state.upload_file_status[f.name] = "解析完成"
                    with expanders[f.name]:
                        status_placeholders[f.name].success(f"✅ **解析完成** ({idx + 1}/{total})")
                    st.session_state.upload_progress_expanded[f.name] = False  # 成功后自动折叠
                else:
                    st.session_state.upload_file_status[f.name] = "处理失败"
                    with expanders[f.name]:
                        status_placeholders[f.name].error(f"❌ **处理失败** ({idx + 1}/{total})")
                    st.session_state.upload_progress_expanded[f.name] = True  # 失败时保持展开
            
            # 全部完成后，显示总结信息
            success_count = sum(1 for r in st.session_state.upload_results if r.get("success"))
            st.session_state.upload_processing = False  # 标记处理完成
            
            if success_count > 0:
                st.success(f"✅ 成功处理 {success_count}/{total} 张图片")
            if success_count < total:
                st.error(f"❌ {total - success_count} 张图片处理失败")
            
            # 处理完成后，自动隐藏进度区域（通过标记控制）
            if success_count == total:
                st.info("💡 所有题目解析完成！请在下方的分页查看区域查看详细结果。")
    
    # 显示处理结果 - 单题分页模式
    # 只有在处理完成且有结果时才显示
    if st.session_state.upload_results and not st.session_state.get("upload_processing", False):
        # 过滤出成功的结果
        success_results = [r for r in st.session_state.upload_results if r.get("success")]
        
        if not success_results:
            st.warning("暂无成功处理的题目")
            return
        
        # 确保索引有效
        total_questions = len(success_results)
        if st.session_state.upload_current_index >= total_questions:
            st.session_state.upload_current_index = 0
        if st.session_state.upload_current_index < 0:
            st.session_state.upload_current_index = total_questions - 1
        
        current_idx = st.session_state.upload_current_index
        result = success_results[current_idx]
        
        # 导航栏
        nav_cols = st.columns([1, 2, 1])
        with nav_cols[0]:
            if st.button("⬅️ 上一题", key="prev_upload", disabled=total_questions <= 1):
                st.session_state.upload_current_index = (current_idx - 1) % total_questions
                st.rerun()
        with nav_cols[1]:
            st.markdown(f"<div style='text-align: center;'><strong>第 {current_idx + 1} / {total_questions} 题</strong></div>", unsafe_allow_html=True)
        with nav_cols[2]:
            if st.button("➡️ 下一题", key="next_upload", disabled=total_questions <= 1):
                st.session_state.upload_current_index = (current_idx + 1) % total_questions
                st.rerun()
        
        st.markdown("---")
        
        # 显示当前题目
        result_key = f"result_{current_idx}"
        if result_key not in st.session_state.upload_chat:
            st.session_state.upload_chat[result_key] = []
        
        st.markdown(f"### 📄 {result['filename']}")
        with st.container():
            st.markdown('<div class="app-card">', unsafe_allow_html=True)
            cols = st.columns([1, 1])
            with cols[0]:
                st.image(
                    decode_image(result["image_base64"]),
                    caption=f"自动分类：{result['subject']}",
                    use_column_width=True,
                )
            with cols[1]:
                st.text_area("题目文本", clean_latex(result["question_text"]), height=200, key=f"text_{current_idx}", disabled=True)
            
            st.markdown("#### 🧠 解题过程")
            st.markdown(format_math_text(clean_latex(result["solution"])), unsafe_allow_html=True)
            st.info(f"**答案：** {format_math_text(clean_latex(result['answer']))}", icon="🧾")
            st.markdown(
                f"**学科**：{result['subject']} ｜ **主题**：{result['topic']} ｜ "
                f"**知识点**：{'、'.join(result['knowledge_points']) or '未标注'}"
            )
            
            # AI 答疑助手 - 优化渲染性能
            st.markdown("---")
            st.markdown("### 🤖 AI 答疑助手")
            
            upload_chat_container = st.container()
            with upload_chat_container:
                for msg in st.session_state.upload_chat[result_key]:
                    with st.chat_message(msg["role"]):
                        st.markdown(format_math_text(clean_latex(msg["content"])), unsafe_allow_html=True)
            
            user_question = st.chat_input(
                "对题目或解析有疑问？问问 AI...",
                key=f"chat_{current_idx}"
            )
            if user_question:
                st.session_state.upload_chat[result_key].append({"role": "user", "content": user_question})
                
                with upload_chat_container:
                    with st.chat_message("user"):
                        st.markdown(user_question)
                    
                    with st.chat_message("assistant"):
                        response_placeholder = st.empty()
                        full_response = ""
                        for chunk in qa_assistant_stream(
                            clean_latex(result["question_text"]),
                            clean_latex(result["solution"]),
                            user_question
                        ):
                            full_response += chunk
                            # 每5个字符更新一次显示，减少渲染次数
                            if len(full_response) % 5 == 0 or chunk == "":
                                response_placeholder.markdown(stream_display(full_response), unsafe_allow_html=True)

                        # 最终显示完整内容
                        response_placeholder.markdown(format_math_text(clean_latex(full_response)), unsafe_allow_html=True)
                        st.session_state.upload_chat[result_key].append({"role": "assistant", "content": full_response})
            
            # 答案有误反馈
            feedback_key = f"feedback_{current_idx}"
            if feedback_key not in st.session_state:
                st.session_state[feedback_key] = False

            col_fb, col_save = st.columns([1, 1])
            with col_fb:
                if st.button("⚠️ 报告答案有误", key=f"report_{current_idx}", use_container_width=True):
                    st.session_state[feedback_key] = True

            if st.session_state[feedback_key]:
                st.warning(
                    "已记录反馈。AI 解析可能存在误差，建议结合教材或老师确认。"
                    "作为产品设计，我们深知 AI 的局限性，后续将支持人工审核和用户纠错机制。"
                )

            # 保存按钮 - 完全信任AI返回的值
            with col_save:
                if st.button("✅ 存入题库", key=f"save_{current_idx}", type="primary"):
                    try:
                        # 直接使用AI分析返回的值，不做任何转换或验证
                        db_subject = result.get("subject")
                        db_topic = result.get("topic")
                        db_knowledge_points = result.get("knowledge_points")
                        db_solution = result.get("solution") or ""
                        db_question_text_clean = result.get("question_text_clean") or clean_latex(result.get("question_text", ""))

                        # 处理空值：如果AI返回null或空，使用默认值，但绝不猜测
                        if not db_subject:
                            db_subject = "未分类"
                        if not db_topic:
                            db_topic = "未标注"
                        if not db_knowledge_points:
                            db_knowledge_points = []

                        # 确保knowledge_points是列表格式
                        if isinstance(db_knowledge_points, str):
                            db_knowledge_points = [kp.strip() for kp in db_knowledge_points.split(',') if kp.strip()]

                        # 获取当前用户 ID（多用户数据隔离）
                        current_user_id = st.session_state.get("user_id")

                        question_id = add_question(
                            result["image_base64"],
                            db_solution,
                            db_knowledge_points,
                            db_subject,
                            db_topic,
                            user_id=current_user_id,
                            question_text_clean=db_question_text_clean,
                        )
                        st.success(f"✅ 已保存（ID: {question_id}）| 学科：{db_subject} | 主题：{db_topic}")
                        # 从结果列表中移除
                        st.session_state.upload_results = [r for r in st.session_state.upload_results if r != result]
                        st.session_state.upload_chat.pop(result_key, None)
                        # 调整索引
                        if st.session_state.upload_current_index >= len([r for r in st.session_state.upload_results if r.get("success")]):
                            st.session_state.upload_current_index = max(0, len([r for r in st.session_state.upload_results if r.get("success")]) - 1)
                        st.rerun()
                    except Exception as exc:
                        st.error(f"保存失败：{exc}")
            
            st.markdown("</div>", unsafe_allow_html=True)


# ==================== 错题库 ====================
@st.cache_data(ttl=5, show_spinner=False)  # 缓存5秒，减少重复查询
def _get_cached_questions(user_id: int) -> List[Dict]:
    """缓存错题列表查询结果"""
    try:
        all_questions = get_all_questions(user_id=user_id)
        return [q for q in all_questions if q and q.get("archived", 0) == 0]
    except Exception as e:
        print(f"获取错题列表失败: {e}")
        return []


def render_mistake_vault() -> None:
    st.title("🗂️ 错题库")
    st.caption("按学科分组展示，专注处理活跃错题 | 文本优先，图片折叠")

    try:
        # 获取当前用户 ID（多用户数据隔离）
        current_user_id = st.session_state.get("user_id")
        if not current_user_id:
            st.warning("请先登录")
            return
        
        # 安全获取错题列表，使用缓存减少数据库查询
        try:
            questions = _get_cached_questions(current_user_id)
            
            if not questions:
                st.info("暂无错题，先去智能搜题吧！")
                return
            
            # 限制显示数量，防止内存问题（最多显示1000题）
            MAX_DISPLAY_QUESTIONS = 1000
            if len(questions) > MAX_DISPLAY_QUESTIONS:
                st.warning(f"⚠️ 错题数量较多（{len(questions)} 题），仅显示最近 {MAX_DISPLAY_QUESTIONS} 题")
                questions = questions[:MAX_DISPLAY_QUESTIONS]
                
        except Exception as db_error:
            st.error(f"❌ 获取错题列表失败: {str(db_error)}")
            import traceback
            with st.expander("查看错误详情", expanded=True):
                st.code(traceback.format_exc())
            st.button("🔄 重试", on_click=lambda: st.rerun())
            return
        
        if not questions:
            st.info("暂无错题，先去智能搜题吧！")
            return

        grouped: Dict[str, List[Dict]] = {}
        for q in questions:
            subject = q.get("subject") or "未分类"
            grouped.setdefault(subject, []).append(q)

        # 确保 grouped.keys() 转换为列表，并过滤掉 None 和空字符串
        subject_names = [s for s in grouped.keys() if s and isinstance(s, str)]
        if not subject_names:
            st.warning("⚠️ 学科数据异常，无法显示错题")
            return
        
        # 限制标签页数量，防止界面崩溃（Streamlit tabs 可能有性能限制）
        MAX_TABS = 30  # 增加到30个标签页
        if len(subject_names) > MAX_TABS:
            st.warning(f"⚠️ 学科数量较多（{len(subject_names)} 个），仅显示前 {MAX_TABS} 个学科")
            subject_names = subject_names[:MAX_TABS]
            # 只保留前MAX_TABS个学科的数据
            grouped = {k: grouped[k] for k in subject_names if k in grouped}
        
        try:
            tabs = st.tabs(subject_names)
        except Exception as tabs_error:
            st.error(f"❌ 创建标签页失败: {str(tabs_error)}")
            st.info("💡 提示：学科数量可能过多，请尝试归档部分错题")
            return
        
        # 确保顺序一致：tabs 和 subject_names 一一对应
        for idx, tab in enumerate(tabs):
            if idx >= len(subject_names):
                break
            subject = subject_names[idx]
            if subject not in grouped:
                continue
            items = grouped[subject]
            with tab:
                try:
                    # 限制每个标签页显示的错题数量，防止渲染过多导致崩溃
                    MAX_ITEMS_PER_TAB = 200  # 每个学科最多显示200题
                    display_items = items[:MAX_ITEMS_PER_TAB]
                    if len(items) > MAX_ITEMS_PER_TAB:
                        st.info(f"📋 该学科共有 {len(items)} 题，仅显示最近 {MAX_ITEMS_PER_TAB} 题")
                    
                    # 使用分页或虚拟滚动优化大量数据渲染
                    for question_idx, question in enumerate(display_items):
                        # 为每个错题添加唯一容器，避免 key 冲突
                        question_key = f"question_{subject}_{question.get('id', question_idx)}"
                        with st.container():
                            try:
                                st.markdown('<div class="app-card">', unsafe_allow_html=True)
                                st.markdown(f"#### 🏷️ {subject} | ID #{question.get('id', 'N/A')}")
                                correct_count = question.get('correct_count', 0) or 0
                                st.caption(
                                    f"✅ 答对 {correct_count}/3 次 ｜ "
                                    f"📊 正确率 {question.get('accuracy', 0.0):.1f}% ｜ "
                                    f"⏱️ 下次复习 {format_next_review(question.get('next_review_time'))}"
                                )
                                
                                # 显示主题和知识点标签
                                topic = question.get("topic", "") or ""
                                knowledge_points = question.get("knowledge_points", [])
                                # 确保 knowledge_points 是列表
                                if isinstance(knowledge_points, str):
                                    try:
                                        import json
                                        knowledge_points = json.loads(knowledge_points)
                                    except:
                                        knowledge_points = []
                                if not isinstance(knowledge_points, list):
                                    knowledge_points = []
                                
                                if topic or knowledge_points:
                                    tag_html = '<div style="margin: 8px 0; display: flex; flex-wrap: wrap; gap: 6px;">'
                                    if topic and topic != "未标注":
                                        tag_html += f'<span style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 4px 12px; border-radius: 15px; font-size: 12px; font-weight: 500;">📌 {topic}</span>'
                                    if knowledge_points:
                                        for kp in knowledge_points[:5]:  # 最多显示5个
                                            if kp and isinstance(kp, str):
                                                tag_html += f'<span style="background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%); color: white; padding: 4px 10px; border-radius: 12px; font-size: 11px;">🏷️ {kp}</span>'
                                    tag_html += '</div>'
                                    st.markdown(tag_html, unsafe_allow_html=True)
                                
                                # 优先显示文本题目（如果有）
                                question_text_clean = question.get("question_text_clean", "") or ""
                                if question_text_clean:
                                    st.markdown("**📝 题目内容：**")
                                    st.markdown(format_math_text(question_text_clean), unsafe_allow_html=True)
                                
                                # 图片折叠显示（辅助视图）- 延迟加载，避免一次性解码所有图片
                                question_image = question.get("question_image")
                                if question_image:
                                    try:
                                        # 检查图片数据是否有效
                                        if not question_image or len(question_image) < 100:
                                            st.warning("⚠️ 图片数据不完整")
                                        else:
                                            with st.expander("🖼️ 查看原图", expanded=False):
                                                try:
                                                    image_bytes = decode_image(question_image)
                                                    st.image(
                                                        image_bytes,
                                                        caption="题目原图",
                                                        use_column_width=True,
                                                    )
                                                except Exception as decode_error:
                                                    st.warning(f"⚠️ 图片解码失败: {str(decode_error)}")
                                    except Exception as img_error:
                                        st.warning(f"⚠️ 图片加载失败: {str(img_error)}")
                                
                                col1, col2 = st.columns(2)
                                if col1.button("去复习", key=f"go_review_{question.get('id')}"):
                                    st.session_state.focus_question_id = question.get("id")
                                    st.session_state.current_page = "🔄 沉浸式复习"
                                    st.rerun()
                                if col2.button("🗑️ 删除此题 (已掌握)", key=f"archive_{question.get('id')}"):
                                    try:
                                        archive_question(question.get("id"), archived=True, user_id=current_user_id)
                                        st.rerun()
                                    except Exception as archive_error:
                                        st.error(f"归档失败: {str(archive_error)}")
                                st.markdown("</div>", unsafe_allow_html=True)
                            except Exception as question_error:
                                # 单个错题渲染失败不影响其他错题
                                st.warning(f"⚠️ 错题 ID {question.get('id', 'N/A')} 显示失败: {str(question_error)}")
                                continue
                except Exception as tab_error:
                    st.error(f"❌ 显示错题时出错: {str(tab_error)}")
                    import traceback
                    with st.expander("查看错误详情", expanded=False):
                        st.code(traceback.format_exc())
    
    except Exception as e:
        st.error(friendly_error(e))
        st.info("💡 提示：可能是数据加载异常，请尝试刷新页面")
        st.button("🔄 刷新页面", on_click=lambda: st.rerun())


# ==================== 复习模式（双阶段状态机） ====================
def render_review_mode() -> None:
    st.title("🔄 沉浸式复习")
    st.caption("优先推送正确率低、已经到期的题目 | 文本优先 | 双阶段状态机")
    
    # 获取当前用户 ID（多用户数据隔离）
    current_user_id = st.session_state.get("user_id")
    
    # 获取待复习题目列表
    due_questions = get_questions_due_for_review(user_id=current_user_id)
    focus_id = st.session_state.focus_question_id
    
    # 处理焦点题目
    if focus_id:
        focus_question = get_question_by_id(focus_id, user_id=current_user_id)
        if focus_question:
            if all(q["id"] != focus_id for q in due_questions):
                due_questions.insert(0, focus_question)
            else:
                due_questions = [q for q in due_questions if q["id"] != focus_id]
                due_questions.insert(0, focus_question)
        st.session_state.focus_question_id = None
        # 设置当前复习题目 ID
        st.session_state.current_review_qid = focus_id
    
    # 如果没有待复习题目
    if not due_questions:
        st.success("🎉 今日所有任务均已完成，可以休息啦！")
        # 清除锁定
        st.session_state.current_review_qid = None
        return
    
    # ========== 核心修复：使用 current_review_qid 锁定当前题目 ==========
    # 优先检查 current_review_qid，如果存在则强制显示该题目
    locked_qid = st.session_state.current_review_qid
    
    if locked_qid:
        # 尝试从 due_questions 中找到锁定的题目
        locked_question = None
        for q in due_questions:
            if q["id"] == locked_qid:
                locked_question = q
                break
        
        # 如果找不到，尝试从数据库获取
        if not locked_question:
            locked_question = get_question_by_id(locked_qid, user_id=current_user_id)
            if locked_question:
                # 将锁定的题目插入到列表开头
                due_questions.insert(0, locked_question)
        
        # 如果找到了锁定的题目，强制使用它
        if locked_question:
            question = locked_question
            qid = locked_qid
            # 更新索引（如果题目在列表中）
            try:
                current_index = next(i for i, q in enumerate(due_questions) if q["id"] == qid)
            except StopIteration:
                current_index = 0
        else:
            # 锁定的题目不存在，清除锁定并使用索引
            st.session_state.current_review_qid = None
            # 确保 current_question_index 是有效的整数
            current_index = st.session_state.get("current_question_index", 0)
            if current_index is None or not isinstance(current_index, int):
                current_index = 0
            if current_index >= len(due_questions) or current_index < 0:
                current_index = 0
            question = due_questions[current_index]
            qid = question["id"]
    else:
        # 没有锁定，使用索引
        # 确保 current_question_index 是有效的整数
        current_index = st.session_state.get("current_question_index", 0)
        if current_index is None or not isinstance(current_index, int):
            current_index = 0
        if current_index >= len(due_questions) or current_index < 0:
            current_index = 0
        question = due_questions[current_index]
        qid = question["id"]
        # 设置锁定
        st.session_state.current_review_qid = qid
    
    # 初始化题目列表（如果为空或已变化）
    current_list_ids = [q["id"] for q in due_questions]
    if (not st.session_state.review_question_list or 
        st.session_state.review_question_list != current_list_ids):
        st.session_state.review_question_list = current_list_ids
        st.session_state.current_question_index = current_index
    
    # 初始化当前题目的状态（按 user_id + qid 存储，防止刷新丢失和用户数据混淆）
    # 使用组合键确保不同用户的数据完全隔离
    user_qid_key = f"{current_user_id}_{qid}"
    
    if user_qid_key not in st.session_state.temp_chat_history:
        st.session_state.temp_chat_history[user_qid_key] = []
    if user_qid_key not in st.session_state.temp_similar_q:
        st.session_state.temp_similar_q[user_qid_key] = None
    if user_qid_key not in st.session_state.temp_similar_data:
        st.session_state.temp_similar_data[user_qid_key] = None
    if user_qid_key not in st.session_state.temp_similar_answer:
        st.session_state.temp_similar_answer[user_qid_key] = None
    if user_qid_key not in st.session_state.temp_similar_result:
        st.session_state.temp_similar_result[user_qid_key] = None
    if user_qid_key not in st.session_state.temp_similar_chat_history:
        st.session_state.temp_similar_chat_history[user_qid_key] = []
    if user_qid_key not in st.session_state.similar_expander_expanded:
        st.session_state.similar_expander_expanded[user_qid_key] = False
    if user_qid_key not in st.session_state.feedback_updated:
        st.session_state.feedback_updated[user_qid_key] = False
    
    # 初始化状态机（如果切换题目，重置状态）
    if "last_question_id" not in st.session_state or st.session_state.get("last_question_id") != qid:
        st.session_state.review_stage = "answering"
        st.session_state.current_result = None
        st.session_state.feedback_updated[user_qid_key] = False
        st.session_state.last_question_id = qid
    
    # 使用统一的review_stage
    current_stage = st.session_state.review_stage
    
    # 显示进度信息
    # 确保 current_index 是有效的整数（用于显示）
    display_index = current_index if (current_index is not None and isinstance(current_index, int)) else 0
    col_progress1, col_progress2 = st.columns([3, 1])
    with col_progress1:
        st.caption(f"📊 进度：{display_index + 1} / {len(due_questions)}")
    with col_progress2:
        if st.button("🗑️ 删除此题", key=f"delete_{qid}", use_container_width=True):
            archive_question(qid, archived=True, user_id=current_user_id)
            st.toast("已删除")
            # 修复：清除锁定状态，防止刷新后重新加载已删除的题目
            st.session_state.current_review_qid = None
            st.session_state.review_stage = "answering"
            st.session_state.current_result = None
            # 更新题目列表
            st.session_state.review_question_list = [q for q in st.session_state.review_question_list if q != qid]
            # 确保索引有效
            # 确保 current_index 是有效的整数
            if current_index is None or not isinstance(current_index, int):
                current_index = 0
            remaining_questions = [q for q in due_questions if q["id"] != qid]
            if current_index >= len(remaining_questions) or current_index < 0:
                st.session_state.current_question_index = max(0, len(remaining_questions) - 1)
            else:
                st.session_state.current_question_index = current_index
            st.rerun()
    
        st.markdown("---")
        
    # 使用容器隔离题目信息渲染，优化滚动性能
    question_container = st.container()
    with question_container:
        # 显示题目信息（两个阶段都显示）- 文本优先，图片折叠
        st.markdown('<div class="app-card">', unsafe_allow_html=True)
        subject = question.get("subject") or "未分类"
        correct_count = question.get('correct_count', 0)
        st.markdown(
            f"**🏷️ {subject}** ｜ ✅ 答对 {correct_count}/3 次 ｜ "
            f"📊 正确率 {question.get('accuracy', 0.0):.1f}%"
        )
        st.caption(f"下次复习：{format_next_review(question.get('next_review_time'))}")
        
        # 显示主题和知识点标签（复习页面）
        topic = question.get("topic", "")
        knowledge_points = question.get("knowledge_points", [])
        if topic or knowledge_points:
            tag_html = '<div style="margin: 8px 0; display: flex; flex-wrap: wrap; gap: 6px;">'
            if topic and topic != "未标注":
                tag_html += f'<span style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 4px 12px; border-radius: 15px; font-size: 12px; font-weight: 500;">📌 主题: {topic}</span>'
            if knowledge_points:
                for kp in knowledge_points[:5]:  # 最多显示5个知识点提示
                    tag_html += f'<span style="background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%); color: white; padding: 4px 10px; border-radius: 12px; font-size: 11px;">💡 {kp}</span>'
            tag_html += '</div>'
            st.markdown(tag_html, unsafe_allow_html=True)
        
        # 优先显示文本题目（如果有）
        question_text_clean = question.get("question_text_clean", "")
        if question_text_clean:
            st.markdown("### 📝 题目内容")
            st.markdown(format_math_text(question_text_clean), unsafe_allow_html=True)
            # 图片折叠显示
            with st.expander("🖼️ 查看原图", expanded=False):
                st.image(decode_image(question["question_image"]), caption="题目原图", use_column_width=True)
        else:
            # 如果没有文本，直接显示图片
            st.image(decode_image(question["question_image"]), caption="题目原图", use_column_width=True)

    # ========== Stage 1: 'answering' (答题阶段) ==========
    if current_stage == "answering":
        input_method = st.radio(
            "选择作答方式",
            ["📝 文本输入", "📷 上传手写答案"],
            key=f"method_{qid}",
            horizontal=True,
        )

        if qid not in st.session_state.review_inputs:
            st.session_state.review_inputs[qid] = {"text": "", "image": None}

        if input_method == "📝 文本输入":
            answer_key = f"text_answer_{qid}"
            if answer_key not in st.session_state:
                st.session_state[answer_key] = ""
            user_answer_text = st.text_area(
                "输入答案或思路",
                key=answer_key,
                placeholder="请在此记录你的详细思路（支持 LaTeX）",
                height=160,
            )
            st.session_state.review_inputs[qid]["text"] = user_answer_text
            st.session_state.review_inputs[qid]["image"] = None
            user_answer_image = None
        else:
            uploaded = st.file_uploader(
                "上传手写答案照片",
                type=["jpg", "jpeg", "png"],
                key=f"upload_{qid}",
            )
            if uploaded:
                st.session_state.review_inputs[qid]["image"] = uploaded.read()
            user_answer_image = st.session_state.review_inputs[qid]["image"]
            user_answer_text = ""
            if user_answer_image:
                st.image(user_answer_image, caption="已上传的答案", width=320)

        if st.button("提交判卷", key=f"submit_{qid}", type="primary"):
            if not user_answer_text and not user_answer_image:
                st.warning("请先输入答案或上传照片")
            else:
                st.info("🤔 AI 正在阅卷...")
                feedback_placeholder = st.empty()
                
                try:
                    # 获取题目文本
                    question_text = ""
                    if question.get("question_image"):
                        try:
                            question_text = clean_latex(ocr_extract_text(decode_image(question["question_image"])))
                        except Exception:
                            question_text = clean_latex(question.get("solution", "")[:600])
                    else:
                        question_text = clean_latex(question.get("solution", "")[:600])
                    
                    # 获取标准答案和解析
                    standard_solution = clean_latex(question.get("solution", ""))
                    
                    # 流式判卷 - 优化体验，即时显示
                    full_feedback = ""
                    for chunk in judge_answer_stream(
                        question_text,
                        standard_solution,
                        user_answer_text,
                        user_answer_image,
                    ):
                        full_feedback += chunk
                        # 即时渲染，显示光标效果
                        display_text = stream_display(full_feedback)
                        feedback_placeholder.markdown(display_text, unsafe_allow_html=True)

                    # 解析判卷结果（保守策略，默认判错）
                    is_correct, feedback_text = parse_judge_result(full_feedback)

                    # 存储判卷结果（不更新数据库，等feedback阶段再更新）
                    st.session_state.current_result = {
                        "is_correct": is_correct,
                        "feedback": clean_latex(feedback_text),
                        "user_answer": user_answer_text or (encode_image(user_answer_image) if user_answer_image else ""),
                    }
                    
                    # 关键：切换到 feedback 阶段，但不改变题目索引
                    st.session_state.review_stage = "feedback"
                    # 确保 feedback_updated 是字典
                    if not isinstance(st.session_state.feedback_updated, dict):
                        st.session_state.feedback_updated = {}
                    if user_qid_key not in st.session_state.feedback_updated:
                        st.session_state.feedback_updated[user_qid_key] = False
                    st.rerun()
                except Exception as exc:
                    st.error(f"判卷失败：{exc}")
        
        # 添加跳过/下一题按钮（在答题阶段）
        st.markdown("---")
        if st.button("➡️ 跳过 / 下一题", key=f"skip_{qid}", type="secondary"):
            # 移动到下一题
            # 确保 current_index 是有效的整数
            if current_index is None or not isinstance(current_index, int):
                current_index = 0
            if current_index < len(due_questions) - 1:
                next_index = current_index + 1
            else:
                next_index = 0
            
            # 清除当前题目的锁定
            st.session_state.current_review_qid = None
            st.session_state.current_question_index = next_index
            
            # 重置状态为 answering
            st.session_state.review_stage = "answering"
            st.session_state.current_result = None
            st.session_state.last_question_id = None
            
            st.rerun()

    # ========== Stage 2: 'feedback' (反馈与交互阶段) ==========
    elif current_stage == "feedback":
        result = st.session_state.current_result
        # 修复：如果 result 丢失（可能是 rerun 导致），尝试从持久化存储中恢复
        if not result:
            result_key = f"persisted_result_{user_qid_key}"
            if result_key in st.session_state:
                # 从持久化存储中恢复 result
                result = st.session_state[result_key]
                st.session_state.current_result = result
            elif user_qid_key in st.session_state.get("feedback_stats", {}):
                # 如果有 stats，说明之前已经判卷过，尝试从 stats 恢复部分信息
                stats = st.session_state.feedback_stats[user_qid_key]
                # 创建一个简化的 result 用于显示
                result = {
                    "is_correct": stats.get("correct_count", 0) > 0,  # 简化判断
                    "feedback": "已判卷完成",
                    "user_answer": ""
                }
                st.session_state.current_result = result
            else:
                # 如果既没有 result 也没有 stats，说明确实没有判卷结果，重置为 answering
                st.session_state.review_stage = "answering"
                st.rerun()
                return  # 提前返回，避免后续代码执行
        
        # 确保 result 存在
        if not result:
            st.session_state.review_stage = "answering"
            st.rerun()
            return
        
        st.markdown("---")
        
        # 显示判卷结果
        if result["is_correct"]:
            st.success("✅ 回答正确！记忆强度 +1")
        else:
            st.error("❌ 回答有误，10 分钟后将再次出现")
            if result["feedback"]:
                st.warning(format_math_text(clean_latex(result["feedback"])), icon="💡")
        
        # 仅在初次渲染时更新数据库（避免重复更新）
        if not st.session_state.feedback_updated[user_qid_key]:
            answer_payload = result["user_answer"]
            stats = update_question_mastery(
                qid,
                result["is_correct"],
                answer_payload,
                result["feedback"],
                user_id=current_user_id,
            )
            st.session_state.feedback_updated[user_qid_key] = True
            if "feedback_stats" not in st.session_state:
                st.session_state.feedback_stats = {}
            st.session_state.feedback_stats[user_qid_key] = stats
        
        # 显示统计信息
        if st.session_state.feedback_updated[user_qid_key] and user_qid_key in st.session_state.get("feedback_stats", {}):
            stats = st.session_state.feedback_stats[user_qid_key]
            st.metric(
                "答对次数",
                f"{stats['correct_count']}/3",
                help="答对3次即可达到掌握标准",
            )
            st.caption(
                f"下次复习：{format_next_review(stats['next_review_time'])} ｜ "
                f"间隔：{describe_interval(stats['interval_minutes'])} ｜ "
                f"累计正确率：{stats['accuracy']:.1f}%"
            )
            
            # 满级记忆归档提示（答对3次即可归档）
            if result["is_correct"] and stats["correct_count"] >= 3:
                st.success("🎉 已答对3次，达到掌握标准！是否将此题归档？")
                col_a, col_b = st.columns(2)
                if col_a.button("移入已掌握", key=f"archive_full_{qid}"):
                    # 归档题目并将知识点添加到知识图谱
                    archive_question(qid, archived=True, user_id=current_user_id)
                    
                    # 添加知识点到知识图谱
                    subject = question.get("subject", "未分类")
                    knowledge_points = question.get("knowledge_points", [])
                    if knowledge_points:
                        added = add_mastered_knowledge(current_user_id, subject, knowledge_points, qid)
                        if added > 0:
                            st.success(f"✅ 已归档！{added} 个知识点已添加到知识图谱")
                        else:
                            st.success("已归档，可在错题库查看归档题目。")
                    else:
                        st.success("已归档，可在错题库查看归档题目。")
                    st.rerun()
                if col_b.button("继续保留", key=f"keep_active_{qid}"):
                    st.info("已继续保留，15 天后再次复习。")
        
        # 交互工具区域
        st.markdown("---")
        
        # 1. 查看完整解析
        with st.expander("📘 查看完整解析 & 参考答案", expanded=False):
            solution_text = clean_latex(question.get("solution", ""))
            st.markdown(format_math_text(solution_text), unsafe_allow_html=True)
        
        # 2. AI 聊天 - 使用容器优化渲染性能
        st.markdown("### 🤖 对解析有疑问？(Chat)")
        
        # 使用容器来显示历史消息，减少重渲染
        chat_container = st.container()
        with chat_container:
            for msg in st.session_state.temp_chat_history[user_qid_key]:
                with st.chat_message(msg["role"]):
                    st.markdown(format_math_text(clean_latex(msg["content"])), unsafe_allow_html=True)
        
        user_question = st.chat_input("对解析有疑问？问问 AI...", key=f"chat_{user_qid_key}")
        if user_question:
            st.session_state.temp_chat_history[user_qid_key].append({"role": "user", "content": user_question})
            
            # 立即显示用户消息
            with chat_container:
                with st.chat_message("user"):
                    st.markdown(user_question)
                
                with st.chat_message("assistant"):
                    question_text = ""
                    if question.get("question_image"):
                        try:
                            question_text = clean_latex(ocr_extract_text(decode_image(question["question_image"])))
                        except Exception:
                            question_text = clean_latex(question.get("solution", "")[:500])
                    else:
                        question_text = clean_latex(question.get("solution", "")[:500])
                    
                    review_history = get_review_logs(qid, user_id=current_user_id)
                    response_placeholder = st.empty()
                    full_response = ""
                    for chunk in chat_with_ai_stream(
                        question_text,
                        clean_latex(question.get("solution", "")),
                        question.get("knowledge_points", []),
                        review_history,
                        user_question
                    ):
                        full_response += chunk
                        # 每5个字符更新一次显示，减少渲染次数
                        if len(full_response) % 5 == 0 or chunk == "":
                            response_placeholder.markdown(stream_display(full_response), unsafe_allow_html=True)

                    # 最终显示完整内容
                    response_placeholder.markdown(format_math_text(clean_latex(full_response)), unsafe_allow_html=True)
                    st.session_state.temp_chat_history[user_qid_key].append({"role": "assistant", "content": full_response})
        
        # 3. 生成同类题
        st.markdown("---")
        if st.button("🔄 生成同类题", key=f"similar_{user_qid_key}"):
            with st.spinner("AI 正在努力生成新题目，请稍候..."):
                question_text = ""
                if question.get("question_image"):
                    try:
                        question_text = clean_latex(ocr_extract_text(decode_image(question["question_image"])))
                    except Exception:
                        question_text = clean_latex(question.get("solution", "")[:500])
                else:
                    question_text = clean_latex(question.get("solution", "")[:500])
                
                knowledge_points = question.get("knowledge_points", [])
                if not knowledge_points:
                    knowledge_points = ["通用练习"]
                
                # 全量接收流式输出
                full_similar_raw = ""
                for chunk in generate_similar_question_stream(question_text, knowledge_points):
                    full_similar_raw += chunk
                
                # 统一清洗 JSON
                json_text = clean_json_text(full_similar_raw)

                # 安全解析 JSON
                try:
                    # 尝试解析 JSON
                    parsed_json = json.loads(json_text)
                    
                    # 验证必要字段
                    if not isinstance(parsed_json, dict):
                        raise ValueError("不是有效的 JSON 对象")
                    
                    # 对所有字段应用 clean_latex 处理后存储
                    cleaned_data = {
                        "question": clean_latex(parsed_json.get("question", "")),
                        "solution": clean_latex(parsed_json.get("solution", "")),
                        "answer": clean_latex(parsed_json.get("answer", ""))
                    }
                    
                    # 验证题目不为空
                    if not cleaned_data["question"]:
                        raise ValueError("题目内容为空")
                    
                    st.session_state.temp_similar_data[user_qid_key] = cleaned_data
                    
                    # 存储清洗后的题目文本（只存储题目，不显示解析和答案）
                    st.session_state.temp_similar_q[user_qid_key] = cleaned_data["question"]
                except (json.JSONDecodeError, ValueError, KeyError) as e:
                    # 如果解析失败，显示错误并清空状态
                    st.error(f"生成同类题失败：无法解析 AI 返回的内容。错误：{str(e)}")
                    st.session_state.temp_similar_data[user_qid_key] = None
                    st.session_state.temp_similar_q[user_qid_key] = None
                
                st.session_state.similar_expander_expanded[user_qid_key] = True
                # 修复：生成同类题后保持当前状态，防止界面消失
                # 关键修复：如果当前在 feedback 阶段，需要确保 current_result 在 rerun 后不丢失
                if current_stage == "feedback" and st.session_state.current_result:
                    # 保存 current_result 到临时变量，rerun 后恢复
                    # 由于 last_question_id == qid，review_stage 不会重置
                    # 但 current_result 可能会丢失，所以需要从 stats 恢复
                    if user_qid_key in st.session_state.get("feedback_stats", {}):
                        # 从 stats 中恢复 result（部分信息）
                        stats = st.session_state.feedback_stats[user_qid_key]
                        # 创建一个简化的 result 用于显示
                        saved_result = st.session_state.current_result.copy()
                        # 保存到 session_state 的持久化存储中
                        result_key = f"persisted_result_{user_qid_key}"
                        st.session_state[result_key] = saved_result
                # 必须调用 st.rerun() 才能显示新生成的同类题
                st.rerun()
        
        # 显示同类题（如果有）- 使用 expander 保持展开状态
        if st.session_state.temp_similar_q[user_qid_key]:
            with st.expander("🔄 同类题练习", expanded=st.session_state.similar_expander_expanded[user_qid_key]):
                st.markdown(format_math_text(clean_latex(st.session_state.temp_similar_q[user_qid_key])), unsafe_allow_html=True)
                st.caption("💡 这是临时练习题，不会存入错题库")
                
                # 同类题答题区域
                similar_answer_key = f"similar_answer_{user_qid_key}"
                if similar_answer_key not in st.session_state:
                    st.session_state[similar_answer_key] = ""
                
                similar_user_answer = st.text_area(
                    "输入你的答案",
                    key=similar_answer_key,
                    placeholder="请在此输入你的答案或思路",
                    height=120,
                )
                
                # 同类题判卷按钮
                if st.button("提交判卷（同类题）", key=f"judge_similar_{user_qid_key}", type="primary"):
                    if not similar_user_answer:
                        st.warning("请先输入答案")
                    else:
                        st.info("🤔 AI 正在阅卷...")
                        feedback_placeholder = st.empty()
                        
                        try:
                            # 修复：使用同类题的答案进行判卷，而不是解析
                            if (st.session_state.temp_similar_data[user_qid_key] and 
                                isinstance(st.session_state.temp_similar_data[user_qid_key], dict)):
                                # 优先使用同类题的答案，如果没有答案则使用解析
                                similar_answer = st.session_state.temp_similar_data[user_qid_key].get("answer", "")
                                similar_solution = st.session_state.temp_similar_data[user_qid_key].get("solution", "")
                                
                                # 构建标准答案：优先使用 answer 字段，如果没有则从 solution 中提取
                                if similar_answer:
                                    # 如果有明确的答案字段，使用答案+解析的组合
                                    standard_for_judge = f"答案：{clean_latex(similar_answer)}\n\n解析：{clean_latex(similar_solution)}"
                                else:
                                    # 如果没有答案字段，使用解析（判卷函数会从中提取答案）
                                    standard_for_judge = clean_latex(similar_solution)
                            else:
                                # 回退：如果没有同类题数据，使用原题解析
                                standard_for_judge = clean_latex(question.get("solution", ""))
                            
                            # 流式判卷 - 优化体验
                            full_feedback = ""
                            for chunk in judge_answer_stream(
                                clean_latex(st.session_state.temp_similar_q[user_qid_key]),
                                standard_for_judge,
                                similar_user_answer,
                                None,
                            ):
                                full_feedback += chunk
                                # 即时渲染，显示光标效果
                                display_text = stream_display(full_feedback)
                                feedback_placeholder.markdown(display_text, unsafe_allow_html=True)

                            # 解析判卷结果（保守策略，默认判错）
                            is_correct, feedback_text = parse_judge_result(full_feedback)

                            # 存储同类题判卷结果
                            st.session_state.temp_similar_result[user_qid_key] = {
                                "is_correct": is_correct,
                                "feedback": clean_latex(feedback_text),
                                "user_answer": similar_user_answer,
                            }
                            st.session_state.temp_similar_answer[user_qid_key] = similar_user_answer
                            st.session_state.similar_expander_expanded[user_qid_key] = True
                            st.rerun()
                        except Exception as exc:
                            st.error(f"判卷失败：{exc}")
                
                # 显示同类题判卷结果
                if st.session_state.temp_similar_result[user_qid_key]:
                    st.markdown("---")
                    similar_result = st.session_state.temp_similar_result[user_qid_key]
                    if similar_result["is_correct"]:
                        st.success("✅ 回答正确！")
                    else:
                        st.error("❌ 回答有误")
                        if similar_result["feedback"]:
                            st.warning(format_math_text(clean_latex(similar_result["feedback"])), icon="💡")
                    
                    # 显示同类题的完整解析（如果有）- 修复嵌套 expander 问题，使用 toggle 避免 rerun
                    if (st.session_state.temp_similar_data[user_qid_key] and 
                        isinstance(st.session_state.temp_similar_data[user_qid_key], dict) and
                        st.session_state.temp_similar_data[user_qid_key].get("solution")):
                        # 使用 toggle 控制显示/隐藏，避免嵌套 expander 和减少 rerun
                        show_solution_key = f"show_similar_solution_{user_qid_key}"
                        if show_solution_key not in st.session_state:
                            st.session_state[show_solution_key] = False
                        
                        # 使用 toggle 而不是 button，减少 rerun
                        st.session_state[show_solution_key] = st.toggle(
                            "📘 查看同类题完整解析",
                            value=st.session_state[show_solution_key],
                            key=f"toggle_solution_{user_qid_key}"
                        )
                        
                        if st.session_state[show_solution_key]:
                            st.markdown("---")
                            st.markdown("### 📘 同类题完整解析")
                            st.markdown(format_math_text(st.session_state.temp_similar_data[user_qid_key]["solution"]), unsafe_allow_html=True)
                            if st.session_state.temp_similar_data[user_qid_key].get("answer"):
                                st.info(f"**答案：** {format_math_text(st.session_state.temp_similar_data[user_qid_key]['answer'])}", icon="🧾")
                    
                    # 同类题的AI交互 - 优化渲染性能
                    st.markdown("### 🤖 对同类题解析有疑问？(Chat)")
                    
                    similar_chat_container = st.container()
                    with similar_chat_container:
                        for msg in st.session_state.temp_similar_chat_history[user_qid_key]:
                            with st.chat_message(msg["role"]):
                                st.markdown(format_math_text(clean_latex(msg["content"])), unsafe_allow_html=True)
                    
                    similar_user_question = st.chat_input("对同类题解析有疑问？问问 AI...", key=f"chat_similar_{user_qid_key}")
                    if similar_user_question:
                        st.session_state.temp_similar_chat_history[user_qid_key].append({"role": "user", "content": similar_user_question})
                        
                        with similar_chat_container:
                            with st.chat_message("user"):
                                st.markdown(similar_user_question)
                            
                            with st.chat_message("assistant"):
                                response_placeholder = st.empty()
                                full_response = ""
                                
                                # 获取同类题的解析（优先使用同类题自己的解析）
                                similar_solution = ""
                                if (st.session_state.temp_similar_data[user_qid_key] and 
                                    isinstance(st.session_state.temp_similar_data[user_qid_key], dict) and
                                    "solution" in st.session_state.temp_similar_data[user_qid_key]):
                                    similar_solution = clean_latex(st.session_state.temp_similar_data[user_qid_key]["solution"])
                                else:
                                    similar_solution = clean_latex(question.get("solution", ""))
                                
                                for chunk in qa_assistant_stream(
                                    clean_latex(st.session_state.temp_similar_q[user_qid_key]),
                                    similar_solution,
                                    similar_user_question
                                ):
                                    full_response += chunk
                                    # 每5个字符更新一次显示，减少渲染次数
                                    if len(full_response) % 5 == 0 or chunk == "":
                                        response_placeholder.markdown(stream_display(full_response), unsafe_allow_html=True)

                                # 最终显示完整内容
                                response_placeholder.markdown(format_math_text(clean_latex(full_response)), unsafe_allow_html=True)
                                st.session_state.temp_similar_chat_history[user_qid_key].append({"role": "assistant", "content": full_response})
        
        # 导航：下一题按钮
        st.markdown("---")
        if st.button("➡️ 下一题", key=f"next_{qid}", type="primary"):
            # 移动到下一题
            # 确保 current_index 是有效的整数
            if current_index is None or not isinstance(current_index, int):
                current_index = 0
            if current_index < len(due_questions) - 1:
                next_index = current_index + 1
            else:
                next_index = 0
            
            # 清除当前题目的锁定
            st.session_state.current_review_qid = None
            st.session_state.current_question_index = next_index
            
            # 重置状态为 answering
            st.session_state.review_stage = "answering"
            st.session_state.current_result = None
            st.session_state.last_question_id = None
            
            # 注意：不清空临时数据，保留在当前 qid 下，这样如果用户返回还能看到
            st.rerun()
    
    st.markdown("</div>", unsafe_allow_html=True)


# ==================== 知识图谱 ====================
def render_knowledge_graph() -> None:
    """渲染知识图谱页面 - 展示已掌握和待掌握的知识点（增强版：带进度追踪和关联错题查看）"""
    # 注意：标题已在主程序入口显示，这里不再重复显示
    import hashlib  # 用于生成唯一的按钮 key
    import time
    
    # ========== 关键修复：强制清理所有可能冲突的状态 ==========
    # 在函数最开始就清理，确保不会有任何状态冲突
    # 检查是否是从复习模式切换过来的
    is_from_review = (
        st.session_state.get("current_review_qid") is not None or
        st.session_state.get("review_stage") != "answering" or
        st.session_state.get("last_question_id") is not None
    )
    
    if is_from_review:
        # 强制清理所有复习模式相关的状态
        review_state_keys = [
            "current_review_qid",
            "review_stage", 
            "last_question_id",
            "current_result",
            "current_question_index",
            "review_question_list"
        ]
        for key in review_state_keys:
            if key in st.session_state:
                if key == "review_stage":
                    st.session_state[key] = "answering"
                elif key == "review_question_list":
                    st.session_state[key] = []
                else:
                    st.session_state[key] = None
        
        # 添加一个标记，表示已经清理过状态
        st.session_state._kg_initialized = True
    
    st.caption("追踪各学科知识点掌握情况 | 复习完成后自动更新 | 点击知识点查看相关错题")
    
    # 添加调试信息
    debug_mode = False  # 可以设置为 True 来查看调试信息
    
    try:
        if debug_mode:
            st.write("🔍 调试：开始执行知识图谱函数")
        
        # 初始化选中的知识点状态（用于显示关联错题）
        if "selected_knowledge_point" not in st.session_state:
            st.session_state.selected_knowledge_point = None
        if "selected_knowledge_subject" not in st.session_state:
            st.session_state.selected_knowledge_subject = None
        
        # 初始化选中的知识点状态（用于显示关联错题）
        if "selected_knowledge_point" not in st.session_state:
            st.session_state.selected_knowledge_point = None
        if "selected_knowledge_subject" not in st.session_state:
            st.session_state.selected_knowledge_subject = None
        
        # 获取当前用户 ID
        current_user_id = st.session_state.get("user_id")
        if not current_user_id:
            st.warning("请先登录")
            return

        # 显示加载指示器（性能优化：先显示简单内容）
        loading_placeholder = st.empty()
        with loading_placeholder.container():
            st.info("🔄 正在加载知识图谱数据...")
        
        # 获取知识点统计（添加异常处理）
        if debug_mode:
            st.write("🔍 调试：准备获取知识点统计")
        
        try:
            stats = get_knowledge_stats_by_subject(current_user_id)
            if debug_mode:
                st.write(f"🔍 调试：获取到统计数据，类型: {type(stats)}, 长度: {len(stats) if isinstance(stats, dict) else 'N/A'}")
            
            # 确保 stats 是字典类型
            if not isinstance(stats, dict):
                loading_placeholder.empty()
                st.error(f"❌ 获取知识点统计返回的数据类型错误: {type(stats)}")
                st.info("💡 提示：返回的数据不是字典类型，可能是数据库查询出现问题")
                return
            # 如果 stats 为空字典，也要处理
            if not stats:
                loading_placeholder.empty()
                st.info("📚 暂无知识点数据。开始使用错题本后，知识图谱将自动更新！")
                st.markdown("""
                ### 如何使用知识图谱？
                1. 📷 **上传错题** - 系统会自动提取知识点
                2. 🔄 **复习错题** - 完成复习后标记掌握程度
                3. ✅ **归档题目** - 当题目达到满级记忆时，相关知识点会标记为"已掌握"
                4. 🧠 **查看图谱** - 在这里查看各学科的知识点掌握情况
                """)
                return
            
            # 清除加载指示器
            loading_placeholder.empty()
        except Exception as e:
            loading_placeholder.empty()
            st.error(friendly_error(e))
            st.info("💡 提示：可能是数据加载异常，请稍后重试")
            return
        # 按学科展示知识图谱
        st.markdown("### 📊 各学科知识图谱")
        
        if debug_mode:
            st.write("🔍 调试：准备创建学科标签页")
        
        # 使用 tabs 按学科分类（过滤掉 None 和空字符串）
        try:
            subject_names = [s for s in stats.keys() if s and isinstance(s, str)]
            if debug_mode:
                st.write(f"🔍 调试：找到 {len(subject_names)} 个学科")
            
            if not subject_names:
                st.warning("⚠️ 学科数据异常，无法显示知识图谱")
                return
            
            # 确保 stats 只包含有效的学科数据，并按照 subject_names 的顺序排列
            valid_stats = {}
            for name in subject_names:
                if name in stats:
                    subject_data = stats[name]
                    # 确保每个学科的数据是字典类型
                    if isinstance(subject_data, dict):
                        valid_stats[name] = subject_data
            
            if not valid_stats:
                st.warning("⚠️ 没有有效的学科数据")
                return
            
            # 限制标签页数量，防止界面崩溃和卡顿
            MAX_TABS = 15  # 减少到15个，提高性能
            if len(subject_names) > MAX_TABS:
                st.warning(f"⚠️ 学科数量较多（{len(subject_names)} 个），仅显示前 {MAX_TABS} 个学科")
                subject_names = subject_names[:MAX_TABS]
                # 只保留前MAX_TABS个学科的数据
                valid_stats = {k: valid_stats[k] for k in subject_names if k in valid_stats}
            
            if debug_mode:
                st.write(f"🔍 调试：准备创建 {len(subject_names)} 个标签页")
            
            # 再次确保状态已清理（双重保险）
            if st.session_state.get("current_review_qid") is not None:
                st.session_state.current_review_qid = None
            if st.session_state.get("review_stage") != "answering":
                st.session_state.review_stage = "answering"
            
            try:
                # 直接创建标签页（st.tabs 必须在顶层调用）
                subject_tabs = st.tabs(subject_names)
                if debug_mode:
                    st.write(f"🔍 调试：成功创建 {len(subject_tabs)} 个标签页")
            except Exception as tabs_error:
                st.error(f"❌ 创建标签页失败: {str(tabs_error)}")
                import traceback
                with st.expander("查看错误详情", expanded=True):
                    st.code(traceback.format_exc())
                st.info("💡 提示：学科数量可能过多，请尝试归档部分错题")
                st.button("🔄 重试", key="retry_tabs", on_click=lambda: st.rerun())
                return
            
            # 确保顺序一致：subject_tabs 和 subject_names 一一对应
            for idx, tab in enumerate(subject_tabs):
                if idx >= len(subject_names):
                    break
                subject = subject_names[idx]
                if subject not in valid_stats:
                    continue
                data = valid_stats[subject]
                
                # 确保 data 是字典类型
                if not isinstance(data, dict):
                    if debug_mode:
                        st.write(f"🔍 调试：学科 {subject} 的数据不是字典类型，跳过")
                    continue
                
                if debug_mode:
                    st.write(f"🔍 调试：处理学科 {subject}")
                
                with tab:
                    try:
                        # 学科统计（更新为新的数据结构）
                        col1, col2, col3, col4 = st.columns(4)
                        mastered_count = data.get("mastered", 0) or 0
                        partial_count = data.get("partial", 0) or 0
                        pending_count = data.get("pending", 0) or 0
                        
                        # 确保是数字类型
                        try:
                            mastered_count = int(mastered_count) if mastered_count else 0
                            partial_count = int(partial_count) if partial_count else 0
                            pending_count = int(pending_count) if pending_count else 0
                        except (ValueError, TypeError):
                            mastered_count = 0
                            partial_count = 0
                            pending_count = 0
                        
                        col1.metric("✅ 已掌握", mastered_count)
                        col2.metric("🟡 部分掌握", partial_count)
                        col3.metric("⏳ 待掌握", pending_count)
                        total_kp = mastered_count + partial_count + pending_count
                        subject_rate = ((mastered_count + partial_count * 0.5) / total_kp * 100) if total_kp > 0 else 0
                        col4.metric("📈 掌握率", str(round(subject_rate, 1)) + "%")
                        
                        # 进度条
                        st.progress(min(max(subject_rate / 100, 0), 1))  # 确保在 0-1 范围内
                        
                        # 知识点掌握度可视化（环形图）
                        if total_kp > 0:
                            try:
                                import plotly.graph_objects as go
                                
                                # 准备数据，过滤掉值为0的项以避免标签重叠
                                labels = []
                                values = []
                                colors_list = []
                                
                                if mastered_count > 0:
                                    labels.append('✅ 已掌握')
                                    values.append(mastered_count)
                                    colors_list.append('#10b981')
                                
                                if partial_count > 0:
                                    labels.append('🟡 部分掌握')
                                    values.append(partial_count)
                                    colors_list.append('#f59e0b')
                                
                                if pending_count > 0:
                                    labels.append('⏳ 待掌握')
                                    values.append(pending_count)
                                    colors_list.append('#6b7280')
                                
                                # 如果所有值都是0，显示提示信息
                                if not labels:
                                    st.info("暂无知识点数据")
                                else:
                                    # 创建环形图展示掌握度分布
                                    fig = go.Figure(data=[
                                        go.Pie(
                                            labels=labels,
                                            values=values,
                                            hole=0.5,  # 环形图
                                            marker=dict(
                                                colors=colors_list,
                                                line=dict(color='#FFFFFF', width=2)
                                            ),
                                            textinfo='label+percent',
                                            textposition='auto',  # 自动调整位置，避免重叠
                                            insidetextorientation='radial',  # 内部文本径向排列
                                            hovertemplate='<b>%{label}</b><br>数量: %{value}<br>占比: %{percent}<extra></extra>',
                                            # 优化文本显示：只在足够大的扇形上显示标签
                                            texttemplate='%{label}<br>%{percent}<br>(%{value})',
                                            textfont=dict(size=12)
                                        )
                                    ])
                                    
                                    fig.update_layout(
                                        title=dict(
                                            text=f'📊 {subject} 知识点掌握度分布',
                                            font=dict(size=16),
                                            x=0.5,
                                            xanchor='center'
                                        ),
                                        showlegend=True,
                                        legend=dict(
                                            orientation="h",
                                            yanchor="bottom",
                                            y=-0.1,  # 移到图表下方
                                            xanchor="center",
                                            x=0.5
                                        ),
                                        margin=dict(l=40, r=40, t=60, b=80),  # 增加底部边距给图例留空间
                                        height=400,
                                        # 优化文本布局，避免重叠
                                        annotations=[dict(text=f'总计: {total_kp}', 
                                                         x=0.5, y=0.5, 
                                                         font_size=14, 
                                                         showarrow=False)]
                                    )
                                    
                                    st.plotly_chart(fig, use_container_width=True)
                            except Exception as e:
                                # 如果图表生成失败，不影响其他功能
                                pass
                        
                        st.markdown("---")
                        
                        # 知识点列表（按状态分组显示，带进度信息）
                        knowledge_points = data.get("knowledge_points", [])
                        if not isinstance(knowledge_points, list):
                            knowledge_points = []
                        
                        # 过滤掉无效的知识点数据（性能优化：使用列表推导式）
                        valid_knowledge_points = [kp for kp in knowledge_points if isinstance(kp, dict) and kp.get("name")]
                        knowledge_points = valid_knowledge_points
                        
                        # 性能优化：限制每个状态显示的知识点数量，防止渲染过多导致卡顿
                        MAX_KP_PER_STATUS = 100  # 每个状态最多显示100个知识点
                        
                        if knowledge_points:
                            # 按状态分组（添加安全检查）
                            mastered_kps = [kp for kp in knowledge_points if isinstance(kp, dict) and kp.get("status") == "mastered"]
                            partial_kps = [kp for kp in knowledge_points if isinstance(kp, dict) and kp.get("status") == "partial"]
                            pending_kps = [kp for kp in knowledge_points if isinstance(kp, dict) and kp.get("status") == "pending"]
                            
                            # 限制数量，防止渲染过多
                            if len(mastered_kps) > MAX_KP_PER_STATUS:
                                mastered_kps = mastered_kps[:MAX_KP_PER_STATUS]
                                st.info(f"📋 已掌握知识点较多（共 {len([kp for kp in knowledge_points if isinstance(kp, dict) and kp.get('status') == 'mastered'])} 个），仅显示前 {MAX_KP_PER_STATUS} 个")
                            if len(partial_kps) > MAX_KP_PER_STATUS:
                                partial_kps = partial_kps[:MAX_KP_PER_STATUS]
                                st.info(f"📋 部分掌握知识点较多（共 {len([kp for kp in knowledge_points if isinstance(kp, dict) and kp.get('status') == 'partial'])} 个），仅显示前 {MAX_KP_PER_STATUS} 个")
                            if len(pending_kps) > MAX_KP_PER_STATUS:
                                pending_kps = pending_kps[:MAX_KP_PER_STATUS]
                                st.info(f"📋 待掌握知识点较多（共 {len([kp for kp in knowledge_points if isinstance(kp, dict) and kp.get('status') == 'pending'])} 个），仅显示前 {MAX_KP_PER_STATUS} 个")
                            
                            if debug_mode:
                                st.write(f"🔍 调试：已掌握 {len(mastered_kps)}, 部分掌握 {len(partial_kps)}, 待掌握 {len(pending_kps)}")
                            
                            # 已掌握知识点（绿色，显示 3/3，可点击查看相关错题）
                            if mastered_kps:
                                st.markdown("#### ✅ 已掌握的知识点")
                                # 使用列布局显示知识点按钮
                                cols_per_row = 4
                                for i in range(0, len(mastered_kps), cols_per_row):
                                    cols = st.columns(cols_per_row)
                                    for j, kp_info in enumerate(mastered_kps[i:i+cols_per_row]):
                                        with cols[j]:
                                            try:
                                                kp_name = kp_info.get("name", "未知知识点") or "未知知识点"
                                                # 清理知识点名称，移除可能导致问题的字符
                                                kp_name_clean = str(kp_name).strip()[:50]  # 限制长度
                                                avg_correct = kp_info.get("avg_correct", 0)
                                                # 安全转换为 int
                                                try:
                                                    correct_count = int(float(avg_correct)) if avg_correct is not None else 0
                                                except (ValueError, TypeError):
                                                    correct_count = 0
                                                question_count = kp_info.get("question_count", 0) or 0
                                                # 使用更安全的 key 生成方式
                                                kp_hash = hashlib.md5(f"{subject}_{kp_name_clean}_{i}_{j}".encode()).hexdigest()[:8]
                                                button_key = f"kp_btn_mastered_{kp_hash}"
                                                
                                                if st.button(
                                                    f"✓ {kp_name_clean}\n({correct_count}/3)",
                                                    key=button_key,
                                                    use_container_width=True,
                                                    help=f"相关题目: {question_count} 道"
                                                ):
                                                    st.session_state.selected_knowledge_point = kp_name_clean
                                                    st.session_state.selected_knowledge_subject = subject
                                                    st.rerun()
                                            except Exception as e:
                                                st.error(f"显示知识点时出错: {str(e)}")
                                                continue
                        
                            # 部分掌握知识点（黄色，显示 X/3，可点击查看相关错题）
                            if partial_kps:
                                st.markdown("#### 🟡 部分掌握的知识点")
                                cols_per_row = 4
                                for i in range(0, len(partial_kps), cols_per_row):
                                    cols = st.columns(cols_per_row)
                                    for j, kp_info in enumerate(partial_kps[i:i+cols_per_row]):
                                        with cols[j]:
                                            try:
                                                kp_name = kp_info.get("name", "未知知识点") or "未知知识点"
                                                # 清理知识点名称
                                                kp_name_clean = str(kp_name).strip()[:50]
                                                avg_correct = kp_info.get("avg_correct", 0)
                                                try:
                                                    correct_count = int(float(avg_correct)) if avg_correct is not None else 0
                                                except (ValueError, TypeError):
                                                    correct_count = 0
                                                question_count = kp_info.get("question_count", 0) or 0
                                                # 使用更安全的 key 生成方式
                                                kp_hash = hashlib.md5(f"{subject}_{kp_name_clean}_{i}_{j}".encode()).hexdigest()[:8]
                                                button_key = f"kp_btn_partial_{kp_hash}"
                                                
                                                if st.button(
                                                    f"◐ {kp_name_clean}\n({correct_count}/3)",
                                                    key=button_key,
                                                    use_container_width=True,
                                                    help=f"相关题目: {question_count} 道"
                                                ):
                                                    st.session_state.selected_knowledge_point = kp_name_clean
                                                    st.session_state.selected_knowledge_subject = subject
                                                    st.rerun()
                                            except Exception as e:
                                                st.error(f"显示知识点时出错: {str(e)}")
                                                continue
                        
                            # 待掌握知识点（橙色，显示 0/3，可点击查看相关错题）
                            if pending_kps:
                                st.markdown("#### ⏳ 待掌握的知识点")
                                cols_per_row = 4
                                for i in range(0, len(pending_kps), cols_per_row):
                                    cols = st.columns(cols_per_row)
                                    for j, kp_info in enumerate(pending_kps[i:i+cols_per_row]):
                                        with cols[j]:
                                            try:
                                                kp_name = kp_info.get("name", "未知知识点") or "未知知识点"
                                                # 清理知识点名称
                                                kp_name_clean = str(kp_name).strip()[:50]
                                                avg_correct = kp_info.get("avg_correct", 0)
                                                try:
                                                    correct_count = int(float(avg_correct)) if avg_correct is not None else 0
                                                except (ValueError, TypeError):
                                                    correct_count = 0
                                                question_count = kp_info.get("question_count", 0) or 0
                                                # 使用更安全的 key 生成方式
                                                kp_hash = hashlib.md5(f"{subject}_{kp_name_clean}_{i}_{j}".encode()).hexdigest()[:8]
                                                button_key = f"kp_btn_pending_{kp_hash}"
                                                
                                                if st.button(
                                                    f"○ {kp_name_clean}\n({correct_count}/3)",
                                                    key=button_key,
                                                    use_container_width=True,
                                                    help=f"相关题目: {question_count} 道"
                                                ):
                                                    st.session_state.selected_knowledge_point = kp_name_clean
                                                    st.session_state.selected_knowledge_subject = subject
                                                    st.rerun()
                                            except Exception as e:
                                                st.error(f"显示知识点时出错: {str(e)}")
                                                continue
                        else:
                            st.info(f"该学科暂无知识点数据")
                    except Exception as e:
                        st.error(f"渲染学科「{subject}」时出错: {str(e)}")
                        import traceback
                        st.code(traceback.format_exc())
                        # continue 在循环内，继续处理下一个学科
                        continue
        except Exception as e:
            st.error(f"❌ 处理学科数据时出错: {str(e)}")
            import traceback
            with st.expander("查看错误详情", expanded=True):
                st.code(traceback.format_exc())
            return
        
        # 显示选中的知识点关联的错题（功能1：关联错题查看）
        if debug_mode:
            st.write(f"🔍 调试：检查选中的知识点 - {st.session_state.selected_knowledge_point}")
        
        if st.session_state.selected_knowledge_point and st.session_state.selected_knowledge_subject:
            st.markdown("---")
            kp_name = st.session_state.selected_knowledge_point
            kp_subject = st.session_state.selected_knowledge_subject
            
            if debug_mode:
                st.write(f"🔍 调试：显示知识点 {kp_name} 的相关错题")
            
            try:
                with st.expander(f"📚 知识点「{kp_name}」的相关错题", expanded=True):
                    # 获取相关错题（添加异常处理）
                    try:
                        related_questions = get_questions_by_knowledge_point(kp_name, user_id=current_user_id)
                        # 确保返回的是列表
                        if not isinstance(related_questions, list):
                            related_questions = []
                    except Exception as e:
                        st.error(f"❌ 获取相关错题时出错: {str(e)}")
                        related_questions = []
                    
                    if related_questions:
                        # 性能优化：限制显示的错题数量，防止渲染过多导致卡顿
                        MAX_RELATED_QUESTIONS = 50  # 最多显示50道相关错题
                        display_questions = related_questions[:MAX_RELATED_QUESTIONS]
                        total_count = len(related_questions)
                        
                        if total_count > MAX_RELATED_QUESTIONS:
                            st.info(f"共找到 {total_count} 道相关错题，仅显示前 {MAX_RELATED_QUESTIONS} 道")
                        else:
                            st.info(f"共找到 {total_count} 道相关错题")
                        
                        for idx, question in enumerate(display_questions):
                            try:
                                with st.container():
                                    st.markdown('<div class="app-card">', unsafe_allow_html=True)
                                    q_subject = question.get("subject") or "未分类"
                                    correct_count = question.get("correct_count", 0) or 0
                                    question_id = question.get("id")
                                    
                                    # 安全检查：确保 question_id 存在
                                    if not question_id:
                                        continue
                                    
                                    st.markdown(f"#### 🏷️ {q_subject} | ID #{question_id}")
                                    st.caption(
                                        f"✅ 答对 {correct_count}/3 次 ｜ "
                                        f"📊 正确率 {question.get('accuracy', 0.0):.1f}% ｜ "
                                        f"⏱️ 下次复习 {format_next_review(question.get('next_review_time'))}"
                                    )
                                    
                                    # 显示题目文本（如果有）
                                    question_text_clean = question.get("question_text_clean", "")
                                    if question_text_clean:
                                        st.markdown("**📝 题目内容：**")
                                        st.markdown(format_math_text(question_text_clean), unsafe_allow_html=True)
                                    
                                    # 操作按钮
                                    col1, col2 = st.columns(2)
                                    if col1.button("去复习", key=f"go_review_kp_{question_id}_{idx}"):
                                        st.session_state.focus_question_id = question_id
                                        st.session_state.current_page = "🔄 沉浸式复习"
                                        st.session_state.selected_knowledge_point = None
                                        st.session_state.selected_knowledge_subject = None
                                        st.rerun()
                                    if col2.button("查看详情", key=f"view_kp_{question_id}_{idx}"):
                                        st.session_state.focus_question_id = question_id
                                        st.session_state.current_page = "🗂️ 错题库"
                                        st.session_state.selected_knowledge_point = None
                                        st.session_state.selected_knowledge_subject = None
                                        st.rerun()
                                    
                                    st.markdown("</div>", unsafe_allow_html=True)
                                    if idx < len(display_questions) - 1:
                                        st.markdown("---")
                            except Exception as e:
                                st.error(f"显示错题时出错: {str(e)}")
                                continue
                    else:
                        st.warning(f"暂无包含「{kp_name}」知识点的错题")
                    
                    # 关闭按钮
                    if st.button("关闭", key="close_kp_view"):
                        st.session_state.selected_knowledge_point = None
                        st.session_state.selected_knowledge_subject = None
                        st.rerun()
            except Exception as expander_error:
                st.error(f"❌ 显示知识点相关错题时出错: {str(expander_error)}")
                import traceback
                with st.expander("查看错误详情", expanded=True):
                    st.code(traceback.format_exc())
        
        # 知识图谱可视化（使用 Plotly）
        st.markdown("---")
        # 已删除雷达图，改为在每个学科tab中显示知识点掌握度环形图（更直观、更实用）
        
        if debug_mode:
            st.write("🔍 调试：知识图谱函数执行完成")
            
    except Exception as e:
        # 如果整个函数执行过程中出现未捕获的异常，显示错误信息
        st.error(f"❌ 知识图谱渲染过程中出现未预期的错误: {str(e)}")
        import traceback
        with st.expander("查看完整错误堆栈", expanded=True):
            st.code(traceback.format_exc())
        st.warning("💡 如果问题持续存在，请尝试刷新页面或联系技术支持")


# ==================== 学习统计 ====================
def render_learning_stats() -> None:
    st.title("📊 学习统计")
    st.caption("实时追踪错题体量、记忆强度与未来复习负荷")

    # 获取当前用户 ID（多用户数据隔离）
    current_user_id = st.session_state.get("user_id")
    questions = get_all_questions(user_id=current_user_id)
    active_questions = [q for q in questions if q.get("archived", 0) == 0]

    total_questions = len(active_questions)
    total_reviews = sum(q.get("review_count", 0) for q in questions)
    # 计算平均答对次数（与记忆曲线逻辑一致：答对3次达到掌握）
    avg_correct_count = (sum(q.get("correct_count", 0) for q in active_questions) / total_questions) if total_questions else 0
    avg_correct_count = round(avg_correct_count)  # 四舍五入到整数

    kpi_cols = st.columns(3)
    kpi_cols[0].metric("活跃错题", total_questions)
    kpi_cols[1].metric("累计复习次数", total_reviews)
    kpi_cols[2].metric("平均答对次数", f"{avg_correct_count}/3 次")

    # 今日任务与已完成
    today = datetime.now()
    today_due = [
        q for q in active_questions
        if parse_iso_datetime(q.get("next_review_time")) and parse_iso_datetime(q.get("next_review_time")) <= today
    ]
    today_due_count = len(today_due)
    today_completed = 0
    for q in today_due:
        for log in get_review_logs(q["id"], user_id=current_user_id):
            review_dt = parse_iso_datetime(log.get("review_time"))
            if review_dt and review_dt.date() == today.date():
                today_completed += 1
                break

    st.markdown("### 📌 今日任务")
    progress = today_completed / today_due_count if today_due_count else 1
    st.progress(progress)
    st.caption(f"今日需复习 {today_due_count} 题，已完成 {today_completed} 题")

    st.markdown("### 📈 复习负荷预测（未来 14 天）")
    forecast: Dict[str, int] = {}
    horizon = today + timedelta(days=14)
    for q in active_questions:
        next_time = parse_iso_datetime(q.get("next_review_time"))
        if next_time and today.date() <= next_time.date() <= horizon.date():
            # 只使用年月日格式
            key = next_time.strftime("%Y-%m-%d")
            forecast[key] = forecast.get(key, 0) + 1

    if forecast:
        # 按日期排序
        ordered_keys = sorted(forecast.keys())
        # 格式化显示标签（只显示月-日）
        display_labels = [datetime.strptime(k, "%Y-%m-%d").strftime("%m月%d日") for k in ordered_keys]
        
        fig = px.bar(
            x=display_labels,
            y=[forecast[k] for k in ordered_keys],
            labels={"x": "日期", "y": "待复习题量"},
            text=[forecast[k] for k in ordered_keys],
        )
        fig.update_traces(marker_color=THEME_PRESETS[st.session_state.theme_choice]["accent"])
        fig.update_layout(
            xaxis=dict(
                type='category',  # 使用分类轴，避免时间精确到秒
                tickangle=-45,
            ),
            yaxis=dict(
                tickmode='linear',
                tick0=0,
                dtick=1,  # 整数刻度
            )
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("未来 14 天暂无复习压力。")


# ==================== 主程序入口 ====================
st.set_page_config(page_title="DeepPrep", layout="wide", page_icon="📚")
init_database()
init_session_state()

if not st.session_state.is_logged_in:
    render_login_view()
    st.stop()

# 登录后渲染主题与侧边栏
render_sidebar()
st.markdown(
    build_theme_css(st.session_state.theme_choice),
    unsafe_allow_html=True,
)

# 为知识图谱页面预清理复习状态，防止切换页面卡死
_kg_safe_init()

page = st.session_state.current_page
if page == "🏠 首页":
    render_dashboard()
elif page == "🔍 智能搜题":
    render_smart_upload()
elif page == "🗂️ 错题库":
    try:
        render_mistake_vault()
    except Exception as e:
        st.error(friendly_error(e))
        st.info("💡 提示：请刷新页面或稍后再试")
        if st.button("🔄 刷新页面", key="mistake_refresh"):
            st.rerun()
elif page == "🔄 沉浸式复习":
    render_review_mode()
elif page == "🧠 知识图谱":
    st.title("🧠 知识图谱")
    
    try:
        render_knowledge_graph()
    except Exception as e:
        st.error(friendly_error(e))
        st.info("💡 提示：请检查数据库连接和数据结构是否正常")
else:
    render_learning_stats()

