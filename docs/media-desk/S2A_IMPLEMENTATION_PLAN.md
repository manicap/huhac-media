# S2a — implementační plán lokálního mapování originálů

**Stav:** **ACCEPTED/PLANNED — NOT IMPLEMENTED**

**Připraveno:** 2026-10-22

**Větev:** `mediadesk`

**Výchozí revize plánu:** `defb3160ddb79b3e9cb0646d4f7a32b45d87889f`

**Rozhodnutí:** D-011, D-009 a D-014 v [DECISIONS.md](DECISIONS.md)

## Stav realizace

- **IMPLEMENTED:** privátní `OriginalsMapping` schema v per-user profilu,
  atomický save, validace polí, profile-only načítání a vyčištění mappingu při
  změně workspace (`src/media_desk/config.py`).
- **IMPLEMENTED:** bezpečný mapped-root resolver, přesný binding a deterministický
  `sha256-sample-v1` s maximálně 16 assety (`src/media_desk/originals.py`).
- **IMPLEMENTED:** fail-closed contract/startup integrace; validní binding mění
  pouze kořen originálů, offline/mismatch zachová workspace a previews bez SHA
  při startu (`src/media_desk/contract.py`, `workspace_status.py`).
- **NOT IMPLEMENTED:** webové validate/save/clear flow.

## 1. Výsledek etapy

Media Desk umožní k jednomu aktivnímu workspace uložit host-specific kořen
originálů. Lokální mapping nahradí katalogový absolutní `source_root` pouze při
read-only otevírání originálů v Media Desku. Workspace, veřejný kontrakt v1,
originály, ingest SQLite a výstupy procesorů zůstanou beze změny.

S2a je přechodný kompatibilní adapter pro existující kontrakt v1. Není storage
registry, nepřidává logický storage identifikátor a neurčuje definitivní storage
architekturu.

## 2. Závazné invarianty a non-goals

### Invarianty

- Mapping je uložen pouze v per-user `config.toml` Media Desku.
- Binding obsahuje přesný `workspace_id` a přesný řetězec `source_root` přečtený
  z katalogu; hodnotu cizího OS se nepokouší kanonizovat.
- `local_root` je absolutní, existující adresář kanonizovaný nativně na serveru.
- Workspace a Media Storage se pouze čtou. Validace ani save nesmí změnit jejich
  obsah, velikost nebo mtime.
- Každá relativní zdrojová cesta zůstane pod kanonickým `local_root`; absolutní
  cesta, `..`, backslash a symlink escape jsou odmítnuty.
- SHA-256 probíhá jen při explicitní validaci/save reprezentativního vzorku.
  Běžný start neprovádí sample ani full rehash.
- UI i uložená metadata nazývají výsledek „vzorková kontrola“, nikdy úplná
  kontrola integrity archivu.
- Nedostupný či neplatný mapping vypne mapped originály do explicitního offline
  stavu; previews, metadata a analýzy z validního workspace zůstanou dostupné.
- S2a nemění chování Media Ingest, Session Grouper, Video Keyframes, Vision ani
  Faces.

### Mimo rozsah

- contract v2, storage registry, více workspace a portable user data;
- zápis nebo přepis katalogového `source_root`;
- automatický ingest, re-ingest, full archive verification nebo AI analýza;
- sdílení resolveru s procesory;
- inicializace nového workspace podle D-012;
- NAS writer, backup/restore implementace nebo multi-host SQLite;
- hot swap běžícího snapshotu a server-side restart.

## 3. Lokální konfigurační kontrakt

Navržená privátní per-user TOML reprezentace:

```toml
[media_desk]
workspace = "/srv/huhac/workspace"

[media_desk.originals_mapping]
workspace_id = "2ec92da1-..."
source_root = "D:\\Huhac\\Media"
local_root = "/mnt/huhac-media"
verification = "sha256-sample-v1"
verified_assets = 16
eligible_assets = 12480
```

`originals_mapping` není součást veřejného workspace kontraktu. Nebude mít CLI
ani environment override v S2a; načítá se výhradně z per-user profilu určeného
`user_config_path()`. Explicitní `--config` ani sdílený workspace jej nepřenášejí.

Uložení zachová stávající `host`, `port` a `keyframe_fingerprint`. Změna aktivní
workspace cesty stávajícím settings flow odstraní starý mapping ve stejné atomické
operaci, protože aplikace podporuje jen jeden aktivní workspace. Selhání
`os.replace` musí zachovat celý původní profil.

