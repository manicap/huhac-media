# S2b — návrh inicializace nového archivu

**Stav:** **PROPOSED / AWAITING APPROVAL — NOT IMPLEMENTED**

**Připraveno:** 2026-10-23

**Větev a auditovaný HEAD:** `mediadesk` / `350bdf78e6f82f9cd489eb87a0bc4e0643abe635`

**Schválená hranice:** D-012 — prázdný workspace zakládá Media Ingest přes
samostatné rozhraní, nikoli Media Desk přímým zápisem producer-owned souborů.

Tento dokument je návrh. Nezavádí CLI, HTTP endpoint, databázovou migraci,
import, procesory ani správu úložišť.

## 1. Terminologie a zjištěný rozpor

Nové zadání používá označení **S2b** pro inicializaci nového archivu. Dosavadní
`ROADMAP.md` označovala stejnou práci jako **S1** a názvem **S2b** označovala
možné budoucí rozšíření storage resolveru do ingestu a Video Keyframes.

Navrhuje se:

- **S2b = inicializace nového archivu** podle tohoto dokumentu;
- dosavadní návrh společného storage resolveru zůstane odložený a bez čísla,
  dokud nedostane samostatně schválený rozsah;
- nejde o schválení ani zahájení tohoto resolveru, kontraktu v2 nebo S2c.

Přejmenování je **PROPOSED** a je jedním z bodů ke schválení.

## 2. Ověřený současný stav

### 2.1 Media Ingest

Současný příkaz `huhac-media ingest` provádí tok `resolve → validate_paths →
scan → plan → confirm → initialize_workspace → workspace_lock → SQLite →
IngestService.execute` (`src/huhac_media/cli.py:43-135`). Není veřejný příkaz
ani stabilní Python kontrakt pouze pro inicializaci.

`src/huhac_media/storage/workspace.py` dnes:

- `validate_paths()` odmítá shodný INPUT/WORK a WORK obsahující INPUT, ale
  záměrně dovoluje WORK uvnitř INPUT;
- `initialize_workspace()` odmítne neprázdný nerozpoznaný WORK, vytvoří adresáře
  a publikuje `workspace.json`;
- `workspace_lock()` zamyká `locks/ingest.lock`, ale volá se až po
  `initialize_workspace()`.

Tento bootstrap nelze beze změny vystavit jako bezpečný S2b init:

1. manifest vzniká před katalogem a SQLite;
2. adresáře a manifest vznikají před získáním zámku;
3. samostatné `initialize_workspace()` zanechá workspace, který Media Desk kvůli
   chybějícímu katalogu odmítne;
4. plný ingest před inicializací skenuje a hashují se kandidátní média, což S2b
   nesmí dělat;
5. současný run lifecycle spojuje discovery, stages, katalog a report.

SQLite je privátní ingest state. `Database.connect()` vytváří DB, zapíná WAL,
`synchronous=FULL` a aplikuje migrace (`storage/database.py:11-28`).
`CatalogStore.ensure_workspace()` vloží stabilní `workspace_id` do tabulky
`workspace` (`storage/catalog.py:89-99`). Veřejný katalog publikuje výhradně
`export_asset_catalog()` atomickým replace (`storage/contract.py:14-83`).

### 2.2 Prázdný workspace a Media Desk

Izolovaný diagnostický běh 2026-10-23 ověřil současný plný ingest nad prázdným
INPUT:

- exit code 0;
- `workspace_contract_version: 1`;
- stabilní UUID `workspace_id` v manifestu;
- SQLite existuje;
- vznikne jeden běžný ingest run/report;
- katalog má `assets: []`, absolutní `source_root` a `generated_by_run_id`;
- `validate_workspace()` vrátí `connected` a Media Desk načte 0 assetů.

Druhý izolovaný diagnostický běh potvrdil, že samotný
`initialize_workspace()` bez katalogu i workspace s malformed katalogem vrací
v Media Desku stav `invalid`. Permission/I/O větev byla ověřena auditováním
exception mapování, nikoli změnou ACL na tomto hostu.

To dokazuje kompatibilitu prázdného katalogu se současným Media Deskem, nikoli
vhodnost plného ingestu jako produktového initu.

