/**
 * Helix documentation chat widget — docs-only assistant via same-origin proxy.
 */

const CHAT_DISMISSED_KEY = "helix-chat-user-closed";
const CHAT_CLIENT_ID_KEY = "helix-chat-client-id";
const CHAT_SESSION_CACHE_KEY = "helix-chat-session-cache";
const CHAT_SIZE_KEY = "helix-chat-size";
const CHAT_SIZE_DEFAULT = { width: 420, height: 580 };
const CHAT_SIZE_MIN = { width: 320, height: 400 };
const CHAT_SIZE_MAX = { width: 560, height: 780 };
const CHAT_I18N = {
  en: {
    title: "Helix Docs Assistant",
    subtitle: "Docs, navigation, and friendly chat",
    placeholder: "Ask about Helix, say hi, or ask what I can do…",
    send: "Send",
    welcome:
      "Hi! I'm the Helix docs assistant. I can explain documentation, open relevant pages, and chat about what I can help with. I don't run commands or access files — ask me anything about Helix or just say hello.",
    thinking: "Thinking…",
    error: "Could not get a reply. Try again later.",
    offline: "Chat is not available on this server.",
    foundDocs: "Related pages",
    newChat: "New chat",
    newChatConfirm: "Start a new conversation? Current history will be cleared.",
    resize: "Resize chat",
  },
  ru: {
    title: "Ассистент документации",
    subtitle: "Документация, навигация и диалог",
    placeholder: "Спросите про Helix, поздоровайтесь или узнайте, чем могу помочь…",
    send: "Отправить",
    welcome:
      "Привет! Я ассистент документации Helix. Могу объяснить разделы, открыть нужные страницы и рассказать, чем помогаю. Команды не выполняю и к файлам не обращаюсь — спрашивайте про Helix или просто поздоровайтесь.",
    thinking: "Думаю…",
    error: "Не удалось получить ответ. Попробуйте позже.",
    offline: "Чат недоступен на этом сервере.",
    foundDocs: "Найденные разделы",
    newChat: "Новый чат",
    newChatConfirm: "Начать новый диалог? Текущая история будет удалена.",
    resize: "Изменить размер чата",
  },
};

function clampChatSize(width, height) {
  const maxWidth = Math.min(CHAT_SIZE_MAX.width, window.innerWidth - 32);
  const maxHeight = Math.min(CHAT_SIZE_MAX.height, window.innerHeight - 96);
  return {
    width: Math.round(Math.min(maxWidth, Math.max(CHAT_SIZE_MIN.width, width))),
    height: Math.round(Math.min(maxHeight, Math.max(CHAT_SIZE_MIN.height, height))),
  };
}

function loadChatSize() {
  try {
    const raw = localStorage.getItem(CHAT_SIZE_KEY);
    if (!raw) return { ...CHAT_SIZE_DEFAULT };
    const data = JSON.parse(raw);
    return clampChatSize(Number(data.width) || CHAT_SIZE_DEFAULT.width, Number(data.height) || CHAT_SIZE_DEFAULT.height);
  } catch {
    return { ...CHAT_SIZE_DEFAULT };
  }
}

function saveChatSize(size) {
  localStorage.setItem(CHAT_SIZE_KEY, JSON.stringify(size));
}

function applyChatSize(panel, size) {
  const next = clampChatSize(size.width, size.height);
  if (window.innerWidth <= 480) {
    panel.style.removeProperty("--helix-chat-width");
    panel.style.removeProperty("--helix-chat-height");
    return next;
  }
  panel.style.setProperty("--helix-chat-width", `${next.width}px`);
  panel.style.setProperty("--helix-chat-height", `${next.height}px`);
  return next;
}

