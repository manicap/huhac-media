# MC-ADR-001 — Media Transfer a content-addressed Media Storage

**Stav:** PROPOSED / AWAITING APPROVAL

**Datum:** 2026-10-23

**Rozsah:** budoucí Media Transfer; MC1 se nemění

## Kontext a závazné vstupy

MC-D013 až MC-D016 stanovují neměnnost externích zdrojů, povinné převzetí před
Ingestem, zákaz publikace neověřených přenosů, obsahovou deduplikaci a oddělenou
evidenci provenience. Toto ADR navrhuje fyzický layout, persistence a recovery,
ale nezavádí implementaci.

## Ověřená kompatibilita se současným Ingestem

Audit aktuálního kódu a kontraktu potvrdil:

- Ingest rekurzivně skenuje `INPUT`, nenásleduje symlinky a ukládá jeho absolutní
  cestu jako katalogový `source_root` (`services/scanner.py`,
  `storage/contract.py`).
- Každý podporovaný soubor Ingest znovu plně hashne SHA-256 a deduplikuje assety
  podle obsahu. Connector proto nesmí obcházet ingest hash ani zapisovat jeho DB.
- Workspace contract v1 publikuje fyzickou relativní cestu pod Ingest `INPUT`.
  Neobsahuje pole pro původní Connector source ID, název nebo transfer run.
- Detekce nejprve používá signaturu a potom příponu. Některé formáty, zejména
  MTS/M2TS, potřebují podporovanou příponu; extensionless payload není obecně
  kompatibilní. CR3 je v první scanner fázi rozpoznán přes ISO-BMFF jako MP4 a
  spoléhá na pozdější metadata refinement i při příponě `.cr3`.
- Workspace může být uvnitř `INPUT` pouze jako explicitně vyloučený work root,
  nebo zcela mimo něj. Connector state a staging se proto nesmějí stát běžnou
  součástí skenovaného Media Storage.
- Ingest SQLite a Python API jsou privátní a nejsou integrační hranicí.

Cílený diagnostický běh nad současným `detect_media` doložil:

| Payload | Bez přípony | S příponou |
|---|---|---|
| JPEG signatura | JPEG image | JPEG image (`.jpg`) |
| transport-stream vzorek | unsupported | MTS video (`.mts`) |
| CR3-like `ftyp crx` | MP4 video | MP4 video (`.cr3`, před refinement) |

Současné scanner integrační testy prošly `3 passed`. Závěr je, že samotný
extensionless `<sha256>` není bezpečný layout. Je nutný verzovaný
**Ingest Compatibility Profile**, který určí bezpečnou kanonickou příponu a má
contract testy proti skutečné detekci Ingestu. Neznámý nebo nejednoznačný formát
se nesmí publikovat jako ingest-ready originál.

## Porovnávané fyzické varianty

| Kritérium | Content-addressed layout | Source-oriented layout |
|---|---|---|
| Příklad | `objects/sha256/ab/<hash>/payload.jpg` | `sources/<source-id>/<original/path>.jpg` |
| Fyzická deduplikace | přirozeně jeden objekt na hash | kopie duplikuje bajty; hardlink/reflink je FS-specifický |
| Kolize názvů | odstraněny z fyzického namespace | vyžadují escaping/přejmenování a case/Unicode politiku |
| Stabilita při rename zdroje | fyzický objekt se nemění | fyzická cesta se mění nebo uchovává historický název |
| Původní názvy/cesty | musí být v oddělené evidenci | částečně viditelné fyzicky, ale stále potřebují source ID a historii |
| Ingest v1 | kompatibilní s kanonickou příponou | přirozeně kompatibilní se zachovanou příponou |
| Opakovaný stejný obsah | ověřený no-op + nová source reference | nový path nebo FS-link; složitější souběh |
| Přenositelnost | běžné adresáře a soubory | hardlink/reflink varianta není přenositelná |
| Audit identity | cesta přímo obsahuje SHA-256 | identita vyžaduje stavovou databázi |

