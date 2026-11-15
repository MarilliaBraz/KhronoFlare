# Khronoflare (Angular)

Explorador de focos FIRMS + console de alertas (NASA Space Apps 2026).  
Marca: **Khronoflare** — logos SVG em [`public/brand/`](public/brand/).

Stack: Angular 22 standalone, Leaflet, signals, i18n PT/EN.

## Rodar

```bash
cd firms-angular
npm install
npm start
```

http://localhost:4200/

## Rotas

| Rota | Função |
|---|---|
| `/` | Explorador (mapa, layers, timeline, seleção circular) |
| `/alerts` | Fila de municípios + workflow de alerta + CAP |
| `/phone` | Receptor ntfy |
| `/outlook` | Outlook do próximo mês (`forecast.json`) |

Specs de implementação: [`docs/specs/`](docs/specs/).

---

## Dados que a UI consome hoje

Tudo sob `public/data/` (servido estático):

| Arquivo | Uso |
|---|---|
| `data.json` | Focos live + municípios + geometrias UF |
| `data-sample.json` | Fallback se `data.json` falhar |
| `forecast.json` | Outlook / células / municípios |
| `calendar.json` | Série mensal harmonizada (stub vazio até o export) |
| `harmonized_mun.json` | Join município → FRP/anomalia (stub vazio até o export) |
| `cities.json` | Opcional (metadados de UF/municípios) |

Contratos tipados: [`src/app/core/models/hotspot.ts`](src/app/core/models/hotspot.ts).  
Loader: [`src/app/core/services/hotspot-data.service.ts`](src/app/core/services/hotspot-data.service.ts).

Atualizar a cópia a partir do protótipo vanilla:

```bash
cp ../nasa-space-apps-2026/web/data.json public/data/
cp ../nasa-space-apps-2026/web/forecast.json public/data/
cp ../nasa-space-apps-2026/web/cities.json public/data/
```

---

## Conectar dados processados (`firms_harmonize`)

O pipeline Python vive em [`../nasa-space-apps-2026/firms_harmonize/`](../nasa-space-apps-2026/firms_harmonize/).  
Saídas esperadas (no PC de quem já rodou o pipeline):

```text
nasa-space-apps-2026/data/processed/
  counts.parquet
  harmonized_cells.parquet
  factors.csv
  calendar_brasil.csv
  calendar_brasil_grid.csv
  validation.json
  frp/frp_fused.parquet          # se rodou FRP
  risk/…                         # se rodou risk-*
```

### Layout pronto para dados harmonizados

A UI já carrega `calendar.json` e `harmonized_mun.json` (stubs vazios = chip “aguardando” / slots `—`).

| Destino na UI | Fonte processada | Status |
|---|---|---|
| Calendário mensal (Layers) | `calendar_brasil.csv` → `calendar.json` | contrato + loader prontos |
| Alertas: FRP / Anomalia | `harmonized_mun.json` por IBGE id | contrato + slots prontos |
| Timeline / histograma diário | série diária real | ainda depende de export diário / NRT |
| Intensidade no mapa | células / `frp_harm` | próximo passo após join |

### Export

```bash
python tools/export_for_web.py \
  --processed ../nasa-space-apps-2026/data/processed \
  --out public/data
```

Skill do agente: [`.cursor/skills/khronoflare-data-wire/SKILL.md`](.cursor/skills/khronoflare-data-wire/SKILL.md).

---

## Branding

| Arquivo | Uso |
|---|---|
| `public/brand/khrono-flare-logo-horizontal.svg` | Header do explorador |
| `public/brand/khrono-flare-icon.svg` | Header compacto (alerts / outlook) |
| `public/brand/khrono-flare-logo.svg` | Versão completa |

## Notas

- Alertas e ntfy são **simulação**.
- O protótipo vanilla em `nasa-space-apps-2026/web/` permanece independente.
- Basemaps: GIBS (Satellite / Relief / Night); contornos UF opcionais (sem máscara de mundo).
