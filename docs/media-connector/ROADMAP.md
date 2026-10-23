# Media Connector — roadmap

1. **Architektonický návrh — COMPLETE.** Samostatná větev a komponentové hranice.
2. **MC1 Local Discovery — COMPLETE.** Read-only JSON CLI, lokální adaptér,
   bezpečná enumerace a pagination bez persistence či čtení obsahu.
3. **Google Drive discovery — DEFERRED / REQUIRES APPROVAL.** OAuth, běžné
   soubory, shared drives, shortcuts a cloud-native dokumenty.
4. **Bezpečný staging a transfer — DEFERRED / REQUIRES ADR.** Transakce,
   recovery, writer, persistence, kolize a retence.
5. **Media Ingest handoff — DEFERRED / REQUIRES ADR.** Provenience bez změny
   workspace contract v1 a bez čtení ingest SQLite.

Po MC1 se vývoj zastavuje. Žádný následující bod není implementovaný ani
automaticky autorizovaný.
