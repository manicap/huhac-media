# Media Connector — roadmap

1. **Architektonický návrh — COMPLETE.** Samostatná větev a komponentové hranice.
2. **MC1 Local Discovery — COMPLETE.** Read-only JSON CLI, lokální adaptér,
   bezpečná enumerace a pagination bez persistence či čtení obsahu.
3. **Google Drive discovery — DEFERRED / REQUIRES APPROVAL.** OAuth, běžné
   soubory, shared drives, shortcuts a cloud-native dokumenty.
4. **Povinný bezpečný staging a Local Transfer — COMPLETE / WINDOWS VERIFIED.**
   Každý zdroj zůstává read-only; pouze úplná ověřená kopie může být publikována
   do Media Storage. Transakce, recovery, writer, persistence, kolize a retence
   používají schválený SHA-256 CAS, atomic no-replace publish a recovery.
   Rozhodnutí je v [TRANSFER_ADR.md](TRANSFER_ADR.md), prováděcí pořadí v
   [TRANSFER_IMPLEMENTATION_PLAN.md](TRANSFER_IMPLEMENTATION_PLAN.md).
5. **Content identity a transfer evidence — COMPLETE PRO LOCAL.**
   Deduplikace napříč zdroji a historie transferů oddělená od originálních
   souborů; veřejným výstupem je redigovaný provenance manifest v1.
6. **Samostatný Media Ingest handoff — BOUNDARY IMPLEMENTED / ORCHESTRATION ABSENT.**
   Ingest přijímá pouze lokálně převzaté originály z Media Storage a nespouští se
   automaticky. Provenience se propojí bez změny workspace contract v1 a bez
   čtení ingest SQLite.

Google Drive, automatická orchestrace Ingestu, NAS kvalifikace a další adaptéry
nejsou touto etapou autorizované.
