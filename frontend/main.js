const CHAT_API_URL = "http://127.0.0.1:8000/chat";

const ACTIVE_CONVERSATION_KEY = "agent_project_conversation_id";
const CONVERSATIONS_KEY = "agent_project_conversations";
const MESSAGES_KEY_PREFIX = "agent_project_messages_";
const MODE_KEY = "agent_project_mode";
const LATEST_MODEL_KEY = "agent_project_latest_model";
const MAX_MESSAGE_LENGTH = 4000;
const THINKING_NOTICE_DELAY_MS = 8000;
const REQUEST_TIMEOUT_MS = 45000;

const MODE_PROMPTS = {
  智能问答: "你是一个简洁、可靠的中文 AI 助手。回答要清晰、可执行，适合初学者理解。",
  代码助手: "你是一个耐心的编程导师。请优先解释思路，再给出简洁代码，并提醒可能的坑。",
  学习助手: "你是一个学习教练。请把复杂概念拆成小步骤，并给出适合练习的例子。",
  项目分析: "你是一个项目分析助手。请从结构、职责、风险和下一步建议几个角度回答。",
};

const FRIENDLY_ERROR_MESSAGES = [
  {
    match: "DASHSCOPE_API_KEY is not configured",
    message: "后端还没有配置 DASHSCOPE_API_KEY。请检查 .env 文件，然后重启服务。",
  },
  {
    match: "API Key is invalid",
    message: "DashScope API Key 无效或权限不足。请确认 Key 是否正确、是否可用。",
  },
  {
    match: "Unable to connect to DashScope",
    message: "暂时连接不上 DashScope。请检查网络或代理配置，稍后再试。",
  },
  {
    match: "timed out",
    message: "模型响应超时了。可以稍后重试，或把问题拆短一点。",
  },
  {
    match: "Request timed out",
    message: "请求超时了。模型暂时没有及时返回，请稍后重试，或把问题拆短一点。",
  },
  {
    match: "Unexpected model service error",
    message: "模型服务暂时异常。请稍后重试；如果持续出现，请查看后端日志。",
  },
];

const EXAMPLE_PROMPTS = [
  "帮我写Python冒泡排序",
  "帮我总结一下这个 FastAPI 项目的结构",
  "解释一下 /chat 接口从请求到返回的完整流程",
  "给我一个适合初学者的 Agent 学习路线",
];

const chatForm = getRequiredElement("#chatForm");
const messageInput = getRequiredElement("#messageInput");
const messageList = getRequiredElement("#messageList");
const sendButton = getRequiredElement("#sendButton");
const charCounter = getRequiredElement("#charCounter");
const conversationIdText = getRequiredElement("#conversationIdText");
const conversationList = getRequiredElement("#conversationList");
const conversationCountText = getRequiredElement("#conversationCountText");
const activeConversationTitle = getRequiredElement("#activeConversationTitle");
const newConversationButton = getRequiredElement("#newConversationButton");
const clearConversationButton = getRequiredElement("#clearConversationButton");
const currentModelText = getRequiredElement("#currentModelText");
const currentModeText = getRequiredElement("#currentModeText");
const modeButtons = document.querySelectorAll(".mode-item");
console.log("modeButtons found", modeButtons.length);

let conversations = loadConversations();
let conversationId = getInitialConversationId();
let messages = loadMessages(conversationId);
let currentMode = localStorage.getItem(MODE_KEY) || "智能问答";
let latestModel = localStorage.getItem(LATEST_MODEL_KEY) || "等待后端返回";
let isLoading = false;
let activeAbortController = null;

initPage();

function getRequiredElement(selector) {
  const element = document.querySelector(selector);
  if (!element) {
    console.error("element missing", selector);
    throw new Error(`页面缺少必要元素：${selector}`);
  }
  console.log("element found", selector, element);
  return element;
}

function initPage() {
  ensureConversation(conversationId);
  conversationIdText.textContent = conversationId;
  currentModelText.textContent = latestModel;
  setMode(currentMode);
  renderConversationList();
  renderMessages();
  updateHeaderTitle();
  updateInputState();
  autoResizeInput();
  messageInput.focus();
}

