const API_ROOT = "http://127.0.0.1:8000/api/db";
const SESSION_KEY = "engwords_focus_sessions_v4";
const params = new URLSearchParams(window.location.search);
let currentUnit = params.get("unit") || "";

const detailMeta = document.getElementById("detailMeta");
const pendingRatingTag = document.getElementById("pendingRatingTag");
const actionStatus = document.getElementById("actionStatus");
const detailQueueBadge = document.getElementById("detailQueueBadge");
const detailUnitBadge = document.getElementById("detailUnitBadge");
const detailWord = document.getElementById("detailWord");
const detailPhonetic = document.getElementById("detailPhonetic");
const detailDefinitionBlock = document.getElementById("detailDefinitionBlock");
const detailDefaultExampleBlock = document.getElementById("detailDefaultExampleBlock");
const detailTatoebaBlock = document.getElementById("detailTatoebaBlock");
const detailAiBlock = document.getElementById("detailAiBlock");
const detailCustomExamplesBlock = document.getElementById("detailCustomExamplesBlock");
const detailNotesBlock = document.getElementById("detailNotesBlock");
const detailSpeakBtn = document.getElementById("detailSpeakBtn");
const prevBtn = document.getElementById("prevBtn");
const wrongBtn = document.getElementById("wrongBtn");
const nextBtn = document.getElementById("nextBtn");
const backToFocusLink = document.getElementById("backToFocusLink");

const ratingLabel = {
  1: "忘记",
  2: "困难",
  3: "良好",
  4: "容易",
};

let session = null;
let busy = false;
let viewCard = null;
let viewingHistory = false;

function setActionStatus(text, isError = false) {
  actionStatus.textContent = text || "";
  actionStatus.style.color = isError ? "var(--again)" : "";
}

function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function getSessionBucketKey(scope = currentUnit ? "unit" : "global", unit = currentUnit) {
  return scope === "unit" && unit ? `unit:${unit}` : "global";
}

function getSessionStore() {
  try {
    const raw = JSON.parse(sessionStorage.getItem(SESSION_KEY) || "{}");
    return raw && typeof raw === "object" ? raw : {};
  } catch {
    return {};
  }
}

function getSession() {
  try {
    const store = getSessionStore();
    const raw = store[getSessionBucketKey()] || store.global || null;
    if (!raw || typeof raw !== "object" || !raw.current) return null;
    return {
      queue: Array.isArray(raw.queue) ? raw.queue : [],
      current: raw.current || null,
      currentUnit: raw.currentUnit || "",
      scope: raw.scope === "global" ? "global" : "unit",
      stats: raw.stats || { newRemaining: 0, reviewRemaining: 0 },
      completed: raw.completed || { newCount: 0, reviewCount: 0 },
      history: Array.isArray(raw.history) ? raw.history : [],
      pendingRating: Number(raw.pendingRating || 3),
    };
  } catch {
    return null;
  }
}

function saveSession() {
  const store = getSessionStore();
  store[getSessionBucketKey(session?.scope, session?.currentUnit || currentUnit)] = session;
  sessionStorage.setItem(SESSION_KEY, JSON.stringify(store));
}

async function fetchJson(path, options = {}) {
  const res = await fetch(`${API_ROOT}${path}`, options);
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(detail || `Request failed: ${res.status}`);
  }
  return res.json();
}

function setBusy(flag) {
  busy = flag;
  prevBtn.disabled = flag;
  wrongBtn.disabled = flag;
  nextBtn.disabled = flag;
}

function fallbackSpeak(text) {
  speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = "en-US";
  utterance.rate = 0.92;
  speechSynthesis.speak(utterance);
}

async function speak(text) {
  if (!text) return;
  try {
    const res = await fetch(`${API_ROOT}/tts?voice=nahida&word=${encodeURIComponent(text)}`);
    if (!res.ok) throw new Error(`TTS ${res.status}`);
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const audio = new Audio(url);
    await audio.play();
    audio.onended = () => URL.revokeObjectURL(url);
  } catch {
    fallbackSpeak(text);
  }
}

function setHtmlBlock(el, html) {
  if (!html) {
    el.classList.add("hidden");
    el.innerHTML = "";
    return;
  }
  el.classList.remove("hidden");
  el.innerHTML = html;
}

function getNotes(card) {
  if (Array.isArray(card.notes_v2)) return card.notes_v2;
  return [];
}

