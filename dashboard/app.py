"""Painel PBL — acompanhamento pedagógico dos grupos.

Executar:  streamlit run dashboard/app.py
Fonte:     lakehouse/pbl.duckdb (gerado por lakehouse/build_lakehouse.py)
"""
from pathlib import Path

import duckdb
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "lakehouse" / "pbl.duckdb"

st.set_page_config(page_title="Painel PBL", page_icon="📊", layout="wide")

COLOR_BAD = "#c62828"


# ---------------------------------------------------------------------------
# Dados
# ---------------------------------------------------------------------------
@st.cache_resource
def get_conn() -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(DB), read_only=True)


@st.cache_data(ttl=600)
def query(sql: str, **params) -> pd.DataFrame:
    con = get_conn()
    return con.execute(sql, params).fetchdf()


@st.cache_data(ttl=600)
def grupos_disponiveis() -> list[str]:
    return query(
        "SELECT grupo FROM dim_grupo ORDER BY grupo").iloc[:, 0].tolist()


def gini(series: pd.Series) -> float:
    values = sorted(float(v) for v in series)
    n = len(values)
    if n == 0 or sum(values) == 0:
        return 0.0
    cumulative = sum((i + 1) * v for i, v in enumerate(values))
    return (2 * cumulative) / (n * sum(values)) - (n + 1) / n


def fmt_horas(h: float) -> str:
    if pd.isna(h):
        return "—"
    if h < 24:
        return f"{h:.0f} h"
    return f"{h / 24:.1f} d"


# ---------------------------------------------------------------------------
# Filtros
# ---------------------------------------------------------------------------
st.sidebar.title("🎯 Painel PBL")
st.sidebar.caption("Turma T28 · Ciclo 2026-1b")

todos_grupos = grupos_disponiveis()
grupos_sel = st.sidebar.multiselect(
    "Grupos", todos_grupos, default=todos_grupos)

grupos_in = ",".join(f"'{g}'" for g in grupos_sel) or "''"
sprints_df = query(
    f"SELECT sk_sprint, grupo, sprint, inicio_em, prazo_em FROM dim_sprint "
    f"WHERE grupo IN ({grupos_in}) ORDER BY grupo, sprint")
sprint_labels = (
    sprints_df["grupo"] + " · " + sprints_df["sprint"]).tolist()
sprints_sel = st.sidebar.multiselect(
    "Sprints", sprint_labels, default=sprint_labels)

sk_sel = sprints_df.loc[
    (sprints_df["grupo"] + " · " + sprints_df["sprint"]).isin(sprints_sel),
    "sk_sprint"].tolist()
sk_in = ",".join(str(int(s)) for s in sk_sel) or "-999"
sem_sprint = st.sidebar.checkbox(
    "Incluir atividade fora de sprint", value=True)

st.sidebar.markdown("---")
st.sidebar.subheader("Limiares de alerta")
LIM_CRUNCH = st.sidebar.slider(
    "% de commits nos 2 últimos dias da sprint (crunch)", 5, 80, 35)
LIM_TOP1 = st.sidebar.slider(
    "% de commits da pessoa mais ativa", 20, 90, 45)
LIM_GINI = st.sidebar.slider(
    "Índice de Gini da distribuição de commits", 0.20, 0.90, 0.55)
LIM_REVIEW = st.sidebar.slider(
    "Mediana de horas para merge", 12, 240, 72)
LIM_SEM_COMENT = st.sidebar.slider(
    "% de MRs mesclados sem comentários", 10, 90, 40)
LIM_CORR = st.sidebar.slider(
    "Correlação quadro × repositório mínima", 0.0, 1.0, 0.5)

grupos_cond = f"f.grupo IN ({grupos_in})"


def sprint_cond(col: str) -> str:
    """Filtro por sprint. `col IS NULL` = atividade fora de qualquer janela."""
    base = f"{col} IN ({sk_in})"
    if sem_sprint:
        return f"({base} OR {col} IS NULL)"
    return base


# ---------------------------------------------------------------------------
# Queries base
# ---------------------------------------------------------------------------
kpi_commits = query(f"""
    SELECT count(*) AS n, coalesce(sum(linhas_total), 0) AS linhas
    FROM fato_commits f WHERE {grupos_cond}
""")

kpi_mrs = query(f"""
    SELECT count(*) AS n_total,
           count(*) FILTER (WHERE situacao = 'merged') AS n_merged,
           coalesce(avg(horas_para_merge) FILTER (WHERE situacao='merged'), 0) AS media_h
    FROM fato_merge_requests f WHERE {grupos_cond}
""")

