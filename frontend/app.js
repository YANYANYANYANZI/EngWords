const API_BASE = "http://127.0.0.1:8000/api"; // ensure matches backend service port
const DB_API_PREFIX = "/db";
const unitListEl = document.getElementById("unitList");
const wordGridEl = document.getElementById("wordGrid");
const unitNameEl = document.getElementById("unitName");
const statsEl = document.getElementById("stats");
const unitFilterInput = document.getElementById("unitFilter"); // may be null when filter input removed from DOM
const wordSearchInput = document.getElementById("wordSearch");
const semanticSearchInput = document.getElementById("semanticSearch");
const searchBtn = document.getElementById("searchBtn");
const semanticSearchBtn = document.getElementById("semanticSearchBtn");
const searchResultsEl = document.getElementById("searchResults");


let allWords = [];
let wordIndex = {};
const dashboardBtn = document.getElementById("dashboardBtn");
const dashboardEl = document.getElementById("dashboard");
const chartCanvas = document.getElementById("chartCanvas");
const dashboardCardsEl = document.getElementById("dashboardCards");
const summaryTextarea = document.getElementById("unitSummary");
const refreshSummaryButton = document.getElementById("refreshSummary");
const backToWords = document.getElementById("backToWords");
const searchBackBtn = document.getElementById("searchBackBtn");
const themeToggle = document.getElementById("themeToggle");
const menuBar = document.getElementById("menuBar");
const focusStudyBtn = document.getElementById("focusStudyBtn");
const FOCUS_UNIT_KEY = "engwords_focus_selected_unit";

let units = [];
let currentUnit = null;
let currentWords = [];
let unitTree = {};
let relations = {};
let dashboardChart = null;
let searchHistory = [];
let highlightWord = null;
let restoreScrollY = null;
const DETAIL_STATE_KEY = "vocab_detail_open_state";

async function apiFetch(path, options = {}) {
  const dbPath = `${API_BASE}${DB_API_PREFIX}${path}`;
  try {
    const dbRes = await fetch(dbPath, options);
    if (dbRes.ok) return dbRes;
    console.warn("DB API fallback", path, dbRes.status, await dbRes.text());
  } catch (error) {
    console.warn("DB API unavailable, fallback to JSON API", path, error);
  }
  return fetch(`${API_BASE}${path}`, options);
}

const UNIT_TITLES = {
  Unit_1: "商业 / 政治 / 社会",
  Unit_2: "科学 / 数学 / 技术",
  Unit_3: "语法 / 交际 / 情绪",
  Unit_4: "运动 / 方向 / 物理",
  Unit_5: "日常 / 交易 / 时间",
  Unit_6: "变化 / 负面 / 动作",
  Unit_7: "物质 / 自然 / 食品",
  Unit_8: "逻辑 / 社交 / 语用",
  Unit_9: "地点 / 旅行 / 方向",
  Unit_10: "物品 / 动物 / 动作",
  Unit_11: "人物 / 社会组织",
  Unit_12: "情绪 / 描述 / 评价",
};

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

function groupUnits(items) {
  const tree = {};
  items.forEach((u) => {
    const [root, sub] = u.unit.split("_Sub");
    if (!tree[root]) {
      tree[root] = { title: UNIT_TITLES[root] || root, subs: [] };
    }
    tree[root].subs.push({ unit: u.unit, count: u.count });
  });
  return tree;
}

async function fetchUnits() {
  const res = await apiFetch(`/units`);
  units = await res.json();
  unitTree = groupUnits(units);
  renderUnitList();
  updateFocusStudyLink();
}

async function loadAllWords() {
  try {
    const res = await apiFetch(`/all_words`);
    if (!res.ok) throw new Error("all_words fetch failed");
    allWords = await res.json();
    wordIndex = {};
    allWords.forEach((item) => {
      if (item.word) {
        wordIndex[item.word.toLowerCase()] = item;
      }
    });
  } catch (error) {
    console.error("loadAllWords error", error);
    allWords = [];
    wordIndex = {};
  }
}

async function loadRelations() {
  const res = await fetch(`${API_BASE}/relations`);
  if (res.ok) {
    relations = await res.json();
  }
}

