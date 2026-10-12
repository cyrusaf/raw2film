"use strict";

const $ = (id) => document.getElementById(id);
const state = { image: null, look: "portra400", looks: [], loading: false, exporting: false, revision: 0, loadToken: 0, timer: null, previewActive: false, previewController: null, view: "wipe" };
const defaults = { strength: 100, exposure: 0, grain: 100 };
const stockDetails = {
  portra400: ["Warm skin tones, gentle contrast, and soft color.", "#bd9470"],
  gold200: ["Golden warmth, rich color, and a sunlit everyday feel.", "#d0ad63"],
  classicchrome: ["Muted color with a restrained, documentary feel.", "#83948d"],
  classicnegative: ["Cool shadows, warm highlights, and bolder color shifts.", "#a59465"],
  neutral: ["Your RAW with camera white balance and exposure only.", "#777e70"],
};
function normalized(id) { return id.toLowerCase().replace(/[^a-z0-9]/g, ""); }
function stockInfo(id) { return stockDetails[normalized(id)] || ["Explore this film recipe, then dial in its strength.", "#a4a68f"]; }
function setStatus(message, kind = "ready") { $("status-text").textContent = message; $("status").className = `status ${kind}`; }
function showError(error) { $("error").textContent = error.message || String(error); $("error").hidden = false; setStatus("Something needs attention", "error"); }
function clearError() { $("error").hidden = true; $("error").textContent = ""; }
function setBusy(message) { $("render-text").textContent = message; $("render-badge").hidden = !message; }
function updateEnabled() {
  $("adjustments").disabled = !state.image || state.loading;
  $("export").disabled = !state.image || state.loading || state.exporting;
  $("file-input").disabled = state.loading;
  $("library").disabled = state.loading || $("library").options.length <= 1;
  $("empty-open").disabled = state.loading;
  $("drop-zone").classList.toggle("is-loading", state.loading);
}
async function responseJSON(response) {
  if (!response.ok) {
    let message = `Request failed (${response.status}).`;
    try { const body = await response.json(); message = body.error || body.detail || message; } catch (_) { /* Keep the HTTP error. */ }
    throw new Error(typeof message === "string" ? message : JSON.stringify(message));
  }
  return response.json();
}
function controls() { return { image_id: state.image.image_id, look: state.look, strength: Number($("strength").value) / 100, exposure: Number($("exposure").value), grain: Number($("grain").value) / 100 }; }
function updateReadouts() {
  for (const key of Object.keys(defaults)) {
    const input = $(key), value = Number(input.value);
    const output = $(`${key}-value`);
    output.replaceChildren(document.createTextNode(key === "exposure" ? `${value > 0 ? "+" : ""}${value.toFixed(1)}` : String(value)));
    const unit = document.createElement("span"); unit.textContent = key === "exposure" ? "EV" : "%"; output.append(unit);
    input.style.setProperty("--progress", `${(value - Number(input.min)) / (Number(input.max) - Number(input.min)) * 100}%`);
    input.setAttribute("aria-valuetext", key === "exposure" ? `${value.toFixed(1)} EV` : `${value} percent`);
  }
  const amplified = Number($("strength").value) > 100;
  $("strength-hint").textContent = amplified ? "Artistic amplification. High strengths can exaggerate color and highlights." : "100% is the base look.";
  $("strength-hint").classList.toggle("amplified", amplified);
}
function selectedName() { return state.looks.find((look) => look.id === state.look)?.name || "Film"; }
function updateLook() {
  document.querySelectorAll(".look-chip").forEach((button) => button.setAttribute("aria-pressed", String(button.dataset.look === state.look)));
  $("look-description").textContent = stockInfo(state.look)[0];
  const noGrain = ["neutral", "classicchrome", "classicnegative"].includes(normalized(state.look));
  $("grain").disabled = noGrain;
  $("grain").parentElement.classList.toggle("grain-disabled", noGrain);
  $("grain-hint").hidden = !noGrain;
}
function renderLooks(looks) {
  state.looks = looks;
  if (!looks.some((look) => look.id === state.look)) state.look = (looks.find((look) => normalized(look.id) === "portra400") || looks.find((look) => normalized(look.id) !== "neutral") || looks[0])?.id || "neutral";
  $("looks").replaceChildren();
  for (const look of looks) {
    const button = document.createElement("button"); button.type = "button"; button.className = "look-chip"; button.dataset.look = look.id; button.setAttribute("aria-label", `Use ${look.name}`);
    const swatch = document.createElement("span"); swatch.className = "swatch"; swatch.style.setProperty("--swatch", stockInfo(look.id)[1]); swatch.setAttribute("aria-hidden", "true");
    button.append(swatch, document.createTextNode(look.name));
    button.addEventListener("click", () => { if (state.look === look.id) return; state.look = look.id; updateLook(); requestPreview(0); });
    $("looks").append(button);
  }
  updateLook();
}
function requestPreview(delay = 180) {
  state.revision++;
  clearTimeout(state.timer);
  if (!state.image || state.loading) return;
  setStatus("Updating preview…", "busy");
  state.timer = setTimeout(() => { state.timer = null; pumpPreview(); }, delay);
}
async function pumpPreview() {
  if (state.previewActive || state.loading || !state.image) return;
  state.previewActive = true;
  const revision = state.revision, imageId = state.image.image_id;
  const params = controls(), label = selectedName();
  const controller = new AbortController(); state.previewController = controller;
  clearError(); setBusy("Rendering preview");
  try {
    const result = await responseJSON(await fetch("/api/preview", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(params), signal: controller.signal }));
    // Decode both frames before swapping so comparisons never mix different settings.
    const frames = await Promise.all([result.neutral, result.styled].map((src) => new Promise((resolve, reject) => { const img = new Image(); img.onload = () => resolve(img); img.onerror = () => reject(new Error("The preview could not be displayed. Try adjusting a control again.")); img.src = src; })));
    if (revision !== state.revision || state.loading || state.image?.image_id !== imageId) return;
    $("neutral-image").src = frames[0].src; $("styled-image").src = frames[1].src;
    $("styled-image").alt = `${label} rendering at ${Math.round(params.strength * 100)} percent strength`;
    $("styled-label").textContent = `${label.toUpperCase()} · ${Math.round(params.strength * 100)}%`;
    $("wipe-look-label").textContent = label;
    $("empty-state").hidden = true; $("photo-stage").hidden = false;
    $("comparison-controls").hidden = state.view !== "wipe";
    setStatus("Preview ready");
    const clipping = Number(result.clipping_pct);
    $("preview-detail").textContent = `${result.width} × ${result.height} preview${Number.isFinite(clipping) && clipping > 0.05 ? ` · ${clipping.toFixed(2)}% output at gamut limits` : " · Camera white balance"}`;
  } catch (error) {
    if (error.name !== "AbortError" && revision === state.revision && !state.loading) showError(error);
  } finally {
    state.previewActive = false;
    if (state.previewController === controller) state.previewController = null;
    if (!state.loading) setBusy("");
    if (revision !== state.revision && state.image && !state.loading && state.timer === null) pumpPreview();
  }
}
async function loadImage(file, libraryId) {
  if (state.loading) return;
  const token = ++state.loadToken;
  state.loading = true; state.revision++;
  clearTimeout(state.timer); state.timer = null;
  state.previewController?.abort();
  clearError(); updateEnabled(); setStatus("Decoding RAW…", "busy"); setBusy("Decoding RAW · this can take a moment");
  try {
    const response = file ? await fetch(`/api/upload?name=${encodeURIComponent(file.name)}`, { method: "POST", headers: { "Content-Type": "application/octet-stream" }, body: file }) : await fetch("/api/load", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ id: libraryId }) });
    const result = await responseJSON(response);
    if (token !== state.loadToken) return;
    state.image = result;
    $("file-name").textContent = result.name;
    $("file-dimensions").textContent = `${result.width.toLocaleString()} × ${result.height.toLocaleString()}`;
    if (file) $("library").value = "";
    $("file-input").value = "";
  } catch (error) { if (token === state.loadToken) showError(error); }
  finally {
    if (token === state.loadToken) { state.loading = false; updateEnabled(); setBusy(""); if (state.image && $("error").hidden) requestPreview(0); }
  }
}
function setView(view) {
  state.view = view; $("comparison").classList.toggle("side-by-side", view === "side");
  $("comparison-controls").hidden = view !== "wipe" || $("photo-stage").hidden;
  for (const [id, isActive] of [["wipe-view", view === "wipe"], ["side-view", view === "side"]]) { $(id).classList.toggle("active", isActive); $(id).setAttribute("aria-pressed", String(isActive)); }
}
async function exportImage() {
  if (!state.image || state.exporting || state.loading) return;
  const params = controls(), name = state.image.name;
  state.exporting = true; updateEnabled(); clearError(); $("export").textContent = "Rendering full-size JPEG…"; setStatus("Preparing full-resolution download…", "busy");
  try {
    const response = await fetch(`/api/export?${new URLSearchParams(params)}`);
    if (!response.ok) { await responseJSON(response); return; }
    const blob = await response.blob(), url = URL.createObjectURL(blob);
    const link = document.createElement("a"); link.href = url; link.download = `${name.replace(/\.[^.]+$/, "")}-${params.look}-${Math.round(params.strength * 100)}.jpg`; document.body.append(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 60000); setStatus("Full-size JPEG downloaded");
  } catch (error) { showError(error); }
  finally { state.exporting = false; $("export").replaceChildren(document.createTextNode("Download full-size JPEG ")); const arrow = document.createElement("span"); arrow.textContent = "↗"; arrow.setAttribute("aria-hidden", "true"); $("export").append(arrow); updateEnabled(); }
}
$("file-input").addEventListener("change", (event) => { const file = event.target.files[0]; if (file) loadImage(file); });
$("library").addEventListener("change", (event) => { if (event.target.value) loadImage(null, event.target.value); });
$("empty-open").addEventListener("click", () => $("file-input").click());
for (const key of Object.keys(defaults)) $(key).addEventListener("input", () => { updateReadouts(); requestPreview(); });
$("reset").addEventListener("click", () => { for (const [key, value] of Object.entries(defaults)) $(key).value = value; updateReadouts(); requestPreview(0); });
$("wipe").addEventListener("input", (event) => $("comparison").style.setProperty("--wipe", `${event.target.value}%`));
$("wipe-view").addEventListener("click", () => setView("wipe"));
$("side-view").addEventListener("click", () => setView("side"));
$("export").addEventListener("click", exportImage);
for (const area of [$("drop-zone"), $("canvas")]) {
  area.addEventListener("dragover", (event) => { event.preventDefault(); if (!state.loading) $("drop-zone").classList.add("drag-over"); });
  area.addEventListener("dragleave", () => $("drop-zone").classList.remove("drag-over"));
  area.addEventListener("drop", (event) => { event.preventDefault(); $("drop-zone").classList.remove("drag-over"); const file = event.dataTransfer.files[0]; if (file) loadImage(file); });
}
// Prevent a dropped RAW outside the target from replacing the editor page.
document.addEventListener("dragover", (event) => { if (event.dataTransfer.types.includes("Files")) event.preventDefault(); });
document.addEventListener("drop", (event) => event.preventDefault());
updateReadouts(); updateEnabled();
(async function initialize() {
  try {
    const data = await responseJSON(await fetch("/api/library"));
    const looks = [...data.looks]; if (!looks.some((look) => normalized(look.id) === "neutral")) looks.unshift({ id: "neutral", name: "Neutral" });
    renderLooks(looks);
    for (const image of data.images) { const option = document.createElement("option"); option.value = image.id; option.textContent = image.name; $("library").append(option); }
    if (!data.images.length) $("library").options[0].textContent = "No local samples · upload a RAW";
    updateEnabled();
  } catch (error) { showError(new Error(`Could not connect to the local editor. ${error.message}`)); }
})();
