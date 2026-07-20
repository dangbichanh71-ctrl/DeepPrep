# DeepPrep 智能备考平台

> 🎯 拍照即搜，AI 秒解，从搜题到掌握，一站式备考闭环。

[![Streamlit](https://img.shields.io/badge/Platform-Streamlit-FF4B4B?logo=streamlit)](https://streamlit.io)
[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)

**👉 线上体验**：https://deepprep.streamlit.app  
**🎮 演示账号**：`demo` / `demo123`（已预置 5 道错题，可直接体验全部功能）

---

## 为什么做 DeepPrep？

备考时我们都遇到过这三个问题：

1. **抄错题太累** — 手抄到错题本费时费力，抄完就再也没翻开过
2. **复习没章法** — 不知道什么时候该复习什么，要么拖延，要么瞎刷
3. **不知道弱在哪** — 错题散落在各个角落，说不清自己哪个知识点最薄弱

DeepPrep 把这三个问题串成一个闭环：**搜题 → 理解 → 复习 → 掌握**。

---

## 核心功能

| 功能 | 一句话 |
|------|--------|
| 🔍 **智能搜题** | 拍照上传，AI 识别文字 + 逐步解析，实时流式显示解题过程 |
| 🗂️ **错题库** | 按学科自动分类，文本优先 + 图片折叠，知识标签一目了然 |
| 🔄 **沉浸式复习** | 间隔重复算法推送 + AI 自动判卷 + AI 实时答疑 |
| 🧠 **知识图谱** | 知识点掌握度可视化，点击即看相关错题，绿色=已掌握 |
| 📊 **学习统计** | 活跃错题、累计复习、14 天预测曲线 |
| 🎯 **同类题生成** | 复习时一键生成同类题，举一反三，不存入库 |

### 产品闭环

```
拍题上传 → AI 识别 + 解题 → 保存错题 → 间隔重复复习 → AI 判卷 → 知识点追踪
    ↑                                                                     │
    └──────────────────── 同类题巩固 ←─────────────────────────────────────┘
```

---

## 看这 4 张图就够了

| 页面 | 截图 |
|------|------|
| 📊 **首页 Dashboard** | 欢迎语 + 统计卡片 + 快捷入口 + 学科分布 |
| 🔍 **智能搜题** | 拍照上传 → 流式 AI 解析 → AI 答疑 → 一键入库 |
| 🔄 **沉浸式复习** | 显示题目 → 用户作答 → AI 判卷 → AI 答疑 → 同类题 |
| 🧠 **知识图谱** | 学科 tabs → 掌握度环形图 → 知识点按钮 → 关联错题 |

---

## 技术栈

- **全栈**：Streamlit（Python 一体化框架，零前后端分离）
- **数据库**：SQLite（轻量零配置，多用户数据隔离）
- **AI**：SiliconFlow API（Qwen3-VL + Qwen2.5，兼容 OpenAI SDK）
- **可视化**：Plotly（交互式图表）
- **部署**：Streamlit Cloud（免费，GitHub 关联，自动部署）

---

## 3 分钟本地跑起来

```bash
# 1. 克隆
git clone https://github.com/dangbichanh71-ctrl/DeepPrep.git
cd DeepPrep

# 2. 装依赖（就 6 个包）
pip install -r requirements.txt

# 3. 配 API Key（在 .env 文件里写一行）
# SILICONFLOW_API_KEY=你的Key

# 4. 跑
streamlit run app.py
```

浏览器打开 `http://localhost:8501`，用 `demo / demo123` 登录即可。

---

## 产品文档

这些文档展示了产品思考深度，也是 PM 作品集的核心交付物：

- 📋 [产品需求文档 (PRD)](docs/PRD.md) — 痛点分析、功能优先级、指标体系
- 👥 [用户故事地图](docs/USER_STORIES.md) — 3 个用户画像 × 核心旅程
- 🔍 [竞品分析](docs/COMPETITIVE_ANALYSIS.md) — vs 作业帮、Anki、猿题库

---

## 作者

DeepPrep 由一名湖南工商大学 AI 专业学生独立完成，作为秋招产品经理方向的作品集项目。

欢迎反馈和建议！如遇 bug 欢迎提 Issue。