kpi_cartoes = query(f"""
    SELECT count(*) AS n_total,
           count(*) FILTER (WHERE situacao = 'closed') AS n_closed
    FROM fato_cartoes f WHERE {grupos_cond}
""")

kpi_membros = query(f"""
    SELECT count(DISTINCT p.pessoa_id) AS n
    FROM dim_pessoa p
    WHERE p.eh_placeholder = 0
      AND p.grupo IN ({grupos_in})
      AND (p.sk_pessoa IN (SELECT DISTINCT sk_autor FROM fato_commits
                           WHERE grupo IN ({grupos_in}))
        OR p.sk_pessoa IN (SELECT DISTINCT sk_autor FROM fato_merge_requests
                           WHERE grupo IN ({grupos_in})))
""")


# ---------------------------------------------------------------------------
# Cabeçalho e visão geral
# ---------------------------------------------------------------------------
st.title("📊 Painel PBL — Repositório GitLab & Quadro Kanban")
st.caption(
    "Ferramenta de apoio ao coordenador: ritmo, carga, revisão e "
    "consistência quadro × repositório.")

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Commits", f"{int(kpi_commits['n'][0]):,}".replace(",", "."),
          f"{int(kpi_commits['linhas'][0]):,} linhas".replace(",", "."))
c2.metric("Merge Requests", f"{int(kpi_mrs['n_total'][0])}",
          f"{int(kpi_mrs['n_merged'][0])} mesclados")
c3.metric("Cartões Kanban", f"{int(kpi_cartoes['n_total'][0])}",
          f"{int(kpi_cartoes['n_closed'][0])} fechados")
c4.metric("Membros ativos", str(int(kpi_membros['n'][0])))
c5.metric("Sprints no filtro", str(len(sk_sel)))

tab_over, tab_ritmo, tab_carga, tab_review, tab_quadro = st.tabs(
    ["🏠 Visão geral", "⏱️ Ritmo & Prazos", "👥 Carga de Trabalho",
     "🔍 Code Review", "🧩 Quadro × Repositório"])

