# S2a.1 — profil a optimalizace startu

**Stav:** **IMPLEMENTED / FINAL VERIFICATION IN PROGRESS**

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

První odpovědi po baseline startupu: `/` 264,3 ms, `/library` 18,5 ms,
`/api/index` 17,6 ms. Jde o jednotlivý smoke, nikoli p50/p95; finální benchmark
doplní opakované hodnoty i přístup k jednomu originálu.

## Schválený směr

Podle D-016 snapshot zaregistruje pouze katalogem autorizovanou source reference
a opaque token bez per-file filesystem I/O. Konkrétní soubor se při každém GET
nebo Range požadavku znovu odvodí z aktivního server-side rootu, canonicalizuje,
ověří confinement a teprve potom jednou otevře. `original_online` před tímto
request-scoped ověřením nesmí být `true`.

## Průběžný after profil

Na stejném uchovaném 10k datasetu po zavedení lazy reference byly tři startupy
6 495 / 6 150 / 5 133 ms, p50 **6 150 ms**, p95 **6 495 ms**. To je proti
baseline p50 zrychlení **4,19×**. Startup provedl jediný `resolve` samotného mapped
rootu při bindingu a **0 per-file resolve/stat/open/SHA** originálů. Orientační
peak nových Python alokací klesl na **31,72 MiB**.

After `cProfile` už neukazuje filesystem přístup originálů mezi hlavními náklady.
Nejdražší je nyní stávající `_processor_results` (4,204 s profilovaného běhu)
kvůli kontrolám analysis adresářů; jeho změna není nutná ke splnění cíle >3× a
není součástí bezpečnostní změny S2a.1.

Finální benchmark doplní opakované HTTP a origin access p50/p95, bezpečnostní
testy a zbytková omezení.
