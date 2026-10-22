# RFC: setup workspace a Media Storage

**Stav:** **S2a VARIANTA 2A IMPLEMENTOVÁNA 2026-10-22; další varianty otevřené**

**Auditováno:** 2026-10-22

**Větev:** `mediadesk`

## Cíl a hranice

Umožnit tři workflow: nový archiv, připojení existujícího archivu pod jinými
hostitelskými cestami a běžný opakovaný start. RFC nemění kontrakt v1, databáze,
originály ani procesory a není oprávněním k implementaci Storage Manageru.

Rozhodnutí D-011 vybralo variantu 2A jako přechodný kompatibilní adapter pouze
pro Media Desk. D-012 potvrdilo ingest-owned inicializaci pro budoucí samostatnou
etapu. Multi-host SQLite zápis přes SMB/NFS zůstává nepodporovaný. Varianty 2B,
2C a konkrétní writer/backup deployment nejsou tímto schváleny.

## 1. Založení nového archivu

| Varianta | Popis | Výhoda | Riziko / dopad | Verdikt |
|---|---|---|---|---|
| A | Web přímo vytvoří `workspace.json`, adresáře a DB. | málo procesů | duplikuje ingest invariants, dává Media Desku write ownership | **REJECT** |
| B | Web spustí dnešní `ingest` nad prázdným inputem. | bez nového API | vznikne plný run, DB, report a katalog; lifecycle/rollback není setup kontrakt | **jen diagnostický workaround, ne produktový návrh** |
| C | Media Ingest dostane úzký idempotentní `init` kontrakt/CLI; web jej později volá přes omezenou službu. | jeden vlastník invariants, testovatelný rollback | nové zapisující API vyžaduje security a failure design | **RECOMMENDED po S2a** |

Minimální `init` musí přijmout explicitní Media Storage a Workspace root, odmítnout
neprázdný nerozpoznaný cíl, zapsat atomicky stabilní `workspace_id`, vytvořit jen
dokumentované artefakty a vrátit strojově čitelný výsledek. Rollback smí odstranit
jen artefakty vytvořené danou operací a pouze pokud před ní cíl prokazatelně
neexistoval/prázdný byl.

### First-run `setup_state`

**PROPOSED.** Stav má být odvozený, ne druhá autoritativní databáze:
`unconfigured` → `candidate_validated` → `confirmation_required` →
`initializing` → `configured_restart_required` → `ready`. Chybové stavy jsou
`workspace_unavailable`, `workspace_invalid`, `storage_unavailable`,
`storage_mismatch` a `initialization_failed`. Běžící server nesmí po zápisu
configu hot-swapovat snapshot. Stav `initializing` pro budoucí zapisující init
potřebuje operation ID a explicitní recovery; S2a jej nepoužívá.

## 2. Připojení existujícího workspace a originálů

| Varianta | Rozsah | Kompatibilita | Složitost | Verdikt |
|---|---|---|---|---|
| A | Lokální Media Desk adapter `workspace_id + catalog_source_root → local_root`. | bez změny v1, procesory dál beze změny | nízká | **RECOMMENDED jako S2a** |
| B | Sdílená knihovna resolveru a per-host config pro všechny konzumenty. | v1 lze zachovat | střední; dotkne se procesorů | **defer, vyžaduje samostatné schválení** |
| C | Contract v2 s logickým storage ID a mapováním. | čistý dlouhodobý model | migrace, dual-read, širší zásah | **defer** |

Mapping varianty A musí být lokální, nesdílený a navázaný nejméně na
`workspace_id`, kanonickou cestu otevřeného workspace a přesnou původní hodnotu
`source_root`. Změna kteréhokoli bindingu mapping zneplatní, nikoli „opraví“.

### Read-only validace a identita

Navržený kontrakt výsledku: `valid`, `workspace_only`, `storage_unavailable`,
`storage_mismatch`, `invalid_workspace`; dále počet aktivních zdrojů, počet
dostupných cest, velikost deterministického SHA vzorku a timestamp kontroly.

1. Validovat manifest a katalog přes stávající `load_workspace`, bez zápisu.
2. Pro každou kontrolovanou cestu použít aktivní POSIX `relative_path`, odmítnout
   absolutní cestu, `..`, backslash a symlink escape.
3. Strukturálně ověřit existenci/typ/velikost; název není důkaz identity.
4. Deterministicky vzorkovat assety napříč katalogem a porovnat SHA-256 s asset ID.
   Schválený plán S2a určuje nejvýše 16 dostupných unikátních assetů, rozložených
   mezi image/video a rozsah velikostí; nejde o úplnou kontrolu integrity.
5. Běžný start pouze levně ověří binding a dostupnost, nehashuje celý archiv a
   nespouští AI. Explicitní full verify není součástí S2a; případně vyžaduje
   samostatnou budoucí etapu.
6. Při více aktivních source versions nehádat: zvolit stejnou deterministickou
   politiku jako konzument, nebo vrátit ambiguity. Toto je otevřené rozhodnutí.

## 3. Co je lokální a co přenosné

| Data | Umístění | Důvod |
|---|---|---|
| workspace cesta, host mapping, bind/port, lokální preference | per-user instance config | závisí na hostiteli, nesmí se přenášet jako pravda pro jiné OS |
| veřejný katalog, previews, processor outputs | workspace | přenosný veřejný/inferenční stav s jasným vlastníkem |
| budoucí výběry, ratingy, kolekce | samostatná portable user-data vrstva | mají se zálohovat/přenášet, ale nejsou inference ani host config |
| ingest SQLite/WAL/locks/run state | privátní runtime logicky náležející workspace | jen ingest writer; ne veřejné API |

Portable user-data schema, souběh a záloha jsou mimo tento RFC.

## 4. Writer a NAS varianty

