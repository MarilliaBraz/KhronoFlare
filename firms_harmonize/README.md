# firms_harmonize

Pipeline que harmoniza os focos de incêndio MODIS (2000→) e VIIRS (2012→) do NASA FIRMS numa série única e gera o calendário de queimadas do desafio *Harmonization of MODIS and VIIRS Hot Spots* (Space Apps 2026).

## Preparar

```bash
python3 -m venv .venv && .venv/bin/pip install pandas numpy pyarrow shapely requests pytest
# chave da API no arquivo .env da raiz:  FIRMS_MAP_KEY=...
```

## Onde colocar os dados

| Pasta | Conteúdo |
|---|---|
| `data/raw/archive/` | CSVs do **FIRMS Archive Download** (descompacte os .zip aqui; `.csv` e `.csv.gz` são aceitos) |
| `data/raw/api/` | cache automático da Area API (`fetch-recent`) |
| `data/boundary/brasil.geojson` | contorno do Brasil (`boundary`, API de malhas do IBGE) |
| `data/processed/` | saídas |

## Rodar

```bash
.venv/bin/python -m firms_harmonize status        # saldo da chave + datas SP/NRT por sensor
.venv/bin/python -m firms_harmonize boundary      # contorno do Brasil (IBGE)
.venv/bin/python -m firms_harmonize fetch-recent  # NRT do dia seguinte ao fim do SP até ontem
.venv/bin/python -m firms_harmonize all           # aggregate + harmonize + validate
.venv/bin/python -m pytest -q tests               # testes
```

Opções: `--res 0.25` (lado da célula, em graus), `--min-conf nominal|high|low`, `--min-count 30` (focos mínimos para estimar um fator), `--no-clip`, `--archive-only`.

## Saídas (`data/processed/`)

| Arquivo | O que é |
|---|---|
| `counts.parquet` | focos por plataforma × mês × célula (já filtrados e recortados) |
| `harmonized_cells.parquet` | série harmonizada por célula × mês: `value` (unidades S-NPP), `origin`, `k`, `factor_level` |
| `factors.csv` | todos os fatores de conversão, com nível espacial, mês e contagens usadas |
| `calendar_brasil.csv` | ano, mês, valor, mediana histórica, p10/p90, anomalia %, percentil |
| `calendar_brasil_grid.csv` | matriz ano × mês para o heatmap |
| `validation.json` | teste fora da amostra Aqua→S-NPP (treino 2012–2016, teste 2017–2021) |

## Método

1. **Filtros iguais para os dois sensores:** confiança nominal + alta (guia MODIS §8.4.2; confiança MODIS: < 30 baixa, 30–79 nominal, ≥ 80 alta); `type = 0` (vegetação) quando o produto informa; recorte pelo contorno do Brasil.
2. **SP antes de NRT:** em cada plataforma e mês, usa o dado científico (SP) quando existe e o NRT só depois do fim do SP.
3. **Referência: S-NPP VIIRS 375 m.** Ele cruza o equador às 13h30, como o Aqua, e sobrepõe o Aqua de 2012 a 2026.
4. **Fator k = Σ referência / Σ origem**, por unidade espacial e mês do calendário, só em meses em que as duas plataformas operavam. Recuo hierárquico: bloco de 1° → bloco de 4° → Brasil por mês → Brasil geral, exigindo ao menos `min_count` focos de origem.
5. **Encadeamento:**
   - nov/2000–jul/2002: Terra → Aqua (calibrado em 2002–2011) → S-NPP
   - ago/2002–jan/2012: Aqua → S-NPP (calibrado em 2012–2021, antes da deriva do Aqua)
   - fev/2012–out/2026: S-NPP observado
   - nov/2026 →: NOAA-20 → S-NPP (calibrado em 2018–2026); NOAA-21 se faltar NOAA-20
6. **Calendário:** mediana, p10 e p90 de cada mês do ano, excluindo o ano corrente; anomalia e percentil do mês atual.

## Limitações conhecidas (declarar no projeto)

- O NRT não traz `type`, então fontes estáticas (indústria, flares) não são removidas nos meses só NRT.
- Terra e Aqua estão em deriva orbital (Terra ~8h32 em 2026; Aqua em deriva livre desde dez/2021). Por isso a calibração Aqua→S-NPP para em 2021.
- Uma célula onde o MODIS viu 0 focos e o VIIRS viu alguns continua com 0 depois da conversão. O fator corrige escala, não detecção.
- Não removemos duplicatas de órbitas sobrepostas. Isso é relevante em latitudes altas e pouco relevante no Brasil.
- Meses de início e fim parciais de cada satélite ficam fora (ver `config.PLATFORM_PERIODS`).