function renderUnitList() {
  unitListEl.innerHTML = "";
  const q = unitFilterInput ? unitFilterInput.value.trim().toLowerCase() : "";

  Object.keys(unitTree).forEach((root) => {
    const group = unitTree[root];
    const groupEl = document.createElement("li");
    groupEl.className = "unit-group";
    const label = document.createElement("div");
    label.className = "group-label";
    label.textContent = `${group.title} (${group.subs.length})`;
    groupEl.appendChild(label);

    const subList = document.createElement("ul");
    subList.className = "subunit-list";

    group.subs.forEach((sub) => {
      if (q && !sub.unit.toLowerCase().includes(q) && !((SUBUNIT_TITLES[sub.unit] || "").toLowerCase().includes(q))) return;
      const item = document.createElement("li");
      item.className = "subunit-item";
      item.textContent = `${SUBUNIT_TITLES[sub.unit] || sub.unit} (${sub.count})`;
      item.dataset.unit = sub.unit;
      if (sub.unit === currentUnit) item.classList.add("active");
      item.addEventListener("click", () => loadUnit(sub.unit));
      subList.appendChild(item);
    });

    groupEl.appendChild(subList);
    unitListEl.appendChild(groupEl);
  });
}

function updateFocusStudyLink() {
  if (!focusStudyBtn) return;
  if (currentUnit) {
    localStorage.setItem(FOCUS_UNIT_KEY, currentUnit);
    focusStudyBtn.href = `focus.html?unit=${encodeURIComponent(currentUnit)}`;
    focusStudyBtn.textContent = `沉浸刷词 · ${SUBUNIT_TITLES[currentUnit] || currentUnit}`;
    return;
  }
  localStorage.removeItem(FOCUS_UNIT_KEY);
  focusStudyBtn.href = "focus.html";
  focusStudyBtn.textContent = "沉浸刷词";
}

async function loadUnit(unitId) {
  currentUnit = unitId;
  unitNameEl.textContent = `${SUBUNIT_TITLES[unitId] || unitId}   /   ${UNIT_TITLES[unitId.split("_")[0]] || unitId.split("_")[0]}`;
  currentWords = await apiFetch(`/words/${unitId}`).then((r) => r.json());
  renderWordGrid();
  if (highlightWord) {
    setTimeout(() => {
      const target = document.querySelector(`[data-word-card="${CSS.escape(highlightWord)}"]`);
      if (target) target.scrollIntoView({ behavior: "smooth", block: "center" });
      highlightWord = null;
    }, 100);
  } else if (restoreScrollY !== null) {
    const y = restoreScrollY;
    restoreScrollY = null;
    setTimeout(() => restoreScrollPosition(y), 100);
  }
  renderStats();
  renderUnitList();
  updateFocusStudyLink();
  await loadSummary(unitId);
}

function renderStats() {
  const total = currentWords.length;
  const done = currentWords.filter((x) => x.status?.memorized_today).length;
  statsEl.textContent = `词量 ${total} → 今日已背 ${done}`;
}

function scrollContainer() {
  return document.querySelector(".content") || document.documentElement;
}

function getScrollPosition() {
  const el = scrollContainer();
  return el === document.documentElement ? window.scrollY : el.scrollTop;
}

function currentAnchorWord() {
  const container = document.querySelector(".content");
  const cards = [...document.querySelectorAll("[data-word-card]")];
  const top = container ? container.getBoundingClientRect().top + 12 : 12;
  const visible = cards.find((card) => card.getBoundingClientRect().bottom > top);
  return visible?.dataset.wordCard || null;
}

function restoreScrollPosition(y) {
  const el = scrollContainer();
  if (el === document.documentElement) {
    window.scrollTo({ top: y, behavior: "smooth" });
  } else {
    el.scrollTo({ top: y, behavior: "smooth" });
  }
}

function speak(text) {
  if (!text) return;
  
  // 清理上一个正在播放的音频
  if (window._speakAudio) {
    window._speakAudio.pause();
    window._speakAudio = null;
  }

  // 尝试通过后端 TTS（纳西妲语音模型）获取发音
  const ttsUrl = `${API_BASE}/db/tts?voice=nahida&word=${encodeURIComponent(text)}`;
  fetch(ttsUrl)
    .then((res) => {
      if (!res.ok) throw new Error(`TTS backend returned ${res.status}`);
      return res.blob();
    })
    .then((blob) => {
      const url = URL.createObjectURL(blob);
      const audio = new Audio(url);
      window._speakAudio = audio;
      audio.play().catch((err) => {
        console.warn("TTS audio play failed, fallback to browser speech", err);
        fallbackSpeak(text);
      });
      audio.onended = () => URL.revokeObjectURL(url);
    })
    .catch((err) => {
      console.warn("TTS backend unavailable, fallback to browser speech", err);
      fallbackSpeak(text);
    });
}

function fallbackSpeak(text) {
  speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(text);
  u.lang = "en-US";
  u.rate = 0.92;
  speechSynthesis.speak(u);
}

