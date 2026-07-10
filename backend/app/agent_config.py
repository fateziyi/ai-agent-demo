# backend/app/agent_config.py
from typing import TypedDict, Annotated
import operator
from langchain_core.messages import BaseMessage, ToolMessage
from langchain_core.tools import tool  # type: ignore
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END  # type: ignore
import os
from dotenv import load_dotenv
from pathlib import Path
from pydantic import SecretStr

# 显式指定 .env 文件路径，确保无论从哪个目录运行都能找到
_env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_env_path, override=True)

# 根据 LLM_PROVIDER 选择对应的 LLM 配置
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "qwen")

# 保存并清除 OpenAI 环境变量，防止 ChatOpenAI 从中自动推断默认配置。
# 当使用 qwen/anthropic 等非 OpenAI 提供商时，OPENAI_API_KEY 等变量
# 会干扰 ChatOpenAI 的 Pydantic 初始化，导致 model/api_key/base_url 被覆盖。
_saved_openai_env = {}
_openai_env_keys = [
    "OPENAI_API_KEY", "OPENAI_MODEL", "OPENAI_BASE_URL",
    "OPENAI_ORGANIZATION", "OPENAI_PROJECT",
]
if LLM_PROVIDER != "openai":
    for key in _openai_env_keys:
        val = os.environ.pop(key, None)
        if val is not None:
            _saved_openai_env[key] = val


def _create_llm():
    """根据 .env 中的 LLM_PROVIDER 创建对应的 LLM 实例。"""
    if LLM_PROVIDER == "openai":
        # 恢复 OpenAI 环境变量
        for key, val in _saved_openai_env.items():
            os.environ[key] = val
        return ChatOpenAI(
            model=os.getenv("OPENAI_MODEL", "gpt-4o"),
            api_key=SecretStr(os.getenv("OPENAI_API_KEY", "")),
            base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            temperature=0,
        )
    elif LLM_PROVIDER == "anthropic":
        return ChatOpenAI(
            model=os.getenv("ANTHROPIC_MODEL", "claude-opus-4-6"),
            api_key=SecretStr(os.getenv("ANTHROPIC_API_KEY", "")),
            base_url=os.getenv("ANTHROPIC_BASE_URL"),
            temperature=0,
        )
    else:  # qwen（默认）
        return ChatOpenAI(
            model=os.getenv("QWEN_MODEL", "qwen-plus"),
            api_key=SecretStr(os.getenv("DASHSCOPE_API_KEY", "")),
            base_url=os.getenv("QWEN_BASE_URL"),
            temperature=0,
        )


llm = _create_llm()
# 1. 定义 Agent 状态
class AgentState(TypedDict):
    """
    Agent 的状态。
    messages: 用于追踪对话历史和 Agent 内部思考的所有消息。
    """
    messages: Annotated[list[BaseMessage], operator.add]

# 2. 定义可供 Agent 调用的工具
# 模拟一个简单的任务管理系统
task_list = [] # 存储任务的简单列表

@tool
def add_task(description: str, due_date: str = "今天") -> str:
    """
    向任务列表中添加一个新任务。
    Args:
        description (str): 任务的详细描述。
        due_date (str): 任务的截止日期或时间，默认为"今天"。
    Returns:
        str: 任务添加成功或失败的反馈信息。
    """
    task_id = len(task_list) + 1
    task_list.append({"id": task_id, "description": description, "due_date": due_date, "completed": False})
    print(f"DEBUG: 任务已添加 - ID:{task_id}, 描述:'{description}', 日期:'{due_date}'")
    return f"任务 '{description}' 已添加到您的列表，截止日期：{due_date}。任务ID：{task_id}"

