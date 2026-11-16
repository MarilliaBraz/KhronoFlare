# Dossiê: Harmonization of MODIS and VIIRS Hot Spots (Space Apps 2026)

Levantamento feito em 13/11/2026, só em fontes oficiais (NASA, UMD/MODIS Fire Team, INPE) e em artigos revisados por pares. Quando algo não pôde ser confirmado, está marcado como **não verificado**.

---

## 1. O que o desafio pede

Fonte: https://www.spaceappschallenge.org/2026/challenges/modis-and-viirs-hot-spots/ (abas Details e Resources)

**Objetivo:** um aplicativo web com um **calendário harmonizado de atividade de queimadas** baseado em focos ativos, que junte a longa série histórica do MODIS com a continuidade e o maior detalhe do VIIRS.

**Duas partes sugeridas pelo enunciado:**
1. **Harmonização MODIS + VIIRS.** Ao final dessa fase, "o sensor de origem não importa mais" e o foco passa a ser padrões, tendências e anomalias.
2. **Aplicativo web** que recebe os dados harmonizados. O usuário escolhe uma região e um intervalo de datas e baixa análises e visualizações.

**Entregas citadas explicitamente:**
- Calendário com o número de focos **desde o início dos anos 2000 até hoje**: quais meses têm mais fogo, quais anos foram piores, como o mês atual se compara aos anteriores.
- Comparar o mês atual com a **mediana histórica** da área selecionada.
- **Escalas de cor acessíveis** para mostrar diferenças entre meses ("calendário em chamas").
- **CSV para download** com os focos da busca.

**Considerações (opcionais):**
- Público: alerta precoce e resposta a emergências, cientistas, gestores de terras, bombeiros.
- Mapa interativo para desenhar a área de interesse, ou entrada de latitude e longitude.
- Índices-chave: anomalias em relação a médias plurianuais, número de focos detectados.

**Por que harmonizar, segundo o enunciado:** MODIS e VIIRS têm resoluções espaciais, sensibilidades e horários de observação diferentes. Além disso, o MODIS (Terra/Aqua) está no fim da vida útil e vem sendo substituído pelo VIIRS.

**Recurso listado pelo desafio:** apenas o **NASA FIRMS** (Fire Information for Resource Management System). Todas as APIs abaixo são do ecossistema FIRMS/Earthdata, ou são fontes oficiais que o FIRMS referencia.

---

## 2. ⚠️ Fatos novos que mudam o projeto

| Fato | Fonte oficial |
|---|---|
| **O Suomi NPP parou de entregar dados em 2/11/2026, às 15h40 UTC.** A NASA pede migração para o NOAA-20 e o NOAA-21. No FIRMS, os focos novos do S-NPP também pararam nessa data. | earthdata.nasa.gov/data/alerts-outages/reminder-new-suomi-npp-observations-cease-november-2-2026 e FAQ do FIRMS |
| **Terra e Aqua estão em deriva orbital.** O Terra hoje cruza o equador às **8h32** (hora local média), não mais às 10h30. O Aqua está em "free-drift" desde dez/2021, descendo de altitude e cruzando o equador cada vez mais tarde. O MODIS dos dois ainda está operacional. | terra.nasa.gov, terra.nasa.gov/about/terra-orbital-drift-information, science.nasa.gov/mission/aqua |

**Consequência:** o horário de passagem do MODIS mudou ao longo da série. Como o fogo tem ciclo diário forte nos trópicos (Giglio et al., 2006), a contagem do MODIS dos últimos anos não é diretamente comparável à dos primeiros anos. Mencionar isso na solução mostra rigor científico (critério **Validity**).

---

## 3. APIs e fontes de dados disponíveis