function localSearch(query, limit = 12) {
  const q = query.trim().toLowerCase();
  if (!q) return [];
  const scoreOf = (item) => {
    const word = (item.word || "").toLowerCase();
    const text = [item.word, item.translation, item.chinese, ...(item.definitions || [])].join(" ").toLowerCase();
    let score = 0;
    if (word === q) score += 100;
    if (word.startsWith(q)) score += 70;
    if (word.includes(q)) score += 45;
    if (text.includes(q)) score += 38;
    const common = [...q].filter((ch) => word.includes(ch)).length;
    score += common / Math.max(q.length, 1) * 18;
    return score;
  };
  return allWords
    .map((item) => ({ ...item, _score: scoreOf(item) }))
    .filter((item) => item._score > 12)
    .sort((a, b) => b._score - a._score)
    .slice(0, limit);
}

async function commitWord(word, field, value) {
  const payload = { unit: currentUnit, word, [field]: value };
  if (field === 'memorized_today' && value === true) {
    payload.memorized_past = true;
  }

  const res = await apiFetch(`/update_word`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    console.error("update_word failed", await res.text());
    return;
  }
  const updated = await res.json();
  replaceWordInCaches(currentUnit, word, updated);
  renderStats();
  renderWordGrid();
}

async function commitNote(word, notes) {
  const entry = currentWords.find((x) => x.word === word);
  if (!entry) return;
  const noteList = notes
    .split("\n")
    .map((text, index) => text.trim() ? createNoteObject(entry, text.trim(), index) : null)
    .filter(Boolean);
  return commitNotes(entry, noteList);
}

function nowIso() {
  return new Date().toISOString();
}

function createNoteObject(entry, text = "", index = 0, links = []) {
  const safeWord = (entry?.word || "word").toLowerCase().replace(/[^a-z0-9]+/g, "_");
  return {
    id: `note_${entry?.unit || currentUnit}_${safeWord}_${Date.now()}_${index}`,
    text,
    links,
    created_at: nowIso(),
    updated_at: nowIso(),
  };
}

function getNotes(entry) {
  if (Array.isArray(entry.notes_v2)) {
    return entry.notes_v2.map((note, index) => typeof note === "string"
      ? createNoteObject(entry, note, index)
      : { id: note.id || createNoteObject(entry, note.text || "", index).id, text: note.text || "", links: Array.isArray(note.links) ? note.links : [], created_at: note.created_at || null, updated_at: note.updated_at || null });
  }
  return (entry.notes || "")
    .split("\n")
    .map((text, index) => text.trim() ? createNoteObject(entry, text.trim(), index) : null)
    .filter(Boolean);
}

function notesToLegacyText(notes) {
  return notes.map((note) => note.text || "").filter((text) => text.trim()).join("\n");
}

function loadDetailState() {
  try {
    return JSON.parse(localStorage.getItem(DETAIL_STATE_KEY) || "{}");
  } catch (error) {
    console.warn("detail state parse failed", error);
    return {};
  }
}

function detailStateKey(entry, section) {
  return `${entry.unit || currentUnit}::${entry.word}::${section}`;
}

function isDetailOpen(entry, section, defaultOpen = false) {
  const state = loadDetailState();
  const key = detailStateKey(entry, section);
  return key in state ? Boolean(state[key]) : defaultOpen;
}

function saveDetailOpen(entry, section, open) {
  const state = loadDetailState();
  state[detailStateKey(entry, section)] = Boolean(open);
  localStorage.setItem(DETAIL_STATE_KEY, JSON.stringify(state));
}

function replaceWordInCaches(unit, word, updated) {
  const current = currentWords.find((x) => x.word === word && (x.unit || currentUnit) === unit);
  const merged = { ...current, ...updated, default_example: updated.default_example || current?.default_example };
  const idx = currentWords.findIndex((x) => x.word === word && (x.unit || currentUnit) === unit);
  if (idx >= 0) currentWords[idx] = merged;
  const allIdx = allWords.findIndex((x) => x.word === word && x.unit === unit);
  if (allIdx >= 0) allWords[allIdx] = { ...allWords[allIdx], ...merged };
}

async function commitNotes(entry, notes) {
  const cleanNotes = notes
    .map((note, index) => ({
      ...note,
      id: note.id || createNoteObject(entry, note.text || "", index).id,
      text: note.text || "",
      links: Array.isArray(note.links) ? note.links : [],
      updated_at: nowIso(),
    }))
    .filter((note) => note.text.trim());
  const payload = { unit: entry.unit || currentUnit, word: entry.word, notes: notesToLegacyText(cleanNotes), notes_v2: cleanNotes };
  const res = await apiFetch(`/update_note`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    console.error("update_note failed", await res.text());
    return;
  }
  const updated = await res.json();
  replaceWordInCaches(entry.unit || currentUnit, entry.word, updated);
  return updated;
}

