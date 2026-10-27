# ADR-N1: Metadata Normalizer v1 — základní kontrakt N1

- **Stav:** ACCEPTED/IMPLEMENTED pro TASK-NORM-001 a rozšíření TASK-NORM-002
- **Datum:** 2026-10-26
- **Rozhodnutí schválil:** implementační scope TASK-NORM-001
- **Auditovaný základ:** Git HEAD `2b4f2e55395f3981e5522f5538fa740f07002b93`

## Kontext

Veřejný workspace contract v1 publikuje katalog a per-asset metadata, ale
neexistuje samostatný, rebuildovatelný read model společných source facts.
Procesory vlastní oddělené namespaces a ingest SQLite je privátní. Media Desk
má host-local user data, která nesmějí přejít do přenositelného processor
artefaktu.

## Rozhodnutí

N1 zavádí procesor `normalizer` / `normalizer-v1` bez databáze. Čte výhradně
`workspace.json`, odkazovaný asset catalog a veřejné per-asset metadata.
Nečte raw metadata, SQLite, originály, výsledky jiných procesorů ani Media Desk
user data.

Publikuje immutable snapshot:

```text
analysis/normalizer/normalizer-v1/
  <configuration_fingerprint>/
    <input_set_fingerprint>/
      manifest.json
      assets/<sha-prefix>/<sha256>.json
```

Snapshot se nejprve celý vytvoří v sibling staging directory. `manifest.json`
se ve stagingu zapíše jako poslední a teprve kompletní directory se atomicky
přesune na finální cestu. Existující validní snapshot se pouze reuseuje a
nepřepisuje. Historické snapshoty se automaticky nemažou.

`configuration_fingerprint` je SHA-256 canonical JSON recipe N1.
`input_set_fingerprint` pokrývá semantic identity manifestu, catalogu a všech
metadata dokumentů, které N1 skutečně čte. Absolutní `source_root`, filesystem
pořadí, mtimes a aktuální čas do fingerprintu nevstupují.

NormalizedAsset v1 připravuje stabilní sekce `identity`, `technical`,
`temporal`, `semantic`, `people`, `event`, `quality`, `provenance` a
`completeness`. N1 naplní pouze source facts, technical, temporal, provenance a
completeness. Ostatní sekce mají explicitní prázdný nebo `not_analyzed` stav;
neobsahují smyšlené inference.

Typed metadata používají uzavřený allowlist jednoznačných převodů. Neplatná či
nejednoznačná hodnota dává typed `null`, původní hodnotu v warning evidence a
nikdy odhad.

## Důsledky

- Workspace contract major zůstává 1; nový processor output je additive a má
  vlastní dokumentovaný contract.
- N1 je plně rebuildovatelný a nevyžaduje mutable state, server ani službu.
- `plan` a `status` jsou striktně read-only; `analyze` zapisuje pouze do
  Normalizer namespace.
- N2 může přidat explicitně vybrané Session/Keyframes/Vision/Faces inputs do
  recipe a input fingerprintu bez změny základního snapshot layoutu.
- N3 může vytvořit Media Desk read adapter a host-local user assertion overlay;
  user data nejsou součástí Normalizer artefaktu.

## Přijaté rozšíření N2 (2026-10-26)

TASK-NORM-002 schvaluje rozšíření stejného `normalizer-v1` kontraktu bez změny
workspace contract major nebo processor ownership. Konfigurace explicitně nese
fingerprinty Session Grouper, Video Keyframes, Vision, Faces a volitelného
Faces Clustering; agregátní výsledky mohou navíc nést logical input fingerprint.

Normalizer validuje v1 envelope, workspace/asset identity, konfiguraci,
modelovou a input provenance a veřejné reference. Hash každého skutečně
čteného upstream JSON souboru nebo explicitní missing/invalid sentinel vstupuje
do input fingerprintu. Ambiguous aggregate či keyframe selection blokuje
publikaci; neexistující explicitní výsledek zůstává dohledatelný jako
`input_unavailable`.

Vision a Faces se projektují po jednotlivých preview/keyframe vstupech. Exact
facety smějí pouze trimovat a deduplikovat podle Unicode casefold; nesmějí
vytvářet překlady, synonyma, confidence ani tvrzení o celém videu. Faces počet
detekcí zůstává oddělený od Vision odhadu lidí a video nemá asset-level počet
unikátních tváří. Cluster references jsou anonymní, nikoli identita.

## Odmítnuté varianty

- Čtení ingest SQLite: porušuje veřejnou kompatibilitní hranici.
- Přepis metadata asset dokumentů: porušuje producer ownership.
- Jeden mutable `current.json`: vytváří implicitní výběr a přepis historie.
- Nová indexační DB: N1 pro ni nemá výkonový ani lifecycle důvod.
- Kopírování Media Desk user assertions: porušuje dnešní host-local ownership.

## Brány dalších změn

Zápis mimo Normalizer namespace, změna workspace contract major, přenositelná
user data, persistentní index/DB nebo automatický výběr mezi více upstream
fingerprinty vyžadují nové samostatné rozhodnutí.
