# NASA Space Apps Challenge 2026 — Resumo para concorrer

Fonte: spaceappschallenge.org (páginas lidas em 13/11/2026: /2026/, /2026/challenges/, abas Resources e Teams de cada desafio, /resources/project-submission-guide/, /awards/).

## 1. Datas e regras essenciais

| Item | Detalhe |
|---|---|
| Hackathon | **14 e 15 de novembro de 2026** |
| Janela de envio | Abre **sáb 14/11 às 9h** e fecha **dom 15/11 às 23h59** (fuso do evento local; no Evento Universal, fuso do dono da equipe) |
| Inscrição | Até o fim do hackathon (15/11). Passos: criar conta → inscrever-se no hackathon → escolher evento local (presencial/virtual ou o "Universal Event") → criar/entrar em equipe |
| Equipe | **Máximo 6 pessoas**. Todos precisam estar **confirmados no mesmo evento local** (quem está em lista de espera precisa ser aceito ou trocar de evento) |
| Idioma | **Tudo em inglês** (página do projeto, slides). Vídeo pode ser em português, mas **com legenda em inglês** |
| Dados NASA | **Obrigatório usar pelo menos 1 dado/recurso da NASA** para concorrer a prêmio global |
| Agências parceiras | Recomendado usar dados delas. Inclui a **Agência Espacial Brasileira (AEB)**, CSA, ESA, ISRO, JAXA, CONAE, UK Space Agency e outras |
| Menores de 18 | Proibido incluir imagem, vídeo, áudio ou semelhança de menores de 18 anos |
| Certificado | Sai automaticamente no Perfil depois que o projeto é enviado |

### Campos obrigatórios da página do projeto
1. **Project Name**
2. **High-Level Project Summary**: o que fizeram, como resolve o desafio, por que importa
3. **Link to Project Demo**: **vídeo de até 30 segundos** OU **até 7 slides** (contando título e introdução). Passou do limite = **desclassificado da avaliação global**
4. **Link to Final Project**: site, GitHub, Drive etc., com acesso público (sem login)
5. **Detailed Project Description**: o que faz, como funciona, benefícios, ferramentas e linguagens
6. **Use of Super Intelligence (SI)**: o site chama IA de "SI". É permitida, mas **não para ter a ideia da solução**. Imagem/vídeo gerado por IA precisa de **marca d'água visível**; áudio, código e dados gerados por IA precisam ser declarados no texto e nos metadados. Não pode usar logos ou elementos da marca NASA em conteúdo gerado
7. **NASA Data**: quais dados da NASA foram usados
8. **Space Agency Partner Data and Other References**: todas as fontes, códigos e imagens (inclusive open source)

Por fim: marcar "Terms and Conditions" + "Confirm All Work is Original" → **Submit for Judging**. Dá para reenviar quantas vezes quiser até o prazo; vale o último envio.

Dicas: só aceita upload de imagem (JPG/PNG/GIF até 10 MB); vídeo e documentos vão por link. Teste os links em janela anônima. Se criar um site, vale pedir classificação no FortiGuard Web Filter para os jurados não serem bloqueados.

### Critérios de julgamento (5)
**Impact, Creativity, Validity, Relevance, Presentation** (o demo pesa principalmente em Presentation).

### Fluxo de premiação
Jurados locais → **Global Nominees** → especialistas da NASA e das agências escolhem **Global Finalists** e Menções Honrosas → comitê executivo escolhe os **10 vencedores globais**.

### 10 prêmios globais
Best Use of Science · Best Use of Data · Best Use of Technology · Galactic Impact · Best Mission Concept · Most Inspirational · Best Storytelling · Global Connection · Art & Technology · Local Impact.

---

## 2. Os 14 desafios: dados e APIs de cada um

Contagem de equipes: aba "Teams" de cada desafio em 13/11/2026 (são equipes inscritas, não projetos enviados).

