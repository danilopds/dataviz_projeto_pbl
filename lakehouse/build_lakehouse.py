"""ETL: loads dados/*.csv into a DuckDB lakehouse (lakehouse/pbl.duckdb).

Builds the dimensional model from item 8 of modelagem/modelagem_logica.md,
with one source fix: sprints of G01/G02 inherit the date intervals of G03
(same sprint number), so commits can be assigned to sprints by commitado_em.
"""
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "dados"
OUT = ROOT / "lakehouse" / "pbl.duckdb"

OUT.parent.mkdir(exist_ok=True)
if OUT.exists():
    OUT.unlink()

con = duckdb.connect(str(OUT))
con.execute("SET timezone='UTC'")


def load(name: str):
    con.execute(
        f"""
        CREATE TABLE src_{name} AS
        SELECT * FROM read_csv('{(SRC / f'{name}.csv').as_posix()}',
            header=true, all_varchar=false, ignore_errors=false)
        """
    )


for name in ["grupos", "pessoas", "sprints", "quadro_colunas",
             "commits", "merge_requests", "cartoes", "kanban_eventos"]:
    load(name)

# ---------------------------------------------------------------------------
# Dimensions
# ---------------------------------------------------------------------------
con.execute("""
CREATE TABLE dim_grupo AS
SELECT row_number() OVER (ORDER BY grupo) AS sk_grupo,
       grupo, branch_padrao,
       CAST(criado_em AS TIMESTAMP) AS criado_em,
       CAST(ultima_atividade_em AS TIMESTAMP) AS ultima_atividade_em
FROM src_grupos ORDER BY sk_grupo
""")

con.execute("""
CREATE TABLE dim_pessoa AS
    SELECT CAST(row_number() OVER (ORDER BY eh_placeholder, pessoa_id) AS INTEGER) AS sk_pessoa,
           pessoa_id, grupo, papel, situacao, eh_placeholder
    FROM (
        SELECT pessoa_id, grupo, papel, situacao, 0 AS eh_placeholder
        FROM src_pessoas
        UNION ALL
        SELECT '[bot]' AS pessoa_id, NULL AS grupo, 'placeholder' AS papel,
               'active' AS situacao, 1 AS eh_placeholder
        UNION ALL
        SELECT '[externo]', NULL, 'placeholder', 'active', 1
    ) t
ORDER BY eh_placeholder, pessoa_id
""")

# dim_sprint: G01/G02 sprints inherit G03 dates by sprint number
con.execute("""
CREATE TABLE dim_sprint AS
WITH base AS (
    SELECT s.grupo, s.sprint, s.situacao, s.inicio_em, s.prazo_em
    FROM src_sprints s
),
g03 AS (
    SELECT sprint, inicio_em, prazo_em FROM src_sprints WHERE grupo = 'G03'
),
fixed AS (
    SELECT b.grupo, b.sprint, b.situacao,
           CASE WHEN b.inicio_em IS NULL AND b.grupo <> 'G03'
                THEN g.inicio_em ELSE b.inicio_em END AS inicio_em,
           CASE WHEN b.prazo_em IS NULL AND b.grupo <> 'G03'
                THEN g.prazo_em ELSE b.prazo_em END AS prazo_em
    FROM base b LEFT JOIN g03 g USING (sprint)
)
SELECT CAST(row_number() OVER (ORDER BY grupo, sprint) AS INTEGER) AS sk_sprint,
       grupo, sprint, situacao,
       CAST(inicio_em AS DATE) AS inicio_em,
       CAST(prazo_em AS DATE) AS prazo_em
FROM fixed
UNION ALL
SELECT -1, '(N/A)', '(sem sprint)', '', NULL, NULL
""")

