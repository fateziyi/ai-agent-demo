<template>
  <div class="chat-container">
    <div class="messages" ref="messageContainer">
      <div v-for="(msg, index) in messages" :key="index" :class="['message-item', msg.sender]">
        <!-- 用户消息 -->
        <div v-if="msg.sender === 'user'" class="user-bubble">{{ msg.content }}</div>

        <!-- Agent 正在思考/流式输出 -->
        <div v-else-if="msg.type === 'llm_chunk' && msg.content" class="agent-bubble">
          {{ msg.content }}
        </div>
        <div v-else-if="msg.type === 'llm_final' && msg.content" class="agent-bubble">
          {{ msg.content }}
        </div>

        <!-- Agent 意图调用工具 -->
        <div v-else-if="msg.type === 'agent_action_intent'" class="tool-status tool-pending">
          <p>
            🤖 正在思考... 准备调用工具: <b>{{ msg.tool_name }}</b>
          </p>
          <pre>{{ JSON.stringify(msg.tool_args, null, 2) }}</pre>
        </div>

        <!-- 工具开始调用 -->
        <div v-else-if="msg.type === 'tool_start'" class="tool-status tool-pending">
          <p>
            ⚙️ 正在执行工具: <b>{{ msg.tool_name }}</b>
          </p>
          <pre v-if="msg.tool_input">{{ JSON.stringify(msg.tool_input, null, 2) }}</pre>
        </div>

        <!-- 工具调用结束 -->
        <div v-else-if="msg.type === 'tool_end'" class="tool-status tool-success">
          <p>
            ✅ 工具 <b>{{ msg.tool_name }}</b> 执行完毕！
          </p>
          <pre>{{ msg.tool_output }}</pre>
        </div>

        <!-- 错误消息 -->
        <div v-else-if="msg.type === 'error'" class="error-bubble">
          <span>❌ 错误:</span> {{ msg.content }}
        </div>
      </div>
      <div v-if="isLoading" class="loading-indicator">
        <span class="dot">.</span><span class="dot">.</span><span class="dot">.</span>
      </div>
    </div>

    <div class="input-area">
      <textarea
        v-model="userInput"
        @keyup.enter.prevent="sendMessage"
        placeholder="输入你的指令..."
        :disabled="isLoading"
        rows="1"
        autoresize
      ></textarea>
      <button @click="sendMessage" :disabled="isLoading">发送</button>
    </div>
  </div>
</template>

<script setup>
import { ref, nextTick } from 'vue';

const messages = ref([]); // 存储所有消息的数组
const userInput = ref(''); // 用户输入
const isLoading = ref(false); // 加载状态，防止重复发送
const messageContainer = ref(null); // 消息容器的引用，用于滚动

let currentLLMMessageIndex = -1; // 用于追踪当前 Agent 正在流式输出的 LLM 消息的索引

// 自动滚动到底部
const scrollToBottom = () => {
  nextTick(() => {
    if (messageContainer.value) {
      messageContainer.value.scrollTop = messageContainer.value.scrollHeight;
    }
  });
};

const sendMessage = async () => {
  if (!userInput.value.trim() || isLoading.value) return;

  const userMessage = userInput.value;
  messages.value.push({ sender: 'user', content: userMessage, type: 'user' });
  userInput.value = '';
  isLoading.value = true;
  currentLLMMessageIndex = -1; // 重置 LLM 消息索引
  scrollToBottom();

  try {
    const response = await fetch('/chat', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ message: userMessage }),
    });

    if (!response.body) {
      throw new Error('ReadableStream not supported or no body in response');
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder('utf-8');
    let buffer = ''; // 用于存储不完整的 SSE 数据
    
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      // SSE 消息通过双换行符分隔
      let lines = buffer.split('\n\n');
      buffer = lines.pop(); // 保留可能不完整的最后一行

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            const data = JSON.parse(line.substring(6)); // 移除 "data: " 前缀
            
            if (data.type === 'llm_chunk') {
              // 如果是新的 LLM 响应或者首次接收到 LLM 块
              if (currentLLMMessageIndex === -1 || messages.value[currentLLMMessageIndex].type !== 'llm_chunk') {
                messages.value.push({ sender: 'agent', type: 'llm_chunk', content: data.content });
                currentLLMMessageIndex = messages.value.length - 1;
              } else {
                // 追加内容到现有 LLM 消息
                messages.value[currentLLMMessageIndex].content += data.content;
              }
            } else if (data.type === 'tool_start' || data.type === 'agent_action_intent') {
              // 工具调用开始或意图
              messages.value.push({
                sender: 'agent',
                type: data.type,
                tool_name: data.tool_name,
                tool_input: data.tool_input || data.tool_args,
              });
              currentLLMMessageIndex = -1; // 重置 LLM 消息索引，因为 Agent 转向工具
            } else if (data.type === 'tool_end') {
              // 工具调用结束
              messages.value.push({
                sender: 'agent',
                type: 'tool_end',
                tool_name: data.tool_name,
                tool_output: data.tool_output,
              });
              currentLLMMessageIndex = -1; // 重置 LLM 消息索引
            } else if (data.type === 'final_message') {
                // 最终的 LLM 消息，可能覆盖之前的流式内容
                if (currentLLMMessageIndex !== -1 && messages.value[currentLLMMessageIndex].type === 'llm_chunk') {
                    messages.value[currentLLMMessageIndex].content = data.content; // 更新最终内容
                    messages.value[currentLLMMessageIndex].type = 'llm_final'; // 标记为最终消息
                } else {
                    messages.value.push({ sender: 'agent', type: 'llm_final', content: data.content });
                }
                currentLLMMessageIndex = -1;
            }
            scrollToBottom();
          } catch (e) {
            console.error("Failed to parse SSE data:", line, e);
          }
        } else if (line.startsWith('event: end')) {
            break; // 收到结束事件
        }
      }
    }
  } catch (error) {
    console.error('Error fetching response:', error);
    messages.value.push({ sender: 'agent', type: 'error', content: `发生错误: ${error.message}` });
  } finally {
    isLoading.value = false;
    scrollToBottom();
  }
};
</script>