function createNoteObject(card, text = "", index = 0, links = []) {
  const safeWord = (card?.word || "word").toLowerCase().replace(/[^a-z0-9]+/g, "_");
  return {
    id: `note_${card?.unit || currentUnit}_${safeWord}_${Date.now()}_${index}`,
    text,
    links,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  };
}

function notesToLegacyText(notes) {
  return notes.map((note) => note.text || "").filter((text) => text.trim()).join("\n");
}

async function commitNotes(card, notes) {
  const cleanNotes = notes
    .map((note, index) => ({
      ...note,
      id: note.id || createNoteObject(card, note.text || "", index).id,
      text: note.text || "",
      links: Array.isArray(note.links) ? note.links : [],
      updated_at: new Date().toISOString(),
    }))
    .filter((note) => note.text.trim());

  const updated = await fetchJson("/update_note", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      unit: card.unit,
      word: card.word,
      notes: notesToLegacyText(cleanNotes),
      notes_v2: cleanNotes,
    }),
  });
  session.current = { ...session.current, ...updated };
  if (viewCard && viewCard.word === updated.word && viewCard.unit === updated.unit) {
    viewCard = { ...viewCard, ...updated };
  }
  saveSession();
  render();
}

async function updateCustomExamples(card, examples) {
  const updated = await fetchJson("/enrich_word", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      unit: card.unit,
      word: card.word,
      pos: card.pos || "",
      definitions: card.definitions || [],
      example_sentences: examples,
      chinese: card.chinese || card.translation || "",
    }),
  });
  session.current = { ...session.current, ...updated };
  if (viewCard && viewCard.word === updated.word && viewCard.unit === updated.unit) {
    viewCard = { ...viewCard, ...updated };
  }
  saveSession();
  render();
}

function renderNotes(card) {
  const notes = getNotes(card);
  const rows = notes.length ? notes.map((note) => `
    <div class="stack-row">
      <div class="info-head">
        <h3>笔记</h3>
        <div class="mini-actions">
          <button class="mini-btn" type="button" data-note-to-example="${escapeHtml(note.id)}">💬 转例句</button>
          <button class="mini-btn" type="button" data-note-delete="${escapeHtml(note.id)}">🗑 删除</button>
        </div>
      </div>
      <textarea class="note-editor" data-note-id="${escapeHtml(note.id)}">${escapeHtml(note.text || "")}</textarea>
    </div>
  `).join("") : "<p>暂无笔记。</p>";

  setHtmlBlock(detailNotesBlock, `
    <div class="info-head">
      <h3>独立笔记</h3>
      <div class="mini-actions">
        <button class="mini-btn" type="button" id="detailAddNoteBtn">＋ 新增</button>
      </div>
    </div>
    <div class="list-stack">${rows}</div>
  `);

  document.getElementById("detailAddNoteBtn")?.addEventListener("click", async () => {
    const text = prompt("输入新笔记内容：");
    if (!text || !text.trim()) return;
    await commitNotes(card, [...getNotes(card), createNoteObject(card, text.trim(), getNotes(card).length)]);
  });

  detailNotesBlock.querySelectorAll(".note-editor").forEach((textarea) => {
    textarea.addEventListener("blur", async () => {
      const nextNotes = getNotes(card).map((note) => note.id === textarea.dataset.noteId ? { ...note, text: textarea.value.trim() } : note);
      await commitNotes(card, nextNotes);
    });
  });

  detailNotesBlock.querySelectorAll("[data-note-delete]").forEach((button) => {
    button.addEventListener("click", async () => {
      const id = button.dataset.noteDelete;
      await commitNotes(card, getNotes(card).filter((note) => note.id !== id));
    });
  });

  detailNotesBlock.querySelectorAll("[data-note-to-example]").forEach((button) => {
    button.addEventListener("click", async () => {
      const id = button.dataset.noteToExample;
      const note = getNotes(card).find((item) => item.id === id);
      if (!note || !note.text.trim()) return;
      const examples = [...(session.current.example_sentences || [])];
      if (!examples.includes(note.text.trim())) examples.unshift(note.text.trim());
      await updateCustomExamples(card, examples.slice(0, 6));
      await commitNotes(session.current, getNotes(session.current).filter((item) => item.id !== id));
    });
  });
}

function renderCustomExamples(card) {
  setHtmlBlock(detailCustomExamplesBlock, "");
}

