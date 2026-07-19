"""
数据库管理模块 - 使用 SQLite 存储错题数据
支持 users 表、questions 表和 review_logs 表
V5.1 - 多用户鉴权版本
"""

import sqlite3
import json
import os
import hashlib
import secrets
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import base64

# 数据库文件路径
DB_FILE = "mistakes.db"
INTERVAL_MINUTES = {
    0: 10,           # 10 分钟（答错后）
    1: 60 * 24,      # 1 天（第1次答对）
    2: 60 * 24 * 7,  # 7 天（第2次答对）
    3: 60 * 24 * 15, # 15 天（第3次答对，达到掌握）
    4: 60 * 24 * 15, # 15 天（保持）
    5: 60 * 24 * 15  # 15 天（保持）
}

QUESTION_EXTRA_COLUMNS = {
    "topic": "TEXT",
    "memory_strength": "INTEGER DEFAULT 0",
    "wrong_count": "INTEGER DEFAULT 0",
    "correct_count": "INTEGER DEFAULT 0",
    "accuracy": "REAL DEFAULT 0.0",
    "archived": "INTEGER DEFAULT 0",
    "next_review_time": "TEXT",
    "user_id": "INTEGER",
    "question_text_clean": "TEXT"
}


def get_connection():
    """获取数据库连接"""
    conn = sqlite3.connect(DB_FILE, timeout=10.0)
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def get_db():
    """数据库连接上下文管理器，确保连接自动关闭，防止连接泄漏"""
    conn = get_connection()
    try:
        yield conn
    finally:
        try:
            conn.close()
        except Exception:
            pass


def safe_get_topic(row):
    """安全地获取 topic 字段（兼容旧数据）"""
    try:
        return row["topic"]
    except (KeyError, IndexError):
        return None


def safe_get_field(row, field_name, default=None):
    """安全地获取字段值（兼容旧数据）"""
    try:
        value = row[field_name]
        return value if value is not None else default
    except (KeyError, IndexError):
        return default


# ==================== 密码哈希工具 ====================
def hash_password(password: str) -> str:
    """使用 SHA-256 + 盐值对密码进行哈希，返回格式：salt$hash"""
    salt = secrets.token_hex(16)
    password_hash = hashlib.sha256((salt + password).encode('utf-8')).hexdigest()
    return f"{salt}${password_hash}"


def verify_password(password: str, stored_hash: str) -> bool:
    """验证密码是否匹配存储的哈希值"""
    try:
        salt, hash_value = stored_hash.split('$')
        password_hash = hashlib.sha256((salt + password).encode('utf-8')).hexdigest()
        return password_hash == hash_value
    except (ValueError, AttributeError):
        return False


# ==================== 用户管理函数 ====================
def create_user(username: str, password: str) -> bool:
    """创建新用户，成功返回 True，失败返回 False（用户名已存在等）"""
    if not username or not password:
        return False

    with get_db() as conn:
        cursor = conn.cursor()
        try:
            password_hash = hash_password(password)
            created_at = datetime.now().isoformat()
            cursor.execute("""
                INSERT INTO users (username, password_hash, created_at)
                VALUES (?, ?, ?)
            """, (username.strip(), password_hash, created_at))
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False
        except Exception as e:
            print(f"创建用户失败: {e}")
            return False


