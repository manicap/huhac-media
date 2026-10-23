# Media Connector — roadmap

1. **Architektonický návrh — COMPLETE.** Samostatná větev a komponentové hranice.
2. **MC1 Local Discovery — COMPLETE.** Read-only JSON CLI, lokální adaptér,
   bezpečná enumerace a pagination bez persistence či čtení obsahu.
3. **Google Drive discovery — DEFERRED / REQUIRES APPROVAL.** OAuth, běžné
   soubory, shared drives, shortcuts a cloud-native dokumenty.
4. **Povinný bezpečný staging a Transfer — ACCEPTED/TARGET, NOT IMPLEMENTED.**
   Každý zdroj zůstává read-only; pouze úplná ověřená kopie může být publikována
   do Media Storage. Transakce, recovery, writer, persistence, kolize a retence
   vyžadují detailní ADR před implementací.
   Návrh je připraven v [TRANSFER_ADR.md](TRANSFER_ADR.md) a čeká na schválení;
   prováděcí pořadí je v
   [TRANSFER_IMPLEMENTATION_PLAN.md](TRANSFER_IMPLEMENTATION_PLAN.md).
5. **Content identity a transfer evidence — ACCEPTED/TARGET, NOT IMPLEMENTED.**
   Deduplikace napříč zdroji a historie transferů oddělená od originálních
   souborů; přesné schema zůstává otevřené.
6. **Samostatný Media Ingest handoff — ACCEPTED/TARGET, NOT IMPLEMENTED.**
   Ingest přijímá pouze lokálně převzaté originály z Media Storage a nespouští se
   automaticky. Provenience se propojí bez změny workspace contract v1 a bez
   čtení ingest SQLite.

Po MC1 se vývoj zastavuje. Žádný následující bod není implementovaný ani
automaticky autorizovaný.