async function addNoteToWord(unit, word, extraNote, links = []) {
  const target = allWords.find((x) => x.unit === unit && x.word === word);
  const targetEntry = target || { unit, word, notes: "", notes_v2: [] };
  const nextNotes = [...getNotes(targetEntry), createNoteObject(targetEntry, extraNote, getNotes(targetEntry).length, links)];
  const res = await apiFetch(`/update_note`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ unit, word, notes: notesToLegacyText(nextNotes), notes_v2: nextNotes }),
  });
  if (!res.ok) throw new Error(await res.text());
  const updated = await res.json();
  replaceWordInCaches(unit, word, updated);
  return updated;
}

async function saveNoteAsExample(entry, note) {
  const text = note.text.trim();
  if (!text) return alert("笔记为空，不能添加为例句");
  const examples = [...(entry.example_sentences || [])];
  if (!examples.includes(text)) examples.unshift(text);
  const res = await apiFetch(`/enrich_word`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      unit: currentUnit,
      word: entry.word,
      pos: entry.pos || "",
      definitions: entry.definitions || [],
      example_sentences: examples.slice(0, 6),
      chinese: entry.chinese || entry.translation || "",
    }),
  });
  if (!res.ok) return alert("添加例句失败");
  const updated = await res.json();
  const merged = { ...updated, default_example: updated.default_example || entry.default_example };
  replaceWordInCaches(currentUnit, entry.word, merged);
  const latest = currentWords.find((item) => item.word === entry.word) || merged;
  const noteText = note.text.trim();
  await commitNotes(latest, getNotes(latest).filter((item) => item.id !== note.id && item.text.trim() !== noteText));
  renderWordGrid();
}

async function updateCustomExamples(entry, examples) {
  const res = await apiFetch(`/enrich_word`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      unit: currentUnit,
      word: entry.word,
      pos: entry.pos || "",
      definitions: entry.definitions || [],
      example_sentences: examples,
      chinese: entry.chinese || entry.translation || "",
    }),
  });
  if (!res.ok) throw new Error(await res.text());
  const updated = await res.json();
  const idx = currentWords.findIndex((x) => x.word === entry.word);
  if (idx >= 0) currentWords[idx] = { ...updated, default_example: entry.default_example };
  renderWordGrid();
}

async function customExampleAction(entry, sentence, action) {
  if (action === "speak") return speak(sentence);
  if (action === "to-note") {
    await commitNotes(entry, [...getNotes(entry), createNoteObject(entry, sentence, getNotes(entry).length)]);
    const next = (entry.example_sentences || []).filter((s) => s !== sentence);
    await updateCustomExamples(entry, next);
    alert("已转换为笔记");
    return;
  }
  if (action === "delete") {
    if (!confirm("删除这条自定义例句？")) return;
    const next = (entry.example_sentences || []).filter((s) => s !== sentence);
    await updateCustomExamples(entry, next);
  }
}

async function saveSingleNote(entry, note, value) {
  const notes = getNotes(entry).map((item) => item.id === note.id ? { ...item, text: value, updated_at: nowIso() } : item);
  const updated = await commitNotes(entry, notes);
  await propagateSyncNoteEdit(entry, note, value);
  if (updated) renderWordGrid();
}

async function propagateSyncNoteEdit(entry, sourceNote, value) {
  const sourceUnit = entry.unit || currentUnit;
  const targets = allWords.filter((wordEntry) => getNotes(wordEntry).some((note) =>
    (note.links || []).some((link) => link.mode === "sync" && link.unit === sourceUnit && link.word === entry.word && link.note_id === sourceNote.id)
  ));
  for (const target of targets) {
    const targetNotes = getNotes(target).map((note) => {
      const linked = (note.links || []).some((link) => link.mode === "sync" && link.unit === sourceUnit && link.word === entry.word && link.note_id === sourceNote.id);
      return linked ? { ...note, text: `↔ 关联自 ${entry.word}: ${value}`, updated_at: nowIso() } : note;
    });
    await commitNotes(target, targetNotes);
  }
}

async function addBlankNote(entry) {
  const text = prompt("输入新笔记内容：");
  if (!text || !text.trim()) return;
  await commitNotes(entry, [...getNotes(entry), createNoteObject(entry, text.trim(), getNotes(entry).length)]);
  renderWordGrid();
}

async function deleteSingleNote(entry, note) {
  if (!confirm("删除这条笔记？")) return;
  const noteText = note.text.trim();
  const updated = await commitNotes(entry, getNotes(entry).filter((item) => item.id !== note.id && item.text.trim() !== noteText));
  if (!updated) return alert("删除失败，请稍后重试");
  renderWordGrid();
}

function updateSearchBackButton() {
  if (!searchHistory.length) {
    searchBackBtn.style.display = "none";
    searchBackBtn.textContent = "← 返回上一级";
    return;
  }
  searchBackBtn.style.display = "inline-block";
  searchBackBtn.textContent = searchHistory.length > 1 ? `← 返回上一级 (${searchHistory.length})` : "← 返回上一级";
}