def verify_user(username: str, password: str) -> Optional[Dict]:
    """验证用户登录，成功返回用户信息字典，失败返回 None"""
    if not username or not password:
        return None

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, username, password_hash, created_at
            FROM users WHERE username = ?
        """, (username.strip(),))
        row = cursor.fetchone()

    if not row:
        return None

    if verify_password(password, row["password_hash"]):
        return {
            "user_id": row["id"],
            "username": row["username"],
            "created_at": row["created_at"]
        }
    return None


def get_user_by_id(user_id: int) -> Optional[Dict]:
    """根据 ID 获取用户信息"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, username, created_at
            FROM users WHERE id = ?
        """, (user_id,))
        row = cursor.fetchone()

    if row:
        return {
            "user_id": row["id"],
            "username": row["username"],
            "created_at": row["created_at"]
        }
    return None


# ==================== 数据库初始化 ====================
def init_database():
    """初始化数据库，创建表结构"""
    with get_db() as conn:
        cursor = conn.cursor()

        # 创建 users 表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)

        # 创建 questions 表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS questions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question_image TEXT NOT NULL,
                solution TEXT NOT NULL,
                knowledge_points TEXT NOT NULL,
                subject TEXT,
                topic TEXT,
                mastery_level INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                next_review_date TEXT NOT NULL,
                review_count INTEGER DEFAULT 0,
                user_id INTEGER,
                question_text_clean TEXT,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)

        ensure_question_columns(cursor)

        # 创建 review_logs 表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS review_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question_id INTEGER NOT NULL,
                review_result TEXT NOT NULL,
                review_time TEXT NOT NULL,
                user_answer TEXT,
                ai_feedback TEXT,
                user_id INTEGER,
                FOREIGN KEY (question_id) REFERENCES questions(id),
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)

        # 确保 review_logs 表有 user_id 字段
        cursor.execute("PRAGMA table_info(review_logs)")
        columns = {column[1] for column in cursor.fetchall()}
        if "user_id" not in columns:
            cursor.execute("ALTER TABLE review_logs ADD COLUMN user_id INTEGER")

        # 创建 mastered_knowledge 表（知识图谱）
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS mastered_knowledge (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                subject TEXT NOT NULL,
                knowledge_point TEXT NOT NULL,
                mastered_at TEXT NOT NULL,
                source_question_id INTEGER,
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (source_question_id) REFERENCES questions(id),
                UNIQUE(user_id, subject, knowledge_point)
            )
        """)

        conn.commit()


def ensure_question_columns(cursor: sqlite3.Cursor):
    """确保 questions 表具备所有新增字段"""
    cursor.execute("PRAGMA table_info(questions)")
    columns = {column[1] for column in cursor.fetchall()}

    for column, ddl in QUESTION_EXTRA_COLUMNS.items():
        if column not in columns:
            cursor.execute(f"ALTER TABLE questions ADD COLUMN {column} {ddl}")
            columns.add(column)

    # 回填 next_review_time
    cursor.execute("""
        UPDATE questions
        SET next_review_time = COALESCE(next_review_time, next_review_date, ?)
        WHERE next_review_time IS NULL OR next_review_time = ''
    """, (datetime.now().isoformat(),))

    # 将 accuracy 归零，避免 NULL
    cursor.execute("""
        UPDATE questions
        SET accuracy = 0.0
        WHERE accuracy IS NULL
    """)


def migrate_from_json():
    """从 JSON 文件迁移数据到 SQLite（如果存在旧数据）"""
    json_file = "mistakes_data.json"
    if not os.path.exists(json_file):
        return

    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        mistakes = data.get("mistakes", [])
        if not mistakes:
            return

        with get_db() as conn:
            cursor = conn.cursor()
            for mistake in mistakes:
                cursor.execute(
                    "SELECT id FROM questions WHERE created_at = ?",
                    (mistake.get("created_at"),)
                )
                if cursor.fetchone():
                    continue  # 已存在，跳过

                cursor.execute("""
                    INSERT INTO questions (
                        question_image, solution, knowledge_points, subject,
                        mastery_level, created_at, next_review_date, review_count,
                        user_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    mistake.get("question_image", ""),
                    mistake.get("solution", ""),
                    json.dumps(mistake.get("knowledge_points", []), ensure_ascii=False),
                    None,
                    min(mistake.get("mastery_level", 0) * 2, 10),
                    mistake.get("created_at", datetime.now().isoformat()),
                    mistake.get("next_review_date", datetime.now().isoformat()),
                    mistake.get("review_count", 0),
                    None  # 旧数据无 user_id
                ))
            conn.commit()
        print(f"成功迁移 {len(mistakes)} 条错题记录到数据库")
    except Exception as e:
        print(f"迁移数据时出错: {e}")


# ==================== 错题管理函数（带 user_id） ====================
def add_question(question_image_base64: str, solution: str,
                 knowledge_points: List[str] = None, subject: str = None,
                 topic: str = None, user_id: int = None,
                 question_text_clean: str = None) -> int:
    """添加错题到数据库，返回新错题的 ID"""
    with get_db() as conn:
        cursor = conn.cursor()
        now = datetime.now().isoformat()
        cursor.execute("""
            INSERT INTO questions (
                question_image, solution, knowledge_points, subject, topic,
                mastery_level, created_at, next_review_date, next_review_time,
                review_count, memory_strength, wrong_count, correct_count,
                accuracy, archived, user_id, question_text_clean
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            question_image_base64,
            solution,
            json.dumps(knowledge_points or [], ensure_ascii=False),
            subject,
            topic,
            0,
            now,
            now,
            now,
            0,
            0,
            0,
            0,
            0.0,
            0,
            user_id,
            question_text_clean
        ))
        question_id = cursor.lastrowid
        conn.commit()
        return question_id


