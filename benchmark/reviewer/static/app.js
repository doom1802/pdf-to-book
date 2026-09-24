const state = { pages: [], types: [], currentId: null, data: null, dirty: false };

const $ = (selector) => document.querySelector(selector);
const pageList = $("#pageList");
const goldBlocks = $("#goldBlocks");
const parserBlocks = $("#parserBlocks");
const parserSelect = $("#parserSelect");

const typeColors = {
  chapter_label: "#6d28d9", heading: "#1d4ed8", paragraph: "#475569",
  epigraph: "#7c3aed", attribution: "#7c3aed", list_item: "#047857",
  code: "#b45309", figure: "#be185d", caption: "#be185d", table: "#0f766e",
  footnote: "#64748b", exercise: "#9a3412", running_header: "#dc2626",
  running_footer: "#dc2626", page_number: "#dc2626"
};

async function request(url, options = {}) {
  const response = await fetch(url, options);
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.error || `Errore HTTP ${response.status}`);
  return body;
}

function toast(message, error = false) {
  const element = $("#toast");
  element.textContent = message;
  element.className = `toast visible${error ? " error" : ""}`;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => { element.className = "toast"; }, 2600);
}

function shortBook(source) {
  if (source.includes("clean-code")) return "Clean Code";
  if (source.includes("data-intensive")) return "Designing Data-Intensive Applications";
  return "Il linguaggio C";
}

function renderNavigation() {
  pageList.replaceChildren();
  const reviewed = state.pages.filter(page => ["reviewed", "adjudicated"].includes(page.status)).length;
  $("#progressText").textContent = `${reviewed} / ${state.pages.length} revisionate`;
  $("#progressBar").style.width = `${100 * reviewed / Math.max(state.pages.length, 1)}%`;
  state.pages.forEach(page => {
    const button = document.createElement("button");
    button.className = `page-item${page.id === state.currentId ? " active" : ""}`;
    const label = document.createElement("strong");
    label.textContent = page.id;
    const meta = document.createElement("span");
    const pageText = document.createElement("i");
    pageText.style.fontStyle = "normal";
    pageText.textContent = `PDF ${page.page_number_pdf}`;
    const status = document.createElement("i");
    status.style.fontStyle = "normal";
    const dot = document.createElement("b");
    dot.className = `status-dot ${page.status}`;
    status.append(dot, document.createTextNode(page.status.replace("annotated_", "")));
    meta.append(pageText, status);
    button.append(label, meta);
    button.addEventListener("click", () => loadPage(page.id));
    pageList.append(button);
  });
}

function selectedPrediction() {
  return state.data?.predictions.find(item => item.parser === parserSelect.value) || null;
}

function metricCard(label, value) {
  const card = document.createElement("div");
  card.className = "metric";
  const name = document.createElement("span");
  name.textContent = label;
  const score = document.createElement("strong");
  score.textContent = value == null ? "n/a" : `${value.toFixed(1)}%`;
  card.append(name, score);
  return card;
}

function renderMetrics() {
  const container = $("#metrics");
  container.replaceChildren();
  const selected = selectedPrediction();
  const metrics = selected?.evaluation.metrics_percent || {};
  [
    ["Testo recuperato", "text_recovery"],
    ["Fedeltà testo", "text_accuracy"],
    ["Blocchi F1", "block_f1"],
    ["Tipi", "block_type_accuracy"],
    ["Ordine", "reading_order_accuracy"],
    ["Codice recuperato", "code_text_recovery"],
    ["Codice classificato", "code_type_accuracy"],
    ["Fedeltà codice", "code_accuracy"]
  ]
    .forEach(([label, key]) => container.append(metricCard(label, metrics[key])));
}

function option(value, selected) {
  const element = document.createElement("option");
  element.value = value;
  element.textContent = value.replaceAll("_", " ");
  element.selected = value === selected;
  return element;
}

function renumberBlocks() {
  state.data.annotation.blocks.forEach((block, index) => {
    block.reading_order = index;
  });
}

function updateBlock(index, key, value) {
  state.data.annotation.blocks[index][key] = value;
  state.dirty = true;
}

