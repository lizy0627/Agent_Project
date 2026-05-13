// 后端聊天接口地址，与当前 FastAPI 项目的 /chat 路由保持一致。
const CHAT_API_URL = "/chat";

// localStorage 键名：保存当前会话 ID 和当前会话消息。
const CONVERSATION_ID_KEY = "agent_project_conversation_id";
const MESSAGES_KEY_PREFIX = "agent_project_messages_";

// 获取页面元素，后续用于渲染消息、读取输入和切换状态。
const chatForm = document.querySelector("#chatForm");
const messageInput = document.querySelector("#messageInput");
const messageList = document.querySelector("#messageList");
const sendButton = document.querySelector("#sendButton");
const statusText = document.querySelector("#statusText");
const conversationIdText = document.querySelector("#conversationIdText");
const newConversationButton = document.querySelector("#newConversationButton");

// 当前后端 ChatRequest 只需要 message；conversationId 先在前端保存，方便后续扩展多轮对话。
let conversationId = getOrCreateConversationId();
let messages = loadMessages(conversationId);
let isLoading = false;

// 初始化页面状态。
conversationIdText.textContent = conversationId;
renderMessages();
autoResizeInput();
messageInput.focus();

// 获取已有会话 ID；如果没有，就生成一个新的会话 ID。
function getOrCreateConversationId() {
  const savedId = localStorage.getItem(CONVERSATION_ID_KEY);
  if (savedId) {
    return savedId;
  }

  const newId = createConversationId();
  localStorage.setItem(CONVERSATION_ID_KEY, newId);
  return newId;
}

