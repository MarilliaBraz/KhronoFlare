# NASA Space Apps 2026

Repositório privado da equipe para compartilhar arquivos, código e ideias do desafio.

## Estrutura

| Caminho | Conteúdo |
|---|---|
| `ideias/` | Propostas e rascunhos da equipe |
| `comentarios-da-equipe/` | Pontos de vista e experiências de cada integrante |
| `firms_harmonize/` | Código de harmonização dos focos de calor MODIS/VIIRS (NASA FIRMS) |
| `tests/` | Testes do código |
| `resumo-space-apps-2026.md` | Resumo do desafio |
| `dossie-modis-viirs-hotspots.md` | Dossiê técnico sobre os sensores MODIS e VIIRS |
| `space-apps-2026.html` | Página de apresentação |

## Comentários da equipe

Cada integrante tem um arquivo para contar o que fez, o que aprendeu, as dificuldades e as sugestões.
Veja como escrever o seu em [comentarios-da-equipe/](comentarios-da-equipe/README.md).

## Dados

Os arquivos brutos do FIRMS (`DL_FIRE_*`) não ficam no repositório porque passam do limite de 100 MB do GitHub.
Baixe-os em https://firms.modaps.eosdis.nasa.gov/download/ e coloque-os na raiz do projeto.

## Como contribuir

1. Clone: `git clone https://github.com/MarilliaBraz/KhronoFlare.git`
2. Instale as dependências (Python 3.12):
   `python -m venv .venv && .venv/bin/pip install -r requirements-dev.txt`
3. Rode os testes: `.venv/bin/python -m pytest -q`
4. Crie uma branch: `git checkout -b minha-ideia`
5. Faça commit e push, depois abra um Pull Request.
