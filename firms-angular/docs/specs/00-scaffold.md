# Spec 00 — Scaffold e contratos

## Objetivo
Criar o projeto Angular standalone em `firms-angular/`, tipar os contratos do `web/` e carregar dados via `HotspotDataService`.

## Dependências
Nenhuma.

## Arquivos-alvo
- `package.json`, `angular.json`, `README.md`
- `src/app/core/models/hotspot.ts`
- `src/app/core/services/hotspot-data.service.ts`
- `public/data/*.json`
- `docs/specs/*`

## Acceptance criteria
- [x] `ng serve` sobe a aplicação
- [x] Types: `HotspotPoint`, `CandidateMun`, `DataPayload`, `ForecastPayload`, `CalendarMonth`
- [x] Service normaliza pontos compactos (`point_fields`) e objetos
- [x] Fallback para `data-sample.json` se `data.json` falhar
- [x] Specs 00–09 documentadas

## Fora de escopo
UI visual, mapa, alertas.
