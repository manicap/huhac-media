import { MediaLibraryModule } from "../modules/media-library";
import { ProjectsModule } from "../modules/projects";
import { LibraryIcon, ProjectsIcon } from "./moduleIcons";
import { defineModuleRegistry } from "./moduleContract";

export const studioModuleRegistry = defineModuleRegistry([
  {
    id: "projects",
    title: "Projekty",
    navigationOrder: 10,
    icon: ProjectsIcon,
    component: ProjectsModule,
    requiredCapabilities: ["synthetic-projects"],
  },
  {
    id: "media-library",
    title: "Mediální knihovna",
    navigationOrder: 20,
    icon: LibraryIcon,
    component: MediaLibraryModule,
    requiredCapabilities: ["synthetic-library"],
  },
]);
