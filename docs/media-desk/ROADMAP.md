# HUHÁČ Media Desk — roadmap po architektonickém auditu

**Auditováno:** 2026-10-22

**Větev:** `mediadesk`

**Auditovaný commit:** `4397b9289de8689ed9282d9cbce842f3de4a60c2`

Tato roadmapa nenahrazuje historické M2–M5 novými významy. Popisuje jen bezpečnou
posloupnost pro tři schválené provozní scénáře.

1. **Audit skutečnosti — COMPLETE.** Inventura M1–M1.3, ownership, cest,
   persistence a gapů je v `AUDIT_2026-10.md`.
2. **Architektonické schválení — STOP GATE.** Pro nejbližší S2a schválit D-011
   (lokální mapping) a jeho validační hranice. D-012 (ingest-owned init) a
   podporovaný writer model mohou zůstat explicitně odložené, ale musí být
   schváleny před etapou, která je použije. Do schválení S2a bez kódu.
3. **Nejmenší bezpečná etapa S2a — PROPOSED.** Přidat pouze host-specific,
   read-only mapping originálů pro Media Desk. Mapping uložit lokálně vedle
   profilu, svázat s `workspace_id` a původním `source_root`, validovat bez zápisu
   do workspace a při chybě degradovat na offline originály. Žádné změny
   procesorů, ingestu, veřejného katalogu ani DB.
4. **S2b — PROPOSED.** Po provozním ověření rozhodnout, zda stejnou abstrakci
   potřebují Video Keyframes/ingest. Teprve pak navrhnout společný adapter nebo
   contract v2; bez automatické migrace.
5. **S1 — PROPOSED.** Navrhnout a implementovat úzký ingest-owned `init` pro nový
   archiv s idempotencí, explicitní autoritou, rollbackem a testem prázdného
   adresáře. Web může toto rozhraní volat až po samostatném security review.
6. **S3 hardening — PROPOSED.** Retry/reconnect, diagnostika mountu a mappingu,
   záloha konfigurace a definice podporovaného single-writer deploymentu.
7. **Portable user data — DEFERRED.** Samostatné schema/ownership/backup ADR;
   nepatří do storage setup etapy.

## Akceptace navržené S2a

- Windows vytvořený workspace se na Linuxu otevře beze změny kteréhokoli souboru
  workspace a originálů.
- Správný lokální Media Storage root zpřístupní pouze aktivní originály uvnitř
  tohoto kořene; preview fungují i bez něj.
- Nesprávný, nedostupný či později změněný root nezmění poslední validní mapping,
  neunikne mimo root a zobrazí bezpečný offline/diagnostický stav.
- `workspace_id`, asset SHA, katalogový `source_root`, analýzy a ingest DB zůstanou
  byte-for-byte beze změny.
- Běžný start neprovádí full rehash. Volitelný hluboký verify je explicitní akce.
