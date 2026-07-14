"""
数据管理模块 - 负责错题数据的存储、读取和管理
使用 JSON 文件存储数据，简单易用
"""

import json  # 导入 JSON 库，用于数据序列化和反序列化
import os  # 导入 os 库，用于文件操作
from datetime import datetime, timedelta  # 导入日期时间库
from typing import List, Dict, Optional  # 导入类型提示

# 数据文件路径
DATA_FILE = "mistakes_data.json"  # 错题数据存储文件


def load_data() -> Dict:
    """
    加载错题数据
    如果文件不存在，返回空的数据结构
    """
    if os.path.exists(DATA_FILE):  # 检查文件是否存在
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:  # 打开文件（UTF-8编码）
                return json.load(f)  # 解析 JSON 数据
        except Exception as e:
            print(f"加载数据失败: {e}")  # 如果出错，打印错误信息
            return {"mistakes": []}  # 返回空数据
    return {"mistakes": []}  # 文件不存在时返回空数据


def save_data(data: Dict):
    """
    保存错题数据到文件
    """
    try:
        with open(DATA_FILE, 'w', encoding='utf-8') as f:  # 打开文件（写入模式）
            json.dump(data, f, ensure_ascii=False, indent=2)  # 保存 JSON 数据（格式化输出）
    except Exception as e:
        print(f"保存数据失败: {e}")  # 如果出错，打印错误信息


def add_mistake(question_image_base64: str, solution: str, knowledge_points: List[str] = None):
    """
    添加错题到错题库
    
    参数:
        question_image_base64: 题目图片的 base64 编码
        solution: 解题过程和答案
        knowledge_points: 涉及的知识点列表
    """
    data = load_data()  # 加载现有数据
    
    # 创建新的错题记录
    mistake = {
        "id": len(data["mistakes"]) + 1,  # 自动生成 ID
        "question_image": question_image_base64,  # 保存题目图片
        "solution": solution,  # 保存解题过程
        "knowledge_points": knowledge_points or [],  # 保存知识点
        "created_at": datetime.now().isoformat(),  # 记录创建时间
        "review_dates": [],  # 复习日期列表（用于记忆曲线）
        "next_review_date": datetime.now().isoformat(),  # 下次复习日期
        "review_count": 0,  # 复习次数
        "mastery_level": 0,  # 掌握程度（0-5，5表示完全掌握）
    }
    
    data["mistakes"].append(mistake)  # 添加到错题列表
    save_data(data)  # 保存数据
    return mistake["id"]  # 返回新错题的 ID


def get_all_mistakes() -> List[Dict]:
    """
    获取所有错题
    """
    data = load_data()  # 加载数据
    return data.get("mistakes", [])  # 返回错题列表


def get_mistake_by_id(mistake_id: int) -> Optional[Dict]:
    """
    根据 ID 获取错题
    """
    mistakes = get_all_mistakes()  # 获取所有错题
    for mistake in mistakes:  # 遍历错题列表
        if mistake["id"] == mistake_id:  # 找到匹配的 ID
            return mistake  # 返回该错题
    return None  # 未找到返回 None


def delete_mistake(mistake_id: int) -> bool:
    """
    删除错题
    返回是否删除成功
    """
    data = load_data()  # 加载数据
    mistakes = data.get("mistakes", [])  # 获取错题列表
    
    # 找到要删除的错题并移除
    original_count = len(mistakes)  # 记录原始数量
    data["mistakes"] = [m for m in mistakes if m["id"] != mistake_id]  # 过滤掉要删除的错题
    
    if len(data["mistakes"]) < original_count:  # 如果数量减少了
        save_data(data)  # 保存数据
        return True  # 返回成功
    return False  # 返回失败


def update_mistake_review(mistake_id: int, mastery_level: int):
    """
    更新错题的复习记录
    根据艾宾浩斯遗忘曲线计算下次复习时间
    
    参数:
        mistake_id: 错题 ID
        mastery_level: 掌握程度（0-5）
    """
    data = load_data()  # 加载数据
    mistakes = data.get("mistakes", [])  # 获取错题列表
    
    for mistake in mistakes:  # 遍历错题列表
        if mistake["id"] == mistake_id:  # 找到匹配的错题
            # 更新复习信息
            mistake["review_count"] += 1  # 增加复习次数
            mistake["mastery_level"] = mastery_level  # 更新掌握程度
            mistake["review_dates"].append(datetime.now().isoformat())  # 记录本次复习时间
            
            # 根据艾宾浩斯遗忘曲线计算下次复习时间
            # 复习间隔：1天、2天、4天、7天、15天、30天
            intervals = [1, 2, 4, 7, 15, 30]  # 复习间隔（天）
            review_count = mistake["review_count"]  # 当前复习次数
            
            if review_count <= len(intervals):  # 如果复习次数在范围内
                days = intervals[review_count - 1]  # 获取对应的间隔天数
            else:
                days = 30  # 超过6次后，固定为30天
            
            # 如果掌握程度高，可以延长间隔
            if mastery_level >= 4:  # 掌握程度较高
                days = int(days * 1.5)  # 延长1.5倍
            
            # 计算下次复习日期
            next_review = datetime.now() + timedelta(days=days)  # 当前时间 + 间隔天数
            mistake["next_review_date"] = next_review.isoformat()  # 保存下次复习日期
            
            save_data(data)  # 保存数据
            return True  # 返回成功
    
    return False  # 未找到错题，返回失败


def get_mistakes_due_for_review() -> List[Dict]:
    """
    获取需要复习的错题（根据记忆曲线）
    返回所有到了复习时间的错题
    """
    mistakes = get_all_mistakes()  # 获取所有错题
    now = datetime.now()  # 当前时间
    
    due_mistakes = []  # 需要复习的错题列表
    
    for mistake in mistakes:  # 遍历所有错题
        next_review_str = mistake.get("next_review_date")  # 获取下次复习日期
        if next_review_str:  # 如果存在
            try:
                next_review = datetime.fromisoformat(next_review_str)  # 解析日期
                if next_review <= now:  # 如果到了复习时间
                    due_mistakes.append(mistake)  # 添加到列表
            except Exception:
                continue  # 如果日期格式错误，跳过
    
    # 按掌握程度和复习次数排序（掌握程度低的优先）
    due_mistakes.sort(key=lambda x: (x.get("mastery_level", 0), x.get("review_count", 0)))
    
    return due_mistakes  # 返回需要复习的错题


def get_mistakes_by_knowledge_point(knowledge_point: str) -> List[Dict]:
    """
    根据知识点获取相关错题
    用于推送同类型的错题
    """
    mistakes = get_all_mistakes()  # 获取所有错题
    related_mistakes = []  # 相关错题列表
    
    for mistake in mistakes:  # 遍历所有错题
        knowledge_points = mistake.get("knowledge_points", [])  # 获取知识点列表
        # 检查是否包含指定知识点（不区分大小写）
        if any(kp.lower() in knowledge_point.lower() or knowledge_point.lower() in kp.lower() 
               for kp in knowledge_points):
            related_mistakes.append(mistake)  # 添加到列表
    
    return related_mistakes  # 返回相关错题