# dim_data: calendar covering all timestamps
con.execute("""
CREATE TABLE dim_data AS
WITH bounds AS (
    SELECT min(ts) AS min_date, max(ts) AS max_date FROM (
        SELECT min(CAST(commitado_em AS TIMESTAMP)) AS ts FROM src_commits
        UNION ALL
        SELECT max(CAST(commitado_em AS TIMESTAMP)) FROM src_commits
        UNION ALL
        SELECT min(CAST(criado_em AS TIMESTAMP)) FROM src_merge_requests
        UNION ALL
        SELECT max(CAST(criado_em AS TIMESTAMP)) FROM src_merge_requests
        UNION ALL
        SELECT min(CAST(criado_em AS TIMESTAMP)) FROM src_cartoes
        UNION ALL
        SELECT max(CAST(fechado_em AS TIMESTAMP)) FROM src_cartoes
        UNION ALL
        SELECT min(CAST(ocorrido_em AS TIMESTAMP)) FROM src_kanban_eventos
        UNION ALL
        SELECT max(CAST(ocorrido_em AS TIMESTAMP)) FROM src_kanban_eventos
    )
),
days AS (
    SELECT unnest(generate_series(min_date, max_date, INTERVAL 1 DAY)) AS d
    FROM bounds
)
SELECT CAST(strftime(d, '%Y%m%d') AS INTEGER) AS sk_data,
       CAST(d AS DATE) AS data,
       year(d) AS ano, quarter(d) AS trimestre, month(d) AS mes,
       strftime(d, '%A') AS nome_dia_semana,
       CASE WHEN dayofweek(d) IN (0, 6) THEN 1 ELSE 0 END AS eh_fim_de_semana
FROM days
""")

# ---------------------------------------------------------------------------
# Facts
# ---------------------------------------------------------------------------
con.execute("""
CREATE TABLE fato_commits AS
SELECT c.grupo, c.commit_id, p.sk_pessoa AS sk_autor,
       CAST(strftime(CAST(c.autorado_em AS TIMESTAMP), '%Y%m%d') AS INTEGER) AS sk_data_autorado,
       CAST(strftime(CAST(c.commitado_em AS TIMESTAMP), '%Y%m%d') AS INTEGER) AS sk_data_commitado,
       CAST(c.autorado_em AS TIMESTAMP) AS autorado_em,
       CAST(c.commitado_em AS TIMESTAMP) AS commitado_em,
       CAST(c.e_merge AS INTEGER) AS e_merge,
       CAST(c.linhas_adicionadas AS INTEGER) AS linhas_adicionadas,
       CAST(c.linhas_removidas AS INTEGER) AS linhas_removidas,
       CAST(c.linhas_total AS INTEGER) AS linhas_total,
       c.titulo, c.mensagem,
       s.sk_sprint AS sk_sprint_commitado
FROM src_commits c
LEFT JOIN dim_pessoa p ON p.pessoa_id = c.autor_id
LEFT JOIN dim_sprint s
  ON s.grupo = c.grupo
 AND CAST(c.commitado_em AS DATE) BETWEEN s.inicio_em AND s.prazo_em
""")

con.execute("""
CREATE TABLE fato_merge_requests AS
SELECT m.grupo, CAST(m.mr_numero AS INTEGER) AS mr_numero,
       pa.sk_pessoa AS sk_autor, pm.sk_pessoa AS sk_merged_por,
       s.sk_sprint,
       CAST(strftime(CAST(m.criado_em AS TIMESTAMP), '%Y%m%d') AS INTEGER) AS sk_data_criacao,
       CAST(strftime(CAST(m.merged_em AS TIMESTAMP), '%Y%m%d') AS INTEGER) AS sk_data_merged,
       CAST(m.criado_em AS TIMESTAMP) AS criado_em,
       CAST(m.merged_em AS TIMESTAMP) AS merged_em,
       m.situacao, m.titulo, m.descricao,
       CAST(m.e_rascunho AS INTEGER) AS e_rascunho,
       CAST(m.comentarios AS INTEGER) AS comentarios,
       m.branch_origem, m.branch_destino,
       m.revisores_ids, m.responsaveis_ids, m.rotulos,
       date_diff('hour', CAST(m.criado_em AS TIMESTAMP),
                 CAST(m.merged_em AS TIMESTAMP)) AS horas_para_merge
FROM src_merge_requests m
LEFT JOIN dim_pessoa pa ON pa.pessoa_id = m.autor_id
LEFT JOIN dim_pessoa pm ON pm.pessoa_id = m.merged_por_id
LEFT JOIN dim_sprint s
  ON s.grupo = m.grupo AND s.sprint = m.sprint
""")