function loadConversations() {
  const parsed = readJson(CONVERSATIONS_KEY, []);
  const normalized = Array.isArray(parsed)
    ? parsed
        .filter((item) => item && typeof item.id === "string")
        .map((item) => ({
          id: item.id,
          title: item.title || "新会话",
          createdAt: item.createdAt || Date.now(),
          updatedAt: item.updatedAt || item.createdAt || Date.now(),
          messageCount: Number(item.messageCount || 0),
        }))
    : [];

  if (normalized.length > 0) {
    return sortConversations(normalized);
  }

  const legacyId = localStorage.getItem(ACTIVE_CONVERSATION_KEY);
  const initialId = legacyId || createConversationId();
  return [
    {
      id: initialId,
      title: "新会话",
      createdAt: Date.now(),
      updatedAt: Date.now(),
      messageCount: loadMessages(initialId).length,
    },
  ];
}

function getInitialConversationId() {
  const savedId = localStorage.getItem(ACTIVE_CONVERSATION_KEY);
  if (savedId && conversations.some((item) => item.id === savedId)) {
    return savedId;
  }

  const firstId = conversations[0]?.id || createConversationId();
  localStorage.setItem(ACTIVE_CONVERSATION_KEY, firstId);
  return firstId;
}

function ensureConversation(id) {
  if (conversations.some((item) => item.id === id)) {
    saveConversations();
    return;
  }

  conversations.unshift({
    id,
    title: "新会话",
    createdAt: Date.now(),
    updatedAt: Date.now(),
    messageCount: loadMessages(id).length,
  });
  saveConversations();
}

