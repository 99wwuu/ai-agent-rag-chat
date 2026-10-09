import json
import asyncio
import os
import traceback
from ast import literal_eval
from fastapi import APIRouter, UploadFile, Form
from fastapi.responses import StreamingResponse
from tools.tools_select import tools
from typing import List, AsyncIterable
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain.agents import create_react_agent, AgentExecutor
from langchain.prompts import SystemMessagePromptTemplate, HumanMessagePromptTemplate
from configs.prompt import PROMPT_TEMPLATES
from configs.setting import chat_model_name, api_key, base_url, TIME_OUT, TEMP_FILE_STORAGE_DIR
from utils.callback import CustomAsyncIteratorCallbackHandler
from db_server.base import session
from db_server.knowledge_base_repository import list_kb_from_db
from tools.code_interpreter import code_interpreter
from utils.load_docs import get_file_content

# 初始化 FastAPI 应用
chat_router = APIRouter(prefix="/chat", tags=["Chat 对话"])


def files_rag(files, uuid):
    # 定义存储路径
    kb_file_storage_path = os.path.join(TEMP_FILE_STORAGE_DIR, uuid)
    result = []
    # 确保存储目录存在
    os.makedirs(kb_file_storage_path, exist_ok=True)
    if files:
        for file in files:
            # 保存文件到指定路径
            file_path = os.path.join(kb_file_storage_path, file.filename)

            with open(file_path, "wb") as f:
                f.write(file.file.read())

    # 遍历目录中的所有文件并读取内容
    for filename in os.listdir(kb_file_storage_path):
        file_path = os.path.join(kb_file_storage_path, filename)
        if os.path.isfile(file_path):
            file_content = get_file_content(file_path)

            # 直接将路径和内容拼接到结果字符串
            result.append(f"document:.{file_path}\ncontent:{file_content}\n")
    return "".join(result)


@chat_router.post("/agent_chat")
async def agent_chat(
        files: List[UploadFile] = None,
        query: str = Form(..., description="用户输入"),
        sys_prompt: str = Form("You are a helpful assistant.", description="系统提示"),
        history_len: int = Form(-1, description="保留历史消息的数量"),
        history: List[str] = Form([], description="历史对话"),
        temperature: float = Form(0.5, description="LLM采样温度"),
        max_tokens: int = Form(1024, description="LLM最大token数配置"),
        session_id: str = Form(None, description="会话标识"),
):
    documents = files_rag(files, session_id)
    history = [literal_eval(item) for item in history]
    # 控制历史记录长度，保留指定数量的消息
    histories = ""
    if history_len > 0:
        history = history[-2 * history_len:]
    
    # 在消息列表中加入历史消息
    for msg in history:
        role = msg.get('role')
        content = msg.get('content')
        histories += f"{role}:{content}\n\n"

    async def agent_chat_iterator() -> AsyncIterable[str]:
        task = None

        def pack(data: dict) -> bytes:
            # 每条消息以换行分隔，方便前端按行解析，避免 JSON 粘包/拆包
            return (json.dumps(data, ensure_ascii=False) + "\n").encode("utf-8")

        try:
            # 使用自己定义的回调处理函数
            callback = CustomAsyncIteratorCallbackHandler()
            callbacks = [callback]

            # 定义聊天模型
            chat_model = ChatOpenAI(
                model=chat_model_name,
                api_key=api_key,
                base_url=base_url,
                temperature=temperature,
                max_tokens=max_tokens,
                streaming=True,
                callbacks=callbacks
            )

            # 定义系统提示，用于设置行为规则
            system_prompt = SystemMessagePromptTemplate.from_template(
                sys_prompt
            )

            # 定义人类提示，用于用户输入
            human_prompt = HumanMessagePromptTemplate.from_template(
                PROMPT_TEMPLATES["agent"]
            )
            # 组装成完整的 ChatPromptTemplate
            chat_prompt = ChatPromptTemplate.from_messages([system_prompt, human_prompt])

            # 创建代理
            agent = create_react_agent(chat_model, tools, chat_prompt, stop_sequence=["\nObserv"])
            agent_executor = AgentExecutor.from_agent_and_tools(
                agent=agent,
                tools=tools,
                verbose=True,
            )

            # 列出所有的知识库
            knowledgebases = list_kb_from_db(session)
            # 整理成字符串
            kbs = "".join([f"{kb['kb_name']} - {kb['kb_info']} \n" for kb in knowledgebases])
            code_interpreter.output_files, code_interpreter.output_codes = "", ""
            # 开启异步任务执行agent
            task = asyncio.create_task(
                agent_executor.acall(
                    inputs={"input": query, "history": histories, "knowledgebases": kbs, "documents": documents})
            )

            # 流式输出：队列token / done事件 / agent任务结束，三者竞速
            # 任务异常结束时也能立刻退出循环，不会一直挂起
            while True:
                token_task = asyncio.ensure_future(callback.queue.get())
                done_task = asyncio.ensure_future(callback.done.wait())
                finished, _ = await asyncio.wait(
                    {token_task, done_task, task},
                    return_when=asyncio.FIRST_COMPLETED,
                )

                if token_task in finished and not token_task.cancelled():
                    token = token_task.result()
                    if done_task not in finished:
                        done_task.cancel()
                    if token:
                        yield pack({"answer": token})
                    # 任务和 done 事件都未结束，继续取下一个 token
                    if task not in finished and done_task not in finished:
                        continue

                if done_task not in finished:
                    done_task.cancel()
                if token_task not in finished:
                    token_task.cancel()

                # done 事件或 agent 任务已结束，排空队列中剩余 token 后退出
                while not callback.queue.empty():
                    yield pack({"answer": callback.queue.get_nowait()})
                break

            # 等待 agent 任务真正结束；若任务内部抛异常（如 API 402/网络错误），这里会抛出
            await asyncio.wait_for(task, TIME_OUT)
            output_files, output_codes = code_interpreter.get_outputs()

            # 最后将输出文件列表发送
            if output_files:
                yield pack({"answer": f'\n\n{output_codes}\n\n![](http://localhost:6605{output_files})'})
            else:
                yield pack({"answer": f'\n\n{output_codes}'})

        except asyncio.TimeoutError:
            if task is not None:
                task.cancel()
            traceback.print_exc()
            yield pack({"answer": "\n\n[错误] 模型响应超时，请稍后重试或简化问题。"})
        except Exception as e:
            # 关键：任何异常都转成一条正常消息返回，保证 HTTP 流正常结束，
            # 前端不会再出现 ChunkedEncodingError: Response ended prematurely（响应提前结束）
            if task is not None and not task.done():
                task.cancel()
            traceback.print_exc()
            yield pack({"answer": f"\n\n[服务端错误] {type(e).__name__}: {e}"})

    # 返回 StreamingResponse，以流的形式发送数据
    return StreamingResponse(agent_chat_iterator(), media_type="application/json")