`media_desk.contract.load_workspace()` vyžaduje manifest, katalog, shodnou verzi
a `workspace_id`, absolutní `source_root` a pole `assets`. Chybějící či neplatný
katalog je dnes **invalid**; permission/I/O nedostupnost se hlásí jako
**unavailable**, nikoli jako prázdná knihovna (`src/media_desk/contract.py:478-527`,
`src/media_desk/workspace_status.py:28-82`). Prázdné `assets: []` je validní.

M1.3 ukládá jen workspace vybraný z profilu a respektuje precedence
CLI → ENV → explicitní TOML → profil → default. Pokud aktivní workspace pochází
z vyšší priority, web profil měnit nesmí (`config.py:52-161`,
`web.py:412-452`). S2b musí zachovat stejné pravidlo.

### 2.3 Veřejný kontrakt v1

`docs/workspace-contract.md` dnes připouští, že nový workspace nemusí mít katalog
až do prvního ingestu. S2b potřebuje užší rozlišení:

- **rozpracovaný/interní bootstrap** může být bez katalogu a manifestu;
- **inicializovaný ready workspace** musí mít manifest i validní prázdný katalog.

Navržené upřesnění nemění `workspace_contract_version: 1`, asset schema ani
význam `workspace_id`. Po schválení implementace se má dokumentace kontraktu
doplnit o prázdný katalog jako platnou producer-owned projekci. V této návrhové
etapě se autoritativní contract dokument nemění.

## 3. Vybraná minimální architektura

### 3.1 Jediná veřejná integrační hranice

Vybraná varianta je **veřejný strojově čitelný CLI kontrakt vlastněný Media
Ingestem**. Media Desk spouští příkaz jako argumentové pole bez shellu. Neimportuje
privátní ingest třídy a nevytváří soubory workspace.

Navržený tvar:

```text
huhac-media init \
  --storage <absolute-path> \
  --workspace <absolute-path> \
  --preflight \
  --json

huhac-media init \
  --storage <absolute-path> \
  --workspace <absolute-path> \
  --operation-id <uuid> \
  --yes \
  --json
```

`--preflight` je striktně bez zápisu. Druhý příkaz opakuje všechny validace,
získá vlastnictví operace a teprve potom zapisuje. `--yes` znamená, že nadřazené
UI nebo přímý CLI uživatel zobrazil a získal výslovné potvrzení.

Uvnitř balíčku může CLI používat nový aplikační service, ale Python funkce není
druhý veřejný mechanismus ani kompatibilitní kontrakt pro Media Desk. Tím se
zachová dnešní producer/consumer oddělení.

Alternativa „veřejná Python funkce volaná Media Deskem“ se nedoporučuje: svázala
by release a interní exception/model schema obou balíčků. Alternativa „spustit
plný ingest nad prázdným INPUT“ se odmítá, protože skenuje, vytváří běžný ingest
run a má jiné failure/recovery chování.

### 3.2 Výstupní envelope

CLI zapisuje na stdout právě jeden JSON dokument; diagnostika jde na stderr a
nesmí obsahovat obsah souborů ani tajné údaje.

```json
{
  "schema_version": 1,
  "operation_id": "uuid",
  "state": "ready",
  "workspace_id": "uuid-or-null",
  "storage_path": "canonical server path",
  "workspace_path": "canonical server path",
  "created": {
    "storage_directory": true,
    "workspace_directory": true,
    "workspace_manifest": true,
    "empty_catalog": true,
    "sqlite": true
  },
  "warnings": [],
  "error": null,
  "restart_required": true
}
```

Stavy veřejného výsledku:

- `preflight_ok`;
- `confirmation_required`;
- `initializing` pouze v interním operation recordu/UI, ne jako úspěšný konečný
  CLI výsledek;
- `ready`;
- `ready_existing` — cíl je již plně validní a nebyl změněn;
- `failed_recoverable`;
- `failed_requires_manual_action`;
- `rejected` — bezpečnostní nebo validační zamítnutí bez zápisu.

Navržené exit codes navazují na současné hodnoty: `0` ready/preflight,
`2` usage, `3` infrastructure/rejected, `4` nepotvrzeno a `130` přerušeno.
Strojový klient rozhoduje podle JSON `state` a `error.code`, ne podle textu.

## 4. Definice inicializovaného prázdného archivu

