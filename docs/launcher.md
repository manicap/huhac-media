# HUHÁČ Launcher v0.2

**Stav:** **IMPLEMENTED** pro lokální Windows správu Media Desk a HUHÁČ Studia
nad společnými pracovními profily.

Launcher je kompaktní Tkinter aplikace. Uživatel zvolí **Media Desk** nebo
**HUHÁČ Studio** a Launcher spravuje nejvýše jeden přímo vlastněný backend.
Nikdy nespouští Media Ingest, Normalizer ani jiný analytický procesor.

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

Workspace a port používají obě aplikace. Media Desk navíc používá profilový
`APPDATA`/`LOCALAPPDATA` root a uložené fingerprinty. Studio tyto Media Desk
parametry nemění ani nepřebírá; Project Core SQLite zůstává ve vlastním host-local
`%LOCALAPPDATA%\HUHAC\Studio` rootu. Volba aplikace není nová profilová databáze
a po novém spuštění Launcheru je výchozí Media Desk.

### Python prostředí aplikací

Media Desk a Studio mohou používat rozdílné virtual environments. Bez explicitní
konfigurace Studio používá `.venv` worktree, ze kterého běží Launcher. Media Desk
v linked Git worktree bezpečně odvodí hlavní worktree z `.git` metadata a použije
jeho `.venv`, pouze pokud kandidát obsahuje `pyproject.toml` a `src/media_desk`.
V běžném samostatném checkoutu se použije lokální `.venv`.

Volitelně lze v kořenové části schema 2 TOML nastavit absolutní cesty:

```toml
media_desk_python = "D:\\HUHAC\\media-desk-env\\Scripts\\python.exe"
studio_python = "D:\\HUHAC\\studio-env\\Scripts\\python.exe"
```

Položky jsou nepovinné, takže existující `launcher.toml` zůstává platný a není
automaticky přepisován. Launcher neurčuje správnost prostředí podle přítomnosti
jednoho balíčku. Vybere prostředí podle aplikace, z jeho `pyvenv.cfg` odvodí skutečný
procesní Python a ze stejného prostředí sestaví `VIRTUAL_ENV`, `PATH` a
`site-packages`. Tím zůstává `Popen` handle navázán na skutečný backend a obě
aplikace dostávají vlastní sadu závislostí.

**Přidat** otevře formulář s výběrem existujícího workspace a samostatného
existujícího adresáře Media Desk profilu. Workspace musí projít veřejným contract
v1 adapterem. **Upravit** zachová port; při skutečné změně workspace zahodí starý
Normalizer výběr, ale nic automaticky nenahrazuje. **Odebrat** odstraní pouze
záznam launcheru. Workspace ani uživatelská data nemaže.

Za běhu backendu jsou aplikace, profil, workspace, fingerprinty, Normalizer a
port zamčené. Přepnutí aplikace nebo profilu vyžaduje Stop a nový Start.

## Normalizer snapshot

Pro Media Desk se po volbě profilu snapshoty načtou na pracovním vlákně výhradně z veřejného
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
Při volbě Studia je pole Normalizer zřetelně neaktivní.

## Port a otevření UI

Port je samostatný pro každý profil. Prázdná, nečíselná nebo mimorozsahová hodnota
zablokuje Start. Launcher náhodný port nevybírá. Obsazený port pouze ohlásí; cizí
proces nepřevezme ani neukončí. Host je pevně `127.0.0.1`.

Tlačítko **Otevřít Media Desk** nebo **Otevřít HUHÁČ Studio** je dostupné pouze
pro launcherem vlastněný běžící backend. Stavový řádek uvádí také skutečnou
aplikaci vlastněného procesu. Prohlížeč dostane novou záložku a aplikačně i
konkrétním startem rozlišenou URL ve tvaru
`http://127.0.0.1:<port>/?launcher_app=<application>&launcher_run=<id>`. Parametry
nemění aplikační data; vynutí nový dokument i při střídání obou aplikací na stejném
originu a brání zobrazení starého Studio nebo Media Desk frontendu z browser cache.

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

Starší schema 2 bez `media_desk_python` a `studio_python` se načítá beze změny;
volitelné hodnoty se zapíší pouze při explicitním uložení takto rozšířeného nastavení.

## Start, Stop a bezpečnost

Start sestaví runtime výhradně z aktivního profilu a ověří loopback port. Media
Desk znovu validuje workspace, Keyframes výběr a případný Normalizer snapshot a
spustí nezměněné `python -m media_desk` bez shellu; readiness vyžaduje úspěšné
`GET /health` s `status = ok` a neprázdným `workspace_id`. Samotné HTTP 200 ani
Studio session payload nejsou úspěšná Media Desk readiness.

Studio validuje veřejný workspace contract, vyžaduje existující
`studio/dist/index.html` a spustí projektovým Pythonem
`python -m huhac_studio.cli --workspace <workspace> --host 127.0.0.1 --port <port>
--frontend <repo>/studio/dist`. Nepředpokládá globální `huhac-studio` ani absolutní
cestu k worktree. Readiness vyžaduje `GET /api/studio/session` v režimu `online`
a přesnou shodu `active_workspace_id` s profilem. Chybějící build oznámí s pokynem
spustit ručně `npm run build` v `studio`; Launcher neinstaluje ani nesestavuje frontend.
Media Desk health payload naopak není úspěšná Studio readiness.

Launcher uchovává přímý `Popen` handle. Stop ukončuje pouze tento proces; nikdy
nehledá PID podle názvu nebo portu a nepoužívá `taskkill`. Výstup je průběžně
odváděn do omezeného redigovaného bufferu. Zavření okna používá stejnou ownership
politiku a vynucené ukončení nabízí pouze pro vlastní nereagující child.

Workspace, originály, ingest SQLite a `analysis/` jsou read-only. Studio projektová
SQLite zůstává samostatná a Media Desk user store se při Studio startu nepoužívá.
Kontrola veřejných artefaktů zachovává path confinement a odmítá symlink/junction escape.

## Omezení v0.2

- Windows GUI, jeden současně vlastněný Media Desk nebo Studio backend;
- jeden port na profil je sdílený oběma volbami, protože současný běh obou aplikací
  Launcher nepodporuje;
- offline Studio není v GUI vystaveno; profily vždy reprezentují konkrétní workspace
  a žádný náhradní ani poslední workspace se nepoužije;
- žádný tray, autostart, Windows Service ani cloudová synchronizace;
- žádné spouštění procesorů nebo automatické přepočítávání fingerprintů;
- žádný automatický výběr nejnovějšího snapshotu nebo volného portu;
- složky profilu musí již existovat;
- launcher nespravuje obsah Media Desk user store, pouze izoluje jeho kořen.