function pushSearchHistory() {
  if (!currentUnit) return;
  const last = searchHistory[searchHistory.length - 1];
  if (last?.unit === currentUnit) return;
  searchHistory.push({ unit: currentUnit, word: currentAnchorWord(), scrollY: getScrollPosition() });
  updateSearchBackButton();
}

function jumpToSearchResult(unit, word) {
  pushSearchHistory();
  highlightWord = word;
  updateSearchBackButton();
  loadUnit(unit);
  searchResultsEl.style.display = 'none';
}

function closeAllMenus(except = null) {
  document.querySelectorAll(".note-menu.open").forEach((menu) => {
    if (menu !== except) menu.classList.remove("open");
  });
}

function actionButton(label, title, onClick, className = "inline-action-btn") {
  const button = document.createElement("button");
  button.type = "button";
  button.className = className;
  button.textContent = label;
  button.title = title;
  button.addEventListener("click", onClick);
  return button;
}

async function linkNoteToAnotherWord(entry, note) {
  const text = note.text.trim();
  if (!text) return alert("笔记为空，不能关联");
  const query = prompt("搜索要关联到哪个单词？输入英文或中文释义");
  if (!query) return;
  const matches = localSearch(query, 8).filter((x) => !(x.unit === currentUnit && x.word === entry.word));
  if (!matches.length) return alert("没有找到可关联的单词");
  const choiceText = matches.map((m, i) => `${i + 1}. ${m.word} (${m.translation || ""}) [${m.unit}]`).join("\n");
  const pick = Number(prompt(`选择编号：\n${choiceText}`));
  const target = matches[pick - 1];
  if (!target) return;
  const mode = prompt("关联方式：输入 1 = 默认同步关联；输入 2 = 作为副本", "1");
  const asCopy = mode === "2";
  const linkA = { unit: target.unit, word: target.word, note_id: asCopy ? null : "pending", mode: asCopy ? "copy" : "sync" };
  const sourceNotes = getNotes(entry).map((item) => item.id === note.id ? { ...item, links: [...(item.links || []), { ...linkA, note_id: null }], updated_at: nowIso() } : item);
  const targetUpdated = await addNoteToWord(
    target.unit,
    target.word,
    asCopy ? text : `↔ 关联自 ${entry.word}: ${text}`,
    [{ unit: currentUnit, word: entry.word, note_id: note.id, mode: asCopy ? "copy" : "sync" }]
  );
  const targetNote = getNotes(targetUpdated).find((item) => item.text === (asCopy ? text : `↔ 关联自 ${entry.word}: ${text}`));
  const linkedSourceNotes = sourceNotes.map((item) => item.id === note.id
    ? { ...item, links: [...(note.links || []), { unit: target.unit, word: target.word, note_id: targetNote?.id || null, mode: asCopy ? "copy" : "sync" }] }
    : item);
  await commitNotes(entry, linkedSourceNotes);
  alert(asCopy ? `已作为副本添加到 ${target.word}` : `已同步关联到 ${target.word}`);
  await loadAllWords();
  renderWordGrid();
}

async function loadSummary(unitId) {
  const res = await fetch(`${API_BASE}/unit_summary/${unitId}`);
  if (res.ok) {
    const payload = await res.json();
    summaryTextarea.value = payload.summary || "";
  } else {
    summaryTextarea.value = "";
  }
}

async function saveSummary() {
  if (!currentUnit) return;
  const payload = { unit: currentUnit, summary: summaryTextarea.value };
  const res = await fetch(`${API_BASE}/unit_summary`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    console.error("save summary failed", await res.text());
  }
}

async function enrichWord(entry) {
  const enrichButton = document.querySelector(`[data-enrich="${entry.word}"]`);
  if (enrichButton) {
    enrichButton.textContent = "补全中…";
    enrichButton.disabled = true;
  }
  const queryRes = await fetch(`${API_BASE}/dict/${entry.word}`);
  if (!queryRes.ok) {
    if (enrichButton) enrichButton.textContent = "补全失败";
    return;
  }
  const data = await queryRes.json();
  if (!data.senses || data.senses.length === 0) {
    if (enrichButton) enrichButton.textContent = "暂无可补全";
    return;
  }

  const definitions = data.senses.map((s) => `${s.pos}: ${s.definition}`);
  const examples = data.senses.flatMap((s) => s.examples || []).slice(0, 2);

  const enrichRes = await apiFetch(`/enrich_word`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      unit: currentUnit,
      word: entry.word,
      pos: data.senses[0]?.pos || entry.pos || "",
      definitions,
      example_sentences: examples,
      chinese: data.senses[0]?.chinese || "",
    }),
  });

  if (!enrichRes.ok) {
    console.error("enrich word failed", await enrichRes.text());
    if (enrichButton) enrichButton.textContent = "补全失败";
    return;
  }

  const updated = await enrichRes.json();
  const idx = currentWords.findIndex((x) => x.word === entry.word);
  if (idx >= 0) currentWords[idx] = updated;
  renderWordGrid();
}