# =========================================================================
# TAB 0 — VISÃO GERAL
# =========================================================================
with tab_over:
    st.subheader("Sinais de atenção pedagógica")
    st.caption(
        "Alertas baseados em limiares configuráveis na barra lateral. "
        "Vermelho = acima do limiar; amarelo = próximo (80% do limiar).")

    alertas: list[dict] = []

    # Alerta 1 — crunch por grupo (últimos 2 dias da sprint)
    crunch_df = query(f"""
        SELECT s.grupo, s.sprint,
               count(*) AS total,
               count(*) FILTER (
                   WHERE CAST(f.commitado_em AS DATE)
                         BETWEEN s.prazo_em - INTERVAL 1 DAY AND s.prazo_em
               ) AS fim,
               count(*) FILTER (
                   WHERE CAST(f.commitado_em AS DATE)
                         BETWEEN s.inicio_em AND s.prazo_em - INTERVAL 2 DAY
               ) AS inicio_meio
        FROM fato_commits f
        JOIN dim_sprint s
          ON s.sk_sprint = f.sk_sprint_commitado
        WHERE {grupos_cond}
          AND {sprint_cond("f.sk_sprint_commitado")}
        GROUP BY s.grupo, s.sprint
        HAVING count(*) >= 10
        ORDER BY s.grupo, s.sprint
    """)
    crunch_df["pct_fim"] = (
        100 * crunch_df["fim"] / crunch_df["total"]).round(1)

    # Alerta 2 — concentração de carga por grupo
    carga_df = query(f"""
        SELECT f.grupo, coalesce(p.pessoa_id, '(desconhecido)') AS pessoa,
               count(*) AS commits
        FROM fato_commits f
        LEFT JOIN dim_pessoa p ON p.sk_pessoa = f.sk_autor
        WHERE {grupos_cond}
          AND coalesce(p.eh_placeholder, 0) = 0
        GROUP BY f.grupo, pessoa
    """)
    conc_df = carga_df.groupby("grupo").agg(
        commits=("commits", "sum"),
        top1=("commits", "max"),
        pessoas=("commits", "count")).reset_index()
    conc_df["pct_top1"] = (100 * conc_df["top1"] / conc_df["commits"]).round(1)
    conc_df["gini"] = carga_df.groupby("grupo")["commits"].apply(
        gini).round(3).values

    # Alerta 3 — code review por grupo
    review_df = query(f"""
        SELECT f.grupo,
               count(*) FILTER (WHERE situacao = 'merged') AS merged,
               count(*) FILTER (WHERE situacao = 'merged'
                                AND comentarios = 0) AS sem_coment,
               median(horas_para_merge) FILTER (
                   WHERE situacao = 'merged') AS mediana_h
        FROM fato_merge_requests f
        WHERE {grupos_cond}
        GROUP BY f.grupo
        ORDER BY f.grupo
    """)
    review_df["pct_sem_coment"] = (
        100 * review_df["sem_coment"] / review_df["merged"]).round(1)

    # Alerta 4 — quadro × repositório por grupo
    qxr_df = query(f"""
        WITH commits_sprint AS (
            SELECT f.grupo, f.sk_sprint_commitado AS sk_sprint,
                   count(*) AS commits
            FROM fato_commits f
            WHERE {grupos_cond} AND f.sk_sprint_commitado IS NOT NULL
            GROUP BY 1, 2
        ),
        cartoes_sprint AS (
            SELECT f.grupo, f.sk_sprint, count(*) AS fechados
            FROM fato_cartoes f
            WHERE {grupos_cond} AND f.situacao = 'closed'
              AND f.sk_sprint IS NOT NULL
            GROUP BY 1, 2
        )
        SELECT coalesce(c.grupo, k.grupo) AS grupo,
               coalesce(c.sk_sprint, k.sk_sprint) AS sk_sprint,
               coalesce(c.commits, 0) AS commits,
               coalesce(k.fechados, 0) AS cartoes_fechados
        FROM commits_sprint c
        FULL OUTER JOIN cartoes_sprint k
          ON k.grupo = c.grupo AND k.sk_sprint = c.sk_sprint
    """)
    qxr_ok = len(qxr_df[(qxr_df["commits"] > 0)
                        | (qxr_df["cartoes_fechados"] > 0)]) >= 2
    if qxr_ok and len(qxr_df) >= 3:
        corr = qxr_df["commits"].corr(qxr_df["cartoes_fechados"]).round(2)
    else:
        corr = None

    for _, row in crunch_df.iterrows():
        pct = row["pct_fim"]
        nivel = ("bad" if pct > LIM_CRUNCH
                 else "warn" if pct > LIM_CRUNCH * 0.8 else "ok")
        alertas.append({
            "nivel": nivel, "tema": "Ritmo",
            "grupo": row["grupo"],
            "mensagem": (f"{row['sprint']}: {pct}% dos commits nos 2 "
                         f"últimos dias ({int(row['fim'])}/"
                         f"{int(row['total'])}) — "
                         f"{'vespera detectada' if nivel != 'ok' else 'ritmo saudável'}")})

    for _, row in conc_df.iterrows():
        if row["pct_top1"] > LIM_TOP1 or row["gini"] > LIM_GINI:
            nivel = ("bad" if row["pct_top1"] > LIM_TOP1
                     and row["gini"] > LIM_GINI else "warn")
        else:
            nivel = "ok"
        alertas.append({
            "nivel": nivel, "tema": "Carga",
            "grupo": row["grupo"],
            "mensagem": (f"top-1 = {row['pct_top1']}% dos commits "
                         f"(Gini {row['gini']}) — "
                         f"{'concentração' if nivel != 'ok' else 'distribuição equilibrada'}")})

    for _, row in review_df.iterrows():
        cond_bad = (row["mediana_h"] > LIM_REVIEW
                    and row["pct_sem_coment"] > LIM_SEM_COMENT)
        cond_warn = (row["mediana_h"] > LIM_REVIEW * 0.8
                     or row["pct_sem_coment"] > LIM_SEM_COMENT * 0.8)
        nivel = "bad" if cond_bad else "warn" if cond_warn else "ok"
        alertas.append({
            "nivel": nivel, "tema": "Review",
            "grupo": row["grupo"],
            "mensagem": (f"mediana p/ merge {fmt_horas(row['mediana_h'])}; "
                         f"{row['pct_sem_coment']}% sem comentários")})

    if corr is not None:
        alertas.append({
            "nivel": ("bad" if abs(corr) < LIM_CORR * 0.5
                      else "warn" if abs(corr) < LIM_CORR else "ok"),
            "tema": "Quadro×Repo", "grupo": "—",
            "mensagem": (f"correlação commits × cartões fechados "
                         f"por sprint = {corr} — "
                         f"{'divergência quadro/repositório' if abs(corr) < LIM_CORR else 'quadro reflete o repositório'}")})

    alertas_df = pd.DataFrame(alertas)
    ICONES = {"bad": "🔴", "warn": "🟡", "ok": "🟢"}
    for tema in ["Ritmo", "Carga", "Review", "Quadro×Repo"]:
        sub = alertas_df[alertas_df["tema"] == tema]
        if sub.empty:
            continue
        bad = int((sub["nivel"] == "bad").sum())
        warn = int((sub["nivel"] == "warn").sum())
        icon = ICONES["bad"] if bad else ICONES["warn"] if warn else ICONES["ok"]
        st.markdown(f"#### {icon} {tema}")
        for _, a in sub.iterrows():
            if a["nivel"] == "ok":
                st.markdown(f"&nbsp;&nbsp;🟢 `{a['grupo']}` {a['mensagem']}",
                            unsafe_allow_html=True)
            else:
                cor = ("red" if a["nivel"] == "bad" else "orange")
                st.markdown(
                    f"&nbsp;&nbsp;{ICONES[a['nivel']]} `{a['grupo']}` "
                    f":{cor}[{a['mensagem']}]", unsafe_allow_html=True)

    st.subheader("Resumo por grupo")
    resumo_df = query(f"""
        SELECT g.grupo,
               (SELECT count(*) FROM fato_commits f
                 WHERE f.grupo = g.grupo
                   AND {sprint_cond('f.sk_sprint_commitado')}) AS commits,
               (SELECT count(*) FROM fato_merge_requests f
                 WHERE f.grupo = g.grupo
                   AND {sprint_cond('f.sk_sprint')}) AS mrs,
               (SELECT count(*) FROM fato_merge_requests f
                 WHERE f.grupo = g.grupo AND f.situacao='merged'
                   AND {sprint_cond('f.sk_sprint')}) AS mrs_merged,
               (SELECT count(*) FROM fato_cartoes f
                 WHERE f.grupo = g.grupo AND f.situacao='closed'
                   AND {sprint_cond('f.sk_sprint')}) AS cartoes_fechados,
               (SELECT count(*) FROM fato_kanban_eventos f
                 WHERE f.grupo = g.grupo
                   AND {sprint_cond('f.sk_data_evento')}) AS eventos_kanban
        FROM dim_grupo g
        WHERE g.grupo IN ({grupos_in})
        ORDER BY g.grupo
    """)
    st.dataframe(resumo_df, use_container_width=True, hide_index=True)