function createConversationId() {
  if (window.crypto && typeof window.crypto.randomUUID === "function") {
    return window.crypto.randomUUID();
  }

  return `conv-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function getMessagesKey(id) {
  return `${MESSAGES_KEY_PREFIX}${id}`;
}

function readJson(key, fallback) {
  const raw = localStorage.getItem(key);
  if (!raw) {
    return fallback;
  }

  try {
    return JSON.parse(raw);
  } catch {
    return fallback;
  }
}

function loadMessages(id) {
  const loaded = readJson(getMessagesKey(id), []);
  return Array.isArray(loaded) ? loaded : [];
}

function saveMessages() {
  localStorage.setItem(getMessagesKey(conversationId), JSON.stringify(messages));
}

function saveConversations() {
  conversations = sortConversations(conversations);
  localStorage.setItem(CONVERSATIONS_KEY, JSON.stringify(conversations));
}

function sortConversations(items) {
  return [...items].sort((a, b) => Number(b.updatedAt || 0) - Number(a.updatedAt || 0));
}

function getCurrentConversation() {
  return conversations.find((item) => item.id === conversationId);
}

function updateConversationMeta(updates = {}) {
  const now = Date.now();
  conversations = conversations.map((item) => {
    if (item.id !== conversationId) {
      return item;
    }

    return {
      ...item,
      updatedAt: updates.updatedAt || now,
      messageCount: messages.length,
      ...updates,
    };
  });

  saveConversations();
  renderConversationList();
  updateHeaderTitle();
}

function replaceActiveConversationId(nextId) {
  if (!nextId || nextId === conversationId) {
    return;
  }

  const oldId = conversationId;
  const current = getCurrentConversation();
  const nextConversation = {
    ...(current || {}),
    id: nextId,
    title: current?.title || "新会话",
    createdAt: current?.createdAt || Date.now(),
    updatedAt: Date.now(),
    messageCount: messages.length,
  };

  conversationId = nextId;
  localStorage.setItem(ACTIVE_CONVERSATION_KEY, conversationId);
  localStorage.setItem(getMessagesKey(conversationId), JSON.stringify(messages));
  localStorage.removeItem(getMessagesKey(oldId));

  conversations = conversations.filter((item) => item.id !== oldId && item.id !== nextId);
  conversations.unshift(nextConversation);
  saveConversations();
  conversationIdText.textContent = conversationId;
  renderConversationList();
  updateHeaderTitle();
}

function renderConversationList() {
  conversationList.innerHTML = "";
  conversationCountText.textContent = String(conversations.length);

  if (conversations.length === 0) {
    const empty = document.createElement("div");
    empty.className = "conversation-empty";
    empty.textContent = "还没有会话。点击上方按钮开始一个新的 Agent 任务。";
    conversationList.appendChild(empty);
    return;
  }

  conversations.forEach((conversation) => {
    const item = document.createElement("div");
    item.className = "conversation-item";
    item.tabIndex = 0;
    item.role = "button";
    item.classList.toggle("active", conversation.id === conversationId);
    item.setAttribute("aria-label", `切换到 ${conversation.title}`);
    item.addEventListener("click", () => {
      console.log("conversation item clicked", conversation.id);
      switchConversation(conversation.id);
    });
    item.addEventListener("keydown", (event) => {
      console.log("conversation item keydown", event.key, conversation.id);
      if (event.target !== item) {
        return;
      }
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        console.log("conversation item keyboard activate", conversation.id);
        switchConversation(conversation.id);
      }
    });

    const main = document.createElement("span");
    main.className = "conversation-main";

    const title = document.createElement("span");
    title.className = "conversation-title";
    title.textContent = conversation.title || "新会话";

    const meta = document.createElement("span");
    meta.className = "conversation-meta";
    meta.textContent = `${conversation.messageCount || 0} 条 · ${formatRelativeTime(conversation.updatedAt)}`;

    main.append(title, meta);

    const deleteButton = document.createElement("button");
    deleteButton.className = "conversation-delete";
    deleteButton.type = "button";
    deleteButton.textContent = "×";
    deleteButton.title = "删除会话";
    deleteButton.setAttribute("aria-label", `删除 ${conversation.title}`);
    deleteButton.addEventListener("click", (event) => {
      console.log("deleteConversationButton clicked", conversation.id);
      event.stopPropagation();
      deleteConversation(conversation.id);
    });

    item.append(main, deleteButton);
    conversationList.appendChild(item);
  });
}

function formatRelativeTime(timestamp) {
  const time = Number(timestamp || Date.now());
  const diff = Date.now() - time;
  const minute = 60 * 1000;
  const hour = 60 * minute;
  const day = 24 * hour;

  if (diff < minute) {
    return "刚刚";
  }

  if (diff < hour) {
    return `${Math.floor(diff / minute)} 分钟前`;
  }

  if (diff < day) {
    return `${Math.floor(diff / hour)} 小时前`;
  }

  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(time));
}

function updateHeaderTitle() {
  const conversation = getCurrentConversation();
  activeConversationTitle.textContent = conversation?.title || "智能体助手";
}

function renderMessages() {
  messageList.innerHTML = "";

  if (messages.length === 0) {
    renderWelcomePanel();
    return;
  }

  messages.forEach((message) => appendMessageElement(message));
  scrollToBottom();
}

function renderWelcomePanel() {
  const welcomePanel = document.createElement("div");
  welcomePanel.className = "welcome-panel";

  const card = document.createElement("div");
  card.className = "welcome-card";

  const badge = document.createElement("span");
  badge.className = "welcome-badge";
  badge.textContent = "DashScope Agent 在线";

  const title = document.createElement("h2");
  title.textContent = "你好，我是你的 Agent 智能体助手";

  const description = document.createElement("p");
  description.textContent =
    "可以帮你解释概念、分析项目、生成代码思路，也能把任务拆成清晰的下一步。左侧会自动保存多个会话，方便你按主题持续推进。";

  const promptGrid = document.createElement("div");
  promptGrid.className = "prompt-grid";

  EXAMPLE_PROMPTS.forEach((prompt) => {
    const button = document.createElement("button");
    button.className = "prompt-card";
    button.type = "button";
    button.textContent = prompt;
    console.log("prompt-card created", prompt);
    button.addEventListener("click", () => {
      console.log("prompt-card clicked", prompt);
      messageInput.value = prompt;
      updateInputState();
      autoResizeInput();
      messageInput.focus();
    });
    promptGrid.appendChild(button);
  });

  card.append(badge, title, description, promptGrid);
  welcomePanel.appendChild(card);
  messageList.appendChild(welcomePanel);
}

function appendMessage(message) {
  messages.push(message);
  saveMessages();
  removeWelcomePanel();
  appendMessageElement(message);

  if (message.role === "user") {
    maybeRenameConversation(message.content);
  } else {
    updateConversationMeta();
  }

  scrollToBottom();
}

function appendMessageElement(message) {
  const messageItem = document.createElement("article");
  messageItem.className = `message ${message.role}-message`;
  messageItem.dataset.messageId = message.id;

  const shell = document.createElement("div");
  shell.className = "message-shell";

  if (message.role === "agent") {
    const avatar = document.createElement("div");
    avatar.className = "agent-avatar";
    avatar.textContent = "AI";
    shell.appendChild(avatar);
  }

  const content = document.createElement("div");
  content.className = "message-content message-body";

  if (message.role === "agent" && message.type !== "loading") {
    content.appendChild(createCopyToolbar(message.content || ""));
  }

  const bubble = document.createElement("div");
  bubble.className = "message-bubble";

  if (message.type === "loading") {
    bubble.appendChild(createTypingIndicator(message.content || "Agent 正在思考"));
  } else if (message.role === "agent") {
    bubble.appendChild(renderMarkdown(message.content || ""));
  } else {
    bubble.textContent = message.content || "";
  }

  content.appendChild(bubble);

  const meta = createMessageMeta(message);
  if (meta) {
    content.appendChild(meta);
  }

  const toolPanel = createToolPanel(message);
  if (toolPanel) {
    content.appendChild(toolPanel);
  }

  shell.appendChild(content);
  messageItem.appendChild(shell);
  messageList.appendChild(messageItem);
}

function createCopyToolbar(text) {
  const toolbar = document.createElement("div");
  toolbar.className = "message-toolbar";

  const button = document.createElement("button");
  button.className = "copy-message-button";
  button.type = "button";
  button.textContent = "复制";
  button.addEventListener("click", () => {
    console.log("copy-message-button clicked");
    copyText(text, button, "已复制");
  });

  toolbar.appendChild(button);
  return toolbar;
}

function createMessageMeta(message) {
  const metaItems = [];

  if (message.createdAt) {
    metaItems.push(message.role === "agent" ? `回复时间 ${message.createdAt}` : `发送时间 ${message.createdAt}`);
  }

  if (message.role === "agent" && message.model) {
    metaItems.push(`模型 ${message.model}`);
  }

  if (metaItems.length === 0) {
    return null;
  }

  const meta = document.createElement("div");
  meta.className = "message-meta";

  metaItems.forEach((item) => {
    const chip = document.createElement("span");
    chip.className = "meta-chip";
    chip.textContent = item;
    meta.appendChild(chip);
  });

  return meta;
}

function createToolPanel(message) {
  if (!message.usedTool && !message.toolName && !message.toolResult) {
    return null;
  }

  const panel = document.createElement("div");
  panel.className = "tool-panel";

  const rows = [];
  if (message.usedTool !== undefined) {
    rows.push(`<div><strong>used_tool: </strong>${escapeHtml(String(message.usedTool))}</div>`);
  }
  if (message.toolName) {
    rows.push(`<div><strong>tool_name: </strong>${escapeHtml(message.toolName)}</div>`);
  }
  if (message.toolResult) {
    rows.push(`<div><strong>tool_result: </strong>${escapeHtml(formatToolResult(message.toolResult))}</div>`);
  }

  panel.innerHTML = rows.join("");
  return panel;
}

function formatToolResult(result) {
  if (typeof result === "string") {
    return result;
  }

  try {
    return JSON.stringify(result, null, 2);
  } catch {
    return String(result);
  }
}

function renderMarkdown(markdown) {
  const root = document.createElement("div");
  root.className = "markdown-body";
  const lines = String(markdown || "").replace(/\r\n/g, "\n").split("\n");
  let index = 0;

  while (index < lines.length) {
    const line = lines[index];

    if (line.trim() === "") {
      index += 1;
      continue;
    }

    const fence = line.match(/^```([\w+-]*)\s*$/);
    if (fence) {
      const language = fence[1] || "text";
      const codeLines = [];
      index += 1;
      while (index < lines.length && !/^```\s*$/.test(lines[index])) {
        codeLines.push(lines[index]);
        index += 1;
      }
      if (index < lines.length) {
        index += 1;
      }
      root.appendChild(createCodeBlock(codeLines.join("\n"), language));
      continue;
    }

    if (isTableStart(lines, index)) {
      const tableLines = [];
      while (index < lines.length && lines[index].includes("|") && lines[index].trim() !== "") {
        tableLines.push(lines[index]);
        index += 1;
      }
      root.appendChild(createTable(tableLines));
      continue;
    }

    const heading = line.match(/^(#{1,3})\s+(.+)$/);
    if (heading) {
      const level = String(heading[1]).length;
      const element = document.createElement(`h${level}`);
      element.appendChild(renderInlineMarkdown(heading[2]));
      root.appendChild(element);
      index += 1;
      continue;
    }

    if (/^>\s?/.test(line)) {
      const quoteLines = [];
      while (index < lines.length && /^>\s?/.test(lines[index])) {
        quoteLines.push(lines[index].replace(/^>\s?/, ""));
        index += 1;
      }
      const quote = document.createElement("blockquote");
      quote.appendChild(renderInlineMarkdown(quoteLines.join(" ")));
      root.appendChild(quote);
      continue;
    }

    if (/^\s*([-*+])\s+/.test(line) || /^\s*\d+\.\s+/.test(line)) {
      const ordered = /^\s*\d+\.\s+/.test(line);
      const list = document.createElement(ordered ? "ol" : "ul");
      while (
        index < lines.length &&
        (ordered ? /^\s*\d+\.\s+/.test(lines[index]) : /^\s*([-*+])\s+/.test(lines[index]))
      ) {
        const itemText = lines[index].replace(ordered ? /^\s*\d+\.\s+/ : /^\s*[-*+]\s+/, "");
        const item = document.createElement("li");
        item.appendChild(renderInlineMarkdown(itemText));
        list.appendChild(item);
        index += 1;
      }
      root.appendChild(list);
      continue;
    }

    const paragraphLines = [];
    while (index < lines.length && lines[index].trim() !== "" && !isBlockStart(lines, index)) {
      paragraphLines.push(lines[index]);
      index += 1;
    }

    if (paragraphLines.length > 0) {
      const paragraph = document.createElement("p");
      paragraph.appendChild(renderInlineMarkdown(paragraphLines.join(" ")));
      root.appendChild(paragraph);
    } else {
      index += 1;
    }
  }

  return root;
}

function isBlockStart(lines, index) {
  const line = lines[index] || "";
  return (
    /^```/.test(line) ||
    /^(#{1,3})\s+/.test(line) ||
    /^>\s?/.test(line) ||
    /^\s*([-*+])\s+/.test(line) ||
    /^\s*\d+\.\s+/.test(line) ||
    isTableStart(lines, index)
  );
}

function isTableStart(lines, index) {
  const current = lines[index] || "";
  const next = lines[index + 1] || "";
  return current.includes("|") && /^\s*\|?[\s:-]+\|[\s|:-]+\s*$/.test(next);
}

function createTable(tableLines) {
  const wrapper = document.createElement("div");
  wrapper.className = "table-wrap";
  const table = document.createElement("table");
  const headerCells = splitTableRow(tableLines[0]);
  const bodyLines = tableLines.slice(2);

  const thead = document.createElement("thead");
  const headerRow = document.createElement("tr");
  headerCells.forEach((cell) => {
    const th = document.createElement("th");
    th.appendChild(renderInlineMarkdown(cell));
    headerRow.appendChild(th);
  });
  thead.appendChild(headerRow);
  table.appendChild(thead);

  const tbody = document.createElement("tbody");
  bodyLines.forEach((rowLine) => {
    const row = document.createElement("tr");
    splitTableRow(rowLine).forEach((cell) => {
      const td = document.createElement("td");
      td.appendChild(renderInlineMarkdown(cell));
      row.appendChild(td);
    });
    tbody.appendChild(row);
  });
  table.appendChild(tbody);

  wrapper.appendChild(table);
  return wrapper;
}

function splitTableRow(line) {
  return line
    .trim()
    .replace(/^\|/, "")
    .replace(/\|$/, "")
    .split("|")
    .map((cell) => cell.trim());
}

function createCodeBlock(code, language) {
  const block = document.createElement("div");
  block.className = "code-block";

  const header = document.createElement("div");
  header.className = "code-block-header";

  const label = document.createElement("span");
  label.textContent = language || "text";

  const copyButton = document.createElement("button");
  copyButton.className = "code-copy-button";
  copyButton.type = "button";
  copyButton.textContent = "复制代码";
  copyButton.addEventListener("click", () => {
    console.log("code-copy-button clicked", language || "text");
    copyText(code, copyButton, "已复制");
  });

  const pre = document.createElement("pre");
  const codeElement = document.createElement("code");
  codeElement.textContent = code;
  pre.appendChild(codeElement);

  header.append(label, copyButton);
  block.append(header, pre);
  return block;
}

function renderInlineMarkdown(text) {
  const fragment = document.createDocumentFragment();
  const pattern = /(\*\*[^*]+\*\*|`[^`]+`|\[([^\]]+)\]\((https?:\/\/[^\s)]+)\))/g;
  let cursor = 0;
  let match;

  while ((match = pattern.exec(text)) !== null) {
    if (match.index > cursor) {
      fragment.appendChild(document.createTextNode(text.slice(cursor, match.index)));
    }

    const token = match[0];
    if (token.startsWith("**")) {
      const strong = document.createElement("strong");
      strong.textContent = token.slice(2, -2);
      fragment.appendChild(strong);
    } else if (token.startsWith("`")) {
      const code = document.createElement("code");
      code.textContent = token.slice(1, -1);
      fragment.appendChild(code);
    } else {
      const link = document.createElement("a");
      link.textContent = match[2];
      link.href = match[3];
      link.target = "_blank";
      link.rel = "noreferrer";
      fragment.appendChild(link);
    }

    cursor = pattern.lastIndex;
  }

  if (cursor < text.length) {
    fragment.appendChild(document.createTextNode(text.slice(cursor)));
  }

  return fragment;
}

