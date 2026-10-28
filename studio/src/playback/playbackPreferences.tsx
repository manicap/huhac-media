import { createContext, type ReactNode, useContext, useState } from "react";
import { useStore } from "zustand";
import { createStore, type StoreApi } from "zustand/vanilla";

const STORAGE_KEY = "huhac-studio-playback-preferences-v1";
const DEFAULT_VOLUME = 0.5;

type PreferenceStorage = Pick<Storage, "getItem" | "setItem">;

interface PersistedPreferences {
  readonly version: 1;
  readonly volume: number;
  readonly muted: boolean;
  readonly lastAudibleVolume: number;
}

export interface PlaybackPreferencesState {
  readonly volume: number;
  readonly muted: boolean;
  readonly lastAudibleVolume: number;
  setVolume: (volume: number) => void;
  setMuted: (muted: boolean) => void;
  syncFromMedia: (volume: number, muted: boolean) => void;
}

export type PlaybackPreferencesStore = StoreApi<PlaybackPreferencesState>;

function validVolume(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value) && value >= 0 && value <= 1;
}

function browserStorage(): PreferenceStorage | null {
  try {
    return typeof window === "undefined" ? null : window.localStorage;
  } catch {
    return null;
  }
}

function loadPreferences(storage: PreferenceStorage | null): PersistedPreferences {
  if (!storage) {
    return { version: 1, volume: DEFAULT_VOLUME, muted: false, lastAudibleVolume: DEFAULT_VOLUME };
  }
  try {
    const parsed = JSON.parse(storage.getItem(STORAGE_KEY) ?? "null") as Partial<PersistedPreferences> | null;
    if (
      parsed?.version === 1
      && validVolume(parsed.volume)
      && typeof parsed.muted === "boolean"
      && validVolume(parsed.lastAudibleVolume)
      && parsed.lastAudibleVolume > 0
    ) {
      return {
        version: 1,
        volume: parsed.volume,
        muted: parsed.muted,
        lastAudibleVolume: parsed.lastAudibleVolume,
      };
    }
  } catch {
    // Browser storage is an optional preference cache; malformed data is ignored.
  }
  return { version: 1, volume: DEFAULT_VOLUME, muted: false, lastAudibleVolume: DEFAULT_VOLUME };
}

function savePreferences(
  storage: PreferenceStorage | null,
  value: Pick<PlaybackPreferencesState, "volume" | "muted" | "lastAudibleVolume">,
) {
  if (!storage) return;
  try {
    storage.setItem(STORAGE_KEY, JSON.stringify({ version: 1, ...value }));
  } catch {
    // Playback remains functional when storage is blocked or full.
  }
}

export function createPlaybackPreferencesStore(
  storage: PreferenceStorage | null = browserStorage(),
): PlaybackPreferencesStore {
  const initial = loadPreferences(storage);
  return createStore<PlaybackPreferencesState>((set) => {
    const persist = (
      next: Pick<PlaybackPreferencesState, "volume" | "muted" | "lastAudibleVolume">,
    ) => {
      savePreferences(storage, next);
      return next;
    };
    return {
      volume: initial.volume,
      muted: initial.muted,
      lastAudibleVolume: initial.lastAudibleVolume,
      setVolume: (value) => {
        if (!validVolume(value)) return;
        set((state) => persist({
          volume: value,
          muted: state.muted,
          lastAudibleVolume: value > 0 ? value : state.lastAudibleVolume,
        }));
      },
      setMuted: (muted) => set((state) => {
        const volume = !muted && state.volume === 0 ? state.lastAudibleVolume : state.volume;
        return persist({ volume, muted, lastAudibleVolume: state.lastAudibleVolume });
      }),
      syncFromMedia: (value, muted) => {
        if (!validVolume(value)) return;
        set((state) => {
          const restoring = state.muted && !muted && value === 0;
          const volume = restoring ? state.lastAudibleVolume : value;
          return persist({
            volume,
            muted,
            lastAudibleVolume: volume > 0 ? volume : state.lastAudibleVolume,
          });
        });
      },
    };
  });
}

const PlaybackPreferencesContext = createContext<PlaybackPreferencesStore | null>(null);

export function PlaybackPreferencesProvider({
  children,
  store: providedStore,
}: {
  readonly children: ReactNode;
  readonly store?: PlaybackPreferencesStore;
}) {
  const [store] = useState(() => providedStore ?? createPlaybackPreferencesStore());
  return (
    <PlaybackPreferencesContext.Provider value={store}>
      {children}
    </PlaybackPreferencesContext.Provider>
  );
}

export function usePlaybackPreferences<T>(
  selector: (state: PlaybackPreferencesState) => T,
): T {
  const store = useContext(PlaybackPreferencesContext);
  if (!store) throw new Error("PlaybackPreferencesProvider is missing");
  return useStore(store, selector);
}