# =========================================================================
# TAB 1 — RITMO & PRAZOS
# =========================================================================
with tab_ritmo:
    st.subheader("O grupo trabalhou ao longo do módulo ou na véspera?")
    serie = query(f"""
        SELECT CAST(f.commitado_em AS DATE) AS dia,
               f.grupo, count(*) AS commits
        FROM fato_commits f
        WHERE {grupos_cond} AND {sprint_cond('f.sk_sprint_commitado')}
        GROUP BY 1, 2 ORDER BY 1
    """)
    fig = px.area(serie, x="dia", y="commits", color="grupo",
                  title="Commits por dia (data de commitado_em)",
                  labels={"dia": "Data", "commits": "Commits",
                          "grupo": "Grupo"})
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("**Distribuição dentro de cada sprint** "
                "(início/meio = da abertura até 2 dias antes do prazo; "
                "fim = 2 últimos dias)")
    dist_df = crunch_df.copy()
    dist_df["pct_inicio_meio"] = (
        100 * dist_df["inicio_meio"] / dist_df["total"]).round(1)
    dist_long = dist_df.melt(
        id_vars=["grupo", "sprint"],
        value_vars=["pct_inicio_meio", "pct_fim"],
        var_name="janela", value_name="pct")
    nomes = {"pct_inicio_meio": "Início/meio", "pct_fim": "Véspera (2 dias)"}
    dist_long["janela"] = dist_long["janela"].map(nomes)
    fig = px.bar(
        dist_long, x="sprint", y="pct", color="janela",
        facet_col="grupo",
        color_discrete_map={
            "Início/meio": "#4c78a8", "Véspera (2 dias)": COLOR_BAD},
        title="% de commits por janela dentro da sprint",
        labels={"pct": "% dos commits", "sprint": "", "janela": "Janela"})
    fig.for_each_yaxis(lambda ax: ax.update(title_text="% dos commits"))
    st.plotly_chart(fig, use_container_width=True)

    c1, c2 = st.columns([3, 2])
    with c1:
        tabela = dist_df.rename(columns={
            "grupo": "Grupo", "sprint": "Sprint", "total": "Commits",
            "fim": "Véspera", "inicio_meio": "Início/meio",
            "pct_fim": "% véspera", "pct_inicio_meio": "% início/meio"})
        st.dataframe(
            tabela[["Grupo", "Sprint", "Commits", "% início/meio",
                    "% véspera"]],
            use_container_width=True, hide_index=True)
    with c2:
        acima = dist_df[dist_df["pct_fim"] > LIM_CRUNCH]
        if acima.empty:
            st.success("Nenhum sprint acima do limiar de véspera.")
        else:
            for _, r in acima.iterrows():
                st.error(
                    f"**{r['grupo']} · {r['sprint']}** — {r['pct_fim']}% "
                    f"dos commits ({int(r['fim'])}/{int(r['total'])}) nos "
                    f"2 últimos dias. Limiar: {LIM_CRUNCH}%.")

    fora = query(f"""
        SELECT f.grupo,
               count(*) FILTER (WHERE f.sk_sprint_commitado IS NULL) AS fora_sprint,
               count(*) AS total
        FROM fato_commits f
        WHERE {grupos_cond}
        GROUP BY 1
    """)
    fora["% fora"] = (100 * fora["fora_sprint"] / fora["total"]).round(1)
    st.caption(
        "Commits fora de qualquer janela de sprint (antes de 2026-04-22 ou "
        "após 2026-06-26): "
        + ", ".join(f"{row['grupo']}: {row['% fora']}%"
                    for _, row in fora.iterrows()))

