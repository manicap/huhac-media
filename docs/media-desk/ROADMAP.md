# HUHÁČ Media Desk — roadmap po architektonickém auditu

**Auditováno:** 2026-10-27

**Větev:** `codex/media-desk-working-library-v1`

**Výchozí commit konsolidace:** `288b9e6221459c074d80016518a4fbaa8bc90aa4`

**Roadmap aktualizována:** 2026-10-27 po konsolidaci Launcheru v0.2

Tato roadmapa nenahrazuje historické M2–M5 novými významy. Popisuje jen bezpečnou
posloupnost pro tři schválené provozní scénáře.

1. **Audit skutečnosti — COMPLETE.** Inventura M1–M1.3, ownership, cest,
   persistence a gapů je v `AUDIT_2026-10.md`.
2. **Architektonické schválení — COMPLETE 2026-10-22.** D-011, D-012 a zákaz
   multi-host SQLite zápisu byly schváleny. Konkrétní budoucí writer/backup model
   zůstává otevřený do síťové zapisující etapy.
3. **Nejmenší bezpečná etapa S2a — COMPLETE 2026-10-22.** Host-specific,
   read-only mapping originálů pro Media Desk je uložen lokálně v profilu,
   svázán s `workspace_id` a původním `source_root`, validován bez zápisu do
   workspace a při chybě degraduje na offline originály. Procesory, ingest,
   veřejný katalog a DB zůstaly beze změny. Prováděcí plán a důkazy:
   [S2A_IMPLEMENTATION_PLAN.md](S2A_IMPLEMENTATION_PLAN.md). S2a je přechodný
   adapter pro v1, nikoli cílová storage architektura.
3a. **S2a.1 — COMPLETE 2026-10-22.** Plošné per-asset filesystem kontroly
   originálů byly ze startu odstraněny; autorizace, confinement a bezpečné
   otevření konkrétního souboru probíhají v GET/Range požadavku. Na syntetickém
   10k katalogu klesl p50 startu z 25,77 s na 7,75 s (3,32×) a startup provádí
   0 per-file I/O originálů. Důkazy: [S2A1_STARTUP_PERFORMANCE.md](S2A1_STARTUP_PERFORMANCE.md).
4. **S2b — COMPLETE 2026-10-23.** Nové zadání tímto
   názvem označuje úzký ingest-owned `init` nového archivu, dříve vedený jako S1.
   Návrh zahrnuje JSON CLI, idempotenci, crash recovery, prázdný katalog,
   lokální-only workspace a chráněnou Media Desk orchestraci. Viz
   [S2B_DESIGN.md](S2B_DESIGN.md),
   [S2B_FAILURE_MATRIX.md](S2B_FAILURE_MATRIX.md) a
   [S2B_IMPLEMENTATION_PLAN.md](S2B_IMPLEMENTATION_PLAN.md) a
   [S2B_VERIFICATION.md](S2B_VERIFICATION.md). Lokální-only workspace je omezení
   etapy S2b, ne cílové rozhodnutí o přenosné knihovně nebo centrálních metadatech.
4a. **Pracovní knihovna v1 — COMPLETE 2026-10-25.** Media Desk má stabilní
   zobrazovací a katalogizační názvy, lazy přehrávače ve virtualizovaných kartách,
   browser-local sdílenou hlasitost, lokální evidenci akcí nad Session Grouper
   relacemi a bezpečnou práci s cestou k originálu. Uživatelská data jsou oddělená
   od workspace a ingest SQLite; přenosná synchronizace zůstává odložená.
4b. **Správa akcí a časová navigace v1.4 — COMPLETE 2026-10-26.** Jedna relace
   může obsahovat více intervalových akcí, ruční výjimky mají přednost a knihovna
   zachovává virtualizaci při zobrazení sbalitelných sekcí. Zápisy jsou atomické,
   revizně chráněné a zůstávají pouze v Media Desk-owned per-user JSON.
4c. **HUHÁČ Launcher v0.2 — COMPLETE 2026-10-27.** Windows Tkinter wrapper
   spravuje více explicitních workspace profilů s oddělenými user-data roots,
   porty a validovanými Normalizer snapshoty, ale současně spouští pouze jeden
   vlastněný Media Desk child na `127.0.0.1`. Readiness ověřuje přes `/health` a
   cizí proces nikdy nepřebírá ani neukončuje. Nejde o orchestraci procesorů,
   multi-workspace backend ani systémovou službu. Osobní profily jsou mimo Git;
   čistý checkout je bezpečně inicializuje z neosobního distribučního příkladu.
4d. **HUHÁČ Studio shell v0.1 — EXPERIMENTAL 2026-10-27.** An isolated static
React module shell validates project-to-library context behavior with synthetic
data. The next gate is an approved project-data ownership/persistence decision,
followed by a narrow read-only FastAPI adapter. This stage does not change Media
Desk, Launcher, workspace contract v1, or any processor.
5. **Shared storage resolver — DEFERRED / UNNUMBERED.** Dříve byl pracovně
   označen jako S2b. Po provozním ověření se teprve rozhodne, zda společnou
   abstrakci potřebují Video Keyframes/ingest; contract v2 ani migrace nejsou
   schválené.
6. **S3 hardening — PROPOSED.** Retry/reconnect, diagnostika mountu a mappingu,
   záloha konfigurace a definice podporovaného single-writer deploymentu.
7. **Portable user data — DEFERRED.** Samostatné schema/ownership/backup ADR;
   nepatří do storage setup etapy.

> **COMPLETE 2026-10-26 — Normalizer v1 / N3.** One explicit immutable snapshot
> is loaded through the read-only adapter. Detail exposes unified information and
> the library provides exact facets with stable cursors. Enrichment/ontology and
> Quality Processor remain **PLANNED / ABSENT**.

## Akceptace dokončené S2a

- Windows vytvořený workspace se na Linuxu otevře beze změny kteréhokoli souboru
  workspace a originálů.
- Správný lokální Media Storage root zpřístupní pouze aktivní originály uvnitř
  tohoto kořene; preview fungují i bez něj.
- Nesprávný, nedostupný či později změněný root nezmění poslední validní mapping,
  neunikne mimo root a zobrazí bezpečný offline/diagnostický stav.
- `workspace_id`, asset SHA, katalogový `source_root`, analýzy a ingest DB zůstanou
  byte-for-byte beze změny.
- Běžný start neprovádí full rehash. Úplný verify není součástí S2a a případně
  vyžaduje samostatnou budoucí etapu.
- UI a dokumentace označí SHA-256 výsledek jako vzorkovou kontrolu, nikoli úplnou
  kontrolu integrity archivu.
