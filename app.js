const state = {
  stats: null,
  materials: [],
  total: 0,
  limit: 24,
  offset: 0,
  selectedMaterialId: null,
  currentGraph: null,
  graphLayout: "force",
  graphLabels: "show",
  graphAnimation: null,
  interpretAnimation: null,
  compareSelected: new Map(),
  compareDetails: new Map(),
  compareSearchResults: [],
  compareVizMode: "both",
  authMode: "login",
  authUser: null,
};

const COMPARE_LIMIT = 30;
const AUTH_USERS_KEY = "m3kg_auth_users";
const AUTH_SESSION_KEY = "m3kg_auth_session";

const relationLabels = {
  HAS_TASTE: "味",
  HAS_NATURE: "性",
  HAS_POTENCY: "效能",
  HAS_FUNCTION: "功能",
  TREATS_INDICATION: "主治",
  HAS_PHARMACOGNOSTIC_ORIGIN: "基源分类",
  BELONGS_TO_GENUS: "隶属属",
  BELONGS_TO_FAMILY: "隶属科",
};

const provincePositions = {
  北京: [74, 29],
  天津: [76, 32],
  河北: [72, 35],
  山西: [65, 37],
  内蒙古: [58, 24],
  辽宁: [83, 28],
  吉林: [88, 21],
  黑龙江: [87, 12],
  上海: [82, 55],
  江苏: [79, 52],
  浙江: [80, 61],
  安徽: [74, 55],
  福建: [77, 70],
  江西: [70, 66],
  山东: [78, 42],
  河南: [66, 48],
  湖北: [64, 58],
  湖南: [62, 68],
  广东: [66, 80],
  广西: [56, 79],
  海南: [60, 91],
  重庆: [52, 61],
  四川: [43, 60],
  贵州: [52, 72],
  云南: [43, 80],
  西藏: [23, 62],
  陕西: [58, 48],
  甘肃: [43, 43],
  青海: [34, 48],
  宁夏: [53, 39],
  新疆: [18, 31],
  台湾: [84, 76],
  香港: [70, 84],
  澳门: [67, 85],
};

const graphRelationOrder = ["HAS_TASTE", "HAS_NATURE", "HAS_POTENCY", "HAS_FUNCTION", "TREATS_INDICATION"];

const graphRelationPalette = {
  HAS_TASTE: { label: "味", color: "#d88924", type: "Taste" },
  HAS_NATURE: { label: "性", color: "#2f7f83", type: "Nature" },
  HAS_POTENCY: { label: "效能", color: "#7866b2", type: "PotencyFeature" },
  HAS_FUNCTION: { label: "功能", color: "#2f8a5f", type: "FunctionTerm" },
  TREATS_INDICATION: { label: "主治", color: "#c65c5c", type: "IndicationTerm" },
};

const nodeColors = {
  MongolianMedicinalPiece: "#134f3a",
  Taste: graphRelationPalette.HAS_TASTE.color,
  Nature: graphRelationPalette.HAS_NATURE.color,
  PotencyFeature: graphRelationPalette.HAS_POTENCY.color,
  FunctionTerm: graphRelationPalette.HAS_FUNCTION.color,
  IndicationTerm: graphRelationPalette.TREATS_INDICATION.color,
};

let chinaGeoJsonPromise = null;

const tasteProfiles = {
  苦: { score: 0.92, tag: "清降燥化" },
  甘: { score: 0.86, tag: "补益缓和" },
  辛: { score: 0.78, tag: "发散行气" },
  涩: { score: 0.72, tag: "收敛固涩" },
  咸: { score: 0.64, tag: "软坚下行" },
  酸: { score: 0.6, tag: "收敛生津" },
  淡: { score: 0.46, tag: "渗利和缓" },
};

const natureScores = {
  寒: { score: -2, tag: "寒凉清热" },
  凉: { score: -1, tag: "偏凉清解" },
  平: { score: 0, tag: "平和调衡" },
  温: { score: 1, tag: "温散助阳" },
  热: { score: 2, tag: "温热峻烈" },
  微寒: { score: -0.5, tag: "微寒清解" },
  微温: { score: 0.5, tag: "微温和散" },
};

const originTypeProfiles = [
  { label: "矿物", pattern: /mineral|mineralia|矿物|无机|石膏|硫黄|朱砂|赭石|磁石|滑石|芒硝|石盐/i },
  { label: "植物", pattern: /viridiplantae|plantae|streptophyta|tracheophyta|magnoliopsida|植物|被子植物|裸子植物/i },
  { label: "动物", pattern: /metazoa|animalia|chordata|arthropoda|mollusca|annelida|insecta|mammalia|动物/i },
  { label: "真菌", pattern: /fungi|mycota|真菌/i },
];

const compareTypeColors = {
  植物: "#2f8a5f",
  动物: "#7866b2",
  矿物: "#7a5a12",
  真菌: "#2f7f83",
  未定: "#7e8b84",
};

const $ = (selector) => document.querySelector(selector);

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function truncate(value, length = 180) {
  const text = String(value ?? "");
  return text.length > length ? `${text.slice(0, length)}...` : text;
}

async function api(path, params = {}) {
  const url = new URL(path, window.location.origin);
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") {
      url.searchParams.set(key, value);
    }
  });
  const response = await fetch(url);
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error || `请求失败：${response.status}`);
  }
  return payload;
}

function showToast(message) {
  const toast = $("#toast");
  toast.textContent = message;
  toast.classList.remove("hidden");
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => toast.classList.add("hidden"), 3600);
}

function readAuthUsers() {
  try {
    const users = JSON.parse(localStorage.getItem(AUTH_USERS_KEY) || "[]");
    return Array.isArray(users) ? users : [];
  } catch {
    return [];
  }
}

function saveAuthUsers(users) {
  localStorage.setItem(AUTH_USERS_KEY, JSON.stringify(users));
}

function setAuthMessage(message = "", isError = false) {
  const messageNode = $("#authMessage");
  messageNode.textContent = message;
  messageNode.classList.toggle("error", isError);
}

function restoreAuthSession() {
  const username = localStorage.getItem(AUTH_SESSION_KEY);
  if (!username) {
    state.authUser = null;
    return;
  }
  state.authUser = readAuthUsers().find((user) => user.username === username) || null;
  if (!state.authUser) localStorage.removeItem(AUTH_SESSION_KEY);
}

function setAuthMode(mode) {
  state.authMode = mode === "register" ? "register" : "login";
  $("#authTitle").textContent = state.authMode === "register" ? "用户注册" : "用户登录";
  document.querySelectorAll("[data-auth-tab]").forEach((tab) => {
    tab.classList.toggle("active", tab.dataset.authTab === state.authMode);
  });
  $("#authLoginForm").classList.toggle("hidden", state.authMode !== "login");
  $("#authRegisterForm").classList.toggle("hidden", state.authMode !== "register");
  setAuthMessage("");
}

function renderAuthPanel() {
  const signedIn = Boolean(state.authUser);
  $("#authSignedIn").classList.toggle("hidden", !signedIn);
  $("#authForms").classList.toggle("hidden", signedIn);
  if (signedIn) {
    $("#authTitle").textContent = "用户中心";
    $("#authUserName").textContent = state.authUser.displayName || state.authUser.username;
  } else {
    setAuthMode(state.authMode);
  }
}

function updateAuthUi() {
  const button = $("#authOpenBtn");
  if (!button) return;
  if (state.authUser) {
    button.textContent = `用户：${state.authUser.displayName || state.authUser.username}`;
    button.classList.add("signed-in");
  } else {
    button.textContent = "登录/注册";
    button.classList.remove("signed-in");
  }
  renderAuthPanel();
}

function openAuthModal(mode = "login") {
  if (!state.authUser) setAuthMode(mode);
  renderAuthPanel();
  $("#authModal").classList.remove("hidden");
  const focusTarget = state.authUser
    ? $("#authLogoutBtn")
    : mode === "register"
      ? $("#registerDisplayName")
      : $("#loginUsername");
  focusTarget?.focus();
}

function closeAuthModal() {
  $("#authModal").classList.add("hidden");
  setAuthMessage("");
}

function handleLogin(event) {
  event.preventDefault();
  const username = $("#loginUsername").value.trim();
  const password = $("#loginPassword").value;
  const user = readAuthUsers().find((item) => item.username === username);
  if (!user || user.password !== password) {
    setAuthMessage("用户名或密码不正确。", true);
    return;
  }
  state.authUser = user;
  localStorage.setItem(AUTH_SESSION_KEY, user.username);
  $("#authLoginForm").reset();
  updateAuthUi();
  setAuthMessage("登录成功。");
  showToast(`已登录：${user.displayName || user.username}`);
}

function handleRegister(event) {
  event.preventDefault();
  const displayName = $("#registerDisplayName").value.trim();
  const username = $("#registerUsername").value.trim();
  const email = $("#registerEmail").value.trim();
  const password = $("#registerPassword").value;
  const passwordConfirm = $("#registerPasswordConfirm").value;
  if (username.length < 3) {
    setAuthMessage("用户名至少需要 3 个字符。", true);
    return;
  }
  if (password.length < 6) {
    setAuthMessage("密码至少需要 6 个字符。", true);
    return;
  }
  if (password !== passwordConfirm) {
    setAuthMessage("两次输入的密码不一致。", true);
    return;
  }
  const users = readAuthUsers();
  if (users.some((user) => user.username === username)) {
    setAuthMessage("该用户名已存在。", true);
    return;
  }
  const user = {
    username,
    displayName: displayName || username,
    email,
    password,
    createdAt: new Date().toISOString(),
  };
  users.push(user);
  saveAuthUsers(users);
  state.authUser = user;
  localStorage.setItem(AUTH_SESSION_KEY, user.username);
  $("#authRegisterForm").reset();
  updateAuthUi();
  setAuthMessage("注册成功，已登录。");
  showToast(`已注册并登录：${user.displayName || user.username}`);
}

