# Audit převzetí galerie Media Desk do HUHÁČ Studia

**Úkol:** TASK-STUDIO-006

**Stav:** audit dokončen; implementace nebyla zahájena

**Auditovaný stav:** větev `feature/studio-shell`, HEAD `9ceb427`, včetně necommitnutých změn TASK-STUDIO-004/005

**Doporučení:** varianta B — převzít ověřené chování do React modulu, nikoliv vložit původní galerii ani nyní vytvářet společný UI modul

## 1. Rozsah, metoda a ochrana rozpracované práce

Audit je pouze čtení existujícího kódu, testů a dokumentace. Neprováděl reset, clean, merge, rebase, konsolidaci ani úpravu rozpracovaných změn TASK-STUDIO-004/005. Jediným novým souborem je tento dokument. Nebyl spuštěn prohlížečový zátěžový test; vlastnosti, které nelze prokázat ze zdrojového kódu, existujících testů nebo zaznamenaných měření, jsou označeny jako **UNVERIFIED**.

Hlavní zkoumané zdroje:

- původní galerie: `src/media_desk/templates/library.html`, `src/media_desk/static/library.js`, `library.css`, `media-controls.js`;
- katalog a HTTP hranice Media Desk: `src/media_desk/index.py`, `src/media_desk/web.py`, `tests/media_desk/test_web.py`, `test_working_library.py`;
- současné Studio: `studio/src/modules/media-library/MediaLibraryModule.tsx`, `studio/src/data/apiDataSource.ts`, `studio/src/context/studioStore.tsx`, `studio/src/app/StudioShell.tsx`, `studio/src/studio.css`;
- Studio backend: `src/huhac_studio/catalog.py`, `service.py`, `web.py` a `tests/studio/`;
- dokumentace: `docs/media-desk/ARCHITECTURE.md`, `M1_1_DESIGN.md`, `M1_1_1_LAYOUT_DIAGNOSIS.md`, `S2A1_STARTUP_PERFORMANCE.md` a aktuální dokumenty v `docs/studio/`.

### Zjištěný nesoulad dokumentace a kódu

**EXISTUJÍCÍ NESOULAD:** úvodní Studio boundary v `docs/media-desk/ARCHITECTURE.md` stále popisuje React Studio jako syntetické a nenapojené na Project Core. Skutečný necommitnutý stav TASK-STUDIO-005 používá API adaptér, TanStack Query a Project Core. Novější dokumentace Studia odpovídá kódu lépe. Historický soubor nebyl v rámci tohoto read-only auditu měněn; tvrzení se má opravit při nejbližší povolené dokumentační synchronizaci.

## 2. Ověřený stav původní galerie Media Desk

### 2.1 Layout, poměry stran a responzivita

Galerie není běžný seznam všech DOM karet. Šablona vytváří virtualizovaný viewport, canvas a pohyblivé okno; výchozí dávka má 50 položek (`library.html`, blok `#library-app`). JavaScript počítá počet sloupců ze skutečné šířky viewportu a CSS minima dlaždice, odvozuje šířku náhledu a výšku řádku a při změně rozměru zachovává viditelnou kotvu (`library.js:67-81`, `275-318`, `511-524`). Jediným scroll rootem je hlavní obsah aplikace, nikoliv vnořený scroll panel.

Karta má pevnou náhledovou scénu `aspect-ratio: 9 / 16`; fotografie i video v ní používají `object-fit: contain` (`library.css:51-54`). To znamená:

- vlastní poměr obrazu se zachová a obsah se neořízne;
- široké i čtvercové médium může mít výrazný letterbox uvnitř portrétní 9:16 scény;
- výška karet v jednom řádku zůstává stabilní;
- galerie nepoužívá rozměry konkrétního assetu k vytvoření masonry nebo proměnné výšky.

