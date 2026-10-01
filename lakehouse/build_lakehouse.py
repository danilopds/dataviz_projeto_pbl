"""ETL: carrega os CSVs do modelo estrela (dimensional/csv) no DuckDB
(lakehouse/pbl.duckdb).

As dimensões e fatos espelham os CSVs publicados em dimensional/csv,
gerados por dimensional/build_csv.py a partir dos dados brutos de dados/.
Colunas analíticas derivadas na carga:
- fato_commits.sk_sprint_commitado e fato_kanban_eventos.sk_sprint_evento:
  sprint atribuída pela data (commitado_em / ocorrido_em) dentro da janela
  inicio_em–prazo_em de dim_sprint (dimensão conformada — as janelas do
  ciclo valem para todos os grupos);
- fato_merge_requests.sk_sprint e fato_cartoes.sk_sprint: o -1 dos CSVs
  (sem sprint) vira NULL no banco, mesma convenção do sk_sprint_commitado;
- fato_merge_requests.horas_para_merge: horas entre criado_em e merged_em.

O banco é construído em pbl.duckdb.tmp e substitui o anterior só no fim
(se o dashboard estiver aberto, feche-o e rode novamente).
"""
import os
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "dimensional" / "csv"
OUT = ROOT / "lakehouse" / "pbl.duckdb"
TMP = ROOT / "lakehouse" / "pbl.duckdb.tmp"

OUT.parent.mkdir(exist_ok=True)
if TMP.exists():
    TMP.unlink()

con = duckdb.connect(str(TMP))
con.execute("SET timezone='UTC'")


def read(name: str) -> str:
    """ FROM clause sobre o CSV publicado, tudo como texto."""
    return (f"FROM read_csv('{(SRC / f'{name}.csv').as_posix()}', "
            "header=true, all_varchar=true)")


# ---------------------------------------------------------------------------
# Dimensões
# ---------------------------------------------------------------------------
con.execute(f"""
CREATE TABLE dim_grupo AS
SELECT CAST(sk_grupo AS INTEGER) AS sk_grupo, grupo, branch_padrao,
       CAST(criado_em AS TIMESTAMP) AS criado_em,
       CAST(ultima_atividade_em AS TIMESTAMP) AS ultima_atividade_em
{read('dim_grupo')}
""")

con.execute(f"""
CREATE TABLE dim_pessoa AS
SELECT CAST(sk_pessoa AS INTEGER) AS sk_pessoa, pessoa_id, grupo,
       CAST(sk_grupo AS INTEGER) AS sk_grupo, papel, situacao,
       CAST(eh_placeholder AS INTEGER) AS eh_placeholder
{read('dim_pessoa')}
""")

con.execute(f"""
CREATE TABLE dim_sprint AS
SELECT CAST(sk_sprint AS INTEGER) AS sk_sprint, sprint, situacao,
       CAST(inicio_em AS DATE) AS inicio_em,
       CAST(sk_data_inicio AS INTEGER) AS sk_data_inicio,
       CAST(prazo_em AS DATE) AS prazo_em,
       CAST(sk_data_prazo AS INTEGER) AS sk_data_prazo
{read('dim_sprint')}
""")

con.execute(f"""
CREATE TABLE dim_quadro_coluna AS
SELECT CAST(sk_quadro_coluna AS INTEGER) AS sk_quadro_coluna, quadro,
       CAST(posicao AS INTEGER) AS posicao, coluna
{read('dim_quadro_coluna')}
""")

con.execute(f"""
CREATE TABLE dim_data AS
SELECT CAST(sk_data AS INTEGER) AS sk_data, TRY_CAST(data AS DATE) AS data,
       CAST(ano AS INTEGER) AS ano, CAST(trimestre AS INTEGER) AS trimestre,
       CAST(mes AS INTEGER) AS mes, nome_mes, CAST(dia AS INTEGER) AS dia,
       CAST(dia_semana_num AS INTEGER) AS dia_semana_num,
       nome_dia_semana, CAST(eh_fim_de_semana AS INTEGER) AS eh_fim_de_semana
{read('dim_data')}
""")

# ---------------------------------------------------------------------------
# Fatos
# ---------------------------------------------------------------------------
con.execute(f"""
CREATE TABLE fato_commits AS
SELECT CAST(f.sk_grupo AS INTEGER) AS sk_grupo,
       CAST(f.sk_autor AS INTEGER) AS sk_autor,
       CAST(f.sk_data_autorado AS INTEGER) AS sk_data_autorado,
       CAST(f.autorado_em AS TIMESTAMP) AS autorado_em,
       CAST(f.sk_data_commitado AS INTEGER) AS sk_data_commitado,
       CAST(f.commitado_em AS TIMESTAMP) AS commitado_em,
       CAST(f.e_merge AS INTEGER) AS e_merge,
       CAST(f.linhas_adicionadas AS INTEGER) AS linhas_adicionadas,
       CAST(f.linhas_removidas AS INTEGER) AS linhas_removidas,
       CAST(f.linhas_total AS INTEGER) AS linhas_total,
       f.grupo, f.commit_id, f.titulo, f.mensagem,
       s.sk_sprint AS sk_sprint_commitado
{read('fato_commits')} f
LEFT JOIN dim_sprint s
  ON CAST(f.commitado_em AS DATE) BETWEEN s.inicio_em AND s.prazo_em
""")