Source-oriented layout bez hardlinků nesplňuje fyzickou deduplikaci. Varianta s
hardlinky přidává platformní, zálohovací a NAS rizika a Ingest by viděl více
source paths pro stejné bajty. Doporučen je proto content-addressed layout;
původní názvy, cesty a historie se zachovají jako metadata, ne jako fyzické
názvy originálu.

## Navržené rozhodnutí

### 1. Fyzický objekt

Media Storage používá content-addressed namespace:

```text
<media-storage>/
  objects/sha256/<first-2-hex>/<64-hex>/payload.<canonical-suffix>
```

Adresář `<64-hex>` je identita objektu. Obsahuje právě jeden běžný payload
soubor, žádný manifest, lock ani dočasná data. `canonical-suffix` určí verzovaný
Ingest Compatibility Profile z ověřeného formátu; nikdy se nepřebírá jako
nedůvěryhodná cesta. Stejný hash nesmí vytvořit druhý fyzický payload.

Transfer SHA-256 má stejný algoritmus a textový tvar jako Ingest, ale Ingest jej
při samostatném běhu vždy nezávisle přepočítá a teprve on publikuje `asset_id`.

### 2. Staging a publication point

Staging je explicitní `transfer-work-root` mimo Media Storage i workspace, ale
na stejném filesystemu jako Media Storage:

```text
<transfer-work-root>/staging/<run-id>/<item-id>.partial/
  payload.<canonical-suffix>
```

Povinné pořadí:

1. pod library-wide writer lockem vytvořit run/item v Connector state;
2. streamovat read-only zdroj do unikátního stagingu a průběžně počítat SHA-256;
3. porovnat zdrojovou verzi před/po čtení;
4. flush + fsync staged payloadu, znovu jej nezávisle přečíst a ověřit SHA-256,
   velikost a formát;
5. získat per-hash lock a vyřešit existující objekt;
6. publikovat celý item adresář platformním atomic **no-replace** rename do
   content-addressed cíle;
7. fsync cílového parentu, potom transakčně označit objekt jako `published`.

Publikační bod je úspěšný no-replace rename. Obyčejný copy, overwrite nebo
cross-filesystem move není publikace. Implementace musí mít explicitní Windows
a Linux backend; pokud filesystem neumí doloženou atomic no-replace operaci a
durability, Transfer fail-closed. NAS/SMB/NFS zůstane v první implementaci
**UNVERIFIED / UNSUPPORTED**, dokud nebude zvlášť kvalifikován.

### 3. Existující obsah a opakovaný transfer

Pokud cílový hash adresář existuje, Transfer jej nikdy nepřepíše. Pod lockem:

- vyžaduje právě jeden regular, non-link payload a bezpečně confined cestu;
- plně přepočítá SHA-256 a ověří velikost;
- při shodě zahodí až následně vlastní staged kopii a atomicky přidá novou
  source-content vazbu — výsledek je `deduplicated_existing`;
- při neshodě vrátí `CONTENT_OBJECT_CORRUPT_OR_COLLISION`, nic nepublikuje,
  nic neopravuje a ponechá důkazy pro ruční diagnostiku.

Běžný startup nedělá full rehash Media Storage. Plný rehash existujícího objektu
je povinný pouze při kolizi/opakovaném transferu na stejnou content identity a
při explicitním integrity auditu.

### 4. Původní názvy, cesty a provenience

Původní hodnoty se nikdy nepoužijí jako cílová filesystem cesta. Connector state
uchová nejméně:

- `workspace_id`, adapter kind a stabilní source profile ID;
- opaque `object_id`, source `version_token`, původní `logical_path` a filename;
- observation čas, velikost a provider metadata/checksum s algoritmem;
- transfer run/item ID, staged SHA-256, content object ID a stav;
- všechny retry/error přechody a vazbu mnoha zdrojů na jeden content object.

Exportovatelný handoff/provenance manifest bude oddělený od originálů a mimo
Media Storage scan root. Workspace contract v1 bude nadále ukazovat pouze na
content-addressed fyzickou cestu. Původní externí provenience tedy nebude ve v1
katalogu viditelná, dokud nebude schválen samostatný integrační kontrakt.