function renderGoldBlocks() {
  goldBlocks.replaceChildren();
  const blocks = state.data.annotation.blocks;
  blocks.forEach((block, index) => {
    const card = document.createElement("section");
    card.className = `block-card${block.include_in_epub ? "" : " excluded"}`;
    card.dataset.type = block.type;
    card.style.setProperty("--block-color", typeColors[block.type] || "#6b7280");

    const toolbar = document.createElement("div");
    toolbar.className = "block-toolbar";
    const number = document.createElement("span");
    number.className = "block-number";
    number.textContent = block.id;
    const type = document.createElement("select");
    state.types.forEach(value => type.append(option(value, block.type)));
    type.addEventListener("change", event => { updateBlock(index, "type", event.target.value); renderGoldBlocks(); });
    const spacer = document.createElement("span");
    spacer.className = "spacer";
    const include = document.createElement("label");
    include.className = "include-control";
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.checked = block.include_in_epub;
    checkbox.addEventListener("change", event => { updateBlock(index, "include_in_epub", event.target.checked); renderGoldBlocks(); });
    include.append(checkbox, document.createTextNode("EPUB"));
    const up = miniButton("↑", "Sposta su", () => moveBlock(index, -1));
    const down = miniButton("↓", "Sposta giù", () => moveBlock(index, 1));
    const remove = miniButton("×", "Elimina", () => removeBlock(index), true);
    toolbar.append(number, type, spacer, include, up, down, remove);

    const textarea = document.createElement("textarea");
    textarea.className = "block-text";
    textarea.rows = block.type === "code" ? 8 : 4;
    textarea.value = block.text || block.description || "";
    textarea.addEventListener("input", event => {
      if (block.type === "figure" && !block.text) {
        delete block.text;
        block.description = event.target.value;
      } else {
        block.text = event.target.value;
      }
      state.dirty = true;
    });

    const details = document.createElement("div");
    details.className = "block-details";
    if (["heading"].includes(block.type)) details.append(detailInput("Livello", block.level || 2, value => updateBlock(index, "level", Number(value))));
    if (["code"].includes(block.type)) details.append(detailInput("Linguaggio", block.language || "text", value => updateBlock(index, "language", value)));
    if (["list_item"].includes(block.type)) details.append(detailInput("Gruppo", block.group_id || "list-01", value => updateBlock(index, "group_id", value)));
    card.append(toolbar, textarea);
    if (details.children.length) card.append(details);
    goldBlocks.append(card);
  });
}

function miniButton(text, title, action, danger = false) {
  const button = document.createElement("button");
  button.className = `mini-button${danger ? " danger" : ""}`;
  button.type = "button";
  button.title = title;
  button.textContent = text;
  button.addEventListener("click", action);
  return button;
}

function detailInput(placeholder, value, onInput) {
  const input = document.createElement("input");
  input.placeholder = placeholder;
  input.value = value;
  input.addEventListener("input", event => onInput(event.target.value));
  return input;
}

function moveBlock(index, delta) {
  const target = index + delta;
  if (target < 0 || target >= state.data.annotation.blocks.length) return;
  const [block] = state.data.annotation.blocks.splice(index, 1);
  state.data.annotation.blocks.splice(target, 0, block);
  renumberBlocks();
  state.dirty = true;
  renderGoldBlocks();
}

function removeBlock(index) {
  const [removed] = state.data.annotation.blocks.splice(index, 1);
  state.data.annotation.blocks.forEach(block => {
    if (block.caption_block_id === removed.id) delete block.caption_block_id;
  });
  renumberBlocks();
  state.dirty = true;
  renderGoldBlocks();
}

function addBlock() {
  const index = state.data.annotation.blocks.length;
  state.data.annotation.blocks.push({ id: `b-${crypto.randomUUID()}`, type: "paragraph", text: "", reading_order: index, include_in_epub: true });
  renumberBlocks();
  state.dirty = true;
  renderGoldBlocks();
  goldBlocks.lastElementChild?.scrollIntoView({ behavior: "smooth", block: "center" });
}

