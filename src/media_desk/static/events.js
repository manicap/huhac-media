const summarize = (payload) =>
  `Původní akce: ${payload.retained_count} · nová akce: ${payload.moved_count} · bez spolehlivého času: ${payload.unknown_count} · ručně přiřazené: ${payload.manual_count}`;

const updateRevision = (revision) => {
  for (const field of document.querySelectorAll('input[name="revision"]')) field.value = revision;
};

for (const form of document.querySelectorAll("[data-split-form]")) {
  const output = form.querySelector("[data-split-result]");
  const confirm = form.querySelector("[data-confirm]");
  const request = async (path) => {
    const response = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded", Accept: "application/json" },
      body: new URLSearchParams(new FormData(form)),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || `HTTP ${response.status}`);
    return payload;
  };
  form.addEventListener("input", () => { confirm.disabled = true; });
  form.querySelector("[data-preview]").addEventListener("click", async () => {
    try {
      const payload = await request("/events/split/preview");
      output.textContent = summarize(payload);
      confirm.disabled = false;
    } catch (error) { output.textContent = error.message; }
  });
  confirm.addEventListener("click", async () => {
    try {
      const payload = await request("/events/split");
      output.textContent = summarize(payload);
      location.reload();
    } catch (error) { output.textContent = error.message; confirm.disabled = true; }
  });
}

const assignmentForm = document.querySelector("[data-assignment-form]");
if (assignmentForm) assignmentForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const output = assignmentForm.querySelector("[data-assignment-result]");
  const response = await fetch("/events/assign", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded", Accept: "application/json" },
    body: new URLSearchParams(new FormData(assignmentForm)),
  });
  const payload = await response.json();
  if (!response.ok) { output.textContent = payload.detail || `HTTP ${response.status}`; return; }
  output.textContent = "Ruční přiřazení bylo uloženo.";
  updateRevision(payload.revision);
});

for (const form of document.querySelectorAll("[data-boundary-form]")) {
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const output = form.querySelector("[data-boundary-result]");
    const response = await fetch("/events/boundary", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded", Accept: "application/json" },
      body: new URLSearchParams(new FormData(form)),
    });
    const payload = await response.json();
    if (!response.ok) { output.textContent = payload.detail || `HTTP ${response.status}`; return; }
    location.reload();
  });
}
