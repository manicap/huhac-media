import type { ComponentType, SVGProps } from "react";

export type ModuleIcon = ComponentType<SVGProps<SVGSVGElement>>;

export interface ModuleAvailabilityContext {
  readonly capabilities: ReadonlySet<string>;
}

export interface StudioModuleDefinition {
  readonly id: string;
  readonly title: string;
  readonly navigationOrder: number;
  readonly icon: ModuleIcon;
  readonly component: ComponentType;
  readonly requiredCapabilities?: readonly string[];
  readonly isAvailable?: (context: ModuleAvailabilityContext) => boolean;
  readonly unavailableReason?: string;
}

export function isModuleAvailable(
  module: StudioModuleDefinition,
  context: ModuleAvailabilityContext,
): boolean {
  const hasCapabilities = (module.requiredCapabilities ?? []).every((capability) =>
    context.capabilities.has(capability),
  );
  return hasCapabilities && (module.isAvailable?.(context) ?? true);
}

export function defineModuleRegistry(
  modules: readonly StudioModuleDefinition[],
): readonly StudioModuleDefinition[] {
  const ids = new Set<string>();
  for (const module of modules) {
    if (!module.id || ids.has(module.id)) {
      throw new Error(`Duplicate or empty Studio module id: ${module.id}`);
    }
    ids.add(module.id);
  }
  return [...modules].sort(
    (left, right) =>
      left.navigationOrder - right.navigationOrder ||
      left.title.localeCompare(right.title, "cs"),
  );
}
