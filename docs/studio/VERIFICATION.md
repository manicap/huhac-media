# Ověření HUHÁČ Studio v0.1

**Platforma:** Windows 10, Node.js 25.8.0, npm 11.11.0, 2026-10-27.

| Kontrola | Výsledek |
|---|---|
| Studio automatické testy | **PASS:** 5 souborů, 18 testů |
| TypeScript + Vite produkční build | **PASS:** Vite 8.3.5, 84 modulů |
| Lokální dev server | **PASS:** loopback `127.0.0.1:5174`, HTTP 200; testovací proces ukončen |
| npm audit po patch aktualizaci Vitest | **PASS:** 0 známých zranitelností |
| Launcher + Media Desk regrese | **PASS:** 138 testů, 6 platformních skipů |
| Původní worktree | **PASS:** původní větev a tracked pracovní strom beze změn |

## TASK-STUDIO-004 — Project Core v1

**Ověřeno:** 2026-10-28 na větvi `feature/studio-shell`.

| Kontrola | Výsledek |
|---|---|
| Project Core cílené testy | **PASS:** 19 testů |
| Celá Python sada | **PASS:** 329 passed, 9 skipped, 52 deselected |
| Studio frontend testy | **PASS:** 5 souborů, 18 testů |
| TypeScript + Vite build | **PASS:** Vite 8.3.5, 84 modulů |
| Python compileall | **PASS:** `src/huhac_studio`, `tests/studio` |
| Git whitespace check | **PASS:** `git diff --check` |

Project Core sada ověřuje schema v1, WAL a integritu, odmítnutí neznámé nebo
unversioned DB, konzistentní backup, host-level single-writer lock, stabilní ID,
neunikátní názvy, case-folded tags, archive/restore, read-only archived stav,
revision conflicts, transakční batch links, role `deliverable`, workspace scope,
offline zachování vazeb a HTTP ochrany Host/Origin/CSRF/body size. Skipy celé
Python sady jsou existující platformní testy; TASK-STUDIO-004 nepřidal žádný skip.

React v0.1 zůstává úmyslně na syntetickém adapteru. Ověření Project Core tedy
netvrdí, že je frontend napojen na nové API nebo že Launcher hostuje Studio.

## TASK-STUDIO-005 — funkční Projekty a Mediální knihovna

**Ověřeno:** 2026-10-28 na větvi `feature/studio-shell`.

| Kontrola | Výsledek |
|---|---|
| Project Core cílené testy | **PASS:** 22 testů |
| Studio frontend testy | **PASS:** 5 souborů, 20 testů |
| TypeScript + Vite build | **PASS:** Vite 8.3.5, 84 modulů |
| Izolovaný browser smoke | **PASS:** create, reload, link, oba moduly, reload persistence |

Sada ověřuje create/edit/archive/restore, předávání revision mezi mutacemi,
přidání a odebrání media links, reaktivní změnu projektu, reset výběru, session
a katalogovou projekci, bezpečné preview, single-origin hostování a zachování
bajtů původního mediálního souboru. Launcher integrace zůstává **ABSENT**.

Studio sada ověřuje registr a pořadí modulů, navigaci a klávesnici, výběr projektu,
reaktivní filtrování knihovny, zachování a reset výběru, workspace reset, lokální
stav, křížovou izolaci modulů, prázdná a chybová data, nedostupný modul a error
boundary. Produkční build a HTTP smoke potvrzují, že prototyp lze lokálně spustit.

Skipy Python regrese jsou stávající Windows testy vyžadující oprávnění pro
symlink; žádný nový skip nevznikl ve Studio sadě.

## TASK-STUDIO-007 — adaptivní galerie a video playback

**Ověřeno:** 2026-10-28 na větvi `feature/studio-shell`.

| Kontrola | Výsledek |
|---|---|
| Studio backend testy | **PASS:** 24 passed, 1 platformní symlink skip |
| Studio frontend testy | **PASS:** 6 souborů, 24 testů |
| TypeScript + Vite build | **PASS:** Vite 8.3.5, 87 modulů |
| Izolovaný browser smoke s reálným katalogem | **PASS:** 85 médií, adaptivní preview, inline video, přepnutí videa a cleanup při odchodu z modulu |