Hustoty mění minimální šířku dlaždice (132/184/240 px) a responzivní CSS dále upravuje minima pro užší viewport (`library.css:1-10`, `109-133`). Tento model je funkční a bez cropu, ale pevná 9:16 scéna není univerzální cílový design pro Studio. Převzít se má princip stabilního boxu + `contain`, nikoliv nutně poměr 9:16.

### 2.2 Přehrávání videa

**IMPLEMENTED:** video element nevzniká při prvním renderu karty. Karta nejprve ukazuje náhled; tlačítko play se zobrazí jen pro video s dostupným `original_url` (`library.js:114-138`). Po explicitním kliknutí `activateVideo`:

- vytvoří `<video>` a teprve pak nastaví URL originálu;
- použije náhled jako poster;
- nastaví `controls`, `preload="metadata"` a `playsInline`;
- nahradí statický náhled přehrávačem a spustí playback (`library.js:479-509`).

Seek zajišťují nativní browser controls a serverové byte ranges. Sdílený `media-controls.js` ukládá lokální hlasitost/mute, spravuje množinu videí a při spuštění nového pozastaví předchozí (`media-controls.js:2-51`). V jednom okamžiku tedy hraje nejvýše jedno spravované video.

**RIZIKO / UNVERIFIED:** obecné odstranění karty při virtualizaci nebo resetu filtru nemá explicitní dispose sekvenci `pause → remove src → load`. Správce odstraní video ze silné `Set` až při události `emptied`; samotné odstranění DOM uzlu ji nemusí vyvolat. Detail explicitně aktivní video pozastaví, ale totéž není prokázáno pro všechny cesty filtru a virtualizace. Původní chování proto nelze bez úpravy převzít jako bezpečný React lifecycle.

### 2.3 Náhledy, lazy loading a výkon

Náhled fotografie pochází z katalogového preview. Pro video se vybírá první keyframe pouze z jednoznačně vybraného platného fingerprintu; chybějící nebo nejednoznačný keyframe skončí placeholderem. HTML obrázku používá `loading="lazy"` a `decoding="async"` (`library.js:114-120`).

Výkon galerie stojí na několika vrstvách:

- renderují se jen viditelné řádky plus tři overscan řádky (`library.js:23`, `252-253`);
- klient drží nejvýše 12 batchů, deduplikuje rozpracované requesty a umí je abortovat (`library.js:24`, `179-220`);
- serverové kurzory obsahují snapshot identity a fingerprint dotazu; změna snapshotu nebo dotazu kurzor zneplatní (`index.py:260-302`);
- preview odpovědi mají ETag a dlouhý immutable cache; originály mají `no-store` (`web.py:1337` a `_serve_original`);
- `window.__MEDIA_DESK_DEBUG__` zpřístupňuje počty DOM dlaždic, requestů a long tasks (`library.js:261`).

Zaznamenané lokální S2A1 měření pro syntetický katalog 10 000 položek uvádí warm-cache p50 přibližně 10,2 ms pro `/library`, 18,0 ms pro `/api/index` a 14,8 ms pro video Range; jde o lokální NTFS benchmark, nikoliv SLA ani důkaz výkonu v NAS/prohlížeči. Existují testy stránkovaného katalogu a kontraktů, ale **UNVERIFIED** zůstává praktická plynulost dlouhého scrollu a dlouhodobá spotřeba paměti při mnoha aktivovaných videích v reálném browseru.

### 2.4 Interakce, výběr a detail

Media Desk podporuje hledání, typ, řazení, event, facety, časový navigátor a hustotu. Kliknutí na vizuál vede do detailu; play má samostatné tlačítko. Návrat z detailu obnovuje filtry a přes session storage také anchor assetu, offset a snapshot.

Původní galerie však nemá obecný single-select ani multi-select pro projektové operace. CSS stav `is-active` označuje kotvu po návratu z detailu, nikoliv uživatelský výběr. Neexistují ověřené šipkové nebo range-selection klávesové zkratky; klávesnice využívá především nativní prvky a Escape pro menu. Akční menu je navázáno na Media Desk eventy, explorer a clipboard, a proto není vhodné k přímému převzetí do Studia.