def get_all_questions(user_id: int = None) -> List[Dict]:
    """获取所有错题（按用户过滤）"""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            if user_id is not None:
                cursor.execute(
                    "SELECT * FROM questions WHERE user_id = ? ORDER BY created_at DESC",
                    (user_id,)
                )
            else:
                cursor.execute("SELECT * FROM questions ORDER BY created_at DESC")

            rows = cursor.fetchall()
            questions = []
            for row in rows:
                try:
                    question = _serialize_question_row(row)
                    if question:
                        questions.append(question)
                except Exception as e:
                    print(f"序列化错题行时出错，跳过: {e}")
                    continue
            return questions
    except Exception as e:
        print(f"获取错题列表时出错: {e}")
        return []


def get_question_by_id(question_id: int, user_id: int = None) -> Optional[Dict]:
    """根据 ID 获取错题"""
    with get_db() as conn:
        cursor = conn.cursor()
        if user_id is not None:
            cursor.execute(
                "SELECT * FROM questions WHERE id = ? AND user_id = ?",
                (question_id, user_id)
            )
        else:
            cursor.execute("SELECT * FROM questions WHERE id = ?", (question_id,))
        row = cursor.fetchone()

    if row:
        return _serialize_question_row(row)
    return None


def delete_question(question_id: int, user_id: int = None) -> bool:
    """删除错题（同时删除相关的复习记录）"""
    with get_db() as conn:
        cursor = conn.cursor()
        # 先验证权限
        if user_id is not None:
            cursor.execute(
                "SELECT id FROM questions WHERE id = ? AND user_id = ?",
                (question_id, user_id)
            )
            if not cursor.fetchone():
                return False

        cursor.execute("DELETE FROM review_logs WHERE question_id = ?", (question_id,))
        cursor.execute("DELETE FROM questions WHERE id = ?", (question_id,))
        conn.commit()
        return cursor.rowcount > 0


def archive_question(question_id: int, archived: bool = True, user_id: int = None) -> None:
    """软归档或恢复错题"""
    with get_db() as conn:
        cursor = conn.cursor()
        if user_id is not None:
            cursor.execute(
                "UPDATE questions SET archived = ? WHERE id = ? AND user_id = ?",
                (1 if archived else 0, question_id, user_id)
            )
        else:
            cursor.execute(
                "UPDATE questions SET archived = ? WHERE id = ?",
                (1 if archived else 0, question_id)
            )
        conn.commit()


def _normalize_mastery(value: Optional[int]) -> int:
    """兼容旧数据，将 0-10 的掌握度转换为 0-3（最多复习3次）"""
    if value is None:
        return 0
    if 0 <= value <= 3:
        return value
    return 3


