# HUHÁČ Media Pipeline — Metadata Normalizer v1

> **Aktualizace TASK-NORM-002:** základní rozhodnutí N1 a upstream rozšíření N2 byla přijata v
> [`docs/ADR-N1-normalizer-contract.md`](docs/ADR-N1-normalizer-contract.md) a
> N1 i N2 jsou implementovány. Tento dokument zůstává návrhovým podkladem pro
> celý Normalizer v1; N3 je nadále plánované a neimplementované. Aktuální
> provozní kontrakt popisuje [`docs/normalizer.md`](docs/normalizer.md).

**Technický návrh a implementační evidence, 2026-10-26**
**Stav dokumentu:** N1/N2 **IMPLEMENTED**, N3 **PROPOSED**
**Auditovaný základ:** Git HEAD `2b4f2e55395f3981e5522f5538fa740f07002b93`; N1/N2 jsou v aktuálním necommitnutém working tree
**Rozsah auditu:** veřejný workspace contract v1, Media Ingest, Session Grouper v1,
Video Keyframe Extractor v1, Vision Processor v1, Faces Processor v1 a Media Desk v1.4.

> Terminologie stavu v tomto dokumentu: **IMPLEMENTED** znamená doložené kódem a
> testy na auditovaném commitu; **ACCEPTED/TARGET** schválený existující směr;
> **PROPOSED** tento návrh čekající na schválení; **ABSENT** funkce není v repozitáři;
> **UNVERIFIED** tvrzení nebo lokální změna bez commitnutého kontraktu.

## 1. Executive Summary

Metadata Normalizer N1/N2 dnes v projektu existuje (**IMPLEMENTED**). Je
deterministický read-only konzument veřejných JSON kontraktů, který
publikuje pouze do vlastního namespace `analysis/normalizer/normalizer-v1/`.
Nečte ingest SQLite, originály ani opaque raw metadata, nevolá AI a nemění
katalog, metadata, výsledky procesorů ani Media Desk user data.

Zásadní návrhová rozhodnutí:

1. **Odvozený procesor bez vlastní DB.** Výstup lze kompletně znovu sestavit z
   veřejného workspace snapshotu, explicitně vybraných upstream fingerprintů a
   verze normalizačních pravidel.
2. **Tři vrstvy zůstávají fyzicky oddělené.** Přenositelný Normalizer artefakt
   obsahuje source facts a machine inferences. User assertions zůstávají v
   host-local Media Desk-owned JSON; Media Desk z obou zdrojů sestaví efektivní
   read model. Rebuild tedy uživatelská data nemůže smazat.
3. **Žádný implicitní výběr mezi fingerprinty.** Konfigurace Normalizeru musí
   uvést jeden požadovaný fingerprint pro každý používaný upstream procesor a
   u videí jeden Video Keyframes fingerprint. Chybějící, neplatný, neúspěšný a
   víceznačný stav se pouze zaznamená.
4. **Žádné univerzální confidence.** Timestamp confidence Session Grouperu,
   detector confidence Faces a stav anonymního clusteru mají rozdílnou
   semantiku. Vision v1 žádné confidence nevydává.
5. **Vision video se v1 svévolně neagreguje.** Jednotlivé keyframe observations
   zůstávají samostatné. Pro filtrování lze vytvořit pouze deterministické
   exact-value facety (trim, prázdné hodnoty pryč, stabilní deduplikace), nikoli
   synonymní, překladové nebo kategoriální závěry.
6. **Historie je adresovaná vstupem.** Vedle `configuration_fingerprint` se
   počítá `input_set_fingerprint`. Nový katalog nebo nový vybraný upstream
   výsledek vytvoří nový immutable snapshot; nepřepíše historii.
7. **Media Desk má číst jeden validovaný normalizer snapshot do paměťového
   indexu.** Nová databáze není pro v1 odůvodněná. Na startu se normalizované
   záznamy načtou jednou, připojí k existujícímu `WorkspaceSnapshot` a facety se
   předpočítají pro současné filtrování/paginaci.

Navržená cesta je kompatibilní s workspace contract v1, ale zavedení nového
veřejně čitelného processor contractu a pravidel jeho výběru má být před
implementací přijato samostatným ADR. Rozšíření přenositelných user assertions,
změna ingest metadata contractu nebo zavedení persistentní indexační DB jsou
výslovně mimo MVP a rovněž by vyžadovaly ADR.

### Auditní omezení

Pracovní strom při auditu nebyl čistý. Necommitnuté změny v `docs/video-keyframes.md`,
`src/video_keyframes/*` a příslušných testech mění výchozí OpenCLIP model a
přidávají selektivní `--asset-id`. Tyto změny jsou **UNVERIFIED** a nejsou v tomto
návrhu považovány za schválený kontrakt. Pro Video Keyframes se používá stav z
auditovaného HEAD: `ViT-B-32/openai`. Návrh je vůči případné pozdější změně
odolný, protože nikdy neodvozuje význam z „defaultu“, ale ukládá model,
konfiguraci a přesný fingerprint.

## 2. Inventář skutečných vstupních dat

### 2.1 Veřejný workspace a Media Ingest

**IMPLEMENTED.** Vstupním bodem je `workspace.json`; consumer vyžaduje
`workspace_contract_version == 1`, ověřuje shodu `workspace_id` s
`metadata/catalog.json` a nesmí číst privátní `state/catalog.sqlite3`.

| Dokument/pole | Typ a povinnost | Skutečný význam pro Normalizer |
|---|---|---|
| `workspace.json.workspace_id` | neprázdný string, povinný | identita workspace |
| `asset_catalog` | relativní POSIX path, povinná | cesta ke katalogu; musí zůstat uvnitř workspace |
| `catalog.generated_at`, `generated_by_run_id` | ISO string / string, publikováno | provenance snapshotu, nikoli asset fact |
| `catalog.source_root` | absolutní host-local path | nepřenášet jako efektivní cestu; lze uvést jen jako snapshot provenance |
| `asset_id` | `sha256:<64 lowercase hex>` | primární identita NormalizedAsset |
| `sha256` | 64 lowercase hex | musí souhlasit s `asset_id` |
| `size_bytes` | integer | source fact |
| `media_type` | `image \| video` | source fact a applicability gate |
| `format`, `mime_type` | string nebo v reálné DB potenciálně null | katalogový source fact; `detected` může být přesnější |
| `availability` | `available \| unavailable` | stav publikovaného snapshotu, ne živý filesystem check |
| `metadata_location`, `preview_location` | relativní path nebo null | reference na veřejný artefakt |
| `sources[]` | array `{source_version_id, relative_path, status}` | úplná publikovaná source provenance; `status` je `active`, `superseded`, `absent` |

Per-asset metadata dokument má `schema_version`, `asset`, `detected`, `capture`,
`technical`, `raw_metadata` a `stages`. `raw_metadata` je záměrně opaque a MVP jej
neinterpretuje.

`capture` vždy publikuje čtyři klíče:

