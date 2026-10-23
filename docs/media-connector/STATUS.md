# Media Connector — stav

**Aktualizováno:** 2026-10-23

**Větev:** `feature/media-connector`

**Základ:** `0433703ad88293c03000dbd1cd4197fbd2e2a51e`

## Skutečný stav

- **IMPLEMENTED:** samostatná vývojová větev a dokumentační prostor.
- **ACCEPTED/TARGET:** jeden klient = jedna knihovna; oddělené local/Google Drive
  adaptéry; zachování workspace contract v1; izolace od ingest SQLite.
- **PROPOSED:** architektura, adapter contract, immutable delivery, handoff
  manifest, recovery model, privátní stav a OAuth bezpečnostní model.
- **ABSENT:** runtime kód, CLI, lokální adaptér, Google Drive adaptér, transfer,
  journal, handoff a integrace s Media Ingestem.
- **UNVERIFIED:** Google API chování, Windows reparse-point implementace,
  nativní Linux confinement, NAS/cloud failure scénáře a výkon velkých listingů.

## Auditovaný základ

Před návrhem byly porovnány:

- `AGENTS.md` a Documentation First & Documentation Sync;
- `docs/system-overview.md` a `docs/architecture.md`;
- `docs/media-ingest.md` a `docs/workspace-contract.md`;
- dokončená rozhodnutí a roadmap Media Desku v
  `docs/media-desk/DECISIONS.md` a `docs/media-desk/ROADMAP.md`;
- lokální a vzdálený commit větve `mediadesk` po `git fetch`.

Zjištěný materiální rozpor je pouze názvoslovný: existující dokumentace uvádí
budoucí neimplementovaný **Media Collector**, zatímco nové zadání zavádí
**Media Connector**. Návrh změnu zaznamenává, ale bez schválení nepřepisuje
globální dokumentaci.

## Důkazy a testy této etapy

Produkční kód se nemění, proto nejsou runtime testy účelné. Před uzavřením
dokumentačního commitu se ověří relativní odkazy, `git diff --check`, seznam
změněných souborů a nezměněný základ větve `mediadesk`.