# =========================================================================
# TAB 2 — CARGA DE TRABALHO
# =========================================================================
with tab_carga:
    st.subheader("O trabalho foi distribuído ou concentrado?")
    incluir_placeholders = st.toggle("Incluir placeholders ([bot]/[externo])",
                                     value=False)

    ph_cond = "0 = 0" if incluir_placeholders else "coalesce(p.eh_placeholder,0) = 0"

    carga = query(f"""
        SELECT f.grupo, coalesce(p.pessoa_id, '(sem autor)') AS pessoa,
               count(DISTINCT f.commit_id) AS commits,
               coalesce(sum(f.linhas_total), 0) AS linhas
        FROM fato_commits f
        LEFT JOIN dim_pessoa p ON p.sk_pessoa = f.sk_autor
        WHERE {grupos_cond} AND {ph_cond}
          AND {sprint_cond('f.sk_sprint_commitado')}
        GROUP BY 1, 2
    """)
    carga_mr = query(f"""
        SELECT f.grupo, coalesce(p.pessoa_id, '(sem autor)') AS pessoa,
               count(*) AS mrs
        FROM fato_merge_requests f
        LEFT JOIN dim_pessoa p ON p.sk_pessoa = f.sk_autor
        WHERE {grupos_cond} AND {ph_cond}
          AND {sprint_cond('f.sk_sprint')}
        GROUP BY 1, 2
    """)
    carga_ct = query(f"""
        SELECT f.grupo, coalesce(p.pessoa_id, '(sem autor)') AS pessoa,
               count(*) FILTER (WHERE f.situacao='closed') AS cartoes_fechados
        FROM fato_cartoes f
        LEFT JOIN dim_pessoa p ON p.sk_pessoa = f.sk_autor
        WHERE {grupos_cond} AND {ph_cond}
          AND {sprint_cond('f.sk_sprint')}
        GROUP BY 1, 2
    """)
    carga_total = (carga.merge(carga_mr, on=["grupo", "pessoa"], how="outer")
                   .merge(carga_ct, on=["grupo", "pessoa"], how="outer")
                   .fillna(0))
    carga_total[["commits", "mrs", "cartoes_fechados", "linhas"]] = \
        carga_total[["commits", "mrs", "cartoes_fechados", "linhas"]].astype(int)
    carga_total["total"] = (carga_total["commits"] + carga_total["mrs"]
                            + carga_total["cartoes_fechados"])
    carga_total = carga_total.sort_values(
        ["grupo", "total"], ascending=[True, False])

    grupo_foco = st.selectbox("Grupo para destaque", grupos_sel)
    foco = carga_total[carga_total["grupo"] == grupo_foco].head(15)
    fig = go.Figure()
    fig.add_bar(name="Commits", x=foco["pessoa"], y=foco["commits"],
                marker_color="#4c78a8")
    fig.add_bar(name="MRs", x=foco["pessoa"], y=foco["mrs"],
                marker_color="#f58518")
    fig.add_bar(name="Cartões fechados", x=foco["pessoa"],
                y=foco["cartoes_fechados"], marker_color="#54a24b")
    fig.update_layout(
        barmode="stack",
        title=f"Distribuição de trabalho — {grupo_foco}",
        xaxis_title=None, yaxis_title="Itens")
    fig.update_xaxes(tickangle=-45)
    st.plotly_chart(fig, use_container_width=True)

    c1, c2, c3 = st.columns(3)
    idx = 0
    for grupo_nome, sub in carga_total.groupby("grupo"):
        gsub = sub[sub["commits"] > 0]
        if gsub.empty:
            continue
        g = gini(gsub["commits"])
        top1 = 100 * gsub["commits"].max() / gsub["commits"].sum()
        cor = ("bad" if g > LIM_GINI or top1 > LIM_TOP1
               else "warn" if g > LIM_GINI * 0.8 or top1 > LIM_TOP1 * 0.8
               else "ok")
        with [c1, c2, c3][idx % 3]:
            st.metric(
                f"{grupo_nome} — Gini (commits)", f"{g:.2f}",
                f"top-1 = {top1:.0f}%",
                delta_color=("inverse" if cor == "bad"
                             else "normal" if cor == "warn" else "off"))
        idx += 1

    st.markdown("**Matriz pessoa × sprint (commits)**")
    matriz = query(f"""
        SELECT f.grupo, coalesce(p.pessoa_id, '(sem autor)') AS pessoa,
               s.sprint, count(*) AS commits
        FROM fato_commits f
        LEFT JOIN dim_pessoa p ON p.sk_pessoa = f.sk_autor
        LEFT JOIN dim_sprint s ON s.sk_sprint = f.sk_sprint_commitado
        WHERE {grupos_cond} AND {ph_cond}
          AND {sprint_cond('f.sk_sprint_commitado')}
          AND f.sk_sprint_commitado IS NOT NULL
        GROUP BY 1, 2, 3
    """)
    if not matriz.empty:
        matriz["pessoa_sprint"] = matriz["grupo"] + " · " + matriz["pessoa"]
        pivot = matriz.pivot_table(
            index="pessoa_sprint", columns="sprint",
            values="commits", fill_value=0)
        fig = px.imshow(pivot, aspect="auto", color_continuous_scale="Blues",
                        labels=dict(color="Commits"))
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("**Tabela detalhada**")
    st.dataframe(
        carga_total.rename(columns={
            "grupo": "Grupo", "pessoa": "Pessoa", "commits": "Commits",
            "linhas": "Linhas", "mrs": "MRs",
            "cartoes_fechados": "Cartões fechados", "total": "Total"}),
        use_container_width=True, hide_index=True)