con.execute("""
CREATE TABLE fato_cartoes AS
SELECT ct.grupo, CAST(ct.cartao_numero AS INTEGER) AS cartao_numero,
       pa.sk_pessoa AS sk_autor, pf.sk_pessoa AS sk_fechado_por,
       s.sk_sprint,
       CAST(strftime(CAST(ct.criado_em AS TIMESTAMP), '%Y%m%d') AS INTEGER) AS sk_data_criacao,
       CAST(strftime(CAST(ct.fechado_em AS TIMESTAMP), '%Y%m%d') AS INTEGER) AS sk_data_fechamento,
       CAST(ct.criado_em AS TIMESTAMP) AS criado_em,
       CAST(ct.fechado_em AS TIMESTAMP) AS fechado_em,
       ct.situacao, ct.titulo, ct.descricao,
       CAST(ct.peso AS INTEGER) AS peso,
       CAST(ct.tempo_estimado_s AS BIGINT) AS tempo_estimado_s,
       CAST(ct.tempo_gasto_s AS BIGINT) AS tempo_gasto_s,
       CAST(ct.comentarios AS INTEGER) AS comentarios,
       ct.responsaveis_ids, ct.rotulos
FROM src_cartoes ct
LEFT JOIN dim_pessoa pa ON pa.pessoa_id = ct.autor_id
LEFT JOIN dim_pessoa pf ON pf.pessoa_id = ct.fechado_por_id
LEFT JOIN dim_sprint s
  ON s.grupo = ct.grupo AND s.sprint = ct.sprint
""")

# dim_quadro_coluna: same sk numbering as relacional/csv/dim_quadro_coluna.csv
con.execute("""
CREATE TABLE dim_quadro_coluna AS
SELECT CAST(row_number() OVER (ORDER BY grupo, quadro, posicao) AS INTEGER) AS sk_quadro_coluna,
       grupo, quadro, posicao, coluna
FROM src_quadro_colunas
UNION ALL
SELECT -1, '(N/A)', '(n/a)', -1, '(n/a)'
""")

con.execute("""
CREATE TABLE fato_kanban_eventos AS
WITH dedup AS (
    SELECT grupo, cartao_numero, ocorrido_em, acao, coluna, pessoa_id,
           row_number() OVER (
               PARTITION BY grupo, cartao_numero, ocorrido_em, acao, coluna
               ORDER BY pessoa_id) AS rn
    FROM src_kanban_eventos
)
SELECT CAST(row_number() OVER (ORDER BY d.grupo, d.cartao_numero, d.ocorrido_em, d.acao, d.coluna) AS INTEGER) AS sk_evento,
       d.grupo, CAST(d.cartao_numero AS INTEGER) AS cartao_numero,
       p.sk_pessoa AS sk_pessoa,
       coalesce(q.sk_quadro_coluna, -1) AS sk_quadro_coluna,
       CAST(strftime(CAST(d.ocorrido_em AS TIMESTAMP), '%Y%m%d') AS INTEGER) AS sk_data_evento,
       CAST(d.ocorrido_em AS TIMESTAMP) AS ocorrido_em,
       d.acao,
       CASE WHEN d.coluna IS NULL OR trim(d.coluna) = '' THEN 'vazio'
            WHEN q.sk_quadro_coluna IS NOT NULL THEN 'coluna'
            ELSE 'rotulo' END AS tipo_evento,
       d.coluna
FROM dedup d
LEFT JOIN dim_pessoa p ON p.pessoa_id = d.pessoa_id
LEFT JOIN dim_quadro_coluna q
  ON q.grupo = d.grupo AND q.coluna = d.coluna AND q.sk_quadro_coluna <> -1
WHERE d.rn = 1
""")

for t in ["grupos", "pessoas", "sprints", "quadro_colunas",
          "commits", "merge_requests", "cartoes", "kanban_eventos"]:
    con.execute(f"DROP TABLE src_{t}")

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
