import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";

import {
  createStudioStore,
  StudioStoreProvider,
  type StudioStore,
} from "../context/studioStore";
import { StudioDataProvider } from "../data/StudioDataProvider";
import type { StudioDataSource } from "../data/contracts";
import { apiDataSource } from "../data/apiDataSource";
import {
  PlaybackPreferencesProvider,
  type PlaybackPreferencesStore,
} from "../playback/playbackPreferences";
import type { StudioModuleDefinition } from "./moduleContract";
import { studioModuleRegistry } from "./moduleRegistry";
import { StudioShell } from "./StudioShell";

const defaultCapabilities = new Set(["projects", "media-library"]);

export function StudioApp({
  store: providedStore,
  dataSource = apiDataSource,
  modules = studioModuleRegistry,
  capabilities = defaultCapabilities,
  playbackStore,
}: {
  readonly store?: StudioStore;
  readonly dataSource?: StudioDataSource;
  readonly modules?: readonly StudioModuleDefinition[];
  readonly capabilities?: ReadonlySet<string>;
  readonly playbackStore?: PlaybackPreferencesStore;
}) {
  const [store] = useState(() => providedStore ?? createStudioStore());
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: { retry: false, staleTime: Number.POSITIVE_INFINITY },
        },
      }),
  );

  return (
    <QueryClientProvider client={queryClient}>
      <StudioDataProvider dataSource={dataSource}>
        <PlaybackPreferencesProvider store={playbackStore}>
          <StudioStoreProvider store={store}>
            <StudioShell modules={modules} capabilities={capabilities} />
          </StudioStoreProvider>
        </PlaybackPreferencesProvider>
      </StudioDataProvider>
    </QueryClientProvider>
  );
}
