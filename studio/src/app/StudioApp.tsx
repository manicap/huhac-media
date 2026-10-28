import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";

import {
  createStudioStore,
  StudioStoreProvider,
  type StudioStore,
} from "../context/studioStore";
import { StudioDataProvider } from "../data/StudioDataProvider";
import type { StudioDataSource } from "../data/contracts";
import { syntheticDataSource } from "../data/syntheticDataSource";
import type { StudioModuleDefinition } from "./moduleContract";
import { studioModuleRegistry } from "./moduleRegistry";
import { StudioShell } from "./StudioShell";

const defaultCapabilities = new Set(["synthetic-projects", "synthetic-library"]);

export function StudioApp({
  store: providedStore,
  dataSource = syntheticDataSource,
  modules = studioModuleRegistry,
  capabilities = defaultCapabilities,
}: {
  readonly store?: StudioStore;
  readonly dataSource?: StudioDataSource;
  readonly modules?: readonly StudioModuleDefinition[];
  readonly capabilities?: ReadonlySet<string>;
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
        <StudioStoreProvider store={store}>
          <StudioShell modules={modules} capabilities={capabilities} />
        </StudioStoreProvider>
      </StudioDataProvider>
    </QueryClientProvider>
  );
}
