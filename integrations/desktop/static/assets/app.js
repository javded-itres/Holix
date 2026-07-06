import {
  configureMonacoLanguages,
  EDITOR_SUGGEST_OPTIONS,
  setupMonacoEnvironment,
} from "./monaco_languages.js";
import { renderMarkdown } from "./markdown_render.js";

setupMonacoEnvironment();

const params = new URLSearchParams(window.location.search);
const token =
  window.HOLIX_STUDIO_TOKEN ||
  params.get("token") ||
  sessionStorage.getItem("holix_studio_token") ||
  "";
if (token) sessionStorage.setItem("holix_studio_token", token);

const authHeaders = () => (token ? { Authorization: `Bearer ${token}` } : {});
const apiUrl = (path) => {
  const sep = path.includes("?") ? "&" : "?";
  const q = token ? `${sep}token=${encodeURIComponent(token)}` : "";
  return `${path}${q}`;
};

const els = {
  profile: document.getElementById("profile-label"),
  status: document.getElementById("conn-status"),
  fileTree: document.getElementById("file-tree"),
  selectedDir: document.getElementById("selected-dir"),
  newFileBtn: document.getElementById("new-file-btn"),
  newFolderBtn: document.getElementById("new-folder-btn"),
  uploadBtn: document.getElementById("upload-btn"),
  fileUpload: document.getElementById("file-upload"),
  editorTitle: document.getElementById("editor-title"),
  editorHost: document.getElementById("editor"),
  previewHost: document.getElementById("preview-host"),
  diffHost: document.getElementById("diff-editor"),
  viewSourceBtn: document.getElementById("view-source-btn"),
  viewPreviewBtn: document.getElementById("view-preview-btn"),
  diffToggle: document.getElementById("diff-toggle"),
  saveBtn: document.getElementById("save-btn"),
  newFileDialog: document.getElementById("new-file-dialog"),
  newFileForm: document.getElementById("new-file-form"),
  newFileName: document.getElementById("new-file-name"),
  newFileDirLabel: document.getElementById("new-file-dir-label"),
  newFileCancel: document.getElementById("new-file-cancel"),
  newFolderDialog: document.getElementById("new-folder-dialog"),
  newFolderForm: document.getElementById("new-folder-form"),
  newFolderName: document.getElementById("new-folder-name"),
  newFolderDirLabel: document.getElementById("new-folder-dir-label"),
  newFolderCancel: document.getElementById("new-folder-cancel"),
  chatLog: document.getElementById("chat-log"),
  chatForm: document.getElementById("chat-form"),
  chatInput: document.getElementById("chat-input"),
  stopBtn: document.getElementById("stop-btn"),
  layout: document.getElementById("layout"),
  filesPanel: document.getElementById("files-panel"),
  editorPanel: document.getElementById("editor-panel"),
  chatPanel: document.getElementById("chat-panel"),
  resizeFiles: document.getElementById("resize-files"),
  resizeChat: document.getElementById("resize-chat"),
  chatCollapseBtn: document.getElementById("chat-collapse-btn"),
  chatExpandBtn: document.getElementById("chat-expand-btn"),
};

const PANEL_LAYOUT_KEY = "holix_studio_panel_layout_v1";
const MARKDOWN_VIEW_KEY = "holix_studio_md_view_v1";
const PREVIEW_DEBOUNCE_MS = 150;
const PANEL_LIMITS = {
  files: { min: 160, max: 520, default: 240 },
  chat: { min: 280, max: 640, default: 360 },
  editorMin: 200,
};
let panelLayout = loadPanelLayout();

let monacoReady = null;
let editor = null;
let diffEditor = null;
let ws = null;
let streamBuffer = "";
let pendingDiff = null;
let runActive = false;

let currentFilePath = null;
let editorDirty = false;
let editorViewMode = loadMarkdownViewMode();
let previewTimer = null;
let selectedDirPath = "";
let expandedDirs = loadExpandedDirs();
let treeNodes = [];