function renderWordGrid() {
  wordGridEl.innerHTML = "";
  currentWords.forEach((entry) => {
    const card = document.createElement("article");
    card.className = "word-card";
    card.dataset.wordCard = entry.word;
    if (entry.word === highlightWord) card.classList.add("highlight-card");
    if (entry.status?.memorized_today) card.classList.add("done-today");

    const meta = document.createElement("div");
    meta.className = "meta";
    const title = document.createElement("h3");
    title.textContent = entry.word;
    const sound = document.createElement("button");
    sound.className = "icon-btn";
    sound.textContent = "▶";
    sound.title = "单词发音";
    sound.addEventListener("click", () => speak(entry.word));
    meta.append(title, sound);

    const trans = document.createElement("p");
    trans.className = "translation";
    trans.textContent = entry.translation || "-";

    const ecdictMeta = document.createElement("div");
    ecdictMeta.className = "ecdict-meta";
    if (entry.phonetic) {
      const phonetic = document.createElement("span");
      phonetic.className = "phonetic-badge";
      phonetic.textContent = `/${entry.phonetic}/`;
      ecdictMeta.appendChild(phonetic);
    }
    const ecdictTags = String(entry.tags || "")
      .split(/[,\s;|]+/)
      .map((tag) => tag.trim())
      .filter(Boolean)
      .slice(0, 4);
    ecdictTags.forEach((tag) => {
      const chip = document.createElement("span");
      chip.className = "ecdict-tag";
      chip.textContent = tag;
      ecdictMeta.appendChild(chip);
    });

    const tags = document.createElement("div");
    tags.className = "tags";
    if (entry.pos) tags.innerHTML += `<span>${entry.pos}</span>`;
    const label = SUBUNIT_TITLES[currentUnit] || currentUnit;
    if (label) tags.innerHTML += `<span>${label}</span>`;

    const checkbox = document.createElement("div");
    checkbox.className = "checkbox-group";

    const memoPast = document.createElement("label");
    memoPast.innerHTML = `<input type="checkbox" ${entry.status?.memorized_past ? "checked" : ""}/> 过去掌握`;
    memoPast.querySelector("input").addEventListener("change", (event) => {
      commitWord(entry.word, "memorized_past", event.target.checked);
    });

    const memoToday = document.createElement("label");
    memoToday.innerHTML = `<input type="checkbox" ${entry.status?.memorized_today ? "checked" : ""}/> 今日打卡`;
    memoToday.querySelector("input").addEventListener("change", (event) => {
      const checked = event.target.checked;
      if (checked) {
        memoPast.querySelector("input").checked = true;
      }
      commitWord(entry.word, "memorized_today", checked);
    });

    checkbox.append(memoPast, memoToday);

    const exampleBlock = document.createElement("div");
    exampleBlock.className = "example-block";
    const defaultExample = entry.default_example || "";
    exampleBlock.innerHTML = `<div class="example-title"><strong>默认例句</strong><button class="mini-btn" type="button" title="发音默认例句">🔊</button></div><p>${defaultExample}</p>`;
    exampleBlock.querySelector(".mini-btn").addEventListener("click", () => speak(defaultExample));
    if (entry.example_sentences?.length) {
      const customDetails = document.createElement("details");
      customDetails.className = "custom-examples custom-examples-details";
      customDetails.open = isDetailOpen(entry, "custom_examples", false);
      customDetails.addEventListener("toggle", () => saveDetailOpen(entry, "custom_examples", customDetails.open));
      customDetails.innerHTML = `<summary><strong>自定义例句（${entry.example_sentences.length}）</strong><span>展开</span></summary>`;
      entry.example_sentences.forEach((sentence) => {
        const row = document.createElement("div");
        row.className = "custom-example-row";
        const text = document.createElement("p");
        text.textContent = sentence;
        const actions = document.createElement("div");
        actions.className = "inline-actions";
        actions.append(
          actionButton("🔊", "发音这条自定义例句", () => customExampleAction(entry, sentence, "speak")),
          actionButton("📝", "把这条例句转换成一条独立笔记", () => customExampleAction(entry, sentence, "to-note")),
          actionButton("🗑", "删除这条自定义例句", () => customExampleAction(entry, sentence, "delete"), "inline-action-btn danger")
        );
        row.append(text, actions);
        customDetails.appendChild(row);
      });
      exampleBlock.appendChild(customDetails);
    }

    const details = document.createElement("details");
    details.className = "note-details";
    const noteCount = getNotes(entry).length;
    details.open = isDetailOpen(entry, "notes", Boolean(noteCount));
    details.addEventListener("toggle", () => saveDetailOpen(entry, "notes", details.open));
    const summary = document.createElement("summary");
    summary.innerHTML = `<span>独立笔记（${noteCount} 条）</span><button class="add-note-btn" type="button" title="新增笔记">＋</button>`;
    summary.querySelector(".add-note-btn").addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      addBlankNote(entry);
    });
    const noteList = document.createElement("div");
    noteList.className = "note-list";
    const notes = getNotes(entry);
    if (!notes.length) {
      const empty = document.createElement("div");
      empty.className = "empty-note";
      empty.textContent = "暂无笔记，点击 ＋ 新增一条独立笔记。";
      noteList.appendChild(empty);
    }
    notes.forEach((note, index) => {
      const item = document.createElement("div");
      item.className = "note-item";
      const head = document.createElement("div");
      head.className = "note-item-head";
      const linkCount = (note.links || []).length;
      const labelEl = document.createElement("span");
      labelEl.textContent = `笔记 ${index + 1}${linkCount ? ` · 已关联 ${linkCount}` : ""}`;
      const actions = document.createElement("div");
      actions.className = "inline-actions";
      actions.append(
        actionButton("💬", "把这条笔记转换为自定义例句，并删除原笔记", () => saveNoteAsExample(entry, note)),
        actionButton("🔗", "关联到其他单词；可选择同步或副本", () => linkNoteToAnotherWord(entry, note)),
        actionButton("🗑", "删除这条独立笔记", () => deleteSingleNote(entry, note), "inline-action-btn danger")
      );
      head.append(labelEl, actions);
      const textarea = document.createElement("textarea");
      textarea.value = note.text || "";
      textarea.placeholder = "输入这一条独立笔记…";
      textarea.addEventListener("blur", () => saveSingleNote(entry, note, textarea.value.trim()));
      item.append(head, textarea);
      noteList.appendChild(item);
    });
    details.append(summary, noteList);

    const chips = document.createElement("div");
    chips.className = "chips";
    chips.textContent = `复习次数 ${entry.status?.review_count ?? 0} ${entry.status?.last_reviewed ? `| 最近 ${entry.status.last_reviewed}` : ''}`;

    const cardParts = [meta, tags, trans];
    if (ecdictMeta.childElementCount) cardParts.push(ecdictMeta);
    cardParts.push(exampleBlock, checkbox, chips, details);
    card.append(...cardParts);
    wordGridEl.appendChild(card);
  });
}

