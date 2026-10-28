import {
  createContext,
  type ReactNode,
  useContext,
} from "react";
import { useStore } from "zustand";
import { createStore, type StoreApi } from "zustand/vanilla";

import type { MediaId, ProjectId, WorkspaceId } from "../data/contracts";

export interface StudioState {
  workspaceId: WorkspaceId | null;
  projectId: ProjectId | null;
  selectedMediaIds: readonly MediaId[];
  activeModuleId: string;
  setWorkspace: (workspaceId: WorkspaceId | null) => void;
  setProject: (projectId: ProjectId | null) => void;
  setActiveModule: (moduleId: string) => void;
  toggleMedia: (mediaId: MediaId) => void;
  clearSelection: () => void;
}

export type StudioStore = StoreApi<StudioState>;

export function createStudioStore(
  initial: Partial<Pick<StudioState, "workspaceId" | "projectId" | "activeModuleId">> = {},
): StudioStore {
  return createStore<StudioState>((set) => ({
    workspaceId: initial.workspaceId ?? null,
    projectId: initial.projectId ?? null,
    selectedMediaIds: [],
    activeModuleId: initial.activeModuleId ?? "projects",
    setWorkspace: (workspaceId) =>
      set((state) =>
        state.workspaceId === workspaceId
          ? state
          : { workspaceId, projectId: null, selectedMediaIds: [] },
      ),
    setProject: (projectId) =>
      set((state) =>
        state.projectId === projectId
          ? state
          : { projectId, selectedMediaIds: [] },
      ),
    setActiveModule: (activeModuleId) => set({ activeModuleId }),
    toggleMedia: (mediaId) =>
      set((state) => ({
        selectedMediaIds: state.selectedMediaIds.includes(mediaId)
          ? state.selectedMediaIds.filter((id) => id !== mediaId)
          : [...state.selectedMediaIds, mediaId],
      })),
    clearSelection: () => set({ selectedMediaIds: [] }),
  }));
}

const StudioStoreContext = createContext<StudioStore | null>(null);

export function StudioStoreProvider({
  children,
  store,
}: {
  children: ReactNode;
  store: StudioStore;
}) {
  return (
    <StudioStoreContext.Provider value={store}>
      {children}
    </StudioStoreContext.Provider>
  );
}

export function useStudioStore<T>(selector: (state: StudioState) => T): T {
  const store = useContext(StudioStoreContext);
  if (!store) {
    throw new Error("StudioStoreProvider is missing");
  }
  return useStore(store, selector);
}
