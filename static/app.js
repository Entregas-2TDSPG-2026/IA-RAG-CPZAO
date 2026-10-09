const storageKey = "da-rag-session-v1";
const messages = document.querySelector("#messages");
const welcome = document.querySelector("#welcome");
const form = document.querySelector("#chat-form");
const input = document.querySelector("#message");
const send = document.querySelector("#send");
const isEmbed = new URLSearchParams(location.search).get("embed") === "1";
if (isEmbed) document.body.classList.add("embed");

let session = { conversation_id: null, turns: [] };
let busy = false;
try {
  const saved = JSON.parse(sessionStorage.getItem(storageKey) || "null");
  if (saved && Array.isArray(saved.turns)) session = saved;
} catch { /* Sessão inválida: inicia uma conversa limpa. */ }

function save() {
  sessionStorage.setItem(storageKey, JSON.stringify(session));
}

function scrollBottom() {
  messages.scrollTop = messages.scrollHeight;
}

function renderTurn(turn) {
  welcome.hidden = true;
  const row = document.createElement("div");
  row.className = `message-row ${turn.role}`;
  if (turn.role === "assistant") {
    const icon = document.createElement("div");
    icon.className = "message-icon";
    icon.setAttribute("aria-hidden", "true");
    icon.textContent = "✦";
    row.append(icon);
  }
  const body = document.createElement("div");
  body.className = "message-body";
  const label = document.createElement("div");
  label.className = "message-label";
  label.textContent = turn.role === "user" ? "Você" : "Assistente";
  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.textContent = turn.content;
  body.append(label, bubble);
  if (turn.role === "assistant" && Array.isArray(turn.sources) && turn.sources.length) {
    const sources = document.createElement("div");
    sources.className = "sources";
    for (const source of turn.sources) {
      const link = document.createElement("a");
      link.href = source.url;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.textContent = `[${source.number}] ${source.title}${source.section && source.section !== source.title ? ` · ${source.section}` : ""} ↗`;
      sources.append(link);
    }
    body.append(sources);
  }
  row.append(body);
  messages.append(row);
  scrollBottom();
}

for (const turn of session.turns) renderTurn(turn);

function setBusy(value) {
  busy = value;
  input.disabled = value;
  send.disabled = value;
}

function showTyping() {
  const row = document.createElement("div");
  row.className = "message-row typing-row";
  row.innerHTML = '<div class="message-icon" aria-hidden="true">✦</div><div class="typing" aria-label="Preparando resposta"><span></span><span></span><span></span></div>';
  messages.append(row);
  scrollBottom();
  return row;
}

async function ask(question) {
  const message = question.trim();
  if (!message || busy) return;
  const history = session.turns.slice(-12).map(({ role, content }) => ({ role, content }));
  const userTurn = { role: "user", content: message };
  session.turns.push(userTurn);
  renderTurn(userTurn);
  save();
  input.value = "";
  input.style.height = "auto";
  setBusy(true);
  const typing = showTyping();
  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, conversation_id: session.conversation_id, history }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Não foi possível consultar o assistente.");
    session.conversation_id = data.conversation_id;
    const assistantTurn = { role: "assistant", content: data.answer, sources: data.sources || [] };
    session.turns.push(assistantTurn);
    typing.remove();
    renderTurn(assistantTurn);
    save();
  } catch (error) {
    typing.remove();
    renderTurn({ role: "assistant", content: error.message || "Falha de conexão. Tente novamente." });
  } finally {
    setBusy(false);
    input.focus();
  }
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  ask(input.value);
});
input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    form.requestSubmit();
  }
});
input.addEventListener("input", () => {
  input.style.height = "auto";
  input.style.height = `${Math.min(input.scrollHeight, 145)}px`;
});
document.querySelectorAll("[data-question]").forEach((button) => {
  button.addEventListener("click", () => ask(button.dataset.question));
});
document.querySelector("#new-chat").addEventListener("click", () => {
  if (busy) return;
  session = { conversation_id: null, turns: [] };
  sessionStorage.removeItem(storageKey);
  messages.querySelectorAll(".message-row").forEach((row) => row.remove());
  welcome.hidden = false;
  input.focus();
});

fetch("/api/health").then(async (response) => {
  if (!response.ok) throw new Error();
  const data = await response.json();
  document.querySelector("#index-status").textContent = `Base pronta · ${data.pages} páginas da disciplina`;
}).catch(() => {
  document.querySelector("#index-status").textContent = "Base temporariamente indisponível";
  document.querySelector(".status-dot").classList.add("offline");
});
