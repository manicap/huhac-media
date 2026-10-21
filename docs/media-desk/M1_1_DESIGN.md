# HUHÁČ Media Desk M1.1 — návrh implementace

Datum inventury: 2026-10-21. Výchozí commit: `8472fb05ed2c3317f9efb8d5f4b56c56ad9edb42`.

## Skutečný stav M1

M1 je samostatný FastAPI balíček `src/media_desk`. Při startu načte veřejný
`workspace.json` a `metadata/catalog.json` do neměnného `WorkspaceSnapshot`.
Nečte ingest SQLite ani neimportuje procesory. Čte pouze veřejná metadata a
validované výsledky Session Grouperu, Video Keyframes, Vision a Faces. Opaque
registry artefaktů chrání náhledy a originály; originály podporují HTTP Range.

Existující routy jsou `/` (stránkovaná galerie), `/assets/{sha256}`,
`/api/assets`, `/api/assets/{sha256}`, `/artifacts/{token}` a `/health`.
Frontend tvoří Jinja šablony a jediný CSS soubor, bez JavaScriptu. Řazení M1 je
capture time sestupně a `asset_id` sestupně; stránkování používá číslo stránky.

Rozdíly proti M1.1:

- `/` je galerie s velkou hero sekcí, nikoliv kompaktní Přehled;
- M1 nemá samostatnou Knihovnu, Kalendář ani timeline relací;
- M1 slučuje odkazy ze všech validních Session Grouper výsledků a neuchovává
  `operational_day` ani `unassigned`; M1.1 bude používat výsledek jen tehdy,
  když je dostupný právě jeden jednoznačný validní snapshot;
- M1 API stránkuje offsetem. Kvůli kompatibilitě zůstane přijímání `page` a
  `page_size`, ale nové UI použije stabilní range/cursor rozhraní.

## Routy M1.1

- `GET /` — kompaktní Přehled.
- `GET /library` — shell virtualizované galerie; query `media_type`, `q`,
  `sort`, `active_asset_id`, volitelně `date_from`/`date_to`.
- `GET /assets/{sha256}` — detail, rozšířený o návratový kontext a sousedy.
- `GET /calendar` — rok/měsíc/den ze serverové agregace.
- `GET /relations` — roční timeline jednoznačně vybraného Session Grouper
  výsledku; vždy označená jako automatické časové skupiny, nikdy Event.
- `GET /api/assets` — kompatibilní M1 stránkování a nový cursor/range režim.
- `GET /api/index` — časové segmenty a počty pro aktuální filtr.
- `GET /api/locate` — přímý index assetu nebo prvního assetu měsíce/dne.
- `GET /api/calendar` — agregace rok/měsíc/den bez načítání assetů klientem.
- stávající detail, artifact a health routy zůstávají kompatibilní.

## Snapshot, řazení a cursor

`LibraryIndex` vznikne jednou při startu nad již validovaným snapshotem. Jeho
`snapshot_id` je SHA-256 kanonického souhrnu `workspace_id`, catalog
`generated_at` a seřazených identit/podstatných indexových polí. Index nedekóduje
média, nepřepočítává hash souborů a nespouští inference.

Podporované řazení je `captured_desc` a `captured_asc`. Parseovatelný capture
čas se porovnává jako zdrojový local wall-clock bez převodu na časovou zónu
stroje. Neznámé datum následuje za datovanými položkami v obou směrech.
Tie-break je vždy `asset_id` vzestupně. Každé `asset_id` je právě jednou.

Opaque cursor je URL-safe base64 kanonického JSON s verzí, `snapshot_id`,
otiskem filtrů a sortu a absolutním start indexem. Server ověří všechny vazby;
cursor ze starého snapshotu nebo jiného filtru vrátí HTTP 409 se stavem
`snapshot_changed`, nikoli smíšenou dávku. `limit` má výchozí hodnotu 50 a
rozsah 10–100. Odpověď obsahuje `items`, `next_cursor`, `prev_cursor`,
`start_index`, `total_count` a `snapshot_id`. Přímý `start` slouží locatoru a
virtualizaci; není veřejným nestabilním offsetem mezi různými snapshoty,
protože požadavek nese `snapshot_id`.

