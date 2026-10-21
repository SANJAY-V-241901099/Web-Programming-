const $ = (selector) => document.querySelector(selector);
let me = null;          // logged-in user
let exercises = [];     // cached exercise list
let currentClient = null;
const charts = {};      // Chart.js instances (destroyed before redrawing)
const isTrainer = () => me && me.role === "admin";

/* ---------- helpers ---------- */
function esc(value = "") {   // stops XSS: user text is never inserted as raw HTML
  return String(value).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

async function api(url, options = {}) {
  if (options.body && !(options.body instanceof FormData)) {
    options.headers = { "Content-Type": "application/json" };
    options.body = JSON.stringify(options.body);
  }
  const response = await fetch(url, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || "Something went wrong.");
  return data;
}

function notice(message, isError = false) {
  const box = $("#notice");
  box.textContent = message;
  box.className = "notice" + (isError ? " error" : "");
  box.hidden = false;
  clearTimeout(notice.timer);
  notice.timer = setTimeout(() => (box.hidden = true), 4000);
}

// Shows errors as a message. Only form submits are cancelled, never clicks.
const safe = (fn) => async (event) => {
  if (event && event.type === "submit") event.preventDefault();
  try { await fn(event); } catch (err) { notice(err.message, true); }
};

const formData = (form) => Object.fromEntries(new FormData(form).entries());
const today = () => new Date().toISOString().slice(0, 10);

/* ---------- login / register ---------- */
$("#tab-login").onclick = () => switchAuth(true);
$("#tab-register").onclick = () => switchAuth(false);
function switchAuth(login) {
  $("#login-form").hidden = !login;
  $("#register-form").hidden = login;
  $("#tab-login").classList.toggle("active", login);
  $("#tab-register").classList.toggle("active", !login);
}
$("#login-form").onsubmit = safe(async (e) => startApp(await api("/api/auth/login", { method: "POST", body: formData(e.target) })));
$("#register-form").onsubmit = safe(async (e) => startApp(await api("/api/auth/register", { method: "POST", body: formData(e.target) })));
$("#logout").onclick = safe(async () => { await api("/api/auth/logout", { method: "POST" }); location.reload(); });

/* ---------- start: different layout for trainer and user ---------- */
const NAV = {
  user: [["dashboard", "Dashboard"], ["exercises", "Exercises"], ["workouts", "Workouts"], ["plans", "My Plans"], ["progress", "Progress"]],
  trainer: [["clients", "Clients"], ["exercises", "Exercises + Videos"], ["plans", "Plans"]],
};

async function startApp(user) {
  me = user;
  $("#auth-view").hidden = true;
  $("#app-view").hidden = false;
  document.body.classList.toggle("trainer", isTrainer());
  $("#badge").textContent = isTrainer() ? "TRAINER PANEL" : "";
  $("#who").textContent = `${user.name}`;
  $("#ex-add").hidden = !isTrainer();
  $("#plan-form").hidden = !isTrainer();
  $("#nav").innerHTML = NAV[isTrainer() ? "trainer" : "user"].map(([p, label]) => `<button data-page="${p}">${label}</button>`).join("");
  document.querySelectorAll("#nav button").forEach((b) => (b.onclick = () => showPage(b.dataset.page)));
  await loadExercises();
  showPage(isTrainer() ? "clients" : "dashboard");
}

const loaders = { dashboard: loadDashboard, clients: loadClients, client: loadClient, exercises: renderExercises, workouts: loadWorkouts, plans: loadPlans, progress: loadProgress };

function showPage(page) {
  document.querySelectorAll("main > section").forEach((s) => (s.hidden = s.id !== `page-${page}`));
  const navPage = page === "client" ? "clients" : page;
  document.querySelectorAll("#nav button").forEach((b) => b.classList.toggle("active", b.dataset.page === navPage));
  safe(loaders[page])();
}
document.querySelectorAll("[data-close]").forEach((b) => (b.onclick = () => ($("#" + b.dataset.close).hidden = true)));

/* ---------- exercise video popup (exact video only, no search page) ---------- */
function videoHTML(ex) {
  const url = (ex.video_url || "").trim();
  const yt = url.match(/(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/)([\w-]{11})/);
  if (yt) {
    return `<iframe class="video" src="https://www.youtube.com/embed/${yt[1]}" title="${esc(ex.name)}" allow="encrypted-media; picture-in-picture" allowfullscreen></iframe>
      <p class="small"><a href="https://www.youtube.com/watch?v=${yt[1]}" target="_blank" rel="noopener">Open this video on YouTube</a> (if the player says unavailable)</p>`;
  }
  if (/\.mp4$/i.test(url)) return `<video class="video" controls src="${esc(url)}"></video>`;
  return `<p class="muted">${isTrainer() ? "No video yet. Use Edit and paste the exact YouTube link." : "The trainer has not added a demo video for this exercise yet. Follow the steps below."}</p>`;
}

function openExercise(id) {
  const ex = exercises.find((e) => e.id === id);
  if (!ex) return;
  const steps = (ex.steps || "").split("\n").filter(Boolean).map((s) => `<li>${esc(s)}</li>`).join("");
  $("#modal-content").innerHTML = `<h2>${esc(ex.name)}</h2><p class="muted">${esc(ex.category)} - ${esc(ex.muscle)}</p>
    ${videoHTML(ex)}<h4>How to do it</h4><ol>${steps}</ol>${ex.tips ? `<p><strong>Tip:</strong> ${esc(ex.tips)}</p>` : ""}`;
  $("#modal").hidden = false;
}
$("#modal-close").onclick = () => { $("#modal").hidden = true; $("#modal-content").innerHTML = ""; };  // clearing stops the video

/* ---------- exercises ---------- */
async function loadExercises() {
  exercises = await api("/api/exercises");
  const options = exercises.map((e) => `<option value="${e.id}">${esc(e.name)}</option>`).join("");
  $("#wk-exercise").innerHTML = options;
  $("#wk-filter-ex").innerHTML = `<option value="">All exercises</option>` + options;
  const cats = [...new Set(exercises.map((e) => e.category))].sort();
  $("#ex-category").innerHTML = `<option value="">All categories</option>` + cats.map((c) => `<option>${esc(c)}</option>`).join("");
}

async function renderExercises() {
  const q = new URLSearchParams({ q: $("#ex-search").value, category: $("#ex-category").value });
  const list = await api("/api/exercises?" + q);
  $("#ex-list").innerHTML = list.map((e) => `
    <div class="card"><h3>${esc(e.name)}</h3>
      <p class="muted">${esc(e.category)} - ${esc(e.muscle)} - ${e.calories_per_min} cal/min
      ${isTrainer() ? (e.video_url ? ` <span class="tag ok">video added</span>` : ` <span class="tag no">no video</span>`) : ""}</p>
      <button class="btn small" data-watch="${e.id}">${e.video_url ? "Watch video" : "How to do it"}</button>
      ${isTrainer() ? `<button class="btn small ghost" data-edit="${e.id}">Edit</button><button class="btn small danger" data-del="${e.id}">Delete</button>` : ""}
    </div>`).join("") || "<p>No exercises found.</p>";
}
$("#ex-search").oninput = safe(renderExercises);
$("#ex-category").onchange = safe(renderExercises);
$("#ex-add").onclick = () => { $("#ex-form").reset(); $("#ex-form").elements.id.value = ""; $("#ex-form").hidden = false; };

$("#ex-list").onclick = safe(async (e) => {
  const t = e.target;
  if (t.dataset.watch) openExercise(Number(t.dataset.watch));
  if (t.dataset.edit) {
    const ex = exercises.find((x) => x.id === Number(t.dataset.edit));
    const form = $("#ex-form");
    for (const key of ["id", "name", "category", "muscle", "calories_per_min", "steps", "tips", "video_url"]) form.elements[key].value = ex[key];
    form.hidden = false;
    form.scrollIntoView({ behavior: "smooth" });
  }
  if (t.dataset.del && confirm("Delete this exercise and its logged workouts?")) {
    await api(`/api/exercises/${t.dataset.del}`, { method: "DELETE" });
    await loadExercises(); await renderExercises();
  }
});

$("#ex-form").onsubmit = safe(async (e) => {
  const data = formData(e.target);
  await api(data.id ? `/api/exercises/${data.id}` : "/api/exercises", { method: data.id ? "PUT" : "POST", body: data });
  e.target.hidden = true;
  notice("Exercise saved.");
  await loadExercises(); await renderExercises();
});

/* ---------- workouts (user) ---------- */
let workouts = [];
async function loadWorkouts() {
  if (!$("#wk-form").elements.workout_date.value) $("#wk-form").elements.workout_date.value = today();
  const q = new URLSearchParams({ date: $("#wk-filter-date").value, exercise_id: $("#wk-filter-ex").value });
  workouts = await api("/api/workouts?" + q);
  $("#wk-list").innerHTML = workouts.map((w) => `<tr>
      <td>${esc(w.workout_date)}</td><td>${esc(w.exercise_name)}</td><td>${w.sets} x ${w.reps}</td><td>${w.weight} kg</td>
      <td>${w.duration}</td><td>${w.calories}</td>
      <td><button class="btn small ghost" data-edit="${w.id}">Edit</button> <button class="btn small danger" data-del="${w.id}">Delete</button></td>
    </tr>`).join("") || `<tr><td colspan="7">No workouts yet. Log your first one above.</td></tr>`;
}
$("#wk-filter-ex").onchange = safe(loadWorkouts);
$("#wk-filter-date").onchange = safe(loadWorkouts);
$("#wk-export").onclick = () => (location.href = "/api/workouts/export");

function resetWorkoutForm() {
  $("#wk-form").reset();
  $("#wk-form").elements.id.value = "";
  $("#wk-form").elements.workout_date.value = today();
  $("#wk-title").textContent = "Log a workout";
  $("#wk-cancel").hidden = true;
}
$("#wk-cancel").onclick = resetWorkoutForm;

$("#wk-form").onsubmit = safe(async (e) => {
  const data = formData(e.target);
  await api(data.id ? `/api/workouts/${data.id}` : "/api/workouts", { method: data.id ? "PUT" : "POST", body: data });
  notice("Workout saved.");
  resetWorkoutForm();
  await loadWorkouts();
});

$("#wk-list").onclick = safe(async (e) => {
  const t = e.target;
  if (t.dataset.edit) {
    const w = workouts.find((x) => x.id === Number(t.dataset.edit));
    const form = $("#wk-form");
    for (const key of ["id", "exercise_id", "sets", "reps", "weight", "duration", "workout_date"]) form.elements[key].value = w[key];
    $("#wk-title").textContent = "Edit workout";
    $("#wk-cancel").hidden = false;
    form.scrollIntoView({ behavior: "smooth" });
  }
  if (t.dataset.del && confirm("Delete this workout?")) {
    await api(`/api/workouts/${t.dataset.del}`, { method: "DELETE" });
    await loadWorkouts();
  }
});

/* ---------- plans ---------- */
async function loadPlans() {
  const [plans, coach] = await Promise.all([api("/api/plans"), isTrainer() ? { plan: null } : api("/api/my/coach")]);
  if (isTrainer() && !$("#plan-rows").children.length) addPlanRow();
  $("#plan-list").innerHTML = plans.map((p) => {
    const days = {};
    p.items.forEach((i) => (days[i.day] = days[i.day] || []).push(i));
    const body = Object.entries(days).map(([day, items]) => `<h4>Day ${day}</h4><ul>` + items.map((i) =>
      `<li>${esc(i.name)} - ${i.sets} x ${i.reps}
        <button class="btn small ghost" data-watch="${i.exercise_id}">Video</button>
        ${isTrainer() ? "" : `<button class="btn small" data-log="${i.exercise_id}" data-sets="${i.sets}" data-reps="${i.reps}">Log it</button>`}</li>`).join("") + "</ul>").join("");
    const mine = coach.plan && coach.plan.id === p.id ? ` <span class="tag ok">Assigned to you</span>` : "";
    return `<div class="card"><h3>${esc(p.name)}${mine}</h3><p class="muted">${esc(p.description)}</p>${body}
      ${isTrainer() ? `<button class="btn small danger" data-delplan="${p.id}">Delete plan</button>` : ""}</div>`;
  }).join("");
}

function addPlanRow() {
  const row = document.createElement("div");
  row.className = "row plan-row";
  row.innerHTML = `<label>Day <input type="number" min="1" max="7" value="1" data-f="day"></label>
    <label>Exercise <select data-f="exercise_id">${exercises.map((e) => `<option value="${e.id}">${esc(e.name)}</option>`).join("")}</select></label>
    <label>Sets <input type="number" min="1" value="3" data-f="sets"></label>
    <label>Reps <input type="number" min="1" value="10" data-f="reps"></label>`;
  $("#plan-rows").appendChild(row);
}
$("#plan-add-row").onclick = addPlanRow;
$("#plan-form").onsubmit = safe(async (e) => {
  const items = [...document.querySelectorAll(".plan-row")].map((r) => Object.fromEntries([...r.querySelectorAll("[data-f]")].map((el) => [el.dataset.f, el.value])));
  const data = formData(e.target);
  await api("/api/plans", { method: "POST", body: { name: data.name, description: data.description, items } });
  e.target.reset(); $("#plan-rows").innerHTML = ""; addPlanRow();
  notice("Plan created.");
  await loadPlans();
});

$("#plan-list").onclick = safe(async (e) => {
  const t = e.target;
  if (t.dataset.watch) openExercise(Number(t.dataset.watch));
  if (t.dataset.log) {   // quick-log a planned exercise for today
    await api("/api/workouts", { method: "POST", body: { exercise_id: t.dataset.log, sets: t.dataset.sets, reps: t.dataset.reps, weight: 0, duration: 10, workout_date: today() } });
    notice("Logged for today. Edit it in Workouts to add weight and time.");
  }
  if (t.dataset.delplan && confirm("Delete this plan?")) { await api(`/api/plans/${t.dataset.delplan}`, { method: "DELETE" }); await loadPlans(); }
});

/* ---------- charts ---------- */
const brand = () => getComputedStyle(document.body).getPropertyValue("--brand").trim() || "#4f46e5";
function drawChart(selector, type, labels, data, label, emptyText = "No data yet.") {
  if (charts[selector]) { charts[selector].destroy(); delete charts[selector]; }
  const canvas = $(selector);
  const box = canvas.parentElement;
  let empty = box.querySelector(".chart-empty");
  if (!data.length) {
    canvas.hidden = true;
    if (!empty) { empty = document.createElement("div"); empty.className = "chart-empty"; box.appendChild(empty); }
    empty.textContent = emptyText;
    return;
  }
  canvas.hidden = false;
  if (empty) empty.remove();
  if (typeof Chart === "undefined") return;   // Chart.js CDN not reachable (offline)
  const color = brand();
  const isLine = type === "line";
  charts[selector] = new Chart(canvas, {
    type,
    data: { labels, datasets: [{
      label, data,
      borderColor: color,
      backgroundColor: isLine ? color + "22" : color + "cc",
      fill: isLine, tension: 0.35, borderWidth: 2,
      pointRadius: 4, pointHoverRadius: 6, pointBackgroundColor: "#fff", pointBorderColor: color, pointBorderWidth: 2,
      borderRadius: 6, maxBarThickness: 36,
    }] },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false }, tooltip: { displayColors: false } },
      scales: {
        x: { grid: { display: false }, ticks: { maxRotation: 0, autoSkip: true, maxTicksLimit: 6 } },
        y: { beginAtZero: !isLine, grace: "10%", grid: { color: "#eceef5" }, ticks: { precision: isLine ? undefined : 0 } },
      },
    },
  });
}

