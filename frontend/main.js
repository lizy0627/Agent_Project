// Configuration

const DEBUG = false;
function debugLog(...args) { if (DEBUG) console.log(...args); }

const CHAT_API_URL = "http://127.0.0.1:8000/chat";
const CHAT_STREAM_API_URL = "http://127.0.0.1:8000/chat/stream";
const CONVERSATIONS_API_URL = "http://127.0.0.1:8000/conversations";
const DOCUMENTS_API_URL = "http://127.0.0.1:8000/documents";
const AUTH_API_URL = "http://127.0.0.1:8000/auth";

const AUTH_TOKEN_KEY = "agent_project_auth_token";
const AUTH_USER_KEY = "agent_project_auth_user";
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
const STREAM_STATUS_MESSAGES = new Set([
  WEB_SEARCH_STATUS_SEARCHING,
  "正在读取网页内容...",
  WEB_SEARCH_STATUS_ORGANIZING,
  "正在连接 MCP 服务...",
  "正在调用 MCP 工具...",
  "正在计算...",
  "正在总结文本...",
  "正在获取当前时间...",
  "正在生成回答...",
  WEB_SEARCH_STATUS_DONE,
]);
const TRACE_STAGE_DEFINITIONS = [
  { key: "intent", label: "意图识别" },
  { key: "search", label: "搜索阶段" },
  { key: "read", label: "读取阶段" },
  { key: "tool", label: "工具调用" },
  { key: "generate", label: "生成阶段" },
];
const TRACE_MAX_EVENTS = 10;
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
  文档问答: "你是一个严谨的文档问答助手。请优先依据上传文档内容回答，没有依据时明确说明。",
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
  文档问答: "D",
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
const authButton = getRequiredElement("#authButton");
const authOverlay = getRequiredElement("#authOverlay");
const authForm = getRequiredElement("#authForm");
const authTitle = getRequiredElement("#authTitle");
const authUsernameInput = getRequiredElement("#authUsernameInput");
const authPasswordInput = getRequiredElement("#authPasswordInput");
const authSubmitButton = getRequiredElement("#authSubmitButton");
const authToggleButton = getRequiredElement("#authToggleButton");
const authMessageText = getRequiredElement("#authMessageText");
const tracePanelToggleButton = getRequiredElement("#tracePanelToggleButton");
const agentTracePanel = getRequiredElement("#agentTracePanel");
const traceStateText = getRequiredElement("#traceStateText");
const traceIntentText = getRequiredElement("#traceIntentText");
const traceToolNameText = getRequiredElement("#traceToolNameText");
const traceToolStatusText = getRequiredElement("#traceToolStatusText");
const traceToolDurationText = getRequiredElement("#traceToolDurationText");
const traceErrorText = getRequiredElement("#traceErrorText");
const traceStageList = getRequiredElement("#traceStageList");
const traceEventList = getRequiredElement("#traceEventList");
const documentUploadInput = getRequiredElement("#documentUploadInput");
const documentUploadButton = getRequiredElement("#documentUploadButton");
const documentList = getRequiredElement("#documentList");
const documentStatusText = getRequiredElement("#documentStatusText");
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
let authToken = localStorage.getItem(AUTH_TOKEN_KEY) || "";
let currentUser = readJson(AUTH_USER_KEY, null);
let authMode = "login";
let isLoading = false;
let activeAbortController = null;
let shouldStickToBottom = true;
let conversationSearchQuery = "";
let documents = [];
let selectedDocumentId = "";
let activeTrace = createEmptyTrace();
let traceCollapsed = window.matchMedia("(max-width: 1080px)").matches;
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
  activeTrace = buildTraceFromMessages();
  renderAgentTrace();
  applyTraceCollapsed();
  updateAuthUi();
  restoreConversationScrollPosition(conversationId);
  updateHeaderTitle();
  updateInputState();
  autoResizeInput();
  updateScrollToBottomButton();
  messageInput.focus();
  void initializeAuth().then(() => {
    if (isAuthenticated()) {
      void loadDocuments();
    }
  });
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

// Auth

async function initializeAuth() {
  try {
    const response = await fetchWithAuth(`${AUTH_API_URL}/me`, {
      method: "GET",
      headers: { Accept: "application/json" },
      skipAuthRedirect: true,
    });
    const data = await parseJsonResponse(response);
    if (!response.ok || !data.success || !data.user) {
      throw new Error("Authentication required.");
    }
    setAuthenticatedUser(data.user, authToken);
  } catch {
    clearAuthState({ resetConversations: false });
    showAuthOverlay("login", "Please log in to continue.");
  }
}

function setAuthenticatedUser(user, token) {
  const previousUserId = currentUser?.id || "";
  currentUser = user;
  authToken = token || authToken || "";
  localStorage.setItem(AUTH_USER_KEY, JSON.stringify(currentUser));
  if (authToken) {
    localStorage.setItem(AUTH_TOKEN_KEY, authToken);
  }

  if (previousUserId && previousUserId !== currentUser.id) {
    resetLocalConversationState();
    resetDocumentState();
  }

  hideAuthOverlay();
  updateAuthUi();
}

function clearAuthState({ resetConversations = true } = {}) {
  authToken = "";
  currentUser = null;
  localStorage.removeItem(AUTH_TOKEN_KEY);
  localStorage.removeItem(AUTH_USER_KEY);
  if (resetConversations) {
    resetLocalConversationState();
    resetDocumentState();
  }
  updateAuthUi();
}