function render() {
  if (!session?.current && !session?.history?.length) {
    window.location.href = currentUnit ? `focus.html?unit=${encodeURIComponent(currentUnit)}` : "focus.html";
    return;
  }

  const card = viewCard || session.current;
  viewingHistory = !!(viewCard && session.current && viewCard.word_id !== session.current.word_id);
  const pendingRating = session.pendingRating || 3;
  currentUnit = currentUnit || session.currentUnit || "";
  backToFocusLink.href = currentUnit ? `focus.html?unit=${encodeURIComponent(currentUnit)}` : "focus.html";
  setActionStatus("");
  detailMeta.textContent = viewingHistory
    ? `历史详情 · 当前预选评分：${ratingLabel[pendingRating] || pendingRating}`
    : `详情页 · 当前预选评分：${ratingLabel[pendingRating] || pendingRating}`;
  pendingRatingTag.textContent = `预选 ${pendingRating}`;
  detailQueueBadge.textContent = card.queue_kind === "review" ? "REVIEW" : "NEW";
  detailUnitBadge.textContent = card.unit;
  detailWord.textContent = card.word;
  detailPhonetic.textContent = card.phonetic ? `/${card.phonetic}/` : "";

  setHtmlBlock(detailDefinitionBlock, `
    <div class="info-head"><h3>释义</h3></div>
    <p>${escapeHtml(card.translation || "")}</p>
  `);
  setHtmlBlock(detailDefaultExampleBlock, card.default_example ? `
    <div class="info-head">
      <h3>默认例句</h3>
      <div class="mini-actions">
        <button class="mini-btn" type="button" id="detailDefaultExampleSpeakBtn">🔊 发音</button>
      </div>
    </div>
    <p>${escapeHtml(card.default_example)}</p>
  ` : "");
  setHtmlBlock(detailTatoebaBlock, "");
  setHtmlBlock(detailAiBlock, "");
  renderCustomExamples(card);
  renderNotes(card);
  document.getElementById("detailDefaultExampleSpeakBtn")?.addEventListener("click", () => speak(card.default_example));
  prevBtn.disabled = !(session.history || []).length;
  wrongBtn.disabled = viewingHistory;
  nextBtn.disabled = false;
  nextBtn.querySelector("strong").textContent = viewingHistory ? "回到当前" : "下一个";
}

async function clearMemorizedToday(card) {
  await fetchJson("/update_word", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      unit: card.unit,
      word: card.word,
      memorized_today: false,
    }),
  });
}

async function advanceWithRating(ratingOverride = null) {
  if (!session?.current || busy) return;
  setBusy(true);
  setActionStatus("正在提交评分并切换下一张...");
  const rating = ratingOverride || session.pendingRating || 3;
  const currentCard = session.current;
  const payload = await fetchJson("/study/review", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ word_id: currentCard.word_id, rating }),
  });
  session.history = session.history || [];
  session.history.push(currentCard);

  const updatedCard = payload.card;
  updatedCard.queue_kind = currentCard.queue_kind;

  if (rating === 1) {
    await clearMemorizedToday(currentCard);
  }

  if (rating === 4) {
    if (currentCard.queue_kind === "new") {
      session.completed.newCount += 1;
      session.stats.newRemaining = Math.max(0, session.stats.newRemaining - 1);
    } else {
      session.completed.reviewCount += 1;
      session.stats.reviewRemaining = Math.max(0, session.stats.reviewRemaining - 1);
    }
  } else {
    session.queue.push(updatedCard);
  }

  session.current = session.queue.shift() || null;
  session.pendingRating = 3;
  saveSession();
  setBusy(false);

  if (!session.current) {
    window.location.replace(currentUnit ? `focus.html?unit=${encodeURIComponent(currentUnit)}` : "focus.html");
    return;
  }
  window.location.replace(currentUnit ? `focus.html?unit=${encodeURIComponent(currentUnit)}` : "focus.html");
}

session = getSession();
viewCard = session?.current || null;
render();

detailSpeakBtn.addEventListener("click", () => speak(viewCard?.word || session?.current?.word));
prevBtn.addEventListener("click", () => {
  if (viewingHistory) {
    viewCard = session?.current || null;
    render();
    return;
  }
  if (session?.history?.length) {
    viewCard = session.history[session.history.length - 1];
    render();
  }
});
wrongBtn.addEventListener("click", () => advanceWithRating(1).catch((error) => {
  console.error(error);
  setBusy(false);
  setActionStatus(`提交失败：${error.message || error}`, true);
}));
nextBtn.addEventListener("click", () => {
  if (viewingHistory) {
    viewCard = session?.current || null;
    render();
    return;
  }
  advanceWithRating().catch((error) => {
    console.error(error);
    setBusy(false);
    setActionStatus(`提交失败：${error.message || error}`, true);
  });
});
