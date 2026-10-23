# S2b — failure a recovery matrix

**Stav:** **ACCEPTED + IMPLEMENTED**

**Návaznost:** [S2B_DESIGN.md](S2B_DESIGN.md), D-009, D-012

Základní pravidlo: S2b nikdy automaticky nemaže existující adresář, cizí data,
workspace ani originály. Retry doplňuje pouze bezpečně rozpoznanou vlastní
rozpracovanou operaci se shodným `operation_id`, kořeny a `workspace_id`.

## Stavový model

```text
unconfigured
  -> preflight_ok
  -> confirmation_required
  -> confirmed
  -> initializing
       -> configured_restart_required -> ready after restart
       -> failed_recoverable -> preflight/retry
       -> failed_requires_manual_action -> stop
```

`preflight_ok` ani confirmation nonce nerezervují cestu. Každý actual init
opakuje validaci pod exkluzivním vlastnictvím operace.

## Matice

| Fáze / situace | Zápis před chybou | Výsledek | Automatická akce | Bezpečný další krok |
|---|---|---|---|---|
| Neplatná/relativní/příliš dlouhá cesta | žádný | `rejected/INVALID_PATH` | žádná | opravit vstup |
| Shodné nebo překrývající se rooty | žádný | `rejected/OVERLAPPING_ROOTS` | žádná | vybrat dvě oddělená umístění |
| Symlink, junction nebo změněná identity parentu | žádný nebo jen vlastní marker | `rejected/PATH_IDENTITY_CHANGED` | nic nemaže | znovu preflight; při markeru ruční kontrola |
| Workspace na network nebo unknown FS | žádný | `rejected/UNSUPPORTED_WORKSPACE_FILESYSTEM` | žádná | vybrat prokazatelně lokální workspace |
| Media Storage dočasně nedostupné | žádný | `failed_recoverable/STORAGE_UNAVAILABLE` | zachovat nonce jen krátce | připojit storage a zopakovat preflight |
| Nedostatek práv parentu/targetu | žádný nebo prázdný adresář vytvořený operací | `failed_recoverable/PERMISSION_DENIED` | nic nemaže | opravit práva; retry se stejnými cestami |
| Nedostatek místa | žádný nebo částečný vlastní bootstrap | `failed_recoverable/NO_SPACE` | nic nemaže | uvolnit místo; retry po kontrole markeru |
| Media Storage je neprázdné už při preflightu | žádný | `rejected/STORAGE_NOT_EMPTY` | žádná | použít budoucí import/připojení, ne init |
| Workspace je neprázdný a nerozpoznaný | žádný | `rejected/WORKSPACE_NOT_EMPTY_UNKNOWN` | žádná | zvolit jiný prázdný cíl; ručně posoudit data |
| Existuje validní workspace | žádný | `ready_existing` při shodném storage, jinak `rejected/EXISTING_WORKSPACE` | žádná | připojit existující archiv přes M1.3/S2a |
| Manifest existuje, katalog chybí/neplatný a není marker | žádný | `failed_requires_manual_action/CORRUPT_OR_LEGACY_PARTIAL` | žádná | audit/obnova; neadoptovat |
| Preflight uspěl, před confirmem vznikla kolize | žádný | `rejected/PREFLIGHT_STALE` | zneplatnit nonce | nový preflight |
| Druhý proces drží init/workspace lock | žádný | `failed_recoverable/INITIALIZATION_BUSY` | čekání ani takeover neprovádět | uživatel zopakuje po ukončení prvního procesu |
| Dva procesy současně rezervují nový target | nejvýše jedna atomická rezervace | jeden pokračuje, druhý `INITIALIZATION_BUSY` | žádná | druhý ověří hotový výsledek později |
| Přerušení po vytvoření Media Storage | nový prázdný storage adresář | `failed_recoverable/INTERRUPTED` | adresář zůstává | retry; adresář musí stále být prázdný a stejný |
| Přerušení po vytvoření workspace markeru/adresářů | privátní skeleton bez manifestu | `failed_recoverable/INTERRUPTED` | skeleton zůstává | retry jen přes shodný marker a po získání locku |
| Selhání SQLite migrace | skeleton, marker, možná DB/WAL | `failed_requires_manual_action` nebo recoverable pouze pro známou transakční chybu | DB se nemaže | diagnostika; retry jen pokud DB quick/integrity check a schema state dovolí |
| Přerušení po workspace row/init run | DB + marker, bez veřejného manifestu | `failed_recoverable/INTERRUPTED` | označit stale init run při retry | ověřit ID a dokončit report/katalog |
| Selhání atomického katalogu | DB + report/marker, bez manifestu | `failed_recoverable/CATALOG_PUBLISH_FAILED` | temp soubor uklidí atomic writer | retry publikuje katalog z ověřené prázdné DB |
| Přerušení po katalogu, před manifestem | validní prázdný katalog, marker, bez entry pointu | `failed_recoverable/INTERRUPTED` | nic nemaže | retry ověří katalog a publikuje manifest |
| Přerušení po manifestu, před finalizací markeru | kompletní ready workspace + marker | `ready_existing` po validaci | pouze označit vlastní marker complete | Media Desk může workspace bezpečně připojit |
| Neznámý soubor se objeví ve storage během initu | částečný bootstrap | `failed_recoverable/STORAGE_CHANGED` před manifestem | soubor se nedotkne | uživatel posoudí; nový archiv vyžaduje prázdný root |
| Neznámý soubor se objeví ve workspace během initu | částečný bootstrap | `failed_requires_manual_action/WORKSPACE_CHANGED` | nic nemaže | ruční audit kolize |
| Hotový init, Media Desk read-only validace selže | ready tvrzení se nepotvrdilo | `failed_requires_manual_action/POSTCONDITION_FAILED` | profil se neuloží | zachovat původní config; audit workspace |
| Hotový init, zápis per-user configu selže | archiv je ready | `ready` + `CONFIG_SAVE_FAILED` | workspace se nemění | zobrazit cestu; později „Připojit existující archiv“ |
| Config uložen, proces nerestartován | archiv ready, profil nový | `configured_restart_required` | žádný hot-swap | restart Media Desku |
| Po restartu storage offline, knihovna prázdná | žádný nový zápis | workspace `connected`, storage warning | mapping/config nemaže | připojit storage před prvním ingestem |
| Pozdější opakovaný init nad ready cílem | žádný | `ready_existing` | žádný nový workspace/run | použít existující archiv |

