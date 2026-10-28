import type {
  MediaSummary,
  ProjectSummary,
  StudioDataSource,
  WorkspaceSummary,
} from "./contracts";

export const syntheticWorkspaces: readonly WorkspaceSummary[] = [
  { id: "workspace-main", title: "HUHÁČ – hlavní", status: "ready" },
  { id: "workspace-archive", title: "Archiv návrhů", status: "ready" },
];

export const syntheticProjects: readonly ProjectSummary[] = [
  {
    id: "project-tour",
    workspaceId: "workspace-main",
    title: "Podzimní turné",
    description: "Koncertní fotografie, krátká videa a propagační podklady.",
    mediaCount: 4,
    notes: "",
    tags: ["turné"],
    status: "active",
    revision: 1,
    createdAt: "2026-09-01T10:00:00Z",
    updatedAt: "2026-09-01T10:00:00Z",
    archivedAt: null,
  },
  {
    id: "project-campaign",
    workspaceId: "workspace-main",
    title: "Kampaň k singlu",
    description: "Sdílené logo, cover art a vertikální video pro vydání singlu.",
    mediaCount: 3,
    notes: "",
    tags: ["kampaň"],
    status: "active",
    revision: 1,
    createdAt: "2026-09-02T10:00:00Z",
    updatedAt: "2026-09-02T10:00:00Z",
    archivedAt: null,
  },
  {
    id: "project-empty",
    workspaceId: "workspace-main",
    title: "Nový projekt",
    description: "Prázdný projekt ověřující bezpečný stav knihovny.",
    mediaCount: 0,
    notes: "",
    tags: [],
    status: "active",
    revision: 1,
    createdAt: "2026-09-03T10:00:00Z",
    updatedAt: "2026-09-03T10:00:00Z",
    archivedAt: null,
  },
  {
    id: "project-archive",
    workspaceId: "workspace-archive",
    title: "Vizuální archiv",
    description: "Oddělený syntetický kontext druhého workspace.",
    mediaCount: 1,
    notes: "",
    tags: [],
    status: "active",
    revision: 1,
    createdAt: "2026-09-04T10:00:00Z",
    updatedAt: "2026-09-04T10:00:00Z",
    archivedAt: null,
  },
];

type SyntheticMedia = MediaSummary & { readonly projectIds: readonly string[] };

const mediaDefaults = {
  originalUrl: null,
  originalAvailable: false,
  originalAccessState: "offline",
  width: null,
  height: null,
  rotation: null,
  durationSeconds: null,
  mimeType: null,
  sizeBytes: null,
} as const;

export const syntheticMedia: readonly SyntheticMedia[] = [
  {
    ...mediaDefaults,
    id: "media-stage-wide",
    workspaceId: "workspace-main",
    projectIds: ["project-tour"],
    title: "Pódium – široký záběr",
    kind: "image",
    capturedAt: "2026-09-18T20:14:00Z",
    previewUrl: null,
    originalAvailable: true,
    originalAccessState: "unchecked",
    width: 1920,
    height: 1080,
    mimeType: "image/jpeg",
    availability: "available",
  },
  {
    ...mediaDefaults,
    id: "media-backstage",
    workspaceId: "workspace-main",
    projectIds: ["project-tour"],
    title: "Backstage moment",
    kind: "video",
    capturedAt: "2026-09-18T21:42:00Z",
    previewUrl: null,
    originalUrl: "/api/studio/originals/video-backstage",
    originalAvailable: true,
    originalAccessState: "unchecked",
    width: 1920,
    height: 1080,
    durationSeconds: 65.4,
    mimeType: "video/mp4",
    availability: "available",
  },
  {
    ...mediaDefaults,
    id: "media-crowd",
    workspaceId: "workspace-main",
    projectIds: ["project-tour"],
    title: "Publikum pod světly",
    kind: "image",
    capturedAt: "2026-09-18T22:05:00Z",
    previewUrl: null,
    originalAvailable: true,
    originalAccessState: "unchecked",
    width: 1080,
    height: 1920,
    mimeType: "image/jpeg",
    availability: "available",
  },
  {
    ...mediaDefaults,
    id: "media-logo",
    workspaceId: "workspace-main",
    projectIds: ["project-tour", "project-campaign"],
    title: "HUHÁČ logo – světlé",
    kind: "image",
    capturedAt: null,
    previewUrl: null,
    originalAvailable: true,
    originalAccessState: "unchecked",
    width: 1000,
    height: 1000,
    mimeType: "image/png",
    availability: "available",
  },
  {
    ...mediaDefaults,
    id: "media-cover",
    workspaceId: "workspace-main",
    projectIds: ["project-campaign"],
    title: "Cover singlu – finále",
    kind: "image",
    capturedAt: "2026-10-03T11:20:00Z",
    previewUrl: null,
    originalAvailable: true,
    originalAccessState: "unchecked",
    width: 3000,
    height: 3000,
    mimeType: "image/jpeg",
    availability: "available",
  },
  {
    ...mediaDefaults,
    id: "media-reel",
    workspaceId: "workspace-main",
    projectIds: ["project-campaign"],
    title: "Vertikální teaser",
    kind: "video",
    capturedAt: "2026-10-04T16:08:00Z",
    previewUrl: null,
    originalUrl: "/api/studio/originals/video-reel",
    originalAvailable: true,
    originalAccessState: "unchecked",
    width: 1080,
    height: 1920,
    durationSeconds: 14.2,
    mimeType: "video/mp4",
    availability: "available",
  },
  {
    ...mediaDefaults,
    id: "media-archive-poster",
    workspaceId: "workspace-archive",
    projectIds: ["project-archive"],
    title: "Plakát – koncept 01",
    kind: "image",
    capturedAt: null,
    previewUrl: null,
    originalAvailable: true,
    originalAccessState: "unchecked",
    width: 1080,
    height: 1920,
    mimeType: "image/jpeg",
    availability: "available",
  },
];

export const syntheticDataSource: StudioDataSource = {
  async getSession() {
    return {
      runtimeId: "runtime-synthetic",
      mode: "online" as const,
      activeWorkspaceId: "workspace-main",
      workspaces: syntheticWorkspaces,
    };
  },
  async listProjects(workspaceId) {
    return syntheticProjects.filter((project) => project.workspaceId === workspaceId);
  },
  async getProject(projectId) {
    const project = syntheticProjects.find((item) => item.id === projectId);
    if (!project) throw new Error("Projekt nebyl nalezen.");
    return project;
  },
  async createProject() {
    throw new Error("Syntetický adapter je pouze pro testy čtení.");
  },
  async updateProject() {
    throw new Error("Syntetický adapter je pouze pro testy čtení.");
  },
  async archiveProject() {
    throw new Error("Syntetický adapter je pouze pro testy čtení.");
  },
  async restoreProject() {
    throw new Error("Syntetický adapter je pouze pro testy čtení.");
  },
  async listWorkspaceMedia(workspaceId) {
    return syntheticMedia.filter((media) => media.workspaceId === workspaceId);
  },
  async listProjectMedia(workspaceId, projectId) {
    return syntheticMedia.filter(
      (media) =>
        media.workspaceId === workspaceId && media.projectIds.includes(projectId),
    );
  },
  async addMediaLinks() {
    throw new Error("Syntetický adapter je pouze pro testy čtení.");
  },
  async removeMediaLinks() {
    throw new Error("Syntetický adapter je pouze pro testy čtení.");
  },
};
