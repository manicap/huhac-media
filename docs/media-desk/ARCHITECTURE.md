# HUHÁČ Media Pipeline / Media Desk — aktuální architektura

**Auditováno:** 2026-10-22

**Větev:** `mediadesk`

**Auditovaný commit:** `4397b9289de8689ed9282d9cbce842f3de4a60c2`

**Rozhodnutí aktualizována:** 2026-10-22 po schválení D-011, D-012 a D-009

> **IMPLEMENTOVÁNO DNES** — Media Desk je lokální read-only konzument jednoho
> veřejného workspace v1. Při startu načte snapshot a zapisuje pouze vlastní
> per-user TOML konfiguraci. Media Ingest je samostatný writer vlastnící interní
> SQLite, veřejné katalogy, náhledy a run state.

> **CÍLOVÝ WORKFLOW, DOSUD NEIMPLEMENTOVÁNO** — založení nového archivu,
> připojení workspace a originálů pod odlišnými cestami na jiném hostiteli a
> bezpečný storage lifecycle. Cíl neuděluje Media Desku právo zapisovat workspace.

## Pojmy a vlastnictví

| Vrstva | Dnešní podoba | Vlastník zápisu | Stav |
|---|---|---|---|
| Media Storage | adresář originálů zadaný ingestu jako `input` | mimo Media Desk; ingest originály čte | **IMPLEMENTED**, správa **ABSENT** |
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

**IMPLEMENTED S2a.1, FINAL VERIFICATION PENDING.** D-016 odděluje katalogem
autorizovanou source reference od aktuálně ověřeného souboru. Snapshot a UI
nesmějí vyžadovat per-asset I/O k originálům. Každý GET/Range musí naopak znovu
ověřit aktivní binding, bezpečnou relativní cestu, canonical confinement a
symlink escape a použít jeden request-scoped otevřený soubor. Opaque token
obsahuje epochu odvozenou z `workspace_id`, katalogového `source_root` a aktivního
server-side rootu; token z předchozího mappingu proto nový snapshot neregistruje.
API stav `unchecked` znamená pouze autorizovanou katalogovou referenci, nikoli
potvrzenou dostupnost souboru. Baseline a průběžné měření jsou v
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
- **ABSENT:** autentizace a TLS; bezpečný default je `127.0.0.1`.

## Tři provozní scénáře

### A. Založení nového archivu

**Dnes:** web nemá takový endpoint. Samostatný ingest umí založit workspace až v
zapisujícím běhu: vytvoří strom a manifest, zamkne workspace, otevře SQLite,
založí run/report a publikuje katalog (`src/huhac_media/cli.py:114-135`,
`src/huhac_media/storage/workspace.py:54-86`,
`src/huhac_media/services/ingest.py:49-118`). Prázdný scan podle kódu nevyžaduje
ExifTool (`src/huhac_media/cli.py:96`), ale cesta nebyla auditním testem
provedena end-to-end, proto je provozní použitelnost **UNVERIFIED**.

**DECIDED/TARGET:** průvodce UI → ingest-owned backend s explicitní autoritou → validace prázdných či
existujících kořenů → atomické založení → lokální config → restart/readiness.
Při selhání odstranit jen prokazatelně nově vytvořené prázdné artefakty, nikdy
cizí adresář. Inicializace musí být oddělená od importu a analýzy; konkrétní API
a rollback protokol zůstávají návrhem budoucí etapy.

### B. Připojení existujícího archivu na jiném OS

**Dnes:** UI → `/settings/validate` → `load_workspace` → `/settings/save` →
lokální TOML → restart funguje pro workspace. Preview zůstane dostupné. Druhý
kořen Media Storage UI nepřijímá; originály z cizího `source_root` jsou offline.

**DECIDED/TARGET:** uživatel zadá workspace i lokální kořen originálů → backend ověří
`workspace_id`, katalog, strukturální shodu a reprezentativní identitu → uloží
host-specific mapping lokálně → další start levně ověří binding a dostupnost,
nikoli SHA vzorek. Při chybě se
nepřepíše poslední validní konfigurace a originály zůstanou offline. SHA-256
vzorek nesmí být prezentován jako úplná integrita; běžný start nehashuje celý archiv.

### C. Běžné opakované spuštění

**Dnes:** profil se načte podle precedence → workspace se resolve/validuje → vznikne
snapshot → `/health` je `ok`; nedostupný mount vrátí non-ready 503 a setup/error
UI bez zápisu (`src/media_desk/web.py:204-218`, `src/media_desk/web.py:662-674`).
Jde o **IMPLEMENTED** scénář pro jeden workspace bez hot reloadu.

**Cíl navíc:** po zavedení mappingu ověřit také jeho binding a dostupnost; při
dočasném výpadku zachovat config, nabídnout retry a nikdy automaticky nepřepsat
sdílený `source_root`.