### 4.1 Media Storage

- absolutní canonical serverová cesta;
- adresář existuje a při potvrzení byl prázdný;
- může být nově vytvořený nebo už existující prázdný;
- init do něj nekopíruje média, nevytváří sidecary a neprovádí SHA;
- neprázdný adresář je pro workflow „nový archiv“ odmítnut; budoucí import nebo
  připojení existujících dat je jiná etapa;
- `source_root` v prázdném katalogu je canonical cesta tohoto adresáře.

Root musí být při actual init dostupný; odpojený root se neinicializuje. Po
dokončení může být dočasně offline, aniž se workspace nebo profil smaže. Pokud
uživatel root před prvním ingestem přesune, prázdný katalog si ponechá původní
provenienční cestu; následující explicitní ingest musí dostat aktuální INPUT a
stejný WORK a atomicky publikuje nový `source_root` bez změny `workspace_id`.

### 4.2 Workspace

Ready workspace má:

```text
workspace.json
state/catalog.sqlite3
metadata/catalog.json
metadata/{sources,assets,raw}/
previews/images/
analysis/
runs/<init-operation>/report.json
logs/
tmp/
locks/
```

Minimální konzistentní stav:

1. jedno UUID `workspace_id` v manifestu, SQLite `workspace` row a katalogu;
2. aktuální privátní SQLite schema a právě jeden dokončený init operation record;
3. prázdný katalog v1 s `assets: []`, absolutním `source_root`, `generated_at`
   a platným `generated_by_run_id` odkazujícím na interně zaznamenanou init
   operaci;
4. atomicky publikovaný `workspace.json` jako poslední veřejný readiness bod;
5. init report uvádí vytvořené a nevytvořené artefakty a nulový počet importů,
   hashů a procesorů.

Init operation se eviduje v dnešní privátní tabulce `runs` s efektivním configem
obsahujícím `operation_kind: initialize`; nespouští však `Scanner`, `Planner`,
`IngestService.execute`, metadata, preview ani procesory. Toto je minimální
varianta bez změny veřejného kontraktu a bez nové DB tabulky. Oddělenost je
vynucena samostatným service a CLI commandem.

První pozdější ingest použije stejné `workspace_id`, stejnou DB a obvyklou
resume/publish logiku. Nevzniká migrace, reanalýza ani zvláštní „empty“ asset.

## 5. Publikace, lock a idempotence

### 5.1 Readiness a pořadí zápisů

Navržené pořadí po druhé validaci:

1. atomicky rezervovat workspace target nebo rozpoznat přesný recoverable marker;
2. získat non-blocking init/workspace lock;
3. zapsat interní operation marker s `operation_id`, canonical roots, verzí a
   evidencí toho, co před operací existovalo;
4. vytvořit chybějící prázdný Media Storage adresář;
5. vytvořit workspace adresáře;
6. vytvořit/migrovat privátní SQLite, vložit workspace row a init run;
7. atomicky zapsat init report;
8. znovu ověřit identity rootů a prázdnost Media Storage;
9. atomicky publikovat prázdný `metadata/catalog.json`;
10. dokončit init run;
11. atomicky publikovat `workspace.json` **jako poslední veřejný readiness bod**;
12. označit operation marker jako complete a uvolnit lock.

Pokud existuje validní manifest, katalog i shodný `source_root`, příkaz vrátí
`ready_existing` bez zápisu. Pokud jde o jiný validní workspace, CLI ho
neadoptuje ani nepřepisuje a odkáže na workflow „Připojit existující archiv“.

### 5.2 Přerušení a retry

Žádný obecný rollback ani rekurzivní mazání se neprovádí. Při pádu může zůstat:

- nově vytvořený prázdný Media Storage adresář;
- workspace s interním markerem, ale bez manifestu;
- kompletní ready workspace s markerem, jehož finalizace se nestihla.

Nový běh pod lockem:

- rozpozná pouze vlastní versioned marker a přesnou dvojici canonical cest;
- ověří každý existující artefakt a stejné `workspace_id`;
- bezpečné chybějící kroky doplní;
- konflikt nebo neznámý soubor vrátí `failed_requires_manual_action` a nic
  nemaže;
- hotový workspace pouze ověří a vrátí `ready_existing`.

