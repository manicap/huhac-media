# HUHÁČ Media Pipeline / Media Desk — aktuální architektura

**Auditováno:** 2026-10-22

**Větev:** `mediadesk`

**Auditovaný commit:** `4397b9289de8689ed9282d9cbce842f3de4a60c2`

**Rozhodnutí aktualizována:** 2026-10-23 po dokončení S2b

> **IMPLEMENTOVÁNO DNES** — běžící galerie je lokální read-only konzument jednoho
> veřejného workspace v1. Výslovně potvrzené založení archivu orchestruje přes
> veřejné JSON CLI samostatného Media Ingest writeru; profil uloží až po vlastní
> read-only validaci výsledku.

> **NADÁLE NEIMPLEMENTOVÁNO** — import z webu, orchestrace procesorů, obecný
> storage lifecycle, síťový workspace writer a cílová přenosná metadata.

## Pojmy a vlastnictví

| Vrstva | Dnešní podoba | Vlastník zápisu | Stav |
|---|---|---|---|
| Media Storage | adresář originálů zadaný ingestu jako `input` | mimo Media Desk; ingest originály čte | **IMPLEMENTED**, prázdný init **IMPLEMENTED**, lifecycle **ABSENT** |
| Workspace | `workspace.json`, `metadata/`, `previews/`, `analysis/`, `state/`, `runs/`, `logs/`, `tmp/`, `locks/` | ingest a každý procesor pouze ve svém namespace | **IMPLEMENTED** |
| Veřejný kontrakt | `workspace.json` → `metadata/catalog.json`, verze 1 | ingest publikuje atomicky | **IMPLEMENTED** |
| Ingest runtime | `state/catalog.sqlite3`, WAL, locks, reporty | Media Ingest | **IMPLEMENTED**, privátní |
| Media Desk instance config | jeden TOML v uživatelském profilu hostitele | Media Desk settings endpoint | **IMPLEMENTED** |
| Přenosná uživatelská data | budoucí výběry, ratingy, kolekce | nerozhodnuto | **PROPOSED** |

Workspace není synonymum pro Media Storage ani pro lokální konfiguraci aplikace.
`source_root` ve veřejném katalogu je dnes absolutní cesta z hostitele posledního
ingestu (`src/huhac_media/storage/contract.py:79-83`). Asset identita je SHA-256,
zatímco aktivní zdroj nese relativní cestu.

## Skutečný tok dat

1. **IMPLEMENTED:** ingest skenuje `input`, vlastní interní SQLite a zapisuje
   manifest, katalog, metadata, previews a run artefakty
   (`src/huhac_media/cli.py:61-135`).
2. **IMPLEMENTED:** procesory začínají veřejným kontraktem a zapisují jen vlastní
   `analysis/<processor>/` výstupy; Media Desk jejich interní API neimportuje.
3. **IMPLEMENTED:** Media Desk při vytvoření aplikace jednou validuje workspace a
   drží snapshot/index v paměti (`src/media_desk/web.py:184-212`).
4. **IMPLEMENTED:** prohlížeč dostává pouze serverem registrované artefakty;
   skutečná cesta musí po resolve zůstat v autorizačním kořeni
   (`src/media_desk/web.py:641-660`).
5. **IMPLEMENTED:** změna cesty z UI atomicky přepíše jen per-user TOML a projeví
   se při příštím startu (`src/media_desk/config.py:164-213`).
6. **IMPLEMENTED S2b:** Media Desk spouští pevné JSON CLI Media Ingestu bez
   Python importu, postvaliduje veřejný kontrakt a až potom uloží profil.

## Databázová hranice a síťová úložiště

**IMPLEMENTED.** SQLite `state/catalog.sqlite3` je privátní ingest state. Writer
zapíná foreign keys, 5s busy timeout, WAL a `synchronous=FULL`
(`src/huhac_media/storage/database.py:11-28`). Ingest používá hostitelský file
lock `locks/ingest.lock` (`src/huhac_media/storage/workspace.py:89-129`). Media
Desk SQLite neotevírá a žádnou vlastní SQLite nemá.

**DECIDED/TARGET.** Jedna logická DB patří k jednomu workspace a nesmí ji zároveň
zapisovat více hostitelů přes sdílený mount.

**UNVERIFIED.** Samotné WAL + advisory lock nejsou důkazem bezpečnosti na SMB/NFS.
Audit neověřoval konzistenci, reconnect, lock semantics ani zálohu konkrétního
NAS. Podporovaný writer deployment musí být vybrán před implementací: přímý
single-writer, lokální writer s publish/sync, nebo backend-owner služba.

## Windows/Linux cesty

**IMPLEMENTED.** Workspace cesta v Media Desk configu je vždy lokální cesta
serverového hostitele. Veřejný katalog přijme absolutní POSIX i Windows
`source_root` (`src/media_desk/contract.py:505-509`), ale při otevírání originálu
se převede přes nativní `Path` aktuálního OS (`src/media_desk/contract.py:136-177`).
Windows cesta na Linuxu (a opačně) se proto bezpečně nepoužije a originál zůstane
offline; preview z workspace je dál zobrazitelné
(`tests/media_desk/test_media_desk_contract.py:105-116`).

**IMPLEMENTED PRO MEDIA DESK.** S2a je lokální, explicitně navázané
mapování `workspace_id + catalog source_root → local media root` pouze pro
read-only Media Desk. Před uložením používá deterministický reprezentativní
SHA-256 vzorek nejvýše 16 dostupných assetů,
výslovně označený jako neúplná kontrola integrity. Běžný start neprovádí
full rehash. Mapping se nesmí zapsat do workspace ani sdíleného katalogu.

