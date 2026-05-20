// Configuration

const DEBUG = false;
function debugLog(...args) { if (DEBUG) console.log(...args); }

const CHAT_API_URL = "http://127.0.0.1:8000/chat";
const CHAT_STREAM_API_URL = "http://127.0.0.1:8000/chat/stream";

const ACTIVE_CONVERSATION_KEY = "agent_project_conversation_id";
const CONVERSATIONS_KEY = "agent_project_conversations";
const MESSAGES_KEY_PREFIX = "agent_project_messages_";
const SCROLL_POSITIONS_KEY = "agent_project_scroll_positions";
const MODE_KEY = "agent_project_mode";
const SELECTED_MODEL_KEY = "agent_project_selected_model";
const THEME_KEY = "agent_project_theme";
const MAX_CONTEXT_ROUNDS_KEY = "agent_project_max_context_rounds";
const STREAMING_ENABLED_KEY = "agent_project_streaming_enabled";
const MAX_MESSAGE_LENGTH = 4000;
const DEFAULT_MAX_CONTEXT_ROUNDS = 10;
const MIN_CONTEXT_ROUNDS = 0;
const MAX_CONTEXT_ROUNDS = 30;
const THINKING_NOTICE_DELAY_MS = 8000;
const REQUEST_TIMEOUT_MS = 45000;
const AUTO_SCROLL_THRESHOLD_PX = 200;
const WEB_SEARCH_STATUS_SEARCHING = "正在联网搜索...";
const WEB_SEARCH_STATUS_ORGANIZING = "正在搜索并整理资料...";
const WEB_SEARCH_STATUS_DONE = "已联网搜索";
const WEB_SEARCH_STATUS_MESSAGES = new Set([
  WEB_SEARCH_STATUS_SEARCHING,
  WEB_SEARCH_STATUS_ORGANIZING,
  WEB_SEARCH_STATUS_DONE,
]);
const CHAT_FAILURE_MESSAGE = "请求失败，请检查后端服务或 API Key";
const DEFAULT_MODE = "通用助手";
const DEFAULT_THEME = "light";

const AVAILABLE_MODELS = [
  { value: "qwen-plus", label: "qwen-plus" },
  { value: "qwen-turbo", label: "qwen-turbo" },
  { value: "qwen-max", label: "qwen-max" },
];
const DEFAULT_MODEL = AVAILABLE_MODELS[0].value;

const MODE_PROMPTS = {
  通用助手: "你是一个简洁、可靠的中文 AI 助手。回答要清晰、可执行，适合初学者理解。",
  代码助手: "你是一个耐心的编程导师。请优先解释思路，再给出简洁代码，并提醒可能的坑。",
  学习助手: "你是一个学习教练。请把复杂概念拆成小步骤，并给出适合练习的例子、检查点和复习建议。",
  面试助手: "你是一个专业的面试辅导助手。请围绕岗位面试场景回答，优先给出结构化思路、示例回答、追问点和改进建议。",
};

const MODE_ALIASES = {
  智能问答: "通用助手",
  项目分析: "面试助手",
};