| Pole | Typ | Poznámka |
|---|---|---|
| `datetime` | string nebo null | normalizovaný ISO-8601 timestamp |
| `source` | string nebo null | konkrétní EXIF/QuickTime/ffprobe klíč, nebo `filesystem:mtime` |
| `timezone_offset` | string nebo null | explicitní offset, pokud byl zjistitelný |
| `filesystem_fallback` | boolean | `true` znamená nízkou důvěryhodnost, ne camera time |

Ingest vybírá první použitelný čas podle pevné priority. Pro obrázek zkouší
`Composite:SubSecDateTimeOriginal`, `ExifIFD/EXIF:DateTimeOriginal`, subsecond
create date a create date; pro video QuickTime/ffprobe creation time a případná
timezone metadata; poslední možností je filesystem mtime. Normalizer v1 nemá
dost veřejných strukturovaných dat k opětovnému posouzení všech kandidátů.
Proto zachová vybranou hodnotu i její source a konflikt „EXIF vs. jiný čas“
označí jako **not observable**, nikoli jako vyřešený.

`technical` publikuje nullable source facts:

- společné: `manufacturer`, `camera_model`, `software`;
- image: `width`, `height`, `orientation`, `color_space`, `lens`,
  `focal_length_mm`, `exposure_seconds`, `aperture`, `iso`, `flash`, `gps`
  (`{latitude, longitude}` pouze když jsou obě souřadnice dostupné);
- video: `container`, `duration_seconds`, `width`, `height`, `fps`,
  `video_codec`, `bitrate`, `rotation`, `audio_present`, `audio_codec`,
  `sample_rate`, `channels`.

Typy jsou částečně závislé na ExifTool výstupu: rozměry a expozice mohou být
JSON number nebo string. Normalizer smí bezpečně převést jen hodnoty, které lze
bezeztrátově validovat; jinak zachová hodnotu ve `raw_value`/conflict evidence a
efektivní typed field nechá null. FFprobe duration/fps jsou `number | null`,
bitrate/sample rate `integer | null`.

`stages.metadata` obsahuje `processor_version`, `config_fingerprint`, `status`,
`finished_at`, `output`, `error_code`. Jde o stav ingest artefaktu, ne registry
ostatních procesorů. Chybějící metadata file nelze vydávat za prázdná metadata.

### 2.2 Session Grouper v1

**IMPLEMENTED.** Jde o aggregate processor. Cesta je:

```text
analysis/session-grouper/session-grouper-v1/
  <configuration_fingerprint>/<logical_input_fingerprint>.json
```

Obálka obsahuje `result_schema_version`, workspace identitu, `processor`,
`model: null`, úplnou `configuration`, její fingerprint, `input` s katalogovým
runem a logical fingerprintem, `created_at`, `status: success`, `error: null` a
`result`.

`result.sessions[]` publikuje:

- `session_id`, `start`, `end`, `time_basis: capture_local_wall_clock`,
  `operational_day`, `boundary_reason`, `confidence`;
- `asset_count`, mapu `media_types`;
- `assets[]`: `asset_id`, `sha256`, `media_type`, `captured_at`, `timestamp`
  (nebo null), `assignment_confidence`, `assignment_reason`.

Timestamp payload rozšiřuje ingest capture o `confidence` (`strong`, `medium`,
`low`, `unusable`). To je heuristika Grouperu vztahující se pouze ke kvalitě
časového podkladu. `result.unassigned[]` obsahuje `asset_id`, `sha256`,
`media_type`, `reason`, `timestamp`; pozorované důvody zahrnují
`asset_unavailable`, `missing_capture_timestamp` a
`filesystem_fallback_disabled`. `result.summary` obsahuje tři počty.

Procesor nepíše durable failed envelope pro chybu celého běhu; neexistující
přesná cesta znamená, že požadovaný aggregate výsledek není publikován. Více
validních výsledků je pro současný Media Desk explicitně `ambiguous`, nikoli
podklad k merge.

### 2.3 Video Keyframe Extractor v1

**IMPLEMENTED na auditovaném HEAD; lokální změny UNVERIFIED.** Per-asset cesta:

```text
analysis/video-keyframes/video-keyframes-v1/
  <configuration_fingerprint>/<sha-prefix>/<sha256>.json
```

Obálka obsahuje standardní identity a provenance, úplnou `configuration`, model
OpenCLIP, `created_at`, `status`, `error`, `result`. Při success je `result`:

- `source`: `source_version_id`, `relative_path`;
- `sampling`: `duration_s`, `interval_s`, `sample_count`;
- `coverage_similarity`;
- neprázdné `keyframes[]`.

Každý keyframe má `keyframe_id`, workspace-relative `location`, `timestamp_s`,
source video identity, processor/model/config fingerprint, `representation`
(`format`, `width`, `height`, `color_space`) a `coverage`
(`candidate_sample_index`, `member_sample_indices`, `member_count`).

Při failure je `status: failed`, `error: {code, message, diagnostics}` a
`result: null`. Nedostupný source se takto publikuje; reuse vyžaduje kompletní
success envelope i existenci všech JPEGů. Více platných keyframe fingerprintů
je downstream víceznačnost a musí se vyřešit explicitní konfigurací.

### 2.4 Vision Processor v1

**IMPLEMENTED.** Vision analyzuje jeden `image_preview` nebo jeden
`video_keyframe`; video tedy může mít více samostatných výsledků. Cesta zahrnuje
Vision fingerprint, asset SHA, input kind a u keyframu i jeho keyframe
fingerprint a ID.

Success envelope navíc obsahuje `input_kind`, přesný `input` provenance a
`timing`. `result` má `attempts[]` s raw odpovědí a validation errors a jediný
canonical objekt `vision`. Failure (`INVALID_MODEL_RESULT` nebo runtime chyba)
zachová attempts, `vision: null`, structured error a timing.

Canonical `vision` je closed schema: všech osm polí je povinných a další jsou
zakázána.

| Pole | Skutečný typ | Kvalita/omezení |
|---|---|---|
| `scene` | string | volný modelový text, bez confidence |
| `people.approx_count` | non-negative integer nebo null | odhad Vision, nikoli Faces count |
| `people.crowd` | boolean | inference bez confidence |
| `activities[]` | string[] | trim + odstranění prázdných/identických duplicit |
| `objects[]` | string[] | totéž |
| `environment[]` | string[] | totéž |
| `visual_attributes[]` | string[] | totéž |
| `tags[]` | string[] | totéž |
| `description` | string | volný modelový text, bez confidence |

Technická normalizace pouze trimuje stringy, odstraňuje prázdné a přesně
duplicitní položky a bezpečně převádí stringové count/bool. Nedělá překlad,
synonyma, taxonomii ani kalibraci. Vision v1 nevydává per-field ani per-label
confidence. Raw attempts jsou audit evidence, ne normalizované sémantické pole
pro UI či vyhledávání.

Loader rozlišuje input issues `MISSING_IMAGE_PREVIEW`,
`MISSING_KEYFRAME_RESULT`, `INVALID_KEYFRAME_RESULT` a
`AMBIGUOUS_KEYFRAME_RESULT`, ale tyto issues nejsou samostatně perzistentním
processor artefaktem. Normalizer proto jejich význam musí odvodit jen z
veřejného snapshotu a explicitně zvoleného keyframe fingerprintu.