def _serialize_question_row(row: sqlite3.Row) -> Dict:
    """统一格式化 questions 表的行（增强错误处理）"""
    try:
        knowledge_raw = safe_get_field(row, "knowledge_points", "")
        knowledge_points = []
        if knowledge_raw:
            try:
                knowledge_points = json.loads(knowledge_raw)
                if not isinstance(knowledge_points, list):
                    knowledge_points = []
            except Exception:
                knowledge_points = []

        memory_strength = safe_get_field(row, "memory_strength", _normalize_mastery(safe_get_field(row, "mastery_level", 0)))
        accuracy = safe_get_field(row, "accuracy", 0.0)

        next_review_time = safe_get_field(row, "next_review_time")
        if not next_review_time:
            next_review_time = safe_get_field(row, "next_review_date", datetime.now().isoformat())

        return {
            "id": safe_get_field(row, "id", 0),
            "question_image": safe_get_field(row, "question_image", ""),
            "solution": safe_get_field(row, "solution", ""),
            "knowledge_points": knowledge_points,
            "subject": safe_get_field(row, "subject", "未分类"),
            "topic": safe_get_topic(row),
            "mastery_level": safe_get_field(row, "mastery_level", 0),
            "memory_strength": memory_strength,
            "created_at": safe_get_field(row, "created_at", datetime.now().isoformat()),
            "next_review_time": next_review_time,
            "review_count": safe_get_field(row, "review_count", 0),
            "wrong_count": safe_get_field(row, "wrong_count", 0),
            "correct_count": safe_get_field(row, "correct_count", 0),
            "accuracy": accuracy,
            "archived": safe_get_field(row, "archived", 0),
            "user_id": safe_get_field(row, "user_id"),
            "question_text_clean": safe_get_field(row, "question_text_clean", "")
        }
    except Exception as e:
        print(f"序列化错题行时出错: {e}")
        return {
            "id": 0,
            "question_image": "",
            "solution": "",
            "knowledge_points": [],
            "subject": "未分类",
            "topic": None,
            "mastery_level": 0,
            "memory_strength": 0,
            "created_at": datetime.now().isoformat(),
            "next_review_time": datetime.now().isoformat(),
            "review_count": 0,
            "wrong_count": 0,
            "correct_count": 0,
            "accuracy": 0.0,
            "archived": 0,
            "user_id": None,
            "question_text_clean": ""
        }


def update_question_mastery(question_id: int, is_correct: bool,
                            user_answer: str = None,
                            ai_feedback: str = None,
                            user_id: int = None) -> Dict:
    """根据 SM-2 变体算法更新记忆强度、复习间隔与统计数据"""
    with get_db() as conn:
        cursor = conn.cursor()

        # 验证权限
        if user_id is not None:
            cursor.execute("""
                SELECT mastery_level, memory_strength, review_count,
                       wrong_count, correct_count, archived
                FROM questions WHERE id = ? AND user_id = ?
            """, (question_id, user_id))
        else:
            cursor.execute("""
                SELECT mastery_level, memory_strength, review_count,
                       wrong_count, correct_count, archived
                FROM questions WHERE id = ?
            """, (question_id,))

        row = cursor.fetchone()
        if not row:
            raise ValueError(f"题目 {question_id} 不存在或无权限，无法更新掌握度")

        current_strength = row["memory_strength"]
        if current_strength is None:
            current_strength = _normalize_mastery(row["mastery_level"])

        review_count = (row["review_count"] or 0) + 1
        wrong_count = row["wrong_count"] or 0
        correct_count = row["correct_count"] or 0

        if is_correct:
            correct_count += 1
            new_strength = min(current_strength + 1, 3)
            if correct_count == 1:
                interval_minutes = INTERVAL_MINUTES[1]  # 1天
            elif correct_count == 2:
                interval_minutes = INTERVAL_MINUTES[2]  # 7天
            else:
                interval_minutes = INTERVAL_MINUTES[3]  # 15天
            review_result = "Pass"
        else:
            new_strength = max(current_strength - 2, 0)
            interval_minutes = INTERVAL_MINUTES[0]  # 10分钟
            wrong_count += 1
            review_result = "Fail"

        accuracy = 0.0
        total_attempts = correct_count + wrong_count
        if total_attempts > 0:
            accuracy = round((correct_count / total_attempts) * 100, 1)

        next_review_dt = datetime.now() + timedelta(minutes=interval_minutes)
        next_review_iso = next_review_dt.isoformat()

        cursor.execute("""
            UPDATE questions
            SET mastery_level = ?, memory_strength = ?, review_count = ?,
                wrong_count = ?, correct_count = ?, accuracy = ?,
                next_review_time = ?, next_review_date = ?, archived = COALESCE(archived, 0)
            WHERE id = ?
        """, (
            new_strength * 2,
            new_strength,
            review_count,
            wrong_count,
            correct_count,
            accuracy,
            next_review_iso,
            next_review_iso,
            question_id
        ))

        cursor.execute("""
            INSERT INTO review_logs (
                question_id, review_result, review_time, user_answer, ai_feedback, user_id
            ) VALUES (?, ?, ?, ?, ?, ?)
        """, (
            question_id,
            review_result,
            datetime.now().isoformat(),
            user_answer,
            ai_feedback,
            user_id
        ))

        conn.commit()

        return {
            "memory_strength": new_strength,
            "next_review_time": next_review_iso,
            "interval_minutes": interval_minutes,
            "accuracy": accuracy,
            "correct_count": correct_count,
            "wrong_count": wrong_count,
            "archived": row["archived"] or 0
        }


