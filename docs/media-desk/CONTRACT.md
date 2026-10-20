# HUHÁČ Media Desk — implementační kontrakt v0.1

**Určeno pro:** Codex
**Repozitář:** `manicap/huhac-media`
**Výchozí větev:** `main`
**Nová pracovní větev:** `feature/media-desk`
**Stav dokumentu:** návrh požadavků pro implementaci; není popisem již hotového Media Desku
**Datum:** 2026-10-20

## 0. ZADÁNÍ CODEXU — JAK ZAČÍT

1. Ověř synchronizovaný a čistý pracovní strom a nejnovější `main`; zkontroluj dokumentaci a testy. **Nezahazuj lokální změny.** Při konfliktech nebo nečistém stromu zastav a nahlas je.
2. Vytvoř z `main` novou větev `feature/media-desk` (nepřepisuj existující větev). Žádné `force push`.
3. Přečti zejména `README.md`, `docs/system-overview.md`, `docs/workspace-contract.md`, `docs/media-ingest.md`, `docs/session-grouper.md`, `docs/video-keyframes.md`, `docs/vision.md`, `docs/faces.md`, `docs/development.md` a `pyproject.toml`.
4. Přidej tento kontrakt do `docs/media-desk/CONTRACT.md`. Pokud je jiná implementace v rozporu s jeho požadavky nebo existujícími veřejnými kontrakty, nejprve konflikt zdokumentuj; **neprováděj tiché změny**.
5. Implementuj **pouze etapu M1** popsanou níže. Nezačínej import, přesouvání originálů, rozsáhlé storage adaptéry ani změny v existujících procesorech.
6. Po M1 předej soupis souborů, příkazy pro spuštění, testy, známá omezení, commit SHA a návrh další malé etapy. Push do pracovní větve pouze dle zavedeného workflow a oprávnění.

## 1. PROČ MEDIA DESK VZNIKÁ

Uživatel potřebuje rychle zpracovávat další fotografie a videa z hudebního klubu Huháč: importovat je, prohlížet, vyhledávat souvislosti, označovat použitelný materiál a otevírat originály v externích editorech včetně DaVinci Resolve. Nechce zbytečnou administrativu ani několik kopií stejných originálů. Přístup má fungovat z Windows i Linuxu, primárně přes lokální web.

Media Desk **není** nový analytický engine ani nový editor. Je to malá webová pracovní aplikace a orchestrátor existujících modulů. Výstupem má být užitečná galerie a pracovní výběr, ne pouze technický dashboard.

### Existující stabilní komponenty — nezměnit jejich chování

- Media Ingest Tool v1 — identita SHA-256, zdrojová historie, metadata, obrázkové náhledy a veřejný workspace.
- Session Grouper v1 — seskupení podle času, nikoli rozpoznání skutečné akce.
- Video Keyframe Extractor v1 — reprezentativní JPEG snímky z videí; v1 není shot detector.
- Vision Processor v1 — validované vizuální popisy prostřednictvím Ollama.
- Faces Processor v1 — anonymní detekce / embeddings / clustery, nikoli identifikace osob.

Současný veřejný vstup je `workspace.json` → `metadata/catalog.json`; `workspace_contract_version == 1`. Interní ingest SQLite není veřejné API. Procesory zapisují výstupy do vlastních `analysis/<processor>/` jmenných prostorů.

## 2. ARCHITEKTONICKÉ POJMY

**Inbox:** dočasný příjmový prostor pro soubory a ZIP, bez povinné automatické integrace Google Drive. V první etapě mimo rozsah.

**Media Storage:** fyzicky uložené originály; mohou být na NAS/SMB, lokálním disku nebo externím SSD. Originály zůstávají neměnné. V rámci spravované storage preferovat jednu fyzickou kopii identického obsahu; kopie pro zálohu není považována za pracovní duplicitu.

**Metadata Storage:** přenosný souborový prostor s veřejnými JSON katalogy, náhledy, výsledky analýz a případně oddělenými uživatelskými údaji Media Desku. Může být na jiném zařízení než Media Storage, včetně SMB sdílení. Není automaticky totožná s interním běhovým adresářem ingestu.