async function performSemanticSearch() {
  const query = semanticSearchInput.value.trim();
  if (!query) {
    searchResultsEl.innerHTML = '';
    searchResultsEl.style.display = 'none';
    return;
  }
  searchResultsEl.innerHTML = '<div class="result-item muted">搜索中…</div>';
  searchResultsEl.style.display = 'block';
  const res = await fetch(`${API_BASE}/search/${encodeURIComponent(query)}?limit=12`);
  if (!res.ok) {
    searchResultsEl.innerHTML = '<div class="result-item">搜索失败</div>';
    searchResultsEl.style.display = 'block';
    return;
  }
  const data = await res.json();
  if ((!data.related || !data.related.length) && relations[query.toLowerCase()]) {
    renderSemanticResults(relations[query.toLowerCase()]);
    return;
  }
  renderSemanticResults(data);
}

function renderSemanticResults(data) {
  searchResultsEl.innerHTML = '';
  searchResultsEl.style.display = 'block';
  const relatedDiv = document.createElement('div');
  relatedDiv.innerHTML = '<h4>相关单词：</h4>';
  (data.related || []).forEach(r => {
    const item = document.createElement('div');
    item.className = 'result-item';
    item.innerHTML = `<strong>${r.word}</strong> <span>${r.translation || ''}</span><small>${r.unit} · ${(r.similarity || 0).toFixed(2)}</small>`;
    item.addEventListener('click', () => {
      jumpToSearchResult(r.unit, r.word);
    });
    relatedDiv.appendChild(item);
  });
  const oppositeDiv = document.createElement('div');
  oppositeDiv.innerHTML = '<h4>相反单词：</h4>';
  (data.opposite || []).forEach(o => {
    const item = document.createElement('div');
    item.className = 'result-item';
    item.innerHTML = `<strong>${o.word}</strong> <span>${o.translation || ''}</span><small>${o.unit} · ${(o.similarity || 0).toFixed(2)}</small>`;
    item.addEventListener('click', () => {
      jumpToSearchResult(o.unit, o.word);
    });
    oppositeDiv.appendChild(item);
  });
  if (!(data.related || []).length && !(data.opposite || []).length) {
    searchResultsEl.innerHTML = '<div class="result-item">未找到，可换中文释义或英文词根试试</div>';
    return;
  }
  searchResultsEl.append(relatedDiv, oppositeDiv);
}