function logoutAuthUser() {
  const label = state.authUser?.displayName || state.authUser?.username || "";
  state.authUser = null;
  localStorage.removeItem(AUTH_SESSION_KEY);
  updateAuthUi();
  setAuthMode("login");
  setAuthMessage(label ? `已退出：${label}` : "已退出登录。");
}

function fillSelect(select, values, label) {
  select.innerHTML = `<option value="">${escapeHtml(label)}</option>`;
  values.forEach((value) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = value;
    select.appendChild(option);
  });
}

function downloadText(filename, text, type = "text/plain;charset=utf-8") {
  const blob = new Blob([text], { type });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

function selectedFilters() {
  return {
    query: $("#queryInput").value.trim(),
    term_category: $("#termCategoryFilter").value,
    property_class: $("#propertyClassFilter").value,
    source_type: $("#sourceTypeFilter").value,
    kingdom: $("#kingdomFilter").value,
  };
}

async function loadStats() {
  state.stats = await api("/api/stats");
  const facets = state.stats.facets;
  fillSelect($("#termCategoryFilter"), facets.term_category || [], "全部术语类别");
  fillSelect($("#propertyClassFilter"), facets.property_class || [], "全部药性类别");
  fillSelect($("#sourceTypeFilter"), facets.source_type || [], "全部来源类型");
  fillSelect($("#kingdomFilter"), facets.kingdom || [], "全部 Kingdom");

  const metadata = state.stats.metadata;
  $("#heroStats").innerHTML = [
    ["蒙药饮片", metadata.material_count],
    ["蒙医术语", metadata.terminology_count],
    ["药性记录", metadata.medicinal_property_count],
    ["基源映射", metadata.mmp_po_count],
  ]
    .map(
      ([label, value]) => `
        <div class="hero-stat">
          <strong>${escapeHtml(value)}</strong>
          <span>${escapeHtml(label)}</span>
        </div>
      `,
    )
    .join("");
}

async function loadMaterials(reset = false) {
  if (reset) state.offset = 0;
  const payload = await api("/api/materials", {
    ...selectedFilters(),
    limit: state.limit,
    offset: state.offset,
  });
  state.materials = payload.items;
  state.total = payload.total;
  renderMaterials();
  updatePager();
  syncCompareButtons();

  if (!state.selectedMaterialId && state.materials.length) {
    openMaterial(state.materials[0].material_id);
  } else if (state.selectedMaterialId) {
    markActiveCard();
  }
}

function renderMaterials() {
  const list = $("#materialList");
  $("#resultCount").textContent = `${state.total} 条`;
  if (!state.materials.length) {
    list.innerHTML = `<div class="empty-state"><p>未找到匹配药材。</p></div>`;
    return;
  }

  list.innerHTML = state.materials
    .map((item) => {
      const active = item.material_id === state.selectedMaterialId ? " active" : "";
      const inCompare = state.compareSelected.has(item.material_id);
      const badges = [
        item.flavors_text && `味：${item.flavors_text}`,
        item.natures_text && `性：${item.natures_text}`,
        item.potencies_text && `效能：${item.potencies_text}`,
        item.source_type_text && `来源：${item.source_type_text}`,
      ]
        .filter(Boolean)
        .map((value) => badge(value))
        .join("");
      return `
        <article class="material-card${active}" data-material-id="${escapeHtml(item.material_id)}">
          <div class="card-title">
            <strong>${escapeHtml(item.label || item.material_id)}</strong>
            <span class="muted">${escapeHtml(item.material_id)}</span>
          </div>
          <div class="badge-row">${badges}</div>
          <p class="card-summary">${escapeHtml(item.terms_text || item.origins_text || "")}</p>
          <div class="card-actions">
            <button class="compare-add-btn secondary" type="button" data-material-id="${escapeHtml(item.material_id)}" ${inCompare ? "disabled" : ""}>
              ${inCompare ? "已加入对比" : "加入对比"}
            </button>
          </div>
        </article>
      `;
    })
    .join("");

  list.querySelectorAll(".material-card").forEach((card) => {
    card.addEventListener("click", () => openMaterial(card.dataset.materialId));
  });
  list.querySelectorAll(".compare-add-btn").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      const material = state.materials.find((item) => item.material_id === button.dataset.materialId);
      addCompareMaterial(button.dataset.materialId, material).catch((error) => showToast(error.message));
    });
  });
}

function updatePager() {
  const current = Math.floor(state.offset / state.limit) + 1;
  const pages = Math.max(1, Math.ceil(state.total / state.limit));
  $("#pageInfo").textContent = `${current} / ${pages}`;
  $("#prevBtn").disabled = state.offset <= 0;
  $("#nextBtn").disabled = state.offset + state.limit >= state.total;
}

function markActiveCard() {
  document.querySelectorAll(".material-card").forEach((card) => {
    card.classList.toggle("active", card.dataset.materialId === state.selectedMaterialId);
  });
}

function badge(value) {
  const text = String(value);
  let type = "";
  if (text.includes("高") || text.includes("有毒") || text.includes("待复核")) type = " warn";
  if (text.includes("否-未命中") || text.includes("未见")) type = " danger";
  return `<span class="badge${type}">${escapeHtml(text)}</span>`;
}

function inferOriginType(origin) {
  const explicitType = String(origin?.source_type || "").trim();
  if (explicitType) return explicitType;
  const taxonomyText = [
    origin?.source_type,
    origin?.kingdom_name,
    origin?.phylum_name,
    origin?.class_name,
    origin?.order_name,
    origin?.family_name,
    origin?.genus_name,
    origin?.species_name,
  ]
    .filter(Boolean)
    .join(" ");
  const profile = originTypeProfiles.find((item) => item.pattern.test(taxonomyText));
  return profile?.label || "未定";
}

function summarizeOriginTypes(origins) {
  if (!origins?.length) return "";
  const types = [...new Set(origins.map(inferOriginType).filter((value) => value && value !== "未定"))];
  return types.length ? types.join("、") : "未定";
}