const MODE_ICONS = {
  通用助手: "?",
  代码助手: "{ }",
  学习助手: "A",
  面试助手: "#",
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

// DOM references

const chatForm = getRequiredElement("#chatForm");
const messageInput = getRequiredElement("#messageInput");
const messageList = getRequiredElement("#messageList");
const sendButton = getRequiredElement("#sendButton");
const charCounter = getRequiredElement("#charCounter");
const conversationIdText = getRequiredElement("#conversationIdText");
const conversationList = getRequiredElement("#conversationList");
const conversationSearchInput = getRequiredElement("#conversationSearchInput");
const conversationCountText = getRequiredElement("#conversationCountText");
const activeConversationTitle = getRequiredElement("#activeConversationTitle");
const newConversationButton = getRequiredElement("#newConversationButton");
const clearConversationButton = getRequiredElement("#clearConversationButton");
const scrollToBottomButton = getRequiredElement("#scrollToBottomButton");
const newMessageNotice = getRequiredElement("#newMessageNotice");
const currentModelText = getRequiredElement("#currentModelText");
const modelSelect = getRequiredElement("#modelSelect");
const currentModeText = getRequiredElement("#currentModeText");
const themeToggleButton = getRequiredElement("#themeToggleButton");
const settingsButton = getRequiredElement("#settingsButton");
const settingsOverlay = getRequiredElement("#settingsOverlay");
const settingsCloseButton = getRequiredElement("#settingsCloseButton");
const settingsModelSelect = getRequiredElement("#settingsModelSelect");
const settingsMaxContextInput = getRequiredElement("#settingsMaxContextInput");
const settingsStreamingToggle = getRequiredElement("#settingsStreamingToggle");
const settingsModeSelect = getRequiredElement("#settingsModeSelect");
const clearAllConversationsButton = getRequiredElement("#clearAllConversationsButton");
ensureModeItems();
ensureModelOptions();
ensureSettingsModeOptions();
const modeButtons = getRequiredElements(".mode-item");
debugLog("modeButtons found", modeButtons.length);

// State

let conversations = loadConversations();
let conversationId = getInitialConversationId();
let messages = loadMessages(conversationId);
let conversationScrollPositions = loadConversationScrollPositions();
let currentMode = normalizeMode(localStorage.getItem(MODE_KEY));
let selectedModel = normalizeModel(localStorage.getItem(SELECTED_MODEL_KEY));
let currentTheme = normalizeTheme(localStorage.getItem(THEME_KEY));
let maxContextRounds = normalizeMaxContextRounds(localStorage.getItem(MAX_CONTEXT_ROUNDS_KEY));
let streamingEnabled = normalizeBooleanSetting(localStorage.getItem(STREAMING_ENABLED_KEY), false);
let isLoading = false;
let activeAbortController = null;
let shouldStickToBottom = true;
let conversationSearchQuery = "";
const messageElementMap = new Map();

initPage();

// DOM helpers

function getRequiredElement(selector) {
  const element = document.querySelector(selector);
  if (!element) {
    if (selector === "#messageInput") {
      console.warn("messageInput missing");
    }
    console.warn("element missing", selector);
    throw new Error(`页面缺少必要元素：${selector}`);
  }
  debugLog("element found", selector, element);
  return element;
}

function getRequiredElements(selector) {
  const elements = document.querySelectorAll(selector);
  if (elements.length === 0) {
    console.warn("elements missing", selector);
    throw new Error(`页面缺少必要元素：${selector}`);
  }
  debugLog("elements found", selector, elements.length);
  return elements;
}

function normalizeMode(mode) {
  const normalizedMode = MODE_ALIASES[mode] || mode;
  return MODE_PROMPTS[normalizedMode] ? normalizedMode : DEFAULT_MODE;
}

function normalizeModel(model) {
  const value = String(model || "").trim();
  return AVAILABLE_MODELS.some((item) => item.value === value) ? value : DEFAULT_MODEL;
}

function normalizeTheme(theme) {
  return theme === "dark" || theme === "light" ? theme : DEFAULT_THEME;
}

function normalizeMaxContextRounds(value) {
  const parsed = Number.parseInt(value, 10);
  if (!Number.isFinite(parsed)) {
    return DEFAULT_MAX_CONTEXT_ROUNDS;
  }

  return Math.min(MAX_CONTEXT_ROUNDS, Math.max(MIN_CONTEXT_ROUNDS, parsed));
}

function normalizeBooleanSetting(value, fallback = false) {
  if (value === "true" || value === true) {
    return true;
  }

  if (value === "false" || value === false) {
    return false;
  }

  return fallback;
}

function createModeButton(modeName) {
  const button = document.createElement("button");
  button.className = "mode-item";
  button.type = "button";
  button.dataset.mode = modeName;

  const icon = document.createElement("span");
  icon.className = "mode-icon";
  icon.setAttribute("aria-hidden", "true");
  icon.textContent = MODE_ICONS[modeName] || "?";

  button.append(icon, document.createTextNode(` ${modeName}`));
  return button;
}

function ensureModelOptions() {
  fillModelSelect(modelSelect);
  fillModelSelect(settingsModelSelect);
}

function fillModelSelect(select) {
  select.replaceChildren(
    ...AVAILABLE_MODELS.map((model) => createOption(model.value, model.label)),
  );
}

function createOption(value, label = value) {
  const option = document.createElement("option");
  option.value = value;
  option.textContent = label;
  return option;
}

function ensureSettingsModeOptions() {
  settingsModeSelect.replaceChildren(
    ...Object.keys(MODE_PROMPTS).map((modeName) => createOption(modeName)),
  );
}

function ensureModeItems() {
  const modeMenu = document.querySelector(".mode-menu");
  if (!modeMenu) {
    console.warn("elements missing", ".mode-menu");
    return;
  }

  Object.keys(MODE_PROMPTS).forEach((modeName) => {
    const existingButton = modeMenu.querySelector(
      `.mode-item[data-mode="${modeName}"]`,
    );
    if (!existingButton) {
      debugLog("mode-item created", modeName);
      modeMenu.appendChild(createModeButton(modeName));
    }
  });
}

function initPage() {
  applyTheme(currentTheme);
  ensureConversation(conversationId);
  conversationIdText.textContent = conversationId;
  setSelectedModel(selectedModel);
  setMode(currentMode);
  setMaxContextRounds(maxContextRounds);
  setStreamingEnabled(streamingEnabled);
  renderConversationList();
  renderMessages({ scrollToEnd: false });
  restoreConversationScrollPosition(conversationId);
  updateHeaderTitle();
  updateInputState();
  autoResizeInput();
  updateScrollToBottomButton();
  messageInput.focus();
}

// Conversation storage

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
          lastMessageSummary: item.lastMessageSummary || getConversationLastMessageSummary(item.id),
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
      lastMessageSummary: getConversationLastMessageSummary(initialId),
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
    lastMessageSummary: getConversationLastMessageSummary(id),
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

function getConversationLastMessageSummary(id) {
  return getLastMessageSummary(loadMessages(id));
}

function getLastMessageSummary(messageItems) {
  const latestTextMessage = [...messageItems]
    .reverse()
    .find((message) => message && message.type !== "loading" && message.content);

  if (!latestTextMessage) {
    return "";
  }

  return summarizeMessageContent(latestTextMessage.content);
}

function summarizeMessageContent(content) {
  const text = String(content || "").replace(/\s+/g, " ").trim();
  if (text.length <= 72) {
    return text;
  }

  return `${text.slice(0, 72)}...`;
}

function loadConversationScrollPositions() {
  const loaded = readJson(SCROLL_POSITIONS_KEY, {});
  if (!loaded || typeof loaded !== "object" || Array.isArray(loaded)) {
    return {};
  }

  return Object.fromEntries(
    Object.entries(loaded)
      .map(([id, value]) => [id, Number(value)])
      .filter(([id, value]) => id && Number.isFinite(value) && value >= 0),
  );
}

function saveMessages() {
  localStorage.setItem(getMessagesKey(conversationId), JSON.stringify(messages));
}

function saveConversationScrollPositions() {
  localStorage.setItem(SCROLL_POSITIONS_KEY, JSON.stringify(conversationScrollPositions));
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
      lastMessageSummary: getLastMessageSummary(messages),
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
  saveCurrentScrollPosition(oldId);
  const current = getCurrentConversation();
  const nextConversation = {
    ...(current || {}),
    id: nextId,
    title: current?.title || "新会话",
    createdAt: current?.createdAt || Date.now(),
    updatedAt: Date.now(),
    messageCount: messages.length,
    lastMessageSummary: getLastMessageSummary(messages),
  };

  conversationId = nextId;
  conversationScrollPositions[conversationId] = conversationScrollPositions[oldId] || 0;
  removeConversationScrollPosition(oldId);
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

// Conversation list

function renderConversationList() {
  conversationList.innerHTML = "";
  const visibleConversations = getVisibleConversations();
  const hasSearchQuery = Boolean(normalizeSearchQuery(conversationSearchQuery));
  conversationCountText.textContent = hasSearchQuery
    ? `${visibleConversations.length}/${conversations.length}`
    : String(conversations.length);

  if (visibleConversations.length === 0) {
    const empty = document.createElement("div");
    empty.className = "conversation-empty";
    empty.textContent = conversations.length === 0
      ? "还没有会话。点击上方按钮开始一个新的 Agent 任务。"
      : "没有匹配的会话。";
    conversationList.appendChild(empty);
    return;
  }

  visibleConversations.forEach((conversation) => {
    const item = document.createElement("div");
    item.className = "conversation-item";
    item.tabIndex = 0;
    item.role = "button";
    item.classList.toggle("active", conversation.id === conversationId);
    item.setAttribute("aria-label", `切换到 ${conversation.title}`);
    item.addEventListener("click", () => {
      debugLog("conversation item clicked", conversation.id);
      switchConversation(conversation.id);
    });
    item.addEventListener("keydown", (event) => {
      debugLog("conversation item keydown", event.key, conversation.id);
      if (event.target !== item) {
        return;
      }
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        debugLog("conversation item keyboard activate", conversation.id);
        switchConversation(conversation.id);
      }
    });

    const main = document.createElement("span");
    main.className = "conversation-main";

    const title = document.createElement("span");
    title.className = "conversation-title";
    title.textContent = conversation.title || "新会话";

    const summary = document.createElement("span");
    summary.className = "conversation-summary";
    summary.textContent = conversation.lastMessageSummary || "暂无消息";

    const meta = document.createElement("span");
    meta.className = "conversation-meta";
    meta.textContent = formatRelativeTime(conversation.updatedAt);

    main.append(title, summary, meta);

    const actions = document.createElement("span");
    actions.className = "conversation-actions";

    const renameButton = document.createElement("button");
    renameButton.className = "conversation-action conversation-rename";
    renameButton.type = "button";
    renameButton.textContent = "✎";
    renameButton.title = "重命名会话";
    renameButton.setAttribute("aria-label", `重命名 ${conversation.title}`);
    renameButton.addEventListener("click", (event) => {
      debugLog("renameConversationButton clicked", conversation.id);
      event.stopPropagation();
      renameConversation(conversation.id);
    });

    const deleteButton = document.createElement("button");
    deleteButton.className = "conversation-action conversation-delete";
    deleteButton.type = "button";
    deleteButton.textContent = "×";
    deleteButton.title = "删除会话";
    deleteButton.setAttribute("aria-label", `删除 ${conversation.title}`);
    deleteButton.addEventListener("click", (event) => {
      debugLog("deleteConversationButton clicked", conversation.id);
      event.stopPropagation();
      deleteConversation(conversation.id);
    });

    actions.append(renameButton, deleteButton);
    item.append(main, actions);
    conversationList.appendChild(item);
  });
}

function getVisibleConversations() {
  const query = normalizeSearchQuery(conversationSearchQuery);
  if (!query) {
    return conversations;
  }

  return conversations.filter((conversation) =>
    normalizeSearchQuery(conversation.title || "新会话").includes(query),
  );
}

function normalizeSearchQuery(value) {
  return String(value || "").trim().toLocaleLowerCase("zh-CN");
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

// Message rendering

function renderMessages({ scrollToEnd = true } = {}) {
  messageList.innerHTML = "";
  messageElementMap.clear();

  if (messages.length === 0) {
    renderWelcomePanel();
    updateScrollToBottomButton();
    return;
  }

  messages.forEach((message) => appendMessageElement(message));
  if (scrollToEnd) {
    scrollToBottom();
  } else {
    updateScrollToBottomButton();
  }
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
    debugLog("prompt-card created", prompt);
    promptGrid.appendChild(button);
  });

  card.append(badge, title, description, promptGrid);
  welcomePanel.appendChild(card);
  messageList.appendChild(welcomePanel);
}

