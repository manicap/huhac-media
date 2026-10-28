export type WorkspaceId = string;
export type ProjectId = string;
export type MediaId = string;

export interface WorkspaceSummary {
  readonly id: WorkspaceId;
  readonly title: string;
  readonly status: "ready" | "offline";
}

export interface ProjectSummary {
  readonly id: ProjectId;
  readonly workspaceId: WorkspaceId;
  readonly title: string;
  readonly description: string;
  readonly notes: string;
  readonly tags: readonly string[];
  readonly mediaCount: number;
  readonly status: "active" | "archived";
  readonly revision: number;
  readonly createdAt: string;
  readonly updatedAt: string;
  readonly archivedAt: string | null;
}

export interface ProjectInput {
  readonly title: string;
  readonly description?: string | null;
  readonly notes?: string | null;
  readonly tags?: readonly string[];
}

export interface MediaSummary {
  readonly id: MediaId;
  readonly workspaceId: WorkspaceId;
  readonly title: string;
  readonly kind: "image" | "video";
  readonly capturedAt: string | null;
  readonly previewUrl: string | null;
  readonly availability: "available" | "unavailable";
  readonly resolution?: "resolved" | "unresolved" | "original_offline" | "catalog_unavailable";
}

export interface StudioDataSource {
  listWorkspaces(): Promise<readonly WorkspaceSummary[]>;
  listProjects(workspaceId: WorkspaceId): Promise<readonly ProjectSummary[]>;
  getProject(projectId: ProjectId): Promise<ProjectSummary>;
  createProject(workspaceId: WorkspaceId, input: ProjectInput): Promise<ProjectSummary>;
  updateProject(
    projectId: ProjectId,
    revision: number,
    input: ProjectInput,
  ): Promise<ProjectSummary>;
  archiveProject(projectId: ProjectId, revision: number): Promise<ProjectSummary>;
  restoreProject(projectId: ProjectId, revision: number): Promise<ProjectSummary>;
  listWorkspaceMedia(workspaceId: WorkspaceId): Promise<readonly MediaSummary[]>;
  listProjectMedia(
    workspaceId: WorkspaceId,
    projectId: ProjectId,
  ): Promise<readonly MediaSummary[]>;
  addMediaLinks(
    projectId: ProjectId,
    revision: number,
    assetIds: readonly MediaId[],
  ): Promise<ProjectSummary>;
  removeMediaLinks(
    projectId: ProjectId,
    revision: number,
    assetIds: readonly MediaId[],
  ): Promise<ProjectSummary>;
}
