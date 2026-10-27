# HUHÁČ Launcher v0.2

**Stav:** **IMPLEMENTED** pro lokální Windows správu více samostatných Media Desk prostředí.

Launcher je kompaktní Tkinter aplikace. Spouští pouze jeden Media Desk backend,
nikdy Media Ingest, Normalizer ani jiný analytický procesor.

## Spuštění

V kořeni repozitáře spusť dvojklikem `HUHAC-Launcher.cmd`. Batch odvodí kořen ze
svého umístění, odstraní problematické koncové zpětné lomítko a použije
`.venv\Scripts\pythonw.exe`. Neinstaluje ani neaktualizuje závislosti.

## Profily

Horní seznam vybírá aktivní profil. Každý profil ukládá:

- stabilní interní ID a zobrazovaný název;
- absolutní cestu k jednomu workspace contract v1;
- vlastní kořen `APPDATA` a `LOCALAPPDATA` pro Media Desk data;
- vlastní port v rozsahu `1024–65535`;
- volitelný explicitní Video Keyframes fingerprint;
- buď přesnou dvojici Normalizer fingerprintů, nebo volbu **Bez Normalizeru**.

**Přidat** otevře formulář s výběrem existujícího workspace a samostatného
existujícího adresáře Media Desk profilu. Workspace musí projít veřejným contract
v1 adapterem. **Upravit** zachová port; při skutečné změně workspace zahodí starý
Normalizer výběr, ale nic automaticky nenahrazuje. **Odebrat** odstraní pouze
záznam launcheru. Workspace ani uživatelská data nemaže.

Za běhu backendu jsou profil, workspace, fingerprinty, Normalizer a port zamčené.

## Normalizer snapshot

Po volbě profilu se snapshoty načtou na pracovním vlákně výhradně z veřejného
namespace:

```text
analysis/normalizer/normalizer-v1/<configuration_fingerprint>/<input_set_fingerprint>/
```

Seznam ukazuje datum, počet médií, zkrácené fingerprinty a stav. Úplnou kontrolu
manifestu, workspace identity, katalogu, asset identit a hashů deleguje existujícímu
read-only Media Desk Normalizer adapteru. Invalidní, stale, chybějící nebo
nebezpečný snapshot se může zobrazit diagnosticky, ale nelze jej aktivovat.
Nejnovější snapshot se nikdy nevybírá automaticky. Konfigurace ukládá vždy oba
fingerprinty; částečný a tím nejednoznačný výběr je neplatný.

Volba **Bez Normalizeru** uloží oba fingerprinty jako nepřítomné. Child procesu
launcher odebere případné zděděné Normalizer environment proměnné.

## Port a otevření UI

Port je samostatný pro každý profil. Prázdná, nečíselná nebo mimorozsahová hodnota
zablokuje Start. Launcher náhodný port nevybírá. Obsazený port pouze ohlásí; cizí
proces nepřevezme ani neukončí. Host je pevně `127.0.0.1`.

Tlačítko **Otevřít Media Desk** je dostupné pouze pro launcherem vlastněný běžící
backend a otevírá aktuální `http://127.0.0.1:<port>`.

## Konfigurace a migrace

Aktivní osobní konfigurace schema 2 je na Windows v:

```text
%LOCALAPPDATA%\HUHAC\Launcher\launcher.toml
```

Do Git historie patří pouze neosobní distribuční příklad
`config/launcher.example.toml`:

```toml
schema_version = 2
active_profile_id = "example"
startup_timeout_seconds = 30
shutdown_timeout_seconds = 8
log_max_characters = 65536

[[profiles]]
id = "example"
name = "Nastavit profil"
workspace = "C:\\HUHAC\\workspace"
profile = "C:\\HUHAC\\media-desk-profile"
port = 8878
```

Při prvním startu bez lokální konfigurace Launcher příklad nejprve validuje a
atomicky z něj založí osobní soubor. Pozdější změna distribučního příkladu již
existující profily nemění. Poškozená existující konfigurace se neopravuje ani
nepřepisuje. Volba `--config <path>` umožňuje explicitní diagnostický nebo
testovací soubor a automatické založení v tom případě obchází.

Původní `[launcher]` schema v0.1 se při prvním úspěšném načtení převede atomickým
`os.replace` na jediný profil `Testovací`. Cesty, port a všechny tři fingerprinty
se zachovají. Migrace zapisuje jen launcher TOML; Media Desk profil a jeho
`library-data/<workspace_id>.json` se neotevírají k zápisu.

## Start, Stop a bezpečnost

Start sestaví runtime výhradně z aktivního profilu, před spuštěním znovu validuje
workspace, Keyframes výběr a případný Normalizer snapshot, ověří port a spustí
`python -m media_desk` bez shellu. Readiness vyžaduje úspěšné `GET /health`.

Launcher uchovává přímý `Popen` handle. Stop ukončuje pouze tento proces; nikdy
nehledá PID podle názvu nebo portu a nepoužívá `taskkill`. Výstup je průběžně
odváděn do omezeného redigovaného bufferu. Zavření okna používá stejnou ownership
politiku a vynucené ukončení nabízí pouze pro vlastní nereagující child.

Workspace, originály, ingest SQLite a `analysis/` jsou read-only. Kontrola veřejných
artefaktů zachovává path confinement a odmítá symlink/junction escape.

## Omezení v0.2

- Windows GUI, jeden současně vlastněný backend;
- žádný tray, autostart, Windows Service ani cloudová synchronizace;
- žádné spouštění procesorů nebo automatické přepočítávání fingerprintů;
- žádný automatický výběr nejnovějšího snapshotu nebo volného portu;
- složky profilu musí již existovat;
- launcher nespravuje obsah Media Desk user store, pouze izoluje jeho kořen.
