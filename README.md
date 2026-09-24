# dataviz_projeto_pbl

> Projeto do Módulo PBL — Repositório GitLab & Quadro Kanban
> Instituto Ápice · Turma T28 · Ciclo 2026-1b · Extraído em 2026-08-29

## Sobre

Conjunto de dados que registra o **rastro de trabalho de grupos PBL** (G01–G03) em dois canais complementares:

1. **Repositório GitLab** (canal de estado, via API REST): `commits` e `merge_requests` de cada grupo;
2. **Quadro Kanban** (movimentação de cartões): `cartoes` e o event log `kanban_eventos`.

Os dados reais foram **pseudonimizados** — autores não-membros aparecem como placeholders `[bot]` e `[externo]`.

## Estrutura do repositório

```
.
├── dados/       # CSVs brutos extraídos (fonte)
├── relacional/  # CSVs no modelo estrela (fatos e dimensões)
├── lakehouse/   # ETL + banco DuckDB (lakehouse/pbl.duckdb)
├── dashboard/   # App Streamlit (painel do coordenador)
└── modelagem/   # Modelagem lógica em Markdown + diagrama (PNG)
```

## Como começar

1. **Clone o repositório:**

   ```bash
   git clone https://github.com/danilopds/dataviz_projeto_pbl.git
   cd dataviz_projeto_pbl
   ```

2. **Crie um ambiente virtual e instale as dependências** (Python 3.10+):

   ```bash
   python -m venv .venv
   .venv\Scripts\activate          # Windows (PowerShell: .venv\Scripts\Activate.ps1)
   # source .venv/bin/activate     # Linux/macOS
   pip install -r requirements.txt
   ```

3. **Explore a modelagem lógica:**
   - Abra [`modelagem/modelagem_logica.md`](./modelagem/modelagem_logica.md) — contém a descrição das entidades, o diagrama entidade-relacionamento em Mermaid e o dicionário de dados;
   - Consulte o diagrama de referência em [`modelagem/modelagem_logica.png`](./modelagem/modelagem_logica.png).

4. **Carregue os dados:**

   - **Modelo estrela (recomendado):** use os CSVs de `relacional/csv/` — fatos (`fato_commits`, `fato_merge_requests`, `fato_cartoes`, `fato_kanban_eventos`) e dimensões (`dim_pessoa`, `dim_grupo`, `dim_sprint`, `dim_data`, `dim_quadro_coluna`);
   - **Fonte bruta:** use os CSVs de `dados/` conforme a tabela da modelagem lógica.

   Exemplo em Python (pandas):

   ```python
   import pandas as pd

   fato_commits = pd.read_csv("relacional/csv/fato_commits.csv")
   dim_pessoa = pd.read_csv("relacional/csv/dim_pessoa.csv")
   ```

5. **Visualize diagramas Mermaid:** o GitHub renderiza Mermaid nativamente nos arquivos `.md`; em editores locais, use a extensão Mermaid do VS Code ou o [Mermaid Live Editor](https://mermaid.live).

## Dashboard (painel do coordenador)

Painel Streamlit com resumo por grupo, alertas pedagógicos (ritmo/vespera, concentração de carga, code review, consistência quadro × repositório) e drilldown por sprint e pessoa.

1. **Construa o lakehouse DuckDB** a partir dos CSVs de `dados/` (recria `lakehouse/pbl.duckdb`; também replica as janelas de datas de sprint de G03 para G01/G02 para alocar commits por `commitado_em`):

   ```bash
   python lakehouse/build_lakehouse.py
   ```

2. **Abra o dashboard:**

   ```bash
   streamlit run dashboard/app.py
   ```

   O app abre em `http://localhost:8501` (para outra porta: `--server.port 8502`).

3. **Validação rápida** (opcional) — testa todas as abas sem navegador:

   ```bash
   python lakehouse/apptest.py
   ```

## Boas práticas de contribuição

- Faça as alterações em uma branch própria e abra um *merge request*;
- Atualize a modelagem lógica sempre que a estrutura de dados mudar;
- Mantenha os CSVs em UTF-8 e com separador `,`.

## Referências

- Modelagem lógica: [`modelagem/modelagem_logica.md`](./modelagem/modelagem_logica.md)
