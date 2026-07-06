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
  editorTitle: document.getElementById("editor-title"),
  editorHost: document.getElementById("editor"),
  diffHost: document.getElementById("diff-editor"),
  diffToggle: document.getElementById("diff-toggle"),
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

function renderTree(nodes, container) {
  container.innerHTML = "";
  const root = document.createElement("div");
  for (const node of nodes || []) {
    root.appendChild(renderNode(node));
  }
  container.appendChild(root);
}

function renderNode(node) {
  const wrap = document.createElement("div");
  if (node.kind === "directory") {
    const label = document.createElement("div");
    label.className = "tree-item tree-dir";
    label.textContent = `📁 ${node.name}`;
    wrap.appendChild(label);
    if (node.children?.length) {
      const kids = document.createElement("div");
      kids.className = "tree-children";
      for (const child of node.children) kids.appendChild(renderNode(child));
      wrap.appendChild(kids);
    }
  } else {
    const file = document.createElement("div");
    file.className = "tree-item tree-file";
    file.textContent = node.name;
    file.dataset.path = node.path;
    file.addEventListener("click", () => openFile(node.path, file));
    wrap.appendChild(file);
  }
  return wrap;
}

async function refreshTree() {
  const res = await fetch(apiUrl("/studio/api/files/tree"), { headers: authHeaders() });
  if (!res.ok) throw new Error(await res.text());
  const data = await res.json();
  renderTree(data.children, els.fileTree);
}

async function openFile(path, el) {
  document.querySelectorAll(".tree-file.active").forEach((n) => n.classList.remove("active"));
  if (el) el.classList.add("active");
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
  els.editorTitle.textContent = data.path;
  const model = editor.getModel();
  if (model) model.dispose();
  editor.setModel(
    monaco.editor.createModel(data.content, data.language || "plaintext"),
  );
}

function showEditor() {
  els.editorHost.classList.remove("hidden");
  els.diffHost.classList.add("hidden");
  els.diffToggle.classList.add("hidden");
}

async function showDiff(diff) {
  pendingDiff = diff;
  const monaco = await loadMonaco();
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
      els.profile.textContent = `profile: ${msg.profile}`;
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
  try {
    await initEditor();
    await refreshTree();
    connectWs();
  } catch (err) {
    setStatus("init failed", false);
    appendChat(String(err), "error");
  }
}

boot();