/* ---------- user dashboard ---------- */
async function loadDashboard() {
  const [d, coach] = await Promise.all([api("/api/dashboard"), api("/api/my/coach")]);
  const box = $("#coach");
  box.hidden = !coach.plan && !coach.notes.length;
  box.innerHTML = `<h3>From your trainer</h3>${coach.plan ? `<p>Your assigned plan: <strong>${esc(coach.plan.name)}</strong> (see My Plans)</p>` : ""}
    ${coach.notes.map((n) => `<p class="note">${esc(n.note)} <span class="muted small">${esc(n.created_at)}</span></p>`).join("")}`;
  $("#stats").innerHTML = [["Workouts", d.workouts], ["Calories burned", d.calories], ["Day streak", d.streak], ["BMI", d.bmi ?? "-"]]
    .map(([k, v]) => `<div class="stat"><span>${v}</span>${k}</div>`).join("");
  drawChart("#chart-weekly", "bar", d.weekly.map((x) => x.wk), d.weekly.map((x) => x.n), "Workouts");
  drawChart("#chart-volume", "line", d.volume.map((x) => x.d), d.volume.map((x) => x.v), "kg");
  drawChart("#chart-weight", "line", d.weights.map((x) => x.d), d.weights.map((x) => x.w), "kg");
  $("#records").innerHTML = d.records.map((r) => `<p>${esc(r.name)}: <strong>${r.best} kg</strong></p>`).join("") || "<p class='muted'>Log workouts with weight to see records.</p>";
}

