import { useMemo, useState, type CSSProperties } from "react";

import type { MediaSummary } from "../../data/contracts";
import { VideoPlayer } from "./VideoPlayer";

const kindLabels: Record<MediaSummary["kind"], string> = {
  image: "Fotografie",
  video: "Video",
};

function formatDuration(value: number | null): string {
  if (value === null || !Number.isFinite(value) || value <= 0) return "Délka neuvedena";
  const seconds = Math.round(value);
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const remainder = seconds % 60;
  return hours > 0
    ? `${hours}:${String(minutes).padStart(2, "0")}:${String(remainder).padStart(2, "0")}`
    : `${minutes}:${String(remainder).padStart(2, "0")}`;
}

function metadataRatio(media: MediaSummary): number | null {
  if (!media.width || !media.height) return null;
  const rotated = media.rotation !== null && Math.abs(media.rotation % 180) === 90;
  return rotated ? media.height / media.width : media.width / media.height;
}

function originalState(media: MediaSummary): string {
  if (!media.originalAvailable || media.originalAccessState === "offline") return "Nedostupný";
  return "Neověřený";
}

export function MediaCard({
  media,
  selected,
  selectionDisabled,
  selectionHint,
  playerActive,
  onToggleSelection,
  onActivatePlayer,
  onClosePlayer,
}: {
  readonly media: MediaSummary;
  readonly selected: boolean;
  readonly selectionDisabled: boolean;
  readonly selectionHint?: string;
  readonly playerActive: boolean;
  readonly onToggleSelection: () => void;
  readonly onActivatePlayer: () => void;
  readonly onClosePlayer: () => void;
}) {
  const initialRatio = useMemo(() => metadataRatio(media), [media]);
  const [naturalRatio, setNaturalRatio] = useState<number | null>(null);
  const ratio = naturalRatio ?? initialRatio ?? 16 / 10;
  const unavailable = media.availability !== "available"
    || (media.resolution !== undefined && media.resolution !== "resolved");
  const canPlay = media.kind === "video" && media.originalUrl !== null && !unavailable;

  return (
    <article
      className={selected ? "media-card media-card--selected" : "media-card"}
      style={{ "--media-aspect": ratio } as CSSProperties}
    >
      <div
        className={`media-card__preview media-card__preview--${media.kind}`}
        style={{ aspectRatio: String(ratio) }}
      >
        {playerActive && media.originalUrl ? (
          <VideoPlayer
            title={media.title}
            source={media.originalUrl}
            poster={media.previewUrl}
            onClose={onClosePlayer}
            onAspectRatio={setNaturalRatio}
          />
        ) : (
          <>
            {media.previewUrl ? (
              <img
                src={media.previewUrl}
                alt=""
                decoding="async"
                loading="lazy"
                onLoad={(event) => {
                  const image = event.currentTarget;
                  if (image.naturalWidth > 0 && image.naturalHeight > 0) {
                    setNaturalRatio(image.naturalWidth / image.naturalHeight);
                  }
                }}
              />
            ) : <span className="media-card__placeholder">Náhled není dostupný</span>}
            {media.kind === "video" ? (
              <button
                className="media-card__play"
                type="button"
                disabled={!canPlay}
                onClick={onActivatePlayer}
                aria-label={canPlay ? `Přehrát ${media.title}` : `Video ${media.title} není dostupné`}
              >
                {canPlay ? "Přehrát" : "Video nedostupné"}
              </button>
            ) : null}
          </>
        )}
        <span className="media-card__kind">{kindLabels[media.kind]}</span>
      </div>
      <div className="media-card__body">
        <div className="media-card__summary">
          <strong title={media.title}>{media.title}</strong>
          <dl className="media-card__metadata">
            <div><dt>Rozlišení</dt><dd>{media.width && media.height ? `${media.width} × ${media.height}` : "Neuvedeno"}</dd></div>
            {media.kind === "video" ? <div><dt>Délka</dt><dd>{formatDuration(media.durationSeconds)}</dd></div> : null}
            <div><dt>Originál</dt><dd>{originalState(media)}</dd></div>
          </dl>
          {selectionHint ? <small>{selectionHint}</small> : null}
          {unavailable ? <small>Médium je momentálně nedostupné</small> : null}
        </div>
        <label className="media-select">
          <input
            type="checkbox"
            checked={selected}
            disabled={selectionDisabled}
            onChange={onToggleSelection}
          />
          <span className="sr-only">Vybrat {media.title}</span>
        </label>
      </div>
    </article>
  );
}
