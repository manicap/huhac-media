import { useEffect, useLayoutEffect, useRef, useState } from "react";

import { usePlaybackPreferences } from "../../playback/playbackPreferences";

export function VideoPlayer({
  title,
  source,
  poster,
  onClose,
  onAspectRatio,
}: {
  readonly title: string;
  readonly source: string;
  readonly poster: string | null;
  readonly onClose: () => void;
  readonly onAspectRatio: (ratio: number) => void;
}) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  const volume = usePlaybackPreferences((preferences) => preferences.volume);
  const muted = usePlaybackPreferences((preferences) => preferences.muted);
  const syncFromMedia = usePlaybackPreferences((preferences) => preferences.syncFromMedia);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    video.volume = volume;
    video.muted = muted;
  }, [muted, volume]);

  useLayoutEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    let disposed = false;
    void video.play().catch(() => {
      if (!disposed) setState("ready");
    });
    return () => {
      disposed = true;
      video.pause();
      video.removeAttribute("src");
      video.load();
    };
  }, [source]);

  return (
    <div className="video-player">
      <video
        aria-label={`Přehrávač ${title}`}
        controls
        onCanPlay={() => setState("ready")}
        onError={() => setState("error")}
        onLoadedMetadata={(event) => {
          const video = event.currentTarget;
          if (video.videoWidth > 0 && video.videoHeight > 0) {
            onAspectRatio(video.videoWidth / video.videoHeight);
          }
          setState("ready");
        }}
        onPlaying={() => setState("ready")}
        onVolumeChange={(event) => {
          const video = event.currentTarget;
          syncFromMedia(video.volume, video.muted);
        }}
        onWaiting={() => setState((current) => current === "error" ? current : "loading")}
        playsInline
        poster={poster ?? undefined}
        preload="metadata"
        ref={videoRef}
        src={source}
      />
      {state === "loading" ? <span className="video-player__status" role="status">Načítám video…</span> : null}
      {state === "error" ? (
        <span className="video-player__status video-player__status--error" role="alert">
          Video nelze přehrát. Formát nebo kodek nemusí být v tomto prohlížeči podporovaný.
        </span>
      ) : null}
      <button className="video-player__close" type="button" onClick={onClose}>
        Zavřít přehrávač
      </button>
    </div>
  );
}