function loadPanelLayout() {
  try {
    const raw = sessionStorage.getItem(PANEL_LAYOUT_KEY);
    if (!raw) return { filesWidth: 240, chatWidth: 360, chatCollapsed: false };
    const data = JSON.parse(raw);
    return {
      filesWidth: clampPanelWidth("files", data.filesWidth ?? 240),
      chatWidth: clampPanelWidth("chat", data.chatWidth ?? 360),
      chatCollapsed: Boolean(data.chatCollapsed),
    };
  } catch {
    return { filesWidth: 240, chatWidth: 360, chatCollapsed: false };
  }
}

function savePanelLayout() {
  sessionStorage.setItem(PANEL_LAYOUT_KEY, JSON.stringify(panelLayout));
}

function clampPanelWidth(panel, value) {
  const limits = PANEL_LIMITS[panel];
  return Math.round(Math.max(limits.min, Math.min(limits.max, Number(value) || limits.default)));
}

function applyPanelLayout() {
  if (!els.layout) return;
  els.layout.style.setProperty("--files-width", `${panelLayout.filesWidth}px`);
  els.layout.style.setProperty("--chat-width", `${panelLayout.chatWidth}px`);
  const collapsed = panelLayout.chatCollapsed;
  els.chatPanel?.classList.toggle("collapsed", collapsed);
  els.resizeChat?.classList.toggle("hidden", collapsed);
  els.chatExpandBtn?.classList.toggle("hidden", !collapsed);
  els.chatCollapseBtn?.classList.toggle("hidden", collapsed);
  requestEditorLayout();
}

function requestEditorLayout() {
  if (editor) editor.layout();
  if (diffEditor) diffEditor.layout();
}

function initPanelResizers() {
  if (!els.layout) return;

  const startResize = (panel, handle, startX, startWidth) => {
    const onMove = (ev) => {
      const dx = ev.clientX - startX;
      const layoutWidth = els.layout.clientWidth;
      const otherPanelWidth =
        panel === "files"
          ? panelLayout.chatCollapsed
            ? 0
            : panelLayout.chatWidth
          : panelLayout.filesWidth;
      const handleSpace = panelLayout.chatCollapsed ? 4 : 8;
      const max =
        panel === "files"
          ? layoutWidth - otherPanelWidth - PANEL_LIMITS.editorMin - handleSpace
          : layoutWidth - panelLayout.filesWidth - PANEL_LIMITS.editorMin - handleSpace;
      const next = clampPanelWidth(panel, startWidth + (panel === "files" ? dx : -dx));
      const capped = Math.min(next, max);
      if (panel === "files") panelLayout.filesWidth = capped;
      else panelLayout.chatWidth = capped;
      applyPanelLayout();
    };
    const onUp = () => {
      els.layout.classList.remove("resizing");
      handle?.classList.remove("active");
      document.removeEventListener("pointermove", onMove);
      document.removeEventListener("pointerup", onUp);
      savePanelLayout();
      requestEditorLayout();
    };
    els.layout.classList.add("resizing");
    handle?.classList.add("active");
    document.addEventListener("pointermove", onMove);
    document.addEventListener("pointerup", onUp);
  };

  els.resizeFiles?.addEventListener("pointerdown", (e) => {
    e.preventDefault();
    startResize("files", els.resizeFiles, e.clientX, panelLayout.filesWidth);
  });
  els.resizeChat?.addEventListener("pointerdown", (e) => {
    if (panelLayout.chatCollapsed) return;
    e.preventDefault();
    startResize("chat", els.resizeChat, e.clientX, panelLayout.chatWidth);
  });

  els.chatCollapseBtn?.addEventListener("click", () => {
    panelLayout.chatCollapsed = true;
    applyPanelLayout();
    savePanelLayout();
  });
  els.chatExpandBtn?.addEventListener("click", () => {
    panelLayout.chatCollapsed = false;
    applyPanelLayout();
    savePanelLayout();
  });

  window.addEventListener("resize", () => requestEditorLayout());
  applyPanelLayout();
}

function loadExpandedDirs() {
  try {
    const raw = sessionStorage.getItem("holix_studio_expanded_dirs_v2");
    return new Set(raw ? JSON.parse(raw) : []);
  } catch {
    return new Set();
  }
}

function saveExpandedDirs() {
  sessionStorage.setItem(
    "holix_studio_expanded_dirs_v2",
    JSON.stringify([...expandedDirs]),
  );
}