### 2.5 Faces Processor v1 a anonymous clustering

**IMPLEMENTED.** Faces používá stejné `image_preview` / `video_keyframe` inputy
a obdobnou cestu. Success `result` obsahuje `image {width, height, color_order:
BGR}` a `faces[]`. Prázdné `faces: []` je platný, skutečně prázdný výsledek.

Každý face record má:

- `face_id` (`face-0000` atd.) a input provenance;
- integer `bbox {x,y,width,height}` v souřadnicích analyzovaného preview/keyframu;
- detector `confidence` v rozsahu threshold–1;
- pět landmarků (`right_eye`, `left_eye`, `nose_tip`, `right_mouth`,
  `left_mouth`) s číselnými `x/y`;
- L2-normalized 256D `embedding`.

Failure má `status: failed`, `{code,message}` a `result: null`. Faces input
issues mají stejné kódy jako Vision a nejsou samostatně perzistentní.

Clustering je zvláštní aggregate výstup pod `faces-clustering-v1`. Obálka
obsahuje cluster config fingerprint, `logical_input_fingerprint` a přesný
`faces_configuration_fingerprint`. `result` obsahuje `face_count` a
`clusters[]`: `cluster_id`, `status` (`core` nebo singleton `uncertain`),
`member_count`, `members[]` s asset/input/face identitou, cestou na Faces
result a provenance. Cluster není osoba a `core` není potvrzená identita ani
confidence.

Pro Normalizer v1 jsou bezpečně použitelné: počet detekcí na jednotlivých
visual inputs, detector confidence jako lokální metrika detekce a anonymní
cluster references. Embeddings, landmarky a boxy se nemají kopírovat do
asset-level read modelu; zůstanou dostupné v originálním processor artefaktu.

### 2.6 Media Desk v1.4 a user data

**IMPLEMENTED.** Media Desk načítá katalog, metadata a validní success výsledky
do `WorkspaceSnapshot` v paměti. Asset dnes obsahuje technická data, preview,
original reference, sessions, seznam všech Vision/Faces results a face cluster
references. Detail ukazuje Vision description a počet Faces; sémantické
atributy nejsou součástí filtrů. Více validních Session Grouper výsledků je
`ambiguous`. Video preview vyžaduje explicitní keyframe fingerprint, pokud je
validních konfigurací více.

Host-local Media Desk JSON schema 2 obsahuje `workspace_id`, `catalog_names`,
`display_names`, `events`, `manual_assignments`, monotónní `revision` a
`provenance_projection`. Událost má stabilní ID, název, session IDs a intervaly
`[start,end)`; ruční assignment assetu má prioritu. Data jsou atomicky uložena
mimo workspace a chráněna revision checkem. To jsou skutečné user assertions,
ale nejsou přenositelným processor outputem.

## 3. Návrh NormalizedAsset v1

### 3.1 Dva kontrakty: přenositelný artefakt a efektivní view

`NormalizedAsset v1` je přenositelný immutable artefakt Normalizeru. Obsahuje
jen to, co lze reprodukovat z veřejných workspace souborů. `EffectiveAssetView
v1` vzniká až v Media Desk připojením host-local user assertions. User data se
nikdy nekopírují do processor namespace.

```text
NormalizedAsset v1 (workspace, rebuildable)
  source_facts + machine_inferences + provenance + completeness
                           \
                            + Media Desk user assertions (host-local, revisioned)
                           /
EffectiveAssetView v1 (in-memory presentation/index view)
```

### 3.2 Processor envelope a snapshot manifest

Navržené umístění:

```text
analysis/normalizer/normalizer-v1/
  <configuration_fingerprint>/<input_set_fingerprint>/
    manifest.json
    assets/<sha-prefix>/<sha256>.json
```

`manifest.json` atomicky zpřístupní celý snapshot až po publikaci všech asset
souborů. Obsahuje schema/contract/workspace identity, úplnou canonical config,
seznam přesně vybraných upstream processorů a fingerprintů, katalog identity,
hash každého skutečně čteného JSON vstupu, sorted asset IDs, summary a status.
Manifest se publikuje jako poslední readiness point. Bez validního manifestu je
adresář nekompletní.

Per-asset envelope:

| Pole | Typ | Povinnost |
|---|---|---|
| `result_schema_version` | integer, vždy `1` | required |
| `workspace_contract_version` | integer, vždy `1` | required |
| `workspace_id` | string | required |
| `asset_id`, `sha256` | canonical strings | required |
| `processor` | `{name:"normalizer",version:"normalizer-v1"}` | required |
| `model` | null | required |
| `configuration_fingerprint` | SHA-256 | required |
| `input_set_fingerprint` | SHA-256 | required |
| `created_at` | ISO-8601 UTC | required, provozní metadata |
| `status` | `success \| failed` | required |
| `error` | object nebo null | required |
| `result` | NormalizedAsset object nebo null | required |

`created_at` nevstupuje do žádného fingerprintu a nemění semantiku výsledku.
JSON se serializuje UTF-8, sorted keys, canonical separators pro hashování a
publikuje atomic replace.

### 3.3 Pole `result`

Následující model je normativní návrh v1. Pole označená `required nullable`
musí existovat, ale mohou být null; díky tomu consumer rozliší známou absenci
hodnoty od chybějícího/neplatného kontraktu.

#### `identity` — source facts

| Pole | Typ/povinnost | Zdroj a pravidlo |
|---|---|---|
| `asset_id` | string, required | katalog; musí odpovídat envelope |
| `sha256` | string, required | katalog |
| `media_type` | enum, required | katalog |
| `size_bytes` | integer, required | katalog |
| `format` | string/null, required nullable | preferovat `metadata.detected.format`, fallback katalog; oba kandidáty zachovat v provenance |
| `mime_type` | string/null, required nullable | stejné pravidlo |
| `availability` | enum, required | katalog snapshot, ne živý I/O |
| `sources` | array, required | stabilně řadit `relative_path,status,source_version_id`; nic nepřepisovat |

Konflikt `detected` vs katalog není chyba sám o sobě: `detected` je dokumentované
refinement. Obě hodnoty se uchovají jako evidence, effective fact je detected.

#### `technical` — source facts

Required objekt s výše inventarizovanými klíči. Klíče nerelevantní pro daný
media type se nevkládají do media-specific podobjektu; společné klíče jsou
required nullable. Rozměry po aplikaci orientace se neodvozují — ingest
publikuje pouze zdrojové width/height a orientation. `orientation_degrees` se
nezavádí, protože současná data mají nejednotný typ a význam.

Každá efektivní hodnota má `field_sources` entry. Příklad targetu:
`/technical/image/width`. Normalizer nezdvojuje source wrapper kolem každého
scalaru; provenance je centrální mapa, aby JSON zůstal čitelný.

#### `temporal`

