const API_ROOT = "http://127.0.0.1:8000/api/db";
const SESSION_KEY = "engwords_focus_sessions_v4";
const FOCUS_UNIT_KEY = "engwords_focus_selected_unit";
const params = new URLSearchParams(window.location.search);
const initialUnit = params.get("unit") || localStorage.getItem(FOCUS_UNIT_KEY) || "";
const SUBUNIT_TITLES = {
  "Unit_1_Sub1": "事业、优势、广告、商业术语",
  "Unit_1_Sub2": "资源、人文、农业、历史",
  "Unit_1_Sub3": "政治、集体、政府",
  "Unit_1_Sub4": "财务、负债、资产",
  "Unit_1_Sub5": "预算、消费、货币",
  "Unit_1_Sub6": "公司、商业交易、产权",
  "Unit_2_Sub1": "时间、周期、变化",
  "Unit_2_Sub2": "建筑/结构/工艺",
  "Unit_2_Sub3": "学习/评估/挑战",
  "Unit_2_Sub4": "基础科学/几何/物理",
  "Unit_2_Sub5": "数据、图表、计算",
  "Unit_2_Sub6": "设备/组件/装修",
  "Unit_2_Sub7": "能力/精度/工具",
  "Unit_2_Sub8": "通信/计算机设备",
  "Unit_3_Sub1": "判断/建议/规范",
  "Unit_3_Sub2": "副词/方位/频率",
  "Unit_3_Sub3": "原因/信念/假设",
  "Unit_3_Sub4": "动作/表现/社会事实",
  "Unit_3_Sub5": "情绪负面",
  "Unit_3_Sub6": "程度词/连接词",
  "Unit_3_Sub7": "赞美/态度",
  "Unit_3_Sub8": "对比/让步/句型",
  "Unit_4_Sub1": "体能/健身",
  "Unit_4_Sub2": "运动/交通",
  "Unit_4_Sub3": "位移/角度/平衡",
  "Unit_4_Sub4": "跨界/机械",
  "Unit_4_Sub5": "手部工具/附着",
  "Unit_4_Sub6": "力/摩擦/机械",
  "Unit_5_Sub1": "时间/等待/状态",
  "Unit_5_Sub2": "金钱/市场",
  "Unit_5_Sub3": "日常行为/可用性",
  "Unit_5_Sub4": "通用动作/基础",
  "Unit_5_Sub5": "节庆时间",
  "Unit_5_Sub6": "获取/运送/证件",
  "Unit_5_Sub7": "访问/账号/申报",
  "Unit_6_Sub1": "重构/重建/冲突",
  "Unit_6_Sub2": "健康/心情/情绪",
  "Unit_6_Sub3": "消失/破坏/连贯",
  "Unit_6_Sub4": "灾难/停止/保存",
  "Unit_7_Sub1": "空气/水/清洁",
  "Unit_7_Sub2": "植物/颜色/味道",
  "Unit_7_Sub3": "身体/伤口/生命",
  "Unit_7_Sub4": "材料/建造",
  "Unit_7_Sub5": "化学/饮料",
  "Unit_7_Sub6": "衣物/天气/保洁",
  "Unit_7_Sub7": "饮食/烹饪",
  "Unit_8_Sub1": "争论/结论/矛盾",
  "Unit_8_Sub2": "关系/一致/对比",
  "Unit_8_Sub3": "时间进展/成就",
  "Unit_8_Sub4": "法律/道德/冲突",
  "Unit_8_Sub5": "评估/认知/观点",
  "Unit_8_Sub6": "规则/妥协/隐瞒",
  "Unit_8_Sub7": "语言/沟通",
  "Unit_8_Sub8": "行动/表现/责任",
  "Unit_9_Sub1": "自然环境",
  "Unit_9_Sub2": "住宿/交通",
  "Unit_9_Sub3": "边界/旅行",
  "Unit_9_Sub4": "探险/到达",
  "Unit_9_Sub5": "区域/城市",
  "Unit_10_Sub1": "工具/材料",
  "Unit_10_Sub2": "动物/养殖",
  "Unit_10_Sub3": "情感/语言风格",
  "Unit_10_Sub4": "动作/速度",
  "Unit_10_Sub5": "人/物/生活",
  "Unit_10_Sub6": "生物/死亡",
  "Unit_10_Sub7": "身体部位",
  "Unit_10_Sub8": "自然/时间",
  "Unit_10_Sub9": "战斗/爆炸",
  "Unit_10_Sub10": "声音/音乐",
  "Unit_11_Sub1": "政治/法律",
  "Unit_11_Sub2": "宗教/庆祝",
  "Unit_11_Sub3": "职业/身份",
  "Unit_11_Sub4": "家族/阶层",
  "Unit_11_Sub5": "行政/管理",
  "Unit_11_Sub6": "身份/服务",
  "Unit_12_Sub1": "负面情绪/心理",
  "Unit_12_Sub2": "性质/状态",
  "Unit_12_Sub3": "人际/美感",
  "Unit_12_Sub4": "紧张/混乱",
  "Unit_12_Sub5": "赞美/自信",
  "Unit_12_Sub6": "普遍/习惯",
  "Unit_12_Sub7": "背叛/负面特质",
  "Unit_12_Sub8": "否定/抽象",
  "Unit_12_Sub9": "争议/危机",
};

