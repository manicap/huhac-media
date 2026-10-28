import { describe, expect, it } from "vitest";

import { createPlaybackPreferencesStore } from "./playbackPreferences";

class MemoryStorage {
  private readonly values = new Map<string, string>();

  getItem(key: string) {
    return this.values.get(key) ?? null;
  }

  setItem(key: string, value: string) {
    this.values.set(key, value);
  }
}

describe("playback preferences", () => {
  it("starts at 50 percent and persists volume and mute across a reload", () => {
    const storage = new MemoryStorage();
    const first = createPlaybackPreferencesStore(storage);
    expect(first.getState().volume).toBe(0.5);
    expect(first.getState().muted).toBe(false);

    first.getState().setVolume(0.35);
    first.getState().setMuted(true);
    const reloaded = createPlaybackPreferencesStore(storage);

    expect(reloaded.getState().volume).toBe(0.35);
    expect(reloaded.getState().muted).toBe(true);
    reloaded.getState().setVolume(0);
    reloaded.getState().setMuted(false);
    expect(reloaded.getState().volume).toBe(0.35);
  });

  it("ignores malformed persisted values and unavailable storage", () => {
    const malformed = {
      getItem: () => "{not-json",
      setItem: () => { throw new Error("blocked"); },
    };
    const store = createPlaybackPreferencesStore(malformed);

    expect(store.getState().volume).toBe(0.5);
    expect(() => store.getState().setVolume(0.7)).not.toThrow();
    expect(store.getState().volume).toBe(0.7);
  });
});