Technické parametry jsou v API a detailu, ale karta zobrazuje jen omezený souhrn (typ, délka/capture, název a event). „Převzít původní kartu“ tedy samo o sobě nepřinese úplný technický inspektor.

## 3. Ověřený stav modulu Mediální knihovna ve Studiu

### 3.1 Co již funguje

**IMPLEMENTED v rozpracovaném TASK-STUDIO-005:** modul používá serverová data přes úzký API adaptér a TanStack Query. Zustand drží pouze pracovní kontext: workspace, projekt, aktivní modul a vybraná `asset_id`. Uživatel může přepnout mezi celým workspace a médii projektu, označit karty checkboxem a přidat nebo odebrat vazby. Projektové operace používají revision/`If-Match` a konflikt 409 řeší na datové hranici.

Výběr se zachová při přepnutí modulu, ale vyčistí se při změně workspace/projektu (`studioStore.tsx:31-52`) a při změně lokálního pohledu knihovny. To je dobrý základ: projektové vazby jsou stabilní `asset_id`, nikoliv DOM stav karty.

### 3.2 Funkční a výkonové mezery

Současná karta používá pevný box 16:10 a `object-fit: cover` (`studio.css:174-176`). Portrétní a velmi široký obsah se proto ořezává. Modul nevytváří video přehrávač, nezná URL originálu a nezobrazuje rozměry, délku ani další technické parametry.

API adaptér stránkuje backend po 100 položkách, ale v cyklu stáhne všechny stránky před vrácením výsledku (`apiDataSource.ts:202-215`). React pak celé pole mapuje do DOM. Chybí:

- incremental/infinite query a uživatelsky viditelná chyba jednotlivé stránky;
- virtualizace nebo windowing;
- snapshot/cursor ochrana proti posunu výsledků během stránkování;
- abort a omezená klientská cache batchů;
- hledání, filtry, detail a návratová scroll kotva.

TanStack Query má pro query nekonečný `staleTime` a spoléhá na explicitní invalidaci (`StudioApp.tsx:32-35`). To je přijatelné pro Project Core mutace, ale katalog potřebuje definovanou obnovu snapshotu.

### 3.3 Důsledek shell lifecycle

Studio při navigaci moduly neodmountuje; všechny panely zůstávají připojené a neaktivní panel se pouze skryje (`StudioShell.tsx:103-119`, `studio.css:89`). Budoucí přehrávač by proto bez explicitní reakce na `activeModuleId` mohl po odchodu z knihovny pokračovat na pozadí. Výběr médií se má při navigaci zachovat, playback nikoliv.

### 3.4 Současná backendová hranice

`CatalogAsset` ve Studiu poskytuje identitu, typ, dostupnost, zobrazovací název, capture a preview token. Neobsahuje rozměry, délku, MIME originálu ani originální stream URL. Endpoint `/api/studio/artifacts/{token}` servíruje pouze registrované preview artefakty přes `FileResponse`, s MIME/ETag/immutable cache a kontrolou confinement (`huhac_studio/web.py:186-205`). Není to zdokumentovaný ani otestovaný video Range endpoint.

Studio tedy nyní video bezpečně přehrát neumí. Chybějící médium je korektně reprezentováno jako nedostupné a projektová vazba zůstane zachována.

## 4. Srovnání