| Pole | Typ | Klasifikace |
|---|---|---|
| `capture.datetime` | string/null | source fact vybraný ingestem |
| `capture.source` | string/null | source fact provenance |
| `capture.timezone_offset` | string/null | source fact |
| `capture.filesystem_fallback` | boolean | source fact/policy marker |
| `capture.quality` | `source_timestamp \| filesystem_fallback \| missing` | deterministická interpretace Normalizeru |
| `session_candidates[]` | array | machine inference ze zvoleného Session Grouper resultu |

Session candidate zachová `session_id`, `start/end`, `operational_day`,
`boundary_reason`, session `confidence`, member `assignment_confidence` a
`assignment_reason` odděleně. Session není event.

#### `semantic` — machine inferences

```text
semantic.observations[]
  input.kind / input.id / keyframe_fingerprint / timestamp_s
  vision_configuration_fingerprint
  scene, people, activities, objects, environment,
  visual_attributes, tags, description
```

Pozorování se řadí podle `(input.kind, keyframe_fingerprint, input.id)`; u videa
se neslučují popisy ani počty lidí. `semantic.facets` jsou pouze přesné uniony
listových polí po Unicode trimu, odstranění empty a deduplikaci casefold key;
první stabilně seřazená původní podoba zůstane display value. `scene` a
`description` se do facety nepřevádějí. Facety mají provenance
`derivation: exact_union_v1` a nejsou source facts.

#### `people` — machine inferences

| Pole | Typ | Pravidlo |
|---|---|---|
| `face_observations[]` | array | pro každý visual input `detected_count` a volitelně min/max detector confidence |
| `detected_face_count` | integer/null | image: počet z jediného inputu; video: null, protože součet keyframů by dvojitě počítal osoby |
| `anonymous_cluster_refs[]` | array | cluster ID/status a přesné member refs pro tento asset |
| `vision_people_observations[]` | array | zachovat `approx_count/crowd` odděleně od Faces |

Faces count a Vision approx count se nikdy nepovažují za konflikt stejného
faktu: měří jiné věci a Vision navíc popisuje konkrétní keyframe.

#### `event`

Přenositelný artefakt v1 má pouze:

```json
{"machine_candidates": [], "user_assertion_available": false}
```

Prázdný seznam je skutečně prázdný výsledek: žádný existující procesor event
candidate neprodukuje. Session associations patří do `temporal`, nikoli sem.
Media Desk `EffectiveAssetView` doplní `event.user_assertion` ze své revisioned
evidence (`event_id`, `name`, `assignment_kind: manual|interval`, relevantní
session/interval). Boolean v portable artefaktu pouze sděluje, že Normalizer
user store nečetl; nesmí se interpretovat jako „uživatel nic neurčil“.

#### `quality`

V1 je required objekt:

```json
{"technical_assessment": null, "status": "not_analyzed"}
```

Projekt nemá Quality processor. Resolution, duration ani presence of preview
se nesmí vydávat za celkové quality score.

#### `provenance`

`field_sources` je mapa JSON Pointer targetu na ordered array evidence:

```json
{
  "/temporal/capture/datetime": [
    {
      "layer": "source_fact",
      "source": "metadata/assets/ab/...json",
      "source_pointer": "/capture/datetime",
      "processor": {"name": "media-ingest", "version": "metadata-v2"},
      "configuration_fingerprint": "normalized-v1",
      "observed_value": "2026-09-26T21:18:02.738+02:00",
      "selection": "selected"
    }
  ]
}
```

Machine evidence navíc uvádí upstream `result_schema_version`, model,
configuration fingerprint, input provenance a relativní result location.
`confidence` se přidá pouze tam, kde upstream skutečně hodnotu poskytuje, a
vždy s `confidence_kind` (`timestamp_quality`, `face_detection_score`). Kde
confidence neexistuje, klíč chybí; nepoužívá se `0` ani odhad.

#### `completeness`

| Pole | Typ | Význam |
|---|---|---|
| `analyses` | mapa processor → status record | stav přesně požadované konfigurace |
| `missing_fields[]` | JSON Pointer[] | očekávaná, ale null/neznámá data |
| `conflicts[]` | structured array | kandidáti, policy a resolution |
| `warnings[]` | structured array | degradace bez konfliktu |
| `source_available` | boolean | z katalogového snapshotu |

Status vocabulary pro každý processor/input:

- `success_nonempty` — validní success s alespoň jedním výsledkem;
- `success_empty` — validní success a legitimně prázdný výsledek, např.
  `faces: []`;
- `not_analyzed` — očekávaná přesná result path chybí;
- `failed` — validní failed envelope;
- `not_applicable` — procesor/input pro tento media type nedává smysl;
- `input_unavailable` — chybí preview, zvolený keyframe nebo source asset;
- `ambiguous` — chybí explicitní volba a existuje více kandidátů; MVP v tomto
  stavu nesmí publikovat success snapshot;
- `invalid` — soubor existuje, ale neprojde kontraktem;
- `unknown` — veřejná data nestačí k přesnější klasifikaci.

`not_analyzed` se nikdy nepřevádí na empty. `failed` zachová error code/message,
ale nepromítne partial model output do semantic facts.

### 3.4 Ilustrační JSON — image asset

Ukázky jsou zkrácené; normativní seznam required fields je výše.

```json
{
  "result_schema_version": 1,
  "workspace_contract_version": 1,
  "workspace_id": "5d59f6c8-8fe0-4fd0-a605-7c0d9b9e5cec",
  "asset_id": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "processor": {"name": "normalizer", "version": "normalizer-v1"},
  "model": null,
  "configuration_fingerprint": "1111111111111111111111111111111111111111111111111111111111111111",
  "input_set_fingerprint": "2222222222222222222222222222222222222222222222222222222222222222",
  "created_at": "2026-10-26T12:00:00+00:00",
  "status": "success",
  "error": null,
  "result": {
    "identity": {
      "asset_id": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      "sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      "media_type": "image",
      "size_bytes": 4819203,
      "format": "JPEG",
      "mime_type": "image/jpeg",
      "availability": "available",
      "sources": [{"source_version_id": "0cf1…", "relative_path": "2026/photo.jpg", "status": "active"}]
    },
    "technical": {
      "common": {"manufacturer": "Canon", "camera_model": "EOS R6", "software": null},
      "image": {"width": 5472, "height": 3648, "orientation": 1, "color_space": "sRGB", "lens": null, "focal_length_mm": 35, "exposure_seconds": 0.008, "aperture": 2.8, "iso": 400, "flash": null, "gps": null}
    },
    "temporal": {
      "capture": {"datetime": "2026-09-26T21:18:02.738+02:00", "source": "Composite:SubSecDateTimeOriginal", "timezone_offset": "+02:00", "filesystem_fallback": false, "quality": "source_timestamp"},
      "session_candidates": [{"session_id": "session-18ab…", "confidence": "strong", "assignment_confidence": "strong", "assignment_reason": "trusted_timestamp_sequence"}]
    },
    "semantic": {
      "observations": [{"input": {"kind": "image_preview", "id": "image-preview"}, "vision_configuration_fingerprint": "3333333333333333333333333333333333333333333333333333333333333333", "scene": "outdoor concert", "people": {"approx_count": 4, "crowd": false}, "activities": ["performing music"], "objects": ["guitar"], "environment": ["outdoors"], "visual_attributes": ["night"], "tags": ["concert"], "description": "Four people perform on an outdoor stage."}],
      "facets": {"activities": ["performing music"], "objects": ["guitar"], "environment": ["outdoors"], "visual_attributes": ["night"], "tags": ["concert"]}
    },
    "people": {"detected_face_count": 3, "face_observations": [{"input_id": "image-preview", "detected_count": 3, "detector_confidence": {"min": 0.81, "max": 0.97}}], "anonymous_cluster_refs": [], "vision_people_observations": [{"input_id": "image-preview", "approx_count": 4, "crowd": false}]},
    "event": {"machine_candidates": [], "user_assertion_available": false},
    "quality": {"technical_assessment": null, "status": "not_analyzed"},
    "provenance": {"field_sources": {}},
    "completeness": {"source_available": true, "analyses": {"vision": {"status": "success_nonempty"}, "faces": {"status": "success_nonempty"}, "quality": {"status": "not_analyzed"}}, "missing_fields": [], "conflicts": [], "warnings": []}
  }
}
```

