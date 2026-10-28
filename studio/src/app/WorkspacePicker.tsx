import { useQuery } from "@tanstack/react-query";

import { useStudioStore } from "../context/studioStore";
import { useStudioData } from "../data/StudioDataProvider";

export function WorkspacePicker() {
  const dataSource = useStudioData();
  const workspaceId = useStudioStore((state) => state.workspaceId);
  const projectId = useStudioStore((state) => state.projectId);
  const setWorkspace = useStudioStore((state) => state.setWorkspace);
  const { data: workspaces = [] } = useQuery({
    queryKey: ["studio", "workspaces"],
    queryFn: () => dataSource.listWorkspaces(),
  });
  const { data: projects = [] } = useQuery({
    queryKey: ["studio", "projects", workspaceId],
    queryFn: () => dataSource.listProjects(workspaceId!),
    enabled: workspaceId !== null,
  });
  const activeProject = projects.find((project) => project.id === projectId);

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