| Oblast | Media Desk galerie | Studio knihovna | Rozhodnutí |
|---|---|---|---|
| Datový zdroj | read-only workspace katalog + snapshot index | read-only Studio catalog adapter | Zachovat Studio hranici; nečíst Media Desk user store |
| Poměr karty | pevná 9:16 scéna, `contain` | pevná 16:10 scéna, `cover` | Převzít bez-crop princip, poměr navrhnout pro Studio |
| Video | lazy vytvoření po play, native controls | absent | Adaptovat do React komponenty |
| Jeden aktivní player | globální vanilla správce | absent | Implementovat explicitní React controller |
| Cleanup playeru | neúplně prokázaný | absent | Nepřebírat; navrhnout explicitní dispose |
| Stránkování | snapshot cursor, batch cache, abort | backend page/size, klient stáhne vše | Doplnit inkrementální hranici a windowing |
| DOM velikost | viditelné řádky + overscan | všechny assety | Převzít princip virtualizace |
| Preview cache | ETag + immutable | ETag + immutable | Zachovat stávající Studio endpoint |
| Original streaming | 200/206/416, request-scoped validace | absent | Přidat úzký Studio endpoint |
| Hledání/filtry | rozsáhlé | absent | Portovat postupně, ne jako podmínku první etapy |
| Detail a návrat | detail route + anchor restore | absent | Pozdější etapa |
| Projektový multi-select | absent | implementován přes checkboxy a `asset_id` | Zachovat Studio model |
| Modulový kontext | samostatná stránka | Zustand, moduly zůstávají mounted | Výběr zachovat, playback při odchodu zastavit |
| Media Desk event akce | těsně integrované | mimo projektový kontrakt | Nepřebírat |

## 5. Co lze převzít

### 5.1 Převzít přímo nebo s minimální extrakcí

- HTTP sémantiku `Range` z `_byte_range`, `_chunks` a `_serve_original`: jeden byte range, `Accept-Ranges`, správné 200/206/416, `Content-Range`, `Content-Length`, `no-store` (`media_desk/web.py:239-305`). Privátní funkce se nemají importovat napříč aplikacemi bez formalizace; lze je přesunout do malého společného interního helperu nebo znovu použít v novém Studio portu s ekvivalentními testy.
- Opaque token, registraci reference a request-scoped ověření vazby workspace/source root, canonical confinement a dostupnosti. Klient nikdy neposílá filesystem cestu.
- Katalogové preview, ETag a immutable cache.
- Čisté formátovací utility a matematiku výpočtu gridu/anchoru lze extrahovat jako framework-neutral funkce, pokud jsou odděleny od DOM.

### 5.2 Převzít jako chování, ale implementovat pro React

- stabilní karta bez cropu a s placeholderem;
- obrázek lazy, video element až po play;
- nejvýše jeden aktivní player a sdílená lokální preference hlasitosti;
- batch cache, abort, overscan, návratová kotva a detekce změny snapshotu;
- oddělení akcí „vybrat“, „přehrát“ a „otevřít detail“;
- offline/error stavy přímo na kartě.

`library.js`, `media-controls.js` ani celý `library.css` se nemají přímo vložit do React komponenty. Používají imperativní DOM, globální stav a shell-specific selektory. Přímá kopie by vytvořila druhý lifecycle uvnitř Reactu.

### 5.3 Nepřebírat

- Media Desk event/session akce a user-data schema;
- URL/form stav původní stránky jako druhý zdroj pravdy vedle Zustand/TanStack Query;
- fixní 9:16 design jako povinný Studio kontrakt;
- globální silnou `Set` video elementů bez explicitního cleanupu;
- přímé filesystem cesty, fyzické kopírování médií nebo zápisy do processor-owned workspace;
- závislost Studio projektu na Media Desk user store.

## 6. Varianty integrace

### Varianta A — přímo použít původní galerii

Možnosti jsou iframe, vložená Jinja stránka nebo spuštění vanilla galerie uvnitř React wrapperu.

**Výhody:** nejrychleji zachová existující vizuál, filtry, virtualizaci a streamování.

**Nevýhody:** dva routery a dva zdroje UI stavu; obtížné napojení projektového multi-selectu, revision konfliktů a Zustand kontextu; duplicitní styling a lifecycle; případné cross-origin/session komplikace.

**Riziko:** vysoké. Vytvořilo by to cizí aplikaci uvnitř Studia a dlouhodobě dvě knihovny.