### 1. Health Monitoring Software (monitoramento de saúde de astronautas) — Intermediário — **2.882 equipes**
Software que coleta indicadores de saúde e ajuda o astronauta a avaliar e agir sobre o próprio estado (radiação, isolamento, perda óssea, saúde mental).
- NASA: 5 Hazards of Human Spaceflight; Human Spaceflight Risks; pesquisas do Human Research Program
- CSA: monitoramento de radiação para a saúde de astronautas; "Why do we do science in space?"
- ⚠️ **Não há API de dados nesta lista**, só material de referência. Para cumprir a regra de dados NASA, dá para puxar do OSDR/RadLab e do DONKI (que aparecem no desafio 3)

### 2. NASA's Discarded Equipment Storytelling (histórias dos equipamentos deixados na Lua e em Marte) — Iniciante/Intermediário — **2.587 equipes**
Contar a história dos equipamentos abandonados para jovens (mapa interativo, HQ, podcast, jogo).
- NASA: **NSSDCA** (catálogo de todas as naves e instrumentos, com parâmetros de missão e status)
- Lista de alvos: Apollo LMs, LRVs, ALSEP, Surveyor, Sojourner, Spirit/Opportunity, Viking 1/2, Phoenix, InSight, Dawn, NEAR Shoemaker, Pioneer 10/11, Ingenuity, Kepler

### 3. Space Mission Design Game (jogo de projeto de missão espacial) — Iniciante/Intermediário — **1.946 equipes**
Jogo em que o usuário projeta, gerencia e simula uma missão completa.
- NASA: Designing & Developing Science Missions; **GMAT** (General Mission Analysis Tool, open source); Concept Maturity Levels (JPL); Mission Design Lab; **NASA Mission Viz**; jogo educativo de telescópios; CubeSat 101; desafio de 2023 "Visualize a Space Mission Using VR"
- CSA: jogos e atividades digitais

### 4. Junior Astronaut Mission Trainer (simulador de missão para astronautas juniores) — Iniciante/Intermediário — **1.912 equipes**
Jogo/app em que o aluno administra um posto lunar ou marciano equilibrando suporte de vida, radiação, energia e comida.
- NASA: **NASA Open APIs (api.nasa.gov)**: APOD, fotos dos rovers de Marte, DONKI; precisa de chave gratuita
- **DONKI**: clima espacial (erupções solares, CMEs)
- **OSDR + API de busca**: biologia espacial e saúde de astronautas
- **RadLab**: dosimetria de radiação da ISS
- **Mars Trek**: terreno e elevação de Marte
- CSA: recursos STEM para jovens; produção de alimentos na Lua

### 5. Field Shift: Adapting Farms with NASA Data (adaptar fazendas com dados da NASA) — Intermediário/Avançado — **1.728 equipes**
Ferramenta de apoio à decisão sobre rotação de culturas.
- NASA: **SMAP** (umidade do solo), **GPM/IMERG** (chuva), **Landsat**, **MODIS/VIIRS** (NDVI), **NASA POWER** (agroclima, com API REST), **SRTM** (relevo), **ECOSTRESS** (temperatura de superfície e evapotranspiração), **NLDAS/GLDAS** (via Earthdata Search), **GEDI** (biomassa)
- Outros (EUA): USDA Ag Data Commons, Web Soil Survey, CropScape/CDL, PRISM, SSURGO/STATSGO2, NAIP, NLCD, CoCoRaHS, USGS NWIS, USDA Market News, NASS QuickStats, OpenET, LANDFIRE; FAO GAEZ (global)
- ESA: **Sentinel-2**; ECMWF: **ERA5**
- Observação: a maior parte dos dados auxiliares cobre só os EUA. Para o Brasil, use os globais (SMAP, IMERG, POWER, MODIS, Sentinel-2, ERA5, GAEZ)

### 6. Earth System Trend Detective (detetive de tendências do sistema terrestre) — Avançado — **1.245 equipes**
Ferramenta que escolhe variáveis de ciência da Terra, mostra séries temporais e testa se a mudança é estatisticamente significativa.
- NASA: **Giovanni** (séries temporais), **Hydrology Time Series**, **AppEEARS** (com API), NOAA **Climate Data Online**, artigo de série temporal com SeaWiFS
- Outros: KNMI Climate Explorer; artigos sobre testes de tendência e significância
- CSA: RADARSAT Constellation Mission (RCM), Geo.ca, missão SWOT, tutorial SAR em Python

