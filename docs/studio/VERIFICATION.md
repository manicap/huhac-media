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