function handlePromptCardClick(promptCard) {
  const text = promptCard.textContent.trim();
  debugLog("prompt card clicked", text);

  const input = document.querySelector("#messageInput");
  if (!input) {
    console.warn("messageInput missing");
    return;
  }

  input.value = text;
  updateInputState();
  autoResizeInput();
  input.focus();

  if (typeof input.setSelectionRange === "function") {
    input.setSelectionRange(text.length, text.length);
  }
}

function appendMessage(message) {
  const shouldKeepAtBottom = shouldStickToBottom || isMessageListNearBottom();

  messages.push(message);
  saveMessages();
  removeWelcomePanel();
  appendMessageElement(message);

  if (message.role === "user") {
    maybeRenameConversation(message.content);
  } else {
    updateConversationMeta();
  }

  if (shouldKeepAtBottom) {
    scrollToBottom();
  } else {
    updateScrollToBottomButton();
  }
}

function appendMessageElement(message) {
  const messageItem = createMessageElement(message);
  messageList.appendChild(messageItem);
  messageElementMap.set(message.id, messageItem);
}

function createMessageElement(message) {
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
    content.appendChild(createMessageToolbar(message));
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

  const toolPanel = createToolPanel(message);
  if (toolPanel) {
    content.appendChild(toolPanel);
  }

  content.appendChild(bubble);

  const meta = createMessageMeta(message);
  if (meta) {
    content.appendChild(meta);
  }

  shell.appendChild(content);
  messageItem.appendChild(shell);
  return messageItem;
}

function replaceMessageElement(message, currentMessageId = message.id) {
  const currentElement = messageElementMap.get(currentMessageId);
  if (!currentElement || !currentElement.isConnected) {
    return false;
  }

  const nextElement = createMessageElement(message);
  currentElement.replaceWith(nextElement);
  if (currentMessageId !== message.id) {
    messageElementMap.delete(currentMessageId);
  }
  messageElementMap.set(message.id, nextElement);
  return true;
}

function createMessageToolbar(message) {
  const toolbar = document.createElement("div");
  toolbar.className = "message-toolbar";

  toolbar.appendChild(createRegenerateButton(message));
  toolbar.appendChild(createCopyButton(message.content || ""));
  return toolbar;
}

function createRegenerateButton(message) {
  const button = document.createElement("button");
  button.className = "regenerate-message-button";
  button.type = "button";
  button.textContent = "重新生成";
  button.addEventListener("click", () => {
    debugLog("regenerate-message-button clicked", message.id);
    regenerateAgentReply(message.id);
  });

  return button;
}

function createCopyButton(text) {
  const button = document.createElement("button");
  button.className = "copy-message-button";
  button.type = "button";
  button.textContent = "复制";
  button.addEventListener("click", () => {
    debugLog("copy-message-button clicked");
    copyText(text, button, "已复制");
  });

  return button;
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
  if (message.usedTool !== true) {
    return null;
  }

  const panel = document.createElement("div");
  panel.className = "tool-panel";

  const header = document.createElement("div");
  header.className = "tool-panel-header";

  const title = document.createElement("div");
  title.className = "tool-panel-title";

  const marker = document.createElement("span");
  marker.className = "tool-panel-marker";
  marker.setAttribute("aria-hidden", "true");

  const name = document.createElement("span");
  name.textContent = getToolPanelTitle(message);

  title.append(marker, name);

  const status = document.createElement("span");
  const toolErrorDetail = getToolErrorDetail(message);
  const toolErrorMessage = isToolSuccessful(message) ? "" : getToolErrorMessage(message);
  const statusText = formatToolStatus(message.toolStatus, toolErrorMessage);
  status.className = `tool-status ${statusText === "失败" ? "failed" : "success"}`;
  status.textContent = statusText;

  header.append(title, status);
  panel.appendChild(header);

  const details = document.createElement("div");
  details.className = "tool-panel-details";
  details.appendChild(createToolDetail("工具名称", message.toolName || "未命名工具"));
  details.appendChild(createToolDetail("工具状态", statusText));
  const routeReason = getToolRouteReason(message);
  if (routeReason) {
    details.appendChild(createToolDetail("调用原因", routeReason));
  }

  if (message.toolDurationMs !== undefined && message.toolDurationMs !== null) {
    details.appendChild(createToolDetail("耗时", formatToolDuration(message.toolDurationMs)));
  }

  if (shouldShowToolErrorDetail(message)) {
    details.appendChild(createToolDetail("\u9519\u8bef\u7801", toolErrorDetail.code || "\u672a\u77e5"));
    details.appendChild(createToolDetail("\u9519\u8bef\u4fe1\u606f", toolErrorDetail.message || getToolDisplayError(message) || "\u672a\u77e5"));
    details.appendChild(createToolDetail("\u662f\u5426\u53ef\u91cd\u8bd5", formatToolRetryable(toolErrorDetail.retryable)));
  }

  panel.appendChild(details);

  const sourceList = createReferenceSourceList(message);
  if (sourceList) {
    panel.appendChild(sourceList);
  }

  const result = document.createElement("pre");
  result.className = "tool-panel-result";
  result.textContent = formatToolResult(getToolDisplayResult(message));
  panel.appendChild(result);

  return panel;
}

function getToolPanelTitle(message) {
  if (message.toolName === "web_search") {
    return WEB_SEARCH_STATUS_DONE;
  }

  return message.toolName || "工具调用";
}

function createReferenceSourceList(message) {
  if (message.toolName !== "web_search") {
    return null;
  }

  const sources = extractReferenceSources(message.toolResult, message.content);
  if (sources.length === 0) {
    return null;
  }

  const wrapper = document.createElement("div");
  wrapper.className = "reference-sources";

  const heading = document.createElement("div");
  heading.className = "reference-sources-title";
  heading.textContent = "参考来源";
  wrapper.appendChild(heading);

  const list = document.createElement("ol");
  list.className = "reference-source-list";

  sources.forEach((source) => {
    const item = document.createElement("li");
    const link = document.createElement("a");
    link.href = source.url;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.textContent = source.title || source.url;
    item.appendChild(link);
    list.appendChild(item);
  });

  wrapper.appendChild(list);
  return wrapper;
}

function extractReferenceSources(toolResult, content = "") {
  const root = normalizeToolResultRoot(toolResult);
  const candidates = [];

  appendSourceCandidates(candidates, root.read_pages);
  appendSourceCandidates(candidates, root.search_results);
  appendSourceCandidates(candidates, root.results);
  appendMarkdownSourceCandidates(candidates, content);

  const seen = new Set();
  return candidates.filter((source) => {
    if (!source.url || seen.has(source.url)) {
      return false;
    }

    seen.add(source.url);
    return true;
  });
}

function normalizeToolResultRoot(toolResult) {
  if (!toolResult || typeof toolResult !== "object") {
    return {};
  }

  if (toolResult.result && typeof toolResult.result === "object") {
    return toolResult.result;
  }

  return toolResult;
}

function appendSourceCandidates(candidates, items) {
  if (!Array.isArray(items)) {
    return;
  }

  items.forEach((item) => {
    if (!item || typeof item !== "object") {
      return;
    }

    const url = String(item.url || "").trim();
    if (!url || !/^https?:\/\//i.test(url)) {
      return;
    }

    const title = String(item.title || item.url || "").trim();
    candidates.push({ title, url });
  });
}

