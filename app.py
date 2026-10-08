# -*- coding: utf-8 -*-
"""
单进程部署入口（本地 / ModelScope 创空间通用）
================================================
一个进程同时提供 FastAPI 接口和 Gradio 页面，无需分别启动 app_server.py 和 webui.py：

    本地启动：python app.py
    访问页面：http://127.0.0.1:7860

部署说明见 README.md「在线 Demo 部署（ModelScope）」一节。
"""
import os

# ============ 必须在 import webui 之前设置：前端 API 模块在 import 时读取该变量 ============
# 部署平台（如 ModelScope）通过 PORT 环境变量指定服务端口，本地默认 7860
PORT = int(os.environ.get("PORT", "7860"))
# 单进程模式下，Gradio 页面通过 HTTP 调用「同进程」的 FastAPI 接口
os.environ.setdefault("API_BASE_URL", f"http://127.0.0.1:{PORT}")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import gradio as gr

from chat.chat_routes import chat_router
from knowledgebase_server.kb_routes import kb_router
from configs.setting import MEDIA_DIR

# 导入 Gradio 页面（import 时完成 demo 构建）
from webui import demo

# 全新环境（云端容器）首次启动时静态目录可能不存在，提前创建，避免 StaticFiles 挂载报错
os.makedirs(MEDIA_DIR, exist_ok=True)

# ============ 构建 FastAPI 应用（与 app_server.py 保持一致）============
app = FastAPI(title="AI Agent RAG Chat")

# 允许跨域请求
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载后端接口路由
app.include_router(chat_router)
app.include_router(kb_router)

# 挂载静态文件目录
app.mount("/media", StaticFiles(directory=MEDIA_DIR), name="media")

# 将 Gradio 页面挂载到根路径 / ，实现单进程同时提供页面与接口
app = gr.mount_gradio_app(app, demo, path="/")


if __name__ == "__main__":
    import uvicorn

    # 0.0.0.0 保证云端容器外可访问；本地同样可用
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="info")