function renderParser() {
  parserBlocks.replaceChildren();
  const selected = selectedPrediction();
  $("#parserTitle").textContent = selected?.parser || "Parser";
  $("#parserEmpty").hidden = Boolean(selected);
  if (!selected) return;
  const matchByPrediction = new Map(selected.evaluation.matches.map(match => [match.predicted_block, match]));
  selected.prediction.blocks.forEach(block => {
    const card = document.createElement("section");
    card.className = `block-card${block.include_in_epub ? "" : " excluded"}${matchByPrediction.has(block.id) ? " matched" : ""}`;
    card.style.setProperty("--block-color", typeColors[block.type] || "#6b7280");
    const label = document.createElement("div");
    label.className = "block-label";
    label.textContent = `${block.id} · ${block.type.replaceAll("_", " ")}`;
    const match = matchByPrediction.get(block.id);
    if (match) {
      const badge = document.createElement("span");
      badge.className = "match-label";
      badge.textContent = `↔ ${match.gold_block} · ${match.text_similarity.toFixed(0)}%`;
      label.append(badge);
    }
    const body = document.createElement("div");
    body.className = "block-body";
    body.dataset.type = block.type;
    body.textContent = block.text || block.description || "[elemento senza testo]";
    card.append(label, body);
    parserBlocks.append(card);
  });
}

function renderParserSelect() {
  const previous = parserSelect.value;
  parserSelect.replaceChildren();
  if (!state.data.predictions.length) parserSelect.append(option("", ""));
  state.data.predictions.forEach(item => parserSelect.append(option(item.parser, previous || item.parser)));
  parserSelect.disabled = state.data.predictions.length === 0;
}

async function loadPage(pageId) {
  if (state.dirty && !confirm("Ci sono modifiche non salvate. Cambiare pagina?")) return;
  try {
    state.data = await request(`/api/pages/${encodeURIComponent(pageId)}`);
    state.currentId = pageId;
    state.dirty = false;
    renderNavigation();
    $("#bookLabel").textContent = shortBook(state.data.annotation.source);
    $("#pageTitle").textContent = `${pageId} · pagina ${state.data.annotation.printed_page || "-"}`;
    $("#sourceImage").src = `/api/pages/${encodeURIComponent(pageId)}/source.png`;
    $("#annotationNotes").value = state.data.annotation.annotation.notes || "";
    renderParserSelect();
    renderGoldBlocks();
    renderParser();
    renderMetrics();
  } catch (error) { toast(error.message, true); }
}

async function save(status) {
  try {
    state.data.annotation.annotation.status = status;
    state.data.annotation.annotation.notes = $("#annotationNotes").value;
    renumberBlocks();
    await request(`/api/pages/${encodeURIComponent(state.currentId)}`, {
      method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(state.data.annotation)
    });
    const page = state.pages.find(item => item.id === state.currentId);
    page.status = status === "draft" ? "annotated_draft" : status;
    state.dirty = false;
    renderNavigation();
    const refreshed = await request(`/api/pages/${encodeURIComponent(state.currentId)}`);
    state.data.predictions = refreshed.predictions;
    renderParser();
    renderMetrics();
    toast(status === "reviewed" ? "Pagina revisionata e salvata" : "Bozza salvata");
  } catch (error) { toast(error.message, true); }
}

async function boot() {
  try {
    const dataset = await request("/api/pages");
    state.pages = dataset.pages;
    state.types = dataset.types;
    renderNavigation();
    if (state.pages.length) await loadPage(state.pages[0].id);
  } catch (error) { toast(error.message, true); }
}

parserSelect.addEventListener("change", () => { renderParser(); renderMetrics(); });
$("#zoom").addEventListener("input", event => { $("#sourceImage").style.width = `${event.target.value}%`; });
$("#annotationNotes").addEventListener("input", () => { state.dirty = true; });
$("#addBlock").addEventListener("click", addBlock);
$("#saveDraft").addEventListener("click", () => save("draft"));
$("#markReviewed").addEventListener("click", () => save("reviewed"));
window.addEventListener("keydown", event => {
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "s") { event.preventDefault(); save("draft"); }
});
window.addEventListener("beforeunload", event => { if (state.dirty) event.preventDefault(); });

boot();
