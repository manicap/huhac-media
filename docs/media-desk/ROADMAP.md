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
4. **S2b — PROPOSED.** Po provozním ověření rozhodnout, zda stejnou abstrakci
   potřebují Video Keyframes/ingest. Teprve pak navrhnout společný adapter nebo
   contract v2; bez automatické migrace.
5. **S1 — ACCEPTED/TARGET, NOT IMPLEMENTED.** Navrhnout a implementovat úzký ingest-owned `init` pro nový
   archiv s idempotencí, explicitní autoritou, rollbackem a testem prázdného
   adresáře, oddělený od importu a analýzy. Web může toto rozhraní volat až po
   samostatném návrhu a security review.
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