function escapeHtml(value) {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

async function copyText(text, button, successText) {
  console.log("copyText start", {
    textLength: text.length,
  });
  const previousText = button.textContent;
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
    } else {
      fallbackCopyText(text);
    }
    button.textContent = successText;
  } catch {
    button.textContent = "复制失败";
  }

  window.setTimeout(() => {
    button.textContent = previousText;
  }, 1200);
}

function fallbackCopyText(text) {
  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.setAttribute("readonly", "");
  textarea.style.position = "fixed";
  textarea.style.top = "-999px";
  document.body.appendChild(textarea);
  textarea.select();
  document.execCommand("copy");
  textarea.remove();
}

function createTypingIndicator(labelText = "Agent 正在思考") {
  const wrapper = document.createElement("span");
  wrapper.className = "typing-indicator";
  wrapper.setAttribute("aria-label", labelText);

  const label = document.createElement("span");
  label.textContent = labelText;
  wrapper.appendChild(label);

  for (let index = 0; index < 3; index += 1) {
    const dot = document.createElement("span");
    dot.className = "typing-dot";
    wrapper.appendChild(dot);
  }

  return wrapper;
}

function removeWelcomePanel() {
  const welcomePanel = messageList.querySelector(".welcome-panel");
  if (welcomePanel) {
    welcomePanel.remove();
  }
}

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
  updateConversationMeta();
  renderMessages();
}