/* ---------- trainer: clients ---------- */
async function loadClients() {
  const { summary, clients } = await api("/api/trainer/clients");
  $("#client-stats").innerHTML = [["Clients", summary.clients], ["Active this week", summary.active_this_week], ["Inactive 7+ days", summary.inactive], ["Workouts logged", summary.total_workouts]]
    .map(([k, v]) => `<div class="stat"><span>${v}</span>${k}</div>`).join("");
  $("#client-list").innerHTML = clients.map((c) => {
    const change = c.start_weight !== null && c.current_weight !== null ? (c.current_weight - c.start_weight).toFixed(1) : null;
    return `<tr><td><strong>${esc(c.name)}</strong><br><span class="muted small">${esc(c.email)}</span></td><td>${esc(c.plan_name || "-")}</td>
      <td>${c.workouts}</td><td>${c.week_workouts ? c.week_workouts : `<span class="tag no">0</span>`}</td><td>${esc(c.last_workout || "never")}</td>
      <td>${change === null ? "-" : `${change > 0 ? "+" : ""}${change} kg`}</td><td>${c.active_goals}</td>
      <td><button class="btn small" data-client="${c.id}">View progress</button></td></tr>`;
  }).join("") || `<tr><td colspan="8">No clients yet. Users who register will appear here.</td></tr>`;
}
$("#client-list").onclick = (e) => { if (e.target.dataset.client) { currentClient = Number(e.target.dataset.client); showPage("client"); } };
$("#client-back").onclick = () => showPage("clients");