Souběžné procesy používají jednu atomickou rezervaci a jeden non-blocking lock.
Právě jeden je writer; druhý dostane `INITIALIZATION_BUSY` nebo
`WORKSPACE_ALREADY_READY`. Současné pořadí `initialize_workspace()` před lockem
se pro nový init nesmí použít.

## 6. Path policy a filesystemy

Pro S2b je politika úmyslně přísnější než dnešní ingest:

- oba cíle musí být absolutní serverové cesty;
- po canonicalizaci nesmějí být shodné;
- žádný root nesmí obsahovat druhý — workspace uvnitř Media Storage se pro nový
  profesionální workflow nepovolí, přestože současný ingest tento historický
  layout umí bezpečně vyloučit ze scanování;
- cílový adresář ani jeho měněná část nesmí být symlink/junction/reparse point;
- zaznamenají se identity existujících parentů a při potvrzení i před publikací
  se znovu ověří;
- POSIX implementace má preferovat `dir_fd`, `O_EXCL` a `O_NOFOLLOW`; Windows
  musí kontrolovat reparse points a identity otevřených directory handles;
- délka každé vstupní cesty je nejvýše 4096 UTF-8 bytů, NUL/control znaky a
  relativní segmenty jsou odmítnuty.

Preflight není rezervace. Kontrola oprávnění a volného místa je pouze snapshot a
warning; skutečné `mkdir/open/replace/fsync` může stále selhat.

### 6.1 Síťové úložiště

- **Workspace:** S2b v první verzi podporuje pouze filesystem klasifikovaný jako
  lokální. Známý SMB/NFS/network mount se odmítne. Stav `unknown` se ve webovém
  workflow odmítne také; UI nesmí tvrdit, že filesystem je bezpečný. Přímý CLI
  může pouze vypsat stejnou chybu, bez override v S2b.
- **Media Storage:** může být lokální nebo připojený network root, protože init
  do něj neukládá média. Nedostupný root se odmítne; pozdější výpadek nepoškodí
  workspace. UI zobrazí, že budoucí ingest dostupnost znovu vyžaduje.

Klasifikace mountu je obranný filtr, ne důkaz správných lock/rename semantics.
Multi-host SQLite zápis zůstává nepodporovaný podle D-009.

## 7. Media Desk workflow

### 7.1 První obrazovka

Při `unset` nebo invalidním setupu nabídne dvě oddělené akce:

1. **Založit nový archiv** — S2b;
2. **Připojit existující archiv** — stávající M1.3/S2a, bez initu.

Formulář vysvětlí „Media Storage = originální média“ a „Workspace = katalog,
náhledy a interní stav“. Nezobrazuje import ani zpracování.

### 7.2 Preflight a potvrzení

Media Desk přijme dvě textové serverové cesty, provede existující ochrany vstupu
a spustí ingest CLI v `--preflight --json` režimu. Výsledek ukáže canonical
cesty, stav adresářů, vztah rootů, typ filesystemu, volné místo jako informaci a
přesný seznam budoucích zápisů.

Server vytvoří krátkodobý jednorázový confirmation nonce vázaný na CSRF session,
canonical cesty a výsledek preflightu. Nonce není rezervace. Potvrzovací POST
znovu spustí CLI actual init, který vše ověří pod lockem.

### 7.3 Dokončení

Media Desk po `ready` ještě read-only zavolá vlastní `validate_workspace()`.
Teprve pak atomicky uloží workspace cestu do per-user profilu. Pokud profil
nelze uložit, archiv zůstává hotový a UI nabídne přesnou cestu pro pozdější
„Připojit existující archiv“.

Vyšší precedence CLI/ENV/explicit TOML zůstává autoritativní. Pokud
`workspace_editable` není true, web S2b init nenabídne, protože by výsledek
nemohl bezpečně aktivovat v profilu. Běžící aplikace snapshot nepřepíná; úspěch
končí stavem `configured_restart_required` a uživatel proces restartuje.

Po restartu se zobrazí běžná prázdná Knihovna s 0 médii. Žádné tlačítko importu,
které dosud neexistuje, se nezobrazuje.

Pozdější přidání médií není součástí webového setupu. Uživatel může mimo Media
Desk umístit originály do Media Storage a explicitně spustit již existující
Media Ingest nad stejnou dvojicí cest, například:

