const app = document.querySelector("#app");
const toast = document.querySelector("#toast");
let pollTimer;

const esc = (value) => String(value ?? "").replace(/[&<>'"]/g, (char) => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[char]));
const date = (value) => value ? new Date(value).toLocaleString() : "—";
const badge = (status) => `<span class="badge ${esc(status)}">${esc(status)}</span>`;
const empty = (message) => `<div class="card empty">${esc(message)}</div>`;

async function api(path, options = {}) {
  const response = await fetch(path, options);
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try { message = (await response.json()).detail || message; } catch (_) {}
    throw new Error(typeof message === "string" ? message : JSON.stringify(message));
  }
  if (response.status === 204) return null;
  return response.json();
}

function notify(message) {
  toast.textContent = message;
  toast.classList.add("show");
  setTimeout(() => toast.classList.remove("show"), 2600);
}

function loading(title = "Loading") { app.innerHTML = `<p class="eyebrow">DataForge</p><h1>${esc(title)}</h1>${empty("Loading…")}`; }
function failure(error) { app.innerHTML += `<div class="card error"><strong>Something went wrong</strong><p>${esc(error.message)}</p><button class="secondary" onclick="location.reload()">Try again</button></div>`; }

async function dashboard() {
  clearInterval(pollTimer); loading("Quality at a glance");
  try {
    const [datasets, jobs] = await Promise.all([api("/api/v1/datasets?limit=100"), api("/api/v1/jobs?limit=100")]);
    const running = jobs.filter((job) => ["QUEUED", "RUNNING", "RETRYING", "SCHEDULED"].includes(job.status)).length;
    const failed = jobs.filter((job) => ["FAILED", "DEAD_LETTERED"].includes(job.status)).length;
    app.innerHTML = `<p class="eyebrow">Operations dashboard</p><h1>Know your data.<br>Trust every version.</h1><p class="muted">Upload, validate, compare, and monitor datasets from one control plane.</p>
      <section class="grid"><div class="card"><span class="muted">Datasets</span><p class="metric">${datasets.length}</p></div><div class="card"><span class="muted">Active jobs</span><p class="metric">${running}</p></div><div class="card"><span class="muted">Succeeded</span><p class="metric">${jobs.filter(j=>j.status==="SUCCEEDED").length}</p></div><div class="card"><span class="muted">Needs attention</span><p class="metric">${failed}</p></div></section>
      <section class="card"><div class="toolbar"><h2>Recent activity</h2><button class="primary" data-view="datasets">Add dataset</button></div>${jobs.length ? jobTable(jobs.slice(0,8)) : '<div class="empty">No jobs yet. Create a dataset and upload a CSV to begin.</div>'}</section>`;
    wireNavigation(); wireJobRows();
  } catch (error) { failure(error); }
}

async function datasets() {
  clearInterval(pollTimer); loading("Datasets");
  try {
    const rows = await api("/api/v1/datasets?limit=100");
    app.innerHTML = `<p class="eyebrow">Catalog</p><h1>Datasets</h1><div class="split"><section><div class="toolbar"><p class="muted">Logical datasets and their version histories.</p></div>${rows.length ? `<div class="card"><table><thead><tr><th>Name</th><th>Description</th><th>Created</th></tr></thead><tbody>${rows.map(d=>`<tr data-id="${d.id}"><td><strong>${esc(d.name)}</strong></td><td>${esc(d.description || "—")}</td><td>${date(d.created_at)}</td></tr>`).join("")}</tbody></table></div>` : empty("No datasets yet.")}</section>
      <aside class="card"><h2>Create dataset</h2><form id="create-dataset"><label>Name<input name="name" required maxlength="200"></label><label>Description<textarea name="description" maxlength="2000"></textarea></label><button class="primary">Create dataset</button></form></aside></div>`;
    document.querySelectorAll("tr[data-id]").forEach(row => row.onclick = () => datasetDetail(row.dataset.id));
    document.querySelector("#create-dataset").onsubmit = async (event) => { event.preventDefault(); const data = Object.fromEntries(new FormData(event.target)); try { const created = await api("/api/v1/datasets", {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(data)}); notify("Dataset created"); datasetDetail(created.id); } catch (error) { notify(error.message); } };
  } catch (error) { failure(error); }
}

async function datasetDetail(id) {
  clearInterval(pollTimer); loading("Dataset detail");
  try {
    const [dataset, versions, rules] = await Promise.all([api(`/api/v1/datasets/${id}`), api(`/api/v1/datasets/${id}/versions`), api(`/api/v1/datasets/${id}/rules`)]);
    app.innerHTML = `<button class="ghost" data-view="datasets">← All datasets</button><p class="eyebrow">Dataset</p><h1>${esc(dataset.name)}</h1><p class="muted">${esc(dataset.description || "No description")}</p>
      <div class="split"><section><div class="card"><div class="toolbar"><h2>Version history</h2><span>${versions.length} versions</span></div>${versions.length ? `<table><thead><tr><th>Version</th><th>Rows</th><th>Score</th><th>Report</th></tr></thead><tbody>${versions.map(v=>`<tr><td>v${v.version_number}<br><small>${date(v.created_at)}</small></td><td>${v.row_count ?? "Processing"}</td><td>${v.quality_score ?? "—"}</td><td>${v.analysis_completed_at ? `<a class="button" target="_blank" href="/api/v1/datasets/${id}/versions/${v.id}/report?format=html">Open</a>` : "Pending"}</td></tr>`).join("")}</tbody></table>` : '<div class="empty">Upload the first CSV version.</div>'}</div>
      <div class="card"><h2>Validation rules</h2>${rules.length ? rules.map(r=>`<p><strong>${esc(r.rule_type)}</strong> · ${esc(r.column_name || "dataset")} · ${esc(r.severity)}</p>`).join("") : '<p class="muted">No custom rules configured.</p>'}</div></section>
      <aside class="card"><h2>Upload CSV</h2><form id="upload"><label>CSV file<input type="file" name="file" accept=".csv,text/csv" required></label><label>Description<textarea name="description"></textarea></label><label>Schedule (optional)<input type="datetime-local" name="scheduled_at"></label><button class="primary">Upload and analyze</button></form></aside></div>`;
    wireNavigation();
    document.querySelector("#upload").onsubmit = async (event) => { event.preventDefault(); const form = new FormData(event.target); if (form.get("scheduled_at")) form.set("scheduled_at", new Date(form.get("scheduled_at")).toISOString()); else form.delete("scheduled_at"); try { const result = await api(`/api/v1/datasets/${id}/versions`, {method:"POST",headers:{"Idempotency-Key":crypto.randomUUID()},body:form}); notify("Upload accepted"); jobDetail(result.job.id); } catch (error) { notify(error.message); } };
  } catch (error) { failure(error); }
}

const jobTable = (jobs) => `<table><thead><tr><th>Status</th><th>Stage</th><th>Progress</th><th>Updated</th></tr></thead><tbody>${jobs.map(job=>`<tr data-job="${job.id}"><td>${badge(job.status)}</td><td>${esc(job.progress_message)}</td><td><div class="progress"><span style="width:${job.progress_percent}%"></span></div>${job.progress_percent}%</td><td>${date(job.completed_at || job.started_at || job.created_at)}</td></tr>`).join("")}</tbody></table>`;
function wireJobRows() { document.querySelectorAll("tr[data-job]").forEach(row => row.onclick = () => jobDetail(row.dataset.job)); }

async function jobs() {
  clearInterval(pollTimer); loading("Jobs");
  try { const rows = await api("/api/v1/jobs?limit=100"); app.innerHTML = `<p class="eyebrow">Processing</p><h1>Jobs</h1><section class="card">${rows.length ? jobTable(rows) : '<div class="empty">No jobs have been submitted.</div>'}</section>`; wireJobRows(); }
  catch (error) { failure(error); }
}

async function jobDetail(id) {
  clearInterval(pollTimer);
  const render = async () => {
    try {
      const [job, events] = await Promise.all([api(`/api/v1/jobs/${id}`), api(`/api/v1/jobs/${id}/events`)]);
      app.innerHTML = `<button class="ghost" data-view="jobs">← All jobs</button><p class="eyebrow">Job ${esc(id.slice(0,8))}</p><div class="toolbar"><h1>${badge(job.status)}</h1><div>${["QUEUED","SCHEDULED","RUNNING","RETRYING"].includes(job.status) ? '<button id="cancel" class="danger">Cancel</button>' : ""}${["FAILED","DEAD_LETTERED"].includes(job.status) ? '<button id="retry" class="secondary">Retry</button>' : ""}</div></div><section class="grid"><div class="card"><span class="muted">Progress</span><p class="metric">${job.progress_percent}%</p><div class="progress"><span style="width:${job.progress_percent}%"></span></div><p>${esc(job.progress_message)}</p></div><div class="card"><span class="muted">Current stage</span><p class="metric">${esc(job.current_stage)}</p><p class="muted">Worker: ${esc(job.worker_id || "unassigned")}</p></div></section><section class="card"><h2>Event history</h2>${events.length ? events.map(e=>`<p><strong>${esc(e.event_type)}</strong> <span class="muted">${date(e.created_at)}</span></p>`).join("") : '<div class="empty">No events recorded.</div>'}</section>`;
      wireNavigation();
      if (document.querySelector("#cancel")) document.querySelector("#cancel").onclick = async () => { try { await api(`/api/v1/jobs/${id}/cancel`, {method:"POST"}); notify("Cancellation requested"); render(); } catch(error) { notify(error.message); } };
      if (document.querySelector("#retry")) document.querySelector("#retry").onclick = async () => { try { await api(`/api/v1/jobs/${id}/retry`, {method:"POST"}); notify("Job queued for retry"); render(); } catch(error) { notify(error.message); } };
      if (["QUEUED","SCHEDULED","RUNNING","RETRYING"].includes(job.status)) pollTimer = setTimeout(render, 1800);
    } catch (error) { failure(error); }
  };
  loading("Job progress"); render();
}

async function compare() {
  clearInterval(pollTimer); loading("Compare versions");
  try {
    const datasets = await api("/api/v1/datasets?limit=100");
    const allVersions = (await Promise.all(datasets.map(async d => (await api(`/api/v1/datasets/${d.id}/versions`)).map(v=>({...v,dataset_name:d.name}))))).flat();
    const options = allVersions.map(v=>`<option value="${v.id}">${esc(v.dataset_name)} · v${v.version_number}</option>`).join("");
    app.innerHTML = `<p class="eyebrow">Drift and overlap</p><h1>Compare versions</h1>${allVersions.length < 2 ? empty("Upload at least two versions to compare.") : `<div class="split"><form id="compare-form" class="card"><label>Left version<select name="left_version_id">${options}</select></label><label>Right version<select name="right_version_id">${options}</select></label><label>Key columns (comma separated)<input name="keys" placeholder="id,email"></label><label><input type="checkbox" name="normalize_text"> Normalize text values</label><button class="primary">Run comparison</button></form><section id="comparison-result" class="card empty">Comparison results will appear here.</section></div>`}`;
    if (document.querySelector("#compare-form")) document.querySelector("#compare-form").onsubmit = async (event) => { event.preventDefault(); const data = new FormData(event.target); const payload = {left_version_id:data.get("left_version_id"),right_version_id:data.get("right_version_id"),selected_key_columns:data.get("keys").split(",").map(x=>x.trim()).filter(Boolean),normalize_text:data.get("normalize_text") === "on"}; try { const result = await api("/api/v1/comparisons", {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)}); const report = await api(`/api/v1/comparisons/${result.id}/report`); document.querySelector("#comparison-result").classList.remove("empty"); document.querySelector("#comparison-result").innerHTML = `<h2>Comparison complete</h2><p>Critical: ${report.severity_summary.critical} · Warnings: ${report.severity_summary.warning} · Info: ${report.severity_summary.info}</p><p>Exact overlap: ${report.overlap.exact_rows.overlapping_row_count} rows</p><a class="button" href="/api/v1/comparisons/${result.id}/report">Download report</a>`; } catch(error) { notify(error.message); } };
  } catch (error) { failure(error); }
}

function wireNavigation() { document.querySelectorAll("[data-view]").forEach(button => button.onclick = () => navigate(button.dataset.view)); }
function navigate(view) { history.pushState({view}, "", `#${view}`); ({dashboard,datasets,jobs,compare}[view] || dashboard)(); document.querySelectorAll("nav button").forEach(b=>b.classList.toggle("active", b.dataset.view===view)); }
window.onpopstate = () => navigate(location.hash.slice(1) || "dashboard");
wireNavigation();
fetch("/api/v1/datasets?limit=1").then(r => { document.querySelector("#system-status").textContent = r.ok ? "API online" : "API degraded"; }).catch(()=>document.querySelector("#system-status").textContent="API offline");
navigate(location.hash.slice(1) || "dashboard");
