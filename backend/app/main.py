# backend/app/main.py
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from langchain_core.messages import HumanMessage, AIMessage
from .agent_config import agent_executor
import json
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

# 允许跨域请求，前端通常在不同的端口运行
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # 允许所有来源，生产环境应限制为前端域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/chat")
async def chat_endpoint(request: Request):
    """
    处理聊天请求，通过 LangGraph Agent 流式生成响应。
    """
    try:
        data = await request.json()
        user_input = data.get("message")
        session_id = data.get("session_id", "default_session") # 用于Checkpointer，目前简化处理

        if not user_input:
            return JSONResponse({"error": "Message is required"}, status_code=400)

        async def generate_response_stream():
            inputs = {"messages": [HumanMessage(content=user_input)]}
            
            # 使用 LangGraph 的 astream_events 方法获取细粒度的事件流
            async for event in agent_executor.astream_events(inputs, version="v1", stream_mode="values"):
                kind = event["event"]
                payload = None

                if kind == "on_chat_model_stream":
                    # LLM 正在生成内容，以块的形式发送
                    chunk = event["data"].get("chunk")
                    if chunk and chunk.content:
                        payload = {"type": "llm_chunk", "content": chunk.content}
                elif kind == "on_tool_start":
                    # 工具开始被调用
                    tool_name = event["name"]
                    tool_input = event["data"].get("input", {})
                    payload = {"type": "tool_start", "tool_name": tool_name, "tool_input": tool_input}
                elif kind == "on_tool_end":
                    # 工具调用结束
                    tool_name = event["name"]
                    tool_output = event["data"].get("output", {})
                    payload = {"type": "tool_end", "tool_name": tool_name, "tool_output": str(tool_output)}
                elif kind == "on_agent_action":
                    # LangGraph 发现了一个 AgentAction，意味着要调用工具
                    # 这里可以更详细地发送工具调用信息
                    action = event["data"].get("input", {}).get("messages", [])[-1].tool_calls[0]  # type: ignore[union-attr]
                    payload = {"type": "agent_action_intent", "tool_name": action.name, "tool_args": action.args}
                elif kind == "on_agent_finish":
                    # Agent 最终完成，可能会有最终的 LLM 回复
                    final_output_messages = event["data"].get("output", {}).get("messages", [])
                    if final_output_messages:
                        # 找到最后一个 AIMessage 作为最终回复
                        final_ai_message = next((msg for msg in reversed(final_output_messages) if isinstance(msg, AIMessage)), None)
                        if final_ai_message and final_ai_message.content:
                            payload = {"type": "final_message", "content": final_ai_message.content}
                
                if payload:
                    yield f"data: {json.dumps(payload)}\n\n"
                
                # 确保每次迭代之间有短暂的暂停，避免CPU过度占用，并允许ASGI服务器发送数据
                await asyncio.sleep(0.01)

            yield "event: end\ndata: {}\n\n" # 发送结束事件

        return StreamingResponse(generate_response_stream(), media_type="text/event-stream")

    except json.JSONDecodeError:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)
    except Exception as e:
        print(f"Server error: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