async function performWordSearch() {
  const query = wordSearchInput.value.trim().toLowerCase();
  if (!query) {
    searchResultsEl.innerHTML = '';
    searchResultsEl.style.display = 'none';
    return;
  }

  let matches = localSearch(query, 12);

  if (!matches.length) {
    searchResultsEl.innerHTML = '<div class="result-item">未找到</div>';
    searchResultsEl.style.display = 'block';
    return;
  }

  renderSearchResults(matches);
}

function renderSearchResults(matches) {
  searchResultsEl.innerHTML = '';
  searchResultsEl.style.display = 'block';

  matches.slice(0, 12).forEach((match) => {
    const item = document.createElement('div');
    item.className = 'result-item';
    item.innerHTML = `<strong>${match.word}</strong><span>${match.translation || ''}</span><small>${match.unit}</small>`;
    item.addEventListener('click', () => {
      jumpToSearchResult(match.unit, match.word);
      if (match.word) {
        wordSearchInput.value = match.word;
      }
    });
    searchResultsEl.appendChild(item);
  });
}

async function showDashboard() {
  dashboardEl.style.display = "block";
  wordGridEl.style.display = "none";
  menuBar.style.display = "flex";
  backToWords.style.display = "inline-block";
  const res = await apiFetch(`/dashboard`);
  if (!res.ok) return;
  const data = await res.json();
  dashboardCardsEl.innerHTML = `
    <div class="dash-card"><span>总词量</span><strong>${data.total_words}</strong></div>
    <div class="dash-card"><span>今日复习</span><strong>${data.reviewed_today}</strong></div>
    <div class="dash-card"><span>已掌握</span><strong>${data.past_memorized}</strong></div>
    <div class="dash-card"><span>复习率</span><strong>${data.review_rate.toFixed(1)}%</strong></div>
  `;
  const ctx = chartCanvas.getContext('2d');
  if (dashboardChart) dashboardChart.destroy();
  dashboardChart = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: ['总词量', '今日复习', '过去掌握', '复习率'],
      datasets: [{
        label: '统计',
        data: [data.total_words, data.reviewed_today, data.past_memorized, data.review_rate],
        backgroundColor: ['#2563eb', '#f97316', '#16a34a', '#8b5cf6'],
        borderRadius: 12
      }]
    },
    options: { responsive: true, plugins: { legend: { display: false } } }
  });
}

function hideDashboard() {
  dashboardEl.style.display = "none";
  wordGridEl.style.display = "block";
  menuBar.style.display = "flex";
  backToWords.style.display = "none";
}

if (unitFilterInput) {
  unitFilterInput.addEventListener("input", renderUnitList);
}
searchBtn.addEventListener("click", performWordSearch);
semanticSearchBtn.addEventListener("click", performSemanticSearch);
wordSearchInput.addEventListener("input", () => {
  clearTimeout(wordSearchInput._timer);
  wordSearchInput._timer = setTimeout(performWordSearch, 120);
});
semanticSearchInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter") performSemanticSearch();
});
dashboardBtn.addEventListener("click", showDashboard);
backToWords.addEventListener("click", hideDashboard);
searchBackBtn.addEventListener("click", () => {
  const state = searchHistory.pop();
  if (!state) return updateSearchBackButton();
  const target = state.unit;
  restoreScrollY = state.scrollY ?? 0;
  highlightWord = state.word || null;
  updateSearchBackButton();
  loadUnit(target);
});
document.addEventListener("click", (event) => {
  if (!event.target.closest(".note-menu") && !event.target.closest(".note-menu-btn")) {
    closeAllMenus();
  }
});
document.addEventListener("focusin", (event) => {
  if (!event.target.closest(".note-menu") && !event.target.closest(".note-menu-btn")) {
    closeAllMenus();
  }
});
themeToggle.addEventListener("click", () => {
  document.body.classList.toggle("dark");
  const dark = document.body.classList.contains("dark");
  localStorage.setItem("vocab_theme", dark ? "dark" : "light");
  themeToggle.textContent = dark ? "☀️ 浅色模式" : "🌙 黑暗模式";
});
if (localStorage.getItem("vocab_theme") === "dark") {
  document.body.classList.add("dark");
  themeToggle.textContent = "☀️ 浅色模式";
}
summaryTextarea.addEventListener("blur", saveSummary);
refreshSummaryButton.addEventListener("click", () => loadSummary(currentUnit));
fetchUnits().then(async () => {
  await loadAllWords();
  await loadRelations();
}).catch((e) => console.error(e));
