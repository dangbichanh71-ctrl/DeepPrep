# DeepPrep 智能备考平台

> AI 驱动的全学段智能备考助手 —— 从搜题到复习，一站式闭环。

[![Streamlit](https://img.shields.io/badge/Platform-Streamlit-FF4B4B?logo=streamlit)](https://streamlit.io)
[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)

**🎯 线上体验**：[点击体验 DeepPrep](https://deepprep.streamlit.app) *(如果链接不可用，说明部署还在进行中)*

---

## 解决的问题

备考过程中，学生面临的三大痛点：

1. **搜题效率低** — 手打题目费时，拍题软件只能搜原题，无法深度理解
2. **复习无规划** — 不知道什么时候该复习什么，要么拖延要么盲目刷题
3. **知识不成体系** — 做过的题散落各处，不知道自己哪些知识点薄弱

**DeepPrep 用 AI 把这三个环节串成一个闭环**：搜题 → 理解 → 复习 → 追踪。

---

## 核心功能

| 功能 | 说明 |
|------|------|
| 🔍 **智能搜题** | 拍照上传题目，AI 自动识别 + 逐步解题，支持流式实时显示 |
| 🗂️ **错题库** | 所有错题集中管理，按学科/知识点分类，支持归档 |
| 🔄 **沉浸式复习** | 基于间隔重复算法，AI 自动判卷 + 生成同类题 |
| 🧠 **知识图谱** | 知识点掌握度可视化，一眼看出强弱项 |
| 📊 **学习统计** | KPI 看板 + 复习预测曲线，量化学习进度 |

### 产品闭环

```
拍题上传 → AI 识别解题 → 保存错题 → 定时复习 → AI 判卷 → 知识图谱追踪
    ↑                                                          │
    └──────────────── 同类题巩固 ←────────────────────────────────┘
```

---

## 技术架构

- **前端/后端**：Streamlit（一体化 Python 框架）
- **数据库**：SQLite（轻量级，零配置）
- **AI 能力**：SiliconFlow API（Qwen 系列模型）
  - Qwen3-VL-32B：图片 OCR 识别
  - Qwen2.5-32B：解题、判卷、生成题目
- **可视化**：Plotly
- **部署**：Streamlit Cloud（免费）

---

## 本地运行

```bash
# 1. 克隆仓库
git clone https://github.com/YOUR_USERNAME/deepprep.git
cd deepprep

# 2. 安装依赖
pip install -r requirements.txt

# 3. 配置 API Key
# 在项目根目录创建 .env 文件，写入：
# SILICONFLOW_API_KEY=你的Key

# 4. 启动
streamlit run app.py
```

访问 http://localhost:8501

---

## 产品文档

- [产品需求文档 (PRD)](docs/PRD.md)
- [用户故事地图](docs/USER_STORIES.md)
- [竞品分析](docs/COMPETITIVE_ANALYSIS.md)

---

## 作者

**DeepPrep** 由一名湖南工商大学 AI 专业学生独立完成，作为秋招产品经理方向的作品集项目。

欢迎反馈和建议！