### Varianta B — adaptovat ověřené chování do React modulu

React zůstane vlastníkem karet, výběru, query stavu a lifecycle. Z Media Desk se převezmou kontrakty a ověřené principy: no-crop, lazy video, jeden player, Range, batch/snapshot a virtualizace.

**Výhody:** čisté napojení na workspace/project context, jedna interakční logika, možnost explicitního cleanupu a postupného dodání.

**Nevýhody:** je nutné znovu implementovat a otestovat části chování; vizuální shoda nevznikne automaticky.

**Riziko:** střední a dobře řiditelné etapami.

**Doporučení:** **zvolit tuto variantu**.

### Varianta C — vyčlenit společný samostatný modul

Společný modul by mohl být framework-neutral katalog/index + streaming port, Web Component, nebo nová sdílená UI knihovna.

**Výhody:** jedna budoucí implementace složité galerie a sjednocené kontrakty.

**Nevýhody:** současná UI jsou v různých paradigmatech; sdílené UI by vyžadovalo přepsat i Media Desk nebo zavést Web Component lifecycle a nový release boundary. To je výrazně větší architektonické rozhodnutí.

**Riziko:** vysoké pro aktuální milník. Smysl může mít později pro framework-neutral index/streaming helpery, nikoliv nyní pro společný vizuální modul.

## 7. Doporučené cílové řešení

### 7.1 React komponenty a stav

Navržené minimum:

- `MediaLibraryModule` vlastní query, filtry/pohled a projektové mutace;
- `MediaGrid` vlastní windowing a anchor;
- `MediaCard` dostává normalizovaný asset a oddělené callbacky `onSelect`, `onPlay`, případně `onOpenDetail`;
- `VideoPlayer` dostává pouze autorizovanou opaque URL a má explicitní `dispose`;
- lokální `PlaybackController` drží nejvýše jedno aktivní `asset_id`; nepatří do sdíleného Zustand pracovního kontextu.

Při změně aktivního playeru, workspace nebo projektu a při unmountu karty se provede `pause()`, odstranění `src` a `load()`. Při odchodu z modulu se playback vždy pozastaví; lze ponechat právě jeden pozastavený player pro rychlý návrat, ale nikdy ne více skrytých aktivních zdrojů. Pokud virtualizace aktivní kartu vyřadí, uloží se nanejvýš lokální čas jednoho playeru a zdroj se uvolní.

Výběr zůstává množinou stabilních `asset_id` v pracovním kontextu a je nezávislý na renderovaném okně. Play ani otevření detailu nesmí checkbox přepnout. Přidání/odebrání vazeb invaliduje detail projektu a projektová média, ale nesmí měnit fyzický soubor.

### 7.2 Úzké backendové rozšíření pro video

Nejmenší bezpečné rozšíření Studio read-only katalogu:

1. doplnit do DTO rozměry, délku, MIME/velikost podle dostupného workspace contractu a opaque `original_url` pouze pro validní dostupný originál;
2. přidat samostatný endpoint, například `/api/studio/originals/{token}`; stávající preview `/artifacts/{token}` ponechat immutable a významově čistý;
3. při každém requestu ověřit token, workspace/catalog binding, source root a canonical confinement včetně symlink hranice;
4. otevřít soubor jednou, použít `fstat`, podporovat jeden byte range a vracet 200/206/416, `Accept-Ranges: bytes`, správný MIME a `Cache-Control: no-store`;
5. při offline/chybějícím souboru vrátit 404, ale nijak neměnit katalog ani projektovou vazbu.

Rozšíření je read-only. Nesmí zapisovat do Media Desk user store, processor-owned analýz ani měnit workspace contract. Studio SQLite zůstává source of truth pouze pro projekty a jejich vazby.

### 7.3 Etapy