async function loadClient() {
  const [c, plans] = await Promise.all([api(`/api/trainer/clients/${currentClient}`), api("/api/plans")]);
  const first = c.measurements[0], last = c.measurements[c.measurements.length - 1];
  $("#client-head").innerHTML = `<h2>${esc(c.name)}</h2><p class="muted">${esc(c.email)} - joined ${esc(c.created_at)}${c.height_cm ? ` - ${c.height_cm} cm` : ""}</p>
    <p>${last ? `Weight: <strong>${last.weight_kg} kg</strong> (started ${first.weight_kg} kg)` : "No body measurements yet."}</p>`;
  drawChart("#chart-c-weekly", "bar", c.weekly.map((x) => x.wk), c.weekly.map((x) => x.n), "Workouts");
  drawChart("#chart-c-weight", "line", c.measurements.map((m) => m.measured_on), c.measurements.map((m) => m.weight_kg), "kg");
  $("#client-plan").innerHTML = `<option value="">No plan</option>` + plans.map((p) => `<option value="${p.id}" ${p.id === c.plan_id ? "selected" : ""}>${esc(p.name)}</option>`).join("");
  $("#client-notes").innerHTML = c.notes.map((n) => `<p class="note">${esc(n.note)} <span class="muted">${esc(n.created_at)}</span></p>`).join("");
  $("#client-goals").innerHTML = c.goals.map((g) => `<div class="goal"><strong>${esc(g.title)}</strong> <span class="tag ${g.status === "Achieved" ? "ok" : ""}">${g.status}</span>
    ${g.progress !== null ? `<div class="bar"><div style="width:${g.progress}%"></div></div>` : ""}</div>`).join("") || "<p class='muted'>No goals set.</p>";
  $("#client-workouts").innerHTML = c.workouts.map((w) => `<tr><td>${esc(w.workout_date)}</td><td>${esc(w.exercise_name)}</td><td>${w.sets} x ${w.reps}</td><td>${w.weight} kg</td><td>${w.duration}</td><td>${w.calories}</td></tr>`).join("") || `<tr><td colspan="6">No workouts yet.</td></tr>`;
}
$("#client-plan-save").onclick = safe(async () => {
  await api(`/api/trainer/clients/${currentClient}/plan`, { method: "PUT", body: { plan_id: $("#client-plan").value ? Number($("#client-plan").value) : null } });
  notice("Plan saved for this client.");
});
$("#note-form").onsubmit = safe(async (e) => {
  await api(`/api/trainer/clients/${currentClient}/notes`, { method: "POST", body: formData(e.target) });
  e.target.reset(); notice("Note sent."); await loadClient();
});

