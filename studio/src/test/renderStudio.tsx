import { render } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";

import { StudioApp } from "../app/StudioApp";
import type { StudioModuleDefinition } from "../app/moduleContract";
import { createStudioStore, type StudioStore } from "../context/studioStore";
import type { StudioDataSource } from "../data/contracts";
import { syntheticDataSource } from "../data/syntheticDataSource";
import type { PlaybackPreferencesStore } from "../playback/playbackPreferences";

export function renderStudio({
  route = "/modules/projects",
  store = createStudioStore(),
  dataSource,
  modules,
  capabilities,
  playbackStore,
}: {
  route?: string;
  store?: StudioStore;
  dataSource?: StudioDataSource;
  modules?: readonly StudioModuleDefinition[];
  capabilities?: ReadonlySet<string>;
  playbackStore?: PlaybackPreferencesStore;
} = {}) {
  return {
    store,
    user: userEvent.setup(),
    ...render(
      <MemoryRouter initialEntries={[route]}>
        <StudioApp
          store={store}
          dataSource={dataSource ?? syntheticDataSource}
          modules={modules}
          capabilities={capabilities}
          playbackStore={playbackStore}
        />
      </MemoryRouter>,
    ),
  };
}