### 7. Interplanetary Survival Guide: Martian Map (mapa de Marte) — Intermediário — **1.207 equipes**
Visão em camadas de um local ou rota em Marte para planejar uma caminhada.
- NASA: **Mars Trek (JPL)**; mapas geológicos USGS–NASA; mapa de rota do Curiosity; NASA Worldview; galeria de imagens brutas do **Perseverance**

### 8. Flame in Freefall (combustão em microgravidade com IA) — Intermediário/Avançado — **1.033 equipes**
Painel com IA que resume, ranqueia e interpreta resultados de experimentos de combustão para segurança contra incêndio.
- NASA: **PSI Data Repository — Combustion Science** (a base principal); NASA Combustion Science; vídeo ScienceCasts; guia de combustão na ISS (2015)
- Contexto: Apollo 1, Apollo 13, incêndio na Mir, spin-offs para bombeiros

### 9. Lunar Landing Site Navigator (locais de pouso lunar) — Intermediário/Avançado — **1.021 equipes**
Comparar locais e datas de pouso no polo sul, com Sol e Terra em relação ao horizonte (energia e comunicação).
- NASA: **QuickMap (LRO/ASU)**, **Moon Trek**, **JPL Horizons** (efemérides, com API)
- CSA: portal de exploração lunar

### 10. Permanent Moon Base Locations and Mars (análogos terrestres de bases na Lua e em Marte) — todos os níveis — **975 equipes**
Achar e caracterizar lugares na Terra parecidos com a Lua ou Marte.
- NASA: **Earthdata Search**, **Worldview**, **PDS** (Planetary Data System), **LRO**, **LRO Diviner**
- CSA: RCM, RADARSAT-1, tutorial SAR em Python
- ESA: Copernicus Data Space Ecosystem, ESA Open Science Catalog
- JAXA: G-Portal

### 11. Planet X and SPHEREx (céu infravermelho do SPHEREx) — Avançado — **840 equipes**
Ferramenta web pública que mostra imagens do SPHEREx e como o céu muda com o tempo.
- NASA: **NASA/IPAC Infrared Science Archive (IRSA)**, recursos do SPHEREx, **notebooks Jupyter de tutorial do SPHEREx**, WiseView (inspiração)
- ESA: **Gaia DR3**
- CSA: NEOSSat (dados + tutorial em Python), Canadian Astronomy Data Centre (CADC)

### 12. Harmonization of MODIS and VIIRS Hot Spots (focos de incêndio) — Intermediário/Avançado — **790 equipes**
App web que harmoniza os focos de incêndio de MODIS e VIIRS em um "calendário de queimadas" por área.
- NASA: **FIRMS** (Fire Information for Resource Management System; tem API e download em CSV/SHP)
- É o desafio com o escopo de dados mais focado: uma fonte só, bem documentada. Ótimo para o Brasil (Amazônia, Cerrado, Pantanal)

### 13. Dancing with the SARs (radar NISAR) — Intermediário/Avançado — **699 equipes**
App que usa dados do NISAR para acompanhar mudanças na superfície (inundação, fogo, subsidência, geleiras).
- NASA: **Earthdata Search**, **ASF Data Search Vertex**, **NISAR Data User Guide**, introdução a sensoriamento remoto e a SAR, **treinamentos ARSET**, NISAR StoryMaps, resumos de aplicações do NISAR, UAVSAR Postcards
- CSA: RCM, RADARSAT-1, tutorial SAR em Python
- CONAE (Argentina): **catálogo SAOCOM** (exige cadastro)

### 14. The Earth Information Jukebox (sonificação de dados da Terra) — Iniciante/Intermediário — **602 equipes**
Interface que combina quadros visuais do EIC com sons gerados em tempo real.
- NASA: banco de conteúdo do **Earth Information Center (EIC/SVS)**; sonificação de Caldwell 73; luzes noturnas 2012–2023; correntes e temperatura do mar; aerossóis GEOS; simulações de qualidade do ar; Perpetual Ocean 2; CO₂ global do DYAMOND; raios detectados da ISS; rio atmosférico 3D; altura da floresta (GEDI)
- Os "dados" são vídeos e imagens do SVS, processados com visão computacional e transformados em áudio

---

## 3. Análise