`verified_assets` a `eligible_assets` jsou auditní informace o poslední explicitní
kontrole, nikoli runtime důkaz úplné integrity. Žádný hash ani cesta k jednotlivým
souborům se do configu neukládá.

## 4. Navržená interní rozhraní

Názvy jsou implementační kontrakt S2a; změna významu vyžaduje aktualizaci plánu,
ne změnu veřejného workspace v1.

### `media_desk.config`

```python
@dataclass(frozen=True)
class OriginalsMapping:
    workspace_id: str
    source_root: str
    local_root: Path
    verification: str
    verified_assets: int
    eligible_assets: int

class Settings:
    ...
    originals_mapping: OriginalsMapping | None

def save_profile(
    config_path: Path,
    *,
    workspace: Path,
    originals_mapping: OriginalsMapping | None,
) -> None: ...
```

Stávající `save_profile_workspace()` může zůstat kompatibilní wrapper. Parser
odmítne neznámou `verification` verzi, neplatné počty a neabsolutní `local_root`.
Mapping se neaktivuje jen proto, že je syntakticky platný.

### Nový modul `media_desk.originals`

```python
MappingState = Literal[
    "unconfigured",
    "valid_sampled",
    "unavailable",
    "binding_mismatch",
    "storage_mismatch",
    "no_verifiable_assets",
    "invalid",
]

@dataclass(frozen=True)
class MappingValidation:
    state: MappingState
    message: str
    workspace_id: str
    source_root: str
    requested_root: Path | None
    resolved_root: Path | None
    eligible_assets: int
    accessible_assets: int
    sampled_assets: int
    matched_assets: int
    mapping: OriginalsMapping | None

def validate_mapping_candidate(
    workspace: Path,
    local_root: Path,
    *,
    sample_limit: int = 16,
) -> MappingValidation: ...

def bind_mapping(
    *,
    workspace_id: str,
    source_root: str,
    configured: OriginalsMapping | None,
) -> MappingValidation: ...

def resolve_mapped_original(
    local_root: Path,
    relative_paths: tuple[str, ...],
) -> Path | None: ...
```

`validate_mapping_candidate` je jediná cesta provádějící SHA-256. `bind_mapping`
je levná startup kontrola přesného bindingu a dostupnosti rootu; nehashuje.
`resolve_mapped_original` používá stejné deterministické pořadí aktivních source
paths jako dnešní `_original()`.

### Integrace contract loaderu

`load_workspace()` dostane volitelný již syntakticky validní a přesně bound
`OriginalsMapping`. Bez něj musí zachovat dnešní chování. S ním použije
`local_root` pouze pro `Artifact(kind="original")`; preview, processor outputs a
veškerá metadata se dál autorizují vůči workspace.

Do interního snapshot/validation contextu se přidá mapping state a původní
katalogový `source_root`, aby UI mohlo vysvětlit degraded stav. Existující JSON
API a úspěšná odpověď `/health` se nemění. Nedostupné originály neznamenají
neplatný workspace.

## 5. Reprezentativní SHA-256 vzorek v1

Algoritmus musí být deterministický a testovatelný:

1. Z katalogu vyber assety s `availability == "available"` a alespoň jedním
   syntakticky bezpečným aktivním source path.
2. Pro každý asset zvol první existující bezpečnou cestu v lexikografickém pořadí,
   stejně jako runtime resolver; asset se vzorkuje nejvýše jednou.
3. Cesty se nejprve strukturálně ověří: confinement po `resolve(strict=True)`,
   běžný soubor a shodná katalogová velikost. Nedostupné položky se započítají do
   diagnostiky, ale nejsou vydávány za ověřené.
4. Dostupné kandidáty rozděl podle `media_type` na image/video. V každé skupině
   seřaď podle `(size_bytes, sha256)` a zvol rovnoměrně rozložené indexy od
   nejmenšího po největší. Limit je celkem 16 assetů, přednostně 8+8; nevyužitá
   kapacita skupiny se převede druhé skupině.
5. Pokud je dostupných nejvýše 16 unikátních assetů, ověř všechny. Při více
   assetech výsledek vždy nese označení `sha256-sample-v1` a poměr `N/M`.
6. Celý obsah každého vybraného souboru se zahashuje a porovná s katalogovým
   `sha256`. Jediný size/hash mismatch odmítne save jako `storage_mismatch`.
7. Nula ověřitelných assetů vrátí `no_verifiable_assets` a mapping nelze uložit.

Tento algoritmus zvyšuje důvěru ve správnost kořene napříč typy a velikostmi, ale
neprokazuje úplnou integritu ani správnost nevzorkovaných souborů. UI to uvede
bez zkratek přímo u výsledku a potvrzovacího tlačítka.