const state = {
  queue: [],
  current: null,
  reveal: false,
  busy: false,
  currentUnit: initialUnit,
  scope: initialUnit ? "unit" : "global",
  stats: {
    newRemaining: 0,
    reviewRemaining: 0,
  },
  completed: {
    newCount: 0,
    reviewCount: 0,
  },
  history: [],
  progressOverview: {
    done: 0,
    total: 0,
  },
};

if (state.currentUnit) {
  localStorage.setItem(FOCUS_UNIT_KEY, state.currentUnit);
}

const focusCard = document.getElementById("focusCard");
const emptyState = document.getElementById("emptyState");
const deckMeta = document.getElementById("deckMeta");
const deckStep = document.getElementById("deckStep");
const newProgress = document.getElementById("newProgress");
const reviewProgress = document.getElementById("reviewProgress");
const newBar = document.getElementById("newBar");
const reviewBar = document.getElementById("reviewBar");
const currentUnitChip = document.getElementById("currentUnitChip");
const topProgressChip = document.getElementById("topProgressChip");
const topProgressText = document.getElementById("topProgressText");
const topProgressBar = document.getElementById("topProgressBar");
const topProgressLabel = document.getElementById("topProgressLabel");
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
const defaultExampleBlock = document.getElementById("defaultExampleBlock");
const customExamplesBlock = document.getElementById("customExamplesBlock");
const notesBlock = document.getElementById("notesBlock");
const speakBtn = document.getElementById("speakBtn");
const reloadBtn = document.getElementById("reloadBtn");
const scopeToggleBtn = document.getElementById("scopeToggleBtn");
const ratingButtons = [...document.querySelectorAll("[data-rating]")];

