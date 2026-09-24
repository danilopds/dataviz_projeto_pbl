import duckdb

con = duckdb.connect("lakehouse/pbl.duckdb")
print("commits sem sprint:", con.execute(
    "SELECT count(*) FROM fato_commits "
    "WHERE sk_sprint_commitado IS NULL").fetchone())
print("por grupo/sprint:", con.execute(
    "SELECT grupo, sk_sprint_commitado, count(*) FROM fato_commits "
    "GROUP BY 1, 2 ORDER BY 1, 2").fetchall())
print("sprint bounds:", con.execute(
    "SELECT grupo, sprint, inicio_em, prazo_em FROM dim_sprint "
    "WHERE grupo IS NOT NULL ORDER BY grupo, sprint LIMIT 6").fetchall())
print("horas merge nulls (merged):", con.execute(
    "SELECT count(*) FROM fato_merge_requests "
    "WHERE situacao='merged' AND horas_para_merge IS NULL").fetchone())
print("tipo_evento:", con.execute(
    "SELECT tipo_evento, count(*) FROM fato_kanban_eventos "
    "GROUP BY 1").fetchall())
print("dim_sprint rows:", con.execute(
    "SELECT grupo, sprint, inicio_em, prazo_em FROM dim_sprint "
    "ORDER BY sk_sprint").fetchall())