### 3.1 FIRMS Area API (principal para dados recentes) ✅
- **Documentação:** https://firms.modaps.eosdis.nasa.gov/api/area/ (API versão 4.2.8)
- **Chave (MAP_KEY):** gratuita, pedida em https://firms.modaps.eosdis.nasa.gov/api/map_key e enviada por e-mail.
- **Limite:** **5.000 transações a cada 10 minutos**. Pedidos grandes contam como várias transações; por exemplo, o mundo inteiro num dia de VIIRS NOAA-20 custa cerca de 36.
- **Consultar o saldo:** `https://firms.modaps.eosdis.nasa.gov/mapserver/mapkey_status/?MAP_KEY=<key>`
- **Endpoints:**
  ```
  https://firms.modaps.eosdis.nasa.gov/api/area/csv/[MAP_KEY]/[SOURCE]/[AREA]/[DAY_RANGE]
  https://firms.modaps.eosdis.nasa.gov/api/area/csv/[MAP_KEY]/[SOURCE]/[AREA]/[DAY_RANGE]/[DATE]
  ```
  - `AREA` = `oeste,sul,leste,norte` (ex.: América do Sul `-85,-57,-32,14`) ou `world`
  - `DAY_RANGE` = **1 a 5** (máximo de 5 dias por chamada)
  - `DATE` = `YYYY-MM-DD`; retorna de DATE até DATE + DAY_RANGE − 1
  - Saída: **somente CSV**
- **Valores de SOURCE:**

| SOURCE | Sensor | Observação |
|---|---|---|
| `MODIS_SP` | MODIS Terra+Aqua, Collection 6.1, **padrão (científico)** | desde **01/11/2000** |
| `MODIS_NRT` | MODIS, tempo quase real | período após o fim do SP |
| `VIIRS_SNPP_SP` | VIIRS Suomi NPP 375 m, padrão | desde **20/01/2012**; **encerrado em 02/11/2026** |
| `VIIRS_SNPP_NRT` | VIIRS Suomi NPP, NRT | **encerrado em 02/11/2026** |
| `VIIRS_NOAA20_SP` / `_NRT` | VIIRS NOAA-20 375 m | desde **01/04/2018** |
| `VIIRS_NOAA21_SP` / `_NRT` | VIIRS NOAA-21 375 m | desde 01/03/2023 segundo a página de download (um resumo do FAQ citou 17/01/2024; **confirmar** com o data_availability) |
| `LANDSAT_NRT` | Landsat 8/9, 30 m | **só EUA e Canadá**, não serve para o Brasil |

- O SP (padrão) substitui o NRT com **cerca de 5 meses de atraso** (página de download; o FAQ fala em 2 a 3 meses para os arquivos mensais "ML"). **Para série histórica, use SP. NRT só para o período recente.**

### 3.2 FIRMS Data Availability API ✅
```
https://firms.modaps.eosdis.nasa.gov/api/data_availability/csv/[MAP_KEY]/[SENSOR]
```
`SENSOR` = `ALL` ou qualquer SOURCE acima. Retorna `data_id, min_date, max_date` em GMT e custa cerca de 5 transações. **Use no app para saber, por sensor, até onde vai o SP e de onde começa o NRT.**

### 3.3 FIRMS Missing Data ✅
https://firms.modaps.eosdis.nasa.gov/api/missing_data/ lista os dias sem dados por satélite (padrão e NRT). Útil para não confundir "dia sem fogo" com "dia sem dado". O formato da URL não está documentado na página; a tabela é carregada via JavaScript.

### 3.4 FIRMS Country API ⚠️ indisponível agora
`/api/country/csv/[MAP_KEY]/[SOURCE]/[ISO3]/[DAY_RANGE]` aparece no índice da API como **"Feature currently not available"** e retornou erro 400. Use a Area API com o bounding box do país. A lista de países fica em `https://firms.modaps.eosdis.nasa.gov/api/countries`.

### 3.5 FIRMS Archive Download (melhor caminho para a série histórica) ✅
- https://firms.modaps.eosdis.nasa.gov/download/
- Dados com **mais de 7 dias**; formatos **CSV, JSON e Shapefile**; login com Earthdata ou código por e-mail. **O arquivo chega por e-mail depois do processamento.** O tempo e o tamanho máximo não estão documentados.
- **Peça hoje mesmo** os recortes da região-alvo (ex.: Brasil) para MODIS C6.1 (2000→) e VIIRS S-NPP / NOAA-20 / NOAA-21 (SP). Com DAY_RANGE máximo de 5, baixar 25 anos pela Area API exigiria milhares de chamadas.