function scrollToBottom() {
  messageList.scrollTop = messageList.scrollHeight;
}

function getCurrentTime() {
  return new Intl.DateTimeFormat("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(new Date());
}

function createMessage(role, content, type = "text", extra = {}) {
  return {
    id: `msg-${Date.now()}-${Math.random().toString(16).slice(2)}`,
    role,
    type,
    content,
    createdAt: getCurrentTime(),
    ...extra,
  };
}

function maybeRenameConversation(text) {
  const conversation = getCurrentConversation();
  if (!conversation || conversation.title !== "新会话") {
    updateConversationMeta();
    return;
  }

  const cleanTitle = text.replace(/\s+/g, " ").trim().slice(0, 26);
  updateConversationMeta({
    title: cleanTitle || "新会话",
  });
}

function setLoading(nextLoading) {
  isLoading = nextLoading;
  messageInput.disabled = nextLoading;
  sendButton.textContent = nextLoading ? "停止生成" : "发送";
  newConversationButton.disabled = nextLoading;
  clearConversationButton.disabled = nextLoading;
  updateInputState();
}

function autoResizeInput() {
  messageInput.style.height = "auto";
  messageInput.style.height = `${Math.min(messageInput.scrollHeight, 180)}px`;
}

function updateInputState() {
  const length = messageInput.value.length;
  const hasText = messageInput.value.trim().length > 0;

  charCounter.textContent = `${length} / ${MAX_MESSAGE_LENGTH}`;
  sendButton.disabled = !isLoading && !hasText;
}

function setMode(mode) {
  console.log("setMode start", mode);
  currentMode = MODE_PROMPTS[mode] ? mode : "智能问答";
  localStorage.setItem(MODE_KEY, currentMode);
  currentModeText.textContent = currentMode;

  modeButtons.forEach((button) => {
    button.classList.toggle("active", button.dataset.mode === currentMode);
  });
}

async function requestAgentReply(message) {
  console.log("requestAgentReply start", {
    conversationId,
    messageLength: message.length,
    mode: currentMode,
  });
  const requestBody = {
    message,
    system_prompt: MODE_PROMPTS[currentMode],
    conversation_id: conversationId,
  };

  activeAbortController = new AbortController();
  let didTimeout = false;
  const timeoutTimer = window.setTimeout(() => {
    didTimeout = true;
    activeAbortController.abort();
  }, REQUEST_TIMEOUT_MS);

  let response;
  try {
    console.log("POST /chat request start", requestBody);
    response = await fetch(CHAT_API_URL, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify(requestBody),
      signal: activeAbortController.signal,
    });
    console.log("POST /chat response received", {
      ok: response.ok,
      status: response.status,
      statusText: response.statusText,
    });
  } catch (error) {
    console.error("POST /chat request error", error);
    window.clearTimeout(timeoutTimer);
    activeAbortController = null;
    if (error.name === "AbortError") {
      if (didTimeout) {
        throw new Error(toFriendlyError("Request timed out"));
      }
      return { aborted: true };
    }
    throw new Error("请求失败，请检查后端");
  }

  window.clearTimeout(timeoutTimer);
  activeAbortController = null;

  if (!response.ok) {
    const data = await parseJsonResponse(response);
    console.error("Chat request failed:", data.error || response.status);
    throw new Error("请求失败，请检查后端");
  }

  const data = await parseJsonResponse(response);
  console.log("POST /chat response body", data);
  if (!data.success) {
    console.error("Chat API returned an error:", data.error);
    throw new Error("请求失败，请检查后端");
  }

  return {
    aborted: false,
    reply: data.reply || "",
    model: data.model || "",
    conversationId: data.conversation_id || conversationId,
    usedTool: data.used_tool,
    toolName: data.tool_name,
    toolResult: data.tool_result,
  };
}