## 6. UI a HTTP flow

### Validace

- `POST /settings/originals/validate`
- přesná pole: `csrf_token`, `local_root`;
- stejné loopback bind, `Host`, `Origin`, CSRF, content-length a control-character
  ochrany jako M1.3;
- aktivní workspace musí být validní a profile settings editovatelné;
- endpoint nic nezapisuje a vrátí stav, počty dostupných a vzorkovaných assetů,
  původní `source_root` a jasný disclaimer vzorkové kontroly.

### Uložení

- `POST /settings/originals/save` se stejnými poli a ochranami;
- server zopakuje celou validaci a SHA sample; nevěří výsledku předchozí stránky;
- uloží pouze `valid_sampled` mapping přes atomický `save_profile`;
- běžící snapshot zůstane beze změny a UI vyžádá restart.

### Odstranění mappingu

- `POST /settings/originals/clear`, přesné pole pouze `csrf_token`;
- atomicky odstraní lokální mapping, workspace config zachová;
- aktivace po restartu; žádný soubor workspace/originálů se nemaže.

### Startup a degraded režim

1. Načíst profil a veřejný workspace v1.
2. Porovnat mapping `workspace_id` a `source_root` přesnou shodou.
3. Pokud binding nesedí, mapping nepoužít a zobrazit `binding_mismatch`.
4. Pokud mapped root není dostupný/čitelný, mapping fail-closed nepoužít,
   originály označit offline a zachovat previews/metadata/analýzy.
5. Pokud binding/root platí, resolver registruje jen confined existující soubory.
6. Startup nevolá SHA-256. UI zobrazuje poslední uložený vzorkový rozsah jako
   historický výsledek validace, nikoli jako čerstvou kontrolu.

Když existuje applicable mapping, ale jeho root je nedostupný, Media Desk
automaticky nepadá zpět na katalogový `source_root`; tím se zabrání nečekanému
otevření jiné hostitelské cesty. Po clear mappingu se vrátí dnešní chování.

## 7. Path confinement a serving

- `local_root.resolve(strict=True)` musí být adresář.
- Source path je výhradně relativní POSIX cesta bez backslash a `..`.
- Kandidát se skládá po částech a `resolve(strict=True)` musí mít kanonický root
  mezi parents a být běžný soubor; symlink ven je offline/invalid.
- `Artifact.authorization_root` je kanonický mapped root.
- `/artifacts/{token}` zachová route-time resolve a containment kontrolu před
  otevřením; klient nikdy neposílá filesystem cestu ani nezíská obecný file-read.
- Testy pokryjí statický symlink escape na Windows, pokud host dovolí symlinky,
  a povinně na POSIX CI. Adversarial TOCTOU výměna symlinku je známé omezení
  stávající path-based serving vrstvy a nesmí být v dokumentaci vydávána za
  vyřešenou bez samostatného safe-open návrhu.

## 8. Plán změn po logických commitech

### Commit 1 — privátní config schema

Soubory: `src/media_desk/config.py`, config unit testy a example/user docs.

- Přidat `OriginalsMapping`, parse/serialize nested profile table a atomický
  `save_profile`.
- Zachovat precedence existujících parametrů a kompatibilní wrapper.
- Při změně workspace odstranit starý mapping.

### Commit 2 — resolver a sample validator

Soubory: nový `src/media_desk/originals.py`, cílené unit testy a syntetické fixtures.

- Implementovat binding, confinement, source selection, statistiky a
  `sha256-sample-v1`.
- Bez webu a bez změn procesorů.

### Commit 3 — read-only contract/startup integrace

Soubory: `contract.py`, `models.py`, `workspace_status.py` a contract/status testy.

- Aplikovat přesně bound mapping pouze na originály.
- Zavést degraded/offline stav bez změny stávajících veřejných API odpovědí.
- Ověřit nulové hash operace při běžném startu.

### Commit 4 — settings UI a chráněné endpointy

Soubory: `web.py`, settings/setup templates, existující CSS jen v nutném rozsahu,
settings/security testy.

- Validate/save/clear flow, vzorkový disclaimer, restart notice a diagnostika.
- Žádný obecný filesystem browser a žádný hot reload.

### Commit 5 — dokumentační synchronizace a akceptace

Aktualizovat `STATUS.md`, `ARCHITECTURE.md`, `DECISIONS.md`, `ROADMAP.md`, Media
Desk README a příklad configu podle skutečně dodaného chování. Označit pouze
prokázané části jako **IMPLEMENTED** a zaznamenat výsledky testů a měření.

## 9. Testovací matice