function loadMonaco() {
  if (monacoReady) return monacoReady;
  monacoReady = new Promise((resolve) => {
    require.config({
      paths: { vs: "https://cdn.jsdelivr.net/npm/monaco-editor@0.52.2/min/vs" },
    });
    require(["vs/editor/editor.main"], () => {
      configureMonacoLanguages(window.monaco);
      resolve(window.monaco);
    });
  });
  return monacoReady;
}

async function initEditor() {
  const monaco = await loadMonaco();
  editor = monaco.editor.create(els.editorHost, {
    value: "// Select a file from the workspace tree",
    language: "plaintext",
    theme: "vs-dark",
    readOnly: true,
    automaticLayout: true,
    minimap: { enabled: false },
    ...EDITOR_SUGGEST_OPTIONS,
  });
  editor.onDidChangeModelContent(() => {
    if (currentFilePath && !editor.getOption(monaco.editor.EditorOption.readOnly)) {
      editorDirty = true;
      updateEditorChrome();
    }
    scheduleMarkdownPreview();
  });
  editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, () => {
    saveCurrentFile();
  });
  diffEditor = monaco.editor.createDiffEditor(els.diffHost, {
    theme: "vs-dark",
    automaticLayout: true,
    readOnly: true,
  });
}

function setStatus(text, ok) {
  els.status.textContent = text;
  els.status.className = ok ? "status ok" : "status err";
}

function loadMarkdownViewMode() {
  try {
    return sessionStorage.getItem(MARKDOWN_VIEW_KEY) === "preview" ? "preview" : "source";
  } catch {
    return "source";
  }
}

function saveMarkdownViewMode() {
  sessionStorage.setItem(MARKDOWN_VIEW_KEY, editorViewMode);
}

function isMarkdownPath(path) {
  if (!path) return false;
  const lower = path.toLowerCase();
  return lower.endsWith(".md") || lower.endsWith(".markdown");
}

function appendChat(text, cls, options = {}) {
  const { streaming = false } = options;
  const wrap = document.createElement("div");
  wrap.className = `msg ${cls}${streaming ? " streaming" : ""}`;
  const body = document.createElement("div");
  body.className = "msg-body";
  body.textContent = text;
  wrap.appendChild(body);
  els.chatLog.appendChild(wrap);
  els.chatLog.scrollTop = els.chatLog.scrollHeight;
  return wrap;
}

function ensureAssistantToggle(msgEl) {
  if (msgEl.querySelector(".msg-toggle")) return;
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "msg-toggle btn small";
  btn.textContent = "Source";
  btn.addEventListener("click", () => toggleAssistantMessageMode(msgEl));
  msgEl.appendChild(btn);
}

function setAssistantMessageBody(msgEl, text, mode) {
  const body = msgEl.querySelector(".msg-body");
  if (!body) return;
  msgEl.dataset.raw = text;
  if (mode === "source") {
    body.textContent = text;
    msgEl.classList.remove("rendered");
    const btn = msgEl.querySelector(".msg-toggle");
    if (btn) btn.textContent = "Preview";
    return;
  }
  body.innerHTML = renderMarkdown(text);
  msgEl.classList.add("rendered");
  const btn = msgEl.querySelector(".msg-toggle");
  if (btn) btn.textContent = "Source";
}

function finalizeAssistantMessage(msgEl, text) {
  if (!msgEl || !text) return;
  msgEl.classList.remove("streaming");
  ensureAssistantToggle(msgEl);
  setAssistantMessageBody(msgEl, text, "rendered");
  els.chatLog.scrollTop = els.chatLog.scrollHeight;
}

function toggleAssistantMessageMode(msgEl) {
  const raw = msgEl.dataset.raw || msgEl.querySelector(".msg-body")?.textContent || "";
  const next = msgEl.classList.contains("rendered") ? "source" : "rendered";
  setAssistantMessageBody(msgEl, raw, next);
}

function appendAssistantMessage(text) {
  const wrap = appendChat("", "assistant");
  finalizeAssistantMessage(wrap, text);
  return wrap;
}

function updateMarkdownPreview() {
  if (!els.previewHost || !editor) return;
  els.previewHost.innerHTML = renderMarkdown(editor.getValue());
}

