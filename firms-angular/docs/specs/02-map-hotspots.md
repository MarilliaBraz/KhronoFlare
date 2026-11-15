# Spec 02 — Mapa e focos ativos

## Objetivo
Leaflet + GIBS, renderizar focos do `data.json`, filtros Active fires.

## Dependências
Specs 00–01.

## Arquivos-alvo
- `src/app/features/explorer/map-view.component.ts`
- `ExplorerStateService` (source, colorBy, confidence)

## Acceptance criteria
- [x] Mapa Leaflet com zoom ± e bases satélite/relevo/noite
- [x] Pontos VIIRS/MODIS coloridos por idade ou sensor
- [x] Filtros Source / Color by / Minimum confidence
- [x] Chip de coords / período / contagem sincronizado

## Fora de escopo
Área queimada, playback, seleção circular.