def get_questions_due_for_review(user_id: int = None) -> List[Dict]:
    """获取需要复习的错题（优先级队列）"""
    with get_db() as conn:
        cursor = conn.cursor()
        now = datetime.now().isoformat()

        if user_id is not None:
            cursor.execute("""
                SELECT * FROM questions
                WHERE archived = 0 AND next_review_time <= ? AND user_id = ?
                ORDER BY accuracy ASC, next_review_time ASC
            """, (now, user_id))
        else:
            cursor.execute("""
                SELECT * FROM questions
                WHERE archived = 0 AND next_review_time <= ?
                ORDER BY accuracy ASC, next_review_time ASC
            """, (now,))

        rows = cursor.fetchall()
        return [_serialize_question_row(row) for row in rows]


def get_questions_by_knowledge_point(knowledge_point: str, user_id: int = None) -> List[Dict]:
    """根据知识点获取相关错题"""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            if user_id is not None:
                cursor.execute("SELECT * FROM questions WHERE user_id = ?", (user_id,))
            else:
                cursor.execute("SELECT * FROM questions")
            rows = cursor.fetchall()

            related_questions = []
            for row in rows:
                knowledge_points = []
                try:
                    knowledge_points_raw = safe_get_field(row, "knowledge_points", "")
                    if knowledge_points_raw:
                        knowledge_points = json.loads(knowledge_points_raw)
                        if not isinstance(knowledge_points, list):
                            knowledge_points = []
                except (json.JSONDecodeError, TypeError, ValueError):
                    knowledge_points = []

                if knowledge_points and isinstance(knowledge_point, str):
                    if any(isinstance(kp, str) and (kp.lower() in knowledge_point.lower() or
                           knowledge_point.lower() in kp.lower()) for kp in knowledge_points):
                        try:
                            related_questions.append(_serialize_question_row(row))
                        except Exception:
                            pass
            return related_questions
    except Exception as e:
        print(f"获取知识点相关错题时出错: {e}")
        return []


def get_review_logs(question_id: int, user_id: int = None) -> List[Dict]:
    """获取指定错题的复习记录"""
    with get_db() as conn:
        cursor = conn.cursor()
        if user_id is not None:
            cursor.execute("""
                SELECT * FROM review_logs
                WHERE question_id = ? AND (user_id = ? OR user_id IS NULL)
                ORDER BY review_time DESC
            """, (question_id, user_id))
        else:
            cursor.execute("""
                SELECT * FROM review_logs
                WHERE question_id = ?
                ORDER BY review_time DESC
            """, (question_id,))

        rows = cursor.fetchall()
        logs = []
        for row in rows:
            logs.append({
                "id": row["id"],
                "question_id": row["question_id"],
                "review_result": row["review_result"],
                "review_time": row["review_time"],
                "user_answer": safe_get_field(row, "user_answer"),
                "ai_feedback": safe_get_field(row, "ai_feedback"),
                "user_id": safe_get_field(row, "user_id")
            })
        return logs


def update_question_subject(question_id: int, subject: str, user_id: int = None):
    """更新错题的学科"""
    with get_db() as conn:
        cursor = conn.cursor()
        if user_id is not None:
            cursor.execute(
                "UPDATE questions SET subject = ? WHERE id = ? AND user_id = ?",
                (subject, question_id, user_id)
            )
        else:
            cursor.execute(
                "UPDATE questions SET subject = ? WHERE id = ?",
                (subject, question_id)
            )
        conn.commit()


