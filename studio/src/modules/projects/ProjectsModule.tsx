import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState, type FormEvent } from "react";

import { useStudioStore } from "../../context/studioStore";
import { errorMessage, StudioApiError } from "../../data/apiDataSource";
import { useStudioData } from "../../data/StudioDataProvider";
import type { ProjectInput, ProjectSummary } from "../../data/contracts";

function parseTags(value: string): string[] {
  return [...new Set(value.split(",").map((tag) => tag.trim()).filter(Boolean))];
}

function ProjectForm({
  initial,
  submitLabel,
  pending,
  onSubmit,
}: {
  initial?: ProjectSummary;
  submitLabel: string;
  pending: boolean;
  onSubmit: (input: ProjectInput) => void;
}) {
  const [title, setTitle] = useState(initial?.title ?? "");
  const [description, setDescription] = useState(initial?.description ?? "");
  const [notes, setNotes] = useState(initial?.notes ?? "");
  const [tags, setTags] = useState(initial?.tags.join(", ") ?? "");

  function submit(event: FormEvent) {
    event.preventDefault();
    onSubmit({ title, description: description || null, notes: notes || null, tags: parseTags(tags) });
  }

  return (
    <form className="project-form" onSubmit={submit}>
      <label>
        <span>Název</span>
        <input required maxLength={240} value={title} onChange={(event) => setTitle(event.target.value)} />
      </label>
      <label>
        <span>Popis</span>
        <textarea maxLength={2000} rows={3} value={description} onChange={(event) => setDescription(event.target.value)} />
      </label>
      {initial ? (
        <label>
          <span>Projektové poznámky</span>
          <textarea maxLength={20000} rows={5} value={notes} onChange={(event) => setNotes(event.target.value)} />
        </label>
      ) : null}
      <label>
        <span>Štítky <small>oddělené čárkou</small></span>
        <input value={tags} onChange={(event) => setTags(event.target.value)} />
      </label>
      <button className="button button--primary" type="submit" disabled={pending || !title.trim()}>
        {pending ? "Ukládám…" : submitLabel}
      </button>
    </form>
  );
}