## Klasifikace chyby

`failed_recoverable` smí být použito pouze tehdy, když:

- žádný cizí soubor nebyl změněn;
- init marker je validní a přesně odpovídá oběma rootům;
- operace umí prokázat, které artefakty vytvořila;
- existující DB/katalog lze bezpečně ověřit před doplněním.

Jinak je stav `failed_requires_manual_action`. „Manual action“ neznamená, že UI
nabídne mazání; zobrazí operation ID, cíle, poslední dokončenou fázi a cestu k
init reportu.

## Retry invarianty

1. Stejný hotový workspace vždy vrátí stejné `workspace_id`.
2. Retry nikdy negeneruje druhé ID, pokud už marker, DB, katalog nebo manifest
   obsahuje první ID.
3. Neshoda kteréhokoli ID, rootu nebo operation markeru zastaví automatický
   recovery.
4. Přerušený init nespouští scan, hash, metadata, preview ani AI.
5. `workspace.json` nevznikne, dokud není prázdný katalog a interní stav
   konzistentní.
6. Selhání configu se nesmí interpretovat jako selhání hotového archivu.
7. Dočasná nedostupnost po dokončení nemaže workspace ani per-user config.

## Zbytková rizika

- Atomická transakce přes dva filesystem rooty neexistuje; proto může po pádu
  zůstat prázdný Media Storage adresář.
- Stejně privilegovaný lokální proces může provést závod mezi kontrolou a
  operací. Directory handles/no-follow a opakovaná validace riziko omezují, ale
  neodstraňují všechny platformní TOCTOU případy.
- Detekce SMB/NFS/network mountu není univerzální. Proto implementace `unknown`
  workspace FS blokuje místo falešné garance.
- Výpadek napájení může vyžadovat SQLite integrity check a kontrolu atomicky
  publikovaných JSON; automatický recovery nesmí hádat.
