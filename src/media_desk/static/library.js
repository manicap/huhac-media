import { bindManagedVideo } from "/static/media-controls.js?v=1.0.0";

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
  const splitDialog = document.querySelector("#event-split-dialog");
  const splitForm = document.querySelector("#event-split-form");
  const splitOutput = document.querySelector("#event-split-preview");
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
  let renderedSignature = "";
  let lastFailedStart = 0;
  let activeAssetId = app.dataset.activeAssetId || new URL(location.href).searchParams.get("active_asset_id");
  let segments = [];
  let sections = [];
  let eventsRevision = 0;
  let layoutRows = [];
  const collapsedSections = new Set();
  const sectionHeaderHeight = 42;
  let rowHeight = 260;
  let tileMin = 176;
  let tileGap = 10;
  let tileToolbarHeight = 30;
  let tileFooterHeight = 50;
  let menuAnchor = null;
  let menuItem = null;
  const menuOverlay = document.createElement("div");
  menuOverlay.id = "card-action-menu";
  menuOverlay.className = "card-menu-overlay";
  menuOverlay.hidden = true;
  menuOverlay.innerHTML = '<button type="button" data-card-action="split">Zahájit novou akci od tohoto média</button><button type="button" data-card-action="manage">Spravovat akce…</button><button type="button" data-card-action="copy-path">Kopírovat cestu</button><button type="button" data-card-action="copy-name">Kopírovat katalogizační název</button><button type="button" data-card-action="copy-id">Kopírovat asset ID</button><button type="button" data-card-action="reveal">Otevřít v Průzkumníku</button>';
  document.body.append(menuOverlay);
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
    tileMin = Number.parseFloat(styles.getPropertyValue("--tile-min")) || 176;
    tileGap = Number.parseFloat(styles.getPropertyValue("--tile-gap")) || 10;
    tileToolbarHeight = Number.parseFloat(styles.getPropertyValue("--tile-toolbar-height")) || 30;
    tileFooterHeight = Number.parseFloat(styles.getPropertyValue("--tile-footer-height")) || 50;
  };
  const updateRowGeometry = () => {
    const trackWidth = (viewport.clientWidth - tileGap * (columns - 1)) / columns;
    const previewWidth = Math.max(1, trackWidth - 2);
    const tileHeight = previewWidth * 16 / 9 + tileToolbarHeight + tileFooterHeight + 2;
    rowHeight = tileHeight + tileGap;
    app.style.setProperty("--tile-height", `${tileHeight}px`);
    app.style.setProperty("--tile-row-height", `${rowHeight}px`);
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
  const formatCaptureParts = (item) => {
    if (!item.capture_time) return { time: "Čas neznámý", date: "Datum pořízení neznámé" };
    const match = item.capture_time.match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2}))?/);
    if (!match) return { time: "Čas neznámý", date: item.capture_label || "Datum pořízení neznámé" };
    let qualifier = "";
    if (item.capture_filesystem_fallback) qualifier = "čas souboru · nízká důvěra";
    else if (!(item.capture_timezone || item.capture_time.endsWith("Z") || item.capture_time.slice(10).includes("+"))) qualifier = "bez časové zóny";
    return {
      time: `${match[4]}:${match[5]}`,
      date: `${Number(match[3])}. ${Number(match[2])}. ${match[1]}`,
      qualifier,
    };
  };
  const formatDuration = (item) => {
    const seconds = Number(item.technical?.duration_seconds);
    if (!Number.isFinite(seconds) || seconds < 0) return "";
    const rounded = Math.round(seconds);
    const hours = Math.floor(rounded / 3600);
    const minutes = Math.floor((rounded % 3600) / 60);
    const rest = rounded % 60;
    return hours ? `${hours}:${String(minutes).padStart(2, "0")}:${String(rest).padStart(2, "0")}` : `${String(minutes).padStart(2, "0")}:${String(rest).padStart(2, "0")}`;
  };
  const cardHtml = (item, index) => {
    const preview = item.preview_url
      ? `<img src="${escapeHtml(item.preview_url)}" alt="Náhled ${escapeHtml(item.display_name)}" width="320" height="210" loading="lazy" decoding="async">`
      : '<div class="placeholder brand-placeholder"><img src="/static/huhac-placeholder.png?v=1.0.0" alt="" width="220" height="124" loading="lazy" decoding="async"><small>Bez náhledu</small></div>';
    const url = new URL(`/assets/${item.sha256}`, location.origin);
    url.searchParams.set("return_to", location.pathname + location.search);
    url.searchParams.set("active_asset_id", item.asset_id);
    const duration = item.media_type === "video" ? formatDuration(item) : "";
    const capture = formatCaptureParts(item);
    const type = item.media_type === "video" ? "Video" : "Foto";
    const mediaLabel = [type, duration].filter(Boolean).join(" · ");
    const mediaIcon = item.media_type === "video" ? "▶" : "▣";
    const eventName = item.event_names?.length ? item.event_names.join(" / ") : "Bez přiřazené akce";
    const play = item.media_type === "video" && item.original_url
      ? '<button class="tile-play" type="button" aria-label="Přehrát video"><span class="tile-action-icon" aria-hidden="true">▶</span><span class="tile-action-label">Přehrát</span></button>' : "";
    const unavailable = item.original_url ? "" : '<span class="offline-pill">Soubor nedostupný</span>';
    return `<article class="media-tile${item.asset_id === activeAssetId ? " is-active" : ""}" data-index="${index}" data-asset-id="${escapeHtml(item.asset_id)}">
      <div class="tile-preview"><a class="tile-visual" href="${escapeHtml(url.pathname + url.search)}">${preview}</a><span class="tile-media-badge"><span aria-hidden="true">${mediaIcon}</span><span>${escapeHtml(mediaLabel)}</span></span><span class="tile-capture-overlay" title="${escapeHtml(item.capture_time || item.capture_label)}"><strong class="tile-time">${escapeHtml(capture.time)}</strong><span class="tile-date">${escapeHtml(capture.date)}</span>${capture.qualifier ? `<span class="tile-capture-qualifier">${escapeHtml(capture.qualifier)}</span>` : ""}</span>${unavailable}<span class="tile-file-error" hidden>Soubor nedostupný</span></div>
      <div class="tile-toolbar">${play}<a class="tile-detail" href="${escapeHtml(url.pathname + url.search)}" aria-label="Otevřít detail média"><span class="tile-action-icon" aria-hidden="true">↗</span><span class="tile-action-label">Detail</span></a><span class="tile-playback-clock" hidden>00:00.0 / 00:00.0</span><span class="tile-toolbar-spacer"></span><button class="tile-menu-button" type="button" aria-label="Akce s médiem" aria-expanded="false" aria-controls="card-action-menu">•••</button></div>
      <div class="tile-copy">
        <span class="tile-event${item.event_names?.length ? "" : " is-unassigned"}" title="${escapeHtml(eventName)}">${escapeHtml(eventName)}</span>
        <span class="tile-capture-inline" title="${escapeHtml(item.capture_time || item.capture_label)}">${escapeHtml(capture.time)} · ${escapeHtml(capture.date)}</span>
        <span class="tile-name" title="${escapeHtml(item.display_name)}">${escapeHtml(item.display_name)}</span>
      </div>
    </article>`;
  };
  const closeMenu = () => {
    menuAnchor?.setAttribute("aria-expanded", "false");
    menuOverlay.hidden = true;
    menuOverlay.style.removeProperty("left");
    menuOverlay.style.removeProperty("top");
    menuAnchor = null;
    menuItem = null;
  };
  const positionMenu = () => {
    if (menuOverlay.hidden || !menuAnchor?.isConnected) return closeMenu();
    const margin = 8;
    const gap = 5;
    const anchor = menuAnchor.getBoundingClientRect();
    const menu = menuOverlay.getBoundingClientRect();
    const roomBelow = window.innerHeight - anchor.bottom - margin;
    const roomAbove = anchor.top - margin;
    const top = roomBelow >= menu.height + gap || roomBelow >= roomAbove
      ? anchor.bottom + gap
      : anchor.top - menu.height - gap;
    const preferredLeft = anchor.right - menu.width;
    menuOverlay.style.left = `${Math.max(margin, Math.min(preferredLeft, window.innerWidth - menu.width - margin))}px`;
    menuOverlay.style.top = `${Math.max(margin, Math.min(top, window.innerHeight - menu.height - margin))}px`;
  };
  const openMenu = (button, item) => {
    if (menuAnchor === button && !menuOverlay.hidden) return closeMenu();
    closeMenu();
    menuAnchor = button;
    menuItem = item;
    const splitAction = menuOverlay.querySelector('[data-card-action="split"]');
    const trustedTime = item?.capture_time && !item.capture_filesystem_fallback && (item.capture_timezone || item.capture_time.endsWith("Z") || item.capture_time.slice(10).includes("+"));
    splitAction.disabled = !(trustedTime && item?.event_assignment && item?.sessions?.length);
    menuOverlay.querySelector('[data-card-action="copy-path"]').disabled = !item?.original_path;
    const revealAction = menuOverlay.querySelector('[data-card-action="reveal"]');
    revealAction.disabled = !item?.original_path;
    revealAction.hidden = window.matchMedia("(max-width: 620px), (pointer: coarse)").matches;
    menuOverlay.hidden = false;
    button.setAttribute("aria-expanded", "true");
    positionMenu();
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
  const buildLayout = () => {
    layoutRows = [];
    let top = 0;
    for (const section of sections) {
      layoutRows.push({ type: "header", top, height: sectionHeaderHeight, section });
      top += sectionHeaderHeight;
      if (!collapsedSections.has(section.event_id)) {
        for (let start = section.start_index; start < section.start_index + section.count; start += columns) {
          const end = Math.min(start + columns, section.start_index + section.count);
          layoutRows.push({ type: "cards", top, height: rowHeight, start, end, section });
          top += rowHeight;
        }
      }
    }
    canvas.style.height = `${Math.max(1, top)}px`;
  };
  const rowAtScroll = (value = galleryScrollTop()) => {
    const forward = layoutRows.find((row) => row.top + row.height > value && row.type === "cards");
    if (forward) return forward;
    for (let index = layoutRows.length - 1; index >= 0; index -= 1) {
      if (layoutRows[index].type === "cards") return layoutRows[index];
    }
    return null;
  };
  const topForIndex = (index) => layoutRows.find((row) => row.type === "cards" && index >= row.start && index < row.end)?.top ?? 0;
  const ensureIndexVisible = (index) => {
    const section = sections.find((item) => index >= item.start_index && index < item.start_index + item.count);
    if (section && collapsedSections.delete(section.event_id)) buildLayout();
  };
  const visibleRows = () => {
    const from = Math.max(0, galleryScrollTop() - overscanRows * rowHeight);
    const to = galleryScrollTop() + scrollRoot.clientHeight + overscanRows * rowHeight;
    return layoutRows.filter((row) => row.top + row.height >= from && row.top <= to);
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
    updateRowGeometry();
    buildLayout();
    const visible = visibleRows();
    const firstTop = visible[0]?.top || 0;
    const cardRows = visible.filter((row) => row.type === "cards");
    const start = cardRows[0]?.start || 0;
    const end = cardRows.at(-1)?.end || 0;
    windowElement.style.transform = `translateY(${firstTop}px)`;
    const rows = [];
    const needed = new Set();
    let cursorTop = firstTop;
    for (const row of visible) {
      if (row.top > cursorTop) rows.push(`<div style="height:${row.top - cursorTop}px"></div>`);
      if (row.type === "header") {
        const collapsed = collapsedSections.has(row.section.event_id);
        const date = row.section.date ? new Intl.DateTimeFormat("cs-CZ", { dateStyle: "medium" }).format(new Date(`${row.section.date}T12:00:00`)) : "Bez spolehlivého data";
        rows.push(`<section class="library-section" style="height:${row.height}px"><button type="button" data-section-toggle="${escapeHtml(row.section.event_id)}" aria-expanded="${!collapsed}"><span aria-hidden="true">${collapsed ? "▸" : "▾"}</span><strong>${escapeHtml(row.section.name)}</strong><span>${escapeHtml(date)} · ${row.section.count} médií</span></button></section>`);
      } else {
        const cards = [];
        for (let index = row.start; index < row.end; index += 1) {
          const item = itemAt(index);
          if (item) cards.push(cardHtml(item, index));
          else needed.add(Math.floor(index / batchSize) * batchSize);
        }
        rows.push(`<div class="library-card-row" style="height:${row.height}px;grid-template-columns:repeat(${columns},minmax(0,1fr))">${cards.join("")}</div>`);
      }
      cursorTop = row.top + row.height;
    }
    const signature = `${generation}:${columns}:${firstTop}:${start}:${end}:${[...collapsedSections].join(",")}:${rows.map((row) => row.slice(0, 120)).join("|")}`;
    if (signature !== renderedSignature) {
      closeMenu();
      windowElement.innerHTML = rows.join("") || (totalCount ? '<div class="gallery-skeleton">Načítání médií…</div>' : '<div class="empty"><h2>Žádná média</h2><p>Změňte filtry nebo hledání.</p></div>');
      renderedSignature = signature;
    }
    [...needed].slice(0, 2).forEach(fetchBatch);
    const firstItem = itemAt(rowAtScroll()?.start ?? 0);
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
    ensureIndexVisible(index);
    scrollRoot.scrollTop = galleryTop() + topForIndex(index);
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
    const currentRow = rowAtScroll(currentGalleryScroll);
    const index = currentRow?.start ?? 0;
    const item = itemAt(index);
    if (!item) return;
    sessionStorage.setItem(storageKey, JSON.stringify({
      url: location.pathname + location.search,
      assetId: item.asset_id,
      offset: currentGalleryScroll - (currentRow?.top ?? 0),
      snapshotId,
    }));
  };
  const locateAndRestore = async (assetId, offset = 0) => {
    if (!assetId) return false;
    const response = await fetch(apiUrl("/api/locate", { asset_id: assetId }));
    if (!response.ok) return false;
    const located = await response.json();
    await fetchBatch(Math.floor(located.index / batchSize) * batchSize);
    ensureIndexVisible(located.index);
    scrollRoot.scrollTop = galleryTop() + topForIndex(located.index) + offset;
    scheduleRender();
    return true;
  };
  const applyDensity = (density, preserveAnchor = true) => {
    const allowed = new Set(["small", "medium", "large"]);
    const next = allowed.has(density) ? density : "medium";
    const oldScrollTop = scrollRoot.scrollTop;
    const oldGalleryTop = galleryTop();
    const insideGallery = oldScrollTop > oldGalleryTop;
    const currentGalleryScroll = Math.max(0, oldScrollTop - oldGalleryTop);
    const anchorRow = rowAtScroll(currentGalleryScroll);
    const anchorIndex = anchorRow?.start ?? 0;
    const offset = currentGalleryScroll - (anchorRow?.top ?? 0);
    app.dataset.density = next;
    densityControls.forEach((control) => { control.checked = control.value === next; });
    try { localStorage.setItem("mediaDesk.libraryDensity", next); } catch { /* Preference persistence is optional. */ }
    requestAnimationFrame(() => {
      render();
      if (!preserveAnchor || !insideGallery) scrollRoot.scrollTop = oldScrollTop;
      else scrollRoot.scrollTop = galleryTop() + topForIndex(anchorIndex) + offset;
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
    sections = payload.sections;
    eventsRevision = payload.events_revision;
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
  const itemForTile = (tile) => itemAt(Number(tile?.dataset.index));
  const showFileError = (tile, message = "Soubor nedostupný") => {
    const label = tile.querySelector(".tile-file-error");
    if (label) { label.textContent = message; label.hidden = false; }
  };
  const copyText = async (value, button) => {
    if (!value) return;
    try {
      await navigator.clipboard.writeText(value);
    } catch {
      const field = document.createElement("textarea");
      field.value = value;
      field.style.position = "fixed";
      field.style.opacity = "0";
      document.body.append(field);
      field.select();
      document.execCommand("copy");
      field.remove();
    }
    const previous = button.textContent;
    button.textContent = "Zkopírováno";
    setTimeout(() => { button.textContent = previous; }, 900);
  };
  const updatePlayButton = (tile, playing) => {
    const button = tile.querySelector(".tile-play");
    if (!button) return;
    button.setAttribute("aria-label", playing ? "Pozastavit video" : "Přehrát video");
    const icon = button.querySelector(".tile-action-icon");
    const label = button.querySelector(".tile-action-label");
    if (icon) icon.textContent = playing ? "Ⅱ" : "▶";
    if (label) label.textContent = playing ? "Pauza" : "Přehrát";
    tile.classList.toggle("is-playing", playing);
  };
  const formatPlayback = (seconds) => {
    const safe = Number.isFinite(seconds) && seconds >= 0 ? seconds : 0;
    const minutes = Math.floor(safe / 60);
    const rest = (safe % 60).toFixed(1).padStart(4, "0");
    return `${String(minutes).padStart(2, "0")}:${rest}`;
  };
  const updatePlaybackClock = (tile, video) => {
    const clock = tile.querySelector(".tile-playback-clock");
    if (!clock) return;
    clock.hidden = false;
    clock.textContent = `${formatPlayback(video.currentTime)} / ${formatPlayback(video.duration)}`;
  };
  const activateVideo = async (tile, item) => {
    if (!item?.original_url) return showFileError(tile);
    const existing = tile.querySelector("video");
    if (existing) {
      if (existing.paused) await existing.play();
      else existing.pause();
      return;
    }
    const visual = tile.querySelector(".tile-visual");
    if (!visual) return;
    const wrapper = document.createElement("div");
    wrapper.className = "tile-visual is-playing";
    const video = document.createElement("video");
    video.src = item.original_url;
    if (item.preview_url) video.poster = item.preview_url;
    video.controls = true;
    video.preload = "metadata";
    video.playsInline = true;
    tile.classList.add("has-player");
    video.addEventListener("error", () => showFileError(tile), { once: true });
    video.addEventListener("play", () => updatePlayButton(tile, true));
    video.addEventListener("pause", () => updatePlayButton(tile, false));
    video.addEventListener("ended", () => updatePlayButton(tile, false));
    for (const name of ["loadedmetadata", "durationchange", "timeupdate", "seeking", "seeked", "pause"]) {
      video.addEventListener(name, () => updatePlaybackClock(tile, video));
    }
    wrapper.append(video);
    visual.replaceWith(wrapper);
    bindManagedVideo(video);
    try { await video.play(); } catch { /* Browser autoplay policy may still require another user gesture. */ }
  };
  scrollRoot.addEventListener("scroll", () => { closeMenu(); scheduleRender(); saveAnchor(); }, { passive: true });
  new ResizeObserver(() => {
    closeMenu();
    const oldScrollTop = scrollRoot.scrollTop;
    const oldGalleryTop = galleryTop();
    const insideGallery = oldScrollTop > oldGalleryTop;
    const currentGalleryScroll = galleryScrollTop();
    const anchorRow = rowAtScroll(currentGalleryScroll);
    const anchorIndex = anchorRow?.start ?? 0;
    const anchor = itemAt(anchorIndex);
    const offset = currentGalleryScroll - (anchorRow?.top ?? 0);
    render();
    if (!insideGallery) scrollRoot.scrollTop = oldScrollTop;
    else if (anchor) scrollRoot.scrollTop = galleryTop() + topForIndex(anchorIndex) + offset;
  }).observe(scrollRoot);
  windowElement.addEventListener("click", async (event) => {
    const sectionToggle = event.target.closest("[data-section-toggle]");
    if (sectionToggle) {
      const id = sectionToggle.dataset.sectionToggle;
      if (collapsedSections.has(id)) collapsedSections.delete(id); else collapsedSections.add(id);
      renderedSignature = "";
      render();
      return;
    }
    const tile = event.target.closest(".media-tile");
    if (!tile) return;
    const item = itemForTile(tile);
    const menuButton = event.target.closest(".tile-menu-button");
    if (menuButton) {
      openMenu(menuButton, item);
      return;
    }
    if (event.target.closest(".tile-play")) {
      await activateVideo(tile, item);
      return;
    }
    if (event.target.closest(".tile-detail")) {
      tile.querySelector("video")?.pause();
      saveAnchor();
      return;
    }
    if (event.target.closest("a")) saveAnchor();
  });
  menuOverlay.addEventListener("click", async (event) => {
    const action = event.target.closest("[data-card-action]");
    if (!action || !menuItem) return;
    const item = menuItem;
    const tile = menuAnchor?.closest(".media-tile");
    const name = action.dataset.cardAction;
    if (name === "copy-path") await copyText(item.original_path, action);
    if (name === "copy-name") await copyText(item.catalog_name, action);
    if (name === "copy-id") await copyText(item.asset_id, action);
    if (name === "split") {
      splitForm.elements.event_id.value = item.event_assignment.event_id;
      splitForm.elements.session_id.value = item.sessions[0].session_id;
      splitForm.elements.revision.value = eventsRevision;
      splitForm.elements.boundary.value = item.capture_time.slice(0, 16);
      splitForm.elements.new_name.value = "Nová akce";
      splitOutput.textContent = "Nejprve zkontrolujte náhled rozdělení.";
      splitForm.querySelector("[data-split-confirm]").disabled = true;
      splitDialog.showModal();
    }
    if (name === "manage") location.href = "/events";
    if (name === "reveal") {
      const response = await fetch(`/api/assets/${item.sha256}/reveal`, {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded", Accept: "application/json" },
        body: new URLSearchParams({ csrf_token: app.dataset.csrfToken }),
      });
      if (!response.ok && tile) {
        let message = "Soubor nedostupný";
        try { message = (await response.json()).detail || message; } catch { /* Use safe fallback. */ }
        showFileError(tile, message);
      }
    }
    if (name !== "copy-path" && name !== "copy-name" && name !== "copy-id") closeMenu();
  });
  document.addEventListener("click", (event) => {
    if (event.target.closest(".card-menu-overlay, .tile-menu-button")) return;
    closeMenu();
  });
  document.addEventListener("keydown", (event) => { if (event.key === "Escape") closeMenu(); });
  window.addEventListener("resize", positionMenu, { passive: true });
  const splitRequest = async (path) => {
    const response = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded", Accept: "application/json" },
      body: new URLSearchParams(new FormData(splitForm)),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || `HTTP ${response.status}`);
    return payload;
  };
  const summarizeSplit = (payload) => `Původní akce: ${payload.retained_count} · nová akce: ${payload.moved_count} · bez spolehlivého času: ${payload.unknown_count} · ručně přiřazené: ${payload.manual_count}`;
  splitForm.addEventListener("input", () => { splitForm.querySelector("[data-split-confirm]").disabled = true; });
  splitForm.querySelector("[data-split-preview]").addEventListener("click", async () => {
    try {
      const payload = await splitRequest("/events/split/preview");
      splitOutput.textContent = summarizeSplit(payload);
      splitForm.querySelector("[data-split-confirm]").disabled = false;
    } catch (error) { splitOutput.textContent = error.message; }
  });
  splitForm.querySelector("[data-split-confirm]").addEventListener("click", async () => {
    try {
      const payload = await splitRequest("/events/split");
      splitOutput.textContent = summarizeSplit(payload);
      splitDialog.close();
      await reset({ restore: false });
    } catch (error) { splitOutput.textContent = error.message; }
  });
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
  form.elements.event_id.addEventListener("change", () => form.requestSubmit());
  densityControls.forEach((control) => control.addEventListener("change", () => applyDensity(control.value)));
  let initialDensity = "medium";
  try { initialDensity = localStorage.getItem("mediaDesk.libraryDensity") || initialDensity; } catch { /* Optional preference. */ }
  applyDensity(initialDensity, false);
  reset().catch(() => { errorElement.hidden = false; countElement.textContent = "Knihovnu nelze načíst"; });
}