### 3.5 Ilustrační JSON — video bez analýzy

```json
{
  "asset_id": "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
  "result": {
    "identity": {"asset_id": "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb", "sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb", "media_type": "video", "availability": "available", "size_bytes": 90313211, "format": "MP4", "mime_type": "video/mp4", "sources": []},
    "semantic": {"observations": [], "facets": {"activities": [], "objects": [], "environment": [], "visual_attributes": [], "tags": []}},
    "people": {"detected_face_count": null, "face_observations": [], "anonymous_cluster_refs": [], "vision_people_observations": []},
    "event": {"machine_candidates": [], "user_assertion_available": false},
    "quality": {"technical_assessment": null, "status": "not_analyzed"},
    "provenance": {"field_sources": {}},
    "completeness": {
      "source_available": true,
      "analyses": {
        "video_keyframes": {"status": "not_analyzed"},
        "vision": {"status": "input_unavailable", "reason": "selected_keyframes_not_available"},
        "faces": {"status": "input_unavailable", "reason": "selected_keyframes_not_available"}
      },
      "missing_fields": [],
      "conflicts": [],
      "warnings": []
    }
  }
}
```

### 3.6 Ilustrační user assertion overlay

Toto není součást processor artefaktu; jde o vstup Media Desk efektivního view:

```json
{
  "schema_version": 1,
  "workspace_id": "5d59f6c8-8fe0-4fd0-a605-7c0d9b9e5cec",
  "asset_id": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "target": "/event/user_assertion",
  "operation": "set",
  "value": {"event_id": "event-9f…", "name": "COVER INCI", "assignment_kind": "manual"},
  "source": {"owner": "media-desk", "revision": 14}
}
```

Presentation precedence je `user_assertion > machine_inference > source_fact`
pouze pro stejný explicitní target. Původní vrstvy se nemažou. Uživatel například
může určit event, ale tím nepřepisuje Session Grouper session.

## 4. Provenance a pravidla řešení konfliktů

### 4.1 Obecná pravidla

1. Kandidáty se vždy zachovají v provenance; žádný silent overwrite.
2. Automatické pravidlo smí vybrat hodnotu jen tehdy, když je deterministické a
   dokumentované pro konkrétní field, například detected format před katalogem.
3. User assertion má prezentační prioritu pouze na svém targetu a nemění
   processor artefakt.
4. Výsledek se stabilně řadí podle canonical identity, nikdy podle filesystem
   enumeration order nebo `created_at`.
5. Confidence se nepřenáší mezi typy a neagreguje do asset score.

### 4.2 Požadované konfliktní situace

| Situace | Chování v1 |
|---|---|
| EXIF datum odporuje jinému času | Ingest už publikoval vybraný čas. Normalizer jej zachová; bez strukturovaných kandidátů označí audit capability `not_observable`. Raw metadata v1 neparsuje. Rozšíření ingest contractu je ADR. |
| Více Vision běhů | Normalizer config musí uvést požadovaný Vision fingerprint. Jiný fingerprint zůstává historický kandidát. Bez volby a s více kandidáty `ambiguous`, žádný success snapshot. |
| Více keyframe fingerprintů | Povinná explicitní volba pro video-dependent Vision/Faces. Žádný arbitrární first/newest. |
| AI event vs user event | V1 žádný AI event nemá. Budoucí machine candidate zůstane vedle user assertion; efektivní event je user assertion. |
| Změna processor config | Nový upstream fingerprint znamená jinou Normalizer config a nový snapshot. Starý zůstává čitelný jako historie. |
| Analýza selže | `failed`, structured upstream error v provenance; partial Vision odpověď se nepoužije jako inference. |
| Analýza neproběhne | `not_analyzed`, pokud je input applicable a přesná result path chybí. |
| Platný prázdný Faces výsledek | `success_empty`; count 0 pro konkrétní input. |
| Uživatel změní označení | Media Desk vytvoří novou revision; efektivní view použije novou assertion. Normalizer rebuild se user store nedotýká. Historii změn dnes Media Desk nepersistuje, pouze current state + revision; audit log je budoucí ADR. |
| Source soubor není dostupný | `identity.availability` podle katalogu a `source_available:false`; metadata a již publikované analýzy mohou zůstat použitelné. Živou dostupnost Media Desk ověřuje až per request. |

### 4.3 Konflikt record

Každý conflict má stabilní `code`, `target`, ordered `candidates[]`, `resolution`
(`selected`, `unresolved`, `user_override`) a `policy`. Neobsahuje volný údaj
„confidence“ bez typu. Příklad:

```json
{
  "code": "MULTIPLE_VISION_CONFIGURATIONS",
  "target": "/semantic/observations",
  "candidates": [
    {"configuration_fingerprint": "3333…", "result_location": "analysis/vision/…"},
    {"configuration_fingerprint": "4444…", "result_location": "analysis/vision/…"}
  ],
  "resolution": "unresolved",
  "policy": "explicit_configuration_required"
}
```

## 5. Fingerprint, lifecycle a rebuild

### 5.1 `configuration_fingerprint`

Lowercase SHA-256 canonical JSON recipe obsahující minimálně:

- processor/result schema version a `normalization_rules: normalized-asset-v1`;
- workspace contract major `1`;
- explicitní upstream processor versions a fingerprints;
- explicitní Video Keyframes fingerprint;
- session logical result selection policy;
- exact-facet recipe version;
- typed conversion policy version;
- `include_unavailable_assets` policy.

Model names se nepřebírají ručně: validují se proti přesně vybranému upstream
envelope a jejich význam je tak pokryt upstream fingerprintem i input hashem.

### 5.2 `input_set_fingerprint`

Lowercase SHA-256 canonical JSON obsahující:

- `workspace_id`, contract version;
- SHA-256 bytes `workspace.json` a zvoleného catalog JSON;
- pro každý asset identity a SHA-256 bytes metadata dokumentu nebo explicitní
  sentinel `missing`;
