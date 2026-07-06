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
  uploadBtn: document.getElementById("upload-btn"),
  fileUpload: document.getElementById("file-upload"),
  editorTitle: document.getElementById("editor-title"),
  editorHost: document.getElementById("editor"),
  diffHost: document.getElementById("diff-editor"),
  diffToggle: document.getElementById("diff-toggle"),
  saveBtn: document.getElementById("save-btn"),
  chatLog: document.getElementById("chat-log"),
  chatForm: document.getElementById("chat-form"),
  chatInput: document.getElementById("chat-input"),
  stopBtn: document.getElementById("stop-btn"),
};

let monacoReady = null;
let editor = null;
let diffEditor = null;
let ws = null;
let streamBuffer = "";
let pendingDiff = null;
let runActive = false;

let currentFilePath = null;
let editorDirty = false;
let selectedDirPath = "";
let expandedDirs = loadExpandedDirs();
let treeNodes = [];

function loadExpandedDirs() {
  try {
    const raw = sessionStorage.getItem("holix_studio_expanded_dirs");
    return new Set(raw ? JSON.parse(raw) : []);
  } catch {
    return new Set();
  }
}

function saveExpandedDirs() {
  sessionStorage.setItem(
    "holix_studio_expanded_dirs",
    JSON.stringify([...expandedDirs]),
  );
}

function loadMonaco() {
  if (monacoReady) return monacoReady;
  monacoReady = new Promise((resolve) => {
    require.config({
      paths: { vs: "https://cdn.jsdelivr.net/npm/monaco-editor@0.52.2/min/vs" },
    });
    require(["vs/editor/editor.main"], () => resolve(window.monaco));
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
  });
  editor.onDidChangeModelContent(() => {
    if (currentFilePath && !editor.getOption(monaco.editor.EditorOption.readOnly)) {
      editorDirty = true;
      updateEditorChrome();
    }
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

function appendChat(text, cls) {
  const div = document.createElement("div");
  div.className = `msg ${cls}`;
  div.textContent = text;
  els.chatLog.appendChild(div);
  els.chatLog.scrollTop = els.chatLog.scrollHeight;
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

function seedExpandedDirs(nodes) {
  if (expandedDirs.size > 0) return;
  for (const node of nodes || []) {
    if (node.kind === "directory") expandedDirs.add(node.path);
  }
  saveExpandedDirs();
}

async function refreshTree() {
  const res = await fetch(apiUrl("/studio/api/files/tree"), { headers: authHeaders() });
  if (!res.ok) throw new Error(await res.text());
  const data = await res.json();
  seedExpandedDirs(data.children);
  renderTree(data.children, els.fileTree);
}

function updateEditorChrome() {
  if (!currentFilePath) {
    els.editorTitle.textContent = "Editor";
    els.saveBtn.classList.add("hidden");
    els.saveBtn.disabled = true;
    return;
  }
  const dirtyMark = editorDirty ? " •" : "";
  els.editorTitle.textContent = `${currentFilePath}${dirtyMark}`;
  els.saveBtn.classList.remove("hidden");
  els.saveBtn.disabled = !editorDirty;
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

async function createNewFile() {
  const name = prompt("Имя нового файла:", "untitled.txt");
  if (!name?.trim()) return;
  const path = selectedDirPath ? `${selectedDirPath}/${name.trim()}` : name.trim();
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
  await refreshTree();
  const parent = path.includes("/") ? path.slice(0, path.lastIndexOf("/")) : "";
  if (parent) expandedDirs.add(parent);
  saveExpandedDirs();
  await refreshTree();
  const fileEl = els.fileTree.querySelector(`.tree-file[data-path="${CSS.escape(data.path)}"]`);
  await openFile(data.path, fileEl);
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
  els.editorHost.classList.remove("hidden");
  els.diffHost.classList.add("hidden");
  els.diffToggle.classList.add("hidden");
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

els.newFileBtn.addEventListener("click", () => createNewFile());
els.uploadBtn.addEventListener("click", () => els.fileUpload.click());
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
      if (last && runActive) last.textContent = text;
      else appendChat(text, "thinking");
      break;
    }
    case "assistant_delta":
      if (!streamBuffer) appendChat("", "assistant");
      streamBuffer += msg.content || "";
      {
        const last = els.chatLog.querySelector(".msg.assistant:last-child");
        if (last) last.textContent = streamBuffer;
      }
      break;
    case "final_response":
      setRunActive(false);
      streamBuffer = "";
      if (msg.content) {
        const last = els.chatLog.querySelector(".msg.assistant:last-child");
        if (last) last.textContent = msg.content;
        else appendChat(msg.content, "assistant");
      }
      refreshTree().catch(() => {});
      break;
    case "tool_call_start":
      appendChat(`▶ ${msg.tool_name}`, "tool");
      break;
    case "tool_call_result":
      if (msg.file_diff) showDiff(msg.file_diff);
      break;
    case "error":
      setRunActive(false);
      appendChat(msg.message || msg.error || "Error", "error");
      streamBuffer = "";
      break;
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