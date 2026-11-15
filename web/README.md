# Hotspot Alert Console (web)

Protótipo do painel de alertas de incêndio: fila de municípios com focos do NASA FIRMS, rascunho do alerta com checagens, aprovação por uma segunda pessoa e pop-up simulado no celular.

## Arquivos

| Arquivo | O que é |
|---|---|
| `index.html` | Estrutura da página |
| `style.css` | Visual (tema claro e escuro) |
| `app.js` | Lógica: fila, mapa, rascunho, aprovação, pop-up, exportação CAP |
| `data.json` | Focos e municípios candidatos que a página carrega |
| `ntfy.js` | Envia o alerta aprovado (ou o cancelamento) para um canal do ntfy.sh |
| `phone.html` + `phone.js` | "Modo celular": abre no celular, escuta o canal e mostra o alerta em tela cheia com sirene e vibração |
| `tools/build_data.py` | Script que gerou o `data.json` |

## Rodar localmente

A página lê o `data.json` com `fetch`, então precisa de um servidor (abrir o arquivo direto do disco não funciona):

```bash
cd web
python -m http.server 8000
```

Depois abra http://localhost:8000.

## Publicar no GitHub Pages

Coloque a pasta `web/` no repositório, vá em **Settings → Pages** e escolha a branch e a pasta. O link abre sem login, como o Space Apps exige.

## Celular de verdade (simulação)

1. Abra o painel por um endereço que o celular alcance (GitHub Pages, ou o IP do computador na mesma rede Wi-Fi, ex.: `http://192.168.0.10:8000`). `localhost` não abre no celular.
2. No card **Real phone**, leia o QR code com o celular (ou copie o link) e toque em **Start receiving alerts**. O toque libera som e vibração.
3. Opcional: instale o app **ntfy** e assine o mesmo canal (`hac-…`) em ntfy.sh para receber também como notificação do sistema.
4. No painel, **Send test** confere a ligação. Depois, cada **Approve and send** e cada cancelamento chegam ao celular.

Limites: o canal do ntfy.sh é público para quem souber o nome (por isso o nome é aleatório e só trafega simulação); o navegador não toca no modo silencioso; no iPhone a página não vibra.

## De onde vêm os dados

- **Focos:** amostra NRT de 12/11/2026 em `tests/fixtures/` (Terra/Aqua MODIS e NOAA-20 VIIRS), do NASA FIRMS.
- **Estados e municípios:** API de malhas e de localidades do IBGE (`servicodados.ibge.gov.br`), qualidade mínima.
- **Prioridade:** provisória = FRP máximo + 0,5 × nº de focos + 5 × focos de alta confiança.

`tools/build_data.py` recebe como argumento uma pasta com `repo/tests/fixtures/` e `ibge/` (arquivos `uf.json`, `estados.json`, `mun_<UF>.json`, `nomes_<UF>.json`) e grava `build/data.json`.

## Próximo passo

Trocar a amostra pelas saídas do `firms_harmonize` (`harmonized_cells.parquet`, `calendar_brasil.csv`) para preencher FRP harmonizado, mediana histórica e anomalia, que hoje aparecem com "—".
