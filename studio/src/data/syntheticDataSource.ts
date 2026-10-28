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
    accent: "#6d5dfc",
  },
  {
    id: "project-campaign",
    workspaceId: "workspace-main",
    title: "Kampaň k singlu",
    description: "Sdílené logo, cover art a vertikální video pro vydání singlu.",
    mediaCount: 3,
    accent: "#e0673b",
  },
  {
    id: "project-empty",
    workspaceId: "workspace-main",
    title: "Nový projekt",
    description: "Prázdný projekt ověřující bezpečný stav knihovny.",
    mediaCount: 0,
    accent: "#2b9b79",
  },
  {
    id: "project-archive",
    workspaceId: "workspace-archive",
    title: "Vizuální archiv",
    description: "Oddělený syntetický kontext druhého workspace.",
    mediaCount: 1,
    accent: "#3e7ba8",
  },
];

export const syntheticMedia: readonly MediaSummary[] = [
  {
    id: "media-stage-wide",
    workspaceId: "workspace-main",
    projectIds: ["project-tour"],
    title: "Pódium – široký záběr",
    kind: "image",
    capturedAt: "2026-09-18T20:14:00Z",
    accent: "linear-gradient(135deg, #392f66, #b86c9d)",
  },
  {
    id: "media-backstage",
    workspaceId: "workspace-main",
    projectIds: ["project-tour"],
    title: "Backstage moment",
    kind: "video",
    capturedAt: "2026-09-18T21:42:00Z",
    accent: "linear-gradient(135deg, #1d5e68, #67b4a5)",
  },
  {
    id: "media-crowd",
    workspaceId: "workspace-main",
    projectIds: ["project-tour"],
    title: "Publikum pod světly",
    kind: "image",
    capturedAt: "2026-09-18T22:05:00Z",
    accent: "linear-gradient(135deg, #7c3f25, #e6a643)",
  },
  {
    id: "media-logo",
    workspaceId: "workspace-main",
    projectIds: ["project-tour", "project-campaign"],
    title: "HUHÁČ logo – světlé",
    kind: "graphic",
    capturedAt: null,
    accent: "linear-gradient(135deg, #282c38, #6b7180)",
  },
  {
    id: "media-cover",
    workspaceId: "workspace-main",
    projectIds: ["project-campaign"],
    title: "Cover singlu – finále",
    kind: "graphic",
    capturedAt: "2026-10-03T11:20:00Z",
    accent: "linear-gradient(135deg, #64233f, #f07167)",
  },
  {
    id: "media-reel",
    workspaceId: "workspace-main",
    projectIds: ["project-campaign"],
    title: "Vertikální teaser",
    kind: "video",
    capturedAt: "2026-10-04T16:08:00Z",
    accent: "linear-gradient(135deg, #224c71, #59a5d8)",
  },
  {
    id: "media-archive-poster",
    workspaceId: "workspace-archive",
    projectIds: ["project-archive"],
    title: "Plakát – koncept 01",
    kind: "graphic",
    capturedAt: null,
    accent: "linear-gradient(135deg, #304a3c, #8fba74)",
  },
];

export const syntheticDataSource: StudioDataSource = {
  async listWorkspaces() {
    return syntheticWorkspaces;
  },
  async listProjects(workspaceId) {
    return syntheticProjects.filter((project) => project.workspaceId === workspaceId);
  },
  async listMedia(workspaceId, projectId) {
    return syntheticMedia.filter(
      (media) =>
        media.workspaceId === workspaceId && media.projectIds.includes(projectId),
    );
  },
};