### 3.6 Arquivos mensais globais da Universidade de Maryland (fonte científica de referência) ✅
Servidor SFTP público do MODIS Fire Team, citado nos guias oficiais:
```
Servidor: fuoco.geog.umd.edu   login: fire   senha: burnt   (credenciais públicas, publicadas no guia)
MODIS : /data/MODIS/C6/MCD14ML/   → MCD14ML.YYYYMM.006.03.txt.gz (texto, campos separados por espaço)
VIIRS : /data/VIIRS/C2/VNP14IMGML/ → VNP14IMGML.YYYYMM.C2.03.csv.gz  (S-NPP)
        VJ114IMGML (NOAA-20) e VJ214IMGML (NOAA-21): mesmo padrão
```
- Vantagem: arquivo global mensal com o campo **`type`** (0 = vegetação, 1 = vulcão, 2 = outra fonte terrestre estática, 3 = offshore). Isso permite **filtrar indústrias, flares e vulcões**, o que a FIRMS NRT não faz. Os arquivos VIIRS ML também trazem `PixArea`, `VZA` (ângulo de visada) e outros campos úteis.
- Ponto de atenção: os arquivos são grandes (o guia desaconselha shapefile pelo limite de 2 GB) e precisam de cliente SFTP (FileZilla, Cyberduck ou a linha de comando).
- Fontes: MODIS C6/C6.1 Fire User Guide v1.0, seção 4.3 (earthdata.nasa.gov/s3fs-public/2023-09/MODIS_C6_C6.1_Fire_User_Guide_1.0.pdf); VIIRS C2 375 m User Guide v1.2, seção 4.2 (earthdata.nasa.gov/s3fs-public/2025-06/VIIRS_C2_AF-375m_User_Guide_1.2.pdf)

### 3.7 Produtos Level 2 completos (LAADS / LP DAAC) — opcional
`VNP14IMG` e `VJ114IMG` (NetCDF, segmentos de órbita de 6 min):
https://ladsweb.modaps.eosdis.nasa.gov/archive/allData/5200/VNP14IMG/ e .../VJ114IMG/. Também existe o **VNP14** (VIIRS 750 m, sem o "IMG"), que **o próprio guia oficial diz ser mais comparável ao MODIS Aqua de 1 km**. Use só se a equipe quiser uma harmonização mais sofisticada; é pesado para 48 horas.

### 3.8 Camadas de mapa (visual) ✅
- **FIRMS WMS:** `https://firms.modaps.eosdis.nasa.gov/mapserver/wms/fires/[MAP_KEY]/[layer]/?REQUEST=GetMap&WIDTH=1024&HEIGHT=512&BBOX=-180,-90,180,90`
  Camadas: `fires_modis_24|48|72|7`, `fires_terra_*`, `fires_aqua_*`, `fires_viirs_*`, `fires_viirs_noaa20_*`, `fires_viirs_noaa21_*`. Só janelas recentes (24 h a 7 dias).
- **FIRMS WFS (CSV):** `/mapserver/wfs/South_America/[MAP_KEY]/?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0&TYPENAME=ms:fires_noaa20_24hrs&...&outputformat=csv`. Camadas `fires_modis_24hrs|7days`, `fires_noaa20_*`, `fires_noaa21_*`.
- **FIRMS WMTS (tiles):** `/mapserver/wmts/fires/today|24hrs|7days/{z}/{row}/{col}`
- **KML footprints:** `/api/kml_fire_footprints/south_america/[24h|48h|72h|7d]/[c6.1|noaa-20-viirs-c2|noaa-21-viirs-c2]`, sem MAP_KEY.
- **NASA GIBS (WMTS, imagens de fundo e camadas datadas):** `https://gibs.earthdata.nasa.gov/wmts/epsg4326/best/{Layer}/default/{YYYY-MM-DD}/{TileMatrixSet}/{z}/{row}/{col}.{ext}`. A lista de camadas fica no GetCapabilities (`.../1.0.0/WMTSCapabilities.xml`). Os nomes exatos das camadas de anomalias térmicas **não foram verificados**, porque o catálogo não carregou.