Locator vrací index a zarovnaný začátek dávky bez sekvenčního čtení. Umí
`asset_id`, `year` + `month` a volitelně `day`. Časové segmenty jsou odvozeny
ze stejného filtrovaného pořadí.

## Datum a kalendářní politika

ISO-8601 hodnotu interpretujeme jako její zapsané wall-clock datum. Offset se
uchová a zobrazuje, ale datum se tiše nepřevádí do lokální zóny serveru.
Naivní čas zůstává naivní a UI jej označí jako čas bez zóny. Hodnota s
`filesystem_fallback: true` má nízkou důvěru a je v sekci „Nezařazeno podle
data“, stejně jako neznámé či nevalidní datum; kalendář ani časová lišta ji
nevydává za důvěryhodné datum pořízení. Search/type filtry se aplikují shodně
na galerii, časové segmenty a kalendář.

Relace používá `operational_day` publikovaný Session Grouperem; pokud chybí,
pro roční seskupení použije datum začátku bez rozdělení relace přes půlnoc.
Assety v relaci zůstávají v pořadí publikovaném procesorem. `unassigned` se
zobrazuje pouze s doloženým důvodem z výsledku.

## UI a zachování kontextu

Společný český shell nabízí Přehled, Knihovnu, Kalendář a Časové relace a
sbalitelný levý panel. Knihovna používá předvídatelnou výšku řádku a skutečné
windowing: v DOM jsou pouze řádky viewportu plus overscan. Horní a dolní spacer
reprezentují zbytek výsledku. Omezená LRU cache drží nejvýše 12 dávek; fetch je
deduplikovaný, při změně query zrušený přes `AbortController`. Obrázky mají
rozměry/aspect ratio, `loading=lazy`, skeleton a `object-fit: contain`.

URL nese filtr, sort a aktivní asset. `history.state`/`sessionStorage` nese
anchor `asset_id`, jeho offset vůči viewportu a poslední library URL. Návrat
načte locator a pouze dávky kolem anchoru. Resize znovu ukotví asset, nikoliv
absolutní scrollTop. Back/Forward zpracuje `popstate`. Při chybě dávky se
spinner ukončí, zobrazí se retry a fallback „Načíst další“.

Pravý časový navigátor používá serverové segmenty a locator. Aktivní segment
se řídí první viditelnou kartou. Na úzkém viewportu se změní na select. Je
zobrazen jen při chronologickém řazení.

## Kompatibilita a bezpečnost

Veřejný workspace kontrakt i procesorové JSON zůstávají beze změny. Mění se
pouze interní read-only model Media Desku. Artifact registry, kontrola
traversalu/symlinků a Range obsluha se znovu použijí. Statické náhledy dostanou
ETag a immutable cache podle tokenu odvozeného z identity artefaktu; originály
se neoznačí jako immutable. M1 kompatibilní `page`/`page_size` odpověď zůstane
dostupná klientům, nové UI ji nepoužívá.

## Testovací plán

1. Index: 5 000 syntetických assetů, deterministické pořadí/tie-break,
   filtry, cursor mismatch, přímý locator, calendar/fallback/timezone a
   jednoznačný Session Grouper výsledek včetně půlnoci a unassigned.
2. Galerie: API integrace, retry/snapshot chyby a browser test windowingu,
   rychlého scrollu, filtrů, back/forward a anchor restore.
3. Časový navigátor: vzdálený skok jediným locator + batch požadavkem,
   aktivní segment a klávesnice.
4. Pohledy: deep links, active asset v kalendáři/relaci a pravdivý nezařazený
   stav.
5. Regrese: stávající Media Desk, Range, offline, AI pohledy, keyframe výběr,
   path security a read-only porovnání. Nakonec jednou FAST, relevantní
   integration/browser suite a finální performance profil.