- relativní path a SHA-256 bytes každého zvoleného Session/Keyframe/Vision/Faces/
  cluster resultu, včetně validních failed envelopes;
- explicitní sentinel pro každý očekávaný, ale chybějící input.

Timestamps souborů ani absolutní host paths do hashe nevstupují. Tím je rebuild
na jiném hostu deterministický. Zahrnutí input bytes znamená, že opravený obsah
na stejné upstream cestě nevytvoří silent overwrite Normalizer historie.

### 5.3 Lifecycle

1. Validovat workspace entry point a katalog.
2. Validovat explicitní upstream selection; při ambiguity skončit bez publikace.
3. Sestavit read-only plan a oba fingerprinty.
4. Pokud existuje kompletní validní manifest se stejnými fingerprinty a všemi
   asset hashes, reuse bez přepisu.
5. Jinak zapisovat asset JSON do sibling staging directory.
6. Fsync soubory, atomicky přesunout snapshot directory a jako poslední
   publikovat/validovat `manifest.json`.
7. Nikdy automaticky nemaž starší input snapshots. Retention není scope v1.

Pád před manifestem zanechá nepublikovaný staging, který consumer ignoruje.
Opakování nad totožnými inputs vytvoří totožný `result` (kromě envelope
`created_at`, který při validním reuse zůstane původní). Rebuild nesmí číst ani
zapisovat Media Desk user data.

### 5.4 Aktuální versus historické výsledky

„Aktuální“ není nejnovější `created_at`. Je to výsledek přesně požadované
Normalizer konfigurace a aktuálně vypočteného input set fingerprintu. Consumer:

- s explicitní dvojicí fingerprintů načte pouze tuto dvojici;
- bez explicitního input fingerprintu může vybrat výsledek pouze tehdy, když je
  pro požadovanou config právě jeden validní snapshot odpovídající aktuálním
  vstupům;
- jinak hlásí `ambiguous/stale` a nevybírá podle času.

## 6. Architektonické začlenění

### 6.1 Ownership a hranice

Normalizer:

- čte pouze `workspace.json`, katalog, per-asset metadata a dokumentované
  processor outputs;
- zapisuje pouze `analysis/normalizer/normalizer-v1/`;
- neimportuje ingest internals a neotevírá SQLite;
- nečte originální media ani host-local user data;
- nevytváří preview, keyframe, embedding ani nový AI výstup;
- ověřuje path confinement a symlink escape stejně přísně jako existující
  consumers;
- publikuje atomic snapshot.

Tím může být čistě odvozeným procesorem bez trvalého mutable stavu. Jeho jediný
„stav“ jsou immutable výsledky/reuse artefakty; scheduling queue není potřeba.

### 6.2 Potřebná rozhodnutí

Před implementací doporučuji schválit ADR-N1:

- processor name/version/path layout;
- manifest-last snapshot publication;
- explicitní upstream fingerprint selection;
- oddělení portable normalized artefaktu a Media Desk user overlay;
- input hashing a retention policy „nezmazat automaticky“.

Workspace contract major se měnit nemusí: stávající contract výslovně dovoluje
processor-defined output pod `analysis/<processor>/`. Nový dokumentovaný
Normalizer contract je additive processor contract. Pokud by však měl být
Normalizer přidán do `workspace.json`, ingest katalogu nebo ingest stages,
šlo by o změnu veřejného ownership a vyžadovalo samostatný ADR (a případně nový
contract major).

Přenositelná synchronizace user assertions by změnila dnešní accepted
host-local ownership Media Desk a vyžaduje samostatné schema/ownership/backup
ADR. Pro v1 se nenavrhuje.

## 7. Integrace Media Desk

### 7.1 Minimální integrace

Media Desk dostane volitelnou konfiguraci Normalizer
`configuration_fingerprint` + případně `input_set_fingerprint`. Při startu:

1. načte současný workspace snapshot jako dnes;
2. validuje jeden Normalizer manifest proti workspace ID, contract version,
   config a aktuálním inputs;
3. streamově načte per-asset NormalizedAsset JSON a připojí jej k existujícímu
   `Asset` podle přesného `asset_id`;
4. připojí existující `UserLibraryData` jako user assertion overlay;
5. v `LibraryIndex` vytvoří in-memory inverted maps pro exact facets a
   completeness statuses.

To je jednoduchá read-only indexační vrstva, nikoli nový databázový systém.
Současný Media Desk již drží snapshot a index v paměti; persistentní SQLite by
zdvojovala lifecycle, locking, migration a backup problém bez důkazu, že je pro
v1 potřeba.

### 7.2 UI/API

- Detail: sekce „Sjednocená metadata“ s badges **Zdroj**, **AI**, **Uživatel** a
  rozbalitelným provenance pro hodnotu.
- Semantic: zobrazit jednotlivé observations; u videa uvést keyframe ID/time.
  Nezobrazovat jejich union jako jeden jistý popis celého videa.
- People: Faces count a Vision estimate vedle sebe s rozdílnými popisky.
- Event: efektivní user event z dnešní Media Desk evidence; session stále jako
  časová relace.
- Filters: exact `activities`, `objects`, `environment`, `visual_attributes`,
  `tags`; dále `analysis_status`, `has_conflict`, `missing_field`,
  `source_available`.
- Diagnostic list: přednastavený filter `failed|not_analyzed|ambiguous|invalid`
  a conflicts.
- API: additive `normalized`, `semantic_facets`, `completeness_summary` v detailu;
  list endpoint vrací jen kompaktní facety/statusy, nikoli celý provenance.
- Bulk edits: pouze budoucí Media Desk user assertions. Normalizer processor
  outputs z UI nikdy neupravovat.

Současné display names, events, filmstrip, Working Library, pagination, lazy
video a original mapping zůstanou beze změny. Query/search může v MVP zahrnout
exact facet strings; full-text ranking ani embedding search se nezavádí.

### 7.3 Výkon

Pro 10k assets se načítají malé per-asset JSON soubory jednou při startupu.
Manifest poskytne count/hash a umožní odmítnout neúplný snapshot před renderem.
Index používá `dict[str, bitmap/set[int]]` nebo sorted integer lists; konkrétní
reprezentaci zvolit až po benchmarku. Povinná akceptace je měřit startup, peak
RSS a filter latency na existujícím 10k synthetic benchmarku. Pokud data ukážou
nepřijatelnou spotřebu, další krok může být compact generated read index uvnitř
Normalizer namespace; nová DB až po samostatném měření a ADR.

## 8. Oddělený návrh Enrichment

Enrichment není součást Normalizer v1 a jeho výstupy nesmí být zapsány jako
source facts.

