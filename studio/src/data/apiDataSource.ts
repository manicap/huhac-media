import type {
  MediaSummary,
  ProjectId,
  ProjectInput,
  ProjectSummary,
  StudioDataSource,
  WorkspaceId,
  WorkspaceSummary,
} from "./contracts";

type ApiProject = {
  project_id: string;
  workspace_id: string;
  title: string;
  description: string | null;
  notes: string | null;
  tags: string[];
  media_count: number;
  status: "active" | "archived";
  revision: number;
  created_at: string;
  updated_at: string;
  archived_at: string | null;
};

type ApiMedia = {
  asset_id: string;
  media_type: "image" | "video";
  availability: "available" | "unavailable";
  display_name: string;
  capture_time: string | null;
  preview_url: string | null;
};

type ApiErrorBody = {
  error?: { code?: string; message?: string; current_revision?: number };
  detail?: string | { code?: string };
};

const messages: Record<string, string> = {
  revision_conflict: "Projekt mezitím změnil jiný požadavek. Načtěte aktuální data a zkuste změnu znovu.",
  project_archived: "Archivovaný projekt je pouze pro čtení. Nejdříve jej obnovte.",
  conflict: "Operaci nelze dokončit v aktuálním stavu projektu. Načtěte data znovu.",
  invalid_csrf: "Relace pro zápis vypršela. Obnovte stránku a zkuste akci znovu.",
  not_found: "Požadovaná položka už není dostupná.",
  validation_error: "Zadané údaje nejsou platné. Zkontrolujte formulář.",
};

export class StudioApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code: string,
    readonly currentRevision?: number,
  ) {
    super(message);
  }
}

export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Operace se nepodařila. Zkuste to znovu.";
}

function projectFromApi(project: ApiProject): ProjectSummary {
  return {
    id: project.project_id,
    workspaceId: project.workspace_id,
    title: project.title,
    description: project.description ?? "",
    notes: project.notes ?? "",
    tags: project.tags,
    mediaCount: project.media_count,
    status: project.status,
    revision: project.revision,
    createdAt: project.created_at,
    updatedAt: project.updated_at,
    archivedAt: project.archived_at,
  };
}

function mediaFromApi(workspaceId: string, media: ApiMedia): MediaSummary {
  return {
    id: media.asset_id,
    workspaceId,
    title: media.display_name,
    kind: media.media_type,
    capturedAt: media.capture_time,
    previewUrl: media.preview_url,
    availability: media.availability,
  };
}

class ProjectApiDataSource implements StudioDataSource {
  private sessionPromise: Promise<{
    csrf_token: string;
    workspaces: { workspace_id: string; status: "ready" | "offline" }[];
  }> | null = null;

  private async request<T>(path: string, init?: RequestInit): Promise<T> {
    const response = await fetch(path, { credentials: "same-origin", ...init });
    if (!response.ok) {
      let body: ApiErrorBody = {};
      try {
        body = (await response.json()) as ApiErrorBody;
      } catch {
        // The localized fallback below is intentionally independent of server text.
      }
      const code = body.error?.code ??
        (typeof body.detail === "object" ? body.detail.code : undefined) ??
        `http_${response.status}`;
      throw new StudioApiError(
        messages[code] ?? body.error?.message ?? `Server vrátil chybu ${response.status}.`,
        response.status,
        code,
        body.error?.current_revision,
      );
    }
    return (await response.json()) as T;
  }

  private session() {
    this.sessionPromise ??= this.request("/api/studio/session");
    return this.sessionPromise;
  }