function bindChatResize(panel, handle, getLang) {
  let startX = 0;
  let startY = 0;
  let startWidth = 0;
  let startHeight = 0;

  const onPointerMove = (ev) => {
    const width = startWidth + (startX - ev.clientX);
    const height = startHeight + (startY - ev.clientY);
    saveChatSize(applyChatSize(panel, { width, height }));
  };

  const stopResize = () => {
    panel.classList.remove("is-resizing");
    window.removeEventListener("pointermove", onPointerMove);
    window.removeEventListener("pointerup", stopResize);
    window.removeEventListener("pointercancel", stopResize);
  };

  handle.addEventListener("pointerdown", (ev) => {
    ev.preventDefault();
    const rect = panel.getBoundingClientRect();
    startX = ev.clientX;
    startY = ev.clientY;
    startWidth = rect.width;
    startHeight = rect.height;
    panel.classList.add("is-resizing");
    handle.setPointerCapture?.(ev.pointerId);
    window.addEventListener("pointermove", onPointerMove);
    window.addEventListener("pointerup", stopResize);
    window.addEventListener("pointercancel", stopResize);
  });

  const refreshLabel = () => {
    const l = getLang?.() === "en" ? "en" : "ru";
    handle.setAttribute("aria-label", chatT(l, "resize"));
    handle.title = chatT(l, "resize");
  };

  refreshLabel();
  document.addEventListener("helix-lang-change", refreshLabel);
  window.addEventListener("resize", () => {
    const width = parseFloat(panel.style.getPropertyValue("--helix-chat-width")) || CHAT_SIZE_DEFAULT.width;
    const height = parseFloat(panel.style.getPropertyValue("--helix-chat-height")) || CHAT_SIZE_DEFAULT.height;
    saveChatSize(applyChatSize(panel, { width, height }));
  });
}

