# Media Desk M1.3 – nastavení workspace

Datum návrhu: 2026-10-21. Výchozí commit: `7da319aee80bea4426d2107176a7be3a39af0417`.

## Rozsah

Media Desk nadále pracuje právě s jedním read-only workspace kontraktu v1.
Novým zapisovaným stavem je pouze per-user TOML konfigurace aplikace. M1.3
nevytváří workspace, nemění katalog, neotevírá ingest SQLite a nespouští žádný
mediální procesor.

## Umístění a precedence konfigurace

- Windows: `%APPDATA%\HUHAC\MediaDesk\config.toml`.
- Linux a ostatní POSIX systémy:
  `${XDG_CONFIG_HOME:-~/.config}/huhac/media-desk/config.toml`.
- Testy mohou předat vlastní adresář resolveru; nikdy nepoužijí skutečný profil.

Každá hodnota se vybírá samostatně v pořadí CLI > ENV > explicitní `--config` >
per-user config > výchozí hodnota. Zdroj aktivní cesty je součástí runtime
nastavení. Pokud workspace pochází z CLI, ENV nebo explicitního configu, webové
pole je zamčené, aby nižší profilová hodnota nemohla působit jako aktivní.

Profil se ukládá atomicky přes dočasný soubor ve stejném adresáři, `fsync` a
`os.replace`. Neúspěšná validace ani zápis původní soubor nezmění.

## UX a aktivace

Start bez workspace je platný stav. `/` zobrazí výzvu „Připojit existující
workspace“, `/settings` zůstane vždy dostupné a datové stránky vracejí řízený
stav 503 s odkazem na Nastavení. Nastavení nabízí ruční vložení serverové cesty,
samostatné ověření a teprve následné uložení stejné ověřené hodnoty.

Změna se bezpečně aktivuje až restartem procesu. Aktuální in-memory snapshot se
za běhu nepřepíná. Po uložení proto UI výslovně oznámí nutnost restartu. Při
dalším startu resolver načte profilovou cestu a vytvoří nový snapshot. Klíč
stavu Knihovny v `sessionStorage` obsahuje identitu workspace, takže se pozice
ani aktivní asset nepřenášejí mezi knihovnami.

## Validace a stavy

Validátor volá existující `load_workspace`, a tedy ověřuje manifest, contract
version 1, veřejný katalog, metadata a stávající ochrany relativních cest a
symlinků. Offline originály validaci neblokují. Výsledek se mapuje na stavy
`Připojeno`, `Nedostupné`, `Neplatné` a `Nenastaveno`; očekávaná chyba se ukáže
česky bez tracebacku.

## Bezpečnost zapisujícího rozhraní

- POST endpointy jsou dostupné jen při loopback bindu.
- `Host` musí být loopback a `Origin`, je-li přítomen, musí mít stejný origin.
- Formulář používá náhodný CSRF token v HttpOnly, SameSite=Strict cookie a
  shodnou skrytou hodnotu.
- Přijímá se pouze očekávaná dvojice polí, maximálně 4096 znaků; NUL a řídicí
  znaky jsou odmítnuty.
- Server přijímá jen adresář workspace. Neexistuje endpoint pro procházení,
  obecné čtení ani zápis souborů.

`GET /health` zachovává úspěšný payload pro připravenou knihovnu. Bez platného
workspace vrací 503 a navíc rozlišuje běžící proces (`status: running`) od
`ready: false`.