function abortCurrentRequest() {
  if (activeAbortController) {
    activeAbortController.abort();
  }
}

async function parseJsonResponse(response) {
  try {
    return await response.json();
  } catch {
    return { success: false, error: "后端返回了无法解析的响应，请查看服务日志。" };
  }
}

function toFriendlyError(errorText) {
  const text = String(errorText || "");
  const knownError = FRIENDLY_ERROR_MESSAGES.find((item) => text.includes(item.match));
  return knownError ? knownError.message : text || "请求失败，请稍后重试。";
}

async function sendCurrentMessage() {
  console.log("sendCurrentMessage start", {
    isLoading,
    inputLength: messageInput.value.length,
  });
  if (isLoading) {
    console.log("sendCurrentMessage abort current request");
    abortCurrentRequest();
    return;
  }

  const userText = messageInput.value.trim();
  if (!userText) {
    console.log("sendCurrentMessage empty input");
    updateInputState();
    return;
  }

  appendMessage(createMessage("user", userText));
  messageInput.value = "";
  autoResizeInput();
  updateInputState();

  const loadingMessage = createMessage("agent", "Agent 正在思考", "loading");
  appendMessage(loadingMessage);
  setLoading(true);

  let hasReceivedFirstChunk = false;
  const thinkingTimer = window.setTimeout(() => {
    if (!hasReceivedFirstChunk) {
      updateMessage(loadingMessage.id, {
        type: "loading",
        role: "agent",
        content: "模型正在思考中，请稍等...",
        createdAt: getCurrentTime(),
      });
    }
  }, THINKING_NOTICE_DELAY_MS);

  try {
    const result = await requestAgentReply(userText);
    console.log("sendCurrentMessage received result", result);
    if (result.aborted) {
      updateMessage(loadingMessage.id, {
        type: "text",
        role: "error",
        content: "已停止生成。",
        createdAt: getCurrentTime(),
      });
      return;
    }

    hasReceivedFirstChunk = true;
    window.clearTimeout(thinkingTimer);

    if (result.conversationId && result.conversationId !== conversationId) {
      replaceActiveConversationId(result.conversationId);
    }

    if (result.model) {
      latestModel = result.model;
      localStorage.setItem(LATEST_MODEL_KEY, latestModel);
      currentModelText.textContent = latestModel;
    }

    updateMessage(loadingMessage.id, {
      type: "text",
      role: "agent",
      content: result.reply || "Agent 没有返回文本内容。",
      model: result.model,
      usedTool: result.usedTool,
      toolName: result.toolName,
      toolResult: result.toolResult,
      createdAt: getCurrentTime(),
    });
  } catch (error) {
    console.error("sendCurrentMessage error", error);
    updateMessage(loadingMessage.id, {
      type: "text",
      role: "error",
      content: "请求失败，请检查后端",
      createdAt: getCurrentTime(),
    });
  } finally {
    window.clearTimeout(thinkingTimer);
    setLoading(false);
    messageInput.focus();
  }
}

