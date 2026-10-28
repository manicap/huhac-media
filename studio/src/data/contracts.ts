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
  readonly mediaCount: number;
  readonly accent: string;
}

export interface MediaSummary {
  readonly id: MediaId;
  readonly workspaceId: WorkspaceId;
  readonly projectIds: readonly ProjectId[];
  readonly title: string;
  readonly kind: "image" | "video" | "audio" | "graphic";
  readonly capturedAt: string | null;
  readonly accent: string;
}

export interface StudioDataSource {
  listWorkspaces(): Promise<readonly WorkspaceSummary[]>;
  listProjects(workspaceId: WorkspaceId): Promise<readonly ProjectSummary[]>;
  listMedia(
    workspaceId: WorkspaceId,
    projectId: ProjectId,
  ): Promise<readonly MediaSummary[]>;
}