| Model | Konzistence a provoz | Stav |
|---|---|---|
| Přímý single writer na sdíleném workspace | jednoduchý, ale závisí na ověřených SMB/NFS lock/WAL/rename semantics a záloze | **UNVERIFIED** |
| Lokální runtime writer + atomický publish/sync veřejných artefaktů | izoluje SQLite, vyžaduje protokol konzistentního publish a recovery | **PROPOSED** |
| Jeden backend-owner writer přes HTTP/job API | nejlepší centralizace zámků, přidává službu, auth a deployment | **PROPOSED pro pozdější provoz** |

Do rozhodnutí je podporovaným bezpečným předpokladem nejvýše jeden ingest writer;
Media Desk je read-only. Souběžné otevření stejné SQLite z více OS přes share je
**UNSUPPORTED**.

Konzistentní záloha musí zachytit privátní DB a jí odpovídající veřejný publish
point. U přímého writeru to znamená writerem koordinovaný checkpoint/stop a
snapshot; prosté kopírování živého `.sqlite3` bez WAL/SHM není přijatelné. U
lokálního runtime modelu musí publish manifest jednoznačně označit kompletní
generaci. U backend-owner modelu vlastní backup/restore tatáž služba. Konkrétní
postup je **UNVERIFIED** a musí vzniknout spolu s volbou deploymentu.

## 5. Bezpečnost, migrace a rollback

- Setup POST zachová loopback/Host/Origin/CSRF/size/exact-field ochrany M1.3.
- Backend nesmí nabídnout obecné listování nebo čtení libovolných cest.
- Mapping autorizuje pouze originály odvozené z validovaných aktivních relativních
  cest uvnitř zvoleného rootu; nikdy workspace SQLite nebo jiné soubory.
- S2a je additive local config change: žádná migrace workspace, rollback znamená
  odstranění/obnovení lokálního mapping záznamu.
- Contract v2, přepis `source_root`, re-ingest, full rehash a opakování AI nejsou
  součástí S2a.

## 6. Testovací plán pro S2a

- unit: binding, Windows/POSIX foreign path, traversal, symlink escape, více
  aktivních sources, deterministický sample a mismatch;
- integration: Windows-like katalog + Linux root, správný/chybný/offline root,
  restart persistence, atomický save failure a zachování starého mappingu;
- read-only invariant: hash/size/mtime všech workspace a originálních souborů
  před/po;
- HTTP security: loopback/LAN, Host, Origin, CSRF, oversized/unexpected fields;
- performance: běžný startup bez full rehash; počet FS operací omezený velikostí
  schváleného vzorku, ne velikostí archivu.

## 7. Implementační varianty a dopady

| Varianta | Změněné soubory / kontrakty | Windows/Linux | Bezpečnost | Migrace / rollback | Testy | Složitost |
|---|---|---|---|---|---|---|
| 2A: Media Desk local mapping (doporučeno) | `media_desk/config.py`, `contract.py`, `workspace_status.py`, settings UI a testy; public v1 beze změny | nativní lokální root na každém hostiteli, foreign root z katalogu zůstává binding | root confinement, symlink/traversal, CSRF/Host/Origin, SHA sample | bez workspace migrace; atomicky obnovit starý lokální config | unit + synthetic cross-OS integration + read-only invariant + startup budget | malá až střední |
| 2B: shared resolver pro konzumenty | nový sdílený adapter a změny každého konzumenta originálů; v1 lze zachovat | jednotné chování, ale více balíčků | audit každého open-file místa | feature flag/dual path; rollback na katalogový root | kontraktní suite napříč Media Desk/Keyframes/ingest | střední až vysoká |
| 2C: contract v2 | manifest/catalog schema, dual reader, dokumentace a všechny konzumenty | logické storage ID je přenosné | nová trust a authorization boundary | explicitní migrátor + backup + downgrade plán | v1/v2 compatibility, migration/rollback, real cross-OS | vysoká |
| 1B: reuse plného ingestu | orchestrace procesu/configu; kontrakt v1 beze změny | závisí na dostupnosti ingest nástrojů | command injection, oprávnění, dlouhý writer běh | vznik DB/run/report; komplikované částečné selhání | prázdný input, interruption, orphan recovery | střední, nevhodné UX |
| 1C: ingest-owned init (doporučeno později) | nový úzký ingest CLI/service + testy; Media Desk až v druhém kroku | stejné invariants na obou OS | explicitní roots, collision checks, operation ID | idempotentní additive init; přesně evidovaný rollback | empty/nonempty/collision, crash points, atomicity | střední |
| NAS direct writer | ingest deployment/docs/backup tooling; bez public změny | FS semantics se mohou lišit | jediný writer a přístupová práva | coordinated checkpoint/snapshot/restore | konkrétní SMB/NFS matrix, disconnect, lock, recovery | vysoká/nejistá |
| Local writer + publish | nový publish protocol/manifest/sync | runtime lokální, public data přenosná | staging + atomic generation switch | předchozí generace jako rollback | partial sync, crash, stale reader, restore | vysoká |
| Backend-owner service | nové job API, auth, deployment a backup API | klienti jsou path-agnostic | authn/authz/TLS/rate limits | server-owned migration a restore | API, concurrency, failover, security | velmi vysoká |

## Schválený směr a zbývající rozhodnutí

Varianta 2A je dokončena jako S2a; implementace a důkazy jsou v
[S2A_IMPLEMENTATION_PLAN.md](S2A_IMPLEMENTATION_PLAN.md). Princip varianty 1C je
schválený jako D-012, ale její konkrétní rozhraní není součástí S2a. Writer/NAS
model a rozšíření resolveru do procesorů zůstávají otevřené, dokud nebudou popsány
konkrétní deployment a failure scénáře.