# =========================================================================
# TAB 3 — CODE REVIEW
# =========================================================================
with tab_review:
    st.subheader("Como está o code review?")

    merged = query(f"""
        SELECT f.*, p.pessoa_id AS autor, pm.pessoa_id AS merged_por
        FROM fato_merge_requests f
        LEFT JOIN dim_pessoa p ON p.sk_pessoa = f.sk_autor
        LEFT JOIN dim_pessoa pm ON pm.sk_pessoa = f.sk_merged_por
        WHERE {grupos_cond} AND f.situacao = 'merged'
          AND {sprint_cond('f.sk_sprint')}
    """)

    if merged.empty:
        st.info("Nenhum MR mesclado no filtro atual.")
    else:
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("MRs mesclados", len(merged))
        k2.metric("Mediana p/ merge", fmt_horas(merged["horas_para_merge"].median()))
        k3.metric("Média p/ merge", fmt_horas(merged["horas_para_merge"].mean()))
        k4.metric("Sem comentários",
                  f"{100 * (merged['comentarios'] == 0).mean():.0f}%")

        c1, c2 = st.columns(2)
        with c1:
            fig = px.histogram(
                merged, x="horas_para_merge", color="grupo", nbins=40,
                title="Distribuição do tempo até o merge (horas)",
                labels={"horas_para_merge": "Horas", "count": "MRs",
                        "grupo": "Grupo"})
            st.plotly_chart(fig, use_container_width=True)
        with c2:
            fig = px.histogram(
                merged, x="comentarios", color="grupo", nbins=20,
                title="Comentários por MR (mesclados)",
                labels={"comentarios": "Comentários", "count": "MRs",
                        "grupo": "Grupo"})
            st.plotly_chart(fig, use_container_width=True)

        c3, c4 = st.columns(2)
        with c3:
            aprov = (merged.groupby("merged_por").size()
                     .sort_values(ascending=False).head(10).reset_index())
            aprov.columns = ["Quem mesclou", "MRs mesclados"]
            fig = px.bar(aprov, y="Quem mesclou", x="MRs mesclados",
                         orientation="h",
                         title="Top aprovadores (merged_por)")
            fig.update_layout(yaxis={"categoryorder": "total ascending"})
            st.plotly_chart(fig, use_container_width=True)
        with c4:
            tamanho = query(f"""
                SELECT f.grupo,
                       count(*) FILTER (WHERE f.e_merge = 1) AS merge_commits,
                       coalesce(sum(f.linhas_total)
                                FILTER (WHERE f.e_merge = 1), 0) AS linhas_merge
                FROM fato_commits f
                WHERE {grupos_cond}
                  AND {sprint_cond('f.sk_sprint_commitado')}
                GROUP BY 1
            """)
            fig = px.bar(
                tamanho, x="grupo", y="linhas_merge",
                color="grupo",
                title="Tamanho das integrações (linhas em commits de merge)",
                labels={"linhas_merge": "Linhas em commits de merge",
                        "grupo": "Grupo"})
            st.plotly_chart(fig, use_container_width=True)

        st.markdown("**Alertas de review**")
        for grupo_nome, sub in merged.groupby("grupo"):
            med = sub["horas_para_merge"].median()
            sem = 100 * (sub["comentarios"] == 0).mean()
            if med > LIM_REVIEW and sem > LIM_SEM_COMENT:
                st.error(
                    f"**{grupo_nome}** — mediana {fmt_horas(med)} "
                    f"(limiar {fmt_horas(LIM_REVIEW)}) e {sem:.0f}% dos MRs "
                    f"sem comentários (limiar {LIM_SEM_COMENT}%).")
            elif med > LIM_REVIEW * 0.8 or sem > LIM_SEM_COMENT * 0.8:
                st.warning(
                    f"**{grupo_nome}** — mediana {fmt_horas(med)}; "
                    f"{sem:.0f}% sem comentários.")

        st.markdown("**MRs mais ativos** (ordenados por comentários)")
        top_mrs = merged.sort_values(
            ["comentarios", "horas_para_merge"], ascending=[False, True])
        st.dataframe(
            top_mrs[["grupo", "mr_numero", "titulo", "autor", "merged_por",
                     "situacao", "comentarios", "horas_para_merge",
                     "criado_em", "merged_em"]].rename(columns={
                "grupo": "Grupo", "mr_numero": "MR", "titulo": "Título",
                "autor": "Autor", "merged_por": "Mesclado por",
                "comentarios": "Comentários",
                "horas_para_merge": "Horas p/ merge",
                "criado_em": "Aberto em", "merged_em": "Mesclado em"}),
            use_container_width=True, hide_index=True, height=420)

        if st.checkbox("Mostrar apenas MRs sem comentários"):
            st.dataframe(
                top_mrs[top_mrs["comentarios"] == 0][
                    ["grupo", "mr_numero", "titulo", "autor",
                     "horas_para_merge"]],
                use_container_width=True, hide_index=True)