1. **Korektní karta a metadata.** Zavést `MediaCard`, přejít z `cover` na `contain`, zvolit stabilní responzivní box, doplnit rozměry/délku/MIME a offline/placeholder stavy. Zachovat současný checkbox a projektové mutace.
2. **Bezpečné video.** Přidat read-only original endpoint s Range testy, lazy `VideoPlayer`, právě jeden aktivní player a explicitní cleanup při navigaci, změně kontextu a vyřazení karty.
3. **Interakční integrace.** Zpevnit oddělení select/play/detail, klávesnicovou dostupnost, potvrzené mutace a návrat z detailu bez ztráty projektového výběru.
4. **Výkon velkého katalogu.** Nahradit eager načtení všech stran inkrementálním snapshot/cursor kontraktem a virtualizovaným gridem; doplnit abort, omezenou cache, anchor restore a měření DOM/request/long-task.
5. **Pokročilé hledání a filtry.** Přenášet jen filtry, které mají jasný Studio use case; neimportovat Media Desk event ownership.

Pořadí 1–4 respektuje požadovanou prioritu uživatelského postupu. Před nasazením na skutečně velký katalog musí být dokončena etapa 4; etapa 2 sama o sobě je bezpečná jen proto, že video vzniká až po kliknutí a controller povolí jediný player.

## 8. Nejbližší implementační etapa

**Doporučený bezprostřední slice:** etapa 1, bez nových npm závislostí a bez databázové migrace.

Rozsah:

- rozšířit read-only katalogové DTO jen o již existující technická metadata;
- vytvořit samostatnou React kartu;
- zachovat celý současný project-link workflow;
- opravit no-crop zobrazení obrázků a video posterů;
- doplnit komponentové/API testy pro široký, čtvercový, portrétní, video a offline asset;
- zdokumentovat veřejný DTO kontrakt ve stejné změně.

Hrubý odhad: 6–10 dotčených souborů, 3–5 cílených testů, přibližně 1–2 vývojové dny. Etapa nezahrnuje playback ani performance přestavbu. Následující video slice bude vyžadovat samostatně přibližně 6–10 souborů a backendové Range/bezpečnostní integrační testy.

## 9. Rizika a otevřené otázky před implementací

- Rozhodnout cílový stabilní poměr karty Studia; audit doporučuje `contain`, ale nepředepisuje 9:16.
- Ověřit, která technická metadata jsou garantována workspace contractem pro image i video a která mohou být `null`.
- Rozhodnout, zda společný Range helper bude interní sdílená Python utilita, nebo ekvivalentní Studio implementace. Import privátních funkcí Media Desk není veřejný kontrakt.
- Definovat snapshot invalidaci Studio katalogu před zavedením cursoru; stránkování pouze číslem stránky není stabilní při změně katalogu.
- Doplnit skutečný browser stress test pro tisíce karet, opakované play/scroll/filter a kontrolu uvolnění síťových i DOM zdrojů. Do té doby je dlouhodobá paměťová stabilita **UNVERIFIED**.
- Opravit zastaralé tvrzení o syntetickém Studiu v `docs/media-desk/ARCHITECTURE.md`, až bude povolena širší dokumentační synchronizace.

## 10. Závěr

Původní Media Desk galerie obsahuje hodnotné, prakticky ověřené principy: no-crop kartu, lazy vytvoření videa, byte-range stream, snapshotové dávky a virtualizaci. Její UI kód ale není vhodný k přímému vložení do React Studia a nemá projektový selection model. Současné Studio naopak správně vlastní workspace/project kontext a vazby přes `asset_id`, ale ořezává náhledy, načítá celý katalog a nemá video transport ani lifecycle.

Nejnižší dlouhodobé riziko má varianta B: zachovat React a Project Core hranice, adaptovat ověřené chování, přidat úzký read-only streaming kontrakt a dodávat po etapách. Datové vlastnictví se tím nemění a žádná etapa nevyžaduje zápis do uživatelských dat Media Desk ani processor-owned workspace.
