# Media Connector — navržený implementační plán

**Stav:** PROPOSED / AWAITING APPROVAL

**Aktuální etapa:** dokumentace pouze; žádný bod níže není implementovaný

## MC1 — read-only lokální discovery (doporučená první etapa)

MC1 záměrně nečeká na rozhodnutí o zápisu do Media Storage. Dodá samostatný
balíček, společné doménové typy, lokální adaptér a strojově čitelný dry-run.

Navržený rozsah:

1. veřejný JSON kontrakt dry-run výstupu včetně stabilních chybových kódů;
2. `SourceAdapter` protocol a contract test suite;
3. lokální read-only adaptér s deterministickou stránkovanou enumerací;
4. confinement, symlink/reparse-point ochrana a kontrola změny souboru;
5. plánovací výstup na stdout nebo atomicky do explicitního souboru;
6. žádné kopírování, journal DB, OAuth, workspace zápisy ani spuštění Ingestu.

### Akceptační kritéria MC1

- stejný nezměněný strom vytvoří deterministicky ekvivalentní plán;
- soubor a adresář unikající přes symlink/reparse point jsou odmítnuty;
- traversal, absolutní a platformně nebezpečné cesty jsou odmítnuty;
- změna velikosti/mtime mezi plánem a otevřením má stabilní
  `SOURCE_CHANGED` výsledek;
- permission denied, offline root, neexistující kořen a kolize jsou rozlišeny
  strojovými kódy;
- Windows i nativní Linux mají cílené filesystem testy; neprovedená platforma
  zůstane označena **UNVERIFIED**;
- žádný test ani runtime zápis nenastane ve workspace, Media Storage nebo ingest
  SQLite;
- code-versus-documentation kontrola potvrdí, že status nehlásí transfer či
  Google Drive jako hotový.

## MC2 — Google Drive read-only discovery

Po schválení auth a privacy rozhodnutí doplní samostatný Google Drive adaptér,
OAuth, stránkování, kvóty, shared-drive politiku a fake-server contract testy.
MC2 ještě nemusí stahovat obsah. Povinné jsou testy redakce tokenů, expirace,
odvolaného souhlasu, pagination restartu, shortcut cyklu a cloud dokumentu.

## MC3 — transfer, ověření a recovery

Začne až po schválení MC-Q03, MC-Q04, kolizní a retenční politiky. Implementuje
dočasné soubory, limity, SHA-256 transferu, journal, restart a atomickou
publikaci immutable delivery. Fault-injection testy pokryjí přerušení po každé
stavové hraně, plný disk, změnu zdroje, síťový timeout a opakovaný publish.

## MC4 — explicitní handoff

Ověří interoperabilitu hotové delivery s nezměněným Media Ingest CLI. Bez
samostatného schválení nepřidá automatickou orchestraci ani změnu workspace
contractu. End-to-end test musí dokázat, že Ingest sám určí SHA-256 asset identity
a Connector nečte jeho SQLite.

## Dokumentační brány každé etapy

Před implementací se znovu porovná tento návrh s kódem a aktuální projektovou
dokumentací. Ve stejné změně se aktualizují alespoň zdejší `STATUS.md`,
`DECISIONS.md`, relevantní kontrakt a uživatelský návod. Globální dokumenty se
změní jen po schválení názvosloví a integračních rozhodnutí.