### 3.9 Fonte brasileira complementar: INPE, Programa Queimadas ✅
- Dados abertos (CSV de focos de 10 min, diários, mensais e anuais; KML, inclusive só do satélite de referência; área queimada; risco de fogo): https://dataserver-coids.inpe.br/queimadas/queimadas/
- O **BDQueimadas** (terrabrasilis.dpi.inpe.br/queimadas/bdqueimadas/) exporta CSV, GeoJSON, KML e Shapefile e filtra por bioma (Amazônia, Cerrado, Pantanal…).
- O INPE trabalha com um **"satélite de referência" (hoje "Aqua Tarde")** justamente para manter a série histórica comparável. É o mesmo princípio de harmonização que o desafio pede, e um bom argumento no pitch. Não encontramos, em página oficial legível, o histórico de qual satélite foi referência em cada período.
- Não é dado da NASA. Serve como **validação local** e para o prêmio **Local Impact**, mas o projeto precisa usar dados da NASA (FIRMS).

---

## 4. Atributos dos focos (para o ETL)

| Campo | MODIS | VIIRS 375 m |
|---|---|---|
| Pixel | ~1 km (cresce na borda da varredura) | ~375 m no nadir |
| Brilho | `brightness` (canal 21/22, K), `bright_t31` | `bright_ti4`, `bright_ti5` (K) |
| Confiança | **0–100%**: baixa < 30, nominal 30–79, alta ≥ 80 | **l / n / h** (baixa, nominal, alta) |
| FRP | MW | MW |
| Dia/noite | `daynight` D/N | `daynight` D/N |
| Satélite | T (Terra) / A (Aqua) | N (S-NPP), N20, N21 |
| Versão | `6.1NRT` / `6.1` (padrão) | `2.0NRT` nos dados recentes |
| Tipo (`type`) | só no MCD14ML (padrão) | só nos arquivos ML (padrão) |
| Hora | `acq_time` HHMM **em UTC** | idem |

Fontes: earthdata.nasa.gov/data/tools/firms/active-fire-data-attributes-modis-viirs; limiares de confiança do MODIS na Tabela 11 do guia C6/C6.1.

**Recomendação oficial sobre confiança** (guia MODIS, §8.4.2): para menos alarmes falsos, use só **nominal + alta** e trate "baixa" como não fogo. Aplique o mesmo critério nos dois sensores.

---

## 5. Por que MODIS e VIIRS não são comparáveis diretamente

| Diferença | MODIS | VIIRS |
|---|---|---|
| Resolução | 1 km | 375 m (detecta muito mais fogo pequeno) |
| Faixa (swath) | 2.330 km | 3.040 km (cobertura global a cada 12 h) |
| Passagem no equador | Terra originalmente 10h30/22h30; **hoje ~8h32**. Aqua originalmente 13h30/1h30, em deriva | S-NPP **13h30/1h30**; NOAA-21 ~50 min à frente do NOAA-20, S-NPP entre os dois |
| Sensibilidade por ângulo | forte dependência do ângulo de visada | estável ao longo da faixa |
| Período | Terra 01/11/2000→; Aqua jul/2002→ (lançado em 04/05/2002) | S-NPP 20/01/2012–02/11/2026; NOAA-20 01/04/2018→; NOAA-21 2023/24→ |

