const API = ""; // same-origin; set to "http://localhost:5001" if running frontend separately

const views = ["school", "hobby", "calendar", "week", "stats"];
document.querySelectorAll(".nav-item").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".nav-item").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    const target = btn.dataset.view;
    views.forEach((v) => document.getElementById(`view-${v}`).classList.toggle("hidden", v !== target));
    if (target === "week") loadWeek();
    if (target === "stats") loadStats();
    if (target === "calendar") loadCalendar();
  });
});

function taskRow(t) {
  const tag = t.category === "school"
    ? `<span class="text-xs px-2 py-0.5 rounded-full tag-school">${t.course || "school"}</span>`
    : `<span class="text-xs px-2 py-0.5 rounded-full tag-hobby">hobby/chore</span>`;
  return `
    <div class="task-row flex items-center justify-between px-4 py-3">
      <div>
        <div class="text-sm">${t.description}</div>
        <div class="mt-1">${tag}</div>
      </div>
      <button class="text-sm text-neutral-500 hover:text-black" onclick="completeTask(${t.id})">Done</button>
    </div>`;
}

async function loadTasks() {
  const [school, hobby] = await Promise.all([
    fetch(`${API}/api/tasks?category=school`).then((r) => r.json()),
    fetch(`${API}/api/tasks?category=hobby`).then((r) => r.json()),
  ]);
  document.getElementById("school-list").innerHTML =
    school.length ? school.map(taskRow).join("") : emptyState("Nothing on your school list yet.");
  document.getElementById("hobby-list").innerHTML =
    hobby.length ? hobby.map(taskRow).join("") : emptyState("Nothing here yet.");
}

function emptyState(msg) {
  return `<div class="px-4 py-6 text-sm text-neutral-400">${msg}</div>`;
}

async function completeTask(id) {
  await fetch(`${API}/api/tasks/${id}/complete`, { method: "POST" });
  loadTasks();
}

document.getElementById("agent-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const input = document.getElementById("agent-input");
  const status = document.getElementById("agent-status");
  if (!input.value.trim()) return;
  status.textContent = "Reading that...";
  try {
    const res = await fetch(`${API}/api/agent/add`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: input.value }),
    });
    if (!res.ok) throw new Error((await res.json()).error || "Something went wrong");
    const data = await res.json();
    status.textContent = `Added ${data.items.length} task(s).`;
    input.value = "";
    loadTasks();
  } catch (err) {
    status.textContent = err.message;
  }
});

// Calendar / syllabus
async function loadCalendar() {
  const events = await fetch(`${API}/api/calendar`).then((r) => r.json());
  const list = document.getElementById("calendar-list");
  list.innerHTML = events.length
    ? events.map((ev) => `
      <div class="task-row flex items-center justify-between px-4 py-3">
        <div>
          <div class="text-sm">${ev.title}</div>
          <div class="text-xs text-neutral-500">${ev.course || ""} · ${ev.event_type}</div>
        </div>
        <div class="text-sm text-neutral-500">${ev.event_date}</div>
      </div>`).join("")
    : emptyState("No upcoming dates yet — paste a syllabus above.");
}

document.getElementById("syllabus-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const course = document.getElementById("syllabus-course").value;
  const text = document.getElementById("syllabus-text").value;
  if (!text.trim()) return;
  const res = await fetch(`${API}/api/agent/syllabus`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ course, text }),
  });
  if (res.ok) {
    document.getElementById("syllabus-text").value = "";
    loadCalendar();
  }
});

// This week
async function loadWeek() {
  const data = await fetch(`${API}/api/tasks/this-week`).then((r) => r.json());
  document.getElementById("week-pending").innerHTML =
    data.pending.length ? data.pending.map(taskRow).join("") : emptyState("Everything's done for now.");
  document.getElementById("week-done").innerHTML =
    data.completed_this_week.length
      ? data.completed_this_week.map((t) => `<div class="task-row px-4 py-3 text-sm">${t.description}</div>`).join("")
      : emptyState("Nothing finished yet this week.");
}

document.getElementById("summary-btn").addEventListener("click", async () => {
  const box = document.getElementById("summary-text");
  box.classList.remove("hidden");
  box.textContent = "Writing your summary...";
  try {
    const res = await fetch(`${API}/api/agent/weekly-summary`, { method: "POST" });
    const data = await res.json();
    box.textContent = data.summary || data.error;
  } catch (err) {
    box.textContent = "Couldn't generate a summary right now.";
  }
});

// Stats
let chart;
async function loadStats() {
  const data = await fetch(`${API}/api/stats`).then((r) => r.json());
  document.getElementById("lifetime-count").textContent = data.lifetime_completed;
  const ctx = document.getElementById("weekly-chart");
  const labels = data.weekly.map((w) => w.week);
  const values = data.weekly.map((w) => w.completed);
  if (chart) chart.destroy();
  chart = new Chart(ctx, {
    type: "bar",
    data: { labels, datasets: [{ label: "Tasks completed", data: values, backgroundColor: "#233B6E" }] },
    options: { plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true } } },
  });
}

loadTasks();