```powershell
huhac-media ingest --input 'D:\HUHAC\Media' --work 'C:\HUHAC\Workspaces\main' --yes
```

Teprve tento oddělený krok skenuje, hashují se média, vytvářejí metadata a
publikuje neprázdný katalog. S2b ho automaticky nespouští.

## 8. Webová bezpečnost

Budoucí endpointy jsou například:

- `POST /setup/archive/preflight` — pouze read-only CLI preflight;
- `POST /setup/archive/initialize` — potvrzení a ingest-owned init.

Oba musí používat dnešní server-side loopback bind, loopback Host, same-origin
Origin, SameSite/HttpOnly CSRF token, exact field set a omezené tělo
(`src/media_desk/web.py:332-377`). Navíc:

- init endpoint není registrován nebo vždy vrací 403 při non-loopback bindu;
- nepřijímá příkaz, executable, flags ani JSON schema od klienta;
- subprocess používá pevné argumentové pole bez shellu, timeout, omezený stdout
  a kontrolu JSON schema;
- preflight nesmí listovat adresáře ani vracet jejich obsah;
- confirmation nonce má krátkou expiraci, je single-use a po restartu neplatí;
- současně smí běžet nejvýše jedna init operace na instanci;
- logují se operation ID, stavy a canonical cíle, nikoli obsah souborů;
- endpoint nic nemaže a neposkytuje obecné čtení/zápis souborů.

Minimální desktop návrh nepřidává vlastní seznam „povolených kořenů“: lokální
uživatel smí po dvojím potvrzení vybrat libovolné dva cíle, do nichž má stejný
OS účet právo zapisovat. Autorizační hranicí je výhradně loopback + same-origin
session a oprávnění tohoto účtu; non-loopback režim init zcela blokuje. Pro
spravovaný deployment je doporučen samostatný OS účet s omezenými filesystem
ACL. Budoucí serverový allowlist by byl další defense-in-depth policy, nikoli
náhrada Host/Origin/CSRF a path ochrany.

Zbytkové riziko: proces běží s oprávněními uživatele a stejně privilegovaný
lokální proces může cesty souběžně měnit. Revalidace, file identities a
no-follow operace riziko omezují, ale nenahrazují OS sandbox nebo oddělený
service account.

## 9. Dopad na Windows/Linux a S2a

`workspace_id` zůstává stabilní a není odvozený z absolutní cesty. Prázdný
katalog má serverový `source_root`, ale bez assetů neautorizuje žádný originál.
Na jiném OS se workspace stále otevře jako prázdný. S2a SHA mapping vyžaduje
assetový vzorek, takže před prvním ingestem není co mapovat; po prvním ingestu
se použije stávající workflow S2a nebo nový ingest aktualizuje `source_root`.

Media Desk tokeny, lazy GET/Range a procesory se S2b nemění. Video Keyframes dál
nezná lokální S2a mapping. Inicializace neslibuje přenosnou storage architekturu.

## 10. Výslovné non-goals

- import, scan, hash, přesun nebo kopírování originálů;
- spuštění metadata, previews, keyframes, Vision, Faces nebo jiných procesorů;
- hot-swap workspace, restart přes HTTP nebo multi-workspace správa;
- obecný storage registry, contract v2 nebo sdílený resolver procesorů;
- přímý writer workspace na SMB/NFS;
- automatické mazání, rollback cizích dat nebo adopce neprázdného cíle;
- změna veřejného asset schema nebo `workspace_contract_version: 1`.

## 11. Body ke schválení

1. **Nomenklatura:** S2b znamená inicializaci; původní „shared resolver S2b“ se
   odloží bez čísla.
2. **Integrační hranice:** jediným veřejným rozhraním je JSON CLI Media Ingestu,
   nikoli veřejný Python import do Media Desku.
3. **Ready definice:** prázdný katalog + SQLite workspace row + samostatně
   evidovaný init run, manifest publikovaný poslední.
4. **Path/deployment politika:** žádné překrývající se rooty a workspace pouze
   na prokazatelně lokálním filesystemu; network/unknown workspace je v S2b
   odmítnut.

Bez schválení těchto bodů se implementace nezahajuje.