### Config

- backward-compatible profil bez mappingu;
- round-trip všech mapping polí na Windows/POSIX hodnotách;
- mapping jen z per-user profilu, ne CLI/ENV/explicit configu;
- neznámá verification verze, neabsolutní root, záporné/nekonzistentní counts;
- změna workspace čistí mapping; failed replace zachová původní bytes.

### Resolver a identita

- exact match/mismatch `workspace_id` a cizího Windows/POSIX `source_root`;
- správný, chybějící, unreadable a file-instead-of-directory root;
- absolutní source path, `..`, backslash, symlink escape a broken symlink;
- více aktivních sources: stejné deterministické pořadí jako runtime;
- správná velikost/hash, size mismatch a SHA mismatch;
- image-only, video-only, mixed, 0, 1, 16 a více než 16 kandidátů;
- determinismus výběru bez závislosti na pořadí katalogu;
- assertion, že validator zavolá hash nejvýše `min(16, accessible_assets)` krát.

### Contract/startup

- bez mappingu přesně dnešní chování;
- cross-OS katalog + správný local root zpřístupní originál;
- binding mismatch a missing mount zachová preview, originál offline;
- symlink ven nikdy nevytvoří autorizovaný artifact;
- `Artifact.authorization_root` je mapped root a `/artifacts` znovu kontroluje
  confinement;
- monkeypatch hash funkce prokáže nula hash volání při startupu a browsingu;
- existující virtualizace, kalendář, relace, Vision/Faces/keyframes zůstanou beze
  změny.

### HTTP a persistence

- validate nic nezapisuje; save revaliduje; clear mění pouze profil;
- workspace/original tree hash+size+mtime před/po je shodný;
- foreign Origin/Host, LAN bind, chybný CSRF, extra pole, control characters a
  oversized body jsou odmítnuty;
- nevalidní candidate nepřepíše poslední validní mapping;
- restart použije validní mapping; bez restartu se snapshot nezmění;
- UI vždy zobrazuje `N z M` a text, že nejde o úplnou kontrolu integrity.

### Účelný rozsah běhů

Po každém commitu nejbližší unit soubor; po contract/web integraci celé
`tests/media_desk`. Před dokončením FAST suite bez external/AI markerů. Žádné
modely, skutečný ingest ani GPU testy. Pro výkon syntetický katalog alespoň 10 000
assetů: zaznamenat startup čas, validační čas zvlášť a počet hash volání. Akceptace
je strukturální — startup hash count musí být 0 a sample hash count nejvýše 16;
čas se reportuje jako skutečné měření, ne jako předem vymyšlený limit.

## 10. Akceptační kritéria

1. Windows-origin `source_root` lze na Linux hostiteli lokálně přemapovat a po
   restartu bezpečně otevřít dostupné originály při zachování previews.
2. Mapping se použije pouze při přesné shodě `workspace_id` i původního
   `source_root` a existuje jen v per-user configu.
3. Žádný soubor workspace, originál, SQLite ani processor output se nezmění.
4. Traversal a symlink escape nevytvoří ani neobslouží artifact mimo local root.
5. Save proběhne jen po úspěšném deterministickém SHA-256 vzorku nejvýše 16
   dostupných unikátních assetů; mismatch save odmítne a zachová starý config.
6. UI uvede přesný poměr vzorku a výslovně řekne, že nejde o úplnou kontrolu
   integrity archivu.
7. Běžný start a browsing provedou nula SHA-256 kontrol originálů a nikdy full
   rehash.
8. Chybějící mount nebo binding mismatch zachová workspace ready pro metadata a
   previews, ale mapped originály jsou offline s diagnostikou.
9. Stávající Media Desk funkce a veřejné API zůstanou kompatibilní; procesory a
   kontrakt v1 nemají změnu.
10. Implementační etapa není dokončená, dokud kód, testy, měření a aktuální
    dokumentace nesouhlasí podle `AGENTS.md`.

## 11. Rollback a známá omezení

Rollback S2a je lokální: použít chráněné clear, nebo vrátit předchozí per-user
config. Není potřeba migrovat workspace ani přepočítat assety/AI. Při rollbacku se
Media Desk vrátí ke katalogovému `source_root` a dnešnímu offline chování.

Vzorková kontrola nezaručuje úplnou integritu archivu, nevzorkované či později
změněné soubory mohou selhat až při otevření. S2a neřeší procesory na jiném OS,
portable mapping, více storages, hostile local-filesystem TOCTOU ani bezpečný NAS
writer. Tyto limity musí zůstat viditelné v uživatelské dokumentaci.