@tool
def list_tasks(status: str = "all") -> str:
    """
    列出所有待办、已完成或全部任务。
    Args:
        status (str): 任务状态，可以是 "all", "pending", "completed"。默认为 "all"。
    Returns:
        str: 格式化的任务列表字符串。
    """
    filtered_tasks = []
    if status == "pending":
        filtered_tasks = [t for t in task_list if not t["completed"]]
    elif status == "completed":
        filtered_tasks = [t for t in task_list if t["completed"]]
    else: # "all"
        filtered_tasks = task_list

    if not filtered_tasks:
        return f"当前没有{status}状态的任务。"
    
    tasks_str = "您的任务列表：\n"
    for task in filtered_tasks:
        status_str = " (已完成)" if task["completed"] else " (待办)"
        tasks_str += f"- ID {task['id']}: {task['description']} (截止: {task['due_date']}){status_str}\n"
    print(f"DEBUG: 任务列表已查询 - 状态:'{status}'")
    return tasks_str

@tool
def complete_task(task_id: int) -> str:
    """
    将指定ID的任务标记为已完成。
    Args:
        task_id (int): 要标记为已完成的任务的ID。
    Returns:
        str: 任务完成状态更新的反馈信息。
    """
    for task in task_list:
        if task["id"] == task_id:
            task["completed"] = True
            print(f"DEBUG: 任务已完成 - ID:{task_id}")
            return f"任务 '{task['description']}' (ID: {task_id}) 已标记为已完成。"
    print(f"DEBUG: 尝试完成任务，但未找到ID:{task_id}")
    return f"未找到ID为 {task_id} 的任务。"

all_tools = [add_task, list_tasks, complete_task]

# 3. 将工具绑定到 LLM（llm 已在上方通过 _create_llm() 创建）
llm_with_tools = llm.bind_tools(all_tools)

# 4. 定义 LangGraph 节点和路由逻辑

def call_model(state: AgentState):
    """
    Agent 的主要 LLM 调用节点。
    它将所有消息发送给 LLM，并返回 LLM 的响应。
    """
    messages = state["messages"]
    response = llm_with_tools.invoke(messages)
    return {"messages": [response]}

def call_tool(state: AgentState):
    """
    Agent 的工具调用节点。
    它根据 LLM 的响应，执行相应的工具。
    """
    last_message = state["messages"][-1]
    tool_outputs = []
    
    # 遍历 LLM 识别出的所有工具调用
    for tool_call in last_message.tool_calls:  # type: ignore[union-attr]
        tool_name = tool_call.name
        tool_args = tool_call.args
        print(f"DEBUG: 正在调用工具 '{tool_name}'，参数: {tool_args}")
        try:
            # 找到对应的工具函数并执行
            chosen_tool = next(t for t in all_tools if t.name == tool_name)
            output = chosen_tool.invoke(tool_args)
            tool_outputs.append(ToolMessage(content=str(output), tool_call_id=tool_call.id))
        except Exception as e:
            error_message = f"调用工具 '{tool_name}' 时发生错误: {e}"
            print(f"ERROR: {error_message}")
            tool_outputs.append(ToolMessage(content=error_message, tool_call_id=tool_call.id))
    
    return {"messages": tool_outputs}

def should_continue(state: AgentState) -> str:
    """
    根据最新消息判断 Agent 是否应该继续执行。
    如果 LLM 响应中包含工具调用，则进入 'call_tool' 节点；否则，Agent 认为任务完成，结束。
    """
    last_message = state["messages"][-1]
    if last_message.tool_calls:  # type: ignore[union-attr]
        return "continue"
    else:
        return "end"

# 5. 构建 LangGraph 流程
workflow = StateGraph(AgentState)

workflow.add_node("llm", call_model)
workflow.add_node("tools", call_tool)

workflow.set_entry_point("llm") # 入口点是 LLM
workflow.add_conditional_edges(
    "llm",        # 从 LLM 节点开始
    should_continue, # 根据 should_continue 函数判断走向
    {
        "continue": "tools", # 如果需要继续，则走向 tools 节点
        "end": END           # 如果不需要，则结束
    }
)
workflow.add_edge("tools", "llm") # 工具执行完毕后，将工具输出返回给 LLM 继续处理

# 编译 Agent
agent_executor = workflow.compile()