<style scoped>
.chat-container {
  display: flex;
  flex-direction: column;
  height: 85vh; /* 调整高度以适应 */
  max-width: 900px;
  margin: 20px auto;
  border: 1px solid #e0e0e0;
  border-radius: 12px;
  overflow: hidden;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
  background-color: #ffffff;
}

.messages {
  flex-grow: 1;
  padding: 15px;
  overflow-y: auto;
  background-color: #fcfcfc;
  scroll-behavior: smooth;
}

.message-item {
  margin-bottom: 12px;
  display: flex;
  align-items: flex-start;
}

.user {
  justify-content: flex-end;
}

.agent {
  justify-content: flex-start;
}

.user-bubble {
  background-color: #007bff;
  color: white;
  padding: 10px 15px;
  border-radius: 18px 18px 2px 18px;
  max-width: 65%;
  word-wrap: break-word;
  font-size: 0.95em;
  line-height: 1.5;
}

.agent-bubble {
  background-color: #e9ecef;
  color: #343a40;
  padding: 10px 15px;
  border-radius: 18px 18px 18px 2px;
  max-width: 65%;
  word-wrap: break-word;
  font-size: 0.95em;
  line-height: 1.5;
}

.tool-status {
  font-size: 0.85em;
  padding: 8px 12px;
  border-radius: 8px;
  margin-left: 5px;
  max-width: 65%;
  word-wrap: break-word;
  line-height: 1.4;
}

.tool-status p {
  margin: 0 0 5px 0;
  font-weight: bold;
  display: flex;
  align-items: center;
}
.tool-status pre {
  background-color: rgba(0, 0, 0, 0.05);
  padding: 5px;
  border-radius: 4px;
  white-space: pre-wrap; /* 保持格式，但允许换行 */
  word-break: break-all;
  font-family: 'Cascadia Code', 'Fira Code', monospace;
  font-size: 0.8em;
}

.tool-pending {
  background-color: #e6f7ff;
  border-left: 4px solid #1890ff;
  color: #0056b3;
}

.tool-success {
  background-color: #f6ffed;
  border-left: 4px solid #52c41a;
  color: #28a745;
}

.error-bubble {
  background-color: #ffebe9;
  border-left: 4px solid #dc3545;
  color: #dc3545;
  padding: 10px 15px;
  border-radius: 8px;
  max-width: 65%;
  word-wrap: break-word;
  font-size: 0.9em;
}
.error-bubble span {
    font-weight: bold;
}

.loading-indicator {
  text-align: center;
  padding: 10px 0;
  font-size: 1.2em;
  color: #6c757d;
}

.dot {
  animation: blink 1s infinite;
}
.dot:nth-child(2) {
  animation-delay: 0.2s;
}
.dot:nth-child(3) {
  animation-delay: 0.4s;
}

@keyframes blink {
  0%, 80%, 100% { opacity: 0; }
  40% { opacity: 1; }
}

.input-area {
  display: flex;
  padding: 10px;
  border-top: 1px solid #eee;
  background-color: #f8f9fa;
  align-items: flex-end; /* 使按钮和文本框底部对齐 */
}

.input-area textarea {
  flex-grow: 1;
  padding: 10px;
  border: 1px solid #ced4da;
  border-radius: 6px;
  margin-right: 10px;
  font-size: 1em;
  line-height: 1.5;
  resize: none; /* 禁用用户手动调整大小 */
  min-height: 38px; /* 至少显示一行 */
  max-height: 150px; /* 最大高度 */
  box-shadow: inset 0 1px 2px rgba(0, 0, 0, 0.075);
}

.input-area button {
  padding: 10px 20px;
  background-color: #007bff;
  color: white;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 1em;
  font-weight: 500;
  transition: background-color 0.2s ease;
}

.input-area button:hover:not(:disabled) {
  background-color: #0056b3;
}

.input-area button:disabled {
  background-color: #a0cfff;
  cursor: not-allowed;
}
</style>
