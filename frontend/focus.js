const API_ROOT = "http://127.0.0.1:8000/api/db";
const state = {
  queue: [],
  current: null,
  reveal: false,
  busy: false,
  stats: {
    newLimit: 20,
    reviewLimit: 50,
    newRemaining: 0,
    reviewRemaining: 0,
  },
  completed: {
    newCount: 0,
    reviewCount: 0,
  },
};

const focusCard = document.getElementById("focusCard");
const emptyState = document.getElementById("emptyState");
const deckMeta = document.getElementById("deckMeta");
const deckStep = document.getElementById("deckStep");
const newProgress = document.getElementById("newProgress");
const reviewProgress = document.getElementById("reviewProgress");
const newBar = document.getElementById("newBar");
const reviewBar = document.getElementById("reviewBar");
const queueKindBadge = document.getElementById("queueKindBadge");
const queueKindBadgeBack = document.getElementById("queueKindBadgeBack");
const unitBadge = document.getElementById("unitBadge");
const unitBadgeBack = document.getElementById("unitBadgeBack");
const wordText = document.getElementById("wordText");
const wordTextBack = document.getElementById("wordTextBack");
const wordPhoneticFront = document.getElementById("wordPhoneticFront");
const wordPhonetic = document.getElementById("wordPhonetic");
const wordTranslation = document.getElementById("wordTranslation");
const definitionBlock = document.getElementById("definitionBlock");
const tatoebaBlock = document.getElementById("tatoebaBlock");
const aiBlock = document.getElementById("aiBlock");
const speakBtn = document.getElementById("speakBtn");
const reloadBtn = document.getElementById("reloadBtn");
const ratingButtons = [...document.querySelectorAll("[data-rating]")];

function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
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
  state.busy = flag;
  ratingButtons.forEach((button) => {
    button.disabled = flag || !state.reveal || !state.current;
  });
  reloadBtn.disabled = flag;
}

function setBlockContent(el, title, text, translation = "") {
  if (!text) {
    el.classList.add("hidden");
    el.innerHTML = "";
    return;
  }
  el.classList.remove("hidden");
  el.innerHTML = `
    <h3>${escapeHtml(title)}</h3>
    <p>${escapeHtml(text)}</p>
    ${translation ? `<p>${escapeHtml(translation)}</p>` : ""}
  `;
}

function updateMeters() {
  const newDone = state.completed.newCount;
  const reviewDone = state.completed.reviewCount;
  const newTotal = Math.max(state.stats.newRemaining + newDone, newDone);
  const reviewTotal = Math.max(state.stats.reviewRemaining + reviewDone, reviewDone);

  newProgress.textContent = `${newDone} / ${newTotal || 0}`;
  reviewProgress.textContent = `${reviewDone} / ${reviewTotal || 0}`;
  newBar.style.width = `${newTotal ? (newDone / newTotal) * 100 : 0}%`;
  reviewBar.style.width = `${reviewTotal ? (reviewDone / reviewTotal) * 100 : 0}%`;
}

