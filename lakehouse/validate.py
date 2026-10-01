import duckdb

con = duckdb.connect("lakehouse/pbl.duckdb")

print("dim_sprint (conformada):", con.execute(
    "SELECT sk_sprint, sprint, inicio_em, prazo_em FROM dim_sprint "
    "ORDER BY sk_sprint").fetchall())
print("dim_quadro_coluna (conformada):", con.execute(
    "SELECT sk_quadro_coluna, quadro, posicao, coluna FROM dim_quadro_coluna "
    "ORDER BY sk_quadro_coluna").fetchall())
print("commits sem sprint:", con.execute(
    "SELECT count(*) FROM fato_commits "
    "WHERE sk_sprint_commitado IS NULL").fetchone())
print("commits por grupo/sprint:", con.execute(
    "SELECT f.grupo, s.sprint, count(*) FROM fato_commits f "
    "LEFT JOIN dim_sprint s ON s.sk_sprint = f.sk_sprint_commitado "
    "GROUP BY 1, 2 ORDER BY 1, 2").fetchall())
print("sk_sprint invalido (MRs/cartoes/eventos):", con.execute(
    "SELECT (SELECT count(*) FROM fato_merge_requests m WHERE m.sk_sprint IS NOT NULL "
    "      AND NOT EXISTS (SELECT 1 FROM dim_sprint s WHERE s.sk_sprint = m.sk_sprint)),"
    "       (SELECT count(*) FROM fato_cartoes c WHERE c.sk_sprint IS NOT NULL "
    "      AND NOT EXISTS (SELECT 1 FROM dim_sprint s WHERE s.sk_sprint = c.sk_sprint)),"
    "       (SELECT count(*) FROM fato_kanban_eventos k WHERE k.sk_sprint_evento IS NOT NULL "
    "      AND NOT EXISTS (SELECT 1 FROM dim_sprint s WHERE s.sk_sprint = k.sk_sprint_evento))"
).fetchone())
print("fora de sprint (NULL):", con.execute(
    "SELECT (SELECT count(*) FROM fato_merge_requests WHERE sk_sprint IS NULL),"
    "       (SELECT count(*) FROM fato_cartoes WHERE sk_sprint IS NULL),"
    "       (SELECT count(*) FROM fato_kanban_eventos WHERE sk_sprint_evento IS NULL)"
).fetchone())
print("tipo_evento:", con.execute(
    "SELECT tipo_evento, count(*) FROM fato_kanban_eventos "
    "GROUP BY 1").fetchall())
print("sk_quadro_coluna invalido:", con.execute(
    "SELECT count(*) FROM fato_kanban_eventos k "
    "WHERE NOT EXISTS (SELECT 1 FROM dim_quadro_coluna q "
    "                  WHERE q.sk_quadro_coluna = k.sk_quadro_coluna)").fetchone())
print("tipo vs sk_quadro_coluna consistentes:", con.execute(
    "SELECT count(*) FROM fato_kanban_eventos k JOIN dim_quadro_coluna q "
    "USING (sk_quadro_coluna) "
    "WHERE (k.tipo_evento = 'coluna') <> (q.sk_quadro_coluna <> -1)").fetchone())
print("horas merge nulls (merged):", con.execute(
    "SELECT count(*) FROM fato_merge_requests "
    "WHERE situacao='merged' AND horas_para_merge IS NULL").fetchone())