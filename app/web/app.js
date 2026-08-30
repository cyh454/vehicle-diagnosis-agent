/* ═══════════════════════════════════════════════
   车载故障诊断助手 — 前端逻辑
   纯原生 JS，无外部依赖
   ═══════════════════════════════════════════════ */
"use strict";

const API = "/api/v1/diagnosis";
const USER_ID = "web";

/* ── 工具中文名映射 ── */
const TOOL_NAMES = {
  query_fault_code: "故障码查询",
  search_knowledge_base: "知识库检索",
  search_similar_cases: "相似维修案例",
  get_vehicle_info: "车辆档案",
  query_parts_info: "配件信息",
  record_diagnosis_result: "诊断记录归档",
};

/* ── 全局状态 ── */
const state = {
  sessionId: null,
  busy: false,
  sessions: [],
};

/* ── DOM 引用 ── */
const $ = (id) => document.getElementById(id);
const messagesEl = $("messages");
const inputEl = $("input");
const sendBtn = $("sendBtn");
const sessionListEl = $("sessionList");
const sessionEmptyEl = $("sessionEmpty");
const chatTitleEl = $("chatTitle");
const vehicleChipEl = $("vehicleChip");
const vehicleTextEl = $("vehicleText");
const statusDotEl = $("statusDot");
const statusTextEl = $("statusText");

/* ═══════════════ Markdown 渲染（安全：先转义再解析） ═══════════════ */

function escapeHtml(s) {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function inlineMd(s) {
  return s
    .replace(/`([^`\n]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>")
    .replace(/\[([^\]\n]+)\]\((https?:\/\/[^)\s]+)\)/g,
      '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
}