// 生成浏览器端会话 ID，优先使用 crypto.randomUUID。
function createConversationId() {
  if (window.crypto && typeof window.crypto.randomUUID === "function") {
    return window.crypto.randomUUID();
  }

  return `conv-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

// 根据会话 ID 拼接消息存储键名。
function getMessagesKey(id) {
  return `${MESSAGES_KEY_PREFIX}${id}`;
}

// 从 localStorage 读取当前会话的历史消息。
function loadMessages(id) {
  const rawMessages = localStorage.getItem(getMessagesKey(id));
  if (!rawMessages) {
    return [];
  }

  try {
    return JSON.parse(rawMessages);
  } catch {
    return [];
  }
}

// 保存当前会话消息，后续刷新页面也能恢复上下文展示。
function saveMessages() {
  localStorage.setItem(getMessagesKey(conversationId), JSON.stringify(messages));
}

// 渲染整个消息列表。
function renderMessages() {
  messageList.innerHTML = "";

  if (messages.length === 0) {
    renderEmptyState();
    return;
  }

  messages.forEach((message) => {
    appendMessageElement(message);
  });

  scrollToBottom();
}

// 渲染空会话状态。
function renderEmptyState() {
  const emptyState = document.createElement("div");
  emptyState.className = "empty-state";
  emptyState.innerHTML = `
    <div class="empty-state-card">
      <span class="empty-badge">Local Agent Console</span>
      <h2>今天想让 Agent 做什么？</h2>
      <p>可以让它解释概念、整理思路、生成代码草稿，或把一个模糊需求拆成可执行步骤。</p>
      <div class="prompt-grid">
        <button class="prompt-card" type="button">帮我总结一下 FastAPI 项目的结构</button>
        <button class="prompt-card" type="button">给我一个适合初学者的 Agent 学习路线</button>
        <button class="prompt-card" type="button">帮我把一个需求拆成开发任务</button>
        <button class="prompt-card" type="button">解释一下 DashScope API 的调用流程</button>
      </div>
    </div>
  `;
  messageList.appendChild(emptyState);

  // 示例问题按钮会把文本填入输入框，方便快速发起第一条消息。
  emptyState.querySelectorAll(".prompt-card").forEach((button) => {
    button.addEventListener("click", () => {
      messageInput.value = button.textContent;
      autoResizeInput();
      messageInput.focus();
    });
  });
}

// 添加一条消息到页面。
function appendMessage(message) {
  messages.push(message);
  saveMessages();
  removeEmptyState();
  appendMessageElement(message);
  scrollToBottom();
}

// 创建单条消息 DOM，保留 meta 容器以便后续展示工具调用或 RAG 来源。
function appendMessageElement(message) {
  const messageItem = document.createElement("article");
  messageItem.className = `message ${message.role}-message`;
  messageItem.dataset.messageId = message.id;

  const content = document.createElement("div");
  content.className = "message-content";

  const bubble = document.createElement("div");
  bubble.className = "message-bubble";

  if (message.type === "loading") {
    bubble.appendChild(createTypingIndicator());
  } else {
    bubble.textContent = message.content;
  }

  const meta = document.createElement("div");
  meta.className = "message-meta";
  meta.textContent = message.createdAt || "";

  content.appendChild(bubble);
  content.appendChild(meta);
  messageItem.appendChild(content);
  messageList.appendChild(messageItem);
}

// 创建“Agent 正在思考...”的加载状态。
function createTypingIndicator() {
  const wrapper = document.createElement("span");
  wrapper.className = "typing-indicator";
  wrapper.setAttribute("aria-label", "Agent 正在思考...");

  const label = document.createElement("span");
  label.textContent = "Agent 正在思考";
  wrapper.appendChild(label);

  for (let index = 0; index < 3; index += 1) {
    const dot = document.createElement("span");
    dot.className = "typing-dot";
    wrapper.appendChild(dot);
  }

  return wrapper;
}

// 移除空会话欢迎态。
function removeEmptyState() {
  const emptyState = messageList.querySelector(".empty-state");
  if (emptyState) {
    emptyState.remove();
  }
}

// 更新指定消息内容，常用于把加载状态替换为 Agent 回复或错误提示。
function updateMessage(messageId, updates) {
  messages = messages.map((message) => {
    if (message.id !== messageId) {
      return message;
    }

    return {
      ...message,
      ...updates,
    };
  });

  saveMessages();
  renderMessages();
}

// 将消息区滚动到底部。
function scrollToBottom() {
  messageList.scrollTop = messageList.scrollHeight;
}

// 获取当前时间，用于轻量显示消息产生时间。
function getCurrentTime() {
  return new Intl.DateTimeFormat("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date());
}

// 创建消息对象，统一消息结构，方便后续扩展工具调用和 RAG 数据。
function createMessage(role, content, type = "text") {
  return {
    id: `msg-${Date.now()}-${Math.random().toString(16).slice(2)}`,
    role,
    type,
    content,
    createdAt: getCurrentTime(),
    toolCalls: [],
    ragSources: [],
  };
}

// 设置加载状态，避免请求过程中重复提交。
function setLoading(nextLoading) {
  isLoading = nextLoading;
  sendButton.disabled = nextLoading;
  messageInput.disabled = nextLoading;
  sendButton.textContent = nextLoading ? "发送中" : "发送";
  statusText.textContent = nextLoading ? "Agent 正在思考..." : "准备就绪";
}

// 调整 textarea 高度，让多行输入自然展开。
function autoResizeInput() {
  messageInput.style.height = "auto";
  messageInput.style.height = `${Math.min(messageInput.scrollHeight, 180)}px`;
}

// 调用后端 /chat 接口，并返回 Agent 回复文本。
async function requestAgentReply(message) {
  const requestBody = {
    message,
  };

  const response = await fetch(CHAT_API_URL, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(requestBody),
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(errorText || `请求失败，状态码：${response.status}`);
  }

  const data = await response.json();
  return data.reply || "Agent 没有返回文本内容。";
}

// 发送当前输入框中的消息。
async function sendCurrentMessage() {
  if (isLoading) {
    return;
  }

  const userText = messageInput.value.trim();
  if (!userText) {
    return;
  }

  appendMessage(createMessage("user", userText));
  messageInput.value = "";
  autoResizeInput();

  const loadingMessage = createMessage("agent", "", "loading");
  appendMessage(loadingMessage);
  setLoading(true);

  try {
    const reply = await requestAgentReply(userText);
    updateMessage(loadingMessage.id, {
      type: "text",
      content: reply,
      role: "agent",
      createdAt: getCurrentTime(),
    });
  } catch (error) {
    updateMessage(loadingMessage.id, {
      type: "text",
      role: "error",
      content: `请求出错：${error.message}。请确认后端已启动，并且 .env 中的 API Key 正确。`,
      createdAt: getCurrentTime(),
    });
  } finally {
    setLoading(false);
    messageInput.focus();
  }
}

// 新建对话：生成新会话 ID，并清空当前页面消息。
function startNewConversation() {
  conversationId = createConversationId();
  localStorage.setItem(CONVERSATION_ID_KEY, conversationId);
  conversationIdText.textContent = conversationId;
  messages = [];
  saveMessages();
  renderMessages();
  statusText.textContent = "准备就绪";
  messageInput.value = "";
  autoResizeInput();
  messageInput.focus();
}

// 表单提交由发送按钮触发。
chatForm.addEventListener("submit", (event) => {
  event.preventDefault();
  sendCurrentMessage();
});

// 输入框监听：Enter 发送，Shift + Enter 保留换行。
messageInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    sendCurrentMessage();
  }
});

// 输入内容变化时动态调整 textarea 高度。
messageInput.addEventListener("input", autoResizeInput);

// 点击按钮创建新会话。
newConversationButton.addEventListener("click", startNewConversation);