function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function getSessionBucketKey(scope = state.scope, unit = state.currentUnit) {
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

function saveSessionStore(store) {
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

function persistSession(extra = {}) {
  const store = getSessionStore();
  store[getSessionBucketKey()] = {
    queue: state.queue,
    current: state.current,
    currentUnit: state.currentUnit,
    scope: state.scope,
    stats: state.stats,
    completed: state.completed,
    history: state.history,
    progressOverview: state.progressOverview,
    ...extra,
  };
  saveSessionStore(store);
}

function normalizeSession(raw) {
  if (!raw || typeof raw !== "object") return null;
  return {
    queue: Array.isArray(raw.queue) ? raw.queue : [],
    current: raw.current || null,
    currentUnit: raw.currentUnit || "",
    scope: raw.scope === "global" ? "global" : "unit",
    stats: {
      newRemaining: Number(raw.stats?.newRemaining || 0),
      reviewRemaining: Number(raw.stats?.reviewRemaining || 0),
    },
    completed: {
      newCount: Number(raw.completed?.newCount || 0),
      reviewCount: Number(raw.completed?.reviewCount || 0),
    },
    history: Array.isArray(raw.history) ? raw.history : [],
    progressOverview: {
      done: Number(raw.progressOverview?.done || 0),
      total: Number(raw.progressOverview?.total || 0),
    },
    pendingRating: Number(raw.pendingRating || 0) || 0,
  };
}

function restoreSession() {
  try {
    const store = getSessionStore();
    const raw = normalizeSession(store[getSessionBucketKey()]);
    if (!raw) return false;
    if ((raw.currentUnit || "") !== (state.currentUnit || "")) return false;
    state.queue = raw.queue || [];
    state.current = raw.current || null;
    state.scope = raw.scope || state.scope;
    state.stats = raw.stats || state.stats;
    state.completed = raw.completed || state.completed;
    state.history = raw.history || [];
    state.progressOverview = raw.progressOverview || state.progressOverview;
    return true;
  } catch {
    return false;
  }
}

function setBusy(flag) {
  state.busy = flag;
  ratingButtons.forEach((button) => {
    button.disabled = flag || !state.current;
  });
  reloadBtn.disabled = flag;
  scopeToggleBtn.disabled = flag || !state.currentUnit;
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

function setBlockContent(el, title, text, translation = "") {
  if (!text) {
    el.classList.add("hidden");
    el.innerHTML = "";
    return;
  }
  el.classList.remove("hidden");
  el.innerHTML = `
    <div class="info-head"><h3>${escapeHtml(title)}</h3></div>
    <p>${escapeHtml(text)}</p>
    ${translation ? `<p>${escapeHtml(translation)}</p>` : ""}
  `;
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

function getUnitLabel(unitCode) {
  return SUBUNIT_TITLES[unitCode] || unitCode || "全局词库";
}

function updateScopeButton() {
  if (!state.currentUnit) {
    scopeToggleBtn.textContent = "仅全局";
    scopeToggleBtn.disabled = true;
    return;
  }
  scopeToggleBtn.disabled = state.busy;
  scopeToggleBtn.textContent = state.scope === "unit"
    ? "切到全局"
    : "切回本单元";
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
  if (state.scope === "unit" && state.currentUnit) {
    currentUnitChip.classList.remove("hidden");
    currentUnitChip.textContent = getUnitLabel(state.currentUnit);
  } else {
    currentUnitChip.classList.add("hidden");
    currentUnitChip.textContent = "";
  }
  topProgressChip.classList.remove("hidden");
  topProgressLabel.textContent = state.scope === "unit" && state.currentUnit ? "本单元总进度" : "全局总进度";
  topProgressText.textContent = `${state.progressOverview.done} / ${state.progressOverview.total}`;
  topProgressBar.style.width = `${state.progressOverview.total ? (state.progressOverview.done / state.progressOverview.total) * 100 : 0}%`;
}

function setProgressOverviewFromItems(progressItems = []) {
  state.progressOverview = {
    done: progressItems.filter((item) => item.status?.memorized_past).length,
    total: progressItems.length,
  };
}

async function refreshProgressOverview() {
  try {
    const progressItems = state.scope === "unit" && state.currentUnit
      ? await fetchJson(`/words/${encodeURIComponent(state.currentUnit)}`)
      : await fetchJson("/all_words");
    setProgressOverviewFromItems(progressItems);
  } catch (error) {
    console.warn("focus progress overview fallback", error);
  }
}

function renderReadonlyBlocks(card) {
  setBlockContent(definitionBlock, "释义", card.translation || (card.definitions || []).join(" / "));
  setBlockContent(tatoebaBlock, "", "", "");
  setBlockContent(aiBlock, "", "", "");

  setHtmlBlock(defaultExampleBlock, card.default_example ? `
    <div class="info-head"><h3>默认例句</h3></div>
    <p>${escapeHtml(card.default_example)}</p>
  ` : "");

  const examples = card.example_sentences || [];
  setHtmlBlock(customExamplesBlock, examples.length ? `
    <div class="info-head"><h3>自定义例句</h3></div>
    <div class="list-stack">
      ${examples.map((sentence) => `<div class="stack-row"><p>${escapeHtml(sentence)}</p></div>`).join("")}
    </div>
  ` : "");

  const notes = Array.isArray(card.notes_v2) ? card.notes_v2 : [];
  setHtmlBlock(notesBlock, notes.length ? `
    <div class="info-head"><h3>独立笔记</h3></div>
    <div class="list-stack">
      ${notes.map((note) => `<div class="stack-row"><p>${escapeHtml(note.text || "")}</p></div>`).join("")}
    </div>
  ` : "");
}

function renderCard() {
  const card = state.current;
  const completed = state.completed.newCount + state.completed.reviewCount;
  const queueSize = state.queue.length + (card ? 1 : 0);
  const modeLabel = state.scope === "unit" && state.currentUnit ? getUnitLabel(state.currentUnit) : "全局词库";
  deckStep.textContent = `${card ? completed + 1 : completed} / ${completed + queueSize}`;
  deckMeta.textContent = `${modeLabel} · 今日队列 ${queueSize} 张 · 空格翻牌 · 点熟悉度进入详情页`;
  updateScopeButton();
  updateMeters();

  if (!card) {
    focusCard.classList.add("hidden");
    emptyState.classList.remove("hidden");
    persistSession();
    return;
  }

  emptyState.classList.add("hidden");
  focusCard.classList.remove("hidden");

  const queueLabel = card.queue_kind === "review" ? "REVIEW" : "NEW";
  queueKindBadge.textContent = queueLabel;
  queueKindBadgeBack.textContent = queueLabel;
  unitBadge.textContent = getUnitLabel(card.unit);
  unitBadgeBack.textContent = getUnitLabel(card.unit);
  wordText.textContent = card.word;
  wordTextBack.textContent = card.word;
  wordPhoneticFront.textContent = card.phonetic ? `/${card.phonetic}/` : "";
  wordPhonetic.textContent = card.phonetic ? `/${card.phonetic}/` : "";
  wordTranslation.textContent = card.translation || "";
  renderReadonlyBlocks(card);
  focusCard.classList.toggle("is-revealed", state.reveal);
  setBusy(false);
  persistSession();
}

function revealCard(force = !state.reveal) {
  if (!state.current) return;
  state.reveal = force;
  focusCard.classList.toggle("is-revealed", state.reveal);
  persistSession();
}

function nextCard() {
  state.current = state.queue.shift() || null;
  state.reveal = false;
  renderCard();
  if (state.current) speak(state.current.word);
}

async function loadDeck() {
  setBusy(true);
  const search = new URLSearchParams();
  if (state.scope === "unit" && state.currentUnit) search.set("unit", state.currentUnit);
  const payload = await fetchJson(`/study/today${search.toString() ? `?${search}` : ""}`);
  state.queue = payload.queue || [];
  state.history = [];
  state.reveal = false;
  state.stats = {
    newRemaining: payload.stats?.new_remaining || 0,
    reviewRemaining: payload.stats?.review_remaining || 0,
  };
  if (!state.completed || typeof state.completed !== "object") {
    state.completed = { newCount: 0, reviewCount: 0 };
  }
  if (!state.progressOverview.total) {
    state.progressOverview = {
      done: 0,
      total: (payload.stats?.new_total || 0) + (payload.stats?.review_total || 0),
    };
  }
  await refreshProgressOverview();
  nextCard();
}

function openDetailWithRating(rating) {
  if (!state.current) return;
  persistSession({ pendingRating: rating });
  window.location.href = `focus_detail.html${state.currentUnit ? `?unit=${encodeURIComponent(state.currentUnit)}` : ""}`;
}

function toggleScope() {
  if (!state.currentUnit) return;
  persistSession();
  state.scope = state.scope === "unit" ? "global" : "unit";
  state.queue = [];
  state.current = null;
  state.history = [];
  state.completed = { newCount: 0, reviewCount: 0 };
  state.progressOverview = { done: 0, total: 0 };
  if (restoreSession()) {
    renderCard();
    refreshProgressOverview().then(() => {
      renderCard();
      persistSession();
    }).catch(() => {});
    if (state.current) speak(state.current.word);
    return;
  }
  loadDeck().catch(showError);
}

function showError(error) {
  console.error(error);
  setBusy(false);
  deckMeta.textContent = `加载失败：${error.message || error}`;
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
  persistSession();
  refreshProgressOverview()
    .then(() => renderCard())
    .catch(() => {})
    .finally(() => {
      loadDeck().catch(showError);
    });
});

scopeToggleBtn.addEventListener("click", toggleScope);

ratingButtons.forEach((button) => {
  button.addEventListener("click", () => {
    openDetailWithRating(Number(button.dataset.rating));
  });
});

document.addEventListener("keydown", (event) => {
  if (event.code === "Space") {
    event.preventDefault();
    revealCard();
    return;
  }
  if (["Digit1", "Digit2", "Digit3", "Digit4"].includes(event.code)) {
    openDetailWithRating(Number(event.code.slice(-1)));
  }
});

if (restoreSession()) {
  renderCard();
  refreshProgressOverview().then(() => {
    renderCard();
    persistSession();
  }).catch(() => {});
  if (state.current) speak(state.current.word);
} else {
  loadDeck().catch(showError);
}