function isAuthenticated() {
  return Boolean(currentUser);
}

function showAuthOverlay(mode = authMode, message = "") {
  authMode = mode === "register" ? "register" : "login";
  syncAuthPanel(message);
  authOverlay.hidden = false;
  document.body.classList.add("auth-open");
  authUsernameInput.focus();
}

function hideAuthOverlay() {
  authOverlay.hidden = true;
  document.body.classList.remove("auth-open");
  authMessageText.textContent = "";
}

function syncAuthPanel(message = "") {
  const isRegister = authMode === "register";
  authTitle.textContent = isRegister ? "Create account" : "Log in";
  authSubmitButton.textContent = isRegister ? "Create account" : "Log in";
  authToggleButton.textContent = isRegister ? "Use existing account" : "Create account";
  authMessageText.textContent = message;
}

function updateAuthUi() {
  if (currentUser) {
    authButton.textContent = currentUser.auth_enabled === false ? "Dev user" : `Logout ${currentUser.username}`;
    authButton.dataset.state = "authenticated";
  } else {
    authButton.textContent = "Log in";
    authButton.dataset.state = "anonymous";
  }
  updateInputState();
}

async function submitAuthForm() {
  const username = authUsernameInput.value.trim();
  const password = authPasswordInput.value;
  if (!username || !password) {
    syncAuthPanel("Username and password are required.");
    return;
  }

  authSubmitButton.disabled = true;
  authMessageText.textContent = authMode === "register" ? "Creating account..." : "Logging in...";
  try {
    const response = await fetch(`${AUTH_API_URL}/${authMode}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify({ username, password }),
    });
    const data = await parseJsonResponse(response);
    if (!response.ok || !data.success || !data.access_token || !data.user) {
      throw new Error(toFriendlyError(data.error || data.message || response.status));
    }
    authPasswordInput.value = "";
    setAuthenticatedUser(data.user, data.access_token);
    await loadDocuments();
  } catch (error) {
    authMessageText.textContent = error instanceof Error ? error.message : "Authentication failed.";
  } finally {
    authSubmitButton.disabled = false;
  }
}

async function fetchWithAuth(url, options = {}) {
  const { skipAuthRedirect = false, headers: optionHeaders, ...fetchOptions } = options;
  const headers = new Headers(optionHeaders || {});
  if (authToken) {
    headers.set("Authorization", `Bearer ${authToken}`);
  }

  const response = await fetch(url, {
    ...fetchOptions,
    headers,
  });

  if (response.status === 401 && !skipAuthRedirect) {
    clearAuthState();
    showAuthOverlay("login", "Please log in again.");
    throw new Error("Please log in first.");
  }

  return response;
}

async function logoutCurrentUser() {
  try {
    if (authToken) {
      await fetchWithAuth(`${AUTH_API_URL}/logout`, {
        method: "POST",
        headers: { Accept: "application/json" },
        skipAuthRedirect: true,
      });
    }
  } catch (error) {
    console.warn("POST /auth/logout request error", error);
  } finally {
    clearAuthState();
    showAuthOverlay("login", "Logged out.");
  }
}

function resetLocalConversationState() {
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
      title: "New conversation",
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
  conversationIdText.textContent = conversationId;
  renderConversationList();
  renderMessages();
  activeTrace = createEmptyTrace();
  renderAgentTrace();
  updateHeaderTitle();
}

function resetDocumentState() {
  documents = [];
  selectedDocumentId = "";
  renderDocumentList();
  updateInputState();
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
  details.appendChild(createToolDetail("耗时", formatToolDuration(message.toolDurationMs)));
  const routeReason = getToolRouteReason(message);
  if (routeReason) {
    details.appendChild(createToolDetail("调用原因", routeReason));
  }

  if (shouldShowToolErrorDetail(message)) {
    const errorNote = document.createElement("div");
    errorNote.className = "tool-error-note";
    errorNote.textContent = formatToolFailureMessage(message);
    panel.appendChild(errorNote);
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

  if (message.toolName === "document_qa") {
    return "文档检索";
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

function formatToolFailureMessage(message) {
  const detail = getToolErrorDetail(message);
  const errorMessage = detail.message || getToolDisplayError(message) || "工具调用失败";
  const retryMessage = detail.retryable === true ? " 可以稍后重试。" : "";
  return `${errorMessage}${retryMessage}`;
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
    return durationMs === undefined || durationMs === null || durationMs === "" ? "未返回" : String(durationMs);
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

function updateMessageElementOnly(messageId, updates) {
  const shouldKeepAtBottom = shouldStickToBottom || isMessageListNearBottom();
  const previousScrollTop = messageList.scrollTop;
  const messageIndex = messages.findIndex((message) => message.id === messageId);
  const currentMessage = messages[messageIndex];
  if (!currentMessage) {
    return false;
  }

  const updatedMessage = {
    ...currentMessage,
    ...updates,
  };
  const nextRole = updatedMessage.role;
  const nextType = updatedMessage.type;
  const shouldShowNewMessageNotice =
    !shouldKeepAtBottom && (nextRole === "agent" || nextRole === "error") && nextType !== "loading";

  messages = [
    ...messages.slice(0, messageIndex),
    updatedMessage,
    ...messages.slice(messageIndex + 1),
  ];
  saveMessages();

  const messageItem = messageElementMap.get(messageId);
  if (!messageItem || !messageItem.isConnected) {
    return false;
  }

  messageItem.className = `message ${updatedMessage.role}-message`;
  messageItem.dataset.messageId = updatedMessage.id;

  const content = messageItem.querySelector(".message-content");
  const bubble = messageItem.querySelector(".message-bubble");
  if (!content || !bubble) {
    return false;
  }

  updateMessageToolbarElement(content, updatedMessage);
  updateToolPanelElement(content, updatedMessage);
  updateMessageBubbleElement(bubble, updatedMessage);
  updateMessageMetaElement(content, updatedMessage);

  if (messageId !== updatedMessage.id) {
    messageElementMap.delete(messageId);
  }
  messageElementMap.set(updatedMessage.id, messageItem);

  if (shouldKeepAtBottom) {
    scrollToBottom({ behavior: "auto" });
  } else if (shouldShowNewMessageNotice) {
    messageList.scrollTop = previousScrollTop;
    showNewMessageNotice();
  } else {
    messageList.scrollTop = previousScrollTop;
    updateScrollToBottomButton();
  }

  return true;
}

function updateMessageToolbarElement(content, message) {
  const toolbar = content.querySelector(".message-toolbar");
  if (message.role !== "agent" || message.type === "loading") {
    toolbar?.remove();
    return;
  }

  const nextToolbar = createMessageToolbar(message);
  if (toolbar) {
    toolbar.replaceWith(nextToolbar);
    return;
  }

  content.insertBefore(nextToolbar, content.firstChild);
}

function updateToolPanelElement(content, message) {
  const currentPanel = content.querySelector(".tool-panel");
  const nextPanel = createToolPanel(message);
  if (!nextPanel) {
    currentPanel?.remove();
    return;
  }

  if (currentPanel) {
    currentPanel.replaceWith(nextPanel);
    return;
  }

  const bubble = content.querySelector(".message-bubble");
  content.insertBefore(nextPanel, bubble || null);
}

function updateMessageBubbleElement(bubble, message) {
  bubble.replaceChildren();
  if (message.type === "loading") {
    bubble.appendChild(createTypingIndicator(message.content || "Agent is thinking..."));
  } else if (message.role === "agent") {
    bubble.appendChild(renderMarkdown(message.content || ""));
  } else {
    bubble.textContent = message.content || "";
  }
}

function updateMessageMetaElement(content, message) {
  const meta = content.querySelector(".message-meta");
  const nextMeta = createMessageMeta(message);
  if (!nextMeta) {
    meta?.remove();
    return;
  }

  if (meta) {
    meta.replaceWith(nextMeta);
    return;
  }

  content.appendChild(nextMeta);
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

function backendMessagesToFrontendMessages(backendMessages, targetConversationId) {
  return backendMessages
    .map((message, index) => {
      const role = backendRoleToFrontendRole(message?.role);
      if (!role) {
        return null;
      }

      return {
        id: `backend-${targetConversationId}-${index}`,
        role,
        type: "text",
        content: String(message.content || ""),
      };
    })
    .filter(Boolean);
}

function backendRoleToFrontendRole(role) {
  if (role === "user") {
    return "user";
  }
  if (role === "assistant") {
    return "agent";
  }
  return null;
}

async function syncBackendConversationMessages(targetConversationId) {
  const backendMessages = await fetchBackendConversationMessages(targetConversationId);
  if (!Array.isArray(backendMessages) || backendMessages.length === 0) {
    return;
  }

  if (targetConversationId !== conversationId) {
    return;
  }

  const nextMessages = backendMessagesToFrontendMessages(backendMessages, targetConversationId);
  if (nextMessages.length === 0) {
    return;
  }

  messages = nextMessages;
  saveMessages();
  updateConversationMeta({
    updatedAt: getCurrentConversation()?.updatedAt,
  });
  renderMessages({ scrollToEnd: false });
  restoreConversationScrollPosition(targetConversationId);
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
  return STREAM_STATUS_MESSAGES.has(normalized) ? normalized : "";
}

// Agent trace

function createEmptyTrace(overrides = {}) {
  return {
    state: "idle",
    intent: "等待下一次请求",
    toolName: "未使用",
    toolStatus: "未开始",
    toolDuration: "--",
    error: "",
    stages: TRACE_STAGE_DEFINITIONS.map((stage) => ({
      ...stage,
      status: "idle",
      detail: "等待",
    })),
    events: [],
    ...overrides,
  };
}

function buildTraceFromMessages() {
  const latestAgentIndex = findLatestAgentMessageIndex();
  if (latestAgentIndex < 0) {
    return createEmptyTrace();
  }

  const agentMessage = messages[latestAgentIndex];
  const previousUserMessage = findPreviousUserMessage(latestAgentIndex);
  const trace = createEmptyTrace({
    state: agentMessage.role === "error" ? "failed" : "success",
    intent: inferTraceIntent(previousUserMessage?.content || agentMessage.content || ""),
  });

  markTraceStage(trace, "intent", "success", "已识别");
  markTraceStage(trace, "generate", agentMessage.role === "error" ? "failed" : "success", "已返回回复");

  if (agentMessage.usedTool === true) {
    applyToolMetadataToTrace(trace, agentMessage);
  } else {
    markTraceStage(trace, "tool", "idle", "未调用工具");
  }

  if (agentMessage.role === "error") {
    trace.error = agentMessage.content || CHAT_FAILURE_MESSAGE;
  }

  trace.events = [
    {
      title: "载入最近一次请求",
      detail: agentMessage.usedTool === true ? "已恢复工具执行摘要" : "最近回复未调用工具",
      status: trace.state,
      time: agentMessage.createdAt || getCurrentTime(),
    },
  ];
  return trace;
}

function findLatestAgentMessageIndex() {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    if (messages[index]?.role === "agent" || messages[index]?.role === "error") {
      return index;
    }
  }

  return -1;
}

function startAgentTrace(userText, { regenerate = false } = {}) {
  const likelyWebSearch = looksLikeWebSearchRequest(userText);
  activeTrace = createEmptyTrace({
    state: "running",
    intent: inferTraceIntent(userText),
  });
  markTraceStage(activeTrace, "intent", "success", "已识别请求意图");
  markTraceStage(
    activeTrace,
    likelyWebSearch ? "search" : "generate",
    "running",
    likelyWebSearch ? "等待搜索结果" : "等待模型输出",
  );
  addTraceEvent(
    regenerate ? "重新生成请求" : "接收用户请求",
    activeTrace.intent,
    "running",
  );
  renderAgentTrace();
}

function inferTraceIntent(text) {
  const normalized = String(text || "").trim();
  if (!normalized) {
    return "等待下一次请求";
  }

  if (looksLikeWebSearchRequest(normalized)) {
    return `联网检索 · ${currentMode}`;
  }

  if (/\b(code|function|bug|error|api|class|react|vue|python|javascript|typescript)\b/i.test(normalized)) {
    return `代码分析 · ${currentMode}`;
  }

  return `对话生成 · ${currentMode}`;
}

function updateAgentTraceFromStatus(statusMessage) {
  const normalizedStatus = normalizeStreamStatusMessage(statusMessage);
  if (!normalizedStatus) {
    return;
  }

  if (normalizedStatus === WEB_SEARCH_STATUS_SEARCHING) {
    updateTraceStage("search", "running", "正在检索外部资料");
  } else if (normalizedStatus === WEB_SEARCH_STATUS_ORGANIZING) {
    updateTraceStage("search", "running", "正在整理搜索资料");
  } else if (normalizedStatus === WEB_SEARCH_STATUS_DONE) {
    updateTraceStage("search", "success", "搜索完成");
  } else if (normalizedStatus.includes("读取网页")) {
    updateTraceStage("read", "running", "正在读取网页内容");
  } else if (normalizedStatus.includes("生成回答")) {
    updateTraceStage("generate", "running", "正在生成回复");
  } else if (normalizedStatus.includes("调用 MCP") || normalizedStatus.includes("连接 MCP")) {
    updateTraceStage("tool", "running", normalizedStatus);
  } else if (normalizedStatus.includes("计算") || normalizedStatus.includes("总结") || normalizedStatus.includes("时间")) {
    updateTraceStage("tool", "running", normalizedStatus);
  }

  addTraceEvent(normalizedStatus, "流式阶段状态更新", "running");
  renderAgentTrace();
}

function updateAgentTraceFromTool(metadata) {
  if (!metadata || metadata.usedTool !== true) {
    return;
  }

  applyToolMetadataToTrace(activeTrace, metadata);
  addTraceEvent(
    `工具 ${activeTrace.toolName}`,
    `${activeTrace.toolStatus}${activeTrace.toolDuration !== "--" ? ` · ${activeTrace.toolDuration}` : ""}`,
    activeTrace.error ? "failed" : normalizeTraceStatus(metadata.toolStatus, metadata),
  );
  renderAgentTrace();
}

function applyToolMetadataToTrace(trace, metadata) {
  const status = normalizeTraceStatus(metadata.toolStatus, metadata);
  const toolError = getToolDisplayError(metadata);

  trace.toolName = metadata.toolName || trace.toolName || "未命名工具";
  trace.toolStatus = metadata.usedTool === true
    ? formatToolStatus(metadata.toolStatus, toolError)
    : "未调用";
  trace.toolDuration = formatToolDuration(metadata.toolDurationMs);
  trace.error = toolError || trace.error || "";
  markTraceStage(trace, "tool", status, status === "running" ? "正在调用工具" : trace.toolStatus);

  if (metadata.toolName === "web_search") {
    markTraceStage(trace, "search", status === "failed" ? "failed" : "success", status === "failed" ? "搜索失败" : "搜索完成");
    const root = normalizeToolResultRoot(metadata.toolResult);
    if (Array.isArray(root.read_pages) && root.read_pages.length > 0) {
      markTraceStage(trace, "read", "success", `已读取 ${root.read_pages.length} 个页面`);
    }
  }

  if (status === "failed") {
    trace.state = "failed";
  }
}

function finalizeAgentTrace(result = {}, { error = "", aborted = false } = {}) {
  if (result.usedTool === true) {
    applyToolMetadataToTrace(activeTrace, result);
  } else if (!activeTrace.error) {
    activeTrace.toolName = "未使用";
    activeTrace.toolStatus = "未调用";
    activeTrace.toolDuration = "--";
    markTraceStage(activeTrace, "tool", "idle", "未调用工具");
  }

  if (aborted) {
    activeTrace.state = "failed";
    activeTrace.error = "已停止生成";
    markTraceStage(activeTrace, "generate", "failed", "用户停止生成");
    addTraceEvent("停止生成", "请求已中止", "failed");
  } else if (error) {
    activeTrace.state = "failed";
    activeTrace.error = error;
    markTraceStage(activeTrace, "generate", "failed", "生成失败");
    addTraceEvent("请求失败", error, "failed");
  } else if (activeTrace.state !== "failed") {
    activeTrace.state = "success";
    markRunningTraceStages("success");
    markTraceStage(activeTrace, "generate", "success", "回复生成完成");
    addTraceEvent("请求完成", "Agent 已返回最终回复", "success");
  }

  renderAgentTrace();
}

function markRunningTraceStages(nextStatus) {
  activeTrace.stages = activeTrace.stages.map((stage) =>
    stage.status === "running" ? { ...stage, status: nextStatus, detail: nextStatus === "success" ? "已完成" : stage.detail } : stage,
  );
}

function updateTraceStage(key, status, detail) {
  markTraceStage(activeTrace, key, status, detail);
}

function markTraceStage(trace, key, status, detail) {
  trace.stages = trace.stages.map((stage) =>
    stage.key === key ? { ...stage, status, detail: detail || stage.detail } : stage,
  );
}

function addTraceEvent(title, detail = "", status = "running") {
  activeTrace.events = [
    {
      title,
      detail,
      status,
      time: getCurrentTime(),
    },
    ...activeTrace.events,
  ].slice(0, TRACE_MAX_EVENTS);
}

function normalizeTraceStatus(status, metadata = {}) {
  if (
    status === "failed" ||
    status === false ||
    metadata.toolError ||
    metadata.toolErrorCode ||
    metadata.toolErrorMessage ||
    metadata.toolErrorDetail
  ) {
    return "failed";
  }

  if (status === "running") {
    return "running";
  }

  if (status === "success" || status === true) {
    return "success";
  }

  return metadata.usedTool === true ? "running" : "idle";
}

function renderAgentTrace() {
  traceStateText.textContent = formatTraceState(activeTrace.state);
  traceStateText.className = `trace-state ${activeTrace.state}`;
  traceIntentText.textContent = activeTrace.intent;
  traceToolNameText.textContent = activeTrace.toolName;
  traceToolStatusText.textContent = activeTrace.toolStatus;
  traceToolDurationText.textContent = activeTrace.toolDuration;

  if (activeTrace.error) {
    traceErrorText.textContent = activeTrace.error;
    traceErrorText.classList.remove("is-hidden");
  } else {
    traceErrorText.textContent = "";
    traceErrorText.classList.add("is-hidden");
  }

  traceStageList.replaceChildren(...activeTrace.stages.map(createTraceStageElement));
  if (activeTrace.events.length === 0) {
    const empty = document.createElement("div");
    empty.className = "trace-empty";
    empty.textContent = "尚未开始请求，发送消息后这里会显示执行过程。";
    traceEventList.replaceChildren(empty);
  } else {
    traceEventList.replaceChildren(...activeTrace.events.map(createTraceEventElement));
  }
}

function createTraceStageElement(stage) {
  const item = document.createElement("div");
  item.className = `trace-stage-item ${stage.status}`;

  const marker = document.createElement("span");
  marker.className = "trace-stage-marker";
  marker.setAttribute("aria-hidden", "true");

  const copy = document.createElement("div");
  copy.className = "trace-stage-copy";

  const title = document.createElement("strong");
  title.textContent = stage.label;

  const detail = document.createElement("span");
  detail.textContent = `${formatTraceStageStatus(stage.status)} · ${stage.detail}`;

  copy.append(title, detail);
  item.append(marker, copy);
  return item;
}

function createTraceEventElement(event) {
  const item = document.createElement("div");
  item.className = `trace-event-item ${event.status}`;

  const marker = document.createElement("span");
  marker.className = "trace-event-marker";
  marker.setAttribute("aria-hidden", "true");

  const copy = document.createElement("div");
  copy.className = "trace-event-copy";

  const time = document.createElement("div");
  time.className = "trace-event-time";
  time.textContent = event.time;

  const title = document.createElement("strong");
  title.textContent = event.title;

  const detail = document.createElement("span");
  detail.textContent = event.detail || formatTraceStageStatus(event.status);

  copy.append(time, title, detail);
  item.append(marker, copy);
  return item;
}

function formatTraceState(state) {
  if (state === "running") {
    return "Running";
  }
  if (state === "success") {
    return "Success";
  }
  if (state === "failed") {
    return "Failed";
  }
  return "Idle";
}

function formatTraceStageStatus(status) {
  if (status === "running") {
    return "执行中";
  }
  if (status === "success") {
    return "已完成";
  }
  if (status === "failed") {
    return "失败";
  }
  return "等待";
}

function applyTraceCollapsed() {
  document.body.classList.toggle("trace-collapsed", traceCollapsed);
  tracePanelToggleButton.setAttribute("aria-expanded", String(!traceCollapsed));
  tracePanelToggleButton.textContent = traceCollapsed ? "Trace" : "隐藏 Trace";
  agentTracePanel.setAttribute("aria-hidden", String(traceCollapsed));
}

function toggleTracePanel() {
  traceCollapsed = !traceCollapsed;
  applyTraceCollapsed();
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
  documentUploadButton.disabled = nextLoading;
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
  const needsDocument = currentMode === "文档问答";
  const hasDocument = Boolean(selectedDocumentId);
  const authReady = isAuthenticated();

  charCounter.textContent = `${length} / ${MAX_MESSAGE_LENGTH}`;
  sendButton.disabled = !isLoading && (!authReady || !hasText || (needsDocument && !hasDocument));
}

function setMode(mode) {
  debugLog("setMode start", mode);
  currentMode = normalizeMode(mode);
  localStorage.setItem(MODE_KEY, currentMode);
  currentModeText.textContent = currentMode;
  settingsModeSelect.value = currentMode;
  messageInput.placeholder = currentMode === "文档问答"
    ? "基于已选择文档提问，Enter 发送，Shift + Enter 换行"
    : "输入问题，Enter 发送，Shift + Enter 换行";

  modeButtons.forEach((button) => {
    button.classList.toggle("active", button.dataset.mode === currentMode);
  });
  updateInputState();
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

// Document question answering

async function loadDocuments() {
  try {
    const response = await fetchWithAuth(DOCUMENTS_API_URL, {
      method: "GET",
      headers: { Accept: "application/json" },
    });
    const data = await parseJsonResponse(response);
    if (!response.ok || !data.success || !Array.isArray(data.documents)) {
      throw new Error(toFriendlyError(data.error || response.status));
    }

    documents = data.documents;
    if (!documents.some((document) => document.id === selectedDocumentId)) {
      selectedDocumentId = documents[0]?.id || "";
    }
    renderDocumentList();
    updateInputState();
  } catch (error) {
    console.warn("GET /documents request error", error);
    documentStatusText.textContent = "!";
    renderDocumentList("文档列表加载失败");
  }
}

async function uploadSelectedDocument() {
  if (guardActionDuringLoading()) {
    return;
  }

  const file = documentUploadInput.files?.[0];
  if (!file) {
    documentUploadInput.click();
    return;
  }

  if (file.size > 5 * 1024 * 1024) {
    window.alert("文件过大，请上传不超过 5MB 的文档。");
    documentUploadInput.value = "";
    return;
  }

  documentUploadButton.disabled = true;
  documentUploadButton.textContent = "上传中...";
  try {
    const formData = new FormData();
    formData.append("file", file);
    const response = await fetchWithAuth(`${DOCUMENTS_API_URL}/upload`, {
      method: "POST",
      body: formData,
    });
    const data = await parseJsonResponse(response);
    if (!response.ok || !data.success || !data.document) {
      throw new Error(toFriendlyError(data.error || response.status));
    }

    selectedDocumentId = data.document.id;
    await loadDocuments();
    setMode("文档问答");
  } catch (error) {
    console.warn("POST /documents/upload request error", error);
    window.alert(error instanceof Error ? error.message : "文档上传失败，请稍后重试。");
  } finally {
    documentUploadInput.value = "";
    documentUploadButton.disabled = false;
    documentUploadButton.textContent = "上传 txt/md/pdf";
  }
}

async function deleteDocument(documentId) {
  if (guardActionDuringLoading()) {
    return;
  }

  const document = documents.find((item) => item.id === documentId);
  if (!window.confirm(`确定删除“${document?.filename || "该文档"}”吗？`)) {
    return;
  }

  try {
    const response = await fetchWithAuth(`${DOCUMENTS_API_URL}/${encodeURIComponent(documentId)}`, {
      method: "DELETE",
    });
    const data = await parseJsonResponse(response);
    if (!response.ok || !data.success) {
      throw new Error(toFriendlyError(data.error || response.status));
    }
    if (selectedDocumentId === documentId) {
      selectedDocumentId = "";
    }
    await loadDocuments();
  } catch (error) {
    console.warn("DELETE /documents request error", error);
    window.alert(error instanceof Error ? error.message : "文档删除失败，请稍后重试。");
  }
}

function renderDocumentList(errorMessage = "") {
  documentList.innerHTML = "";
  documentStatusText.textContent = errorMessage ? "!" : String(documents.length);

  if (errorMessage || documents.length === 0) {
    const empty = document.createElement("div");
    empty.className = "document-empty";
    empty.textContent = errorMessage || "上传 txt / md / pdf 后，可切换到文档问答模式提问。";
    documentList.appendChild(empty);
    return;
  }

  documents.forEach((documentItem) => {
    const item = document.createElement("div");
    item.className = "document-item";
    item.classList.toggle("active", documentItem.id === selectedDocumentId);

    const main = document.createElement("button");
    main.className = "document-main";
    main.type = "button";
    main.addEventListener("click", () => {
      selectedDocumentId = documentItem.id;
      renderDocumentList();
      setMode("文档问答");
      messageInput.focus();
    });

    const title = document.createElement("span");
    title.className = "document-title";
    title.textContent = documentItem.filename || "未命名文档";

    const meta = document.createElement("span");
    meta.className = "document-meta";
    meta.textContent = `${formatFileSize(documentItem.size_bytes)} · ${documentItem.chunk_count || 0} chunks`;
    main.append(title, meta);

    const deleteButton = document.createElement("button");
    deleteButton.className = "document-delete-button";
    deleteButton.type = "button";
    deleteButton.setAttribute("aria-label", `删除 ${documentItem.filename}`);
    deleteButton.textContent = "×";
    deleteButton.addEventListener("click", (event) => {
      event.stopPropagation();
      void deleteDocument(documentItem.id);
    });

    item.append(main, deleteButton);
    documentList.appendChild(item);
  });
}

function formatFileSize(sizeBytes) {
  const size = Number(sizeBytes || 0);
  if (size < 1024) {
    return `${size} B`;
  }
  if (size < 1024 * 1024) {
    return `${(size / 1024).toFixed(1)} KB`;
  }
  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}

// Agent request flow

async function clearBackendConversation(conversationId) {
  const targetConversationId = String(conversationId || "").trim();
  if (!targetConversationId) {
    return false;
  }

  try {
    const response = await fetchWithAuth(
      `${CONVERSATIONS_API_URL}/${encodeURIComponent(targetConversationId)}`,
      { method: "DELETE" },
    );
    if (response.ok) {
      return true;
    }

    console.warn("DELETE /conversations request failed", {
      conversationId: targetConversationId,
      status: response.status,
      statusText: response.statusText,
    });
  } catch (error) {
    console.warn("DELETE /conversations request error", {
      conversationId: targetConversationId,
      error,
    });
  }

  return false;
}

async function fetchBackendConversationMessages(conversationId) {
  const targetConversationId = String(conversationId || "").trim();
  if (!targetConversationId) {
    return null;
  }

  try {
    const response = await fetchWithAuth(
      `${CONVERSATIONS_API_URL}/${encodeURIComponent(targetConversationId)}/messages`,
      {
        method: "GET",
        headers: {
          Accept: "application/json",
        },
      },
    );
    if (!response.ok) {
      console.warn("GET /conversations/messages request failed", {
        conversationId: targetConversationId,
        status: response.status,
        statusText: response.statusText,
      });
      return null;
    }

    const data = await parseJsonResponse(response);
    if (!data.success || !Array.isArray(data.messages)) {
      console.warn("GET /conversations/messages returned invalid data", {
        conversationId: targetConversationId,
        data,
      });
      return null;
    }

    return data.messages;
  } catch (error) {
    console.warn("GET /conversations/messages request error", {
      conversationId: targetConversationId,
      error,
    });
  }

  return null;
}

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
    const result = targetMode === "文档问答"
      ? await requestDocumentAnswer(
          message,
          {
            model: targetModel,
            signal: activeAbortController.signal,
          },
        )
      : targetStreamingEnabled
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

async function requestDocumentAnswer(message, { model, signal }) {
  if (!selectedDocumentId) {
    throw new Error("请先上传并选择一个文档。");
  }

  debugLog("POST /documents/{id}/ask request start", {
    documentId: selectedDocumentId,
    messageLength: message.length,
    model,
  });
  const response = await fetchWithAuth(`${DOCUMENTS_API_URL}/${encodeURIComponent(selectedDocumentId)}/ask`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    body: JSON.stringify({
      question: message,
      model,
    }),
    signal,
  });
  const data = await parseJsonResponse(response);
  if (!response.ok || !data.success) {
    const message = toFriendlyError(data.error || response.status);
    throw new Error(message || "文档问答请求失败，请稍后重试。");
  }

  return {
    aborted: false,
    reply: data.answer || "",
    model: data.model || model || "",
    conversationId,
    usedTool: true,
    toolName: "document_qa",
    toolStatus: "success",
    toolResult: data.chunks || [],
    toolError: null,
    toolErrorCode: null,
    toolErrorMessage: null,
    toolRetryable: false,
    toolErrorDetail: null,
    toolDurationMs: null,
  };
}

async function requestJsonAgentReply(requestBody, signal, fallbackConversationId) {
  debugLog("POST /chat request start", requestBody);
  const response = await fetchWithAuth(CHAT_API_URL, {
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
  const response = await fetchWithAuth(CHAT_STREAM_API_URL, {
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
  startAgentTrace(previousUserMessage.content || "", { regenerate: true });
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
    updateAgentTraceFromStatus(normalizedStatus);
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
      updateAgentTraceFromTool(metadata);
      const statusContent = getToolStatusContent(metadata);
      const metadataUpdates = {
        role: "agent",
        ...metadata,
        createdAt: getCurrentTime(),
      };
      if (!hasReceivedFirstChunk) {
        metadataUpdates.type = "loading";
        const nextStatusContent =
          statusContent || (likelyWebSearch && streamingEnabled ? WEB_SEARCH_STATUS_ORGANIZING : null);
        if (nextStatusContent) {
          metadataUpdates.content = nextStatusContent;
        }
        updateMessage(loadingMessage.id, metadataUpdates);
        return;
      }

      if (!updateMessageElementOnly(loadingMessage.id, metadataUpdates)) {
        updateMessage(loadingMessage.id, metadataUpdates);
      }
    },
    onStatus: (statusMessage) => {
      updateLoadingStatus(statusMessage);
    },
    onChunk: (chunk, partialReply) => {
      if (!hasReceivedFirstChunk) {
        updateTraceStage("generate", "running", "正在接收流式输出");
        addTraceEvent("开始流式输出", "已收到首个内容片段", "running");
        renderAgentTrace();
      }
      hasReceivedFirstChunk = true;
      if (searchStatusTimer) {
        window.clearTimeout(searchStatusTimer);
      }
      const chunkUpdates = {
        type: "text",
        role: "agent",
        content: partialReply || "Agent 正在重新生成...",
        createdAt: getCurrentTime(),
      };
      if (!updateMessageElementOnly(loadingMessage.id, chunkUpdates)) {
        updateMessage(loadingMessage.id, chunkUpdates);
      }
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
        updateAgentTraceFromStatus(WEB_SEARCH_STATUS_ORGANIZING);
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
      finalizeAgentTrace(result, { aborted: true });
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
    finalizeAgentTrace(result);
  } catch (error) {
    console.warn("regenerateAgentReply error", error);
    finalizeAgentTrace({}, { error: error instanceof Error ? error.message : CHAT_FAILURE_MESSAGE });
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

  const backendConversationIds = conversations.map((item) => item.id).filter(Boolean);
  backendConversationIds.forEach((id) => {
    void clearBackendConversation(id);
  });

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
  activeTrace = createEmptyTrace();
  renderAgentTrace();
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

  if (!isAuthenticated()) {
    showAuthOverlay("login", "Please log in to continue.");
    return;
  }

  startAgentTrace(userText);
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
    updateAgentTraceFromStatus(normalizedStatus);
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
        updateAgentTraceFromStatus(WEB_SEARCH_STATUS_ORGANIZING);
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
      updateAgentTraceFromStatus(likelyWebSearch ? WEB_SEARCH_STATUS_ORGANIZING : "正在生成回答...");
    }
  }, THINKING_NOTICE_DELAY_MS);

  try {
    const result = await requestAgentReply(userText, {
      onToolMetadata: (metadata) => {
        updateAgentTraceFromTool(metadata);
        const statusContent = getToolStatusContent(metadata);
        const metadataUpdates = {
          role: "agent",
          ...metadata,
          createdAt: getCurrentTime(),
        };
        if (!hasReceivedFirstChunk) {
          metadataUpdates.type = "loading";
          const nextStatusContent =
            statusContent || (likelyWebSearch && streamingEnabled ? WEB_SEARCH_STATUS_ORGANIZING : null);
          if (nextStatusContent) {
            metadataUpdates.content = nextStatusContent;
          }
          updateMessage(loadingMessage.id, metadataUpdates);
          return;
        }

        if (!updateMessageElementOnly(loadingMessage.id, metadataUpdates)) {
          updateMessage(loadingMessage.id, metadataUpdates);
        }
      },
      onStatus: (statusMessage) => {
        updateLoadingStatus(statusMessage);
      },
      onChunk: (chunk, partialReply) => {
        if (!hasReceivedFirstChunk) {
          updateTraceStage("generate", "running", "正在接收流式输出");
          addTraceEvent("开始流式输出", "已收到首个内容片段", "running");
          renderAgentTrace();
        }
        hasReceivedFirstChunk = true;
        if (searchStatusTimer) {
          window.clearTimeout(searchStatusTimer);
        }
        window.clearTimeout(thinkingTimer);
        const chunkUpdates = {
          type: "text",
          role: "agent",
          content: partialReply || "Agent 正在生成...",
          createdAt: getCurrentTime(),
        };
        if (!updateMessageElementOnly(loadingMessage.id, chunkUpdates)) {
          updateMessage(loadingMessage.id, chunkUpdates);
        }
      },
    });
    debugLog("sendCurrentMessage received result", result);
    if (result.aborted) {
      finalizeAgentTrace(result, { aborted: true });
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
    finalizeAgentTrace(result);
    debugLog("sendCurrentMessage agent reply rendered", loadingMessage.id);
  } catch (error) {
    console.warn("sendCurrentMessage error", error);
    finalizeAgentTrace({}, { error: error instanceof Error ? error.message : CHAT_FAILURE_MESSAGE });
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
  activeTrace = createEmptyTrace();
  renderAgentTrace();
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
  activeTrace = buildTraceFromMessages();
  renderAgentTrace();
  restoreConversationScrollPosition(conversationId);
  updateHeaderTitle();
  messageInput.value = "";
  autoResizeInput();
  updateInputState();
  messageInput.focus();
  void syncBackendConversationMessages(nextId);
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

  void clearBackendConversation(targetId);
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
    activeTrace = buildTraceFromMessages();
    renderAgentTrace();
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

  void clearBackendConversation(conversationId);
  messages = [];
  saveMessages();
  removeConversationScrollPosition(conversationId);
  updateConversationMeta({
    messageCount: 0,
  });
  renderMessages();
  activeTrace = createEmptyTrace();
  renderAgentTrace();
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

tracePanelToggleButton.addEventListener("click", () => {
  toggleTracePanel();
  messageInput.focus();
});

settingsButton.addEventListener("click", () => {
  openSettingsPanel();
});

authButton.addEventListener("click", () => {
  if (currentUser) {
    void logoutCurrentUser();
    return;
  }
  showAuthOverlay("login");
});

authForm.addEventListener("submit", (event) => {
  event.preventDefault();
  void submitAuthForm();
});

authToggleButton.addEventListener("click", () => {
  authMode = authMode === "login" ? "register" : "login";
  syncAuthPanel();
  authPasswordInput.value = "";
  authUsernameInput.focus();
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

documentUploadButton.addEventListener("click", () => {
  documentUploadInput.click();
});

documentUploadInput.addEventListener("change", () => {
  void uploadSelectedDocument();
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
    return;
  }

  if (event.key === "Escape" && !traceCollapsed && window.matchMedia("(max-width: 1080px)").matches) {
    traceCollapsed = true;
    applyTraceCollapsed();
    tracePanelToggleButton.focus();
  }
});
