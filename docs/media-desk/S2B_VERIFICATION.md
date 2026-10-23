# S2b — implementace a ověření inicializace nového archivu

**Stav:** **IMPLEMENTED**

**Dokončeno:** 2026-10-23 na větvi `mediadesk`

## Implementované rozhraní

Media Ingest vlastní jedinou veřejnou hranici:

```powershell
python -m huhac_media init `
  --storage 'D:\HUHAC\Media' `
  --workspace 'C:\HUHAC\Workspaces\main' `
  --preflight --json

python -m huhac_media init `
  --storage 'D:\HUHAC\Media' `
  --workspace 'C:\HUHAC\Workspaces\main' `
  --operation-id '<UUID z preflightu>' `
  --yes --json
```

`--preflight` neprovádí žádný zápis. Stdout obsahuje právě jeden JSON envelope
`schema_version: 1`; klient rozhoduje podle `state` a `error.code`. Exit kódy jsou
0 pro úspěch/ready, 2 pro chybu argumentů, 3 pro zamítnutí nebo provozní chybu,
4 bez potvrzení a 130 při přerušení.

Confirmed init znovu validuje cesty pod exkluzivním zámkem, používá versioned
operation marker, nevytváří žádná média a nespouští Scanner, Planner,
`IngestService`, metadata, preview ani procesory. Vytvoří interní SQLite workspace
row a init run, report s nulovými počty, katalog v1 s `assets: []` a publikuje
`workspace.json` jako poslední veřejný readiness bod.

Media Desk spouští CLI pevným seznamem argumentů bez shellu, kontroluje přesné
JSON schema, timeout a velikost výstupu. Confirm vyžaduje krátkodobý jednorázový
nonce svázaný s operation ID a oběma canonical cestami. Po úspěchu Desk provede
vlastní read-only validaci veřejného kontraktu a teprve potom atomicky uloží
profil; aktivace vyžaduje restart.

## Ověřené scénáře

1. **Nový archiv:** nové nebo existující prázdné kořeny vytvoří ready workspace
   se stabilním UUID a nulou médií. Overview, Library, Calendar, Relations a API
   se po restartu otevřou s prázdným výsledkem.
2. **Existující archiv na jiném OS:** nadále používá M1.3/S2a „Připojit existující
   workspace“ a lokální mapování originálů; S2b nepřepisuje `source_root` ani
   veřejný katalog existujícího archivu.
3. **Běžné opakované spuštění:** ready cíl vrací `ready_existing`, zachová stejné
   `workspace_id`, nevytváří další run a nemění byte/mtime manifestu, katalogu ani
   SQLite. SQLite readiness kontrola používá read-only immutable režim, takže
   nevytváří WAL/SHM sidecary.

## Bezpečnostní a failure ověření

- equality a oba směry containment rootů jsou odmítnuty;
- symlink/reparse komponenty jsou odmítnuty; kontrola se opakuje před manifestem;
- network a unknown workspace filesystem fail-closed; Media Storage může být
  network pouze pokud je dostupný a prázdný;
- deset failure injection bodů od rezervace po manifest má bezpečný retry se
  stejným operation/workspace ID;
- souběh dává právě jednoho writera a `INITIALIZATION_BUSY` druhému procesu;
- neznámá kolize končí manual-action stavem a cizí soubor zůstává byte-for-byte;
- neprázdný Media Storage se nemění, nedokončený stav se nemaže;
- chyba postvalidace nebo config save zachová původní profil; hotový archiv
  zůstává použitelný;
- empty katalog načetly Media Desk, Session Grouper, Video Keyframes, Vision i
  Faces bez změny workspace contract v1.

## Testy a měření

Na Windows hostu 2026-10-23:

- cílená S2b/Media Desk/security sada: **53 passed, 4 skipped**, 32,93 s;
- finální FAST regrese: **200 passed, 7 skipped, 48 deselected**, 18,32 s;
- nativní symlink test byl přeskočen bez oprávnění vytvořit symlink;
- nový init, 30 měřených běhů po 3 warm-up: p50 **425,81 ms**, p95
  **4 867,38 ms**, minimum 386,36 ms, maximum 5 212,54 ms;
- `ready_existing`, 100 běhů: p50 **3,60 ms**, p95 **4,06 ms**, maximum 5,91 ms;
- Media Storage po měření obsahoval **0 položek**.

Vysoké p95 nového initu odpovídá několika pozorovaným filesystem/SQLite/antivirus
odlehlým hodnotám na tomto hostu; číslo není maskováno průměrem. Runtime neroste
s počtem médií, protože S2b přijímá jen prázdný storage a nic neskenuje.

## Známá omezení

- Nativní Windows workflow je ověřeno. WSL ani Linux distribuce na tomto hostu
  nebyla dostupná, proto nativní Linux smoke zůstává **UNVERIFIED**; POSIX větev
  locku a mount klasifikace je implementována, ale musí projít CI/Linux během.
- Detekce mountu je obranný filtr, nikoli univerzální důkaz lock/rename semantics;
  unknown workspace se proto odmítá bez override.
- Lokální-only workspace je omezení S2b, nikoli definitivní storage architektura.
- Neexistuje automatické mazání ani adopce neznámého nedokončeného stavu.
- Import, scan, SHA, metadata, preview, AI, multi-workspace, hot-swap a další
  storage etapy nejsou součástí S2b.
