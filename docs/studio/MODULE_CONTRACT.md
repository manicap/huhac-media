# Veřejný kontrakt modulů Studia

`StudioModuleDefinition` definuje stabilní ID, titul, pořadí, ikonu, vstupní React
komponentu, požadované capabilities a volitelné pravidlo dostupnosti. Registr je
statický, seřazený a odmítá duplicitní nebo prázdná ID.

Modul smí používat:

- veřejný Zustand context z `src/context`;
- veřejný `StudioDataSource` z `src/data`;
- vlastní komponenty, lokální stav a testy.

Modul nesmí importovat interní soubory jiného modulu, zapisovat přímo do
workspace nebo přidávat doménová pravidla do shellu. V0.1 registry importuje jen
veřejný `index.ts` každého modulu; automatický test kontroluje křížové importy.

## Přidání modulu

1. Založte `src/modules/<id>/` s komponentou, veřejným `index.ts` a testem.
2. Přidejte definici do `src/app/moduleRegistry.ts`.
3. Deklarujte jen skutečně potřebné capabilities.
4. Doménová data zpřístupněte přes úzké veřejné rozhraní, ne importem jiného modulu.
5. Ověřte navigaci, lokální stav, prázdný/chybový stav a error boundary.

Shell udržuje registrované dostupné moduly připojené a neaktivní panel skrývá.
To zachovává lokální React stav. Nákladné serverové operace proto musí moduly
řídit query klíči a `enabled`, ne očekáváním unmountu.
