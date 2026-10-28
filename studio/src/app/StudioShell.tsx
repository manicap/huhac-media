import { useEffect, useMemo, useState } from "react";
import { NavLink, useLocation, useNavigate } from "react-router-dom";

import { useStudioStore } from "../context/studioStore";
import { ChevronIcon } from "./moduleIcons";
import {
  isModuleAvailable,
  type StudioModuleDefinition,
} from "./moduleContract";
import { ModuleErrorBoundary } from "./ModuleErrorBoundary";
import { WorkspacePicker } from "./WorkspacePicker";

export function StudioShell({
  modules,
  capabilities,
}: {
  readonly modules: readonly StudioModuleDefinition[];
  readonly capabilities: ReadonlySet<string>;
}) {
  const [navigationCollapsed, setNavigationCollapsed] = useState(false);
  const location = useLocation();
  const navigate = useNavigate();
  const setActiveModule = useStudioStore((state) => state.setActiveModule);
  const selectedCount = useStudioStore((state) => state.selectedMediaIds.length);
  const availabilityContext = useMemo(() => ({ capabilities }), [capabilities]);
  const availableModules = modules.filter((module) =>
    isModuleAvailable(module, availabilityContext),
  );
  const routeModuleId = location.pathname.match(/^\/modules\/([^/]+)\/?$/)?.[1];
  const activeModule = availableModules.find((module) => module.id === routeModuleId);

  useEffect(() => {
    if (location.pathname === "/" && availableModules[0]) {
      navigate(`/modules/${availableModules[0].id}`, { replace: true });
    }
  }, [availableModules, location.pathname, navigate]);

  useEffect(() => {
    if (activeModule) {
      setActiveModule(activeModule.id);
    }
  }, [activeModule, setActiveModule]);

  return (
    <div className={navigationCollapsed ? "studio studio--collapsed" : "studio"}>
      <aside className="studio-navigation" aria-label="Moduly Studia">
        <div className="brand-lockup">
          <span className="brand-mark" aria-hidden="true">H</span>
          <div className="brand-copy">
            <strong>HUHÁČ</strong>
            <span>Studio</span>
          </div>
        </div>
        <nav className="module-navigation">
          {modules.map((module) => {
            const available = isModuleAvailable(module, availabilityContext);
            const Icon = module.icon;
            return available ? (
              <NavLink
                key={module.id}
                className={({ isActive }) =>
                  isActive ? "module-link module-link--active" : "module-link"
                }
                to={`/modules/${module.id}`}
                title={navigationCollapsed ? module.title : undefined}
              >
                <Icon className="module-link__icon" />
                <span>{module.title}</span>
              </NavLink>
            ) : (
              <span
                aria-disabled="true"
                className="module-link module-link--disabled"
                key={module.id}
                title={module.unavailableReason ?? "Modul není dostupný"}
              >
                <Icon className="module-link__icon" />
                <span>{module.title}</span>
              </span>
            );
          })}
        </nav>
        <button
          className="collapse-button"
          type="button"
          aria-label={navigationCollapsed ? "Rozbalit navigaci" : "Sbalit navigaci"}
          aria-expanded={!navigationCollapsed}
          onClick={() => setNavigationCollapsed((value) => !value)}
        >
          <ChevronIcon />
          <span>Sbalit panel</span>
        </button>
      </aside>

      <header className="studio-header">
        <WorkspacePicker />
        <div className="selection-status" aria-live="polite">
          <span className="status-dot" aria-hidden="true" />
          <strong>{selectedCount}</strong> vybráno
        </div>
      </header>

      <main className="studio-main" id="main-content">
        {availableModules.map((module) => {
          const ModuleComponent = module.component;
          const isActive = module.id === activeModule?.id;
          return (
            <section
              className="module-panel"
              aria-label={module.title}
              hidden={!isActive}
              key={module.id}
            >
              <ModuleErrorBoundary moduleTitle={module.title}>
                <ModuleComponent />
              </ModuleErrorBoundary>
            </section>
          );
        })}
        {location.pathname !== "/" && !activeModule ? (
          <section className="module-state" role="status">
            <p className="eyebrow">Navigace</p>
            <h2>Modul není dostupný</h2>
            <p>Zvolte některý z dostupných modulů v levém panelu.</p>
          </section>
        ) : null}
      </main>
    </div>
  );
}