function renderCard() {
  const card = state.current;
  const completed = state.completed.newCount + state.completed.reviewCount;
  const queueSize = state.queue.length + (card ? 1 : 0);
  deckStep.textContent = `${card ? completed + 1 : completed} / ${completed + queueSize}`;
  deckMeta.textContent = `今日队列 ${queueSize} 张，空格翻牌，数字 1-4 评分`;
  updateMeters();

  if (!card) {
    focusCard.classList.add("hidden");
    emptyState.classList.remove("hidden");
    return;
  }

  emptyState.classList.add("hidden");
  focusCard.classList.remove("hidden");
  focusCard.classList.toggle("is-revealed", state.reveal);

  const queueLabel = card.queue_kind === "review" ? "REVIEW" : "NEW";
  queueKindBadge.textContent = queueLabel;
  queueKindBadgeBack.textContent = queueLabel;
  unitBadge.textContent = card.unit;
  unitBadgeBack.textContent = card.unit;
  wordText.textContent = card.word;
  wordTextBack.textContent = card.word;
  wordPhoneticFront.textContent = card.phonetic || "";
  wordPhonetic.textContent = card.phonetic || "";
  wordTranslation.textContent = card.translation || "";
  setBlockContent(definitionBlock, "Definition", (card.definitions || []).join(" / "));
  setBlockContent(tatoebaBlock, "Tatoeba", card.tatoeba_example?.text, card.tatoeba_example?.translation);
  setBlockContent(aiBlock, "AI Example", card.ai_example?.text || card.default_example, card.ai_example?.translation);
  setBusy(false);
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
  if (window._focusAudio) {
    window._focusAudio.pause();
    window._focusAudio = null;
  }
  try {
    const res = await fetch(`${API_ROOT}/tts?voice=nahida&word=${encodeURIComponent(text)}`);
    if (!res.ok) throw new Error(`TTS ${res.status}`);
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const audio = new Audio(url);
    window._focusAudio = audio;
    await audio.play();
    audio.onended = () => URL.revokeObjectURL(url);
  } catch (error) {
    console.warn("focus TTS fallback", error);
    fallbackSpeak(text);
  }
}

function revealCard(force = !state.reveal) {
  if (!state.current) return;
  state.reveal = force;
  renderCard();
}

function nextCard() {
  state.current = state.queue.shift() || null;
  state.reveal = false;
  renderCard();
  if (state.current) {
    speak(state.current.word);
  }
}

async function loadDeck() {
  setBusy(true);
  const payload = await fetchJson("/study/today");
  state.queue = payload.queue || [];
  state.stats = {
    newLimit: payload.stats?.new_limit || 20,
    reviewLimit: payload.stats?.review_limit || 50,
    newRemaining: payload.stats?.new_remaining || 0,
    reviewRemaining: payload.stats?.review_remaining || 0,
  };
  state.completed = { newCount: 0, reviewCount: 0 };
  nextCard();
}

async function submitRating(rating) {
  if (!state.current || !state.reveal || state.busy) return;
  setBusy(true);
  const current = state.current;
  const payload = await fetchJson("/study/review", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ word_id: current.word_id, rating }),
  });

  if (current.queue_kind === "new") {
    state.completed.newCount += 1;
    state.stats.newRemaining = Math.max(0, state.stats.newRemaining - 1);
  } else {
    state.completed.reviewCount += 1;
    state.stats.reviewRemaining = Math.max(0, state.stats.reviewRemaining - 1);
  }

  if (payload.review?.requeue_in_session) {
    const updatedCard = payload.card;
    updatedCard.queue_kind = payload.review.state === 2 ? "review" : current.queue_kind;
    state.queue.push(updatedCard);
    if (updatedCard.queue_kind === "new") {
      state.stats.newRemaining += 1;
      state.completed.newCount = Math.max(0, state.completed.newCount - 1);
    } else {
      state.stats.reviewRemaining += 1;
      state.completed.reviewCount = Math.max(0, state.completed.reviewCount - 1);
    }
  }

  nextCard();
}

focusCard.addEventListener("click", (event) => {
  if (event.target.closest("button")) return;
  revealCard();
});

speakBtn.addEventListener("click", (event) => {
  event.stopPropagation();
  speak(state.current?.word);
});

reloadBtn.addEventListener("click", () => {
  loadDeck().catch(showError);
});

ratingButtons.forEach((button) => {
  button.addEventListener("click", () => {
    submitRating(Number(button.dataset.rating)).catch(showError);
  });
});

document.addEventListener("keydown", (event) => {
  if (event.target.tagName === "INPUT" || event.target.tagName === "TEXTAREA") return;
  if (event.code === "Space") {
    event.preventDefault();
    revealCard();
    return;
  }
  if (["Digit1", "Digit2", "Digit3", "Digit4"].includes(event.code)) {
    submitRating(Number(event.code.slice(-1))).catch(showError);
  }
});

function showError(error) {
  console.error(error);
  setBusy(false);
  deckMeta.textContent = `加载失败：${error.message || error}`;
}

loadDeck().catch(showError);
