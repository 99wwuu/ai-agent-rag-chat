# AI 智能体知识库问答系统

基于 **LangChain + FastAPI** 的 AI 智能体对话系统，支持 ReAct Agent 自主工具调用、RAG 知识库混合检索与流式输出。

## 功能特性

- 🤖 **ReAct Agent**：大模型根据问题自主决策调用工具（天气查询、网络搜索、代码执行、知识库检索、计算器等）
- 📚 **RAG 知识库**：文档上传后自动切块、向量化并持久化存储，支持基于私有文档的问答
- 🔀 **混合检索**：FAISS 语义检索 + BM25 关键词检索加权融合，jieba 中文分词，召回更全面
- 💬 **流式输出**：基于 asyncio 的异步流式响应，打字机效果逐字返回
- 📎 **临时文档问答**：上传文件无需建库，可直接作为上下文提问
- 🛡️ **健壮性设计**：超时/异常统一兜底，保证流式响应不中断

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | Gradio（聊天页 + 知识库管理页） |
| 后端框架 | FastAPI + Uvicorn |
| Agent 框架 | LangChain（create_react_agent / AgentExecutor） |
| 大模型 | Qwen2.5-72B-Instruct（硅基流动 OpenAI 兼容接口） |
| 向量检索 | FAISS + bge-large-zh Embedding |
| 关键词检索 | BM25 + jieba 分词（EnsembleRetriever 加权融合） |
| 数据存储 | SQLite + SQLAlchemy（知识库台账） |
| 异步机制 | asyncio（Queue / Event / create_task / StreamingResponse） |

## 系统架构

```
Gradio 页面（聊天 / 知识库管理）
        │
FastAPI 接口层（/chat/agent_chat、/knowledgebase/*）
        │
LangChain ReAct Agent（Qwen2.5 + 工具集）
        │
   ┌────┴─────────────┐
工具调用（天气/搜索/    RAG 检索层
代码执行/计算器）      FAISS 语义检索 + BM25 关键词检索
        │              EnsembleRetriever 加权融合
        └────┬─────────┘
             ▼
   SQLite（知识库台账）+ 本地文件（FAISS 向量库、文档）
```

## 快速开始

```bash
# 1. 安装依赖
pip install fastapi uvicorn langchain langchain-openai langchain-community faiss-cpu sqlalchemy jieba gradio requests

# 2. 配置 API Key（硅基流动），设置环境变量
#    Windows PowerShell:
setx SILICONFLOW_API_KEY "你的API Key"

# 3. 启动后端服务
python app_server.py
# 接口文档：http://127.0.0.1:6605/docs

# 4. 启动前端页面
python webui.py
```

## 核心流程

**RAG 文档入库**：加载文档（txt/pdf/csv/md）→ 文本切块（chunk_size=128，overlap=20）→ Embedding 向量化 → 存入 FAISS 持久化

**Agent 对话**：用户提问 → ReAct 循环（Thought → Action → Observation）自主选择工具/知识库 → 检索结果拼入 Prompt → 流式生成回答

## 项目亮点

- **混合检索策略**：针对 FAISS 语义检索精确匹配弱、BM25 不懂同义词的问题，使用 EnsembleRetriever 按 0.5/0.5 权重融合，显著提升召回率
- **异步流式架构**：Agent 后台任务执行，主循环通过 asyncio.wait 竞速监听 token 队列、结束信号与任务状态，配合自定义 Callback 实现稳定的流式输出
- **可扩展工具设计**：工具基于统一接口封装，可快速扩展（如新增计算器工具，并针对 eval 设计了字符白名单 + 禁用内置函数的双层安全防护）
- **密钥安全管理**：API Key 通过环境变量注入，配合 .gitignore 避免凭据泄露