Backend sada pokrývá autorizaci originálu přes katalogový token, MIME, celé 200
odpovědi, jednolité HTTP Range 206, neplatný range 416, source-root confinement
a odmítnutí symlink escape. Platformní skip vzniká jen tam, kde testovací účet
Windows nemůže vytvořit symlink.

Frontend sada pokrývá horizontální, čtvercový a vertikální poměr stran, jediný
aktivní player, cleanup při přepnutí a navigaci, oddělení playbacku od výběru a
sdílenou/persistovanou hlasitost i mute včetně neplatného `localStorage` obsahu.
Browser smoke použil skutečný workspace katalog a originální MP4; ověřil lazy
vytvoření jediného nativního playeru, Range stream, hlasitost 50 %, zachování
výběru, přepnutí mezi videi, klávesnicové ovládání nativního playeru a zrušení
playeru po návratu do Projektů. Testovací server byl ukončen a izolovaná DB nebyla
použita jako provozní nastavení.

## TASK-STUDIO-008 — kompaktní galerie a hromadné operace

**Ověřeno:** 2026-10-28 na větvi `feature/studio-shell`.

| Kontrola | Výsledek |
|---|---|
| Media Library cílené testy | **PASS:** 1 soubor, 10 testů |
| Studio frontend testy | **PASS:** 6 souborů, 25 testů |
| TypeScript + Vite build | **PASS:** Vite 8.3.5, 87 modulů |
| Izolovaný browser smoke s reálným katalogem | **PASS:** 85 médií, pohodlná i kompaktní galerie, trvalá hromadná lišta a inline video |

Frontendový test pokrývá zachování výběru při změně hustoty, stav bez aktivního
projektu, dostupnost kontextové hromadné akce, zrušení výběru a nezměněné DOM
pořadí prvních karet. Browser smoke při 1920 × 1080 ověřil u prvních dvanácti
položek stejné zdrojové a vizuální pořadí zleva doprava a shora dolů, tři karty
šířky 484 px v řádku, výšku náhledu 223 px, čtrnáctipixelové mezery a nulový
horizontální overflow. Při 1000 × 800 zůstalo prvních šest položek v řádkovém
chronologickém pořadí bez horizontálního overflow. Výběr zůstal stabilní a player
načetl originál do `readyState 4`; kontextová lišta u horního okraje neměla žádný
průnik s playerem. Proměnlivý poměr stran může portrétní kartu stáhnout na minimální
šířku 150 px nebo ponechat část řádku volnou, obsah však zůstává velký, bez ořezu
a bez komplikovaného měřeného layout enginu.

## TASK-STUDIO-009 — pracovní prostředí a izolace knihoven

**Ověřeno:** 2026-10-28 na větvi `feature/studio-shell`.

| Kontrola | Výsledek |
|---|---|
| Session/offline backend testy | **PASS:** 10 passed, 1 platformní symlink skip |
| Cílené frontend testy | **PASS:** 2 soubory, 16 testů |
| TypeScript + Vite build | **PASS:** Vite 8.3.5, 87 modulů |
| Praktický testovací profil | **PASS:** workspace `5f3f16d1-5ff0-44ae-b8c2-ffc60a2ffe27`, 16 médií, 2 aktivní projekty |
| Praktický hlavní profil | **PASS:** workspace `37604dde-e37d-4940-8d4c-63955f610cfe`, 85 médií, žádný projekt tohoto workspace |
| Praktický offline profil | **PASS:** `active_workspace_id: null`, žádný katalog, projekt ani výběr v UI |

Příčinou shodného prostředí byla kombinace pevného Vite proxy targetu na portu
8878 a automatického výběru první offline identity ze Studio SQLite. Session nyní
vrací unikátní `runtime_id`, explicitní režim a pouze skutečně připojený workspace
jako aktivní; odpověď má `Cache-Control: no-store`. Frontend session při focusu
obnovuje, změnu runtime promítne do query cache a offline identity neaktivuje.

Praktický smoke proběhl postupným zastavením a spuštěním single-workspace backendu.
Hlavička ukázala přesné ID obou online knihoven, jejich galerie obsahovaly 16 a 85
karet a hlavní profil nepřevzal testovací výběr ani projekty. Offline UI ukázalo
`Offline · bez aktivní knihovny`, nula vybraných médií a žádné karty. Po ověření
byly všechny tři testovací procesy zastaveny. Hash, délka a mtime obou manifestů,
katalogů a Media Desk user dat zůstaly před a po scénáři shodné.