| Schopnost | Deterministická pravidla | Vyžaduje AI/model nebo kurátorovaný zdroj |
|---|---|---|
| Exact trim/dedupe/casefold key | ano; už v Normalizer facets | ne |
| Synonyma (`car`/`automobile`, české varianty) | pouze s verzovaným schváleným slovníkem | otevřené synonym discovery ano |
| CZ/EN normalizace | pouze s verzovaným bilingual dictionary a zachováním originálu | volný překlad ano |
| Širší kategorie z objektů | s explicitní verzovanou taxonomií (`guitar → musical instrument`) | taxonomii může navrhnout AI, ale musí být oddělená inference |
| Event candidate podle času | deterministické intervalové návrhy možné ze sessions | obsahové pojmenování/porovnání vyžaduje další model nebo ruleset |
| Přenos mezi keyframy | exact provenance-aware union lze pravidlem | tvrzení o celém videu vyžaduje temporal model/policy |
| Missing-information detection | ano z completeness statuses | návrh chybějící hodnoty může vyžadovat AI |
| Semantic search | exact/inverted term search ano | embeddings, multilingual ranking a reranking jsou samostatný processor |

Doporučený budoucí processor `enrichment-v1` čte immutable Normalizer snapshot,
má vlastní config/input fingerprints a produkuje oddělené
`machine_inferences`. Každé pravidlo nese `rule_id`, version, input terms a
output term. AI výstup nese model/prompt/config provenance. Normalizer může v
budoucí schema version tyto výsledky zprostředkovat, nesmí je vydávat za fakta.

## 9. Minimální MVP a implementační kroky

### MVP scope

MVP zahrnuje ingest facts, capture, technical, jednu explicitní Session Grouper
konfiguraci, jeden explicitní Video Keyframes fingerprint, jednu explicitní
Vision konfiguraci, jednu Faces konfiguraci a volitelně jeden Faces clustering
výsledek. Nevytváří event candidates, quality score, synonyma, překlady,
taxonomii, embeddings index, full-text engine ani persistentní DB.

### Samostatné testovatelné kroky

1. **ADR a JSON schemas.** Schválit ADR-N1, `manifest.schema.json` a
   `normalized-asset.schema.json`. Hotovo, když examples validují a negativní
   fixtures odmítnou missing/extra/nesprávně typed required fields.
2. **Read-only contract loader.** Načíst veřejný workspace a explicitní upstream
   selections bez importu ingest/processor internals. Hotovo, když test hlídá
   nulový přístup k SQLite/originálům a pokrývá path traversal/symlink escape.
3. **Input inventory a fingerprint.** Canonical hash se sentinely missing.
   Hotovo, když reverse filesystem order dává stejný hash a změna jediného byte
   vstupu jiný hash.
4. **Ingest fact normalization.** Identity/capture/technical/source provenance.
   Hotovo pro image/video, nulls, unavailable asset, metadata missing a detected
   refinement conflict.
5. **Session projection.** Explicitně jeden aggregate result; membership a
   unassigned reason. Hotovo, když multiple candidates selžou jako ambiguous a
   session není označena eventem.
6. **Vision projection.** Per-input observations a exact facets. Hotovo, když
   video keyframy zůstanou oddělené, failed/absent/invalid/empty se nerozmažou a
   žádné confidence není vytvořeno.
7. **Faces projection.** Per-input counts, typed detector score a cluster refs.
   Hotovo, když `faces: []` je success_empty a video asset total zůstane null.
8. **Atomic publisher/reuse.** Staging + manifest last. Hotovo, když fault
   injection v každém publish bodu nikdy nezpřístupní partial snapshot a
   totožný rerun reuse-nepřepisuje.
9. **Media Desk read adapter.** Volitelné načtení snapshotu, detail a compact API.
   Hotovo, když chybějící Normalizer zachová dnešní UI beze změny a invalidní
   snapshot se zobrazí jako diagnostika, ne crash.
10. **Facety a completeness filters.** In-memory index. Hotovo, když pagination
    a snapshot-bound cursors zůstanou stabilní a lze vyfiltrovat missing/conflict.
11. **User overlay.** Mapovat existující events/manual assignments do
    EffectiveAssetView bez změny user JSON schema. Hotovo, když manual assignment
    přebije intervalovou prezentaci a Normalizer rebuild nechá user file
    byte-for-byte nezměněný.
12. **Dokumentace a compatibility suite.** Aktualizovat `README`, system overview,
    architecture, workspace processor docs, Media Desk STATUS/ARCHITECTURE/
    DECISIONS/ROADMAP a user docs. Hotovo, když odkazy/startup příklady platí a
    test zachová všechny producer/upstream soubory content/size/mtime.

## 10. Rozhodnutí N1/N2 a odložené otázky

### Vyřešeno implementací N1/N2

1. **ADR-N1:** processor contract, path layout, manifest-last a dvojice
   config/input fingerprints jsou přijaty.
2. **Selection UX:** N2 používá CLI fingerprint options; automatický newest je
   zakázán a Media Desk selection zůstává N3.
3. **User overlay boundary:** portable Normalizer user data nečte;
   `EffectiveAssetView` zůstává budoucí Media Desk-owned projekce.
4. **Typed EXIF conversions:** N1 používá uzavřený `safe-scalars-v1` allowlist;
   odmítnuté hodnoty zůstávají null s provenance warning.

### Neblokující / odložené

- Má budoucí ingest contract publikovat všechny capture-time kandidáty, aby šel
  odhalit EXIF/QuickTime conflict bez čtení opaque raw metadata? Vyžaduje ADR.
- Má Media Desk udržovat audit log historie user assertions, ne pouze current
  state a revision? Nová persistence/backup smlouva, mimo v1.
- Jaká retention platí pro historické Normalizer snapshots? V1 nic automaticky
  nemaže; cleanup/orchestrator je samostatný návrh.
- Exact facet display používá lexical minimum po `(casefold, original)` pro
  úplnou determinističnost.
- Normalizer zahrnuje unavailable assets; historická metadata a analýzy
  zůstávají použitelné a dostupnost je explicitní.
- Persistentní index/SQLite: **ne** bez benchmark evidence. Pokud bude potřeba,
  rozhodnout ownership, migrations, atomic refresh a backup samostatným ADR.

### Aktuální stav implementace

ADR-N1 i rozšíření N2 jsou schválené a implementované. Necommitnutá Video
Keyframes změna zůstává auditní nejistota, nikoli blokátor: N2 ji izoluje
explicitním fingerprintem a spoléhá pouze na stabilní veřejný v1 JSON kontrakt.

## 11. Evidence — kód, dokumentace a testy

Původní upstream audit vychází z HEAD uvedeného v záhlaví; u Video Keyframes
byl pro schválený kontrakt použit `git show HEAD:<path>`, nikoli lokálně změněný
obsah. N1/N2 evidence níže odpovídá aktuálnímu necommitnutému working tree.

### Autoritativní dokumentace

- [`docs/workspace-contract.md`](docs/workspace-contract.md) — veřejný contract,
  ownership, standardní result envelope, fingerprint/reuse a atomic replace.
- [`docs/architecture.md`](docs/architecture.md) a
  [`docs/system-overview.md`](docs/system-overview.md) — producer/consumer hranice;
  Normalizer N1/N2 je implementovaný, N3 je plánovaný.