def update_question_text_clean(question_id: int, question_text_clean: str, user_id: int = None):
    """更新错题的清洗后题目文本"""
    with get_db() as conn:
        cursor = conn.cursor()
        if user_id is not None:
            cursor.execute(
                "UPDATE questions SET question_text_clean = ? WHERE id = ? AND user_id = ?",
                (question_text_clean, question_id, user_id)
            )
        else:
            cursor.execute(
                "UPDATE questions SET question_text_clean = ? WHERE id = ?",
                (question_text_clean, question_id)
            )
        conn.commit()


# ==================== 知识图谱相关函数 ====================
def add_mastered_knowledge(user_id: int, subject: str, knowledge_points: List[str],
                          source_question_id: int = None) -> int:
    """添加已掌握的知识点到知识图谱，返回成功添加的知识点数量"""
    if not user_id or not knowledge_points:
        return 0

    with get_db() as conn:
        cursor = conn.cursor()
        added_count = 0
        now = datetime.now().isoformat()

        for kp in knowledge_points:
            if not kp or not kp.strip():
                continue
            try:
                cursor.execute("""
                    INSERT OR IGNORE INTO mastered_knowledge
                    (user_id, subject, knowledge_point, mastered_at, source_question_id)
                    VALUES (?, ?, ?, ?, ?)
                """, (user_id, subject or "未分类", kp.strip(), now, source_question_id))
                if cursor.rowcount > 0:
                    added_count += 1
            except Exception as e:
                print(f"添加知识点失败: {e}")

        conn.commit()
        return added_count


def get_mastered_knowledge(user_id: int, subject: str = None) -> List[Dict]:
    """获取用户已掌握的知识点"""
    with get_db() as conn:
        cursor = conn.cursor()
        if subject:
            cursor.execute("""
                SELECT * FROM mastered_knowledge
                WHERE user_id = ? AND subject = ?
                ORDER BY mastered_at DESC
            """, (user_id, subject))
        else:
            cursor.execute("""
                SELECT * FROM mastered_knowledge
                WHERE user_id = ?
                ORDER BY subject, mastered_at DESC
            """, (user_id,))

        rows = cursor.fetchall()

    result = []
    for row in rows:
        result.append({
            "id": row["id"],
            "user_id": row["user_id"],
            "subject": row["subject"],
            "knowledge_point": row["knowledge_point"],
            "mastered_at": row["mastered_at"],
            "source_question_id": safe_get_field(row, "source_question_id")
        })
    return result


