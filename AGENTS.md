# DeepPrep 项目协作规则

你是我的开发搭档，不是单纯的代码生成助手。

## 项目背景

这是我的秋招核心作品集——DeepPrep 智能备考平台。

目标：在有限时间内完成一个真正可以上线、可以放进简历、可以给面试官体验的产品。

所有建议请始终围绕：快速上线、产品展示价值、良好的用户体验、适合秋招展示。不要为了炫技术而增加复杂度。

## 关于我

我是 GitHub、部署、云服务方面的新手。如果方案涉及新概念，不要默认我知道，用一句话简单解释。不要长篇教学。

## 协作方式

- 不要一次完成整个项目。每次只完成一个阶段。每完成一个阶段后停止，等待确认。
- 每次开始工作前，告诉我：①为什么做这个 ②完成后得到什么 ③预计多久 ④有没有风险 ⑤是否需要我参与
- 如果你发现产品逻辑、页面流程、用户体验有可优化的地方，先告诉我建议和价值，等我确认后再改。

## 关于代码

优先保证：可以运行、不影响已有功能、代码简单清晰、可维护。不要为了追求高级写法增加复杂度。

## 关于方案

如果存在多个方案，不要替我决定。列出每个方案的优点、缺点，给出你的推荐，让我自己选。

## 技术栈

- 前端/后端：Streamlit
- 数据库：SQLite
- AI：SiliconFlow API（Qwen 系列模型）
- 部署：Streamlit Cloud

---

## 当前项目状态

### 已完成 ✅

- [x] Git 初始化 + 安全加固（移除硬编码 API Key）
- [x] GitHub 仓库：`dangbichanh71-ctrl/DeepPrep`（Private，分支 `main`）
- [x] Streamlit Cloud 部署：https://deepprep.streamlit.app
- [x] README.md（产品介绍风格）
- [x] 速度优化：prompt 精简，max_tokens 从 3000 降到 1500
- [x] 答案反馈按钮：解析下方增加"⚠️ 报告答案有误"
- [x] 全学科 prompt 适配：翻译题逐词拆解、数学题逐步计算、代码题算法推演
- [x] LaTeX 渲染修复：要求上标下标用花括号（x^{2}）
- [x] 知识点细化：prompt 要求具体标签（如"哈希表/散列查找"而非"数据结构"）

### 待推送 ⏳

本地有一个未推送的 commit：`speed and prompt optimization`，内容为 ai_utils.py + app.py + AGENTS.md 的修改。由于网络问题暂未推送到 GitHub。用户需要在自己终端执行 `git push`。

### 待完成 🔜

按优先级排列（参考完整计划：`C:\Users\Administrator\.Codex\plans\sunny-enchanting-meerkat.md`）：

| 优先级 | 任务 | 阶段 |
|--------|------|------|
| 🔴 当前 | 线上测试 6 道题，验证速度和质量改善 | 测试 |
| 🟡 下一步 | 首页 Dashboard 重设计（登录后第一眼） | 阶段二 |
| 🟡 下一步 | AI 错误友好处理（中文提示替代报错堆栈） | 阶段二 |
| 🟡 下一步 | 注册/登录页优化（展示产品价值主张） | 阶段二 |
| 🟡 下一步 | 侧边栏信息优化（用户身份、使用天数、错题数） | 阶段二 |
| 🔵 后续 | 产品文档撰写（PRD、用户故事、竞品分析） | 阶段三 |
| 🔵 后续 | 产品演示视频录制（2-3分钟） | 阶段三 |
| 🔵 后续 | GitHub 仓库改为 Public | 阶段三 |

### 重要链接

- GitHub 仓库：https://github.com/dangbichanh71-ctrl/DeepPrep
- 线上地址：https://deepprep.streamlit.app
- 完整计划文件：`C:\Users\Administrator\.Codex\plans\sunny-enchanting-meerkat.md`
- GitHub 用户名：dangbichanh71-ctrl
- Git 用户：luoyiguo / dangbichanh71@gmail.com

### 关键决策记录

1. 不迁移 PostgreSQL（SQLite 够用）
2. 不做移动端深度适配（面试官在 PC 上看）
3. 知识分类通过 knowledge_points 细化，不扩展学科大类
4. GitHub 先 Private 后 Public（文档完善后再公开）
5. 演示视频在阶段三（产品打磨完成后）录制
6. ai_utils.py 已加 frequency_penalty=0.5 + presence_penalty=0.3 + temperature 调至 0.3，修复 LLM 重复输出死循环
7. 本地还有解析报错未解决（待 Codex 看图定位）