export function ProjectsModule() {
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState<"active" | "archived">("active");
  const [createOpen, setCreateOpen] = useState(false);
  const [inspectedProjectId, setInspectedProjectId] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [conflict, setConflict] = useState(false);
  const workspaceId = useStudioStore((state) => state.workspaceId);
  const projectId = useStudioStore((state) => state.projectId);
  const setProject = useStudioStore((state) => state.setProject);
  const dataSource = useStudioData();
  const queryClient = useQueryClient();
  const projectsQuery = useQuery({
    queryKey: ["studio", "projects", workspaceId],
    queryFn: () => dataSource.listProjects(workspaceId!),
    enabled: workspaceId !== null,
  });
  const selectedId = inspectedProjectId ?? projectId;
  const detailQuery = useQuery({
    queryKey: ["studio", "project", selectedId],
    queryFn: () => dataSource.getProject(selectedId!),
    enabled: selectedId !== null,
  });
  const projectMediaQuery = useQuery({
    queryKey: ["studio", "project-media", workspaceId, selectedId],
    queryFn: () => dataSource.listProjectMedia(workspaceId!, selectedId!),
    enabled: workspaceId !== null && selectedId !== null,
  });

  useEffect(() => {
    if (projectId) setInspectedProjectId(projectId);
  }, [projectId]);

  const refreshProject = (project: ProjectSummary) => {
    queryClient.setQueryData(["studio", "project", project.id], project);
    void queryClient.invalidateQueries({ queryKey: ["studio", "projects", project.workspaceId] });
  };
  const handleError = (error: unknown) => {
    setNotice(errorMessage(error));
    setConflict(error instanceof StudioApiError && error.code === "revision_conflict");
  };

  const createMutation = useMutation({
    mutationFn: (input: ProjectInput) => dataSource.createProject(workspaceId!, input),
    onSuccess: (project) => {
      refreshProject(project);
      setProject(project.id);
      setInspectedProjectId(project.id);
      setCreateOpen(false);
      setNotice("Projekt byl vytvořen.");
    },
    onError: handleError,
  });
  const updateMutation = useMutation({
    mutationFn: ({ project, input }: { project: ProjectSummary; input: ProjectInput }) =>
      dataSource.updateProject(project.id, project.revision, input),
    onSuccess: (project) => {
      refreshProject(project);
      setNotice("Změny projektu byly uloženy.");
      setConflict(false);
    },
    onError: handleError,
  });
  const archiveMutation = useMutation({
    mutationFn: (project: ProjectSummary) => dataSource.archiveProject(project.id, project.revision),
    onSuccess: (project) => {
      refreshProject(project);
      setProject(null);
      setStatus("archived");
      setNotice("Projekt byl archivován. Média ani soubory se nezměnily.");
    },
    onError: handleError,
  });
  const restoreMutation = useMutation({
    mutationFn: (project: ProjectSummary) => dataSource.restoreProject(project.id, project.revision),
    onSuccess: (project) => {
      refreshProject(project);
      setProject(project.id);
      setStatus("active");
      setNotice("Projekt byl obnoven.");
    },
    onError: handleError,
  });

  const projects = useMemo(() => {
    const normalizedQuery = query.trim().toLocaleLowerCase("cs");
    return (projectsQuery.data ?? []).filter(
      (project) =>
        project.status === status &&
        (!normalizedQuery || project.title.toLocaleLowerCase("cs").includes(normalizedQuery)),
    );
  }, [projectsQuery.data, query, status]);
  const detail = detailQuery.data;

  return (
    <div className="module-page projects-module">
      <header className="module-heading">
        <div>
          <p className="eyebrow">Studio Project Core</p>
          <h1>Projekty</h1>
          <p className="module-lead">Pracovní celky uložené v samostatné Studio databázi.</p>
        </div>
        <button className="button button--primary" type="button" disabled={!workspaceId} onClick={() => setCreateOpen((value) => !value)}>
          {createOpen ? "Zavřít formulář" : "Nový projekt"}
        </button>
      </header>

      {notice ? (
        <div className={conflict ? "feedback feedback--error" : "feedback"} role={conflict ? "alert" : "status"}>
          <span>{notice}</span>
          {conflict ? <button type="button" onClick={() => { setConflict(false); void detailQuery.refetch(); }}>Načíst aktuální verzi</button> : null}
        </div>
      ) : null}

      {createOpen && workspaceId ? (
        <section className="project-create-panel" aria-label="Vytvořit projekt">
          <h2>Nový projekt</h2>
          <ProjectForm submitLabel="Vytvořit projekt" pending={createMutation.isPending} onSubmit={(input) => createMutation.mutate(input)} />
        </section>
      ) : null}

      {!workspaceId ? (
        <section className="module-state" role="status"><h2>Není připojený workspace</h2><p>Spusťte Studio s parametrem <code>--workspace</code>.</p></section>
      ) : projectsQuery.isPending ? (
        <section className="module-state" role="status">Načítám projekty…</section>
      ) : projectsQuery.isError ? (
        <section className="module-state module-state--error" role="alert"><h2>Projekty se nepodařilo načíst</h2><p>{errorMessage(projectsQuery.error)}</p></section>
      ) : (
        <div className="projects-workspace">
          <section className="projects-list-panel">
            <div className="project-list-tools">
              <label className="search-field"><span className="sr-only">Filtrovat projekty</span><input type="search" placeholder="Filtrovat projekty" value={query} onChange={(event) => setQuery(event.target.value)} /></label>
              <div className="segmented-control" role="group" aria-label="Stav projektů">
                <button type="button" aria-pressed={status === "active"} onClick={() => setStatus("active")}>Aktivní</button>
                <button type="button" aria-pressed={status === "archived"} onClick={() => setStatus("archived")}>Archivované</button>
              </div>
            </div>
            {projects.length ? (
              <div className="project-list" aria-label="Dostupné projekty">
                {projects.map((project) => {
                  const active = project.id === projectId;
                  const inspected = project.id === selectedId;
                  return (
                    <button
                      type="button"
                      className={`project-row${active ? " project-row--active" : ""}${inspected ? " project-row--inspected" : ""}`}
                      aria-pressed={inspected}
                      key={project.id}
                      onClick={() => {
                        setInspectedProjectId(project.id);
                        setProject(project.status === "active" ? project.id : null);
                      }}
                    >
                      <span><strong>{project.title}</strong><small>{project.description || "Bez popisu"}</small></span>
                      <span className="project-row__meta">{project.mediaCount} médií · {project.status === "active" ? "Aktivní" : "Archivovaný"}</span>
                    </button>
                  );
                })}
              </div>
            ) : <div className="empty-inline">Žádné odpovídající projekty.</div>}
          </section>

          <section className="project-detail-panel" aria-label="Detail projektu">
            {!selectedId ? <div className="empty-inline">Vyberte projekt ze seznamu.</div> : detailQuery.isPending ? <p>Načítám detail…</p> : detailQuery.isError ? <div role="alert">{errorMessage(detailQuery.error)}</div> : detail ? (
              <>
                <div className="project-detail-heading">
                  <div><span className={`status-badge status-badge--${detail.status}`}>{detail.status === "active" ? "Aktivní" : "Archivovaný"}</span><h2>{detail.title}</h2></div>
                  {detail.status === "active" ? (
                    <button className="button button--danger" type="button" disabled={archiveMutation.isPending} onClick={() => archiveMutation.mutate(detail)}>Archivovat</button>
                  ) : (
                    <button className="button button--primary" type="button" disabled={restoreMutation.isPending} onClick={() => restoreMutation.mutate(detail)}>Obnovit projekt</button>
                  )}
                </div>
                {detail.status === "active" ? (
                  <ProjectForm key={`${detail.id}-${detail.revision}`} initial={detail} submitLabel="Uložit změny" pending={updateMutation.isPending} onSubmit={(input) => updateMutation.mutate({ project: detail, input })} />
                ) : <div className="read-only-note">Archivovaný projekt je pouze pro čtení. Obnovením jej znovu zpřístupníte pro úpravy.</div>}
                <div className="project-media-summary">
                  <h3>Připojená média <span>{detail.mediaCount}</span></h3>
                  {projectMediaQuery.isPending ? <p>Načítám média…</p> : projectMediaQuery.data?.length ? (
                    <ul>{projectMediaQuery.data.slice(0, 8).map((media) => <li key={media.id}>{media.title}</li>)}</ul>
                  ) : <p>Projekt zatím nemá připojená média.</p>}
                </div>
              </>
            ) : null}
          </section>
        </div>
      )}
    </div>
  );
}