function appendMarkdownSourceCandidates(candidates, content) {
  const pattern = /\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g;
  let match;

  while ((match = pattern.exec(String(content || ""))) !== null) {
    candidates.push({
      title: match[1].trim(),
      url: match[2].trim(),
    });
  }
}

function getToolDisplayResult(message) {
  if (message.toolError) {
    return message.toolError;
  }

  if (message.toolResult !== undefined && message.toolResult !== null && message.toolResult !== "") {
    return message.toolResult;
  }

  return "无返回结果";
}

function getToolRouteReason(message) {
  const root = normalizeToolResultRoot(message.toolResult);
  return String(root.route_reason || "").trim();
}

function shouldShowToolErrorDetail(message) {
  return message.usedTool === true && !isToolSuccessful(message) && isToolFailed(message);
}

function isToolFailed(message) {
  return Boolean(
    message.toolStatus === "failed" ||
      message.toolStatus === false ||
      message.toolError ||
      message.toolErrorCode ||
      message.toolErrorMessage ||
      message.toolErrorDetail,
  );
}

function isToolSuccessful(message) {
  return message.toolStatus === "success" || message.toolStatus === true;
}

function getToolErrorDetail(message) {
  const detail = normalizeToolErrorDetail(message.toolErrorDetail);
  return {
    code: detail.code || message.toolErrorCode || "",
    message: detail.message || message.toolErrorMessage || "",
    retryable: detail.retryable ?? message.toolRetryable,
  };
}

function normalizeToolErrorDetail(detail) {
  if (!detail || typeof detail !== "object") {
    return {};
  }

  return {
    code: detail.code,
    message: detail.message,
    retryable: detail.retryable,
  };
}

function getToolErrorMessage(message) {
  return getToolErrorDetail(message).message || message.toolError || "";
}

function getToolDisplayError(message) {
  return getToolErrorMessage(message) || message.toolError || "";
}

function formatToolRetryable(value) {
  if (value === true) {
    return "\u662f";
  }

  if (value === false) {
    return "\u5426";
  }

  return "\u672a\u77e5";
}

function createToolDetail(label, value) {
  const item = document.createElement("div");
  item.className = "tool-panel-detail";

  const labelElement = document.createElement("span");
  labelElement.textContent = label;

  const valueElement = document.createElement("strong");
  valueElement.textContent = value;

  item.append(labelElement, valueElement);
  return item;
}

function formatToolStatus(status, error) {
  if (error || status === "failed" || status === false) {
    return "失败";
  }

  if (status === "running") {
    return "执行中";
  }

  return "已完成";
}

