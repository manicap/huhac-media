import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { useStudioStore } from "../../context/studioStore";
import { errorMessage, StudioApiError } from "../../data/apiDataSource";
import { useStudioData } from "../../data/StudioDataProvider";
import type { ProjectSummary } from "../../data/contracts";
import { MediaCard } from "./MediaCard";

export function MediaLibraryModule() {
  const [density, setDensity] = useState<"comfortable" | "compact">("comfortable");
  const [view, setView] = useState<"all" | "project">("project");
  const [notice, setNotice] = useState<string | null>(null);
  const [conflict, setConflict] = useState(false);
  const [activeVideoId, setActiveVideoId] = useState<string | null>(null);
  const workspaceId = useStudioStore((state) => state.workspaceId);
  const projectId = useStudioStore((state) => state.projectId);
  const selectedMediaIds = useStudioStore((state) => state.selectedMediaIds);
  const toggleMedia = useStudioStore((state) => state.toggleMedia);
  const clearSelection = useStudioStore((state) => state.clearSelection);
  const activeModuleId = useStudioStore((state) => state.activeModuleId);
  const dataSource = useStudioData();
  const queryClient = useQueryClient();
  const projectQuery = useQuery({
    queryKey: ["studio", "project", projectId],
    queryFn: () => dataSource.getProject(projectId!),
    enabled: projectId !== null,
  });
  const mediaQuery = useQuery({
    queryKey: ["studio", view === "all" ? "workspace-media" : "project-media", workspaceId, projectId],
    queryFn: () => view === "all"
      ? dataSource.listWorkspaceMedia(workspaceId!)
      : dataSource.listProjectMedia(workspaceId!, projectId!),
    enabled: workspaceId !== null && (view === "all" || projectId !== null),
  });
  const linkedMediaQuery = useQuery({
    queryKey: ["studio", "project-media", workspaceId, projectId],
    queryFn: () => dataSource.listProjectMedia(workspaceId!, projectId!),
    enabled: view === "all" && workspaceId !== null && projectId !== null,
  });
  const linkedIds = new Set((linkedMediaQuery.data ?? []).map((media) => media.id));

  useEffect(() => setActiveVideoId(null), [projectId, workspaceId]);
  useEffect(() => {
    if (activeModuleId !== "media-library") setActiveVideoId(null);
  }, [activeModuleId]);
  useEffect(() => {
    if (
      activeVideoId !== null
      && mediaQuery.data
      && !mediaQuery.data.some((media) => media.id === activeVideoId)
    ) {
      setActiveVideoId(null);
    }
  }, [activeVideoId, mediaQuery.data]);

  const refreshAfterLinks = (project: ProjectSummary, message: string) => {
    queryClient.setQueryData(["studio", "project", project.id], project);
    void queryClient.invalidateQueries({ queryKey: ["studio", "projects", workspaceId] });
    void queryClient.invalidateQueries({ queryKey: ["studio", "project-media", workspaceId, project.id] });
    clearSelection();
    setNotice(message);
    setConflict(false);
  };
  const handleError = (error: unknown) => {
    setNotice(errorMessage(error));
    setConflict(error instanceof StudioApiError && error.code === "revision_conflict");
  };
  const addMutation = useMutation({
    mutationFn: () => dataSource.addMediaLinks(projectId!, projectQuery.data!.revision, selectedMediaIds),
    onSuccess: (project) => refreshAfterLinks(project, "Vybraná média byla přidána do projektu."),
    onError: handleError,
  });
  const removeMutation = useMutation({
    mutationFn: () => dataSource.removeMediaLinks(projectId!, projectQuery.data!.revision, selectedMediaIds),
    onSuccess: (project) => refreshAfterLinks(project, "Vazby byly odebrány. Původní soubory zůstaly beze změny."),
    onError: handleError,
  });

  const switchView = (next: "all" | "project") => {
    setActiveVideoId(null);
    clearSelection();
    setView(next);
    setNotice(null);
  };

  const selectionActionDisabled = !projectId
    || !projectQuery.data
    || addMutation.isPending
    || removeMutation.isPending;

  return (
    <div className={`module-page media-library-module${selectedMediaIds.length ? " media-library-module--selection" : ""}${activeVideoId ? " media-library-module--playing" : ""}`}>
      <header className="module-heading">
        <div>
          <p className="eyebrow">Veřejný workspace katalog</p>
          <h1>Mediální knihovna</h1>
          <p className="module-lead">Média zůstávají ve workspace; Studio ukládá pouze projektové vazby.</p>
        </div>
        <div className="density-control" role="group" aria-label="Hustota knihovny">
          <button type="button" aria-pressed={density === "comfortable"} onClick={() => setDensity("comfortable")}>Pohodlná</button>
          <button type="button" aria-pressed={density === "compact"} onClick={() => setDensity("compact")}>Kompaktní</button>
        </div>
      </header>

      {!workspaceId ? (
        <section className="module-state" role="status"><h2>Není připojený workspace</h2><p>Spusťte Studio s veřejným workspace katalogem.</p></section>
      ) : (
        <>
          <div className="library-toolbar">
            <div className="segmented-control" role="group" aria-label="Pohled knihovny">
              <button type="button" aria-pressed={view === "all"} onClick={() => switchView("all")}>Všechna média</button>
              <button type="button" aria-pressed={view === "project"} disabled={!projectId} onClick={() => switchView("project")}>Média projektu</button>
            </div>
          </div>

          {notice ? (
            <div className={conflict ? "feedback feedback--error" : "feedback"} role={conflict ? "alert" : "status"}>
              <span>{notice}</span>
              {conflict ? <button type="button" onClick={() => { setConflict(false); void projectQuery.refetch(); }}>Načíst aktuální verzi</button> : null}
            </div>
          ) : null}

          {view === "project" && !projectId ? (
            <section className="module-state" role="status"><h2>Nejprve vyberte aktivní projekt</h2><p>Archivované projekty jsou pouze pro čtení a nelze je použít jako pracovní kontext.</p></section>
          ) : mediaQuery.isPending ? (
            <section className="module-state" role="status">Načítám média…</section>
          ) : mediaQuery.isError ? (
            <section className="module-state module-state--error" role="alert"><h2>Knihovnu se nepodařilo načíst</h2><p>{errorMessage(mediaQuery.error)}</p></section>
          ) : mediaQuery.data?.length === 0 ? (
            <section className="module-state" role="status"><h2>{view === "all" ? "Workspace neobsahuje žádná média" : "Tento projekt zatím nemá žádná média"}</h2><p>{view === "all" ? "Katalog je prázdný." : "Přepněte na Všechna média a přidejte výběr do projektu."}</p></section>
          ) : (
            <div className={`media-grid media-grid--${density}`} aria-label={view === "all" ? "Všechna média" : "Média aktivního projektu"}>
              {mediaQuery.data?.map((media) => {
                const selected = selectedMediaIds.includes(media.id);
                const alreadyLinked = view === "all" && linkedIds.has(media.id);
                return (
                  <MediaCard
                    key={media.id}
                    media={media}
                    selected={selected}
                    selectionDisabled={alreadyLinked}
                    selectionHint={alreadyLinked ? "Už je v projektu" : undefined}
                    playerActive={activeVideoId === media.id}
                    onToggleSelection={() => toggleMedia(media.id)}
                    onActivatePlayer={() => setActiveVideoId(media.id)}
                    onClosePlayer={() => setActiveVideoId(null)}
                  />
                );
              })}
            </div>
          )}

          {selectedMediaIds.length ? (
            <section className="selection-action-bar" aria-label="Hromadné operace" role="region">
              <div className="selection-action-bar__summary" aria-live="polite">
                <strong>{selectedMediaIds.length} vybráno</strong>
                {!projectId ? <span>Pro projektovou akci nejprve vyberte aktivní projekt.</span> : null}
              </div>
              <div className="selection-action-bar__actions">
                {view === "all" ? (
                  <button
                    className="button button--primary"
                    type="button"
                    disabled={selectionActionDisabled}
                    onClick={() => addMutation.mutate()}
                  >
                    Přidat do projektu
                  </button>
                ) : (
                  <button
                    className="button button--danger"
                    type="button"
                    disabled={selectionActionDisabled}
                    onClick={() => removeMutation.mutate()}
                  >
                    Odebrat z projektu
                  </button>
                )}
                <button className="button button--secondary" type="button" onClick={clearSelection}>
                  Zrušit výběr
                </button>
              </div>
            </section>
          ) : null}
        </>
      )}
    </div>
  );
}