function scheduleMarkdownPreview() {
  if (editorViewMode !== "preview" || !isMarkdownPath(currentFilePath)) return;
  clearTimeout(previewTimer);
  previewTimer = setTimeout(updateMarkdownPreview, PREVIEW_DEBOUNCE_MS);
}

function setEditorViewMode(mode) {
  editorViewMode = mode === "preview" ? "preview" : "source";
  saveMarkdownViewMode();
  applyEditorViewMode();
}

function applyEditorViewMode() {
  const md = isMarkdownPath(currentFilePath);
  els.viewSourceBtn?.classList.toggle("hidden", !md);
  els.viewPreviewBtn?.classList.toggle("hidden", !md);
  if (!md) {
    els.editorHost?.classList.remove("hidden");
    els.previewHost?.classList.add("hidden");
    return;
  }
  els.viewSourceBtn?.classList.toggle("active-view", editorViewMode === "source");
  els.viewPreviewBtn?.classList.toggle("active-view", editorViewMode === "preview");
  const preview = editorViewMode === "preview";
  els.editorHost?.classList.toggle("hidden", preview);
  els.previewHost?.classList.toggle("hidden", !preview);
  if (preview) updateMarkdownPreview();
  requestEditorLayout();
}

function updateSelectedDirLabel() {
  els.selectedDir.textContent = selectedDirPath ? `/${selectedDirPath}` : "/";
}

function selectDirectory(path) {
  selectedDirPath = path || "";
  document.querySelectorAll(".tree-dir.active").forEach((n) => n.classList.remove("active"));
  if (selectedDirPath) {
    const row = els.fileTree.querySelector(`.tree-dir[data-path="${CSS.escape(selectedDirPath)}"]`);
    if (row) row.classList.add("active");
  }
  updateSelectedDirLabel();
}

function expandPathAncestors(path) {
  const parts = (path || "").split("/").filter(Boolean);
  for (let i = 1; i <= parts.length; i++) {
    expandedDirs.add(parts.slice(0, i).join("/"));
  }
  saveExpandedDirs();
}

function renderTree(nodes, container) {
  treeNodes = nodes || [];
  container.innerHTML = "";
  const root = document.createElement("div");
  for (const node of treeNodes) {
    root.appendChild(renderNode(node));
  }
  container.appendChild(root);
  if (selectedDirPath) selectDirectory(selectedDirPath);
  if (currentFilePath) {
    const fileEl = els.fileTree.querySelector(
      `.tree-file[data-path="${CSS.escape(currentFilePath)}"]`,
    );
    if (fileEl) fileEl.classList.add("active");
  }
}

function renderNode(node) {
  const wrap = document.createElement("div");
  wrap.className = "tree-node";
  if (node.kind === "directory") {
    const hasKids = Boolean(node.children?.length);
    const expanded = expandedDirs.has(node.path);
    const row = document.createElement("div");
    row.className = "tree-row";

    const toggle = document.createElement("button");
    toggle.type = "button";
    toggle.className = hasKids ? "tree-toggle" : "tree-toggle placeholder";
    toggle.textContent = expanded ? "▼" : "▶";
    toggle.setAttribute("aria-label", expanded ? "Collapse" : "Expand");
    if (hasKids) {
      toggle.addEventListener("click", (e) => {
        e.stopPropagation();
        if (expandedDirs.has(node.path)) expandedDirs.delete(node.path);
        else expandedDirs.add(node.path);
        saveExpandedDirs();
        renderTree(treeNodes, els.fileTree);
      });
    }

    const label = document.createElement("div");
    label.className = "tree-item tree-dir";
    label.textContent = `📁 ${node.name}`;
    label.dataset.path = node.path;
    label.title = node.path;
    label.addEventListener("click", () => selectDirectory(node.path));

    row.appendChild(toggle);
    row.appendChild(label);
    wrap.appendChild(row);

    if (hasKids) {
      const kids = document.createElement("div");
      kids.className = expanded ? "tree-children" : "tree-children collapsed";
      for (const child of node.children) kids.appendChild(renderNode(child));
      wrap.appendChild(kids);
    }
  } else {
    const row = document.createElement("div");
    row.className = "tree-row";
    const spacer = document.createElement("button");
    spacer.type = "button";
    spacer.className = "tree-toggle placeholder";
    spacer.tabIndex = -1;

    const file = document.createElement("div");
    file.className = "tree-item tree-file";
    file.textContent = node.name;
    file.dataset.path = node.path;
    file.title = node.path;
    file.addEventListener("click", () => openFile(node.path, file));

    row.appendChild(spacer);
    row.appendChild(file);
    wrap.appendChild(row);
  }
  return wrap;
}

