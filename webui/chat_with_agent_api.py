# 定义后台 API 的 URL
import json
import requests

chat_with_agent_url = "http://127.0.0.1:6605/chat/agent_chat"
chat_url = "http://127.0.0.1:6605/chat/chat"


def chat_with_agent(prompt, history, sys_prompt, history_len, temperature, max_tokens, stream, session_id):
    # 构建文件和表单数据
    files = [('files', (open(file_path["path"], 'rb'))) for file_path in prompt["files"]]
    if prompt["files"] != []:
        # 提取文件路径并拼接到 query 中
        query = f'{prompt["text"]}\n' + "".join(prompt["files"][0]["path"])
    else:
        query = f'{prompt["text"]}\n'
    # 构建请求数据
    data = {
        "query": query,
        "sys_prompt": sys_prompt,
        "history_len": history_len,
        "history": [str(h) for h in history],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "session_id": session_id,
    }

    # 发送请求到 FastAPI 后端
    chunks = ""
    try:
        # timeout=(连接超时, 读取超时)：后端每条消息结束后都会正常关闭流，长时间无数据视为异常
        response = requests.post(chat_with_agent_url, files=files, data=data, stream=True, timeout=(10, 300))
        if response.status_code != 200:
            yield "请求失败，请检查后台服务器（app_server.py）是否正常运行。"
            return

        # 后端按行返回 JSON（每行一个 {"answer": ...}），
        # 用缓冲区按行解析，避免网络分包/粘包导致 json.loads 报错
        buffer = ""
        for piece in response.iter_content(chunk_size=None, decode_unicode=True):
            if not piece:
                continue
            buffer += piece
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                chunks += obj.get("answer", "")
                if stream:
                    yield chunks

        # 处理最后一行（没有换行符结尾的情况）
        buffer = buffer.strip()
        if buffer:
            obj = json.loads(buffer)
            chunks += obj.get("answer", "")

        # 非流式模式下最后一次性返回；流式模式下再刷新一次最终结果
        yield chunks

    except Exception as e:
        # 连接中断、JSON解析失败等异常，把已生成的内容和错误信息一起展示
        err_msg = f"发生错误：{type(e).__name__}: {e}"
        yield f"{chunks}\n\n{err_msg}" if chunks else err_msg