function formatToolDuration(durationMs) {
  const value = Number(durationMs);
  if (!Number.isFinite(value)) {
    return String(durationMs);
  }

  if (value < 1000) {
    return `${Math.max(0, Math.round(value))} ms`;
  }

  return `${(value / 1000).toFixed(2)} s`;
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

// Markdown rendering

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
    debugLog("code-copy-button clicked", language || "text");
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

// Clipboard and indicators

async function copyText(text, button, successText) {
  debugLog("copyText start", {
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
  const shouldKeepAtBottom = shouldStickToBottom || isMessageListNearBottom();
  const previousScrollTop = messageList.scrollTop;
  const messageIndex = messages.findIndex((message) => message.id === messageId);
  const currentMessage = messages[messageIndex];
  if (!currentMessage) {
    return;
  }

  const nextRole = updates.role || currentMessage?.role;
  const nextType = updates.type || currentMessage?.type;
  const shouldShowNewMessageNotice =
    !shouldKeepAtBottom && (nextRole === "agent" || nextRole === "error") && nextType !== "loading";
  const updatedMessage = {
    ...currentMessage,
    ...updates,
  };

  messages = [
    ...messages.slice(0, messageIndex),
    updatedMessage,
    ...messages.slice(messageIndex + 1),
  ];

  saveMessages();
  updateConversationMeta();
  if (!replaceMessageElement(updatedMessage, messageId)) {
    renderMessages({ scrollToEnd: false });
  }

  if (shouldKeepAtBottom) {
    scrollToBottom();
  } else if (shouldShowNewMessageNotice) {
    messageList.scrollTop = previousScrollTop;
    showNewMessageNotice();
  } else {
    messageList.scrollTop = previousScrollTop;
    updateScrollToBottomButton();
  }
}

// Scrolling

function scrollToBottom({ behavior = "smooth" } = {}) {
  const messageList = document.querySelector("#messageList");
  if (!messageList) return;
  const button = document.querySelector("#scrollToBottomButton");
  const notice = document.querySelector("#newMessageNotice");
  shouldStickToBottom = true;

  messageList.scrollTo({
    top: messageList.scrollHeight,
    behavior,
  });
  if (button) {
    button.classList.add("is-hidden");
  }
  if (notice) {
    notice.classList.add("is-hidden");
  }
}

function saveCurrentScrollPosition(id = conversationId) {
  if (!id) return;

  conversationScrollPositions[id] = Math.max(0, Math.round(messageList.scrollTop));
  saveConversationScrollPositions();
}

function restoreConversationScrollPosition(id) {
  const savedScrollTop = conversationScrollPositions[id];

  window.requestAnimationFrame(() => {
    if (id !== conversationId) {
      return;
    }

    if (Number.isFinite(savedScrollTop)) {
      const maxScrollTop = Math.max(0, messageList.scrollHeight - messageList.clientHeight);
      messageList.scrollTop = Math.min(savedScrollTop, maxScrollTop);
      shouldStickToBottom = isMessageListNearBottom();
      updateScrollToBottomButton();
      return;
    }

    scrollToBottom({ behavior: "auto" });
  });
}

function removeConversationScrollPosition(id) {
  if (!id || !(id in conversationScrollPositions)) {
    return;
  }

  delete conversationScrollPositions[id];
  saveConversationScrollPositions();
}

function handleMessageListScroll() {
  shouldStickToBottom = isMessageListNearBottom();
  saveCurrentScrollPosition();
  updateScrollToBottomButton();
}

function isMessageListNearBottom() {
  const messageList = document.querySelector("#messageList");
  if (!messageList) return true;

  const distanceToBottom = messageList.scrollHeight - messageList.scrollTop - messageList.clientHeight;
  return distanceToBottom <= AUTO_SCROLL_THRESHOLD_PX;
}

function updateScrollToBottomButton() {
  const button = document.querySelector("#scrollToBottomButton");
  if (!button) return;

  const isNearBottom = isMessageListNearBottom();
  button.classList.toggle("is-hidden", isNearBottom);

  if (isNearBottom) {
    hideNewMessageNotice();
  }
}

function showNewMessageNotice() {
  const notice = document.querySelector("#newMessageNotice");
  if (!notice) return;

  notice.classList.remove("is-hidden");
  updateScrollToBottomButton();
}

function hideNewMessageNotice() {
  const notice = document.querySelector("#newMessageNotice");
  if (!notice) return;

  notice.classList.add("is-hidden");
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

function looksLikeWebSearchRequest(text) {
  const normalized = String(text || "").toLowerCase().trim();
  if (!normalized) {
    return false;
  }

  const searchKeywords = [
    "搜索",
    "联网",
    "网上",
    "查一下",
    "帮我查",
    "最新",
    "最近",
    "新闻",
    "官网",
    "资料",
    "价格",
    "论文",
    "教程",
    "github",
    "search",
    "latest",
    "news",
    "current",
    "recent",
    "website",
    "official",
    "price",
    "today",
  ];

  return searchKeywords.some((keyword) => normalized.includes(keyword));
}

function getToolStatusContent(metadata) {
  if (metadata?.usedTool === true && metadata?.toolName === "web_search") {
    return WEB_SEARCH_STATUS_DONE;
  }

  return null;
}

function normalizeStreamStatusMessage(message) {
  const normalized = String(message || "").trim();
  return WEB_SEARCH_STATUS_MESSAGES.has(normalized) ? normalized : "";
}

// Input state

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
  debugLog("setLoading", nextLoading);
  isLoading = nextLoading;
  messageInput.disabled = nextLoading;
  modelSelect.disabled = nextLoading;
  settingsButton.disabled = nextLoading;
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
  debugLog("setMode start", mode);
  currentMode = normalizeMode(mode);
  localStorage.setItem(MODE_KEY, currentMode);
  currentModeText.textContent = currentMode;
  settingsModeSelect.value = currentMode;

  modeButtons.forEach((button) => {
    button.classList.toggle("active", button.dataset.mode === currentMode);
  });
  debugLog("mode changed", currentMode);
}

function setSelectedModel(model) {
  selectedModel = normalizeModel(model);
  localStorage.setItem(SELECTED_MODEL_KEY, selectedModel);
  modelSelect.value = selectedModel;
  settingsModelSelect.value = selectedModel;
  currentModelText.textContent = selectedModel;
  debugLog("model changed", selectedModel);
}

function setMaxContextRounds(value) {
  maxContextRounds = normalizeMaxContextRounds(value);
  localStorage.setItem(MAX_CONTEXT_ROUNDS_KEY, String(maxContextRounds));
  settingsMaxContextInput.value = String(maxContextRounds);
  debugLog("max context rounds changed", maxContextRounds);
}

function setStreamingEnabled(value) {
  streamingEnabled = Boolean(value);
  localStorage.setItem(STREAMING_ENABLED_KEY, String(streamingEnabled));
  settingsStreamingToggle.checked = streamingEnabled;
  debugLog("streaming changed", streamingEnabled);
}

function applyTheme(theme) {
  currentTheme = normalizeTheme(theme);
  document.documentElement.dataset.theme = currentTheme;
  localStorage.setItem(THEME_KEY, currentTheme);

  const isDark = currentTheme === "dark";
  themeToggleButton.textContent = isDark ? "浅色" : "深色";
  themeToggleButton.setAttribute(
    "aria-label",
    isDark ? "切换浅色主题" : "切换深色主题",
  );
  themeToggleButton.setAttribute("aria-pressed", String(isDark));
  debugLog("theme changed", currentTheme);
}

function toggleTheme() {
  applyTheme(currentTheme === "dark" ? "light" : "dark");
}

// Agent request flow

async function requestAgentReply(
  message,
  {
    targetConversationId = conversationId,
    targetMode = currentMode,
    targetModel = selectedModel,
    targetMaxContextRounds = maxContextRounds,
    targetStreamingEnabled = streamingEnabled,
    onChunk = null,
    onToolMetadata = null,
    onStatus = null,
  } = {},
) {
  debugLog("requestAgentReply start", {
    conversationId: targetConversationId,
    messageLength: message.length,
    mode: targetMode,
    model: targetModel,
    maxContextRounds: targetMaxContextRounds,
    streamingEnabled: targetStreamingEnabled,
  });
  const requestBody = {
    message,
    system_prompt: MODE_PROMPTS[targetMode],
    model: targetModel,
    conversation_id: targetConversationId,
    max_context_rounds: targetMaxContextRounds,
  };

  activeAbortController = new AbortController();
  let didTimeout = false;
  const timeoutTimer = window.setTimeout(() => {
    didTimeout = true;
    activeAbortController.abort();
  }, REQUEST_TIMEOUT_MS);

  try {
    const result = targetStreamingEnabled
      ? await requestStreamingAgentReply(
          requestBody,
          activeAbortController.signal,
          targetConversationId,
          onChunk,
          onToolMetadata,
          onStatus,
        )
      : await requestJsonAgentReply(
          requestBody,
          activeAbortController.signal,
          targetConversationId,
        );
    window.clearTimeout(timeoutTimer);
    activeAbortController = null;
    return result;
  } catch (error) {
    console.warn("POST /chat request error", error);
    window.clearTimeout(timeoutTimer);
    activeAbortController = null;
    if (error.name === "AbortError") {
      if (didTimeout) {
        throw new Error(toFriendlyError("Request timed out"));
      }
      return { aborted: true };
    }
    if (error instanceof Error && error.message && error.name !== "TypeError") {
      throw error;
    }
    throw new Error(CHAT_FAILURE_MESSAGE);
  }
}

async function requestJsonAgentReply(requestBody, signal, fallbackConversationId) {
  debugLog("POST /chat request start", requestBody);
  const response = await fetch(CHAT_API_URL, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    body: JSON.stringify(requestBody),
    signal,
  });
  debugLog("POST /chat response received", {
    ok: response.ok,
    status: response.status,
    statusText: response.statusText,
  });
  if (!response.ok) {
    const data = await parseJsonResponse(response);
    const message = toFriendlyError(data.error || response.status);
    console.warn("Chat request failed:", message);
    throw new Error(message || CHAT_FAILURE_MESSAGE);
  }

  const data = await parseJsonResponse(response);
  debugLog("POST /chat response body", data);
  if (!data.success) {
    const message = toFriendlyError(data.error);
    console.warn("Chat API returned an error:", message);
    throw new Error(message || CHAT_FAILURE_MESSAGE);
  }

  return {
    aborted: false,
    reply: data.reply || "",
    model: data.model || "",
    conversationId: data.conversation_id || fallbackConversationId,
    usedTool: data.used_tool,
    toolName: data.tool_name,
    toolStatus: data.tool_status,
    toolResult: data.tool_result,
    toolError: data.tool_error,
    toolErrorCode: data.tool_error_code,
    toolErrorMessage: data.tool_error_message,
    toolRetryable: data.tool_retryable,
    toolErrorDetail: data.tool_error_detail,
    toolDurationMs: data.tool_duration_ms,
  };
}

async function requestStreamingAgentReply(
  requestBody,
  signal,
  fallbackConversationId,
  onChunk,
  onToolMetadata,
  onStatus,
) {
  debugLog("POST /chat/stream request start", requestBody);
  const response = await fetch(CHAT_STREAM_API_URL, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
    },
    body: JSON.stringify(requestBody),
    signal,
  });

  if (!response.ok) {
    const data = await parseJsonResponse(response);
    const message = toFriendlyError(data.error || response.status);
    console.warn("Streaming chat request failed:", message);
    throw new Error(message || CHAT_FAILURE_MESSAGE);
  }

  if (!response.body) {
    throw new Error("浏览器不支持读取流式响应。");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let reply = "";
  let metadata = {};
  let done = {};
  const handleStreamEvent = (event) => {
    if (!event) {
      return;
    }

    if (event.event === "metadata") {
      metadata = event.data || {};
      if (typeof onToolMetadata === "function") {
        onToolMetadata(normalizeToolMetadata(metadata));
      }
      return;
    }

    if (event.event === "status") {
      const message = normalizeStreamStatusMessage(event.data?.message);
      if (message && typeof onStatus === "function") {
        onStatus(message);
      }
      return;
    }

    if (event.event === "chunk") {
      const content = event.data?.content || "";
      reply += content;
      if (typeof onChunk === "function") {
        onChunk(content, reply);
      }
      return;
    }

    if (event.event === "done") {
      done = event.data || {};
      if (typeof onToolMetadata === "function") {
        onToolMetadata(normalizeToolMetadata(done));
      }
      return;
    }

    if (event.event === "error") {
      throw new Error(toFriendlyError(event.data?.error));
    }
  };

  while (true) {
    const { value, done: readerDone } = await reader.read();
    if (readerDone) {
      break;
    }

    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split(/\n\n/);
    buffer = parts.pop() || "";

    parts.forEach((part) => {
      handleStreamEvent(parseSseEvent(part));
    });
  }

  if (buffer.trim()) {
    handleStreamEvent(parseSseEvent(buffer));
  }

  return {
    aborted: false,
    reply,
    model: done.model || metadata.model || "",
    conversationId: done.conversation_id || metadata.conversation_id || fallbackConversationId,
    usedTool: done.used_tool ?? metadata.used_tool ?? false,
    toolName: done.tool_name ?? metadata.tool_name,
    toolStatus: done.tool_status ?? metadata.tool_status,
    toolResult: done.tool_result ?? metadata.tool_result,
    toolError: done.tool_error ?? metadata.tool_error,
    toolErrorCode: done.tool_error_code ?? metadata.tool_error_code,
    toolErrorMessage: done.tool_error_message ?? metadata.tool_error_message,
    toolRetryable: done.tool_retryable ?? metadata.tool_retryable,
    toolErrorDetail: done.tool_error_detail ?? metadata.tool_error_detail,
    toolDurationMs: done.tool_duration_ms ?? metadata.tool_duration_ms,
  };
}

function normalizeToolMetadata(data = {}) {
  return {
    usedTool: data.used_tool,
    toolName: data.tool_name,
    toolStatus: data.tool_status,
    toolResult: data.tool_result,
    toolError: data.tool_error,
    toolErrorCode: data.tool_error_code,
    toolErrorMessage: data.tool_error_message,
    toolRetryable: data.tool_retryable,
    toolErrorDetail: data.tool_error_detail,
    toolDurationMs: data.tool_duration_ms,
  };
}

function parseSseEvent(rawEvent) {
  const lines = String(rawEvent || "").split(/\r?\n/);
  let eventName = "message";
  const dataLines = [];

  lines.forEach((line) => {
    if (line.startsWith("event:")) {
      eventName = line.slice(6).trim();
    } else if (line.startsWith("data:")) {
      dataLines.push(line.slice(5).trimStart());
    }
  });

  if (dataLines.length === 0) {
    return null;
  }

  try {
    return {
      event: eventName,
      data: JSON.parse(dataLines.join("\n")),
    };
  } catch {
    return {
      event: eventName,
      data: {},
    };
  }
}

function abortCurrentRequest() {
  if (activeAbortController) {
    activeAbortController.abort();
  }
}

function findPreviousUserMessage(messageIndex) {
  for (let index = messageIndex - 1; index >= 0; index -= 1) {
    if (messages[index]?.role === "user") {
      return messages[index];
    }
  }

  return null;
}

async function regenerateAgentReply(messageId) {
  debugLog("regenerateAgentReply start", messageId);
  if (guardActionDuringLoading()) {
    debugLog("regenerateAgentReply blocked by loading");
    return;
  }

  const targetIndex = messages.findIndex((message) => message.id === messageId);
  const targetMessage = messages[targetIndex];
  if (targetIndex < 0 || targetMessage?.role !== "agent" || targetMessage.type === "loading") {
    console.warn("regenerateAgentReply target missing", messageId);
    return;
  }

  const previousUserMessage = findPreviousUserMessage(targetIndex);
  if (!previousUserMessage) {
    window.alert("找不到这条 AI 回复前面的用户消息，无法重新生成。");
    return;
  }

  const originalMessage = { ...targetMessage };
  const likelyWebSearch = looksLikeWebSearchRequest(previousUserMessage.content || "");
  const initialLoadingText = likelyWebSearch ? WEB_SEARCH_STATUS_SEARCHING : "Agent 正在重新生成...";
  const loadingMessage = createMessage("agent", initialLoadingText, "loading");
  let hasReceivedFirstChunk = false;
  let searchStatusTimer = null;
  const updateLoadingStatus = (statusMessage) => {
    const normalizedStatus = normalizeStreamStatusMessage(statusMessage);
    if (hasReceivedFirstChunk || !normalizedStatus) {
      return;
    }
    if (searchStatusTimer) {
      window.clearTimeout(searchStatusTimer);
      searchStatusTimer = null;
    }
    updateMessage(loadingMessage.id, {
      type: "loading",
      role: "agent",
      content: normalizedStatus,
      createdAt: getCurrentTime(),
    });
  };
  const requestContext = {
    targetConversationId: conversationId,
    targetMode: currentMode,
    targetModel: selectedModel,
    targetMaxContextRounds: maxContextRounds,
    targetStreamingEnabled: streamingEnabled,
    onToolMetadata: (metadata) => {
      const statusContent = getToolStatusContent(metadata);
      if (hasReceivedFirstChunk) {
        return;
      }
      const metadataUpdates = {
        type: "loading",
        role: "agent",
        ...metadata,
        createdAt: getCurrentTime(),
      };
      const nextStatusContent =
        statusContent || (likelyWebSearch && streamingEnabled ? WEB_SEARCH_STATUS_ORGANIZING : null);
      if (nextStatusContent) {
        metadataUpdates.content = nextStatusContent;
      }
      updateMessage(loadingMessage.id, metadataUpdates);
    },
    onStatus: (statusMessage) => {
      updateLoadingStatus(statusMessage);
    },
    onChunk: (chunk, partialReply) => {
      hasReceivedFirstChunk = true;
      if (searchStatusTimer) {
        window.clearTimeout(searchStatusTimer);
      }
      updateMessage(loadingMessage.id, {
        type: "text",
        role: "agent",
        content: partialReply || "Agent 正在重新生成...",
        createdAt: getCurrentTime(),
      });
    },
  };
  const shouldKeepAtBottom = shouldStickToBottom || isMessageListNearBottom();
  const previousScrollTop = messageList.scrollTop;

  messages = [
    ...messages.slice(0, targetIndex),
    loadingMessage,
    ...messages.slice(targetIndex + 1),
  ];
  saveMessages();
  updateConversationMeta();
  if (!replaceMessageElement(loadingMessage, targetMessage.id)) {
    renderMessages({ scrollToEnd: false });
  }

  if (shouldKeepAtBottom) {
    scrollToBottom();
  } else {
    messageList.scrollTop = previousScrollTop;
    updateScrollToBottomButton();
  }

  setLoading(true);
  if (likelyWebSearch && streamingEnabled) {
    searchStatusTimer = window.setTimeout(() => {
      if (!hasReceivedFirstChunk) {
        updateMessage(loadingMessage.id, {
          type: "loading",
          role: "agent",
          content: WEB_SEARCH_STATUS_ORGANIZING,
          createdAt: getCurrentTime(),
        });
      }
    }, 250);
  }

  try {
    const result = await requestAgentReply(previousUserMessage.content || "", requestContext);
    debugLog("regenerateAgentReply received result", result);
    if (result.aborted) {
      if (searchStatusTimer) {
        window.clearTimeout(searchStatusTimer);
      }
      updateMessage(loadingMessage.id, originalMessage);
      return;
    }

    if (result.conversationId && result.conversationId !== conversationId) {
      replaceActiveConversationId(result.conversationId);
    }

    if (result.model) {
      currentModelText.textContent = result.model;
    }

    hasReceivedFirstChunk = true;
    if (searchStatusTimer) {
      window.clearTimeout(searchStatusTimer);
    }
    updateMessage(loadingMessage.id, {
      type: "text",
      role: "agent",
      content: result.reply || "Agent 没有返回文本内容。",
      model: result.model,
      usedTool: result.usedTool,
      toolName: result.toolName,
      toolStatus: result.toolStatus,
      toolResult: result.toolResult,
      toolError: result.toolError,
      toolErrorCode: result.toolErrorCode,
      toolErrorMessage: result.toolErrorMessage,
      toolRetryable: result.toolRetryable,
      toolErrorDetail: result.toolErrorDetail,
      toolDurationMs: result.toolDurationMs,
      createdAt: getCurrentTime(),
    });
  } catch (error) {
    console.warn("regenerateAgentReply error", error);
    updateMessage(loadingMessage.id, originalMessage);
    window.alert(error instanceof Error ? error.message : CHAT_FAILURE_MESSAGE);
  } finally {
    if (searchStatusTimer) {
      window.clearTimeout(searchStatusTimer);
    }
    setLoading(false);
    messageInput.focus();
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
  const text = normalizeErrorText(errorText);
  const knownError = FRIENDLY_ERROR_MESSAGES.find((item) => text.includes(item.match));
  return knownError ? knownError.message : text || "请求失败，请稍后重试。";
}

function normalizeErrorText(errorValue) {
  if (!errorValue) {
    return "";
  }
  if (typeof errorValue === "object") {
    return String(errorValue.message || errorValue.error_message || errorValue.code || "");
  }
  return String(errorValue);
}

// Settings panel

function openSettingsPanel() {
  if (guardActionDuringLoading()) {
    return;
  }

  syncSettingsControls();
  settingsOverlay.hidden = false;
  document.body.classList.add("settings-open");
  settingsPanelFocusTarget().focus();
}

function closeSettingsPanel() {
  settingsOverlay.hidden = true;
  document.body.classList.remove("settings-open");
  settingsButton.focus();
}

function settingsPanelFocusTarget() {
  return settingsModelSelect;
}

function syncSettingsControls() {
  settingsModelSelect.value = selectedModel;
  settingsModeSelect.value = currentMode;
  settingsMaxContextInput.value = String(maxContextRounds);
  settingsStreamingToggle.checked = streamingEnabled;
}

function clearAllLocalConversations() {
  debugLog("clearAllLocalConversations start");
  if (guardActionDuringLoading()) {
    return;
  }

  if (!window.confirm("确定清空所有本地会话吗？此操作不可恢复。")) {
    return;
  }

  const keysToRemove = [];
  for (let index = 0; index < localStorage.length; index += 1) {
    const key = localStorage.key(index);
    if (
      key === ACTIVE_CONVERSATION_KEY ||
      key === CONVERSATIONS_KEY ||
      key === SCROLL_POSITIONS_KEY ||
      key?.startsWith(MESSAGES_KEY_PREFIX)
    ) {
      keysToRemove.push(key);
    }
  }

  keysToRemove.forEach((key) => localStorage.removeItem(key));

  conversationId = createConversationId();
  messages = [];
  conversationScrollPositions = {};
  conversations = [
    {
      id: conversationId,
      title: "新会话",
      createdAt: Date.now(),
      updatedAt: Date.now(),
      messageCount: 0,
      lastMessageSummary: "",
    },
  ];

  localStorage.setItem(ACTIVE_CONVERSATION_KEY, conversationId);
  saveConversations();
  saveMessages();
  saveConversationScrollPositions();
  conversationSearchQuery = "";
  conversationSearchInput.value = "";
  conversationIdText.textContent = conversationId;
  renderConversationList();
  renderMessages();
  updateHeaderTitle();
  closeSettingsPanel();
  messageInput.focus();
}

// Conversation actions

async function sendCurrentMessage() {
  debugLog("sendCurrentMessage start", {
    isLoading,
    inputLength: messageInput.value.length,
  });
  if (isLoading) {
    debugLog("sendCurrentMessage abort current request");
    abortCurrentRequest();
    return;
  }

  const userText = messageInput.value.trim();
  if (!userText) {
    debugLog("sendCurrentMessage empty input");
    updateInputState();
    return;
  }

  appendMessage(createMessage("user", userText));
  debugLog("sendCurrentMessage user message appended");
  messageInput.value = "";
  autoResizeInput();
  updateInputState();

  const likelyWebSearch = looksLikeWebSearchRequest(userText);
  const initialLoadingText = likelyWebSearch ? WEB_SEARCH_STATUS_SEARCHING : "Agent 正在思考";
  const loadingMessage = createMessage("agent", initialLoadingText, "loading");
  appendMessage(loadingMessage);
  debugLog("sendCurrentMessage loading message appended", loadingMessage.id);
  setLoading(true);

  let hasReceivedFirstChunk = false;
  let searchStatusTimer = null;
  const updateLoadingStatus = (statusMessage) => {
    const normalizedStatus = normalizeStreamStatusMessage(statusMessage);
    if (hasReceivedFirstChunk || !normalizedStatus) {
      return;
    }
    if (searchStatusTimer) {
      window.clearTimeout(searchStatusTimer);
      searchStatusTimer = null;
    }
    updateMessage(loadingMessage.id, {
      type: "loading",
      role: "agent",
      content: normalizedStatus,
      createdAt: getCurrentTime(),
    });
  };
  if (likelyWebSearch && streamingEnabled) {
    searchStatusTimer = window.setTimeout(() => {
      if (!hasReceivedFirstChunk) {
        updateMessage(loadingMessage.id, {
          type: "loading",
          role: "agent",
          content: WEB_SEARCH_STATUS_ORGANIZING,
          createdAt: getCurrentTime(),
        });
      }
    }, 250);
  }
  const thinkingTimer = window.setTimeout(() => {
    if (!hasReceivedFirstChunk) {
      updateMessage(loadingMessage.id, {
        type: "loading",
        role: "agent",
        content: likelyWebSearch ? WEB_SEARCH_STATUS_ORGANIZING : "模型正在思考中，请稍等...",
        createdAt: getCurrentTime(),
      });
    }
  }, THINKING_NOTICE_DELAY_MS);

  try {
    const result = await requestAgentReply(userText, {
      onToolMetadata: (metadata) => {
        const statusContent = getToolStatusContent(metadata);
        if (hasReceivedFirstChunk) {
          return;
        }
        const metadataUpdates = {
          type: "loading",
          role: "agent",
          ...metadata,
          createdAt: getCurrentTime(),
        };
        const nextStatusContent =
          statusContent || (likelyWebSearch && streamingEnabled ? WEB_SEARCH_STATUS_ORGANIZING : null);
        if (nextStatusContent) {
          metadataUpdates.content = nextStatusContent;
        }
        updateMessage(loadingMessage.id, metadataUpdates);
      },
      onStatus: (statusMessage) => {
        updateLoadingStatus(statusMessage);
      },
      onChunk: (chunk, partialReply) => {
        hasReceivedFirstChunk = true;
        if (searchStatusTimer) {
          window.clearTimeout(searchStatusTimer);
        }
        window.clearTimeout(thinkingTimer);
        updateMessage(loadingMessage.id, {
          type: "text",
          role: "agent",
          content: partialReply || "Agent 正在生成...",
          createdAt: getCurrentTime(),
        });
      },
    });
    debugLog("sendCurrentMessage received result", result);
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
    if (searchStatusTimer) {
      window.clearTimeout(searchStatusTimer);
    }
    window.clearTimeout(thinkingTimer);

    if (result.conversationId && result.conversationId !== conversationId) {
      replaceActiveConversationId(result.conversationId);
    }

    if (result.model) {
      currentModelText.textContent = result.model;
    }

    updateMessage(loadingMessage.id, {
      type: "text",
      role: "agent",
      content: result.reply || "Agent 没有返回文本内容。",
      model: result.model,
      usedTool: result.usedTool,
      toolName: result.toolName,
      toolStatus: result.toolStatus,
      toolResult: result.toolResult,
      toolError: result.toolError,
      toolErrorCode: result.toolErrorCode,
      toolErrorMessage: result.toolErrorMessage,
      toolRetryable: result.toolRetryable,
      toolErrorDetail: result.toolErrorDetail,
      toolDurationMs: result.toolDurationMs,
      createdAt: getCurrentTime(),
    });
    debugLog("sendCurrentMessage agent reply rendered", loadingMessage.id);
  } catch (error) {
    console.warn("sendCurrentMessage error", error);
    updateMessage(loadingMessage.id, {
      type: "text",
      role: "error",
      content: error instanceof Error ? error.message : CHAT_FAILURE_MESSAGE,
      createdAt: getCurrentTime(),
    });
  } finally {
    if (searchStatusTimer) {
      window.clearTimeout(searchStatusTimer);
    }
    window.clearTimeout(thinkingTimer);
    setLoading(false);
    messageInput.focus();
  }
}

function submitChatForm(source) {
  debugLog("submitChatForm start", source);
  if (typeof chatForm.requestSubmit === "function") {
    chatForm.requestSubmit();
    return;
  }

  sendCurrentMessage();
}

function startNewConversation() {
  debugLog("startNewConversation start");
  if (guardActionDuringLoading()) {
    debugLog("startNewConversation blocked by loading");
    return;
  }

  saveCurrentScrollPosition();
  conversationId = createConversationId();
  removeConversationScrollPosition(conversationId);
  conversationSearchQuery = "";
  conversationSearchInput.value = "";
  debugLog("newConversation created", conversationId);
  localStorage.setItem(ACTIVE_CONVERSATION_KEY, conversationId);
  conversations.unshift({
    id: conversationId,
    title: "新会话",
    createdAt: Date.now(),
    updatedAt: Date.now(),
    messageCount: 0,
    lastMessageSummary: "",
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

function renameConversation(targetId) {
  debugLog("renameConversation start", targetId);
  if (guardActionDuringLoading()) {
    debugLog("renameConversation blocked by loading", targetId);
    return;
  }

  const target = conversations.find((item) => item.id === targetId);
  if (!target) {
    return;
  }

  const currentTitle = target.title || "新会话";
  const nextTitle = window.prompt("请输入新的会话标题", currentTitle);
  if (nextTitle === null) {
    return;
  }

  const cleanTitle = nextTitle.replace(/\s+/g, " ").trim().slice(0, 60);
  if (!cleanTitle || cleanTitle === currentTitle) {
    return;
  }

  conversations = conversations.map((item) =>
    item.id === targetId ? { ...item, title: cleanTitle } : item,
  );
  saveConversations();
  renderConversationList();

  if (targetId === conversationId) {
    updateHeaderTitle();
  }

  messageInput.focus();
}

function switchConversation(nextId) {
  debugLog("switchConversation start", nextId);
  if (nextId === conversationId || guardActionDuringLoading()) {
    debugLog("switchConversation skipped", {
      nextId,
      conversationId,
      isLoading,
    });
    return;
  }

  saveCurrentScrollPosition();
  conversationId = nextId;
  localStorage.setItem(ACTIVE_CONVERSATION_KEY, conversationId);
  messages = loadMessages(conversationId);
  conversationIdText.textContent = conversationId;
  renderConversationList();
  renderMessages({ scrollToEnd: false });
  restoreConversationScrollPosition(conversationId);
  updateHeaderTitle();
  messageInput.value = "";
  autoResizeInput();
  updateInputState();
  messageInput.focus();
}

function deleteConversation(targetId) {
  debugLog("deleteConversation start", targetId);
  if (guardActionDuringLoading()) {
    debugLog("deleteConversation blocked by loading", targetId);
    return;
  }

  const target = conversations.find((item) => item.id === targetId);
  if (!window.confirm(`确定删除“${target?.title || "该会话"}”吗？此操作不可恢复。`)) {
    return;
  }

  localStorage.removeItem(getMessagesKey(targetId));
  removeConversationScrollPosition(targetId);
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
        lastMessageSummary: "",
      },
    ];
  }

  if (targetId === conversationId) {
    conversationId = conversations[0].id;
    messages = loadMessages(conversationId);
    localStorage.setItem(ACTIVE_CONVERSATION_KEY, conversationId);
    conversationIdText.textContent = conversationId;
    renderMessages({ scrollToEnd: false });
    restoreConversationScrollPosition(conversationId);
    updateHeaderTitle();
  }

  saveConversations();
  renderConversationList();
  messageInput.focus();
}

function clearCurrentConversation() {
  debugLog("clearCurrentConversation start", conversationId);
  if (guardActionDuringLoading()) {
    debugLog("clearCurrentConversation blocked by loading");
    return;
  }

  if (!window.confirm("确定要清空当前会话吗？")) {
    debugLog("clearCurrentConversation cancelled");
    return;
  }

  messages = [];
  saveMessages();
  removeConversationScrollPosition(conversationId);
  updateConversationMeta({
    messageCount: 0,
  });
  renderMessages();
  messageInput.focus();
}

function guardActionDuringLoading() {
  if (!isLoading) {
    return false;
  }

  debugLog("guardActionDuringLoading blocked action");
  window.alert("当前正在生成回复，请先点击“停止生成”。");
  return true;
}

// Event bindings

chatForm.addEventListener("submit", (event) => {
  debugLog("chatForm submit start");
  event.preventDefault();
  sendCurrentMessage();
});

sendButton.addEventListener("click", () => {
  debugLog("sendButton clicked");
});

messageList.addEventListener("scroll", handleMessageListScroll);

scrollToBottomButton.addEventListener("click", () => {
  scrollToBottom({ behavior: "smooth" });
});

newMessageNotice.addEventListener("click", () => {
  scrollToBottom({ behavior: "smooth" });
});

document.addEventListener("click", (event) => {
  if (!(event.target instanceof Element)) {
    return;
  }

  const promptCard = event.target.closest(".prompt-card");
  if (!promptCard) {
    return;
  }

  handlePromptCardClick(promptCard);
});

messageInput.addEventListener("keydown", (event) => {
  debugLog("messageInput keydown", {
    key: event.key,
    shiftKey: event.shiftKey,
  });
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    debugLog("messageInput enter submit");
    submitChatForm("keyboard-enter");
  }
});

messageInput.addEventListener("input", () => {
  debugLog("messageInput input", {
    length: messageInput.value.length,
  });
  updateInputState();
  autoResizeInput();
});

newConversationButton.addEventListener("click", () => {
  debugLog("new conversation clicked");
  startNewConversation();
});

conversationSearchInput.addEventListener("input", () => {
  conversationSearchQuery = conversationSearchInput.value;
  renderConversationList();
});

modelSelect.addEventListener("change", () => {
  setSelectedModel(modelSelect.value);
  messageInput.focus();
});

themeToggleButton.addEventListener("click", () => {
  toggleTheme();
  messageInput.focus();
});

settingsButton.addEventListener("click", () => {
  openSettingsPanel();
});

settingsCloseButton.addEventListener("click", () => {
  closeSettingsPanel();
});

settingsOverlay.addEventListener("click", (event) => {
  if (event.target === settingsOverlay) {
    closeSettingsPanel();
  }
});

settingsModelSelect.addEventListener("change", () => {
  setSelectedModel(settingsModelSelect.value);
});

settingsMaxContextInput.addEventListener("change", () => {
  setMaxContextRounds(settingsMaxContextInput.value);
});

settingsStreamingToggle.addEventListener("change", () => {
  setStreamingEnabled(settingsStreamingToggle.checked);
});

settingsModeSelect.addEventListener("change", () => {
  setMode(settingsModeSelect.value);
});

clearAllConversationsButton.addEventListener("click", () => {
  clearAllLocalConversations();
});

clearConversationButton.addEventListener("click", () => {
  debugLog("clear conversation clicked");
  clearCurrentConversation();
});

modeButtons.forEach((button) => {
  button.addEventListener("click", () => {
    debugLog("modeButton clicked", button.dataset.mode);
    setMode(button.dataset.mode);
    messageInput.focus();
  });
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !settingsOverlay.hidden) {
    closeSettingsPanel();
  }
});