function startNewConversation() {
  console.log("startNewConversation start");
  if (guardActionDuringLoading()) {
    console.log("startNewConversation blocked by loading");
    return;
  }

  conversationId = createConversationId();
  console.log("newConversation created", conversationId);
  localStorage.setItem(ACTIVE_CONVERSATION_KEY, conversationId);
  conversations.unshift({
    id: conversationId,
    title: "新会话",
    createdAt: Date.now(),
    updatedAt: Date.now(),
    messageCount: 0,
  });
  saveConversations();
  messages = [];
  saveMessages();
  conversationIdText.textContent = conversationId;
  renderConversationList();
  renderMessages();
  updateHeaderTitle();
  messageInput.value = "";
  autoResizeInput();
  updateInputState();
  messageInput.focus();
}

function switchConversation(nextId) {
  console.log("switchConversation start", nextId);
  if (nextId === conversationId || guardActionDuringLoading()) {
    console.log("switchConversation skipped", {
      nextId,
      conversationId,
      isLoading,
    });
    return;
  }

  conversationId = nextId;
  localStorage.setItem(ACTIVE_CONVERSATION_KEY, conversationId);
  messages = loadMessages(conversationId);
  conversationIdText.textContent = conversationId;
  renderConversationList();
  renderMessages();
  updateHeaderTitle();
  messageInput.value = "";
  autoResizeInput();
  updateInputState();
  messageInput.focus();
}

