# S2a.1 — profil a optimalizace startu

**Stav:** **IMPLEMENTED / COMPLETE 2026-10-22**

**Baseline commit:** `159fc910e806019494e179b596531040cab9127a`

**Prostředí:** Windows, lokální NTFS, Python z projektového `.venv`, syntetické
malé soubory bez EXIF/FFmpeg/AI. Síťový mount ani nativní Linux nejsou na tomto
hostu dostupné.

## Metodika

`tests/media_desk/benchmark_s2a.py` vytváří reprodukovatelný katalog a
`tests/media_desk/benchmark_s2a1.py` měří `create_app`, první HTTP odpovědi,
Python alokace přes `tracemalloc`, volání filesystem metod pouze pod kořenem
originálů a `cProfile` kritické cesty. OS cache nebyla násilně vyprazdňována:
první běh bezprostředně po vytvoření datasetu je evidován odděleně, další běhy
jsou teplé. Jde o lokální syntetický benchmark, ne simulaci latence NAS.

## Baseline před implementací

Jednotlivé první běhy po vytvoření datasetu:

| Assety | Validace mappingu | `create_app` | SHA při startu |
|---:|---:|---:|---:|
| 100 | 383 ms | 317 ms | 0 |
| 1 000 | 3 049 ms | 2 505 ms | 0 |
| 10 000 | 24 530 ms | 23 882 ms | 0 |

Teplé opakování `create_app` pro 10 000 assetů: 24 021 / 25 767 / 28 106 ms,
p50 **25 767 ms**, p95 **28 106 ms**. Orientační peak nových Python alokací při
samostatném běhu byl **44,34 MiB**; nejde o procesní RSS.

Instrumentace originálů na jeden startup naměřila:

- `Path.resolve`: **20 001**;
- `Path.is_file`: **10 000**;
- `Path.open`, SHA-256: **0**.

`cProfile` při 10 000 assetech:

| Funkce | Kumulativní čas |
|---|---:|
| `create_app` | 32,684 s |
| `load_workspace` | 32,237 s |
| `_original` | **23,092 s** |
| `Path.resolve` / Windows `realpath` | 14,643 / 13,902 s |
| `_processor_results` | 6,066 s |
| `Path.is_file` | 1,688 s |

Primární příčinou je tedy prokázaná plošná canonicalizace a existence každého
originálu při tvorbě snapshotu. `_processor_results` je sekundární náklad; S2a.1
nejprve odstraní per-asset I/O originálů a po změně znovu změří jeho relativní
podíl.

Samostatné pětiběhové baseline měření `create_app` doplnilo velikostní řadu:

| Assety | p50 před | p95 před |
|---:|---:|---:|
| 100 | 323,9 ms | 420,6 ms |
| 1 000 | 2 753,2 ms | 3 223,6 ms |
| 10 000 | 25 767,3 ms | 28 105,8 ms |

## Schválený směr

Podle D-016 snapshot zaregistruje pouze katalogem autorizovanou source reference
a opaque token bez per-file filesystem I/O. Konkrétní soubor se při každém GET
nebo Range požadavku znovu odvodí z aktivního server-side rootu, canonicalizuje,
ověří confinement a teprve potom jednou otevře. `original_online` před tímto
request-scoped ověřením nesmí být `true`.

## Finální after profil

Pět opakování na stejných uchovaných datasetech:

| Assety | p50 po | p95 po | Zrychlení p50 |
|---:|---:|---:|---:|
| 100 | 130,0 ms | 363,0 ms | 2,49× |
| 1 000 | 861,6 ms | 1 362,3 ms | 3,20× |
| 10 000 | 7 752,8 ms | 8 192,8 ms | **3,32×** |

Startup provedl jediný `resolve` samotného mapped rootu při bindingu a **0
per-file resolve/stat/is_file/open/SHA** originálů. Orientační peak nových Python
alokací pro 10 000 položek klesl z **44,34 MiB** na **31,72 MiB**. Hodnota je
`tracemalloc` peak, nikoli procesní RSS.

After `cProfile` už neukazuje filesystem přístup originálů mezi hlavními náklady.
Nejdražší je nyní stávající `_processor_results` (4,204 s profilovaného běhu)
kvůli kontrolám analysis adresářů; jeho změna není nutná ke splnění cíle >3× a
není součástí bezpečnostní změny S2a.1.

## HTTP a request-scoped origin access

Pět požadavků na 10k snapshot; p95 je maximum z pěti vzorků. První požadavek
zahrnuje inicializaci `TestClient`, proto je zejména baseline p95 záměrně
konzervativní.

| Operace | p50 před | p95 před | p50 po | p95 po |
|---|---:|---:|---:|---:|
| `/` | 74,0 ms | 2 154,5 ms | 44,5 ms | 337,9 ms |
| `/library` | 48,2 ms | 104,2 ms | 10,2 ms | 32,2 ms |
| `/api/index` | 39,7 ms | 83,5 ms | 18,0 ms | 29,1 ms |
| image GET | 15,7 ms | 27,4 ms | 21,5 ms | 82,6 ms |
| video Range | 20,3 ms | 23,7 ms | 14,8 ms | 109,7 ms |

Deset origin požadavků po změně provedlo očekávaných deset per-file
canonicalizací, deset `is_file` a deset otevření. Dvě volání `resolve` na
požadavek odpovídají canonicalizaci rootu a kandidáta. Invalidní Range se
odmítne a otevřený descriptor se uzavře; validní full GET i Range streamují z
jediného již ověřeného descriptoru bez opětovného otevření cesty.

## Bezpečnostní a provozní ověření

- chybějící soubor po startu: vždy HTTP 404, p50 13,2 ms, p95 24,3 ms;
- dočasně nedostupný mapped root: vždy HTTP 404, p50 8,8 ms, p95 17,1 ms;
- nedostupnost nemaže uložené mapování a metadata/previews zůstávají čitelné;
- změna mapping rootu mění binding epochu, takže starý opaque token nový snapshot
  nepřijme;
- testy blokují file i directory symlink escape a traversal; na tomto Windows
  hostu byly symlink případy přeskočeny kvůli chybějícímu oprávnění, POSIX testy
  zůstávají součástí sady;
- SHA-256 vzorek běží jen při vytvoření/změně mapování, nikoli při startupu nebo
  běžném otevření souboru.

Vizuální kontrola při 1024 × 576 potvrdila jeden svislý scroll kontejner
`.app-main`, nulový horizontální overflow a správný stav „ověří se při otevření“
v Knihovně i detailu.

## Omezení měření

Měření proběhlo na Windows a lokálním NTFS s teplou OS cache. Síťový NAS/SMB,
řízený cold-cache běh a nativní Linux na tomto hostu nebyly dostupné. Přenosnost
Windows/POSIX cest je pokryta parametrizovanými testy, nikoli nativním Linux
během. Mezi `resolve` a `open` zůstává na nepřátelském či souběžně měněném
filesystemu zbytkové TOCTOU okno; po otevření se už streamuje z jediného
descriptoru. S2a.1 nemění Media Ingest, procesory, SQLite ani veřejný kontrakt
`workspace_contract_version: 1`.