**O que a literatura mede:**
- Em Punjab (Índia), o VIIRS detectou **4,8×** mais focos que MODIS Terra+Aqua e **6,5×** mais que só o Aqua. Os totais mensais de FRP dos dois tiveram correlação forte (r² = 0,98) [[Vadrevu et al., 2018]](https://consensus.app/papers/details/w:1c921859-94c7-4431-83ba-8b2d963a1afa/?utm_source=claude_code).
- No nordeste da Ásia, o MODIS deixou de detectar **65%** (floresta) e **83%** (áreas de baixa biomassa) dos pixels de fogo vistos pelo VIIRS [[Fu et al., 2020]](https://consensus.app/papers/details/w:45e5bde5-8e82-4c4b-aa75-d455425d742f/?utm_source=claude_code).
- **A razão entre os sensores varia por região, tipo de vegetação e estação.** Por isso o fator de harmonização deve ser calculado **por região e por mês**, nunca como um número global único [[Li et al., 2018]](https://consensus.app/papers/details/w:c6fe62bc-5bef-413b-83a5-269c8d247791/?utm_source=claude_code).
- Já há um trabalho de 2026 que funde MYD14 (Aqua) e VNP14IMG (2012–2024) com correção de duplicatas e pareamento quase simultâneo das passagens [[Zheng et al., 2026]](https://consensus.app/papers/details/w:04e4ac5c-1e41-4529-bd8a-5b99806f2ea6/?utm_source=claude_code).
- A NASA já trata o VIIRS como continuidade do MODIS em área queimada (VNP64A1 versus MCD64A1), com alta consistência [[Giglio et al., 2025]](https://consensus.app/papers/details/w:890cd161-c9ea-4c3e-b4ea-c3598a38d37e/?utm_source=claude_code).

---

## 6. Proposta de harmonização viável em 48 horas

**Ideia central: o "par de referência" Aqua MODIS ↔ S-NPP VIIRS.** Os dois cruzam o equador às 13h30 e têm **cerca de 14 anos de sobreposição (2012–2026)**. Esse período comum permite calibrar a conversão.

1. **Filtrar igual nos dois sensores:** confiança nominal + alta; `type = 0` (vegetação) quando disponível; separar dia e noite.
2. **Agregar** em grade (ex.: 0,25° ou por município/bioma) × mês → contagem de focos.
3. **Calibrar no período de sobreposição:** para cada célula (ou região) e cada mês do ano, ajustar `VIIRS ≈ k × MODIS_Aqua` com mediana das razões ou regressão robusta. Guardar k e a incerteza.
4. **Série harmonizada:**
   - 2002–2011: MODIS Aqua × k → "unidades VIIRS"
   - 2012–2026: VIIRS S-NPP (observado)
   - 2018–2026: calibrar S-NPP ↔ NOAA-20 (mesma tecnologia, ~50 min de diferença) e seguir com NOAA-20/21 depois de 02/11/2026
   - Nov/2000–jun/2002 (só Terra): opcional, com fator Terra→Aqua calibrado em 2003–2011; é preciso sinalizar a deriva do horário do Terra
5. **Validar:** fazer validação cruzada, calibrando com 2012–2018 e testando com 2019–2026, e mostrar o erro no app (critério **Validity**).
6. **No app:** o calendário mostra a série harmonizada; um selo indica qual sensor gerou cada mês; a comparação é **mês atual × mediana histórica (percentil)**; o CSV traz os focos brutos e os agregados harmonizados.

Alternativa mais simples (plano B): usar só VIIRS a partir de 2012 e MODIS antes, mostrando **anomalias padronizadas (z-score ou percentil) dentro de cada sensor**. Fica mais fraco cientificamente, mas é rápido.

---

## 7. Arquitetura sugerida

- **Pré-processamento (Python):** pandas/geopandas lendo MCD14ML + VNP14IMGML (ou os CSVs do Archive Download); agrega e harmoniza; exporta Parquet/JSON por região.
- **Backend leve:** FastAPI ou só arquivos estáticos; chama a **FIRMS Area API** só para os últimos dias (NRT) e para o CSV de download.
- **Frontend:** Leaflet ou MapLibre com o WMS/WMTS do FIRMS e o GIBS de fundo; desenho de polígono (Leaflet.draw); heatmap de calendário mês × ano (D3/ECharts) com paleta acessível (ex.: viridis/inferno).
- **Cuidados:** a MAP_KEY fica **no servidor**, nunca no front; cache das respostas da API para respeitar o limite de 5.000 transações a cada 10 minutos.

---

## 8. Checklist para hoje (antes de sábado às 9h)

- [ ] Pedir a **MAP_KEY** do FIRMS (chega por e-mail).
- [ ] Criar o login **Earthdata** e pedir no **Archive Download** os focos da região-alvo: MODIS C6.1 desde 2000 e VIIRS S-NPP, NOAA-20 e NOAA-21 (SP).
- [ ] Testar o SFTP `fuoco.geog.umd.edu` e baixar alguns MCD14ML e VNP14IMGML mensais.
- [ ] Rodar `data_availability/csv/[KEY]/ALL` para fixar as datas de corte SP/NRT de cada sensor.
- [ ] Definir a região de demonstração (sugestão: Pantanal ou Cerrado, onde o impacto local é forte).

---

## Fontes oficiais consultadas
- Desafio: spaceappschallenge.org/2026/challenges/modis-and-viirs-hot-spots/
- FIRMS API: firms.modaps.eosdis.nasa.gov/api/ (area, data_availability, map_key, missing_data, kml_fire_footprints); /download/; /mapserver/
- Earthdata FIRMS: earthdata.nasa.gov/data/tools/firms; /faq; /active-fire-data-attributes-modis-viirs
- VIIRS 375 m: earthdata.nasa.gov/data/instruments/viirs/viirs-i-band-375-m-active-fire-data
- Guias: MODIS_C6_C6.1_Fire_User_Guide_1.0.pdf (mai/2021); VIIRS_C2_AF-375m_User_Guide_1.2.pdf (jun/2025)
- Aviso do Suomi NPP: earthdata.nasa.gov/data/alerts-outages/reminder-new-suomi-npp-observations-cease-november-2-2026
- Terra/Aqua: terra.nasa.gov; terra.nasa.gov/about/terra-orbital-drift-information; science.nasa.gov/mission/aqua
- GIBS: nasa-gibs.github.io/gibs-api-docs/
- INPE: terrabrasilis.dpi.inpe.br/queimadas/; dataserver-coids.inpe.br/queimadas/queimadas/

**Não verificado / lacunas:** nomes exatos das camadas do GIBS; tempo de entrega do Archive Download; histórico do satélite de referência do INPE.

**Confirmado em 14/11/2026 no formulário do Archive Download:** o NOAA-21 começa em **01/03/2023**; o MODIS Aqua começa em **04/07/2002**. Com a opção "País", o formulário aceitou o **período inteiro num único pedido** (o aviso de "limitado a 1 ano" não bloqueou o envio).

## Disponibilidade real (API data_availability, consultada em 14/11/2026)
| Fonte | Início | Fim |
|---|---|---|
| MODIS_SP | 2000-11-01 | 2026-08-31 |
| MODIS_NRT | 2026-09-01 | 2026-11-14 |
| VIIRS_SNPP_SP | 2012-01-20 | 2026-07-31 |
| VIIRS_SNPP_NRT | 2026-08-01 | 2026-11-02 (fim) |
| VIIRS_NOAA20_SP | 2018-04-01 | 2026-07-31 |
| VIIRS_NOAA20_NRT | 2026-08-01 | 2026-11-13 |
| VIIRS_NOAA21_SP | 2023-03-01 | 2026-07-31 |
| VIIRS_NOAA21_NRT | 2024-01-17 | 2026-11-13 |
| Extras listados: GOES_NRT (2022-08-09→), BA_MODIS e BA_VIIRS (área queimada) | | |

Regra para o app: usar **SP até o max_date do SP** e **NRT depois**. Consultar o endpoint a cada execução, porque as datas avançam.

Teste em 12/11/2026, retângulo do Brasil: NOAA-20 NRT = 6.721 focos; MODIS NRT (Terra+Aqua) = 1.492 focos, cerca de **4,5×** mais no VIIRS, coerente com a literatura. O retângulo inclui países vizinhos (ex.: Chile), então é preciso recortar pelo polígono do Brasil.

## Pedidos feitos ao FIRMS Archive Download (14/11/2026, Brasil, CSV)
| ID | Fonte | Período |
|---|---|---|
| 846226 | MODIS C6.1 | 01/11/2000 – 13/11/2026 |
| 846227 | VIIRS S-NPP C2 | 20/01/2012 – 02/11/2026 |
| 846228 | VIIRS NOAA-20 C2 | 01/04/2018 – 13/11/2026 |
| 846229 | VIIRS NOAA-21 C2 | 01/03/2023 – 13/11/2026 |