- [`docs/media-ingest.md`](docs/media-ingest.md),
  [`docs/session-grouper.md`](docs/session-grouper.md),
  [`docs/video-keyframes.md`](docs/video-keyframes.md),
  [`docs/vision.md`](docs/vision.md), [`docs/faces.md`](docs/faces.md).
- [`docs/media-desk/STATUS.md`](docs/media-desk/STATUS.md),
  [`ARCHITECTURE.md`](docs/media-desk/ARCHITECTURE.md),
  [`DECISIONS.md`](docs/media-desk/DECISIONS.md),
  [`ROADMAP.md`](docs/media-desk/ROADMAP.md) — aktuální stav a accepted ownership;
  historický `CONTRACT.md` nebyl použit jako novější autorita.

### Implementace a relevantní funkce

- [`src/huhac_media/storage/contract.py`](src/huhac_media/storage/contract.py) —
  `export_asset_catalog`; [`storage/sidecars.py`](src/huhac_media/storage/sidecars.py)
  — `export_asset`; [`media/metadata.py`](src/huhac_media/media/metadata.py) —
  `MetadataExtractor._technical`; [`media/capture_time.py`](src/huhac_media/media/capture_time.py)
  — `select_capture_datetime`.
- [`src/session_grouper/contract.py`](src/session_grouper/contract.py) —
  `load_workspace`; [`grouping.py`](src/session_grouper/grouping.py) —
  `group_assets`; [`output.py`](src/session_grouper/output.py) —
  `input_fingerprint`, `build_payload`, `read_reusable_payload`.
- [`src/video_keyframes/contract.py`](src/video_keyframes/contract.py) — source
  selection; [`output.py`](src/video_keyframes/output.py) — `publish_keyframes`,
  `success_payload`, `failure_payload`, `read_reusable_result`;
  [`service.py`](src/video_keyframes/service.py) — SHA-256 source verification.
- [`src/vision/schema.py`](src/vision/schema.py) — exact closed schema,
  `validate_vision_result`, `technically_normalize`;
  [`contract.py`](src/vision/contract.py) — input/keyframe ambiguity;
  [`output.py`](src/vision/output.py) — success/failure/reuse envelope;
  [`service.py`](src/vision/service.py) — attempts, repair a failure handling.
- [`src/faces/contract.py`](src/faces/contract.py) — visual inputs/issues;
  [`output.py`](src/faces/output.py) — detector result validation a envelopes;
  [`service.py`](src/faces/service.py) — face serialization;
  [`clustering.py`](src/faces/clustering.py) — complete-link clusters, logical
  fingerprint a aggregate output.
- [`src/media_desk/contract.py`](src/media_desk/contract.py) — validace všech
  public processor outputs, ambiguity a snapshot;
  [`models.py`](src/media_desk/models.py) — dnešní Asset/WorkspaceSnapshot;
  [`index.py`](src/media_desk/index.py) — in-memory index;
  [`user_data.py`](src/media_desk/user_data.py) — schema 2, atomic write,
  revisions, events/manual assignments.
- [`src/normalizer/contract.py`](src/normalizer/contract.py),
  [`upstream.py`](src/normalizer/upstream.py),
  [`project.py`](src/normalizer/project.py), [`output.py`](src/normalizer/output.py)
  a [`service.py`](src/normalizer/service.py) — bezpečné public-contract načtení,
  N1/N2 projekce, fingerprinty, completeness a immutable snapshot publication.

### Test evidence a fixtures

- [`tests/integration/test_workspace_contract.py`](tests/integration/test_workspace_contract.py)
  a [`tests/integration/test_ingest.py`](tests/integration/test_ingest.py) —
  publikovaný katalog/metadata, availability a atomic behavior.
- [`tests/unit/test_metadata.py`](tests/unit/test_metadata.py) a
  [`tests/unit/test_capture_time.py`](tests/unit/test_capture_time.py) — přesná
  technická pole, typové převody a timestamp priority/fallback.
- [`tests/session_grouper/test_contract.py`](tests/session_grouper/test_contract.py),
  [`test_grouping.py`](tests/session_grouper/test_grouping.py) a
  [`test_session_cli.py`](tests/session_grouper/test_session_cli.py) — public-only
  reads, confidence, unassigned reasons, determinismus a reuse.
- [`tests/video_keyframes/test_keyframe_contract.py`](tests/video_keyframes/test_keyframe_contract.py),
  [`test_output.py`](tests/video_keyframes/test_output.py),
  [`test_service.py`](tests/video_keyframes/test_service.py) — envelopes,
  keyframe provenance, failures a exact reuse (auditována HEAD verze).
- [`tests/vision/test_schema.py`](tests/vision/test_schema.py),
  [`test_vision_contract.py`](tests/vision/test_vision_contract.py),
  [`test_vision_output.py`](tests/vision/test_vision_output.py),
  [`test_vision_service.py`](tests/vision/test_vision_service.py) — closed semantic
  schema, normalization, ambiguity, raw attempts, repair a durable failure.
- [`tests/faces/test_faces_contract.py`](tests/faces/test_faces_contract.py),
  [`test_faces_output_service.py`](tests/faces/test_faces_output_service.py),
  [`test_faces_clustering.py`](tests/faces/test_faces_clustering.py) — detector
  schema, zero/multiple detections, provenance, embeddings a anonymous clusters.
- [`tests/media_desk/test_media_desk_contract.py`](tests/media_desk/test_media_desk_contract.py),
  [`test_index.py`](tests/media_desk/test_index.py),
  [`test_working_library.py`](tests/media_desk/test_working_library.py) — current
  loading/filtering, ambiguity, host-local names/events, manual precedence a
  revision persistence.
- [`tests/normalizer/`](tests/normalizer/) — N1 source facts, N2 upstream
  kontrakty, per-keyframe projekce, exact facety, failure states, fingerprinty,
  reuse, fault injection a zákaz privátních vstupů.

### Kontrola dokumentace versus kód

- **Konzistentní:** workspace v1 ownership, SHA-256 identity, catalog/metadata
  shapes, processor namespaces, atomic result files, Vision schema, Faces
  anonymity, Session≠Event a Media Desk read-only workspace behavior.
- **Konzistentní stav:** Normalizer N1/N2 je **IMPLEMENTED**. N3 Media Desk
  adapter, Enrichment, Quality a semantic search jsou **ABSENT/PLANNED**.
- **Materiální lokální odchylka:** necommitnutá Video Keyframes změna upravuje
  default model a CLI selection. Byla oddělena jako **UNVERIFIED**; návrh se o ni
  neopírá.
- **Známé omezení kontraktu:** ingest metadata dokumentace popisuje nullable
  facts, ale některé ExifTool-derived values nejsou v kódu převedeny na jednotné
  scalar typy. Proto návrh nepředstírá silnější typovou jistotu a vyžaduje
  explicitní safe-conversion policy.

---

**Aktuální verdikt:** čistě odvozený Normalizer v1 má implementované N1 i N2.
Další samostatný milník je N3 Media Desk read adapter a user overlay; databáze,
nová inference a změny producer contracts zůstávají mimo schválený rozsah.