**Runtime Storage:** lokální/pod kontrolou jediného backendu: fronta úloh, logy aplikace, cache, pracovní soubory a interní zapisovatelné databáze. Žádné současné otevírání SQLite více stroji přes SMB; pro ingest zachovat jeho stávající interní pravidla a nemanipulovat s jeho databází přímo.

**Workspace:** logická jednotka veřejného kontraktu pipeline; identifikována `workspace_id`, nezaměňovat se Storage a Metadata Storage.

**Media Desk Library:** budoucí logický pohled / kolekce nad jedním či více workspace; více storages ve stejném pohledu není požadavek M1.

## 3. ZÁSADY NEZÁVISLOSTI A PŘENOSITELNOSTI

1. Aplikace nesmí mít zakódované `D:\`, `/mnt/nas`, IP adresu ani konkrétní SMB server. Vnější fyzické cesty jsou lokální konfigurace backendu.
2. Uchovávat stabilní identitu assetu ze stávajícího SHA-256; pro umístění používat **logický storage identifikátor + relativní cestu**. To je **budoucí návrh Media Desk vrstvy**, nikoli existující vlastnost `workspace_contract_version: 1`.
3. Stávající ingest `source_root` je absolutní cesta a některé procesory otevírají originály přes `source_root` + aktivní `relative_path`. **Nezaměňovat to za hotovou podporu remapování.** M1 jen čte; pozdější řešení musí explicitně ověřit kompatibilitu a bezpečně aktualizovat zdrojové cesty schváleným postupem (např. opětovným ingestem), nikoli editací katalogových JSON ručně.
4. Originály neměnit, neodstraňovat a neimportovat stejný obsah duplicitně. Rozlišovat mezi fyzickým originálem a generovanou proxy/cache.
5. Metadata mají zůstat čitelná i bez dostupných originálů: galerie může použít existující náhledy a oznámit `original offline`. Nezobrazovat nefunkční originální cestu jako platnou.
6. Oddělené umístění originálů/metadat je cílový návrh, ne povinnost přestěhovat data před M1. Existující workspace musí jít otevřít **read-only** v původním stavu.
7. Windows a Linux jsou klientské platformy. Backend a procesory běží vždy na definovaném hostiteli; browser nemá přímý přístup k souborovým cestám serveru. M1 neřeší distribuované processing workers.
8. V jedné metadata storage může mít v jednom okamžiku právo zápisu nanejvýš jeden správce. Běžní klienti přistupují přes HTTP/API, nikoli přímo k interní SQLite.

## 4. CÍLOVÝ WORKFLOW (VÍCE ETAP, NE IMPLEMENTACE M1)

1. Uživatel stáhne ZIP z Google Drive nebo připraví lokální složku.
2. Importer bezpečně rozbalí/staguje soubory v Inboxu, ověří formáty, velikosti a SHA-256; odmítne zip-slip, symlinky / nebezpečné názvy a zip-bomby; selhání nesmí smazat vstup.
3. Storage Manager uloží unikátní originál do Media Storage atomicky a po kontrole integrity; při existující identitě pouze vytvoří zdrojovou vazbu. Pozdější klasifikace nesmí měnit fyzickou adresu originálu.
4. Stávající Media Ingest vytvoří / aktualizuje workspace a veřejný katalog. Navazující procesory lze spouštět odděleně a opakovaně; respektují vlastní fingerprint a reuse.
5. Media Desk zobrazí foto/video, náhled, relaci, stav analýzy, vizuální popis a anonymní shluky obličejů. Uživatel může označit zajímavé assety a sestavit výběr.
6. Otevírání ve vnějších editorech používá platnou cestu viditelnou **na hostiteli editoru**, ne webovou URL předstírající cestu. Export manifestu s identitou a relativními odkazy je základ; hardlinky pouze na stejném FS, symlinky jen po ověření kompatibility, žádné tiché fyzické kopie.

## 5. ZÁLOHA A RELOKACE — CÍLOVÉ SCÉNÁŘE

**A. Úplný přenos:** konzistentní export originálů + veřejných metadat/analýz + uživatelských údajů + manifest SHA-256, případně náhledů. Na novém systému ověřit identitu a mapování, nepouštět drahé analýzy zbytečně znovu. Uložené výsledky musí být ověřeny vůči vstupům a konfiguraci, ne pouze nalezeny podle jména.

**B. Jen originály:** kopírovat soubory; na novém místě vytvořit nový workspace a znovu zpracovat. Vlastní anotace, hodnocení a kolekce se bez samostatného exportu nepřenášejí.

**C. Jen metadata:** povolit prohlížení dostupných náhledů a záznamů bez přístupných originálů; znovupřipojení Media Storage řešit validací identit a mapováním cest.

Kontrakt export/import formátu, snapshot při současných zápisech, UUID storage a relokační algoritmus teprve navrhnout v samostatné etapě. Nevydávat „kopírovat složku za běhu“ za garantovanou konzistentní zálohu.

## 6. TECHNICKÝ SMĚR (LEHKÝ, NIKOLI PŘEDEPSANÝ FRAMEWORK NAVŽDY)

- Backend: Python 3.11+, preferovaně FastAPI.
- Frontend: server-rendered HTML, HTMX + minimum JavaScriptu, lehké CSS. Bez povinného React/Vue buildu.
- Rozhraní: jednoduché REST endpoints pro katalog a náhledy; později úlohy a SSE stav.
- Pro pozdější orchestraci používat existující **CLI procesy přes bezpečné `subprocess` argumenty**, nikdy shell interpolation ani import interních tříd procesorů. Jejich public JSON je integrační hranice.
- Nepřidávat Celery, Redis, PostgreSQL, Docker nebo distribuovaný cluster pro MVP.
- Prohlížení galerie: stránkování, lazy loading, bezpečné načítání náhledů; nerozbalit stovky originálních videí do paměti.
- Video: v M1 zobrazit existující keyframe jako thumbnail a bezpečné otevření/stream originálu jen pokud je dostupný, s HTTP Range podporou nebo dokumentovaným omezením přehrávání.
- Provoz: výchozí bind `127.0.0.1`; přístup z LAN pouze po explicitní konfiguraci a vyřešení autentizace. Žádné veřejné upload ani spouštění příkazů bez ochrany.

## 7. ETAPY A AKCEPTACE

### M1 — Read-only galerie existujícího workspace **(JEDINÝ IMPLEMENTAČNÍ ÚKOL NYNÍ)**

**Rozsah:**
- Nový samostatný Python balíček (navržený název `src/media_desk/`) s izolovanými závislostmi a CLI `media-desk` pro spuštění web serveru. Nezasahovat do interního ingestu a analyzátorů.
- Konfigurovat jedno umístění **existujícího** workspace pomocí argumentu/env/config; nevyžadovat migraci adresářů ani import.
- Validovat `workspace.json`, major contract verzi, `workspace_id` a `metadata/catalog.json`. Chyby zobrazovat srozumitelně, bez tracebacks v prohlížeči.
- Galerie dostupných assetů (image/video), stránkování, filtrování podle typu, zdrojový název, capture time, technické údaje, asset ID.
- Obrázky zobrazovat ze stávající `preview_location`; pro videa zobrazit kompatibilní dokončené keyframes, pokud existují. Při více fingerprints nevybírat nahodile: nabídnout explicitní výběr konfigurace nebo jednoznačně označený stav bez náhledu.
- Zobrazit seskupení Session Grouper v1, je-li dostupné; **nenazývat relaci automaticky známou událostí**.
- Na detailu assetu zobrazit dostupné úspěšné Vision/Faces výsledky, model/provenance a stav chybějících výsledků; u Faces anonymní skupiny bez tvrzení identity.
- Při nedostupném originálu zachovat browse metadata a dostupné náhledy; bezpečně označit „originál offline“.
- Striktně read-only vůči workspace: žádná změna ingest databáze, veřejných JSON, originálů nebo `analysis/`.
- File-serving zabezpečit proti `..`, URL encoding obcházení, symlink escape, neautorizovanému přístupu k libovolným cestám a čtení interní SQLite. Povolit pouze odvozené public artifact cesty a oprávněné originály.
- Přidat FAST testy: validní workspace, chybné kontrakty, chybějící artefakty, offline originál, více fingerprintů, filtrování, stránkování, path traversal, read-only chování. Testy nesmí vyžadovat skutečná média ani modely.
- Dokumentovat instalaci, start na Windows/Linux, demo se syntetickým workspace a omezení.

**Akceptace M1:**
1. Spustím web proti existujícímu workspace bez změny jeho obsahu a bez zvláštních migrací.
2. Otevřu stovky položek bez načtení všech originálů do browseru.
3. Vidím fotografie, reprezentativní náhledy videí, data, časové relace a existující AI výsledky.
4. Při výpadku NAS neztratím galerii ani metadata již dostupná v metadata storage; odkazy na offline originály jsou jasně označené.
5. Testy ochrany cest a read-only režimu projdou; stávající testy pipeline zůstanou zelené.
6. Předložené screenshoty / krátký popis průchodu potvrzují funkční UI; nevyvozovat UX kvalitu jen ze zelených testů.

### M2 — Storage registry a oddělené umístění dat **(AŽ PO SCHVÁLENÍ M1)**

- Návrh a otestování storage identit, logických mapování (`storage_id` + relativní cesta), mount pointů Windows/Linux a offline režimu.
- Explicitně vyřešit vazbu na stávající absolutní `source_root`, včetně kompatibilního přepojení; zachovat smluvený v1 veřejný kontrakt, pokud lze, jinak předložit návrh verze a migrace ke schválení.
- Rozhodnout, zda backend čte metadata ze SMB pouze read-only, zatímco ingest runtime zůstává lokální. Sdílení zapisovatelné SQLite přes SMB nepovolit.
- Po úspěšném ověření možnost konfigurovat Media Storage a Metadata Storage odděleně.

### M3 — Orchestrátor existujících CLI **(AŽ PO SCHVÁLENÍ M2)**

- Pořadí závislostí ingest → session + keyframes → vision + faces (s respektováním vstupních podmínek).
- Spouštět oddělené procesy, zobrazovat progres, logy, chyby, reuse; maximálně jedna paměťově náročná úloha současně na slabším PC.
- Žádný distribuovaný worker ani tiché paralelní mutace jedné metadata storage.

### M4 — Inbox / import ZIP a deduplikované Media Storage **(AŽ PO SCHVÁLENÍ M3)**

- Bezpečný staging, integrita, atomické převzetí, no-overwrite; kontrola účinku opakovaného importu.
- Definovat a schválit umístění a názvy originálů před zápisem produkčních dat.
- Bez automatického přístupu do Google účtu; uživatel poskytne ZIP/složku.

### M5 — Uživatelské výběry a přenositelné exporty **(AŽ PO SCHVÁLENÍ M4)**

- Oblíbené, hodnocení, kolekce, ruční zařazení odděleně od analytických výsledků.
- Export manifestu a dva režimy přenosu (celý archiv / jen originály) plus validovaná obnova. Případné výstupy pro DaVinci až podle konkrétního workflow.

## 8. VÝSLOVNÉ NON-GOALS PRVNÍHO MVP

Google Drive API, NAS správa a konfigurace SMB serveru, cloud sync, více souběžných zapisovatelů, editace originálů, identifikace osob, automatická identifikace akcí, inteligentní střih, automatické publikování na sociální sítě, SceneForge integrace, GPU tuning, nové AI modely, redesign již schválených procesorů.

## 9. PRAVIDLA KVALITY A PŘEDÁNÍ

- Malé, oddělené, ověřitelné commity. Úpravy existujících modulů pouze po zdůvodněné potřebě a jasné kompatibilitě.
- Testuj jen to, co bylo skutečně spuštěno; odlišuj fake testy, reálnou integraci, ruční kontrolu UI a neověřené scénáře.
- Ověř `git status`, změny a relevantní testy před commitem; žádná produkční média, credentials ani lokální config v Gitu.
- Po M1 zastav. Zpráva musí obsahovat: implementováno / neimplementováno; seznam dotčených souborů; výsledky testů; přesné start příkazy Win/Linux; omezení; SHA commitu; návrh M2 bez jeho implementace.

**Hlavní kritérium úspěchu:** uživatel může rychle prohlížet a využívat dříve vytvořený mediální katalog z běžného prohlížeče; přitom zůstanou původní originály, metadata a procesory bezpečně nedotčené.
