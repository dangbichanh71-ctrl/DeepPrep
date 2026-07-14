"""
高数题目图片生成器
生成复杂的高等数学题目并保存为图片
"""

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib import font_manager
import os
import numpy as np

# 设置中文字体（Windows系统）
plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'Arial Unicode MS']
plt.rcParams['axes.unicode_minus'] = False  # 解决负号显示问题

# 启用 LaTeX 渲染（如果系统安装了 LaTeX）
plt.rcParams['text.usetex'] = False  # 如果系统没有 LaTeX，设为 False

# 创建题目文件夹
questions_folder = "test_questions"
if not os.path.exists(questions_folder):
    os.makedirs(questions_folder)

def create_question_image(question_num, title, question_text, filename):
    """
    创建题目图片
    
    参数:
        question_num: 题目编号
        title: 题目标题
        question_text: 题目内容（列表，每行一个元素）
        filename: 保存的文件名
    """
    fig, ax = plt.subplots(figsize=(10, 8))
    ax.axis('off')  # 隐藏坐标轴
    
    # 设置背景色
    fig.patch.set_facecolor('white')
    ax.set_facecolor('white')
    
    # 标题
    title_text = f"题目 {question_num}: {title}"
    ax.text(0.5, 0.95, title_text, 
            fontsize=18, fontweight='bold', 
            ha='center', va='top',
            transform=ax.transAxes)
    
    # 题目内容
    y_position = 0.85
    line_height = 0.08
    
    for line in question_text:
        ax.text(0.1, y_position, line,
                fontsize=14,
                ha='left', va='top',
                transform=ax.transAxes,
                family='monospace')
        y_position -= line_height
    
    # 保存图片
    filepath = os.path.join(questions_folder, filename)
    plt.savefig(filepath, dpi=150, bbox_inches='tight', facecolor='white')
    plt.close()
    print(f"已生成: {filepath}")

# 题目1: 复杂极限
create_question_image(
    1,
    "极限计算",
    [
        "求下列极限：",
        "",
        "lim(x→0) [e^x - 1 - sin(x)] / x²",
        "",
        "提示：可以使用洛必达法则或泰勒展开"
    ],
    "question_01_limit.png"
)

# 题目2: 导数应用
create_question_image(
    2,
    "导数与极值",
    [
        "设函数 f(x) = x³ - 3x² + 2x + 1",
        "",
        "求：",
        "(1) f'(x) 和 f''(x)",
        "(2) 函数的单调区间",
        "(3) 函数的极值点和极值",
        "(4) 函数在区间 [-1, 3] 上的最值"
    ],
    "question_02_derivative.png"
)

# 题目3: 隐函数求导
create_question_image(
    3,
    "隐函数求导",
    [
        "设方程 x²y + y²x = 1 确定了隐函数 y = y(x)",
        "",
        "求 dy/dx 和 d²y/dx²",
        "",
        "并在点 (1, 1) 处求导数值"
    ],
    "question_03_implicit.png"
)

# 题目4: 定积分
create_question_image(
    4,
    "定积分计算",
    [
        "计算下列定积分：",
        "",
        "∫[0, π] x·sin(x) dx",
        "",
        "提示：可以使用分部积分法"
    ],
    "question_04_integral.png"
)

# 题目5: 反常积分
create_question_image(
    5,
    "反常积分",
    [
        "判断下列反常积分的敛散性，若收敛则求其值：",
        "",
        "∫[1, +∞] 1/(x²+1) dx",
        "",
        "∫[0, 1] 1/√x dx"
    ],
    "question_05_improper.png"
)

# 题目6: 级数
create_question_image(
    6,
    "级数敛散性",
    [
        "判断下列级数的敛散性：",
        "",
        "∑(n=1 to ∞) n² / 2ⁿ",
        "",
        "∑(n=1 to ∞) (-1)ⁿ / n",
        "",
        "∑(n=1 to ∞) 1 / (n·ln(n))"
    ],
    "question_06_series.png"
)

# 题目7: 多元函数偏导数
create_question_image(
    7,
    "多元函数偏导数",
    [
        "设函数 z = f(x, y) = x²y + e^(xy) + sin(xy)",
        "",
        "求：",
        "(1) ∂z/∂x 和 ∂z/∂y",
        "(2) ∂²z/∂x², ∂²z/∂y², ∂²z/∂x∂y",
        "(3) 在点 (0, 1) 处的所有偏导数值"
    ],
    "question_07_partial.png"
)

# 题目8: 二重积分
create_question_image(
    8,
    "二重积分",
    [
        "计算二重积分：",
        "",
        "∬[D] (x² + y²) dxdy",
        "",
        "其中 D 是由曲线 y = x² 和 y = 2x 所围成的区域"
    ],
    "question_08_double_integral.png"
)

# 题目9: 微分方程
create_question_image(
    9,
    "微分方程",
    [
        "求解下列微分方程：",
        "",
        "dy/dx + 2xy = x·e^(-x²)",
        "",
        "满足初始条件 y(0) = 1"
    ],
    "question_09_differential.png"
)

# 题目10: 泰勒展开
create_question_image(
    10,
    "泰勒展开",
    [
        "求函数 f(x) = ln(1 + x) 在 x = 0 处的",
        "",
        "(1) 3阶泰勒多项式",
        "(2) 拉格朗日余项",
        "(3) 使用泰勒多项式近似计算 ln(1.1) 的误差"
    ],
    "question_10_taylor.png"
)

# 题目11: 参数方程
create_question_image(
    11,
    "参数方程求导",
    [
        "设曲线的参数方程为：",
        "",
        "x = t² + 1",
        "y = t³ - t",
        "",
        "求：",
        "(1) dy/dx",
        "(2) d²y/dx²",
        "(3) 曲线在 t = 1 处的切线方程"
    ],
    "question_11_parametric.png"
)

# 题目12: 向量函数
create_question_image(
    12,
    "向量函数",
    [
        "设向量函数 r(t) = (t², e^t, sin(t))",
        "",
        "求：",
        "(1) r'(t) 和 r''(t)",
        "(2) |r'(t)|",
        "(3) 在 t = 0 处的切向量和法向量"
    ],
    "question_12_vector.png"
)

# 题目13: 拉格朗日乘数法
create_question_image(
    13,
    "条件极值",
    [
        "求函数 f(x, y) = x² + y² 在约束条件",
        "",
        "x + y = 1",
        "",
        "下的极值（使用拉格朗日乘数法）"
    ],
    "question_13_lagrange.png"
)

# 题目14: 三重积分
create_question_image(
    14,
    "三重积分",
    [
        "计算三重积分：",
        "",
        "∭[Ω] (x + y + z) dxdydz",
        "",
        "其中 Ω 是由平面 x=0, y=0, z=0 和",
        "x + y + z = 1 所围成的四面体"
    ],
    "question_14_triple_integral.png"
)

# 题目15: 傅里叶级数
create_question_image(
    15,
    "傅里叶级数",
    [
        "将函数 f(x) = x, x ∈ [-π, π]",
        "",
        "展开为傅里叶级数，并写出前3项"
    ],
    "question_15_fourier.png"
)

print(f"\n所有题目已生成完成！共生成 15 道题目")
print(f"题目保存在文件夹: {questions_folder}/")