async function refreshTree() {
  const res = await fetch(apiUrl("/studio/api/files/tree"), { headers: authHeaders() });
  if (!res.ok) throw new Error(await res.text());
  const data = await res.json();
  renderTree(data.children, els.fileTree);
}

function updateEditorChrome() {
  if (!currentFilePath) {
    els.editorTitle.textContent = "Editor";
    els.saveBtn.classList.add("hidden");
    els.saveBtn.disabled = true;
    applyEditorViewMode();
    return;
  }
  const dirtyMark = editorDirty ? " •" : "";
  els.editorTitle.textContent = `${currentFilePath}${dirtyMark}`;
  els.saveBtn.classList.remove("hidden");
  els.saveBtn.disabled = !editorDirty;
  applyEditorViewMode();
}

function setEditorReadOnly(readOnly) {
  const monaco = window.monaco;
  if (!editor || !monaco) return;
  editor.updateOptions({ readOnly });
}

async function openFile(path, el) {
  if (editorDirty) {
    const discard = confirm(
      "Есть несохранённые изменения. Открыть другой файл без сохранения?",
    );
    if (!discard) return;
    editorDirty = false;
  }

  document.querySelectorAll(".tree-file.active").forEach((n) => n.classList.remove("active"));
  if (el) el.classList.add("active");

  const slash = path.lastIndexOf("/");
  selectDirectory(slash >= 0 ? path.slice(0, slash) : "");

  showEditor();
  const res = await fetch(apiUrl(`/studio/api/files/read?path=${encodeURIComponent(path)}`), {
    headers: authHeaders(),
  });
  if (!res.ok) {
    appendChat(`Cannot open ${path}: ${await res.text()}`, "error");
    return;
  }
  const data = await res.json();
  const monaco = await loadMonaco();
  currentFilePath = data.path;
  editorDirty = false;
  const model = editor.getModel();
  if (model) model.dispose();
  editor.setModel(
    monaco.editor.createModel(data.content, data.language || "plaintext"),
  );
  setEditorReadOnly(false);
  updateEditorChrome();
}

