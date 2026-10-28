import { useQuery } from "@tanstack/react-query";
import { useEffect } from "react";

import { useStudioStore } from "../context/studioStore";
import { useStudioData } from "../data/StudioDataProvider";

export function WorkspacePicker() {
  const dataSource = useStudioData();
  const workspaceId = useStudioStore((state) => state.workspaceId);
  const projectId = useStudioStore((state) => state.projectId);
  const setWorkspace = useStudioStore((state) => state.setWorkspace);
  const setProject = useStudioStore((state) => state.setProject);
  const { data: workspaces = [] } = useQuery({
    queryKey: ["studio", "workspaces"],
    queryFn: () => dataSource.listWorkspaces(),
  });
  const projectsQuery = useQuery({
    queryKey: ["studio", "projects", workspaceId],
    queryFn: () => dataSource.listProjects(workspaceId!),
    enabled: workspaceId !== null,
  });
  const projects = projectsQuery.data ?? [];
  const activeProject = projects.find((project) => project.id === projectId);

  useEffect(() => {
    if (!workspaces.length) return;
    if (!workspaceId || !workspaces.some((workspace) => workspace.id === workspaceId)) {
      setWorkspace(
        workspaces.find((workspace) => workspace.status === "ready")?.id ?? workspaces[0].id,
      );
    }
  }, [setWorkspace, workspaceId, workspaces]);

  useEffect(() => {
    if (
      projectId &&
      !projectsQuery.isPending &&
      !projectsQuery.isFetching &&
      (!activeProject || activeProject.status !== "active")
    ) {
      setProject(null);
    }
  }, [activeProject, projectId, projectsQuery.isFetching, projectsQuery.isPending, setProject]);

  return (
    <div className="context-strip" aria-label="Pracovní kontext">
      <label className="workspace-picker">
        <span>Workspace</span>
        <select
          aria-label="Aktivní workspace"
          value={workspaceId ?? ""}
          onChange={(event) => setWorkspace(event.target.value || null)}
        >
          <option value="">Bez workspace</option>
          {workspaces.map((workspace) => (
            <option key={workspace.id} value={workspace.id}>
              {workspace.title}
            </option>
          ))}
        </select>
      </label>
      <div className="active-project" aria-live="polite">
        <span>Aktivní projekt</span>
        <strong>{activeProject?.title ?? "Žádný projekt"}</strong>
      </div>
    </div>
  );
}
