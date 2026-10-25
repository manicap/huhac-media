const STORAGE_KEY = "mediaDesk.videoAudio";
const managedVideos = new Set();
let activeVideo = null;
let applying = false;

const readPreference = () => {
  try {
    const value = JSON.parse(localStorage.getItem(STORAGE_KEY));
    const volume = Number(value?.volume);
    return {
      volume: Number.isFinite(volume) ? Math.max(0, Math.min(1, volume)) : 1,
      muted: value?.muted === true,
    };
  } catch {
    return { volume: 1, muted: false };
  }
};

let preference = readPreference();

const applyPreference = (video) => {
  applying = true;
  video.volume = preference.volume;
  video.muted = preference.muted;
  applying = false;
};

const publishPreference = (source) => {
  preference = { volume: source.volume, muted: source.muted };
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(preference)); } catch { /* Persistence is optional. */ }
  for (const video of managedVideos) if (video !== source) applyPreference(video);
};

export const bindManagedVideo = (video) => {
  if (!video || managedVideos.has(video)) return video;
  managedVideos.add(video);
  applyPreference(video);
  video.addEventListener("play", () => {
    if (activeVideo && activeVideo !== video) activeVideo.pause();
    activeVideo = video;
  });
  video.addEventListener("pause", () => { if (activeVideo === video) activeVideo = null; });
  video.addEventListener("volumechange", () => { if (!applying) publishPreference(video); });
  video.addEventListener("emptied", () => managedVideos.delete(video), { once: true });
  return video;
};

window.addEventListener("storage", (event) => {
  if (event.key !== STORAGE_KEY) return;
  preference = readPreference();
  for (const video of managedVideos) applyPreference(video);
});
