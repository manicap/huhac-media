import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef } from "react";

import { useStudioStore } from "../context/studioStore";
import { useStudioData } from "../data/StudioDataProvider";

export function WorkspacePicker() {
  const dataSource = useStudioData();
  const workspaceId = useStudioStore((state) => state.workspaceId);
  const projectId = useStudioStore((state) => state.projectId);
  const setWorkspace = useStudioStore((state) => state.setWorkspace);
  const setProject = useStudioStore((state) => state.setProject);
  const queryClient = useQueryClient();
  const previousRuntimeId = useRef<string | null>(null);
  const sessionQuery = useQuery({
    queryKey: ["studio", "session"],
    queryFn: () => dataSource.getSession(),
    staleTime: 0,
    refetchOnMount: "always",
    refetchOnWindowFocus: "always",
  });
  const session = sessionQuery.data;
  const workspaces = session?.workspaces ?? [];
  const projectsQuery = useQuery({
    queryKey: ["studio", "projects", workspaceId],
    queryFn: () => dataSource.listProjects(workspaceId!),
    enabled: workspaceId !== null,
  });
  const projects = projectsQuery.data ?? [];
  const activeProject = projects.find((project) => project.id === projectId);

  useEffect(() => {
    if (!session) return;
    const runtimeChanged = previousRuntimeId.current !== null
      && previousRuntimeId.current !== session.runtimeId;
    previousRuntimeId.current = session.runtimeId;
    if (workspaceId !== session.activeWorkspaceId) {
      setWorkspace(session.activeWorkspaceId);
    }
    if (runtimeChanged) {
      queryClient.removeQueries({
        predicate: (query) => query.queryKey[0] === "studio" && query.queryKey[1] !== "session",
      });
    }
  }, [queryClient, session, setWorkspace, workspaceId]);

  useEffect(() => {
    if (!sessionQuery.isError) return;
    setWorkspace(null);
    queryClient.removeQueries({
      predicate: (query) => query.queryKey[0] === "studio" && query.queryKey[1] !== "session",
    });
  }, [queryClient, sessionQuery.isError, setWorkspace]);

  useEffect(() => {
    if (
      projectId
      && !projectsQuery.isPending
      && !projectsQuery.isFetching
      && (!activeProject || activeProject.status !== "active")
    ) {
      setProject(null);
    }
  }, [activeProject, projectId, projectsQuery.isFetching, projectsQuery.isPending, setProject]);

  return (
    <div className="context-strip" aria-label="Pracovní kontext">
      <div
        className={`workspace-picker workspace-picker--${session?.mode ?? "loading"}`}
        aria-live="polite"
      >
        <span>Pracovní prostředí</span>
        <strong>
          {sessionQuery.isPending
            ? "Ověřuji backend…"
            : sessionQuery.isError
              ? "Backend není dostupný"
              : session?.mode === "online"
                ? `Online · ${session.activeWorkspaceId}`
                : "Offline · bez aktivní knihovny"}
        </strong>
        {session?.mode === "offline" && workspaces.length ? (
          <small>
            {workspaces.length === 1
              ? "1 uložený workspace je dostupný pouze jako offline evidence."
              : `${workspaces.length} uložené workspace jsou dostupné pouze jako offline evidence.`}
          </small>
        ) : null}
      </div>
      <div className="active-project" aria-live="polite">
        <span>Aktivní projekt</span>
        <strong>{activeProject?.title ?? "Žádný projekt"}</strong>
      </div>
    </div>
  );
}