/** 将 Markdown 文本渲染为 HTML（支持标题/列表/表格/代码块/引用等） */
function md(src) {
  if (!src) return "";
  const codes = [];
  // 1. 摘出围栏代码块
  src = src.replace(/```(\w*)[ \t]*\r?\n?([\s\S]*?)```/g, (_, lang, code) => {
    codes.push(`<pre><code>${escapeHtml(code.replace(/\n$/, ""))}</code></pre>`);
    return `\u0000C${codes.length - 1}\u0000`;
  });

  // 2. 转义剩余 HTML
  src = escapeHtml(src.replace(/\r\n/g, "\n"));

  // 3. 逐行解析块级结构
  const lines = src.split("\n");
  const out = [];
  let i = 0;
  const flushPara = (buf) => {
    if (buf.length) out.push(`<p>${buf.map(inlineMd).join("<br>")}</p>`);
    buf.length = 0;
  };
  const para = [];

  while (i < lines.length) {
    const line = lines[i];
    const trimmed = line.trim();

    // 代码块占位符（整行）
    const ph = trimmed.match(/^\u0000C(\d+)\u0000$/);
    if (ph) { flushPara(para); out.push(codes[+ph[1]]); i++; continue; }

    if (!trimmed) { flushPara(para); i++; continue; }

    // 标题
    const h = trimmed.match(/^(#{1,6})\s+(.+)$/);
    if (h) {
      flushPara(para);
      const level = Math.min(h[1].length, 4);
      out.push(`<h${level}>${inlineMd(h[2])}</h${level}>`);
      i++; continue;
    }

    // 水平线
    if (/^(-{3,}|\*{3,})$/.test(trimmed)) { flushPara(para); out.push("<hr>"); i++; continue; }

    // 引用
    if (trimmed.startsWith("&gt;")) {
      flushPara(para);
      const quote = [];
      while (i < lines.length && lines[i].trim().startsWith("&gt;")) {
        quote.push(lines[i].trim().replace(/^&gt;\s?/, ""));
        i++;
      }
      out.push(`<blockquote>${quote.map(inlineMd).join("<br>")}</blockquote>`);
      continue;
    }

    // 表格（当前行含 | 且下一行是分隔行）
    if (trimmed.includes("|") && i + 1 < lines.length &&
        /^\s*\|?[\s:|-]+\|[\s:|-]*$/.test(lines[i + 1])) {
      flushPara(para);
      const parseRow = (row) =>
        row.trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim());
      const head = parseRow(trimmed);
      i += 2;
      const body = [];
      while (i < lines.length && lines[i].includes("|") && lines[i].trim()) {
        body.push(parseRow(lines[i]));
        i++;
      }
      const th = head.map((c) => `<th>${inlineMd(c)}</th>`).join("");
      const trs = body.map((r) =>
        `<tr>${r.map((c) => `<td>${inlineMd(c)}</td>`).join("")}</tr>`).join("");
      out.push(`<table><thead><tr>${th}</tr></thead><tbody>${trs}</tbody></table>`);
      continue;
    }

    // 无序 / 有序列表
    const ulMatch = trimmed.match(/^[-*•]\s+(.+)$/);
    const olMatch = trimmed.match(/^(\d+)[.、]\s+(.+)$/);
    if (ulMatch || olMatch) {
      flushPara(para);
      const ordered = Boolean(olMatch);
      const tag = ordered ? "ol" : "ul";
      const items = [];
      const re = ordered ? /^\d+[.、]\s+/ : /^[-*•]\s+/;
      while (i < lines.length) {
        const t = lines[i].trim();
        if (re.test(t)) {
          items.push(`<li>${inlineMd(t.replace(re, ""))}</li>`);
          i++;
        } else if (t && items.length && !/^(#{1,6}\s|\u0000C\d+\u0000$|[-*•]\s|\d+[.、]\s)/.test(t)) {
          // 续行并入上一项
          items[items.length - 1] = items[items.length - 1].replace(
            /<\/li>$/, `<br>${inlineMd(t)}</li>`);
          i++;
        } else break;
      }
      out.push(`<${tag}>${items.join("")}</${tag}>`);
      continue;
    }

    // 普通段落
    para.push(trimmed);
    i++;
  }
  flushPara(para);

  // 4. 还原代码块
  return out.join("\n").replace(/\u0000C(\d+)\u0000/g, (_, n) => codes[+n]);
}

/* ═══════════════ 通用工具 ═══════════════ */

function formatTime(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const now = new Date();
  const hm = `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
  const sameDay = d.toDateString() === now.toDateString();
  if (sameDay) return hm;
  return `${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")} ${hm}`;
}

function fmtLatency(ms) {
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${ms}ms`;
}

function scrollToBottom() {
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

async function api(path, options = {}) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 190000);
  try {
    const res = await fetch(path, { ...options, signal: ctrl.signal });
    if (!res.ok) {
      let detail = `HTTP ${res.status}`;
      try { detail = (await res.json()).detail || detail; } catch { /* ignore */ }
      throw new Error(detail);
    }
    return await res.json();
  } finally {
    clearTimeout(timer);
  }
}

/* ═══════════════ 消息渲染 ═══════════════ */

const AI_AVATAR = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2 3 7v10l9 5 9-5V7z"/><path d="m9 12 2 2 4-4"/></svg>`;

function buildToolCallsCard(toolCalls) {
  if (!toolCalls || !toolCalls.length) return null;
  const names = toolCalls.map((t) => TOOL_NAMES[t.tool] || t.tool);
  const items = toolCalls.map((t) => {
    const input = typeof t.input === "string" ? t.input : JSON.stringify(t.input ?? {}, null, 2);
    return `
      <div class="tool-item">
        <div class="t-head">${TOOL_NAMES[t.tool] || t.tool}
          <span class="t-badge">${escapeHtml(t.tool)}</span>
        </div>
        <div class="t-block"><div class="t-label">输入</div><pre>${escapeHtml(input || "—")}</pre></div>
        ${t.output ? `<div class="t-block"><div class="t-label">输出</div><pre>${escapeHtml(t.output)}</pre></div>` : ""}
      </div>`;
  }).join("");
  const details = document.createElement("details");
  details.className = "tools-card";
  details.innerHTML = `
    <summary>
      <svg class="wrench" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/></svg>
      诊断过程 · 调用 ${toolCalls.length} 个工具（${[...new Set(names)].join("、")}）
      <svg class="chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="m6 9 6 6 6-6"/></svg>
    </summary>
    ${items}`;
  return details;
}

/** 追加一条消息到聊天区，返回气泡元素 */
function appendMessage({ role, content, toolCalls = null, latencyMs = null, createdAt = null }) {
  const wrap = document.createElement("div");
  wrap.className = `msg ${role === "user" ? "user" : "ai"}`;

  const avatar = document.createElement("div");
  avatar.className = `avatar ${role === "user" ? "user" : "ai"}`;
  avatar.innerHTML = role === "user" ? "工程师" : AI_AVATAR;

  const body = document.createElement("div");
  body.className = "msg-body";

  const bubble = document.createElement("div");
  bubble.className = "bubble" + (content === "__ERROR__" ? " error-bubble" : "");
  bubble.innerHTML = content === "__ERROR__"
    ? "⚠️ 请求失败，诊断服务暂不可用。请检查后端服务、数据库与 LLM 配置后重试。"
    : md(content);
  body.appendChild(bubble);

  if (role === "assistant" && toolCalls && toolCalls.length) {
    body.appendChild(buildToolCallsCard(toolCalls));
  }

  const bits = [];
  if (role === "assistant" && latencyMs) {
    bits.push(`<span class="latency">⚡ ${fmtLatency(latencyMs)}</span>`);
  }
  if (createdAt) bits.push(`<span>${formatTime(createdAt)}</span>`);
  if (bits.length) {
    const meta = document.createElement("div");
    meta.className = "msg-meta";
    meta.innerHTML = bits.join("");
    body.appendChild(meta);
  }

  wrap.appendChild(avatar);
  wrap.appendChild(body);
  messagesEl.appendChild(wrap);
  scrollToBottom();
  return wrap;
}

function showTyping() {
  const wrap = document.createElement("div");
  wrap.className = "msg ai";
  wrap.id = "typingRow";
  wrap.innerHTML = `
    <div class="avatar ai">${AI_AVATAR}</div>
    <div class="msg-body">
      <div class="bubble"><span class="typing"><i></i><i></i><i></i></span></div>
    </div>`;
  messagesEl.appendChild(wrap);
  scrollToBottom();
}

function removeTyping() {
  document.getElementById("typingRow")?.remove();
}

function showWelcome() {
  const suggestions = [
    { icon: "🔋", title: "12V 蓄电池亏电", desc: "车辆停放一晚后无法上电，如何排查低压蓄电池亏电？" },
    { icon: "⚠️", title: "故障码解读", desc: "P0562 这个故障码是什么意思？可能的原因和诊断步骤有哪些？" },
    { icon: "🔌", title: "充电故障", desc: "车载充电机（OBC）交流充电慢，指示灯闪烁，帮我分析原因。" },
    { icon: "🛡️", title: "绝缘故障", desc: "仪表提示动力电池绝缘阻值偏低，请给出完整的排查流程。" },
  ];
  messagesEl.innerHTML = `
    <div class="welcome">
      <div class="welcome-icon">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
          <path d="M5 17h14M6.5 17a1.8 1.8 0 1 1-3.6 0 1.8 1.8 0 0 1 3.6 0zM21.1 17a1.8 1.8 0 1 1-3.6 0 1.8 1.8 0 0 1 3.6 0z"/>
          <path d="M4 17v-4.2c0-.6.2-1.2.5-1.7L7 6.5C7.4 5.6 8.3 5 9.3 5h5.4c1 0 1.9.6 2.3 1.5l2.5 4.6c.3.5.5 1.1.5 1.7V17"/>
          <path d="M4.6 11h14.8"/><path d="M13.5 7.5 11 11h2.5l-1.8 3.5"/>
        </svg>
      </div>
      <h3>车载故障诊断助手</h3>
      <p>融合维修知识库、OBD 故障码字典、历史维修案例与车辆档案。<br>
         直接描述故障现象即可开始，系统会自动识别并绑定车辆。</p>
      <div class="suggestions">
        ${suggestions.map((s, i) => `
          <button class="suggestion" data-i="${i}">
            <div class="sg-icon">${s.icon}</div>
            <div class="sg-title">${s.title}</div>
            <div class="sg-desc">${s.desc}</div>
          </button>`).join("")}
      </div>
    </div>`;
  messagesEl.querySelectorAll(".suggestion").forEach((btn) => {
    btn.addEventListener("click", () => {
      inputEl.value = suggestions[+btn.dataset.i].desc;
      inputEl.focus();
      autoResize();
      updateSendState();
      sendMessage();
    });
  });
}

function setVehicle(vehicle) {
  if (!vehicle) { vehicleChipEl.classList.add("hidden"); return; }
  const parts = [vehicle.brand, vehicle.model];
  if (vehicle.year) parts.push(`${vehicle.year}款`);
  if (vehicle.power_type) parts.push(vehicle.power_type);
  vehicleTextEl.textContent = parts.join(" · ") + (vehicle.vin ? ` · VIN ${vehicle.vin}` : "");
  vehicleChipEl.classList.remove("hidden");
}

/* ═══════════════ 会话列表 ═══════════════ */

function renderSessionList() {
  if (!state.sessions.length) {
    sessionListEl.innerHTML = `<div class="session-empty">暂无历史会话</div>`;
    return;
  }
  sessionListEl.innerHTML = state.sessions.map((s) => {
    const title = s.title || "未命名会话";
    const vehicle = s.vehicle ? `${s.vehicle.brand} ${s.vehicle.model}` : "";
    return `
      <div class="session-item ${s.session_id === state.sessionId ? "active" : ""}" data-id="${s.session_id}">
        <div class="s-title">${escapeHtml(title)}</div>
        <div class="s-meta">
          <span>${formatTime(s.updated_at)}</span>
          <span class="dot"></span>
          <span>${s.message_count} 条消息</span>
          ${vehicle ? `<span class="dot"></span><span class="s-vehicle">🚗 ${escapeHtml(vehicle)}</span>` : ""}
        </div>
      </div>`;
  }).join("");
  sessionListEl.querySelectorAll(".session-item").forEach((el) => {
    el.addEventListener("click", () => {
      loadSession(el.dataset.id);
      closeSidebar();
    });
  });
}

async function refreshSessions() {
  try {
    state.sessions = await api(`${API}/sessions?limit=50`);
    renderSessionList();
  } catch { /* 静默失败 */ }
}

async function loadSession(id) {
  if (state.busy) return;
  try {
    const detail = await api(`${API}/sessions/${id}`);
    state.sessionId = id;
    localStorage.setItem("vda-session", id);
    messagesEl.innerHTML = "";
    detail.messages.forEach((m) =>
      appendMessage({
        role: m.role, content: m.content, toolCalls: m.tool_calls,
        latencyMs: m.latency_ms, createdAt: m.created_at,
      }));
    if (!detail.messages.length) showWelcome();
    chatTitleEl.textContent = detail.title || "诊断会话";
    setVehicle(detail.vehicle);
    renderSessionList();
    scrollToBottom();
  } catch {
    // 会话可能已被删除
    localStorage.removeItem("vda-session");
    newSession();
  }
}

function newSession() {
  state.sessionId = null;
  localStorage.removeItem("vda-session");
  chatTitleEl.textContent = "新的诊断会话";
  setVehicle(null);
  showWelcome();
  renderSessionList();
  inputEl.focus();
  closeSidebar();
}

/* ═══════════════ 发送消息 ═══════════════ */

function updateSendState() {
  sendBtn.disabled = state.busy || !inputEl.value.trim();
}

async function sendMessage() {
  const text = inputEl.value.trim();
  if (!text || state.busy) return;

  // 用户气泡
  if (messagesEl.querySelector(".welcome")) messagesEl.innerHTML = "";
  appendMessage({ role: "user", content: text, createdAt: new Date().toISOString() });
  inputEl.value = "";
  autoResize();
  updateSendState();

  state.busy = true;
  sendBtn.disabled = true;
  sendBtn.classList.add("loading");
  showTyping();

  try {
    const res = await api(`${API}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text, session_id: state.sessionId, user_id: USER_ID }),
    });
    removeTyping();
    state.sessionId = res.session_id;
    localStorage.setItem("vda-session", res.session_id);
    appendMessage({
      role: "assistant", content: res.reply,
      toolCalls: res.tool_calls, latencyMs: res.latency_ms,
      createdAt: new Date().toISOString(),
    });
    setVehicle(res.vehicle);
    chatTitleEl.textContent = res.reply ? text.slice(0, 24) : chatTitleEl.textContent;
    refreshSessions();
  } catch (e) {
    removeTyping();
    appendMessage({ role: "assistant", content: "__ERROR__" });
    console.error(e);
  } finally {
    state.busy = false;
    sendBtn.classList.remove("loading");
    updateSendState();
    inputEl.focus();
    scrollToBottom();
  }
}

/* ═══════════════ 健康检查轮询 ═══════════════ */

async function checkHealth() {
  try {
    const res = await fetch("/health");
    const data = await res.json();
    const ok = data.status === "healthy";
    statusDotEl.className = `status-dot ${ok ? "ok" : "bad"}`;
    statusTextEl.textContent = ok
      ? "系统在线 · 数据库 & 向量检索正常"
      : "服务降级 · " + Object.entries(data.checks || {})
          .filter(([, v]) => !String(v).startsWith("ok"))
          .map(([k]) => k).join("/") + " 异常";
  } catch {
    statusDotEl.className = "status-dot bad";
    statusTextEl.textContent = "无法连接后端服务";
  }
}

/* ═══════════════ 主题 ═══════════════ */

function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  $("iconMoon").style.display = theme === "dark" ? "" : "none";
  $("iconSun").style.display = theme === "dark" ? "none" : "";
  localStorage.setItem("vda-theme", theme);
}

/* ═══════════════ 移动端侧栏 ═══════════════ */

function closeSidebar() {
  $("sidebar").classList.remove("open");
  $("backdrop").classList.remove("show");
}

/* ═══════════════ 输入框 ═══════════════ */

function autoResize() {
  inputEl.style.height = "auto";
  inputEl.style.height = Math.min(inputEl.scrollHeight, 168) + "px";
}

/* ═══════════════ 初始化 ═══════════════ */

function init() {
  applyTheme(localStorage.getItem("vda-theme") || "light");

  $("newChatBtn").addEventListener("click", newSession);
  $("themeToggle").addEventListener("click", () =>
    applyTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark"));
  $("menuBtn").addEventListener("click", () => {
    $("sidebar").classList.add("open");
    $("backdrop").classList.add("show");
  });
  $("backdrop").addEventListener("click", closeSidebar);

  sendBtn.addEventListener("click", sendMessage);
  inputEl.addEventListener("input", () => { autoResize(); updateSendState(); });
  inputEl.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
      e.preventDefault();
      sendMessage();
    }
  });

  checkHealth();
  setInterval(checkHealth, 20000);
  refreshSessions();

  // 恢复上次会话
  const saved = localStorage.getItem("vda-session");
  if (saved) {
    loadSession(saved);
  } else {
    showWelcome();
  }
  inputEl.focus();
}

init();