function splitTermText(value) {
  return String(value || "")
    .split(/[；;、，,\/\s]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function uniqueValues(values) {
  return [...new Set(values.map((value) => String(value || "").trim()).filter(Boolean))];
}

function compactText(values, max = 8) {
  const items = uniqueValues(values);
  if (!items.length) return "未记录";
  const head = items.slice(0, max).join("；");
  return items.length > max ? `${head} 等${items.length}项` : head;
}

function summarizeOriginClassification(origins, material) {
  if (!origins?.length) return material?.origins_text || "未记录";
  const labels = origins.map((origin) =>
    [
      origin.kingdom_name || "kingdom未记录",
      origin.species_name || "species未记录",
      origin.species_id || "ID未记录",
    ].join(" / "),
  );
  return compactText(labels, 12);
}

function renderSourceDescription(material) {
  const text = String(material?.source_description_text || "").trim();
  const container = $("#sourceDescription");
  if (!text) {
    container.classList.add("hidden");
    container.innerHTML = "";
    return;
  }
  container.classList.remove("hidden");
  container.innerHTML = `
    <p class="eyebrow">药材基源来源</p>
    <p>${escapeHtml(text)}</p>
  `;
}

function termsByRelation(detail, relation) {
  const labels = (detail?.terms || [])
    .filter((term) => term.relation === relation)
    .map((term) => term.term_label);
  return uniqueValues(labels);
}

function compareEntryFromDetail(detail) {
  const material = detail.material || {};
  const tasteLabels = termsByRelation(detail, "HAS_TASTE");
  const natureLabels = termsByRelation(detail, "HAS_NATURE");
  const tasteItems = (tasteLabels.length ? tasteLabels : splitTermText(material.flavors_text)).map(quantifyTaste);
  const natureItems = (natureLabels.length ? natureLabels : splitTermText(material.natures_text)).map(quantifyNature);
  const origins = detail.origins || [];
  return {
    id: material.material_id,
    label: material.label || material.material_id,
    sourceType: summarizeOriginTypes(origins),
    flavors: material.flavors_text || compactText(tasteLabels),
    natures: material.natures_text || compactText(natureLabels),
    tasteMean: average(tasteItems.map((item) => item.score)),
    natureMean: average(natureItems.map((item) => item.score)),
    functions: material.functions_text || compactText(termsByRelation(detail, "HAS_FUNCTION")),
    indications: material.indications_text || compactText(termsByRelation(detail, "TREATS_INDICATION")),
    sourceDescription: material.source_description_text || "未记录",
    origins: summarizeOriginClassification(origins, material),
  };
}

function compareSelectedIds() {
  return [...state.compareSelected.keys()];
}

async function openMaterial(materialId) {
  state.selectedMaterialId = materialId;
  markActiveCard();
  $("#emptyState").classList.add("hidden");
  $("#detailView").classList.remove("hidden");
  $("#detailTitle").textContent = "加载中";
  $("#relationSummary").innerHTML = "";
  $("#regionList").innerHTML = "";
  $("#sourceDescription").innerHTML = "";
  $("#sourceDescription").classList.add("hidden");
  $("#graphSvg").innerHTML = "";

  try {
    const [detail, graph] = await Promise.all([
      api(`/api/materials/${encodeURIComponent(materialId)}`),
      api(`/api/graph/${encodeURIComponent(materialId)}`),
    ]);
    renderDetail(detail);
    state.currentGraph = graph;
    renderGraph(graph);
  } catch (error) {
    showToast(error.message);
  }
}

function renderDetail(payload) {
  const material = payload.material;
  const originSource = summarizeOriginTypes(payload.origins || []);
  $("#detailId").textContent = material.material_id;
  $("#detailTitle").textContent = material.label || material.material_id;
  $("#detailBadges").innerHTML = [
    material.flavors_text && `味：${material.flavors_text}`,
    material.natures_text && `性：${material.natures_text}`,
    material.potencies_text && `效能：${material.potencies_text}`,
    (material.source_type_text || originSource) && `来源：${material.source_type_text || originSource}`,
  ]
    .filter(Boolean)
    .map((value) => badge(value))
    .join("");

  renderRelations(payload.relation_summary || []);
  renderSourceDescription(material);
  renderOrigins(payload.origins || []);
  renderInterpretation(payload);
  syncCompareButtons();
}

function renderRelations(rows) {
  const visibleRows = rows.filter((row) => row.relation !== "HAS_PHARMACOGNOSTIC_ORIGIN");
  if (!visibleRows.length) {
    $("#relationSummary").innerHTML = `<p class="muted">无关系聚合。</p>`;
    return;
  }
  $("#relationSummary").innerHTML = visibleRows
    .map(
      (row) => `
        <div class="relation-item">
          <strong>${escapeHtml(relationLabels[row.relation] || row.relation)}</strong>
          <span>${escapeHtml(row.terms)}</span>
        </div>
      `,
    )
    .join("");
}

function renderOrigins(rows) {
  if (!rows.length) {
    $("#regionList").innerHTML = `<p class="muted">当前药材无 restored table 基源分类记录。</p>`;
    return;
  }
  $("#regionList").innerHTML = rows
    .map((row) => {
      const originType = inferOriginType(row);
      const speciesName = row.species_name || "species未记录";
      const speciesId = row.species_id || "ID未记录";
      const kingdomName = row.kingdom_name || "kingdom未记录";
      return `
        <article class="origin-card">
          <div class="origin-card-head">
            <strong>${escapeHtml(speciesName)}</strong>
            <span class="origin-type-pill">${escapeHtml(originType)}</span>
          </div>
          <div class="origin-grid">
            <div class="origin-field">
              <span>来源类型</span>
              <b>${escapeHtml(originType)}</b>
            </div>
            <div class="origin-field">
              <span>kingdom_Name</span>
              <b>${escapeHtml(kingdomName)}</b>
            </div>
            <div class="origin-field origin-field-wide">
              <span>species_name</span>
              <b>${escapeHtml(speciesName)}</b>
            </div>
            <div class="origin-field">
              <span>species_ID</span>
              <b>${escapeHtml(speciesId)}</b>
            </div>
          </div>
        </article>
      `;
    })
    .join("");
}

function colorForCompareType(sourceType) {
  const type = String(sourceType || "未定").split("、")[0] || "未定";
  return compareTypeColors[type] || compareTypeColors.未定;
}

function compareEntryFromSeed(seed) {
  const tasteItems = splitTermText(seed?.flavors_text).map(quantifyTaste);
  const natureItems = splitTermText(seed?.natures_text).map(quantifyNature);
  return {
    id: seed?.material_id || "",
    label: seed?.label || seed?.material_id || "",
    sourceType: seed?.source_type_text || "加载中",
    flavors: seed?.flavors_text || "加载中",
    natures: seed?.natures_text || "加载中",
    tasteMean: average(tasteItems.map((item) => item.score)),
    natureMean: average(natureItems.map((item) => item.score)),
    functions: seed?.functions_text || "加载中",
    indications: seed?.indications_text || "加载中",
    sourceDescription: seed?.source_description_text || "加载中",
    origins: seed?.origins_text || "加载中",
  };
}

function compareEntries() {
  return compareSelectedIds().map((id) => {
    const detail = state.compareDetails.get(id);
    if (detail) return compareEntryFromDetail(detail);
    return compareEntryFromSeed(state.compareSelected.get(id));
  });
}

async function addCompareMaterial(materialId, seed = {}) {
  if (!materialId) return;
  if (state.compareSelected.has(materialId)) {
    showToast("该药材已在对比列表中。");
    return;
  }
  if (state.compareSelected.size >= COMPARE_LIMIT) {
    showToast(`最多可选择 ${COMPARE_LIMIT} 味药材。`);
    return;
  }
  state.compareSelected.set(materialId, { material_id: materialId, label: seed?.label || materialId, ...seed });
  renderCompare();
  syncCompareButtons();
  await loadCompareDetails([materialId]);
}

function removeCompareMaterial(materialId) {
  state.compareSelected.delete(materialId);
  state.compareDetails.delete(materialId);
  renderCompare();
  syncCompareButtons();
}

function clearCompareMaterials() {
  state.compareSelected.clear();
  state.compareDetails.clear();
  renderCompare();
  syncCompareButtons();
}

async function loadCompareDetails(ids = compareSelectedIds()) {
  const missing = ids.filter((id) => state.compareSelected.has(id) && !state.compareDetails.has(id));
  if (!missing.length) return;
  const payload = await api("/api/compare", { ids: missing.join(",") });
  (payload.items || []).forEach((detail) => {
    const materialId = detail.material?.material_id;
    if (!materialId) return;
    state.compareDetails.set(materialId, detail);
    if (state.compareSelected.has(materialId)) {
      state.compareSelected.set(materialId, { ...state.compareSelected.get(materialId), ...detail.material });
    }
  });
  if (payload.missing?.length) showToast(`未找到 ${payload.missing.length} 个药材编号。`);
  renderCompare();
  syncCompareButtons();
}

function syncCompareButtons() {
  const count = state.compareSelected.size;
  document.querySelectorAll(".compare-add-btn").forEach((button) => {
    const selected = state.compareSelected.has(button.dataset.materialId);
    button.disabled = selected || (!selected && count >= COMPARE_LIMIT);
    button.textContent = selected ? "已加入对比" : count >= COMPARE_LIMIT ? "已达30味" : "加入对比";
  });

  const detailButton = $("#addDetailCompareBtn");
  if (detailButton) {
    const selected = state.selectedMaterialId && state.compareSelected.has(state.selectedMaterialId);
    detailButton.disabled = !state.selectedMaterialId || selected || (!selected && count >= COMPARE_LIMIT);
    detailButton.textContent = selected ? "已加入对比" : count >= COMPARE_LIMIT ? "已达30味" : "加入对比";
  }
  if (state.compareSearchResults.length) renderCompareSearchResults();
}

function renderCompare() {
  const entries = compareEntries();
  $("#compareMeta").textContent = `已选择 ${entries.length}/${COMPARE_LIMIT} 味药材，对比味、性、功能、主治和基源分类。`;
  renderCompareSelected(entries);
  renderCompareVisualization(entries);
  renderCompareTable(entries);
}

function renderCompareSelected(entries) {
  if (!entries.length) {
    $("#compareSelected").innerHTML = `
      <div class="compare-empty">
        从检索结果、药材详情或上方搜索框加入药材后，可在这里进行多药材并列比较。
      </div>
    `;
    return;
  }
  $("#compareSelected").innerHTML = entries
    .map(
      (entry) => `
        <span class="compare-chip">
          <b>${escapeHtml(entry.label)}</b>
          <small>${escapeHtml(entry.id)}</small>
          <button type="button" data-remove-compare="${escapeHtml(entry.id)}" aria-label="移除${escapeHtml(entry.label)}">×</button>
        </span>
      `,
    )
    .join("");
  $("#compareSelected").querySelectorAll("[data-remove-compare]").forEach((button) => {
    button.addEventListener("click", () => removeCompareMaterial(button.dataset.removeCompare));
  });
}

function renderCompareSearchResults(rows = state.compareSearchResults) {
  if (!rows.length) {
    $("#compareSearchResults").innerHTML = `<span class="muted">搜索结果会显示在这里，可直接加入对比。</span>`;
    return;
  }
  $("#compareSearchResults").innerHTML = rows
    .map((item) => {
      const selected = state.compareSelected.has(item.material_id);
      const limitReached = !selected && state.compareSelected.size >= COMPARE_LIMIT;
      return `
        <button class="compare-result ${selected ? "selected" : ""}" type="button" data-material-id="${escapeHtml(item.material_id)}" ${selected || limitReached ? "disabled" : ""}>
          <strong>${escapeHtml(item.label || item.material_id)}</strong>
          <span>${selected ? "已加入" : limitReached ? "已达30味" : escapeHtml(item.material_id)}</span>
        </button>
      `;
    })
    .join("");
  $("#compareSearchResults").querySelectorAll(".compare-result").forEach((button) => {
    button.addEventListener("click", () => {
      const item = rows.find((row) => row.material_id === button.dataset.materialId);
      addCompareMaterial(button.dataset.materialId, item).catch((error) => showToast(error.message));
    });
  });
}

async function runCompareSearch() {
  const query = $("#compareQuery").value.trim();
  if (!query) {
    showToast("请输入药材名称、编号、功能、主治或基源关键词。");
    return;
  }
  const payload = await api("/api/materials", { query, limit: 12, offset: 0 });
  state.compareSearchResults = payload.items || [];
  renderCompareSearchResults();
}

function renderCompareVisualization(entries) {
  const mode = $("#compareVizMode").value;
  state.compareVizMode = mode;
  if (!entries.length) {
    $("#compareVizMeta").textContent = "";
    $("#compareVisualization").innerHTML = `<div class="compare-empty">请选择至少 1 味药材。</div>`;
    return;
  }
  $("#compareVizMeta").textContent =
    mode === "both" ? "横轴为味权重均值，纵轴为性寒热均值。" : mode === "taste" ? "按味权重均值排序。" : "按性寒热均值排序。";
  $("#compareVisualization").innerHTML =
    mode === "taste" ? renderCompareTasteBars(entries) : mode === "nature" ? renderCompareNatureBars(entries) : renderCompareScatter(entries);
}

function renderCompareScatter(entries) {
  const width = 980;
  const height = 430;
  const margin = { left: 72, right: 28, top: 34, bottom: 58 };
  const plotWidth = width - margin.left - margin.right;
  const plotHeight = height - margin.top - margin.bottom;
  const xFor = (value) => margin.left + Math.max(0, Math.min(1, value)) * plotWidth;
  const yFor = (value) => margin.top + (1 - (Math.max(-2, Math.min(2, value)) + 2) / 4) * plotHeight;
  const points = entries
    .map((entry, index) => {
      const x = xFor(entry.tasteMean);
      const y = yFor(entry.natureMean);
      const labelY = y + (index % 2 === 0 ? -12 : 18);
      return `
        <g class="compare-point">
          <circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="8" fill="${colorForCompareType(entry.sourceType)}"></circle>
          <text x="${Math.min(x + 12, width - 120).toFixed(1)}" y="${Math.max(18, Math.min(height - 16, labelY)).toFixed(1)}">${escapeHtml(truncate(entry.label, 8))}</text>
          <title>${escapeHtml(entry.label)}：味 ${formatNumber(entry.tasteMean)}，性 ${formatSigned(entry.natureMean)}，来源 ${escapeHtml(entry.sourceType)}</title>
        </g>
      `;
    })
    .join("");
  return `
    <svg class="compare-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="药物味性二维对比图">
      <line x1="${margin.left}" y1="${margin.top + plotHeight}" x2="${width - margin.right}" y2="${margin.top + plotHeight}" class="compare-axis"></line>
      <line x1="${margin.left}" y1="${margin.top}" x2="${margin.left}" y2="${margin.top + plotHeight}" class="compare-axis"></line>
      <line x1="${margin.left}" y1="${yFor(0)}" x2="${width - margin.right}" y2="${yFor(0)}" class="compare-grid-line"></line>
      <text x="${margin.left}" y="${height - 18}" class="compare-axis-label">味权重 0</text>
      <text x="${width - margin.right}" y="${height - 18}" text-anchor="end" class="compare-axis-label">味权重 1</text>
      <text x="18" y="${yFor(2)}" class="compare-axis-label">热 +2</text>
      <text x="18" y="${yFor(0) + 4}" class="compare-axis-label">平 0</text>
      <text x="18" y="${yFor(-2)}" class="compare-axis-label">寒 -2</text>
      ${points}
    </svg>
  `;
}

function renderCompareTasteBars(entries) {
  const sorted = [...entries].sort((a, b) => b.tasteMean - a.tasteMean);
  return renderCompareBars(sorted, {
    className: "taste-bars",
    label: "味权重",
    min: 0,
    max: 1,
    value: (entry) => entry.tasteMean,
    format: formatNumber,
    color: "#d88924",
  });
}

function renderCompareNatureBars(entries) {
  const sorted = [...entries].sort((a, b) => b.natureMean - a.natureMean);
  const width = 980;
  const rowHeight = 34;
  const height = 64 + sorted.length * rowHeight;
  const left = 150;
  const center = 535;
  const barWidth = 360;
  const rows = sorted
    .map((entry, index) => {
      const y = 45 + index * rowHeight;
      const value = Math.max(-2, Math.min(2, entry.natureMean));
      const w = Math.abs(value) / 2 * (barWidth / 2);
      const x = value >= 0 ? center : center - w;
      const color = value >= 0 ? "#c65c5c" : "#4f8fc4";
      return `
        <text x="18" y="${y + 5}" class="compare-bar-label">${escapeHtml(truncate(entry.label, 10))}</text>
        <rect x="${x.toFixed(1)}" y="${y - 11}" width="${Math.max(2, w).toFixed(1)}" height="18" rx="5" fill="${color}"></rect>
        <text x="${center + barWidth / 2 + 18}" y="${y + 5}" class="compare-value">${escapeHtml(formatSigned(entry.natureMean))}</text>
      `;
    })
    .join("");
  return `
    <svg class="compare-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="药物性寒热对比图">
      <text x="${left}" y="22" class="compare-axis-label">寒凉</text>
      <text x="${center}" y="22" text-anchor="middle" class="compare-axis-label">平</text>
      <text x="${center + barWidth / 2}" y="22" text-anchor="end" class="compare-axis-label">温热</text>
      <line x1="${center}" y1="34" x2="${center}" y2="${height - 18}" class="compare-grid-line"></line>
      ${rows}
    </svg>
  `;
}

function renderCompareBars(entries, options) {
  const width = 980;
  const rowHeight = 34;
  const height = 64 + entries.length * rowHeight;
  const labelWidth = 150;
  const barWidth = 680;
  const rows = entries
    .map((entry, index) => {
      const y = 45 + index * rowHeight;
      const value = Math.max(options.min, Math.min(options.max, options.value(entry)));
      const w = ((value - options.min) / (options.max - options.min || 1)) * barWidth;
      return `
        <text x="18" y="${y + 5}" class="compare-bar-label">${escapeHtml(truncate(entry.label, 10))}</text>
        <rect x="${labelWidth}" y="${y - 11}" width="${Math.max(2, w).toFixed(1)}" height="18" rx="5" fill="${options.color}"></rect>
        <text x="${labelWidth + barWidth + 18}" y="${y + 5}" class="compare-value">${escapeHtml(options.format(value))}</text>
      `;
    })
    .join("");
  return `
    <svg class="compare-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="药物${escapeHtml(options.label)}对比图">
      <text x="${labelWidth}" y="22" class="compare-axis-label">${escapeHtml(options.label)} ${options.min}</text>
      <text x="${labelWidth + barWidth}" y="22" text-anchor="end" class="compare-axis-label">${options.max}</text>
      ${rows}
    </svg>
  `;
}

function renderCompareTable(entries) {
  if (!entries.length) {
    $("#compareTableWrap").innerHTML = `<div class="compare-empty">暂无对比矩阵。</div>`;
    return;
  }
  const header = entries
    .map(
      (entry) => `
        <th>
          <strong>${escapeHtml(entry.label)}</strong>
          <span>${escapeHtml(entry.id)}</span>
        </th>
      `,
    )
    .join("");
  const row = (label, formatter) => `
    <tr>
      <th>${escapeHtml(label)}</th>
      ${entries.map((entry) => `<td>${escapeHtml(formatter(entry) || "未记录")}</td>`).join("")}
    </tr>
  `;
  $("#compareTableWrap").innerHTML = `
    <table class="compare-table">
      <thead>
        <tr><th>对比项</th>${header}</tr>
      </thead>
      <tbody>
        ${row("来源类型", (entry) => entry.sourceType)}
        ${row("味", (entry) => entry.flavors)}
        ${row("味权重均值", (entry) => formatNumber(entry.tasteMean))}
        ${row("性", (entry) => entry.natures)}
        ${row("性寒热均值", (entry) => formatSigned(entry.natureMean))}
        ${row("功能", (entry) => entry.functions)}
        ${row("主治", (entry) => entry.indications)}
        ${row("基源来源", (entry) => entry.sourceDescription)}
        ${row("基源分类", (entry) => entry.origins)}
      </tbody>
    </table>
  `;
}

function renderRegions(rows) {
  if (!rows.length) {
    $("#regionList").innerHTML = `<p class="muted">无 GBIF 省级分布记录。</p>`;
    return;
  }
  $("#regionList").innerHTML = `<p class="muted">正在加载中国省级边界底图...</p>`;
  loadChinaGeoJson()
    .then((geoJson) => {
      $("#regionList").innerHTML = renderChinaDistributionMap(rows, geoJson);
    })
    .catch(() => {
      $("#regionList").innerHTML = renderFallbackDistributionMap(rows);
    });
}

function renderChinaDistributionMap(rows, geoJson) {
  const width = 980;
  const height = 720;
  const max = Math.max(...rows.map((row) => Number(row.record_count || 0)), 1);
  const sorted = [...rows].sort((a, b) => Number(b.record_count || 0) - Number(a.record_count || 0));
  const valueByProvince = new Map(
    sorted.map((row) => [
      normalizeProvinceName(row.region),
      {
        region: row.region,
        value: Number(row.record_count || 0),
      },
    ]),
  );
  const features = (geoJson.features || []).filter((feature) => feature.properties?.name);
  const project = createGeoProjector(features, width, height, 28);
  const provincePaths = features
    .map((feature) => {
      const fullName = feature.properties.name;
      const shortName = normalizeProvinceName(fullName);
      const record = valueByProvince.get(shortName);
      const value = record?.value || 0;
      const active = value > 0 ? " active" : "";
      return `
        <path class="province-shape${active}" d="${geometryToSvgPath(feature.geometry, project)}" style="fill:${mapFillColor(value, max)}">
          <title>${escapeHtml(fullName)}：${value ? `${value} 条 GBIF 记录` : "未检出 GBIF 记录"}</title>
        </path>
      `;
    })
    .join("");
  const bubbles = sorted
    .map((row, index) => {
      const value = Number(row.record_count || 0);
      const feature = features.find((item) => normalizeProvinceName(item.properties.name) === normalizeProvinceName(row.region));
      const center = feature?.properties?.centroid || feature?.properties?.center;
      const pos = center ? project(center) : fallbackMapPosition(index, width, height);
      const radius = 5 + Math.sqrt(value / max) * 18;
      const shortName = provinceDisplayName(row.region);
      return `
        <g class="map-point" transform="translate(${pos.x.toFixed(1)} ${pos.y.toFixed(1)})">
          <circle class="map-pulse" r="${(radius + 4).toFixed(1)}"></circle>
          <circle class="map-dot" r="${radius.toFixed(1)}"></circle>
          <text y="${-(radius + 6).toFixed(1)}" text-anchor="middle">${escapeHtml(shortName)}</text>
          <title>${escapeHtml(row.region)}：${escapeHtml(value)} 条 GBIF 记录</title>
        </g>
      `;
    })
    .join("");
  const topItems = sorted
    .slice(0, 8)
    .map(
      (row) => `
        <div class="map-rank-item">
          <span>${escapeHtml(row.region)}</span>
          <strong>${escapeHtml(row.record_count || 0)}</strong>
        </div>
      `,
    )
    .join("");
  return `
    <div class="distribution-map-card">
      <svg class="distribution-map" viewBox="0 0 ${width} ${height}" role="img" aria-label="GBIF 中国省级分布标准地图">
        <g class="province-layer">${provincePaths}</g>
        ${bubbles}
        <g class="map-scale" transform="translate(22 642)">
          <text x="0" y="-10">GBIF 记录数</text>
          <rect x="0" y="0" width="34" height="12" class="scale-empty"></rect>
          <rect x="42" y="0" width="34" height="12" class="scale-low"></rect>
          <rect x="84" y="0" width="34" height="12" class="scale-mid"></rect>
          <rect x="126" y="0" width="34" height="12" class="scale-high"></rect>
          <text x="0" y="30">无记录</text>
          <text x="126" y="30">高</text>
        </g>
      </svg>
      <div class="map-rank">
        <div class="map-rank-title">标准中国省级边界底图 · 记录数 Top 省区</div>
        ${topItems}
      </div>
    </div>
  `;
}

function renderFallbackDistributionMap(rows) {
  const max = Math.max(...rows.map((row) => Number(row.record_count || 0)), 1);
  const sorted = [...rows].sort((a, b) => Number(b.record_count || 0) - Number(a.record_count || 0));
  const bubbles = sorted
    .map((row, index) => {
      const value = Number(row.record_count || 0);
      const pos = provincePositions[normalizeProvinceName(row.region)] || fallbackMapPosition(index, 100, 100);
      const radius = 4 + Math.sqrt(value / max) * 16;
      const x = Array.isArray(pos) ? pos[0] : pos.x;
      const y = Array.isArray(pos) ? pos[1] : pos.y;
      return `
        <g class="map-point" transform="translate(${x} ${y})">
          <circle class="map-pulse" r="${(radius + 4).toFixed(1)}"></circle>
          <circle class="map-dot" r="${radius.toFixed(1)}"></circle>
          <text y="${-(radius + 6).toFixed(1)}" text-anchor="middle">${escapeHtml(row.region)}</text>
          <title>${escapeHtml(row.region)}：${escapeHtml(value)} 条 GBIF 记录</title>
        </g>
      `;
    })
    .join("");
  const topItems = sorted
    .slice(0, 8)
    .map(
      (row) => `
        <div class="map-rank-item">
          <span>${escapeHtml(row.region)}</span>
          <strong>${escapeHtml(row.record_count || 0)}</strong>
        </div>
      `,
    )
    .join("");
  return `
    <div class="distribution-map-card">
      <svg class="distribution-map fallback" viewBox="0 0 100 100" role="img" aria-label="GBIF 省级分布动态地图">
        <path class="map-shape" d="M12 30 C18 15 37 9 55 14 C72 18 88 28 91 45 C94 62 81 77 64 85 C47 93 29 88 19 74 C8 60 5 45 12 30Z"></path>
        <path class="map-shape inner" d="M29 45 C36 36 50 33 62 38 C74 43 79 55 72 66 C65 78 48 80 37 72 C26 64 21 54 29 45Z"></path>
        ${bubbles}
      </svg>
      <div class="map-rank">
        <div class="map-rank-title">记录数 Top 省区</div>
        ${topItems}
      </div>
    </div>
  `;
}

function loadChinaGeoJson() {
  if (!chinaGeoJsonPromise) {
    chinaGeoJsonPromise = fetch("assets/china_100000_full.json").then((response) => {
      if (!response.ok) throw new Error("China map asset not found");
      return response.json();
    });
  }
  return chinaGeoJsonPromise;
}

function normalizeProvinceName(value) {
  const aliases = {
    NeiMonggol: "内蒙古",
    "Inner Mongolia": "内蒙古",
    Tibet: "西藏",
    Xizang: "西藏",
    Xinjiang: "新疆",
    Ningxia: "宁夏",
    Guangxi: "广西",
  };
  const text = String(value || "").trim();
  if (aliases[text]) return aliases[text];
  return text.replace(/壮族|回族|维吾尔|特别行政区|自治区|省|市/g, "");
}

function provinceDisplayName(value) {
  return normalizeProvinceName(value).slice(0, 4);
}

function createGeoProjector(features, width, height, padding) {
  const bounds = collectGeoBounds(features);
  const lonSpan = bounds.maxLon - bounds.minLon || 1;
  const latSpan = bounds.maxLat - bounds.minLat || 1;
  const scale = Math.min((width - padding * 2) / lonSpan, (height - padding * 2) / latSpan);
  const mapWidth = lonSpan * scale;
  const mapHeight = latSpan * scale;
  const offsetX = (width - mapWidth) / 2;
  const offsetY = (height - mapHeight) / 2;
  return ([lon, lat]) => ({
    x: offsetX + (lon - bounds.minLon) * scale,
    y: offsetY + (bounds.maxLat - lat) * scale,
  });
}

function collectGeoBounds(features) {
  const bounds = {
    minLon: Infinity,
    maxLon: -Infinity,
    minLat: Infinity,
    maxLat: -Infinity,
  };
  features.forEach((feature) => {
    visitGeoPoints(feature.geometry?.coordinates, ([lon, lat]) => {
      bounds.minLon = Math.min(bounds.minLon, lon);
      bounds.maxLon = Math.max(bounds.maxLon, lon);
      bounds.minLat = Math.min(bounds.minLat, lat);
      bounds.maxLat = Math.max(bounds.maxLat, lat);
    });
  });
  return bounds;
}

function visitGeoPoints(coords, visitor) {
  if (!Array.isArray(coords)) return;
  if (typeof coords[0] === "number") {
    visitor(coords);
    return;
  }
  coords.forEach((item) => visitGeoPoints(item, visitor));
}

function geometryToSvgPath(geometry, project) {
  if (!geometry) return "";
  const polygons = geometry.type === "Polygon" ? [geometry.coordinates] : geometry.coordinates || [];
  return polygons
    .map((rings) =>
      rings
        .map((ring) =>
          ring
            .map((point, index) => {
              const p = project(point);
              return `${index === 0 ? "M" : "L"}${p.x.toFixed(2)} ${p.y.toFixed(2)}`;
            })
            .join(" ") + " Z",
        )
        .join(" "),
    )
    .join(" ");
}

function mapFillColor(value, max) {
  if (!value) return "#f4f8f5";
  const ratio = Math.sqrt(Number(value) / Math.max(Number(max), 1));
  const light = 88 - ratio * 38;
  return `hsl(153 44% ${light.toFixed(1)}%)`;
}

function fallbackMapPosition(index, width = 100, height = 100) {
  const angle = (index * 137.5 * Math.PI) / 180;
  const radius = Math.min(width, height) * (0.18 + (index % 5) * 0.045);
  return {
    x: width * 0.52 + Math.cos(angle) * radius,
    y: height * 0.53 + Math.sin(angle) * radius,
  };
}

function renderGraph(graph) {
  stopAnimation("graphAnimation");
  const svg = $("#graphSvg");
  svg.innerHTML = "";
  const centerId = graph.center_id || `MongolianMedicinalPiece:${graph.material_id}`;
  const edges = (graph.edges || []).filter((edge) => graphRelationOrder.includes(edge.predicate));
  const visibleNodeIds = new Set([centerId]);
  edges.forEach((edge) => {
    visibleNodeIds.add(edge.source);
    visibleNodeIds.add(edge.target);
  });
  const nodes = (graph.nodes || []).filter((node) => visibleNodeIds.has(node.id));
  $("#graphMeta").textContent = `${nodes.length} 节点，${edges.length} 边`;
  if (!nodes.length) return;

  const width = 920;
  const height = 540;
  const nodeRelation = new Map();
  edges.forEach((edge) => {
    if (edge.source === centerId) nodeRelation.set(edge.target, edge.predicate);
  });
  const anchors = {
    [centerId]: { x: width / 2, y: height / 2, strength: 0.035 },
    HAS_TASTE: { x: 210, y: 180, strength: 0.012 },
    HAS_NATURE: { x: 240, y: 365, strength: 0.012 },
    HAS_POTENCY: { x: 462, y: 135, strength: 0.011 },
    HAS_FUNCTION: { x: 672, y: 245, strength: 0.01 },
    TREATS_INDICATION: { x: 716, y: 398, strength: 0.01 },
  };
  const simNodes = nodes.map((node, index) => {
    const relation = node.id === centerId ? centerId : nodeRelation.get(node.id);
    return {
      ...node,
      relation,
      radius: node.id === centerId ? 22 : 13,
      color: colorForGraphNode(node, nodeRelation, centerId),
      anchor: anchors[relation] || { x: width / 2, y: height / 2, strength: 0.006 },
      ...initialForcePosition(index, nodes.length, width, height, relation),
      vx: 0,
      vy: 0,
    };
  });
  const simEdges = edges.map((edge) => ({
    ...edge,
    color: graphRelationPalette[edge.predicate]?.color || "#9db4a6",
    label: relationLabels[edge.predicate] || edge.predicate,
    distance: edge.source === centerId ? 142 : 110,
  }));
  state.graphAnimation = renderForceNetwork(svg, simNodes, simEdges, {
    width,
    height,
    centerId,
    showLabels: state.graphLabels !== "hide",
    charge: 7600,
    linkStrength: 0.026,
    anchorStrength: 1,
    labelEvery: 999,
    nodeClass: "graph-node",
    labelClass: "graph-label",
    edgeClass: "graph-edge",
    edgeLabelClass: "graph-edge-label",
    title: "动态力导向：节点自动散开并按语义关系聚拢",
    titleY: 518,
  });
  renderGraphLegend(svg);
}

function placeSemantic(nodes, edges, centerId, center, position) {
  const buckets = new Map(graphRelationOrder.map((relation) => [relation, []]));
  const relationByNode = new Map();
  edges.forEach((edge) => {
    if (edge.source === centerId) relationByNode.set(edge.target, edge.predicate);
  });
  nodes.forEach((node) => {
    const relation = relationByNode.get(node.id);
    if (buckets.has(relation)) buckets.get(relation).push(node);
  });

  const lanes = [
    { relation: "HAS_TASTE", x: 270, top: 92, bottom: 228 },
    { relation: "HAS_NATURE", x: 270, top: 318, bottom: 448 },
    { relation: "HAS_POTENCY", x: 455, top: 88, bottom: 452 },
    { relation: "HAS_FUNCTION", x: 640, top: 70, bottom: 470 },
    { relation: "TREATS_INDICATION", x: 820, top: 70, bottom: 470 },
  ];
  lanes.forEach((lane) => placeColumnGroup(buckets.get(lane.relation) || [], lane.x, lane.top, lane.bottom, position));
}

function placeColumnGroup(nodes, x, top, bottom, position) {
  if (!nodes.length) return;
  const maxPerColumn = 12;
  const columnCount = Math.ceil(nodes.length / maxPerColumn);
  const columnGap = 58;
  nodes.forEach((node, index) => {
    const column = Math.floor(index / maxPerColumn);
    const row = index % maxPerColumn;
    const itemsInColumn = Math.min(maxPerColumn, nodes.length - column * maxPerColumn);
    const span = Math.max(bottom - top, 1);
    const y = itemsInColumn === 1 ? (top + bottom) / 2 : top + (span * row) / (itemsInColumn - 1);
    position.set(node.id, {
      x: x + (column - (columnCount - 1) / 2) * columnGap,
      y,
    });
  });
}

function colorForGraphNode(node, nodeRelation, centerId) {
  if (node.id === centerId) return nodeColors.MongolianMedicinalPiece;
  const relation = nodeRelation.get(node.id);
  return graphRelationPalette[relation]?.color || nodeColors[node.type] || "#6f7f72";
}

function renderGraphLegend(svg) {
  const legend = svgEl("g", { class: "graph-legend", transform: "translate(24 22)" });
  graphRelationOrder.forEach((relation, index) => {
    const item = graphRelationPalette[relation];
    const x = index * 86;
    legend.appendChild(svgEl("circle", { cx: x, cy: 0, r: 6, fill: item.color }));
    legend.appendChild(svgEl("text", { x: x + 12, y: 4 }, item.label));
  });
  svg.appendChild(legend);
}

function renderGraphLaneLabels(layer) {
  [
    ["味", 270, 58, graphRelationPalette.HAS_TASTE.color],
    ["性", 270, 292, graphRelationPalette.HAS_NATURE.color],
    ["效能", 455, 58, graphRelationPalette.HAS_POTENCY.color],
    ["功能", 640, 46, graphRelationPalette.HAS_FUNCTION.color],
    ["主治", 820, 46, graphRelationPalette.TREATS_INDICATION.color],
  ].forEach(([label, x, y, color]) => {
    const group = svgEl("g", { class: "graph-lane-label" });
    group.appendChild(svgEl("rect", { x: Number(x) - 30, y: Number(y) - 18, width: 60, height: 24, rx: 12, fill: color }));
    group.appendChild(svgEl("text", { x, y, "text-anchor": "middle" }, label));
    layer.appendChild(group);
  });
}

function stopAnimation(key) {
  if (state[key]) {
    window.cancelAnimationFrame(state[key]);
    state[key] = null;
  }
}

function initialForcePosition(index, count, width, height, relation) {
  const anchors = {
    HAS_TASTE: [0.25, 0.34],
    HAS_NATURE: [0.28, 0.68],
    HAS_POTENCY: [0.5, 0.28],
    HAS_FUNCTION: [0.7, 0.46],
    TREATS_INDICATION: [0.76, 0.72],
  };
  const anchor = anchors[relation] || [0.5, 0.5];
  const angle = (index * 137.5 * Math.PI) / 180;
  const radius = 18 + (index % Math.max(count, 1)) * 2.8;
  return {
    x: width * anchor[0] + Math.cos(angle) * radius,
    y: height * anchor[1] + Math.sin(angle) * radius,
  };
}

function renderForceNetwork(svg, nodes, edges, options) {
  stopAnimation(options.animationKey);
  const nodeById = new Map(nodes.map((node) => [node.id, node]));
  const linkedEdges = edges.filter((edge) => nodeById.has(edge.source) && nodeById.has(edge.target));
  const edgeLayer = svgEl("g", { class: "force-edge-layer" });
  const labelLayer = svgEl("g", { class: "force-label-layer" });
  const nodeLayer = svgEl("g", { class: "force-node-layer" });
  svg.append(edgeLayer, labelLayer, nodeLayer);
  if (options.title) {
    svg.appendChild(svgEl("text", { x: 24, y: options.titleY || 34, class: "force-title" }, options.title));
  }

  const edgeElements = linkedEdges.map((edge) => {
    const line = svgEl("line", {
      class: edge.className || options.edgeClass || "graph-edge",
      stroke: edge.color || "#9db4a6",
    });
    edgeLayer.appendChild(line);
    return { edge, line };
  });
  const edgeLabels = linkedEdges
    .filter((edge, index) => options.showEdgeLabels && index % Math.max(options.labelEvery || 1, 1) === 0)
    .map((edge) => {
      const text = svgEl("text", {
        "text-anchor": "middle",
        class: options.edgeLabelClass || "graph-edge-label",
      });
      text.textContent = edge.label || "";
      labelLayer.appendChild(text);
      return { edge, text };
    });
  const nodeElements = nodes.map((node) => {
    const group = svgEl("g", { class: "force-node" });
    const circle = svgEl("circle", {
      r: node.radius || 12,
      fill: node.color || "#6f7f72",
      class: node.className || options.nodeClass || "graph-node",
    });
    const label = svgEl("text", {
      y: (node.radius || 12) + 14,
      "text-anchor": "middle",
      class: options.labelClass || "graph-label",
    });
    label.textContent = truncate(node.label || node.id, node.labelLength || 16);
    if (!options.showLabels || node.showLabel === false) label.setAttribute("display", "none");
    group.append(circle, label, svgEl("title", {}, `${node.type || ""}\n${node.label || node.id}`));
    nodeLayer.appendChild(group);
    return { node, group, circle, label };
  });

  let alpha = 1;
  let frame = 0;
  const tick = () => {
    frame += 1;
    forceTick(nodes, linkedEdges, nodeById, options, alpha, frame);
    edgeElements.forEach(({ edge, line }) => {
      const source = nodeById.get(edge.source);
      const target = nodeById.get(edge.target);
      line.setAttribute("x1", source.x.toFixed(1));
      line.setAttribute("y1", source.y.toFixed(1));
      line.setAttribute("x2", target.x.toFixed(1));
      line.setAttribute("y2", target.y.toFixed(1));
    });
    edgeLabels.forEach(({ edge, text }) => {
      const source = nodeById.get(edge.source);
      const target = nodeById.get(edge.target);
      text.setAttribute("x", ((source.x + target.x) / 2).toFixed(1));
      text.setAttribute("y", ((source.y + target.y) / 2).toFixed(1));
    });
    nodeElements.forEach(({ node, group }) => {
      group.setAttribute("transform", `translate(${node.x.toFixed(1)} ${node.y.toFixed(1)})`);
    });
    alpha = Math.max(0.028, alpha * 0.985);
    state[options.animationKey] = window.requestAnimationFrame(tick);
  };
  state[options.animationKey] = window.requestAnimationFrame(tick);
  return state[options.animationKey];
}

function forceTick(nodes, edges, nodeById, options, alpha, frame) {
  const charge = options.charge || 6000;
  for (let i = 0; i < nodes.length; i += 1) {
    for (let j = i + 1; j < nodes.length; j += 1) {
      const a = nodes[i];
      const b = nodes[j];
      if (options.skipLeafRepulsion && a.kind === "material" && b.kind === "material") continue;
      let dx = b.x - a.x;
      let dy = b.y - a.y;
      let dist2 = dx * dx + dy * dy;
      if (dist2 < 1) {
        dx = 1 + i * 0.01;
        dy = 1 + j * 0.01;
        dist2 = 2;
      }
      const dist = Math.sqrt(dist2);
      const minDistance = (a.radius || 12) + (b.radius || 12) + 18;
      const repulsion = charge / Math.max(dist2, minDistance * minDistance * 0.35);
      const push = dist < minDistance ? repulsion * 1.7 : repulsion;
      const fx = (dx / dist) * push * alpha;
      const fy = (dy / dist) * push * alpha;
      a.vx -= fx;
      a.vy -= fy;
      b.vx += fx;
      b.vy += fy;
    }
  }

  edges.forEach((edge) => {
    const source = nodeById.get(edge.source);
    const target = nodeById.get(edge.target);
    let dx = target.x - source.x;
    let dy = target.y - source.y;
    let dist = Math.sqrt(dx * dx + dy * dy) || 1;
    const desired = edge.distance || options.linkDistance || 120;
    const force = (dist - desired) * (options.linkStrength || 0.025) * alpha;
    const fx = (dx / dist) * force;
    const fy = (dy / dist) * force;
    source.vx += fx;
    source.vy += fy;
    target.vx -= fx;
    target.vy -= fy;
  });

  const pulse = 1 + Math.sin(frame / 42) * 0.08;
  nodes.forEach((node) => {
    const anchor = node.anchor || { x: options.width / 2, y: options.height / 2, strength: 0.006 };
    const strength = (anchor.strength || 0.006) * (options.anchorStrength || 1) * pulse;
    node.vx += (anchor.x - node.x) * strength * alpha;
    node.vy += (anchor.y - node.y) * strength * alpha;
    const damping = node.id === options.centerId ? 0.72 : 0.82;
    node.vx *= damping;
    node.vy *= damping;
    node.x += node.vx;
    node.y += node.vy;
    const margin = (node.radius || 12) + 18;
    node.x = Math.max(margin, Math.min(options.width - margin, node.x));
    node.y = Math.max(margin + 18, Math.min(options.height - margin, node.y));
  });
}

function renderInterpretation(payload) {
  stopAnimation("interpretAnimation");
  const svg = $("#interpretSvg");
  svg.innerHTML = "";
  const groups = groupTermsByRelation(payload.terms || []);
  const relevantCount = graphRelationOrder.reduce((sum, relation) => sum + (groups[relation]?.length || 0), 0);
  if (!relevantCount) {
    $("#interpretMeta").textContent = "";
    $("#interpretText").innerHTML = `<p class="muted">当前药材缺少味、性、效能、功能或主治术语，无法生成解释图。</p>`;
    return;
  }

  const tasteQuant = groups.HAS_TASTE.map(quantifyTaste);
  const natureQuant = groups.HAS_NATURE.map(quantifyNature);
  const forceData = buildInterpretForceData(groups, tasteQuant, natureQuant);
  renderInterpretSvg(svg, forceData.nodes, forceData.edges);
  renderInterpretText(tasteQuant, natureQuant);
  $("#interpretMeta").textContent = `${relevantCount} 个术语 · 动态力导向解释网络`;
}

function groupTermsByRelation(terms) {
  const groups = Object.fromEntries(graphRelationOrder.map((relation) => [relation, []]));
  terms.forEach((term) => {
    if (!groups[term.relation]) return;
    const label = String(term.term_label || "").trim();
    if (label && !groups[term.relation].includes(label)) groups[term.relation].push(label);
  });
  return groups;
}

function quantifyTaste(label) {
  const text = String(label);
  const components = Object.keys(tasteProfiles).filter((key) => text.includes(key));
  const matched = components.length ? components : [text];
  const scores = matched.map((key) => tasteProfiles[key]?.score || 0.5);
  const baseScore = scores.reduce((sum, value) => sum + value, 0) / scores.length;
  const modifier = text.includes("微") ? 0.75 : 1;
  const tags = matched.map((key) => tasteProfiles[key]?.tag).filter(Boolean);
  return {
    label,
    score: Math.max(0, Math.min(1, baseScore * modifier)),
    tag: tags.length ? tags.join("/") : "经验味向",
  };
}

function quantifyNature(label) {
  const text = String(label);
  const key = Object.keys(natureScores)
    .sort((a, b) => b.length - a.length)
    .find((item) => text.includes(item));
  const profile = natureScores[key] || { score: 0, tag: "寒热未定" };
  return {
    label,
    score: profile.score,
    tag: profile.tag,
  };
}

function makePlainInterpretNodes(labels, sub, max = 8) {
  const nodes = labels.slice(0, max).map((label) => ({ label, sub }));
  if (labels.length > max) nodes.push({ label: `+${labels.length - max}`, sub: "更多术语" });
  return nodes;
}

function buildInterpretForceData(groups, tasteQuant, natureQuant) {
  const width = 980;
  const height = 520;
  const anchors = {
    HAS_TASTE: { x: 170, y: 170, strength: 0.016 },
    HAS_NATURE: { x: 170, y: 350, strength: 0.016 },
    HAS_POTENCY: { x: 430, y: 260, strength: 0.012 },
    HAS_FUNCTION: { x: 650, y: 215, strength: 0.011 },
    TREATS_INDICATION: { x: 810, y: 350, strength: 0.011 },
  };
  const nodes = [];
  const edges = [];
  const addNode = (id, relation, label, sub, index, radius = 15) => {
    nodes.push({
      id,
      label,
      sub,
      type: graphRelationPalette[relation]?.type || relation,
      relation,
      radius,
      labelLength: 10,
      color: graphRelationPalette[relation]?.color || "#6f7f72",
      anchor: anchors[relation],
      ...initialForcePosition(index + nodes.length, 18, width, height, relation),
      vx: 0,
      vy: 0,
    });
  };
  tasteQuant.forEach((item, index) =>
    addNode(`taste:${item.label}`, "HAS_TASTE", item.label, item.score.toFixed(2), index, 17),
  );
  natureQuant.forEach((item, index) =>
    addNode(`nature:${item.label}`, "HAS_NATURE", item.label, formatSigned(item.score), index, 17),
  );
  makePlainInterpretNodes(groups.HAS_POTENCY, "传统效能", 8).forEach((item, index) =>
    addNode(`potency:${item.label}`, "HAS_POTENCY", item.label, item.sub, index),
  );
  makePlainInterpretNodes(groups.HAS_FUNCTION, "功能表达", 10).forEach((item, index) =>
    addNode(`function:${item.label}`, "HAS_FUNCTION", item.label, item.sub, index),
  );
  makePlainInterpretNodes(groups.TREATS_INDICATION, "主治指向", 10).forEach((item, index) =>
    addNode(`indication:${item.label}`, "TREATS_INDICATION", item.label, item.sub, index),
  );

  const byRelation = (relation) => nodes.filter((node) => node.relation === relation);
  const connect = (sourceNodes, targetNodes, color, distance) => {
    if (!sourceNodes.length || !targetNodes.length) return;
    sourceNodes.forEach((source) => {
      targetNodes.forEach((target) => {
        edges.push({
          source: source.id,
          target: target.id,
          color,
          distance,
          label: "",
          className: "interpret-force-edge",
        });
      });
    });
  };
  const tasteNodes = byRelation("HAS_TASTE");
  const natureNodes = byRelation("HAS_NATURE");
  const potencyNodes = byRelation("HAS_POTENCY");
  const functionNodes = byRelation("HAS_FUNCTION");
  const indicationNodes = byRelation("TREATS_INDICATION");
  const middleNodes = potencyNodes.length ? potencyNodes : functionNodes;
  connect(tasteNodes, middleNodes, graphRelationPalette.HAS_TASTE.color, 150);
  connect(natureNodes, middleNodes, graphRelationPalette.HAS_NATURE.color, 150);
  connect(potencyNodes, functionNodes, graphRelationPalette.HAS_POTENCY.color, 130);
  connect(functionNodes, indicationNodes, graphRelationPalette.HAS_FUNCTION.color, 122);
  if (!functionNodes.length) connect(potencyNodes, indicationNodes, graphRelationPalette.HAS_POTENCY.color, 140);
  return { nodes, edges };
}

function renderInterpretSvg(svg, nodes, edges) {
  const width = 980;
  const height = 520;
  renderForceNetwork(svg, nodes, edges, {
    width,
    height,
    animationKey: "interpretAnimation",
    showLabels: true,
    charge: 5200,
    linkStrength: 0.022,
    anchorStrength: 1,
    linkDistance: 128,
    nodeClass: "interpret-force-node",
    labelClass: "interpret-force-label",
    edgeClass: "interpret-force-edge",
    edgeLabelClass: "interpret-force-edge-label",
    title: "味/性作为先验输入，效能、功能、主治在力导向网络中自动形成关联结构",
  });
}

function layoutInterpretNodes(nodes, x, top, bottom) {
  const count = Math.max(nodes.length, 1);
  const height = 42;
  const span = bottom - top;
  return nodes.map((node, index) => ({
    ...node,
    x,
    y: count === 1 ? top + span / 2 : top + (span * index) / (count - 1),
    width: 132,
    height,
  }));
}

function drawInterpretNode(svg, node, color) {
  const group = svgEl("g", { class: `interpret-node${node.muted ? " muted-node" : ""}` });
  group.appendChild(
    svgEl("rect", {
      x: node.x - node.width / 2,
      y: node.y - node.height / 2,
      width: node.width,
      height: node.height,
      rx: 8,
      fill: node.muted ? "#eef3ef" : color,
    }),
  );
  group.appendChild(
    svgEl(
      "text",
      { x: node.x, y: node.y - 3, "text-anchor": "middle", class: "interpret-node-label" },
      truncate(node.label, 9),
    ),
  );
  group.appendChild(
    svgEl(
      "text",
      { x: node.x, y: node.y + 13, "text-anchor": "middle", class: "interpret-node-sub" },
      truncate(node.sub, 13),
    ),
  );
  group.appendChild(svgEl("title", {}, `${node.label}\n${node.sub}`));
  svg.appendChild(group);
}

function drawInterpretEdges(svg, fromNodes, toNodes, color) {
  const fromActive = fromNodes.filter((node) => !node.muted);
  const toActive = toNodes.filter((node) => !node.muted);
  if (!fromActive.length || !toActive.length) return;
  const comboCount = fromActive.length * toActive.length;
  if (comboCount <= 36) {
    fromActive.forEach((fromNode) => {
      toActive.forEach((toNode) => drawInterpretCurve(svg, fromNode, toNode, color, 0.22, 1.2));
    });
    return;
  }
  const fromCenter = centerOfNodes(fromActive);
  const toCenter = centerOfNodes(toActive);
  fromActive.forEach((fromNode) => drawInterpretCurve(svg, fromNode, toCenter, color, 0.18, 1.1));
  toActive.forEach((toNode) => drawInterpretCurve(svg, fromCenter, toNode, color, 0.18, 1.1));
  drawInterpretCurve(svg, fromCenter, toCenter, color, 0.38, 3);
}

function centerOfNodes(nodes) {
  return {
    x: nodes.reduce((sum, node) => sum + node.x, 0) / nodes.length,
    y: nodes.reduce((sum, node) => sum + node.y, 0) / nodes.length,
    width: 0,
  };
}

function drawInterpretCurve(svg, fromNode, toNode, color, opacity, strokeWidth) {
  const x1 = fromNode.x + (fromNode.width || 0) / 2;
  const y1 = fromNode.y;
  const x2 = toNode.x - (toNode.width || 0) / 2;
  const y2 = toNode.y;
  const bend = Math.max(50, (x2 - x1) * 0.48);
  svg.insertBefore(
    svgEl("path", {
      d: `M${x1.toFixed(1)} ${y1.toFixed(1)} C${(x1 + bend).toFixed(1)} ${y1.toFixed(1)}, ${(x2 - bend).toFixed(1)} ${y2.toFixed(1)}, ${x2.toFixed(1)} ${y2.toFixed(1)}`,
      fill: "none",
      stroke: color,
      "stroke-width": strokeWidth,
      opacity,
      "marker-end": "url(#interpretArrow)",
      class: "interpret-edge",
    }),
    svg.firstChild,
  );
}

function renderInterpretText(tasteQuant, natureQuant) {
  const tasteMean = average(tasteQuant.map((item) => item.score));
  const natureMean = average(natureQuant.map((item) => item.score));
  const tastePercent = Math.round(Math.max(0, Math.min(1, tasteMean)) * 100);
  const naturePercent = Math.round(((Math.max(-2, Math.min(2, natureMean)) + 2) / 4) * 100);
  $("#interpretText").innerHTML = `
    <section class="quant-panel" aria-label="味性量化">
      <article class="quant-card taste">
        <div class="quant-head">
          <span>味权重均值</span>
          <strong>${formatNumber(tasteMean)}</strong>
        </div>
        <div class="quant-track"><i style="width:${tastePercent}%"></i></div>
        <div class="quant-scale"><span>0</span><span>1</span></div>
        <div class="quant-chip-row">${renderQuantChips(tasteQuant, (item) => `${item.label} · ${item.score.toFixed(2)}`)}</div>
      </article>
      <article class="quant-card nature">
        <div class="quant-head">
          <span>性寒热均值</span>
          <strong>${formatSigned(natureMean)}</strong>
        </div>
        <div class="quant-track bipolar"><i style="left:${naturePercent}%"></i></div>
        <div class="quant-scale"><span>寒 -2</span><span>平 0</span><span>热 +2</span></div>
        <div class="quant-chip-row">${renderQuantChips(natureQuant, (item) => `${item.label} · ${formatSigned(item.score)}`)}</div>
      </article>
    </section>
  `;
}

function renderQuantChips(items, formatter) {
  if (!items.length) return `<span class="quant-chip muted-chip">未记录</span>`;
  return items
    .map((item) => `<span class="quant-chip">${escapeHtml(formatter(item))}</span>`)
    .join("");
}

function summarizeLabels(labels, max = 6) {
  if (!labels.length) return "未记录";
  const head = labels.slice(0, max).join("、");
  return labels.length > max ? `${head}等${labels.length}项` : head;
}

function average(values) {
  const valid = values.filter((value) => Number.isFinite(value));
  if (!valid.length) return 0;
  return valid.reduce((sum, value) => sum + value, 0) / valid.length;
}

function formatNumber(value) {
  return Number(value || 0).toFixed(2);
}

function formatSigned(value) {
  const number = Number(value || 0);
  return `${number > 0 ? "+" : ""}${number.toFixed(2)}`;
}

function placeRing(nodes, radius, center, position, offset = 0) {
  const count = Math.max(nodes.length, 1);
  nodes.forEach((node, index) => {
    const angle = offset + (Math.PI * 2 * index) / count - Math.PI / 2;
    position.set(node.id, {
      x: center.x + Math.cos(angle) * radius,
      y: center.y + Math.sin(angle) * radius,
    });
  });
}

function placeCompact(nodes, edges, centerId, center, position) {
  const width = 920;
  const height = 540;
  const movable = nodes.filter((node) => node.id !== centerId);
  placeRing(movable, 200, center, position);

  for (let step = 0; step < 80; step += 1) {
    movable.forEach((node) => {
      const p = position.get(node.id);
      let dx = 0;
      let dy = 0;
      movable.forEach((other) => {
        if (other.id === node.id) return;
        const q = position.get(other.id);
        const vx = p.x - q.x;
        const vy = p.y - q.y;
        const dist2 = Math.max(80, vx * vx + vy * vy);
        dx += (vx / dist2) * 95;
        dy += (vy / dist2) * 95;
      });
      edges.forEach((edge) => {
        const linked =
          edge.source === node.id ? edge.target : edge.target === node.id ? edge.source : edge.source === centerId ? null : null;
        if (!linked) return;
        const q = position.get(linked);
        if (!q) return;
        dx += (q.x - p.x) * 0.0025;
        dy += (q.y - p.y) * 0.0025;
      });
      dx += (center.x - p.x) * 0.0012;
      dy += (center.y - p.y) * 0.0012;
      p.x = Math.max(36, Math.min(width - 36, p.x + dx));
      p.y = Math.max(36, Math.min(height - 36, p.y + dy));
    });
  }
}

function svgEl(name, attrs = {}, text = null) {
  const element = document.createElementNS("http://www.w3.org/2000/svg", name);
  Object.entries(attrs).forEach(([key, value]) => element.setAttribute(key, value));
  if (text !== null) element.textContent = text;
  return element;
}

async function runGlobalSearch() {
  const query = $("#globalQuery").value.trim();
  if (!query) {
    $("#globalResults").innerHTML = "";
    return;
  }
  try {
    const payload = await api("/api/search", {
      query,
      type: $("#globalType").value,
      limit: 20,
    });
    renderGlobalResults(payload.items);
  } catch (error) {
    showToast(error.message);
  }
}

function renderGlobalResults(rows) {
  if (!rows.length) {
    $("#globalResults").innerHTML = `<p class="muted">未找到匹配记录。</p>`;
    return;
  }
  $("#globalResults").innerHTML = rows
    .map(
      (row) => `
        <article class="global-item">
          <small>${escapeHtml(row.doc_type)} · ${escapeHtml(row.ref_id)}</small>
          <strong>${escapeHtml(row.title || row.ref_id)}</strong>
          <p>${escapeHtml(row.snippet || "")}</p>
        </article>
      `,
    )
    .join("");
}

function bindEvents() {
  $("#authOpenBtn").addEventListener("click", () => openAuthModal("login"));
  $("#authCloseBtn").addEventListener("click", closeAuthModal);
  $("#authModal").addEventListener("click", (event) => {
    if (event.target === $("#authModal")) closeAuthModal();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !$("#authModal").classList.contains("hidden")) closeAuthModal();
  });
  document.querySelectorAll("[data-auth-tab]").forEach((tab) => {
    tab.addEventListener("click", () => setAuthMode(tab.dataset.authTab));
  });
  $("#authLoginForm").addEventListener("submit", handleLogin);
  $("#authRegisterForm").addEventListener("submit", handleRegister);
  $("#authLogoutBtn").addEventListener("click", logoutAuthUser);
  $("#searchBtn").addEventListener("click", () => loadMaterials(true).catch((error) => showToast(error.message)));
  $("#queryInput").addEventListener("keydown", (event) => {
    if (event.key === "Enter") loadMaterials(true).catch((error) => showToast(error.message));
  });
  ["termCategoryFilter", "propertyClassFilter", "sourceTypeFilter", "kingdomFilter"].forEach(
    (id) => {
      $(`#${id}`).addEventListener("change", () => loadMaterials(true).catch((error) => showToast(error.message)));
    },
  );
  $("#prevBtn").addEventListener("click", () => {
    state.offset = Math.max(0, state.offset - state.limit);
    loadMaterials(false).catch((error) => showToast(error.message));
  });
  $("#nextBtn").addEventListener("click", () => {
    state.offset += state.limit;
    loadMaterials(false).catch((error) => showToast(error.message));
  });
  $("#refreshBtn").addEventListener("click", () => init().catch((error) => showToast(error.message)));
  $("#addDetailCompareBtn").addEventListener("click", () => {
    if (!state.selectedMaterialId) return;
    const seed = state.materials.find((item) => item.material_id === state.selectedMaterialId) || {
      material_id: state.selectedMaterialId,
      label: $("#detailTitle").textContent,
    };
    addCompareMaterial(state.selectedMaterialId, seed).catch((error) => showToast(error.message));
  });
  $("#compareSearchBtn").addEventListener("click", () => runCompareSearch().catch((error) => showToast(error.message)));
  $("#compareQuery").addEventListener("keydown", (event) => {
    if (event.key === "Enter") runCompareSearch().catch((error) => showToast(error.message));
  });
  $("#compareVizMode").addEventListener("change", () => renderCompare());
  $("#clearCompareBtn").addEventListener("click", clearCompareMaterials);
  $("#graphLayout").addEventListener("change", () => {
    state.graphLayout = $("#graphLayout").value;
    if (state.currentGraph) renderGraph(state.currentGraph);
  });
  $("#graphLabels").addEventListener("change", () => {
    state.graphLabels = $("#graphLabels").value;
    if (state.currentGraph) renderGraph(state.currentGraph);
  });
  $("#exportGraphBtn").addEventListener("click", exportGraphSvg);
  $("#globalSearchBtn").addEventListener("click", () => runGlobalSearch());
  $("#globalQuery").addEventListener("keydown", (event) => {
    if (event.key === "Enter") runGlobalSearch();
  });
}

function exportGraphSvg() {
  const svg = $("#graphSvg");
  if (!state.currentGraph || !svg.innerHTML.trim()) {
    showToast("当前没有可导出的图谱。");
    return;
  }
  const clone = svg.cloneNode(true);
  clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");
  const css = `
    .graph-edge{stroke:#9db4a6;stroke-width:1.2;opacity:.78}
    .graph-node{stroke:#fff;stroke-width:2}
    .graph-label{fill:#18221c;font-size:12px;paint-order:stroke;stroke:rgba(255,255,255,.9);stroke-width:4px;stroke-linejoin:round}
    .graph-edge-label{fill:#536359;font-size:10px;paint-order:stroke;stroke:rgba(255,255,255,.8);stroke-width:3px}
    .graph-legend text{fill:#536359;font-size:12px}
    .graph-lane-label rect{opacity:.9}
    .graph-lane-label text{fill:#fff;font-size:13px;font-weight:700}
  `;
  const style = svgEl("style", {}, css);
  clone.insertBefore(style, clone.firstChild);
  const xml = new XMLSerializer().serializeToString(clone);
  downloadText(`${state.currentGraph.material_id}_kg.svg`, xml, "image/svg+xml;charset=utf-8");
}

async function init() {
  restoreAuthSession();
  updateAuthUi();
  state.selectedMaterialId = null;
  renderCompare();
  renderCompareSearchResults();
  await loadStats();
  await loadMaterials(true);
  syncCompareButtons();
}

bindEvents();
init().catch((error) => showToast(error.message));
