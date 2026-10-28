# Projektový datový kontrakt – návrh

**Stav:** **PROPOSED / NOT IMPLEMENTED**. Tento dokument není schválené úložiště,
migrace ani veřejné write API.

Projekt je pracovní celek, nikoli časová událost ani Session Grouper relace.
Jedno médium může být ve více projektech bez kopie originálu.

```ts
interface Project {
  projectId: string;
  workspaceId: string;
  title: string;
  description?: string;
  revision: number;
  createdAt: string;
  updatedAt: string;
}

interface ProjectMediaLink {
  projectId: string;
  mediaId: string; // stabilní veřejné asset ID existujícího workspace
  role: "source" | "reference" | "output";
  sortOrder?: number;
}
```

Budoucí Studio project service má vlastnit projekty a vazby. Nesmí je zapisovat
do `analysis/<processor>/`, ingest SQLite, veřejného katalogu ani stávajících
Media Desk událostí. Otevřené rozhodnutí musí určit umístění, schema verze,
atomický writer, optimistic concurrency, zálohu, přenositelnost a chování při
změně katalogu.

Prototyp používá stejné hranice pouze jako TypeScript `ProjectSummary` a
`MediaSummary.projectIds` v paměti. Neexistuje persistence ani migrační kód.
