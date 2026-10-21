# Media Desk M1.1.1 — diagnostika desktopového layoutu

Datum: 2026-10-21. Výchozí commit: `ddf207408827b520cb390f3d97b7be25291e347c`.

## Příčiny

- Dokument (`body`) byl svisle scrollovatelný a Knihovna současně vytvořila
  druhý scroll root přes `.library-viewport { height: calc(...); overflow:
  auto; }`. Virtualizace poslouchala pouze vnitřní `scrollTop`, proto nešlo
  vnitřní scrollbar odstranit bez změny výpočtu viditelného okna.
- Obecné pravidlo `main { max-width: 1480px; margin: auto; padding: ...72px }`
  omezovalo `.app-main` i po odečtení 190px sidebaru. Na širokém desktopu tak
  vznikaly velké prázdné okraje a grid nedostal dostupnou šířku.
- Globální marketingové titulky (`38–84px`) a následné view override
  (`42–72px`) zvětšovaly pracovní hlavičky a spotřebovaly výšku viewportu.
- Toggle byl prostředním ze tří prvků `.topbar` s
  `justify-content: space-between`; jeho poloha proto nesouvisela s hranou
  sidebaru.
- `/calendar` bez `year` záměrně renderoval `.year-list`, takže workspace s
  jedním rokem ukázal nadpis „Roky“ a jednu osamělou dlaždici.

## Zvolená oprava

Jediným primárním scroll rootem je `.app-main` pod pevnou hlavičkou. `body` se
neposouvá a `.library-viewport` nemá vlastní overflow ani pevnou výšku.
Virtualizace počítá relativní posun galerie z `scrollTop` `.app-main`, dál
vykresluje pouze viewport + overscan a zachovává anchor pomocí asset indexu a
pixelového offsetu. Hlavní obsah nemá `max-width`, má malé desktopové okraje a
grid měří skutečnou šířku galerie.

Toggle je fixed u hrany sidebaru a ve sbaleném stavu se přesune k levému okraji.
Kalendář bez explicitního roku vybere nejnovější dostupný rok, zobrazí 12
skutečných měsíců a nad mřížkou nabídne všechny roky s katalogovými počty.
Datová a timezone politika se nemění.
