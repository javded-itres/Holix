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
const apiJsonHeaders = () => ({
  ...authHeaders(),
  "Content-Type": "application/json",
});
const apiUrl = (path) => {
  const sep = path.includes("?") ? "&" : "?";
  const q = token ? `${sep}token=${encodeURIComponent(token)}` : "";
  return `${path}${q}`;
};

const els = {
  profile: document.getElementById("profile-label"),
  status: document.getElementById("conn-status"),
  fileTree: document.getElementById("file-tree"),
  treeContextMenu: document.getElementById("tree-context-menu"),
  selectedDir: document.getElementById("selected-dir"),
  newFileBtn: document.getElementById("new-file-btn"),
  newFolderBtn: document.getElementById("new-folder-btn"),
  deleteItemBtn: document.getElementById("delete-item-btn"),
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
  moveDialog: document.getElementById("move-dialog"),
  moveForm: document.getElementById("move-form"),
  moveSourceLabel: document.getElementById("move-source-label"),
  moveDestination: document.getElementById("move-destination"),
  moveIntoDir: document.getElementById("move-into-dir"),
  moveCancel: document.getElementById("move-cancel"),
  deleteDialog: document.getElementById("delete-dialog"),
  deleteForm: document.getElementById("delete-form"),
  deleteTargetLabel: document.getElementById("delete-target-label"),
  deleteCancel: document.getElementById("delete-cancel"),
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
let focusedTreeItem = null;
let moveSourcePath = null;
let deletePending = null;

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

function parentDir(path) {
  const slash = (path || "").lastIndexOf("/");
  return slash >= 0 ? path.slice(0, slash) : "";
}

function canMoveInto(sourcePath, destDir, sourceKind) {
  if (!sourcePath) return false;
  const dest = destDir || "";
  if (sourcePath === dest) return false;
  if (sourceKind === "directory") {
    if (dest === sourcePath || dest.startsWith(`${sourcePath}/`)) return false;
  }
  if (parentDir(sourcePath) === dest) return false;
  return true;
}

function clearDropTargets() {
  els.fileTree?.querySelectorAll(".drop-target").forEach((n) => n.classList.remove("drop-target"));
}

function setFocusedTreeItem(path, kind) {
  focusedTreeItem = path ? { path, kind } : null;
  updateTreeSelectionChrome();
}

function updateTreeSelectionChrome() {
  const has = Boolean(focusedTreeItem?.path);
  els.deleteItemBtn?.classList.toggle("hidden", !has);
}

function hideTreeContextMenu() {
  els.treeContextMenu?.classList.add("hidden");
}

function bindContextMenuAction(btn, handler) {
  btn.addEventListener("mousedown", (e) => e.stopPropagation());
  btn.addEventListener("click", (e) => {
    e.preventDefault();
    e.stopPropagation();
    hideTreeContextMenu();
    handler();
  });
}

function showTreeContextMenu(x, y, node) {
  if (!els.treeContextMenu) return;
  hideTreeContextMenu();
  setFocusedTreeItem(node.path, node.kind);
  const destLabel = selectedDirPath ? `/${selectedDirPath}` : "/";
  const menu = els.treeContextMenu;
  menu.innerHTML = "";

  const intoBtn = document.createElement("button");
  intoBtn.type = "button";
  intoBtn.textContent = `В текущую папку (${destLabel})`;
  intoBtn.disabled = !canMoveInto(node.path, selectedDirPath, node.kind);
  bindContextMenuAction(intoBtn, () => {
    moveTreePath(node.path, selectedDirPath, true);
  });

  const moveBtn = document.createElement("button");
  moveBtn.type = "button";
  moveBtn.textContent = "Переместить…";
  bindContextMenuAction(moveBtn, () => openMoveDialog(node.path));

  const delBtn = document.createElement("button");
  delBtn.type = "button";
  delBtn.className = "danger";
  delBtn.textContent = node.kind === "directory" ? "Удалить папку" : "Удалить файл";
  bindContextMenuAction(delBtn, () => openDeleteDialog(node.path, node.kind));

  menu.append(intoBtn, moveBtn, delBtn);
  menu.style.left = `${x}px`;
  menu.style.top = `${y}px`;
  menu.classList.remove("hidden");
  const rect = menu.getBoundingClientRect();
  const maxX = Math.max(8, window.innerWidth - rect.width - 8);
  const maxY = Math.max(8, window.innerHeight - rect.height - 8);
  menu.style.left = `${Math.min(x, maxX)}px`;
  menu.style.top = `${Math.min(y, maxY)}px`;
}

function setupDirectoryDropTarget(el, dirPath) {
  el.addEventListener("dragover", (e) => {
    if (!e.dataTransfer?.types?.includes("text/x-holix-path")) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
    el.classList.add("drop-target");
  });
  el.addEventListener("dragleave", () => el.classList.remove("drop-target"));
  el.addEventListener("drop", async (e) => {
    e.preventDefault();
    el.classList.remove("drop-target");
    const source = e.dataTransfer.getData("text/x-holix-path");
    const kind = e.dataTransfer.getData("text/x-holix-kind");
    if (!source || !canMoveInto(source, dirPath, kind)) return;
    await moveTreePath(source, dirPath, true);
  });
}

function attachTreeItem(el, node) {
  el.dataset.path = node.path;
  el.dataset.kind = node.kind;
  el.draggable = true;

  el.addEventListener("dragstart", (e) => {
    e.dataTransfer.setData("text/x-holix-path", node.path);
    e.dataTransfer.setData("text/x-holix-kind", node.kind);
    e.dataTransfer.effectAllowed = "move";
    setFocusedTreeItem(node.path, node.kind);
  });
  el.addEventListener("dragend", () => clearDropTargets());

  el.addEventListener("contextmenu", (e) => {
    e.preventDefault();
    e.stopPropagation();
    setFocusedTreeItem(node.path, node.kind);
    showTreeContextMenu(e.clientX, e.clientY, node);
  });

  if (node.kind === "directory") {
    setupDirectoryDropTarget(el, node.path);
  }
}

function handlePathDeleted(path) {
  if (currentFilePath === path || (currentFilePath && currentFilePath.startsWith(`${path}/`))) {
    currentFilePath = null;
    editorDirty = false;
    const monaco = window.monaco;
    if (editor && monaco) {
      const model = editor.getModel();
      if (model) model.dispose();
      editor.setModel(monaco.editor.createModel("", "plaintext"));
      setEditorReadOnly(true);
    }
    updateEditorChrome();
  }
  if (selectedDirPath === path || selectedDirPath.startsWith(`${path}/`)) {
    selectedDirPath = parentDir(path);
  }
  for (const expanded of [...expandedDirs]) {
    if (expanded === path || expanded.startsWith(`${path}/`)) expandedDirs.delete(expanded);
  }
  saveExpandedDirs();
  if (
    focusedTreeItem &&
    (focusedTreeItem.path === path || focusedTreeItem.path.startsWith(`${path}/`))
  ) {
    setFocusedTreeItem(null, null);
  }
}

function handlePathMoved(source, dest, kind) {
  if (currentFilePath === source) {
    currentFilePath = dest;
    updateEditorChrome();
  } else if (currentFilePath?.startsWith(`${source}/`)) {
    currentFilePath = dest + currentFilePath.slice(source.length);
    updateEditorChrome();
  }
  if (selectedDirPath === source || selectedDirPath.startsWith(`${source}/`)) {
    selectedDirPath = dest + selectedDirPath.slice(source.length);
  } else if (selectedDirPath === parentDir(source) && kind === "directory" && dest === selectedDirPath) {
    selectDirectory(dest);
  }
  const nextExpanded = new Set();
  for (const expanded of expandedDirs) {
    if (expanded === source || expanded.startsWith(`${source}/`)) {
      nextExpanded.add(dest + expanded.slice(source.length));
    } else {
      nextExpanded.add(expanded);
    }
  }
  expandedDirs.clear();
  for (const expanded of nextExpanded) expandedDirs.add(expanded);
  saveExpandedDirs();
  expandPathAncestors(dest);
  setFocusedTreeItem(dest, kind);
  if (kind === "directory") selectDirectory(dest);
}

async function readApiError(res) {
  const text = await res.text();
  try {
    const data = JSON.parse(text);
    if (typeof data.detail === "string" && data.detail) return data.detail;
  } catch {
    /* plain text */
  }
  return text || res.statusText || "Unknown error";
}

function openDeleteDialog(path, kind) {
  if (!els.deleteDialog || !path) return;
  deletePending = { path, kind };
  const label = kind === "directory" ? "Папка" : "Файл";
  els.deleteTargetLabel.textContent = `${label}: /${path}`;
  els.deleteDialog.showModal();
}

function closeDeleteDialog() {
  els.deleteDialog?.close();
  deletePending = null;
}

function treeSelectionFocused() {
  const active = document.activeElement;
  if (!active) return false;
  if (active === els.fileTree || els.fileTree?.contains(active)) return true;
  if (active === els.deleteItemBtn) return true;
  return Boolean(els.filesPanel?.contains(active) && !active.closest?.(".monaco-editor"));
}

function isDeleteShortcut(e) {
  if (!focusedTreeItem?.path) return false;
  if (els.deleteDialog?.open || els.moveDialog?.open || els.newFileDialog?.open || els.newFolderDialog?.open) {
    return false;
  }
  if (e.key === "Delete") return true;
  if (e.key === "Backspace" && treeSelectionFocused()) return true;
  return false;
}

async function executeDelete(path, kind) {
  const res = await fetch(apiUrl("/studio/api/files/delete"), {
    method: "POST",
    headers: apiJsonHeaders(),
    body: JSON.stringify({ path }),
  });
  if (!res.ok) {
    const err = await readApiError(res);
    appendChat(`Удаление не удалось: ${err}`, "error");
    if (res.status === 404) await refreshTree().catch(() => {});
    return false;
  }
  handlePathDeleted(path);
  setFocusedTreeItem(null, null);
  await refreshTree();
  appendChat(`Удалено: ${path}`, "tool");
  return true;
}

async function moveTreePath(source, destination, into = false) {
  const res = await fetch(apiUrl("/studio/api/files/move"), {
    method: "POST",
    headers: apiJsonHeaders(),
    body: JSON.stringify({ source, destination, into }),
  });
  if (!res.ok) {
    const err = await readApiError(res);
    appendChat(`Перемещение не удалось: ${err}`, "error");
    if (res.status === 404) await refreshTree().catch(() => {});
    return null;
  }
  const data = await res.json();
  handlePathMoved(source, data.path, data.kind);
  await refreshTree();
  if (data.kind === "file") {
    const fileEl = els.fileTree.querySelector(
      `.tree-file[data-path="${CSS.escape(data.path)}"]`,
    );
    if (fileEl) fileEl.classList.add("active");
  }
  appendChat(`Moved to ${data.path}`, "tool");
  return data;
}

function openMoveDialog(sourcePath) {
  if (!els.moveDialog) return;
  moveSourcePath = sourcePath;
  els.moveSourceLabel.textContent = `Из: /${sourcePath}`;
  const base = sourcePath.includes("/") ? sourcePath.slice(sourcePath.lastIndexOf("/") + 1) : sourcePath;
  const destDir = parentDir(sourcePath);
  els.moveDestination.value = destDir ? `${destDir}/${base}` : base;
  if (els.moveIntoDir) els.moveIntoDir.checked = false;
  els.moveDialog.showModal();
  requestAnimationFrame(() => {
    els.moveDestination.focus();
    els.moveDestination.select();
  });
}

function closeMoveDialog() {
  els.moveDialog?.close();
  moveSourcePath = null;
}

function initTreeFileOps() {
  document.addEventListener("mousedown", (e) => {
    if (!els.treeContextMenu?.contains(e.target)) hideTreeContextMenu();
  });
  document.addEventListener(
    "keydown",
    (e) => {
      if (!isDeleteShortcut(e)) return;
      if (document.activeElement === els.chatInput) return;
      e.preventDefault();
      e.stopPropagation();
      openDeleteDialog(focusedTreeItem.path, focusedTreeItem.kind);
    },
    true,
  );

  els.deleteItemBtn?.addEventListener("click", () => {
    if (!focusedTreeItem?.path) return;
    openDeleteDialog(focusedTreeItem.path, focusedTreeItem.kind);
  });
  els.fileTree?.addEventListener("click", () => els.fileTree.focus());

  els.selectedDir?.addEventListener("dragover", (e) => {
    if (!e.dataTransfer?.types?.includes("text/x-holix-path")) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
    els.selectedDir.classList.add("drop-target");
  });
  els.selectedDir?.addEventListener("dragleave", () => {
    els.selectedDir.classList.remove("drop-target");
  });
  els.selectedDir?.addEventListener("drop", async (e) => {
    e.preventDefault();
    els.selectedDir.classList.remove("drop-target");
    const source = e.dataTransfer.getData("text/x-holix-path");
    const kind = e.dataTransfer.getData("text/x-holix-kind");
    if (!source || !canMoveInto(source, "", kind)) return;
    await moveTreePath(source, "", true);
  });
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
    label.title = node.path;
    label.addEventListener("click", () => {
      setFocusedTreeItem(node.path, "directory");
      selectDirectory(node.path);
      els.fileTree?.focus();
    });
    attachTreeItem(label, node);

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
    file.title = node.path;
    file.addEventListener("click", () => {
      setFocusedTreeItem(node.path, "file");
      openFile(node.path, file);
      els.fileTree?.focus();
    });
    attachTreeItem(file, node);

    row.appendChild(spacer);
    row.appendChild(file);
    wrap.appendChild(row);
  }
  return wrap;
}

async function refreshTree() {
  const res = await fetch(apiUrl("/studio/api/files/tree?depth=8"), { headers: authHeaders() });
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
els.deleteCancel?.addEventListener("click", () => closeDeleteDialog());
els.deleteForm?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const pending = deletePending;
  closeDeleteDialog();
  if (!pending?.path) return;
  await executeDelete(pending.path, pending.kind);
});
els.moveCancel?.addEventListener("click", () => closeMoveDialog());
els.moveForm?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const source = moveSourcePath;
  const destination = (els.moveDestination?.value || "").trim().replace(/\/+$/, "");
  const into = Boolean(els.moveIntoDir?.checked);
  closeMoveDialog();
  if (!source) return;
  await moveTreePath(source, destination, into);
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
    case "connected": {
      const mode = msg.workspace_mode === "profile" ? "workspace" : "cwd";
      els.profile.textContent = msg.workspace_root
        ? `profile: ${msg.profile} · ${mode}: ${msg.workspace_root}`
        : `profile: ${msg.profile}`;
      break;
    }
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
  initTreeFileOps();
  updateTreeSelectionChrome();
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