### Os mais escolhidos (equipes inscritas em 13/11)
| # | Desafio | Equipes | % do total (~19,5 mil) |
|---|---|---|---|
| 1 | Health Monitoring Software | 2.882 | 14,8% |
| 2 | Discarded Equipment Storytelling | 2.587 | 13,3% |
| 3 | Space Mission Design Game | 1.946 | 10,0% |
| 4 | Junior Astronaut Mission Trainer | 1.912 | 9,8% |
| 5 | Field Shift (fazendas) | 1.728 | 8,9% |
| 6 | Earth System Trend Detective | 1.245 | 6,4% |
| 7 | Martian Map | 1.207 | 6,2% |
| 8 | Flame in Freefall | 1.033 | 5,3% |
| 9 | Lunar Landing Site Navigator | 1.021 | 5,2% |
| 10 | Moon/Mars Analogs | 975 | 5,0% |
| 11 | Planet X / SPHEREx | 840 | 4,3% |
| 12 | MODIS/VIIRS Hot Spots | 790 | 4,1% |
| 13 | Dancing with the SARs | 699 | 3,6% |
| 14 | Earth Information Jukebox | 602 | 3,1% |

Padrão: os desafios **de nível iniciante, focados em jogo, história ou app** (1–4) concentram quase metade das equipes. Os de **dados geoespaciais pesados** (SAR, SPHEREx, FIRMS) têm bem menos concorrência.

### APIs e fontes mais recorrentes e reaproveitáveis
| Fonte | Desafios onde aparece | Acesso programático |
|---|---|---|
| NASA Earthdata Search / CMR | 5, 10, 13 (e base de SMAP, GPM, NLDAS...) | Sim (CMR API, `earthaccess` em Python) |
| CSA RADARSAT (RCM / RADARSAT-1) + tutorial SAR | 6, 10, 13 | Download + Python |
| NASA Worldview / GIBS | 5, 7, 10 | Sim (WMTS do GIBS) |
| Trek (Mars Trek / Moon Trek) | 4, 7, 9 | Sim (serviços de tiles e WMTS) |
| MODIS / VIIRS | 5, 12 | Sim (FIRMS API, AppEEARS) |
| api.nasa.gov (APOD, DONKI, Mars Photos) | 4 (e útil em 1, 2, 3) | Sim (chave gratuita) |
| OSDR / RadLab | 4 (e útil em 1) | Sim (API de busca) |
| JPL Horizons | 9 | Sim (API REST) |
| NASA POWER | 5 | Sim (API REST) |
| AppEEARS / Giovanni | 6 | AppEEARS tem API; Giovanni é web |
| IRSA (SPHEREx) / Gaia | 11 | Sim (TAP/astroquery) |
| ASF Vertex (NISAR) | 13 | Sim (`asf_search`) |
| PSI Data Repository | 8 | Download |
| NSSDCA / PDS | 2, 10 | Web/consulta |

**As mais versáteis:** api.nasa.gov, Earthdata (CMR/earthaccess), GIBS/Worldview, FIRMS e NASA POWER. Têm API REST simples, não exigem processamento pesado e servem para vários desafios.

### Relação aplicabilidade × concorrência (para uma equipe brasileira)
- **Melhor custo-benefício:** *MODIS/VIIRS Hot Spots* (790 equipes, uma fonte com API bem documentada, impacto local forte no Brasil, encaixa nos prêmios Local Impact e Best Use of Data); *Earth Information Jukebox* (602 equipes, o menos disputado, aceita iniciantes, forte para Art & Technology e Storytelling).
- **Bom equilíbrio:** *Lunar Landing Site Navigator* (Horizons API + Moon Trek, escopo claro); *Field Shift* (muito aplicável, mas disputado e com dados auxiliares centrados nos EUA).
- **Muito concorridos:** Health Monitoring e Discarded Equipment. Dá para vencer, mas a diferenciação precisa vir do produto e da narrativa. No Health Monitoring, atenção: os recursos listados não trazem dataset, então é preciso buscar dados no OSDR ou no DONKI.
- **Alta barreira técnica:** Dancing with the SARs e Planet X / SPHEREx (arquivos grandes e processamento científico). Pouca concorrência, mas arriscado para um hackathon de 48h.