async function saveCurrentFile() {
  if (!currentFilePath || !editorDirty) return;
  const content = editor.getValue();
  const res = await fetch(apiUrl("/studio/api/files/write"), {
    method: "POST",
    headers: { ...authHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify({ path: currentFilePath, content }),
  });
  if (!res.ok) {
    appendChat(`Save failed: ${await res.text()}`, "error");
    return;
  }
  editorDirty = false;
  updateEditorChrome();
}

function openNewFileDialog() {
  if (!els.newFileDialog) return;
  els.newFileDirLabel.textContent = `Папка: ${selectedDirPath ? `/${selectedDirPath}` : "/"}`;
  els.newFileName.value = "untitled.txt";
  els.newFileDialog.showModal();
  requestAnimationFrame(() => {
    els.newFileName.focus();
    els.newFileName.select();
  });
}

function closeNewFileDialog() {
  els.newFileDialog?.close();
}

async function createNewFile(name) {
  const trimmed = (name || "").trim();
  if (!trimmed) return;
  const path = selectedDirPath ? `${selectedDirPath}/${trimmed}` : trimmed;
  const res = await fetch(apiUrl("/studio/api/files/write"), {
    method: "POST",
    headers: { ...authHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify({ path, content: "", create_only: true }),
  });
  if (!res.ok) {
    appendChat(`Create failed: ${await res.text()}`, "error");
    return;
  }
  const data = await res.json();
  expandPathAncestors(path);
  await refreshTree();
  const fileEl = els.fileTree.querySelector(`.tree-file[data-path="${CSS.escape(data.path)}"]`);
  await openFile(data.path, fileEl);
}

function openNewFolderDialog() {
  if (!els.newFolderDialog) return;
  els.newFolderDirLabel.textContent = `Папка: ${selectedDirPath ? `/${selectedDirPath}` : "/"}`;
  els.newFolderName.value = "new-folder";
  els.newFolderDialog.showModal();
  requestAnimationFrame(() => {
    els.newFolderName.focus();
    els.newFolderName.select();
  });
}

function closeNewFolderDialog() {
  els.newFolderDialog?.close();
}

async function createNewFolder(name) {
  const trimmed = (name || "").trim().replace(/\/+$/, "");
  if (!trimmed) return;
  const path = selectedDirPath ? `${selectedDirPath}/${trimmed}` : trimmed;
  const res = await fetch(apiUrl("/studio/api/files/mkdir"), {
    method: "POST",
    headers: { ...authHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify({ path }),
  });
  if (!res.ok) {
    appendChat(`Folder create failed: ${await res.text()}`, "error");
    return;
  }
  const data = await res.json();
  expandPathAncestors(data.path);
  await refreshTree();
  selectDirectory(data.path);
}

async function uploadFiles(fileList) {
  if (!fileList?.length) return;
  let ok = 0;
  for (const file of fileList) {
    const body = new FormData();
    body.append("directory", selectedDirPath);
    body.append("file", file, file.name);
    const res = await fetch(apiUrl("/studio/api/files/upload"), {
      method: "POST",
      headers: authHeaders(),
      body,
    });
    if (!res.ok) {
      appendChat(`Upload ${file.name}: ${await res.text()}`, "error");
    } else {
      ok += 1;
    }
  }
  if (ok) {
    if (selectedDirPath) expandedDirs.add(selectedDirPath);
    saveExpandedDirs();
    await refreshTree();
    appendChat(`Uploaded ${ok} file(s)`, "tool");
  }
}

function showEditor() {
  els.diffHost.classList.add("hidden");
  els.diffToggle.classList.add("hidden");
  applyEditorViewMode();
}

async function showDiff(diff) {
  pendingDiff = diff;
  const monaco = await loadMonaco();
  currentFilePath = null;
  editorDirty = false;
  setEditorReadOnly(true);
  updateEditorChrome();
  els.editorTitle.textContent = `Diff: ${diff.path}`;
  els.editorHost.classList.add("hidden");
  els.previewHost?.classList.add("hidden");
  els.viewSourceBtn?.classList.add("hidden");
  els.viewPreviewBtn?.classList.add("hidden");
  els.diffHost.classList.remove("hidden");
  els.diffToggle.classList.remove("hidden");
  els.diffToggle.textContent = "Show file";
  const original = monaco.editor.createModel(diff.old || "", "plaintext");
  const modified = monaco.editor.createModel(diff.new || "", "plaintext");
  diffEditor.setModel({ original, modified });
}

els.diffToggle.addEventListener("click", async () => {
  if (pendingDiff?.path) {
    showEditor();
    await openFile(pendingDiff.path);
  }
});
els.viewSourceBtn?.addEventListener("click", () => setEditorViewMode("source"));
els.viewPreviewBtn?.addEventListener("click", () => setEditorViewMode("preview"));

els.newFileBtn?.addEventListener("click", () => openNewFileDialog());
els.newFileCancel?.addEventListener("click", () => closeNewFileDialog());
els.newFileForm?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const name = els.newFileName?.value || "";
  closeNewFileDialog();
  await createNewFile(name);
});
els.newFolderBtn?.addEventListener("click", () => openNewFolderDialog());
els.newFolderCancel?.addEventListener("click", () => closeNewFolderDialog());
els.newFolderForm?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const name = els.newFolderName?.value || "";
  closeNewFolderDialog();
  await createNewFolder(name);
});
els.uploadBtn?.addEventListener("click", () => els.fileUpload?.click());
els.fileUpload.addEventListener("change", async (e) => {
  await uploadFiles(e.target.files);
  e.target.value = "";
});
els.saveBtn.addEventListener("click", () => saveCurrentFile());