  private async write<T>(path: string, method: string, revision?: number, body?: unknown) {
    const session = await this.session();
    const headers: Record<string, string> = { "X-CSRF-Token": session.csrf_token };
    if (body !== undefined) headers["Content-Type"] = "application/json";
    if (revision !== undefined) headers["If-Match"] = String(revision);
    return this.request<T>(path, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  }

  async listWorkspaces(): Promise<readonly WorkspaceSummary[]> {
    const session = await this.session();
    return session.workspaces.map((workspace) => ({
      id: workspace.workspace_id,
      title: workspace.workspace_id,
      status: workspace.status,
    }));
  }

  async listProjects(workspaceId: WorkspaceId) {
    const response = await this.request<{ items: ApiProject[] }>(
      `/api/studio/workspaces/${encodeURIComponent(workspaceId)}/projects?status=all`,
    );
    return response.items.map(projectFromApi);
  }

  async getProject(projectId: ProjectId) {
    return projectFromApi(
      await this.request<ApiProject>(`/api/studio/projects/${encodeURIComponent(projectId)}`),
    );
  }

  async createProject(workspaceId: WorkspaceId, input: ProjectInput) {
    return projectFromApi(
      await this.write<ApiProject>(
        `/api/studio/workspaces/${encodeURIComponent(workspaceId)}/projects`,
        "POST",
        undefined,
        input,
      ),
    );
  }

  async updateProject(projectId: ProjectId, revision: number, input: ProjectInput) {
    return projectFromApi(
      await this.write<ApiProject>(
        `/api/studio/projects/${encodeURIComponent(projectId)}`,
        "PATCH",
        revision,
        input,
      ),
    );
  }

  async archiveProject(projectId: ProjectId, revision: number) {
    return projectFromApi(
      await this.write<ApiProject>(
        `/api/studio/projects/${encodeURIComponent(projectId)}/archive`,
        "POST",
        revision,
      ),
    );
  }

  async restoreProject(projectId: ProjectId, revision: number) {
    return projectFromApi(
      await this.write<ApiProject>(
        `/api/studio/projects/${encodeURIComponent(projectId)}/restore`,
        "POST",
        revision,
      ),
    );
  }

  async listWorkspaceMedia(workspaceId: WorkspaceId) {
    const result: MediaSummary[] = [];
    let page = 1;
    let total = 0;
    do {
      const response = await this.request<{ items: ApiMedia[]; total: number }>(
        `/api/studio/workspaces/${encodeURIComponent(workspaceId)}/media?page=${page}&page_size=100`,
      );
      total = response.total;
      result.push(...response.items.map((item) => mediaFromApi(workspaceId, item)));
      page += 1;
    } while (result.length < total);
    return result;
  }

  async listProjectMedia(workspaceId: WorkspaceId, projectId: ProjectId) {
    const [catalog, links] = await Promise.all([
      this.listWorkspaceMedia(workspaceId),
      this.request<{
        items: { asset_id: string; media_type: "image" | "video" | null; resolution: MediaSummary["resolution"] }[];
      }>(`/api/studio/projects/${encodeURIComponent(projectId)}/media`),
    ]);
    const byId = new Map(catalog.map((item) => [item.id, item]));
    return links.items.map((link) => ({
      ...(byId.get(link.asset_id) ?? {
        id: link.asset_id,
        workspaceId,
        title: link.asset_id,
        kind: link.media_type ?? "image",
        capturedAt: null,
        previewUrl: null,
        availability: "unavailable" as const,
      }),
      resolution: link.resolution,
    }));
  }

  async addMediaLinks(projectId: ProjectId, revision: number, assetIds: readonly string[]) {
    return projectFromApi(
      await this.write<ApiProject>(
        `/api/studio/projects/${encodeURIComponent(projectId)}/media-links`,
        "POST",
        revision,
        { links: assetIds.map((asset_id) => ({ asset_id, role: "reference" })) },
      ),
    );
  }

  async removeMediaLinks(projectId: ProjectId, revision: number, assetIds: readonly string[]) {
    let currentRevision = revision;
    let project: ApiProject | null = null;
    for (const assetId of assetIds) {
      project = await this.write<ApiProject>(
        `/api/studio/projects/${encodeURIComponent(projectId)}/media-links/${encodeURIComponent(assetId)}`,
        "DELETE",
        currentRevision,
      );
      currentRevision = project.revision;
    }
    if (!project) return this.getProject(projectId);
    return projectFromApi(project);
  }
}

export const apiDataSource: StudioDataSource = new ProjectApiDataSource();