### 5. Persistentní stav a ownership

Navržen je privátní lokální SQLite katalog Media Connectoru pod explicitním
`connector-state-root`, vázaný na `workspace_id`. Není součástí Media Storage,
workspace ani ingest SQLite a není veřejným API.

Minimální entity:

- `source_profiles`, `source_observations`;
- `transfer_runs`, `transfer_items`, append-only `transfer_events`;
- `content_objects` a `source_content_links`;
- schema version a operation/lock metadata.

Jeden aktivní writer na knihovnu drží OS lock. SQLite transakce zaznamenává stav
před a po externí filesystem operaci; DB a filesystem netvoří jednu atomickou
transakci, proto recovery vždy reconciliuje oba světy. Multi-host zápis není
podporovaný. Záloha state je samostatná odpovědnost Connectoru; ztráta state
nesmí poškodit originály, ale znamená ztrátu zdrojové historie.

### 6. Recovery a konzistence

| Selhání | Povinné chování |
|---|---|
| zdroj zmizí / timeout | retryable stav, partial není publikován, source config zůstává |
| zdroj se během čtení změní | `SOURCE_CHANGED`, staged data nejsou publikována |
| disk full / write chyba | `TRANSFER_WRITE_FAILED`, žádný validní objekt |
| pád před verify | run/item `interrupted`, partial zůstává izolovaný |
| pád po verify před publish | recovery znovu ověří staged payload |
| pád po publish před DB commit | recovery najde expected hash path, plně jej ověří a teprve pak adoptuje |
| cílový objekt shodný | dedup/no-op, přidá se pouze source-content vazba |
| cílový objekt neshodný | fail-closed, žádný overwrite ani automatická oprava |
| state DB nedostupná | žádný transfer ani publish |

Automatický cleanup není součást recovery. Retence ověřených/neověřených
stagingů vyžaduje explicitní, auditovanou operaci v pozdější etapě.

### 7. Cesty a souběh

- Source otevření vždy znovu použije adapter confinement a link/reparse ochrany.
- Storage, staging, state a workspace se nesmějí překrývat žádným směrem.
- Final path vzniká pouze z validovaného lowercase SHA-256 a allowlisted suffixu.
- Library writer lock serializuje publish/state transitions; per-hash lock řeší
  dedup race. Neznámé soubory nebo adresáře se nikdy neadoptují ani nepřepisují.
- Podporovaný workflow nespouští Ingest souběžně s Transferem. Protože Ingest
  nesdílí Connector lock, technicky může při souběhu vidět starý nebo nový
  kompletní objekt, nikdy partial; úplnost konkrétního běhu ale není zaručena.

## Kompatibilita a důsledky

- Workspace contract zůstává v1 a Ingest kód/SQLite se nemění.
- Ingest dostane `Media Storage` jako `INPUT`, scanner najde pouze publikované
  payloady a sám vypočte asset SHA-256.
- Katalogová `relative_path` bude content-addressed cesta, nikoli externí název.
- Media Desk a procesory mohou originál otevřít běžným `source_root +
  relative_path`; S2a mapping zůstává použitelný.
- Connector state je jediný vlastník externí provenience a transfer historie.
- Content-addressed namespace usnadní dedup a recovery, ale není lidsky čitelný.

## Body ke schválení

1. Content-addressed adresář na SHA-256 s jediným `payload.<canonical-suffix>`.
2. Povinný Ingest Compatibility Profile a zákaz publikace nejednoznačného
   ingest-ready formátu.
3. Explicitní same-filesystem staging mimo Media Storage a atomic no-replace
   publish; první rozsah pouze na kvalifikovaných lokálních filesystémech.
4. Privátní lokální Connector SQLite, single writer a recovery reconciliace.
5. Oddělená provenience; workspace contract v1 obsahuje pouze fyzickou CAS cestu.
6. Full rehash existujícího objektu při dedup kolizi, nikoli při běžném startu.
