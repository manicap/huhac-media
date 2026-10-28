import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import { useStudioStore } from "../../context/studioStore";
import { useStudioData } from "../../data/StudioDataProvider";

export function ProjectsModule() {
  const [query, setQuery] = useState("");
  const workspaceId = useStudioStore((state) => state.workspaceId);
  const projectId = useStudioStore((state) => state.projectId);
  const setProject = useStudioStore((state) => state.setProject);
  const dataSource = useStudioData();
  const projectsQuery = useQuery({
    queryKey: ["studio", "projects", workspaceId],
    queryFn: () => dataSource.listProjects(workspaceId!),
    enabled: workspaceId !== null,
  });
  const projects = useMemo(() => {
    const normalizedQuery = query.trim().toLocaleLowerCase("cs");
    return (projectsQuery.data ?? []).filter(
      (project) =>
        !normalizedQuery ||
        `${project.title} ${project.description}`
          .toLocaleLowerCase("cs")
          .includes(normalizedQuery),
    );
  }, [projectsQuery.data, query]);

  return (
    <div className="module-page projects-module">
      <header className="module-heading">
        <div>
          <p className="eyebrow">Pracovní kontext</p>
          <h1>Projekty</h1>
          <p className="module-lead">
            Syntetické pracovní celky oddělené od událostí a automatických sessions.
          </p>
        </div>
        <label className="search-field">
          <span className="sr-only">Filtrovat projekty</span>
          <input
            type="search"
            placeholder="Filtrovat projekty"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </label>
      </header>

      {!workspaceId ? (
        <section className="module-state" role="status">
          <h2>Není vybraný workspace</h2>
          <p>Vyberte pracovní prostor v horní liště.</p>
        </section>
      ) : projectsQuery.isPending ? (
        <section className="module-state" role="status">Načítám projekty…</section>
      ) : projectsQuery.isError ? (
        <section className="module-state module-state--error" role="alert">
          <h2>Projekty se nepodařilo načíst</h2>
          <p>Zkontrolujte datový adaptér a zkuste načtení znovu.</p>
        </section>
      ) : projects.length === 0 ? (
        <section className="module-state" role="status">
          <h2>Žádné odpovídající projekty</h2>
          <p>Změňte filtr nebo zvolte jiný workspace.</p>
        </section>
      ) : (
        <div className="project-grid" aria-label="Dostupné projekty">
          {projects.map((project) => {
            const active = project.id === projectId;
            return (
              <button
                type="button"
                className={active ? "project-card project-card--active" : "project-card"}
                aria-pressed={active}
                key={project.id}
                onClick={() => setProject(project.id)}
              >
                <span
                  className="project-card__accent"
                  style={{ background: project.accent }}
                  aria-hidden="true"
                />
                <span className="project-card__body">
                  <span className="project-card__meta">
                    {project.mediaCount} {project.mediaCount === 1 ? "médium" : "médií"}
                  </span>
                  <strong>{project.title}</strong>
                  <span>{project.description}</span>
                </span>
                <span className="project-card__state">
                  {active ? "Aktivní" : "Otevřít"}
                </span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
