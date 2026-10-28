import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { useStudioStore } from "../../context/studioStore";
import { useStudioData } from "../../data/StudioDataProvider";
import type { MediaSummary } from "../../data/contracts";

const kindLabels: Record<MediaSummary["kind"], string> = {
  image: "Fotografie",
  video: "Video",
  audio: "Audio",
  graphic: "Grafika",
};

function formatDate(value: string | null): string {
  if (!value) return "Bez data";
  return new Intl.DateTimeFormat("cs-CZ", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "Europe/Prague",
  }).format(new Date(value));
}

export function MediaLibraryModule() {
  const [density, setDensity] = useState<"comfortable" | "compact">("comfortable");
  const workspaceId = useStudioStore((state) => state.workspaceId);
  const projectId = useStudioStore((state) => state.projectId);
  const selectedMediaIds = useStudioStore((state) => state.selectedMediaIds);
  const toggleMedia = useStudioStore((state) => state.toggleMedia);
  const dataSource = useStudioData();
  const mediaQuery = useQuery({
    queryKey: ["studio", "media", workspaceId, projectId],
    queryFn: () => dataSource.listMedia(workspaceId!, projectId!),
    enabled: workspaceId !== null && projectId !== null,
  });

  return (
    <div className="module-page media-library-module">
      <header className="module-heading">
        <div>
          <p className="eyebrow">Výběr podle stabilních ID</p>
          <h1>Mediální knihovna</h1>
          <p className="module-lead">
            Read-only pohled syntetických médií přiřazených k aktivnímu projektu.
          </p>
        </div>
        <div className="density-control" role="group" aria-label="Hustota knihovny">
          <button
            type="button"
            aria-pressed={density === "comfortable"}
            onClick={() => setDensity("comfortable")}
          >
            Pohodlná
          </button>
          <button
            type="button"
            aria-pressed={density === "compact"}
            onClick={() => setDensity("compact")}
          >
            Kompaktní
          </button>
        </div>
      </header>

      {!projectId || !workspaceId ? (
        <section className="module-state" role="status">
          <h2>Nejprve vyberte projekt</h2>
          <p>Knihovna se automaticky přepne podle sdíleného pracovního kontextu.</p>
        </section>
      ) : mediaQuery.isPending ? (
        <section className="module-state" role="status">Načítám média…</section>
      ) : mediaQuery.isError ? (
        <section className="module-state module-state--error" role="alert">
          <h2>Knihovnu se nepodařilo načíst</h2>
          <p>Projekt zůstal aktivní; datový adaptér ale vrátil chybu.</p>
        </section>
      ) : mediaQuery.data?.length === 0 ? (
        <section className="module-state" role="status">
          <h2>Tento projekt zatím nemá žádná média</h2>
          <p>Prototyp nic nevytváří ani nezapisuje do stávající pipeline.</p>
        </section>
      ) : (
        <div
          className={`media-grid media-grid--${density}`}
          aria-label="Média aktivního projektu"
        >
          {mediaQuery.data?.map((media) => {
            const selected = selectedMediaIds.includes(media.id);
            return (
              <article
                className={selected ? "media-card media-card--selected" : "media-card"}
                key={media.id}
              >
                <div
                  className="media-card__preview"
                  style={{ background: media.accent }}
                  aria-hidden="true"
                >
                  <span>{kindLabels[media.kind]}</span>
                </div>
                <div className="media-card__body">
                  <div>
                    <strong>{media.title}</strong>
                    <span>{formatDate(media.capturedAt)}</span>
                  </div>
                  <label className="media-select">
                    <input
                      type="checkbox"
                      checked={selected}
                      onChange={() => toggleMedia(media.id)}
                    />
                    <span className="sr-only">Vybrat {media.title}</span>
                  </label>
                </div>
              </article>
            );
          })}
        </div>
      )}
    </div>
  );
}