/* ---------- user progress: measurements, goals, weight trend ---------- */
async function loadProgress() {
  const [ms, goals] = await Promise.all([api("/api/measurements"), api("/api/goals")]);
  const trend = [...ms].sort((a, b) => a.measured_on.localeCompare(b.measured_on) || a.id - b.id);
  drawChart("#chart-progress", "line", trend.map((m) => m.measured_on), trend.map((m) => m.weight_kg), "kg", "Log your weight to see your trend.");
  $("#ms-list").innerHTML = ms.slice(0, 6).map((m) => `<p>${esc(m.measured_on)}: ${m.weight_kg} kg
    ${m.body_fat ? ` - ${m.body_fat}% fat` : ""}${m.waist_cm ? ` - waist ${m.waist_cm} cm` : ""}
    <button class="btn small danger" type="button" data-delms="${m.id}">x</button></p>`).join("");
  $("#goal-list").innerHTML = goals.map((g) => `<div class="goal"><strong>${esc(g.title)}</strong> ${g.deadline ? `<span class="muted">by ${esc(g.deadline)}</span>` : ""}
    ${g.progress !== null ? `<div class="bar"><div style="width:${g.progress}%"></div></div>` : ""}
    <button class="btn small ghost" type="button" data-goal="${g.id}" data-status="${g.status === "Active" ? "Achieved" : "Active"}">${g.status === "Active" ? "Mark achieved" : "Achieved - reopen"}</button>
    <button class="btn small danger" type="button" data-delgoal="${g.id}">Delete</button></div>`).join("");
}

$("#ms-form").onsubmit = safe(async (e) => { await api("/api/measurements", { method: "POST", body: formData(e.target) }); e.target.reset(); await loadProgress(); });
$("#goal-form").onsubmit = safe(async (e) => { await api("/api/goals", { method: "POST", body: formData(e.target) }); e.target.reset(); await loadProgress(); });

$("#page-progress").onclick = safe(async (e) => {
  const t = e.target;
  if (t.dataset.delms) await api(`/api/measurements/${t.dataset.delms}`, { method: "DELETE" });
  else if (t.dataset.goal) await api(`/api/goals/${t.dataset.goal}`, { method: "PUT", body: { status: t.dataset.status } });
  else if (t.dataset.delgoal) await api(`/api/goals/${t.dataset.delgoal}`, { method: "DELETE" });
  else return;
  await loadProgress();
});

/* ---------- already logged in? ---------- */
api("/api/auth/me").then(startApp).catch(() => {});