function deleteConversation(targetId) {
  console.log("deleteConversation start", targetId);
  if (guardActionDuringLoading()) {
    console.log("deleteConversation blocked by loading", targetId);
    return;
  }

  const target = conversations.find((item) => item.id === targetId);
  const hasMessages = loadMessages(targetId).length > 0;
  if (hasMessages && !window.confirm(`确定删除“${target?.title || "该会话"}”吗？`)) {
    return;
  }

  localStorage.removeItem(getMessagesKey(targetId));
  conversations = conversations.filter((item) => item.id !== targetId);

  if (conversations.length === 0) {
    const newId = createConversationId();
    conversations = [
      {
        id: newId,
        title: "新会话",
        createdAt: Date.now(),
        updatedAt: Date.now(),
        messageCount: 0,
      },
    ];
  }

  if (targetId === conversationId) {
    conversationId = conversations[0].id;
    messages = loadMessages(conversationId);
    localStorage.setItem(ACTIVE_CONVERSATION_KEY, conversationId);
    conversationIdText.textContent = conversationId;
    renderMessages();
    updateHeaderTitle();
  }

  saveConversations();
  renderConversationList();
  messageInput.focus();
}

function clearCurrentConversation() {
  console.log("clearCurrentConversation start", conversationId);
  if (guardActionDuringLoading()) {
    console.log("clearCurrentConversation blocked by loading");
    return;
  }

  messages = [];
  saveMessages();
  updateConversationMeta({
    title: "新会话",
    messageCount: 0,
  });
  renderMessages();
  messageInput.focus();
}

function guardActionDuringLoading() {
  if (!isLoading) {
    return false;
  }

  console.log("guardActionDuringLoading blocked action");
  window.alert("当前正在生成回复，请先点击“停止生成”。");
  return true;
}

chatForm.addEventListener("submit", (event) => {
  console.log("chatForm submit start");
  event.preventDefault();
  sendCurrentMessage();
});

sendButton.addEventListener("click", () => {
  console.log("sendButton clicked");
});

messageInput.addEventListener("keydown", (event) => {
  console.log("messageInput keydown", {
    key: event.key,
    shiftKey: event.shiftKey,
  });
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    console.log("messageInput enter send");
    sendCurrentMessage();
  }
});

messageInput.addEventListener("input", () => {
  console.log("messageInput input", {
    length: messageInput.value.length,
  });
  updateInputState();
  autoResizeInput();
});

newConversationButton.addEventListener("click", () => {
  console.log("newConversation clicked");
  startNewConversation();
});
clearConversationButton.addEventListener("click", () => {
  console.log("clearConversation clicked");
  clearCurrentConversation();
});

modeButtons.forEach((button) => {
  button.addEventListener("click", () => {
    console.log("modeButton clicked", button.dataset.mode);
    setMode(button.dataset.mode);
    messageInput.focus();
  });
});