function connectWs() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const q = token ? `?token=${encodeURIComponent(token)}` : "";
  ws = new WebSocket(`${proto}://${location.host}/studio/ws${q}`);
  ws.onopen = () => setStatus("connected", true);
  ws.onclose = () => setStatus("disconnected", false);
  ws.onerror = () => setStatus("error", false);
  ws.onmessage = (ev) => {
    let msg;
    try {
      msg = JSON.parse(ev.data);
    } catch {
      return;
    }
    handleWs(msg);
  };
}

function setRunActive(active) {
  runActive = active;
  els.chatInput.disabled = active;
  els.chatForm.querySelector('button[type="submit"]').disabled = active;
  els.stopBtn.disabled = !active;
}

function handleWs(msg) {
  switch (msg.type) {
    case "connected":
      els.profile.textContent = msg.workspace_root
        ? `profile: ${msg.profile} · ${msg.workspace_root}`
        : `profile: ${msg.profile}`;
      break;
    case "run_started":
      setRunActive(true);
      streamBuffer = "";
      break;
    case "thinking": {
      const last = els.chatLog.querySelector(".msg.thinking:last-child");
      const text = msg.message || "Thinking…";
      if (last && runActive) {
        const body = last.querySelector(".msg-body");
        if (body) body.textContent = text;
        else last.textContent = text;
      } else {
        appendChat(text, "thinking");
      }
      break;
    }
    case "assistant_delta":
      if (!streamBuffer) appendChat("", "assistant", { streaming: true });
      streamBuffer += msg.content || "";
      {
        const last = els.chatLog.querySelector(".msg.assistant.streaming:last-child");
        const body = last?.querySelector(".msg-body");
        if (body) body.textContent = streamBuffer;
      }
      break;
    case "final_response": {
      setRunActive(false);
      const content = msg.content || streamBuffer;
      streamBuffer = "";
      if (content) {
        const last = els.chatLog.querySelector(".msg.assistant:last-child");
        if (last) finalizeAssistantMessage(last, content);
        else appendAssistantMessage(content);
      }
      refreshTree().catch(() => {});
      break;
    }
    case "tool_call_start":
      appendChat(`▶ ${msg.tool_name}`, "tool");
      break;
    case "tool_call_result":
      if (msg.file_diff) showDiff(msg.file_diff);
      break;
    case "tool_call_error": {
      const errText = (msg.message || msg.error || "").trim();
      if (errText) {
        appendChat(
          msg.tool_name ? `✖ ${msg.tool_name}: ${errText}` : `✖ ${errText}`,
          "error",
        );
      }
      break;
    }
    case "confirmation_request":
      appendChat(
        `⚠ ${msg.tool_name || "tool"}: ${msg.reason || "требуется подтверждение"}`,
        "tool",
      );
      break;
    case "confirmation_response":
    case "subagent_question":
      break;
    case "error": {
      const errText = (msg.message || msg.error || "").trim();
      if (!errText) break;
      setRunActive(false);
      appendChat(errText, "error");
      streamBuffer = "";
      break;
    }
    case "max_steps_reached":
      setRunActive(false);
      appendChat(`Max steps reached (${msg.max_steps || "?"})`, "error");
      streamBuffer = "";
      break;
    case "run_stopped":
      setRunActive(false);
      appendChat("Stopped.", "tool");
      streamBuffer = "";
      break;
    case "run_finished":
      setRunActive(false);
      break;
    default:
      break;
  }
}

function sendWs(payload) {
  if (ws?.readyState === WebSocket.OPEN) ws.send(JSON.stringify(payload));
}

els.chatForm.addEventListener("submit", (e) => {
  e.preventDefault();
  e.stopPropagation();
  const text = els.chatInput.value.trim();
  if (!text) return;
  if (runActive) {
    appendChat("Дождитесь ответа или нажмите Stop.", "tool");
    return;
  }
  appendChat(text, "user");
  streamBuffer = "";
  sendWs({ type: "user_message", text });
  els.chatInput.value = "";
});

els.stopBtn.addEventListener("click", () => sendWs({ type: "slash", command: "/stop" }));

async function boot() {
  initPanelResizers();
  updateSelectedDirLabel();
  connectWs();
  try {
    await initEditor();
    await refreshTree();
  } catch (err) {
    setStatus("tree load failed", false);
    appendChat(`Workspace: ${err}`, "error");
  }
}

boot();