Binding a auditní počty jsou pouze v per-user profilu. Nedostupný kořen mapping
automaticky nemaže; binding mismatch či nedostupnost vypnou mapped originály,
zatímco metadata a previews zůstávají dostupné. Každý kandidát i každý požadavek
na artifact znovu ověřuje canonical containment a odmítá symlink escape.

S2a je přechodný kompatibilní adapter pro veřejný kontrakt v1, nikoli definitivní
storage architektura nebo storage registry. Rozšíření na procesory či obecnou
storage abstrakci vyžaduje nové rozhodnutí a samostatný návrh; S2a procesory nemění.
Video Keyframes nadále přímo používá katalogový `source_root`
(`src/video_keyframes/contract.py:102-124`).

**IMPLEMENTED S2a.1.** D-016 odděluje katalogem
autorizovanou source reference od aktuálně ověřeného souboru. Snapshot a UI
nesmějí vyžadovat per-asset I/O k originálům. Každý GET/Range musí naopak znovu
ověřit aktivní binding, bezpečnou relativní cestu, canonical confinement a
symlink escape a použít jeden request-scoped otevřený soubor. Opaque token
obsahuje epochu odvozenou z `workspace_id`, katalogového `source_root` a aktivního
server-side rootu; token z předchozího mappingu proto nový snapshot neregistruje.
API stav `unchecked` znamená pouze autorizovanou katalogovou referenci, nikoli
potvrzenou dostupnost souboru. Baseline a finální měření jsou v
[S2A1_STARTUP_PERFORMANCE.md](S2A1_STARTUP_PERFORMANCE.md).

## Bezpečnost Media Desku

- **IMPLEMENTED:** workspace validuje výhradně veřejný kontrakt
  (`src/media_desk/workspace_status.py:28-85`).
- **IMPLEMENTED:** relativní katalogové cesty odmítají absolutní cestu, `..` a
  symlink escape (`src/media_desk/contract.py:57-91`).
- **IMPLEMENTED:** settings POST vyžaduje loopback bind, loopback `Host`, shodný
  `Origin`, omezené tělo, přesnou sadu polí a CSRF token
  (`src/media_desk/web.py:264-303`).
- **IMPLEMENTED:** LAN bind dovolí read-only prohlížení, ale blokuje změnu configu.
- **IMPLEMENTED:** S2a validate/save/clear používají stejnou
  loopback/Host/Origin/CSRF hranici; save vždy znovu provede SHA-256 vzorek a
  chybný kandidát nezmění poslední platný profil.
- **IMPLEMENTED:** S2b preflight/confirm používá tutéž HTTP hranici a navíc
  jednorázový expirovaný nonce svázaný s operation ID a oběma cestami.
- **ABSENT:** autentizace a TLS; bezpečný default je `127.0.0.1`.

## Tři provozní scénáře

### A. Založení nového archivu

**IMPLEMENTED (S2b):** veřejnou hranicí je JSON CLI vlastněné
Media Ingestem. Read-only preflight nic nerezervuje; confirmed init zopakuje
validace, atomicky rezervuje operaci, vytvoří privátní SQLite stav a prázdný
katalog a publikuje `workspace.json` poslední. Media Desk až potom provede
read-only postcondition validaci, uloží lokální profil a vyžádá restart.
Žádný scan, hash, import ani procesor se nespouští. Detail a failure model jsou v
[S2B_DESIGN.md](S2B_DESIGN.md) a
[S2B_FAILURE_MATRIX.md](S2B_FAILURE_MATRIX.md).

Schválený návrh je přísnější než dnešní plný ingest: nový Workspace a Media Storage se
nesmějí překrývat a workspace musí být na prokazatelně lokálním filesystemu.
Lokální-only workspace je bezpečnostní omezení etapy S2b, nikoli definitivní
omezení Media Pipeline. Přenosná knihovna a případné centrální úložiště metadat
zůstávají otevřeným tématem. Implementační důkazy jsou v
[S2B_VERIFICATION.md](S2B_VERIFICATION.md).

### B. Připojení existujícího archivu na jiném OS

**IMPLEMENTED:** UI přijme workspace i lokální kořen originálů. Backend ověří
`workspace_id`, přesný původní `source_root`, confinement a reprezentativní
SHA-256 vzorek, potom mapping atomicky uloží jen do lokálního profilu. Další
start levně ověří binding a root, ale neprochází ani nehashuje jednotlivé
originály. Konkrétní soubor se ověří až při GET/Range. Chybný kandidát nepřepíše
poslední platnou konfiguraci; dočasná nedostupnost ji nemaže. SHA-256 vzorek je
výslovně neúplná kontrola integrity. Preview z workspace zůstává dostupné.

### C. Běžné opakované spuštění

**IMPLEMENTED:** profil se načte podle precedence, workspace se resolve/validuje
a mapping ověří pouze binding a dostupnost rootu. Snapshot registruje unchecked
source reference bez per-file origin I/O; `/health` je `ok`. Nedostupný workspace
vrátí non-ready 503 a setup/error UI bez zápisu. Nedostupný mapped root zachová
profil i browsable metadata/previews, pouze originály bezpečně degraduje na
offline. Jde o jeden workspace bez hot reloadu a bez přepisu sdíleného
`source_root`.