def get_knowledge_stats_by_subject(user_id: int) -> Dict[str, Dict]:
    """获取各学科的知识点统计（增强版：包含掌握进度）"""
    try:
        with get_db() as conn:
            cursor = conn.cursor()

            # 获取已掌握的知识点（按学科分组）
            cursor.execute("""
                SELECT subject, knowledge_point FROM mastered_knowledge
                WHERE user_id = ?
            """, (user_id,))
            mastered_rows = cursor.fetchall()

            mastered_set = set()
            mastered_by_subject = {}
            for row in mastered_rows:
                try:
                    subject = safe_get_field(row, "subject") or "未分类"
                    kp = safe_get_field(row, "knowledge_point")
                    if kp:
                        mastered_set.add((subject, kp))
                        if subject not in mastered_by_subject:
                            mastered_by_subject[subject] = set()
                        mastered_by_subject[subject].add(kp)
                except Exception:
                    continue

            # 获取所有活跃题目的知识点和答对次数
            cursor.execute("""
                SELECT subject, knowledge_points, correct_count FROM questions
                WHERE user_id = ? AND archived = 0
            """, (user_id,))
            question_rows = cursor.fetchall()
    except Exception as e:
        print(f"获取知识点统计时数据库错误: {e}")
        return {}

    # 构建知识点统计
    kp_stats = {}

    for row in question_rows:
        try:
            subject = safe_get_field(row, "subject") or "未分类"
            correct_count = safe_get_field(row, "correct_count", 0) or 0
            try:
                correct_count = int(correct_count) if correct_count else 0
            except (ValueError, TypeError):
                correct_count = 0

            knowledge_points_raw = safe_get_field(row, "knowledge_points", "")

            if knowledge_points_raw:
                try:
                    kps = json.loads(knowledge_points_raw)
                    if isinstance(kps, list):
                        for kp in kps:
                            if not kp or not isinstance(kp, str) or not kp.strip():
                                continue
                            kp = kp.strip()
                            if subject not in kp_stats:
                                kp_stats[subject] = {}
                            if kp not in kp_stats[subject]:
                                kp_stats[subject][kp] = {"total_correct": 0, "question_count": 0}
                            kp_stats[subject][kp]["total_correct"] += correct_count
                            kp_stats[subject][kp]["question_count"] += 1
                except (json.JSONDecodeError, TypeError, ValueError):
                    pass
        except Exception:
            continue

    # 构建返回结果
    stats = {}

    try:
        for subject, kp_data in kp_stats.items():
            if not subject or not isinstance(subject, str):
                continue
            if subject not in stats:
                stats[subject] = {
                    "mastered": 0,
                    "partial": 0,
                    "pending": 0,
                    "knowledge_points": []
                }

            for kp, data in kp_data.items():
                try:
                    question_count = data.get("question_count", 0) or 0
                    total_correct = data.get("total_correct", 0) or 0
                    try:
                        question_count = int(question_count)
                        total_correct = int(total_correct)
                    except (ValueError, TypeError):
                        continue

                    if question_count <= 0:
                        continue

                    avg_correct = total_correct / question_count

                    is_mastered = (subject, kp) in mastered_set
                    if is_mastered or avg_correct >= 3:
                        status = "mastered"
                        stats[subject]["mastered"] += 1
                    elif avg_correct >= 1:
                        status = "partial"
                        stats[subject]["partial"] += 1
                    else:
                        status = "pending"
                        stats[subject]["pending"] += 1

                    stats[subject]["knowledge_points"].append({
                        "name": str(kp) if kp else "未知知识点",
                        "avg_correct": round(avg_correct, 1),
                        "question_count": question_count,
                        "status": status,
                        "is_mastered": is_mastered
                    })
                except Exception:
                    continue

        # 对知识点列表按状态和答对次数排序
        for subject in stats:
            try:
                if "knowledge_points" in stats[subject] and isinstance(stats[subject]["knowledge_points"], list):
                    stats[subject]["knowledge_points"].sort(
                        key=lambda x: (
                            0 if x.get("status") == "pending" else (1 if x.get("status") == "partial" else 2),
                            -x.get("avg_correct", 0)
                        )
                    )
            except Exception:
                pass

        return stats
    except Exception as e:
        print(f"构建知识点统计结果时出错: {e}")
        return {}


def remove_mastered_knowledge(user_id: int, subject: str, knowledge_point: str) -> bool:
    """移除已掌握的知识点，返回是否成功"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            DELETE FROM mastered_knowledge
            WHERE user_id = ? AND subject = ? AND knowledge_point = ?
        """, (user_id, subject, knowledge_point))
        conn.commit()
        return cursor.rowcount > 0


# ==================== 数据库初始化 ====================
# 初始化数据库（如果不存在）
if not os.path.exists(DB_FILE):
    init_database()
    migrate_from_json()
else:
    # 检查表是否存在，如果不存在则创建
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='questions'
        """)
        has_questions = cursor.fetchone()

    if not has_questions:
        init_database()
    else:
        with get_db() as conn:
            cursor = conn.cursor()
            # 确保 users 表存在
            cursor.execute("""
                SELECT name FROM sqlite_master
                WHERE type='table' AND name='users'
            """)
            if not cursor.fetchone():
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        username TEXT UNIQUE NOT NULL,
                        password_hash TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    )
                """)
                conn.commit()

            # 确保所有新字段存在
            ensure_question_columns(cursor)

            # 确保 review_logs 表有 user_id 字段
            cursor.execute("PRAGMA table_info(review_logs)")
            columns = {column[1] for column in cursor.fetchall()}
            if "user_id" not in columns:
                cursor.execute("ALTER TABLE review_logs ADD COLUMN user_id INTEGER")
                conn.commit()

            # 确保 mastered_knowledge 表存在
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS mastered_knowledge (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    subject TEXT NOT NULL,
                    knowledge_point TEXT NOT NULL,
                    mastered_at TEXT NOT NULL,
                    source_question_id INTEGER,
                    FOREIGN KEY (user_id) REFERENCES users(id),
                    FOREIGN KEY (source_question_id) REFERENCES questions(id),
                    UNIQUE(user_id, subject, knowledge_point)
                )
            """)
            conn.commit()