# =========================================================================
# TAB 4 — QUADRO × REPOSITÓRIO
# =========================================================================
with tab_quadro:
    st.subheader("O quadro reflete o repositório?")

    qxr = query(f"""
        WITH commits_sprint AS (
            SELECT f.grupo, s.sprint, f.sk_sprint_commitado AS sk_sprint,
                   count(*) AS commits,
                   count(DISTINCT f.sk_autor) AS dev_ativos
            FROM fato_commits f
            LEFT JOIN dim_sprint s ON s.sk_sprint = f.sk_sprint_commitado
            WHERE {grupos_cond} AND f.sk_sprint_commitado IS NOT NULL
            GROUP BY 1, 2, 3
        ),
        cartoes_sprint AS (
            SELECT f.grupo, s.sprint, f.sk_sprint,
                   count(*) AS cartoes_criados,
                   count(*) FILTER (WHERE f.situacao='closed') AS cartoes_fechados,
                   coalesce(sum(f.tempo_gasto_s), 0) / 3600.0 AS horas_gastas
            FROM fato_cartoes f
            LEFT JOIN dim_sprint s ON s.sk_sprint = f.sk_sprint
            WHERE {grupos_cond} AND f.sk_sprint IS NOT NULL
              AND {sprint_cond('f.sk_sprint')}
            GROUP BY 1, 2, 3
        )
        SELECT c.grupo, c.sprint, c.commits, c.dev_ativos,
               coalesce(k.cartoes_criados, 0) AS cartoes_criados,
               coalesce(k.cartoes_fechados, 0) AS cartoes_fechados,
               coalesce(k.horas_gastas, 0) AS horas_gastas
        FROM commits_sprint c
        LEFT JOIN cartoes_sprint k
          ON k.grupo = c.grupo AND k.sk_sprint = c.sk_sprint
        ORDER BY c.grupo, c.sprint
    """)

    if qxr.empty:
        st.info("Sem dados no filtro atual.")
    else:
        fig = go.Figure()
        fig.add_bar(name="Cartões fechados", x=qxr["grupo"] + " · " + qxr["sprint"],
                    y=qxr["cartoes_fechados"], marker_color="#54a24b")
        fig.add_bar(name="Commits", x=qxr["grupo"] + " · " + qxr["sprint"],
                    y=qxr["commits"], marker_color="#4c78a8")
        fig.update_layout(
            barmode="group",
            title="Cartões fechados × commits por sprint",
            yaxis_title="Quantidade")
        fig.update_xaxes(tickangle=-45)
        st.plotly_chart(fig, use_container_width=True)

        if len(qxr) >= 3:
            corr = qxr["commits"].corr(qxr["cartoes_fechados"]).round(2)
            if abs(corr) < LIM_CORR:
                st.error(
                    f"Correlação commits × cartões fechados = **{corr}** "
                    f"(abaixo do limiar {LIM_CORR}). O quadro não está "
                    f"acompanhando o repositório — investigar cartões "
                    f"empilhados ou commits sem rastreio.")
            else:
                st.success(
                    f"Correlação commits × cartões fechados = **{corr}** "
                    f"— quadro e repositório caminham juntos.")

        vinculo = query(f"""
            WITH refs AS (
                SELECT f.grupo,
                       regexp_extract(f.titulo, '#([0-9]+)', 1) AS ref
                FROM fato_commits f
                WHERE {grupos_cond}
                  AND {sprint_cond('f.sk_sprint_commitado')}
            )
            SELECT r.grupo,
                   count(*) AS commits_total,
                   count(*) FILTER (WHERE r.ref <> '') AS commits_com_ref,
                   count(DISTINCT TRY_CAST(r.ref AS INTEGER))
                       FILTER (WHERE r.ref <> '') AS cartoes_distintos
            FROM refs r
            GROUP BY 1
        """)
        cartoes_tot = query(f"""
            SELECT f.grupo, count(*) AS cartoes_total
            FROM fato_cartoes f WHERE {grupos_cond} GROUP BY 1
        """)
        vinculo = vinculo.merge(cartoes_tot, on="grupo")
        vinculo["% commits com #"] = (
            100 * vinculo["commits_com_ref"] / vinculo["commits_total"]).round(1)
        vinculo["% cartões citados"] = (
            100 * vinculo["cartoes_distintos"] / vinculo["cartoes_total"]).round(1)
        st.markdown(
            "**Rastreio heurístico via `#N`** (número do cartão citado em "
            "títulos/branches de commits — aproximação do extrator)")
        st.dataframe(
            vinculo.rename(columns={
                "grupo": "Grupo", "commits_total": "Commits",
                "commits_com_ref": "Com #N",
                "cartoes_distintos": "Cartões distintos citados",
                "cartoes_total": "Cartões no quadro"}),
            use_container_width=True, hide_index=True)

        st.markdown("**Ritmo do quadro: eventos por tipo**")
        eventos = query(f"""
            SELECT f.grupo, s.sprint, f.tipo_evento, count(*) AS n
            FROM fato_kanban_eventos f
            LEFT JOIN dim_sprint s
              ON s.grupo = f.grupo
             AND CAST(f.ocorrido_em AS DATE) BETWEEN s.inicio_em AND s.prazo_em
            WHERE {grupos_cond} AND {sprint_cond('f.sk_data_evento')}
            GROUP BY 1, 2, 3
        """)
        eventos["grupo_sprint"] = eventos["grupo"] + " · " + eventos["sprint"].fillna("(fora)")
        fig = px.bar(eventos, x="grupo_sprint", y="n", color="tipo_evento",
                     title="Eventos do Kanban por sprint (coluna / rótulo)",
                     labels={"n": "Eventos", "tipo_evento": "Tipo"})
        fig.update_xaxes(tickangle=-45)
        st.plotly_chart(fig, use_container_width=True)

        st.caption(
            "Como ler: sprints com muitos commits e poucos cartões fechados "
            "indicam trabalho técnico fora do quadro; o contrário indica "
            "plano sem execução versionada.")