con.execute(f"""
CREATE TABLE fato_merge_requests AS
SELECT CAST(f.sk_grupo AS INTEGER) AS sk_grupo,
       CAST(f.sk_autor AS INTEGER) AS sk_autor,
       CAST(f.sk_merged_por AS INTEGER) AS sk_merged_por,
       NULLIF(CAST(f.sk_sprint AS INTEGER), -1) AS sk_sprint,
       CAST(f.sk_data_criacao AS INTEGER) AS sk_data_criacao,
       CAST(f.criado_em AS TIMESTAMP) AS criado_em,
       CAST(f.sk_data_atualizacao AS INTEGER) AS sk_data_atualizacao,
       CAST(f.atualizado_em AS TIMESTAMP) AS atualizado_em,
       CAST(f.sk_data_merged AS INTEGER) AS sk_data_merged,
       CAST(f.merged_em AS TIMESTAMP) AS merged_em,
       CAST(f.sk_data_fechamento AS INTEGER) AS sk_data_fechamento,
       CAST(f.fechado_em AS TIMESTAMP) AS fechado_em,
       CAST(f.mr_numero AS INTEGER) AS mr_numero,
       f.titulo, f.descricao, f.situacao,
       CAST(f.e_rascunho AS INTEGER) AS e_rascunho,
       CAST(f.comentarios AS INTEGER) AS comentarios,
       f.branch_origem, f.branch_destino,
       f.revisores_ids, f.responsaveis_ids, f.rotulos, f.grupo,
       date_diff('hour', CAST(f.criado_em AS TIMESTAMP),
                 CAST(f.merged_em AS TIMESTAMP)) AS horas_para_merge
{read('fato_merge_requests')} f
""")

con.execute(f"""
CREATE TABLE fato_cartoes AS
SELECT CAST(f.sk_grupo AS INTEGER) AS sk_grupo,
       CAST(f.sk_autor AS INTEGER) AS sk_autor,
       CAST(f.sk_fechado_por AS INTEGER) AS sk_fechado_por,
       NULLIF(CAST(f.sk_sprint AS INTEGER), -1) AS sk_sprint,
       CAST(f.sk_data_criacao AS INTEGER) AS sk_data_criacao,
       CAST(f.criado_em AS TIMESTAMP) AS criado_em,
       CAST(f.sk_data_atualizacao AS INTEGER) AS sk_data_atualizacao,
       CAST(f.atualizado_em AS TIMESTAMP) AS atualizado_em,
       CAST(f.sk_data_fechamento AS INTEGER) AS sk_data_fechamento,
       CAST(f.fechado_em AS TIMESTAMP) AS fechado_em,
       CAST(f.sk_data_prazo AS INTEGER) AS sk_data_prazo,
       CAST(f.prazo_em AS DATE) AS prazo_em,
       CAST(f.cartao_numero AS INTEGER) AS cartao_numero,
       f.titulo, f.descricao, f.situacao,
       CAST(f.peso AS INTEGER) AS peso,
       CAST(f.comentarios AS INTEGER) AS comentarios,
       CAST(f.tempo_estimado_s AS BIGINT) AS tempo_estimado_s,
       CAST(f.tempo_gasto_s AS BIGINT) AS tempo_gasto_s,
       f.responsaveis_ids, f.rotulos, f.grupo
{read('fato_cartoes')} f
""")

con.execute(f"""
CREATE TABLE fato_kanban_eventos AS
SELECT CAST(f.sk_evento AS INTEGER) AS sk_evento,
       CAST(f.sk_grupo AS INTEGER) AS sk_grupo,
       CAST(f.sk_pessoa AS INTEGER) AS sk_pessoa,
       CAST(f.sk_quadro_coluna AS INTEGER) AS sk_quadro_coluna,
       CAST(f.sk_data_evento AS INTEGER) AS sk_data_evento,
       CAST(f.ocorrido_em AS TIMESTAMP) AS ocorrido_em,
       f.grupo, CAST(f.cartao_numero AS INTEGER) AS cartao_numero,
       f.acao, f.tipo_evento, f.coluna,
       s.sk_sprint AS sk_sprint_evento
{read('fato_kanban_eventos')} f
LEFT JOIN dim_sprint s
  ON CAST(f.ocorrido_em AS DATE) BETWEEN s.inicio_em AND s.prazo_em
""")

con.execute("CHECKPOINT")
print(con.execute(
    "SELECT table_name FROM information_schema.tables ORDER BY 1").fetchall())
counts = {
    t: con.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
    for t in ["dim_grupo", "dim_pessoa", "dim_sprint", "dim_data",
              "dim_quadro_coluna", "fato_commits", "fato_merge_requests",
              "fato_cartoes", "fato_kanban_eventos"]
}
print(counts)
con.close()

try:
    os.replace(TMP, OUT)
except PermissionError:
    raise SystemExit(
        "não foi possível substituir lakehouse/pbl.duckdb — feche o dashboard "
        "(streamlit) e rode novamente; o banco novo ficou em "
        "lakehouse/pbl.duckdb.tmp")