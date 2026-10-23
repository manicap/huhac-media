# HUHÁČ Media Desk — roadmap po architektonickém auditu

**Auditováno:** 2026-10-22

**Větev:** `mediadesk`

**Auditovaný commit:** `4397b9289de8689ed9282d9cbce842f3de4a60c2`

**Roadmap aktualizována:** 2026-10-22 po architektonickém schválení

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
4. **S2b — ACCEPTED / IMPLEMENTATION AUTHORIZED, NOT YET IMPLEMENTED.** Nové zadání tímto
   názvem označuje úzký ingest-owned `init` nového archivu, dříve vedený jako S1.
   Návrh zahrnuje JSON CLI, idempotenci, crash recovery, prázdný katalog,
   lokální-only workspace a chráněnou Media Desk orchestraci. Viz
   [S2B_DESIGN.md](S2B_DESIGN.md),
   [S2B_FAILURE_MATRIX.md](S2B_FAILURE_MATRIX.md) a
   [S2B_IMPLEMENTATION_PLAN.md](S2B_IMPLEMENTATION_PLAN.md). D-017 až D-020 byly
   schváleny 2026-10-23; lokální-only workspace je omezení etapy S2b, ne cílové
   rozhodnutí o přenosné knihovně nebo centrálním úložišti metadat.
5. **Shared storage resolver — DEFERRED / UNNUMBERED.** Dříve byl pracovně
   označen jako S2b. Po provozním ověření se teprve rozhodne, zda společnou
   abstrakci potřebují Video Keyframes/ingest; contract v2 ani migrace nejsou
   schválené.
6. **S3 hardening — PROPOSED.** Retry/reconnect, diagnostika mountu a mappingu,
   záloha konfigurace a definice podporovaného single-writer deploymentu.
7. **Portable user data — DEFERRED.** Samostatné schema/ownership/backup ADR;
   nepatří do storage setup etapy.

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