function chatT(lang, key) {
  return CHAT_I18N[lang]?.[key] ?? CHAT_I18N.en[key] ?? key;
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

const markdownDebounceTimers = new WeakMap();

function preprocessDocLinks(text) {
  return String(text || "").replace(/(?:#\/docs\/|\/docs\/)([a-z0-9-]+)/g, (match, slug) => {
    return `[${match}](/docs/${slug})`;
  });
}

function sanitizeMarkdownHtml(html) {
  const doc = new DOMParser().parseFromString(html, "text/html");
  doc.querySelectorAll("script, style, iframe, object, embed, form").forEach((el) => el.remove());
  doc.querySelectorAll("*").forEach((el) => {
    for (const attr of [...el.attributes]) {
      if (attr.name.startsWith("on") || attr.name === "srcdoc") {
        el.removeAttribute(attr.name);
      }
    }
  });
  return doc.body.innerHTML;
}

function renderMarkdownInner(text) {
  const prepared = preprocessDocLinks(text);
  if (typeof marked !== "undefined" && marked?.parse) {
    return sanitizeMarkdownHtml(marked.parse(prepared, { breaks: true, gfm: true }));
  }
  return escapeHtml(prepared).replace(/\n/g, "<br>");
}

function ensureMarkdownRoot(bubble) {
  let mdRoot = bubble.querySelector(":scope > .helix-chat-md");
  if (mdRoot) return mdRoot;

  const chips = bubble.querySelector(":scope > .helix-chat-doc-chips");
  bubble.textContent = "";
  mdRoot = document.createElement("div");
  mdRoot.className = "helix-chat-md";
  bubble.appendChild(mdRoot);
  if (chips) bubble.appendChild(chips);
  return mdRoot;
}

function wrapMarkdownTables(root) {
  root.querySelectorAll(".helix-chat-md table").forEach((table) => {
    if (table.parentElement?.classList.contains("helix-chat-table-scroll")) return;
    const wrap = document.createElement("div");
    wrap.className = "helix-chat-table-scroll";
    table.replaceWith(wrap);
    wrap.appendChild(table);
  });
}

function enhanceMarkdownLinks(root) {
  root.querySelectorAll(".helix-chat-md a[href]").forEach((link) => {
    const href = link.getAttribute("href") || "";
    if (href.startsWith("http://") || href.startsWith("https://")) {
      link.target = "_blank";
      link.rel = "noopener noreferrer";
    }
  });
}

function getPageSlug() {
  const path = location.pathname.replace(/\/+$/, "") || "/";
  if (!path.startsWith("/docs/")) return null;
  const slug = path.slice(6);
  return /^[a-z0-9-]+$/.test(slug) ? slug : null;
}

function navigateToDoc(slug) {
  if (!slug) return;
  document.dispatchEvent(new CustomEvent("helix-open-doc", { detail: { slug } }));
}

function extractDocSlugsFromText(text) {
  const slugs = [];
  const re = /(?:#\/docs\/|\/docs\/)([a-z0-9-]+)/g;
  let match;
  while ((match = re.exec(text || "")) !== null) {
    slugs.push(match[1]);
  }
  return slugs;
}

function firstDocSlugInText(text) {
  const slugs = extractDocSlugsFromText(text);
  return slugs.length ? slugs[0] : null;
}

function resolveNavigateSlug({ text, openSlug, currentSlug = getPageSlug() }) {
  const candidates = [openSlug, firstDocSlugInText(text)].filter(Boolean);
  for (const slug of candidates) {
    if (slug !== currentSlug) return slug;
  }
  return null;
}

function navigateFromLatestReply({ text, openSlug } = {}) {
  const slug = resolveNavigateSlug({ text, openSlug });
  if (slug) navigateToDoc(slug);
}

function applyMarkdownContent(bubble, text, { streaming = false } = {}) {
  const mdRoot = ensureMarkdownRoot(bubble);
  const render = () => {
    mdRoot.innerHTML = renderMarkdownInner(text);
    bindDocLinks(bubble);
    enhanceMarkdownLinks(bubble);
    wrapMarkdownTables(bubble);
  };

  if (streaming) {
    clearTimeout(markdownDebounceTimers.get(bubble));
    markdownDebounceTimers.set(
      bubble,
      window.setTimeout(() => {
        render();
        markdownDebounceTimers.delete(bubble);
      }, 80),
    );
    return;
  }

  clearTimeout(markdownDebounceTimers.get(bubble));
  markdownDebounceTimers.delete(bubble);
  render();
}

function parseSseBlock(block) {
  const line = block.split("\n").find((l) => l.startsWith("data: "));
  if (!line) return null;
  try {
    return JSON.parse(line.slice(6));
  } catch {
    return null;
  }
}

function getOrCreateClientId() {
  let id = localStorage.getItem(CHAT_CLIENT_ID_KEY);
  if (!id) {
    id = crypto.randomUUID();
    localStorage.setItem(CHAT_CLIENT_ID_KEY, id);
  }
  return id;
}

function loadLocalSession(clientId) {
  try {
    const raw = localStorage.getItem(CHAT_SESSION_CACHE_KEY);
    if (!raw) return [];
    const data = JSON.parse(raw);
    if (data.client_id !== clientId) return [];
    return Array.isArray(data.messages) ? data.messages : [];
  } catch {
    return [];
  }
}

function saveLocalSession(clientId, messages) {
  localStorage.setItem(
    CHAT_SESSION_CACHE_KEY,
    JSON.stringify({
      client_id: clientId,
      updated_at: new Date().toISOString(),
      messages,
    }),
  );
}

function renderDocChips(container, pages, lang) {
  const existing = container.querySelector(".helix-chat-doc-chips");
  if (existing) existing.remove();
  if (!pages?.length) return;

  const wrap = document.createElement("div");
  wrap.className = "helix-chat-doc-chips";
  const label = document.createElement("div");
  label.className = "helix-chat-doc-chips-label";
  label.textContent = chatT(lang, "foundDocs");
  wrap.appendChild(label);

  const row = document.createElement("div");
  row.className = "helix-chat-doc-chips-row";
  for (const page of pages) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "helix-chat-doc-chip";
    btn.dataset.slug = page.slug;
    btn.textContent = page.title || page.slug;
    btn.addEventListener("click", () => navigateToDoc(page.slug));
    row.appendChild(btn);
  }
  wrap.appendChild(row);
  container.appendChild(wrap);
}

function bindDocLinks(bubble) {
  bubble.querySelectorAll('a[href*="/docs/"], .helix-chat-doc-link').forEach((link) => {
    const href = link.getAttribute("href") || "";
    const slug = link.dataset.slug || href.match(/(?:#\/docs\/|\/docs\/)([a-z0-9-]+)/)?.[1];
    if (!slug) return;
    link.classList.add("helix-chat-doc-link");
    link.dataset.slug = slug;
    link.setAttribute("href", "#");
    if (link.dataset.bound === "1") return;
    link.dataset.bound = "1";
    link.addEventListener("click", (ev) => {
      ev.preventDefault();
      navigateToDoc(slug);
    });
  });
}

function renderAssistantBubble(bubble, text, pages, lang, { streaming = false } = {}) {
  applyMarkdownContent(bubble, text, { streaming });
  if (pages?.length) renderDocChips(bubble, pages, lang);
}

function renderThinkingBubble(bubble, langKey, langCode = "ru") {
  bubble.className = "helix-chat-bubble assistant typing";
  bubble.replaceChildren();
  const label = document.createElement("span");
  label.className = "helix-chat-thinking-label";
  label.textContent = chatT(langCode, langKey);
  const dots = document.createElement("span");
  dots.className = "helix-chat-thinking-dots";
  dots.setAttribute("aria-hidden", "true");
  dots.innerHTML = "<span></span><span></span><span></span>";
  bubble.append(label, dots);
}

function beginAssistantReply(bubble) {
  if (!bubble.classList.contains("typing")) return;
  bubble.classList.remove("typing");
  bubble.replaceChildren();
}

export async function initChatWidget({ getLang }) {
  let config;
  try {
    const res = await fetch("/api/docs-chat/config.json", { cache: "no-store" });
    if (!res.ok) return;
    config = await res.json();
  } catch {
    return;
  }
  if (!config?.enabled) return;

  const clientId = getOrCreateClientId();
  const sessionPath = config.sessionPath || "/api/docs-chat/session";

  const root = document.createElement("div");
  root.className = "helix-chat-root";
  root.innerHTML = `
    <div class="helix-chat-panel" id="helix-chat-panel" role="dialog" aria-label="Documentation chat">
      <button type="button" class="helix-chat-resize" id="helix-chat-resize" aria-label="Resize chat"></button>
      <div class="helix-chat-header">
        <div>
          <p class="helix-chat-title" id="helix-chat-title"></p>
          <p class="helix-chat-subtitle" id="helix-chat-subtitle"></p>
        </div>
        <div class="helix-chat-header-actions">
          <button type="button" class="helix-chat-new" id="helix-chat-new"></button>
          <button type="button" class="helix-chat-close" id="helix-chat-close" aria-label="Close">×</button>
        </div>
      </div>
      <div class="helix-chat-messages" id="helix-chat-messages"></div>
      <form class="helix-chat-form" id="helix-chat-form">
        <textarea class="helix-chat-input" id="helix-chat-input" rows="1" required></textarea>
        <button type="submit" class="helix-chat-send" id="helix-chat-send"></button>
      </form>
    </div>
    <button type="button" class="helix-chat-toggle" id="helix-chat-toggle" aria-expanded="false" aria-controls="helix-chat-panel">
      <svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.8">
        <path d="M4 5.5h16a1.5 1.5 0 0 1 1.5 1.5v8a1.5 1.5 0 0 1-1.5 1.5H9l-4.5 3v-3H4a1.5 1.5 0 0 1-1.5-1.5V7a1.5 1.5 0 0 1 1.5-1.5z"/>
      </svg>
    </button>
  `;
  document.body.appendChild(root);

  const panel = root.querySelector("#helix-chat-panel");
  const resizeHandle = root.querySelector("#helix-chat-resize");
  const toggle = root.querySelector("#helix-chat-toggle");
  const closeBtn = root.querySelector("#helix-chat-close");
  const newBtn = root.querySelector("#helix-chat-new");
  const messages = root.querySelector("#helix-chat-messages");
  const form = root.querySelector("#helix-chat-form");
  const input = root.querySelector("#helix-chat-input");
  const sendBtn = root.querySelector("#helix-chat-send");
  const titleEl = root.querySelector("#helix-chat-title");
  const subtitleEl = root.querySelector("#helix-chat-subtitle");

  let busy = false;
  let sessionMessages = [];

  function lang() {
    return getLang?.() === "en" ? "en" : "ru";
  }

  function applyLabels() {
    const l = lang();
    titleEl.textContent = chatT(l, "title");
    subtitleEl.textContent = chatT(l, "subtitle");
    input.placeholder = chatT(l, "placeholder");
    sendBtn.textContent = chatT(l, "send");
    newBtn.textContent = chatT(l, "newChat");
    newBtn.title = chatT(l, "newChat");
  }

  function renderMessage(msg) {
    const el = document.createElement("div");
    el.className = `helix-chat-bubble ${msg.role}`;
    if (msg.role === "assistant") {
      if (msg.typing) {
        renderThinkingBubble(el, "thinking", lang());
      } else {
        renderAssistantBubble(el, msg.content || "", msg.pages, lang());
      }
    } else {
      applyMarkdownContent(el, msg.content || "");
    }
    messages.appendChild(el);
    return el;
  }

  function renderAllMessages() {
    messages.replaceChildren();
    for (const msg of sessionMessages) {
      renderMessage(msg);
    }
    messages.scrollTop = messages.scrollHeight;
  }

  function ensureWelcome() {
    if (sessionMessages.length) return;
    sessionMessages.push({
      role: "assistant",
      content: chatT(lang(), "welcome"),
      welcome: true,
    });
    saveLocalSession(clientId, sessionMessages);
  }

  async function loadSession() {
    let serverMessages = [];
    try {
      const res = await fetch(`${sessionPath}?client_id=${encodeURIComponent(clientId)}`, {
        cache: "no-store",
      });
      if (res.ok) {
        const data = await res.json();
        serverMessages = Array.isArray(data.messages) ? data.messages : [];
      }
    } catch {
      /* use local fallback */
    }

    const localMessages = loadLocalSession(clientId);
    sessionMessages =
      serverMessages.length >= localMessages.length ? serverMessages : localMessages;
    ensureWelcome();
    saveLocalSession(clientId, sessionMessages);
    renderAllMessages();
  }

  async function clearSession() {
    sessionMessages = [];
    saveLocalSession(clientId, []);
    try {
      await fetch(`${sessionPath}?client_id=${encodeURIComponent(clientId)}`, {
        method: "DELETE",
      });
    } catch {
      /* ignore */
    }
    ensureWelcome();
    renderAllMessages();
  }

  function setOpen(open) {
    root.classList.toggle("is-open", open);
    toggle.setAttribute("aria-expanded", open ? "true" : "false");
    if (open) input.focus();
  }

  function recordExchange(userText, assistantText, pages) {
    sessionMessages.push({ role: "user", content: userText });
    const entry = { role: "assistant", content: assistantText };
    if (pages?.length) entry.pages = pages;
    sessionMessages.push(entry);
    saveLocalSession(clientId, sessionMessages);
  }

  async function sendMessage(text) {
    if (busy) return;
    busy = true;
    sendBtn.disabled = true;
    renderMessage({ role: "user", content: text });
    const typing = renderMessage({ role: "assistant", typing: true });
    messages.scrollTop = messages.scrollHeight;

    let streamedText = "";
    let foundPages = [];
    let pendingOpenSlug = null;
    const replyEl = typing;

    try {
      const res = await fetch(config.proxyPath || "/api/docs-chat", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "text/event-stream",
        },
        body: JSON.stringify({
          message: text,
          client_id: clientId,
          lang: lang(),
          page_slug: getPageSlug(),
          stream: true,
        }),
      });

      if (!res.ok) {
        typing.className = "helix-chat-bubble error";
        typing.textContent = chatT(lang(), "error");
        return;
      }

      const contentType = res.headers.get("Content-Type") || "";
      if (!contentType.includes("text/event-stream") || !res.body) {
        const data = await res.json();
        typing.classList.remove("typing");
        typing.className = "helix-chat-bubble assistant";
        const content = data.content || chatT(lang(), "error");
        renderAssistantBubble(typing, content, data.pages, lang());
        recordExchange(text, content, data.pages);
        if (replyEl.isConnected) navigateFromLatestReply({ text: content, openSlug: data.open_slug });
        return;
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split("\n\n");
        buffer = parts.pop() || "";
        for (const part of parts) {
          const evt = parseSseBlock(part);
          if (!evt) continue;
          if (evt.type === "docs" && evt.pages?.length) {
            foundPages = evt.pages;
            if (streamedText.trim()) {
              beginAssistantReply(typing);
              renderAssistantBubble(typing, streamedText, foundPages, lang(), { streaming: true });
            } else {
              renderDocChips(typing, foundPages, lang());
            }
          } else if (evt.type === "content") {
            const piece = evt.content || "";
            if (!piece) continue;
            streamedText += piece;
            beginAssistantReply(typing);
            renderAssistantBubble(typing, streamedText, foundPages, lang(), { streaming: true });
            messages.scrollTop = messages.scrollHeight;
          } else if (evt.type === "replace") {
            streamedText = evt.content || "";
            if (!streamedText.trim()) continue;
            beginAssistantReply(typing);
            renderAssistantBubble(typing, streamedText, foundPages, lang(), { streaming: true });
          } else if (evt.type === "done") {
            pendingOpenSlug = evt.open_slug || null;
          } else if (evt.type === "error") {
            typing.className = "helix-chat-bubble error";
            typing.textContent = evt.message || chatT(lang(), "error");
          }
        }
      }

      if (!streamedText.trim()) {
        typing.className = "helix-chat-bubble error";
        typing.textContent = chatT(lang(), "error");
        recordExchange(text, chatT(lang(), "error"), []);
      } else {
        beginAssistantReply(typing);
        renderAssistantBubble(typing, streamedText, foundPages, lang());
        recordExchange(text, streamedText, foundPages);
        if (replyEl.isConnected) navigateFromLatestReply({ text: streamedText, openSlug: pendingOpenSlug });
      }
    } catch {
      typing.className = "helix-chat-bubble error";
      typing.textContent = chatT(lang(), "error");
    } finally {
      busy = false;
      sendBtn.disabled = false;
      input.focus();
    }
  }

  toggle.addEventListener("click", () => setOpen(!root.classList.contains("is-open")));
  closeBtn.addEventListener("click", () => {
    setOpen(false);
    localStorage.setItem(CHAT_DISMISSED_KEY, "1");
  });
  newBtn.addEventListener("click", async () => {
    if (busy) return;
    if (!window.confirm(chatT(lang(), "newChatConfirm"))) return;
    await clearSession();
  });

  form.addEventListener("submit", (ev) => {
    ev.preventDefault();
    const text = input.value.trim();
    if (!text) return;
    input.value = "";
    sendMessage(text);
  });

  input.addEventListener("keydown", (ev) => {
    if (ev.key === "Enter" && !ev.shiftKey) {
      ev.preventDefault();
      form.requestSubmit();
    }
  });

  applyChatSize(panel, loadChatSize());
  bindChatResize(panel, resizeHandle, getLang);

  applyLabels();
  document.addEventListener("helix-lang-change", applyLabels);
  await loadSession();

  const dismissed = localStorage.getItem(CHAT_DISMISSED_KEY) === "1";
  if (!dismissed) {
    setOpen(true);
  }
}