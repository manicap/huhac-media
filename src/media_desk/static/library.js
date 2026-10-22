const app = document.querySelector("#library-app");

if (app) {
  const storageKey = `mediaDesk.library:${app.dataset.workspaceId}`;
  const viewport = document.querySelector("#library-viewport");
  const scrollRoot = document.querySelector(".app-main");
  const canvas = document.querySelector("#library-canvas");
  const windowElement = document.querySelector("#library-window");
  const form = document.querySelector("#library-filters");
  const errorElement = document.querySelector("#library-error");
  const noticeElement = document.querySelector("#snapshot-notice");
  const countElement = document.querySelector("#library-count");
  const periodElement = document.querySelector("#library-period");
  const timeNavigator = document.querySelector("#time-navigator");
  const timeSelect = document.querySelector("#time-select");
  const densityControls = [...form.querySelectorAll('input[name="density"]')];
  const batchSize = Number(app.dataset.batchSize || 50);
  const overscanRows = 3;
  const maxCachedBatches = 12;
  const cache = new Map();
  const inflight = new Map();
  let snapshotId = app.dataset.snapshotId;
  let totalCount = 0;
  let columns = 1;
  let generation = 0;
  let renderScheduled = false;
  let lastFailedStart = 0;
  let activeAssetId = app.dataset.activeAssetId || new URL(location.href).searchParams.get("active_asset_id");
  let segments = [];
  let rowHeight = 260;
  let tileMin = 176;
  let tileGap = 10;
  const metrics = { batchRequests: 0, failedBatchRequests: 0, deduplicatedFetches: 0, maxInflightRequests: 0, peakDomTiles: 0, longTasksOver100ms: 0, initialHeapBytes: globalThis.performance?.memory?.usedJSHeapSize ?? null };
  if (globalThis.PerformanceObserver) {
    try {
      new PerformanceObserver((list) => { metrics.longTasksOver100ms += list.getEntries().filter((entry) => entry.duration > 100).length; }).observe({ type: "longtask", buffered: true });
    } catch { /* Long-task observation is optional in unsupported browsers. */ }
  }

  const params = () => {
    const values = new URLSearchParams(new FormData(form));
    values.delete("density");
    for (const [key, value] of [...values.entries()]) if (!value) values.delete(key);
    return values;
  };
  const readGeometry = () => {
    const styles = getComputedStyle(app);
    rowHeight = Number.parseFloat(styles.getPropertyValue("--tile-row-height")) || 260;
    tileMin = Number.parseFloat(styles.getPropertyValue("--tile-min")) || 176;
    tileGap = Number.parseFloat(styles.getPropertyValue("--tile-gap")) || 10;
  };
  const apiUrl = (path, extra = {}) => {
    const values = params();
    for (const [key, value] of Object.entries(extra)) {
      if (value !== undefined && value !== null) values.set(key, String(value));
    }
    return `${path}?${values}`;
  };
  const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[character]);
  const formatCaptureLabel = (item) => {
    if (!item.capture_time) return item.capture_label;
    const match = item.capture_time.match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/);
    if (!match) return item.capture_label;
    const label = `${Number(match[3])}. ${Number(match[2])}. ${match[1]} · ${match[4]}:${match[5]}`;
    if (item.capture_filesystem_fallback) return `${label} · čas souboru (nízká důvěra)`;
    if (!(item.capture_timezone || item.capture_time.endsWith("Z") || item.capture_time.slice(10).includes("+"))) return `${label} · bez časové zóny`;
    return label;
  };
  const cardHtml = (item, index) => {
    const preview = item.preview_url
      ? `<img src="${escapeHtml(item.preview_url)}" alt="Náhled ${escapeHtml(item.source_name)}" width="320" height="210" loading="lazy" decoding="async">`
      : `<div class="placeholder"><span>${item.media_type === "video" ? "VIDEO" : "FOTO"}</span><small>${escapeHtml(item.preview_status)}</small></div>`;
    const url = new URL(`/assets/${item.sha256}`, location.origin);
    url.searchParams.set("return_to", location.pathname + location.search);
    url.searchParams.set("active_asset_id", item.asset_id);
    return `<article class="media-tile${item.asset_id === activeAssetId ? " is-active" : ""}" data-index="${index}" data-asset-id="${escapeHtml(item.asset_id)}">
      <a class="tile-preview" href="${escapeHtml(url.pathname + url.search)}">${preview}<span class="type-pill">${item.media_type === "video" ? "video" : "foto"}</span>${item.original_access_state === "unchecked" ? '<span class="offline-pill">ověří se při otevření</span>' : '<span class="offline-pill">originál offline</span>'}</a>
      <div class="tile-copy"><strong title="${escapeHtml(item.source_name)}">${escapeHtml(item.source_name)}</strong><span>${escapeHtml(formatCaptureLabel(item))}</span></div>
    </article>`;
  };
  const touchCache = (start, items) => {
    cache.delete(start);
    cache.set(start, items);
    while (cache.size > maxCachedBatches) cache.delete(cache.keys().next().value);
  };
  const itemAt = (index) => {
    const start = Math.floor(index / batchSize) * batchSize;
    return cache.get(start)?.[index - start];
  };
  const fetchBatch = async (start) => {
    if (start < 0 || start >= totalCount || cache.has(start)) return;
    if (inflight.has(start)) {
      metrics.deduplicatedFetches += 1;
      return inflight.get(start);
    }
    const localGeneration = generation;
    const controller = new AbortController();
    metrics.batchRequests += 1;
    const promise = fetch(apiUrl("/api/assets", { limit: batchSize, start, snapshot_id: snapshotId }), {
      signal: controller.signal, headers: { Accept: "application/json" },
    }).then(async (response) => {
      if (response.status === 409) {
        noticeElement.hidden = false;
        throw new Error("snapshot_changed");
      }
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const payload = await response.json();
      if (localGeneration !== generation) return;
      touchCache(start, payload.items);
      errorElement.hidden = true;
      scheduleRender();
    }).catch((error) => {
      if (error.name !== "AbortError" && error.message !== "snapshot_changed") {
        metrics.failedBatchRequests += 1;
        lastFailedStart = start;
        errorElement.hidden = false;
      }
    }).finally(() => inflight.delete(start));
    promise.controller = controller;
    inflight.set(start, promise);
    metrics.maxInflightRequests = Math.max(metrics.maxInflightRequests, inflight.size);
    return promise;
  };
  const visibleRange = () => {
    const firstRow = Math.max(0, Math.floor(galleryScrollTop() / rowHeight) - overscanRows);
    const visibleRows = Math.ceil(scrollRoot.clientHeight / rowHeight) + overscanRows * 2;
    return { firstRow, start: firstRow * columns, end: Math.min(totalCount, (firstRow + visibleRows) * columns) };
  };
  const galleryTop = () => viewport.getBoundingClientRect().top - scrollRoot.getBoundingClientRect().top + scrollRoot.scrollTop;
  const galleryScrollTop = () => Math.max(0, scrollRoot.scrollTop - galleryTop());
  const updateDebug = (start, end) => {
    const domTiles = windowElement.querySelectorAll(".media-tile").length;
    metrics.peakDomTiles = Math.max(metrics.peakDomTiles, domTiles);
    window.__MEDIA_DESK_DEBUG__ = {
      domTiles,
      cachedBatches: cache.size,
      inflightRequests: inflight.size,
      totalCount,
      renderedStart: start,
      renderedEnd: end,
      columns,
      rowHeight,
      density: app.dataset.density,
      ...metrics,
      currentHeapBytes: globalThis.performance?.memory?.usedJSHeapSize ?? null,
    };
  };
  const render = () => {
    renderScheduled = false;
    readGeometry();
    columns = Math.max(1, Math.floor((viewport.clientWidth + tileGap) / (tileMin + tileGap)));
    canvas.style.height = `${Math.max(1, Math.ceil(totalCount / columns) * rowHeight)}px`;
    const { firstRow, start, end } = visibleRange();
    windowElement.style.transform = `translateY(${firstRow * rowHeight}px)`;
    windowElement.style.gridTemplateColumns = `repeat(${columns}, minmax(0, 1fr))`;
    const cards = [];
    const needed = new Set();
    for (let index = start; index < end; index += 1) {
      const item = itemAt(index);
      if (item) cards.push(cardHtml(item, index));
      else needed.add(Math.floor(index / batchSize) * batchSize);
    }
    windowElement.innerHTML = cards.join("") || (totalCount ? '<div class="gallery-skeleton">Načítání médií…</div>' : '<div class="empty"><h2>Žádná média</h2><p>Změňte filtry nebo hledání.</p></div>');
    [...needed].slice(0, 2).forEach(fetchBatch);
    const firstItem = itemAt(Math.floor(galleryScrollTop() / rowHeight) * columns);
    periodElement.textContent = firstItem?.capture_label || "";
    if (firstItem) setActivePeriod(firstItem);
    updateDebug(start, end);
  };

  const monthName = (month) => new Intl.DateTimeFormat("cs-CZ", { month: "short" }).format(new Date(2020, month - 1, 1));
  const segmentKey = (segment) => segment.year ? `${segment.year}-${String(segment.month).padStart(2, "0")}` : "unknown";
  const renderTimeNavigator = () => {
    if (!form.elements.sort.value.startsWith("captured_")) {
      timeNavigator.innerHTML = '<span class="muted">Časová osa je dostupná jen pro chronologické řazení.</span>';
      return;
    }
    const years = new Map();
    for (const segment of segments.filter((item) => item.year)) {
      if (!years.has(segment.year)) years.set(segment.year, []);
      years.get(segment.year).push(segment);
    }
    timeNavigator.innerHTML = [...years].slice(0, 4).map(([year, months]) => `<div class="time-year"><button type="button" data-period="${year}-${String(months[0].month).padStart(2, "0")}" aria-label="Přejít na rok ${year}">${year}</button><div class="time-months">${months.map((item) => `<button type="button" data-period="${segmentKey(item)}" title="${item.count} médií">${escapeHtml(monthName(item.month))}</button>`).join("")}</div></div>`).join("") + (segments.some((item) => !item.year) ? '<button type="button" data-period="unknown">Bez data</button>' : "");
    timeSelect.innerHTML = '<option value="">Vyberte období…</option>' + segments.map((item) => `<option value="${segmentKey(item)}">${item.year ? `${monthName(item.month)} ${item.year}` : "Bez důvěryhodného data"} · ${item.count}</option>`).join("");
  };
  const setActivePeriod = (item) => {
    let key = "unknown";
    if (item.capture_time && !item.capture_filesystem_fallback) {
      const match = item.capture_time.match(/^(\d{4})-(\d{2})/);
      if (match) key = `${match[1]}-${match[2]}`;
    }
    for (const button of timeNavigator.querySelectorAll("[data-period]")) {
      button.classList.toggle("is-current", button.dataset.period === key);
    }
    timeSelect.value = segments.some((item) => segmentKey(item) === key) ? key : "";
  };
  const jumpToPeriod = async (key) => {
    const segment = segments.find((item) => segmentKey(item) === key);
    if (!segment) return;
    let index = segment.index;
    if (segment.year) {
      const response = await fetch(apiUrl("/api/locate", { year: segment.year, month: segment.month }));
      if (!response.ok) return;
      index = (await response.json()).index;
    }
    await fetchBatch(Math.floor(index / batchSize) * batchSize);
    scrollRoot.scrollTop = galleryTop() + Math.floor(index / columns) * rowHeight;
    scheduleRender();
    viewport.focus({ preventScroll: true });
  };
  const scheduleRender = () => {
    if (!renderScheduled) {
      renderScheduled = true;
      requestAnimationFrame(render);
    }
  };
  const saveAnchor = () => {
    const currentGalleryScroll = galleryScrollTop();
    const index = Math.floor(currentGalleryScroll / rowHeight) * columns;
    const item = itemAt(index);
    if (!item) return;
    sessionStorage.setItem(storageKey, JSON.stringify({
      url: location.pathname + location.search,
      assetId: item.asset_id,
      offset: currentGalleryScroll - Math.floor(index / columns) * rowHeight,
      snapshotId,
    }));
  };
  const locateAndRestore = async (assetId, offset = 0) => {
    if (!assetId) return false;
    const response = await fetch(apiUrl("/api/locate", { asset_id: assetId }));
    if (!response.ok) return false;
    const located = await response.json();
    await fetchBatch(Math.floor(located.index / batchSize) * batchSize);
    scrollRoot.scrollTop = galleryTop() + Math.floor(located.index / columns) * rowHeight + offset;
    scheduleRender();
    return true;
  };
  const applyDensity = (density, preserveAnchor = true) => {
    const allowed = new Set(["small", "medium", "large"]);
    const next = allowed.has(density) ? density : "medium";
    const oldRowHeight = rowHeight;
    const oldColumns = columns;
    const oldScrollTop = scrollRoot.scrollTop;
    const oldGalleryTop = galleryTop();
    const insideGallery = oldScrollTop > oldGalleryTop;
    const currentGalleryScroll = Math.max(0, oldScrollTop - oldGalleryTop);
    const anchorIndex = Math.floor(currentGalleryScroll / oldRowHeight) * oldColumns;
    const offset = currentGalleryScroll % oldRowHeight;
    app.dataset.density = next;
    densityControls.forEach((control) => { control.checked = control.value === next; });
    try { localStorage.setItem("mediaDesk.libraryDensity", next); } catch { /* Preference persistence is optional. */ }
    requestAnimationFrame(() => {
      render();
      if (!preserveAnchor || !insideGallery) scrollRoot.scrollTop = oldScrollTop;
      else scrollRoot.scrollTop = galleryTop() + Math.floor(anchorIndex / columns) * rowHeight + offset;
    });
  };
  const reset = async ({ restore = true } = {}) => {
    generation += 1;
    for (const promise of inflight.values()) promise.controller?.abort();
    inflight.clear();
    cache.clear();
    errorElement.hidden = true;
    const response = await fetch(apiUrl("/api/index"));
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const payload = await response.json();
    snapshotId = payload.snapshot_id;
    totalCount = payload.total_count;
    segments = payload.segments;
    countElement.textContent = `${new Intl.NumberFormat("cs-CZ").format(totalCount)} médií`;
    renderTimeNavigator();
    render();
    if (restore) {
      let stored;
      try { stored = JSON.parse(sessionStorage.getItem(storageKey)); } catch { stored = null; }
      const sameUrl = stored?.url === location.pathname + location.search;
      await locateAndRestore(activeAssetId || (sameUrl ? stored.assetId : null), sameUrl ? stored.offset : 0);
    }
  };
  scrollRoot.addEventListener("scroll", () => { scheduleRender(); saveAnchor(); }, { passive: true });
  new ResizeObserver(() => {
    const oldColumns = columns;
    const oldScrollTop = scrollRoot.scrollTop;
    const oldGalleryTop = galleryTop();
    const insideGallery = oldScrollTop > oldGalleryTop;
    const currentGalleryScroll = galleryScrollTop();
    const anchorIndex = Math.floor(currentGalleryScroll / rowHeight) * oldColumns;
    const anchor = itemAt(anchorIndex);
    const offset = currentGalleryScroll % rowHeight;
    render();
    if (!insideGallery) scrollRoot.scrollTop = oldScrollTop;
    else if (anchor) scrollRoot.scrollTop = galleryTop() + Math.floor(anchorIndex / columns) * rowHeight + offset;
  }).observe(scrollRoot);
  windowElement.addEventListener("click", (event) => { if (event.target.closest("a")) saveAnchor(); });
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const url = new URL("/library", location.origin);
    url.search = params();
    history.pushState({}, "", url);
    activeAssetId = null;
    reset({ restore: false }).catch(() => { errorElement.hidden = false; });
  });
  window.addEventListener("popstate", () => location.reload());
  document.querySelector("#library-retry").addEventListener("click", () => fetchBatch(lastFailedStart));
  document.querySelector("#library-load-more").addEventListener("click", () => fetchBatch(lastFailedStart));
  noticeElement.querySelector("button").addEventListener("click", () => location.reload());
  timeNavigator.addEventListener("click", (event) => {
    const button = event.target.closest("[data-period]");
    if (button) jumpToPeriod(button.dataset.period);
  });
  timeSelect.addEventListener("change", () => jumpToPeriod(timeSelect.value));
  form.elements.media_type.addEventListener("change", () => form.requestSubmit());
  form.elements.sort.addEventListener("change", () => form.requestSubmit());
  densityControls.forEach((control) => control.addEventListener("change", () => applyDensity(control.value)));
  let initialDensity = "medium";
  try { initialDensity = localStorage.getItem("mediaDesk.libraryDensity") || initialDensity; } catch { /* Optional preference. */ }
  applyDensity(initialDensity, false);
  reset().catch(() => { errorElement.hidden = false; countElement.textContent = "Knihovnu nelze načíst"; });
}
