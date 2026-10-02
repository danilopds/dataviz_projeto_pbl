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
# Okabe-Ito (seguro para daltonismo); um grupo mantém a mesma cor em todo o painel.
PALETA_GRUPOS = ["#0072B2", "#E69F00", "#CC79A7", "#009E73", "#D55E00",
                 "#56B4E9", "#F0E442", "#000000"]
COR_COMMITS = "#4c78a8"
COR_MRS = "#f58518"
COR_CARTOES = "#54a24b"


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
        "SELECT grupo FROM dim_grupo WHERE sk_grupo <> -1 "
        "ORDER BY grupo").iloc[:, 0].tolist()


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
CORES_GRUPO = {g: PALETA_GRUPOS[i % len(PALETA_GRUPOS)]
               for i, g in enumerate(todos_grupos)}
grupos_sel = st.sidebar.multiselect(
    "Grupos", todos_grupos, default=todos_grupos)

grupos_in = ",".join(f"'{g}'" for g in grupos_sel) or "''"
sprints_df = query(
    "SELECT sk_sprint, sprint, inicio_em, prazo_em FROM dim_sprint "
    "WHERE sk_sprint <> -1 ORDER BY sk_sprint")
sprints_df["label"] = (
    sprints_df["sprint"] + " · "
    + sprints_df["inicio_em"].dt.strftime("%d/%m") + "–"
    + sprints_df["prazo_em"].dt.strftime("%d/%m"))
sprint_labels = sorted(sprints_df["label"].unique().tolist())
sprints_sel = st.sidebar.multiselect(
    "Sprints", sprint_labels, default=sprint_labels)

sk_sel = sprints_df.loc[
    sprints_df["label"].isin(sprints_sel), "sk_sprint"].tolist()
sk_in = ",".join(str(int(s)) for s in sk_sel) or "-999"
sem_sprint = st.sidebar.checkbox(
    "Incluir atividade fora de sprint", value=False)

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
    SELECT count(*) FILTER (WHERE coalesce(p.eh_placeholder, 0) = 0) AS membros,
           count(*) AS total
    FROM fato_commits f
    LEFT JOIN dim_pessoa p ON p.sk_pessoa = f.sk_autor
    WHERE {grupos_cond} AND {sprint_cond('f.sk_sprint_commitado')}
""")

kpi_mrs = query(f"""
    SELECT count(*) AS n_total,
           count(*) FILTER (WHERE situacao = 'merged') AS n_merged
    FROM fato_merge_requests f
    WHERE {grupos_cond} AND {sprint_cond('f.sk_sprint')}
""")

kpi_cartoes = query(f"""
    SELECT count(*) AS n_total,
           count(*) FILTER (WHERE situacao = 'closed') AS n_closed
    FROM fato_cartoes f
    WHERE {grupos_cond} AND {sprint_cond('f.sk_sprint')}
""")

# Atividade por repositório (f.grupo), mesma base do gráfico de carga.
kpi_membros = query(f"""
    WITH ativ AS (
        SELECT grupo, sk_autor FROM fato_commits
        WHERE grupo IN ({grupos_in}) AND {sprint_cond('sk_sprint_commitado')}
        UNION
        SELECT grupo, sk_autor FROM fato_merge_requests
        WHERE grupo IN ({grupos_in}) AND {sprint_cond('sk_sprint')}
        UNION
        SELECT grupo, sk_autor FROM fato_cartoes
        WHERE grupo IN ({grupos_in}) AND situacao = 'closed'
          AND {sprint_cond('sk_sprint')}
    )
    SELECT DISTINCT a.grupo, p.pessoa_id
    FROM ativ a JOIN dim_pessoa p ON p.sk_pessoa = a.sk_autor
    WHERE p.eh_placeholder = 0
""")
n_membros_ativos = kpi_membros["pessoa_id"].nunique()
membros_por_grupo = " · ".join(
    f"{g} {n}" for g, n in kpi_membros.groupby("grupo").size().items())

kpi_membros_total = query(f"""
    SELECT count(*) AS n
    FROM dim_pessoa
    WHERE eh_placeholder = 0 AND grupo IN ({grupos_in})
""")


# ---------------------------------------------------------------------------
# Cabeçalho e visão geral
# ---------------------------------------------------------------------------
st.title("📊 Painel PBL — Repositório GitLab & Quadro Kanban")
st.caption(
    "Ferramenta de apoio ao coordenador: ritmo, carga, revisão e "
    "consistência quadro × repositório.")

c1, c2, c3, c4 = st.columns(4)
c1.metric(
    "Commits de membros",
    f"{int(kpi_commits['membros'][0]):,}".replace(",", "."),
    f"de {int(kpi_commits['total'][0]):,} no filtro (inclui bots/externos)".replace(
        ",", "."),
    delta_color="off",
    delta_arrow="off",
    help="Commits de membros cadastrados nos grupos selecionados. "
         "O total inclui commits de atores não cadastrados "
         "([bot]/[externo]).")
c2.metric(
    "MRs mesclados",
    f"{int(kpi_mrs['n_merged'][0]):,}".replace(",", "."),
    f"de {int(kpi_mrs['n_total'][0]):,} MRs no filtro".replace(",", "."),
    delta_color="off",
    delta_arrow="off",
    help="Merge Requests com situação 'merged' dentro dos filtros atuais.")
c3.metric(
    "Cartões fechados",
    f"{int(kpi_cartoes['n_closed'][0]):,}".replace(",", "."),
    f"de {int(kpi_cartoes['n_total'][0]):,} cartões no filtro".replace(",", "."),
    delta_color="off",
    delta_arrow="off",
    help="Cartões Kanban com situação 'closed' dentro dos filtros atuais.")
c4.metric(
    "Membros ativos",
    str(n_membros_ativos),
    f"{membros_por_grupo}",
    delta_color="off",
    delta_arrow="off",
    help="Membros (exceto placeholders) com pelo menos um commit, MR ou "
         "cartão fechado nos filtros atuais. A quebra por grupo é por "
         "repositório, igual ao gráfico de carga de trabalho; quem atua no "
         "repositório de outro grupo conta no repositório onde atuou.")

tab_over, tab_ritmo, tab_carga, tab_review, tab_quadro = st.tabs(
    ["🏠 Visão geral", "⏱️ Ritmo & Prazos", "👥 Carga de Trabalho",
     "🔍 Code Review", "🧩 Quadro & Repositório"])

# =========================================================================
# TAB 0 — VISÃO GERAL
# =========================================================================
with tab_over:
    st.subheader("Sinais de atenção pedagógica")
    st.caption(
        "Mostra apenas exceções — vermelho = acima do limiar; amarelo = próximo "
        "(80% do limiar). Itens saudáveis entram só na contagem. "
        "Limiares configuráveis em cada tema.")

    # (key, rótulo, mín, máx, padrão) por tema; sliders são desenhados no loop
    # de temas, mas os valores são lidos do session_state antes dos cálculos.
    LIMIARES = {
        "ritmo": [
            ("lim_crunch",
             "% de commits nos 2 últimos dias da sprint (véspera)",
             5, 80, 35)],
        "carga": [
            ("lim_top1", "% de commits da pessoa mais ativa", 20, 90, 25),
            ("lim_gini", "Índice de Gini da distribuição de commits",
             0.20, 0.90, 0.35)],
        "review": [
            ("lim_review", "Mediana de horas para merge", 1, 24, 5),
            ("lim_sem_coment", "% de MRs mesclados sem comentários",
             10, 90, 40)],
        "quadro": [
            ("lim_corr", "Correlação quadro × repositório mínima",
             0.0, 1.0, 0.8)],
    }
    for specs in LIMIARES.values():
        for chave, _, _, _, padrao in specs:
            st.session_state.setdefault(chave, padrao)
    LIM_CRUNCH = st.session_state["lim_crunch"]
    LIM_TOP1 = st.session_state["lim_top1"]
    LIM_GINI = st.session_state["lim_gini"]
    LIM_REVIEW = st.session_state["lim_review"]
    LIM_SEM_COMENT = st.session_state["lim_sem_coment"]
    LIM_CORR = st.session_state["lim_corr"]

    # Alerta 1 — crunch por grupo (últimos 2 dias da sprint)
    crunch_df = query(f"""
        SELECT f.grupo, s.sprint,
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
        GROUP BY f.grupo, s.sprint
        HAVING count(*) >= 10
        ORDER BY f.grupo, s.sprint
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
          AND {sprint_cond('f.sk_sprint_commitado')}
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
          AND {sprint_cond('f.sk_sprint')}
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
            WHERE {grupos_cond}
              AND f.sk_sprint_commitado IN ({sk_in})
            GROUP BY 1, 2
        ),
        cartoes_sprint AS (
            SELECT f.grupo, f.sk_sprint, count(*) AS fechados
            FROM fato_cartoes f
            WHERE {grupos_cond} AND f.situacao = 'closed'
              AND f.sk_sprint IN ({sk_in})
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

    temas: list[dict] = []
    n_sprints_alerta = len(crunch_df)
    pal_sprint = "sprint" if n_sprints_alerta == 1 else "sprints"

    # Ritmo — exceções por sprint (renderizadas agrupadas por grupo)
    exce_ritmo: list[tuple[str, str, str]] = []
    for _, row in crunch_df.iterrows():
        pct = row["pct_fim"]
        nivel = ("bad" if pct > LIM_CRUNCH
                 else "warn" if pct > LIM_CRUNCH * 0.8 else "ok")
        if nivel != "ok":
            detalhe = ("véspera detectada" if nivel == "bad"
                       else "atenção: próximo do limiar")
            exce_ritmo.append((nivel, row["grupo"], (
                f"{row['sprint']}: {pct}% dos commits nos 2 últimos dias "
                f"({int(row['fim'])}/{int(row['total'])}) — {detalhe}")))
    temas.append({
        "marker": "⏱️ Ritmo", "limiares": "ritmo",
        "resumo": (f"{len(exce_ritmo)} de {n_sprints_alerta} {pal_sprint} "
                   "acumuladas com véspera ou próxima do limiar" if exce_ritmo
                   else f"{n_sprints_alerta} {pal_sprint} com ritmo saudável"),
        "excecoes": exce_ritmo, "agrupar": True,
        "nota": "Participação dos 2 últimos dias da sprint (véspera) no total "
                "de commits; sprints com pelo menos 10 commits, no recorte "
                "dos filtros."})

    # Carga — exceções por grupo
    exce_carga: list[tuple[str, str, str]] = []
    for _, row in conc_df.iterrows():
        if row["pct_top1"] > LIM_TOP1 or row["gini"] > LIM_GINI:
            nivel = ("bad" if row["pct_top1"] > LIM_TOP1
                     and row["gini"] > LIM_GINI else "warn")
        else:
            nivel = "ok"
        if nivel != "ok":
            exce_carga.append((nivel, row["grupo"], (
                f"top-1 = {row['pct_top1']}% dos commits "
                f"(Gini {row['gini']})")))
    n_grupos_alerta = len(conc_df)
    pal_grupo = "grupo" if n_grupos_alerta == 1 else "grupos"
    temas.append({
        "marker": "👥 Carga", "limiares": "carga",
        "resumo": (f"{len(exce_carga)} de {n_grupos_alerta} {pal_grupo} com "
                   "carga concentrada" if exce_carga
                   else f"{n_grupos_alerta} {pal_grupo} com carga equilibrada"),
        "excecoes": exce_carga,
        "nota": "Distribuição de commits por membro do grupo, no recorte dos "
                "filtros; exclui placeholders ([bot]/[externo])."})

    # Review — exceções por grupo
    exce_review: list[tuple[str, str, str]] = []
    for _, row in review_df.iterrows():
        cond_bad = (row["mediana_h"] > LIM_REVIEW
                    and row["pct_sem_coment"] > LIM_SEM_COMENT)
        cond_warn = (row["mediana_h"] > LIM_REVIEW * 0.8
                     or row["pct_sem_coment"] > LIM_SEM_COMENT * 0.8)
        nivel = "bad" if cond_bad else "warn" if cond_warn else "ok"
        if nivel != "ok":
            exce_review.append((nivel, row["grupo"], (
                f"mediana p/ merge {fmt_horas(row['mediana_h'])}; "
                f"{row['pct_sem_coment']}% sem comentários")))
    n_grupos_review = len(review_df)
    pal_grupo_review = ("grupo" if n_grupos_review == 1 else "grupos")
    temas.append({
        "marker": "🔍 Review", "limiares": "review",
        "resumo": (f"{len(exce_review)} de {n_grupos_review} "
                   f"{pal_grupo_review} em atenção na revisão" if exce_review
                   else f"{n_grupos_review} {pal_grupo_review} com revisão "
                        "saudável"),
        "excecoes": exce_review,
        "nota": "Sobre MRs mesclados: mediana de horas da abertura ao merge e "
                "% de MRs sem nenhum comentário, no recorte dos filtros."})

    # Quadro × Repo — correlação global
    if corr is not None:
        nivel = ("bad" if abs(corr) < LIM_CORR * 0.5
                 else "warn" if abs(corr) < LIM_CORR else "ok")
        saudavel = nivel == "ok"
        temas.append({
            "marker": "🧩 Quadro × Repo", "limiares": "quadro",
            "resumo": (f"correlação commits × cartões fechados = {corr} — "
                       + ("quadro reflete o repositório" if saudavel
                          else "divergência quadro/repositório")),
            "excecoes": ([] if saudavel else [(nivel, "", (
                "divergência quadro/repositório — investigar cartões "
                "empilhados ou commits sem rastreio"))]),
            "nota": "Correlação de Pearson entre commits e cartões fechados "
                    "por sprint, apenas nas sprints selecionadas; exige "
                    "pelo menos 3 sprints no recorte."})
    else:
        temas.append({
            "marker": "🧩 Quadro × Repo", "limiares": "quadro",
            "icon": "⚪",
            "resumo": "sem dados suficientes para correlacionar",
            "excecoes": [],
            "nota": "Correlação de Pearson entre commits e cartões fechados "
                    "por sprint, apenas nas sprints selecionadas; exige "
                    "pelo menos 3 sprints no recorte."})

    ICONES = {"bad": "🔴", "warn": "🟡", "ok": "🟢"}
    separar_grupos = len(grupos_sel) > 1
    for i, tema in enumerate(temas):
        exce = tema["excecoes"]
        icon = (tema.get("icon")
                or (ICONES["bad"] if any(n == "bad" for n, _, _ in exce)
                    else ICONES["warn"] if exce else ICONES["ok"]))
        if i > 0:
            st.divider()
        st.markdown(f"#### {tema['marker']}")
        with st.expander("⚙️ Limiares de alerta", expanded=False):
            for chave, rotulo, vmin, vmax, _ in LIMIARES[tema["limiares"]]:
                st.slider(rotulo, vmin, vmax, key=chave)
        st.markdown(f"#### {icon} {tema['resumo']}")
        if tema.get("nota"):
            st.caption(tema["nota"])
        ultimo_grupo = None
        for nivel, grupo, msg in exce:
            cor = "red" if nivel == "bad" else "orange"
            if tema.get("agrupar") and separar_grupos:
                if grupo != ultimo_grupo:
                    st.markdown(f"&nbsp;&nbsp;**{grupo}**")
                    ultimo_grupo = grupo
                st.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;{ICONES[nivel]} "
                            f":{cor}[{msg}]", unsafe_allow_html=True)
            elif tema.get("agrupar"):
                st.markdown(f"&nbsp;&nbsp;{ICONES[nivel]} "
                            f":{cor}[{grupo} · {msg}]",
                            unsafe_allow_html=True)
            else:
                texto = f"{grupo}: {msg}" if grupo else msg
                st.markdown(f"&nbsp;&nbsp;{ICONES[nivel]} :{cor}[{texto}]",
                            unsafe_allow_html=True)

    st.subheader("Resumo por grupo")
    resumo_df = query(f"""
        WITH ev AS (
            SELECT k.grupo, k.sk_sprint_evento AS sk_sprint, count(*) AS n
            FROM fato_kanban_eventos k
            GROUP BY 1, 2
        ),
        ev_filtro AS (
            SELECT grupo, sum(n) AS eventos
            FROM ev
            WHERE sk_sprint IN ({sk_in})
                  {"OR sk_sprint IS NULL" if sem_sprint else ""}
            GROUP BY 1
        )
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
               coalesce(ev.eventos, 0) AS eventos_quadro
        FROM dim_grupo g
        LEFT JOIN ev_filtro ev ON ev.grupo = g.grupo
        WHERE g.grupo IN ({grupos_in})
        ORDER BY g.grupo
    """)
    st.dataframe(
        resumo_df.rename(columns={
            "grupo": "Grupo", "commits": "Commits", "mrs": "MRs",
            "mrs_merged": "MRs mesclados",
            "cartoes_fechados": "Cartões fechados",
            "eventos_quadro": "Eventos no quadro"}),
        use_container_width=True, hide_index=True)

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
    serie["pct"] = (100 * serie["commits"]
                    / serie.groupby("grupo")["commits"].transform("sum"))
    fig = px.line(serie, x="dia", y="pct", color="grupo",
                  custom_data=["commits"],
                  color_discrete_map=CORES_GRUPO,
                  title="Commits por dia (% do total de commits do grupo)",
                  labels={"dia": "Data", "pct": "% dos commits do grupo",
                          "grupo": "Grupo"})
    fig.update_traces(hovertemplate=(
        "%{x|%Y-%m-%d}<br>%{y:.1f}% (%{customdata[0]} commits)"
        "<extra>%{fullData.name}</extra>"))
    fig.update_yaxes(ticksuffix="%", rangemode="tozero")
    # add_shape/add_annotation evitam o bug de add_vline com eixo de datas
    for _, s in sprints_df[sprints_df["label"].isin(sprints_sel)].iterrows():
        x = s["prazo_em"].strftime("%Y-%m-%d")
        fig.add_shape(type="line", x0=x, x1=x, y0=0, y1=1, yref="paper",
                      line=dict(color="gray", dash="dash", width=1))
        fig.add_annotation(x=x, y=1, yref="paper", text=s["sprint"],
                           showarrow=False, yanchor="bottom",
                           font=dict(color="gray", size=10))
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
            "Início/meio": COR_COMMITS, "Véspera (2 dias)": COLOR_BAD},
        title="% de commits por janela dentro da sprint",
        labels={"pct": "% dos commits", "sprint": "", "janela": "Janela"})
    fig.for_each_yaxis(lambda ax: ax.update(title_text="% dos commits"))
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("**Tabela de distribuição de commits por janela**")
    tabela = dist_df.rename(columns={
        "grupo": "Grupo", "sprint": "Sprint", "total": "Commits",
        "fim": "Véspera", "inicio_meio": "Início/meio",
        "pct_fim": "% véspera", "pct_inicio_meio": "% início/meio"})
    st.dataframe(
        tabela[["Grupo", "Sprint", "Commits", "% início/meio",
                "% véspera"]],
        use_container_width=True, hide_index=True)

    acima = dist_df[dist_df["pct_fim"] > LIM_CRUNCH]
    if acima.empty:
        st.success("Nenhum sprint acima do limiar de véspera.")
    else:
        for _, r in acima.iterrows():
            st.error(
                f"**{r['grupo']} · {r['sprint']}** — {r['pct_fim']}% "
                f"dos commits ({int(r['fim'])}/{int(r['total'])}) nos "
                f"2 últimos dias. Limiar: {LIM_CRUNCH}%.")
    st.caption(
        f"Limiar de véspera em uso: {LIM_CRUNCH}%. Ajuste em "
        "🏠 Visão geral → ⏱️ Ritmo → Limiares de alerta.")

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
    foco = carga_total[carga_total["grupo"] == grupo_foco].head(15).copy()
    grupo_de = query("SELECT pessoa_id, grupo FROM dim_pessoa").set_index(
        "pessoa_id")["grupo"]
    foco["origem"] = foco["pessoa"].map(grupo_de)
    visitante = foco["origem"].notna() & (foco["origem"] != grupo_foco)
    foco["rotulo"] = foco["pessoa"].where(
        ~visitante, foco["pessoa"] + " (de " + foco["origem"].fillna("") + ")")
    fig = go.Figure()
    fig.add_bar(name="Commits", x=foco["rotulo"], y=foco["commits"],
                marker_color=COR_COMMITS)
    fig.add_bar(name="MRs", x=foco["rotulo"], y=foco["mrs"],
                marker_color=COR_MRS)
    fig.add_bar(name="Cartões fechados", x=foco["rotulo"],
                y=foco["cartoes_fechados"], marker_color=COR_CARTOES)
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
    incluir_ph_review = st.toggle(
        "Incluir placeholders ([bot]/[externo])", value=False, key="ph_review",
        help="Desligado: exclui MRs cujo autor ou quem mesclou é placeholder, "
             "e commits de merge de placeholders.")
    ph_mr = ("0 = 0" if incluir_ph_review else
             "coalesce(p.eh_placeholder, 0) = 0 "
             "AND coalesce(pm.eh_placeholder, 0) = 0")
    ph_commit = ("0 = 0" if incluir_ph_review else
                 "coalesce(pa.eh_placeholder, 0) = 0")

    merged = query(f"""
        SELECT f.*, p.pessoa_id AS autor, pm.pessoa_id AS merged_por
        FROM fato_merge_requests f
        LEFT JOIN dim_pessoa p ON p.sk_pessoa = f.sk_autor
        LEFT JOIN dim_pessoa pm ON pm.sk_pessoa = f.sk_merged_por
        WHERE {grupos_cond} AND f.situacao = 'merged' AND ({ph_mr})
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

        ordem_grupos = sorted(merged["grupo"].unique())
        s1, _ = st.columns(2)
        PERC_EIXO = s1.slider(
            "Percentil máximo do eixo nos box plots", 90, 100, 95,
            help="Corta só a visualização: MRs acima do percentil global "
                 "ficam fora do eixo. KPIs, medianas e alertas usam "
                 "todos os MRs.")
        c1, c2 = st.columns(2)
        with c1:
            limite = float(merged["horas_para_merge"].quantile(PERC_EIXO / 100))
            fig = px.box(
                merged, x="horas_para_merge", y="grupo", color="grupo",
                points="outliers",
                title="Tempo até o merge por grupo (horas)",
                labels={"horas_para_merge": "Horas", "grupo": "Grupo"},
                color_discrete_map=CORES_GRUPO,
                category_orders={"grupo": ordem_grupos})
            fig.update_traces(boxmean=True)
            fig.update_xaxes(range=[0, limite * 1.05])
            fig.update_layout(showlegend=False)
            st.plotly_chart(fig, use_container_width=True)
            fora = int((merged["horas_para_merge"] > limite).sum())
            st.caption(
                f"Eixo até o percentil {PERC_EIXO} global ({limite:.1f} h); "
                f"{fora} de {len(merged)} MRs ficam fora do eixo. "
                "Linha tracejada = média.")
        with c2:
            faixas = ["0", "1", "2", "3", "4", "5+"]
            dist = merged.assign(
                faixa=merged["comentarios"].map(
                    lambda n: "5+" if n >= 5 else str(int(n))))
            dist = (dist.groupby(["grupo", "faixa"]).size()
                    .rename("mrs").reset_index())
            dist["pct"] = (100 * dist["mrs"]
                           / dist.groupby("grupo")["mrs"].transform("sum"))
            fig = px.bar(
                dist, x="faixa", y="pct", color="grupo", barmode="group",
                custom_data=["mrs"],
                title="Comentários por MR (mesclados)",
                labels={"faixa": "Comentários", "pct": "% dos MRs do grupo",
                        "grupo": "Grupo"},
                color_discrete_map=CORES_GRUPO,
                category_orders={"faixa": faixas, "grupo": ordem_grupos})
            fig.update_traces(
                hovertemplate="%{y:.1f}% (%{customdata[0]} MRs)")
            # Sem isso o Plotly infere eixo numérico ("0".."4") e descarta "5+".
            fig.update_xaxes(type="category")
            st.plotly_chart(fig, use_container_width=True)

        c3, c4 = st.columns(2)
        with c3:
            aprov = (merged.groupby(["merged_por", "grupo"]).size()
                     .rename("MRs mesclados").reset_index()
                     .rename(columns={"merged_por": "Quem mesclou",
                                      "grupo": "Grupo"}))
            top10 = (aprov.groupby("Quem mesclou")["MRs mesclados"].sum()
                     .nlargest(10).index)
            aprov = aprov[aprov["Quem mesclou"].isin(top10)]
            fig = px.bar(aprov, y="Quem mesclou", x="MRs mesclados",
                         color="Grupo", orientation="h",
                         color_discrete_map=CORES_GRUPO,
                         category_orders={"Grupo": sorted(grupos_sel)},
                         title="Top aprovadores (merged_por)")
            fig.update_layout(yaxis={"categoryorder": "total ascending"})
            st.plotly_chart(fig, use_container_width=True)
        with c4:
            tamanho = query(f"""
                SELECT f.grupo,
                       coalesce(s.sprint, '(sem sprint)') AS sprint,
                       sum(f.linhas_total) AS linhas_merge,
                       count(*) AS merge_commits
                FROM fato_commits f
                LEFT JOIN dim_sprint s ON s.sk_sprint = f.sk_sprint_commitado
                LEFT JOIN dim_pessoa pa ON pa.sk_pessoa = f.sk_autor
                WHERE {grupos_cond} AND f.e_merge = 1 AND {ph_commit}
                  AND {sprint_cond('f.sk_sprint_commitado')}
                GROUP BY 1, 2
            """)
            ordem_sprints = sprints_df["sprint"].drop_duplicates().tolist()
            cores_sprint = dict(zip(
                ordem_sprints, px.colors.qualitative.Set2))
            cores_sprint["(sem sprint)"] = "#bdbdbd"
            fig = px.bar(
                tamanho, x="grupo", y="linhas_merge", color="sprint",
                custom_data=["merge_commits"], text="linhas_merge",
                title="Tamanho das integrações por sprint "
                      "(linhas em commits de merge)",
                labels={"linhas_merge": "Linhas em commits de merge",
                        "grupo": "Grupo", "sprint": "Sprint"},
                color_discrete_map=cores_sprint,
                category_orders={"sprint": ordem_sprints + ["(sem sprint)"],
                                 "grupo": sorted(grupos_sel)})
            fig.update_traces(
                texttemplate="%{text:,.0f}", textposition="inside",
                hovertemplate="%{y:,.0f} linhas (%{customdata[0]} merges)")
            fig.update_layout(barmode="stack",
                              uniformtext=dict(minsize=9, mode="hide"))
            totais = tamanho.groupby("grupo", as_index=False)[
                "linhas_merge"].sum()
            fig.add_scatter(
                x=totais["grupo"], y=totais["linhas_merge"], mode="text",
                text=totais["linhas_merge"].map("{:,.0f}".format),
                textposition="top center", showlegend=False,
                hoverinfo="skip", cliponaxis=False)
            fig.update_yaxes(range=[0, totais["linhas_merge"].max() * 1.1])
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
            WHERE {grupos_cond}
              AND f.sk_sprint_commitado IN ({sk_in})
            GROUP BY 1, 2, 3
        ),
        cartoes_sprint AS (
            SELECT f.grupo, s.sprint, f.sk_sprint,
                   count(*) AS cartoes_criados,
                   count(*) FILTER (WHERE f.situacao='closed') AS cartoes_fechados,
                   coalesce(sum(f.tempo_gasto_s), 0) / 3600.0 AS horas_gastas
            FROM fato_cartoes f
            LEFT JOIN dim_sprint s ON s.sk_sprint = f.sk_sprint
            WHERE {grupos_cond}
              AND f.sk_sprint IN ({sk_in})
            GROUP BY 1, 2, 3
        )
        SELECT coalesce(c.grupo, k.grupo) AS grupo,
               coalesce(c.sprint, k.sprint) AS sprint,
               coalesce(c.commits, 0) AS commits,
               coalesce(c.dev_ativos, 0) AS dev_ativos,
               coalesce(k.cartoes_criados, 0) AS cartoes_criados,
               coalesce(k.cartoes_fechados, 0) AS cartoes_fechados,
               coalesce(k.horas_gastas, 0) AS horas_gastas
        FROM commits_sprint c
        FULL OUTER JOIN cartoes_sprint k
          ON k.grupo = c.grupo AND k.sk_sprint = c.sk_sprint
        ORDER BY 1, 2
    """)

    if qxr.empty:
        st.info("Sem dados no filtro atual.")
    else:
        fig = go.Figure()
        fig.add_bar(name="Cartões fechados", x=qxr["grupo"] + " · " + qxr["sprint"],
                    y=qxr["cartoes_fechados"], marker_color=COR_CARTOES)
        fig.add_bar(name="Commits", x=qxr["grupo"] + " · " + qxr["sprint"],
                    y=qxr["commits"], marker_color=COR_COMMITS)
        fig.update_layout(
            barmode="group",
            title="Cartões fechados × commits por sprint",
            yaxis_title="Quantidade")
        fig.update_xaxes(tickangle=-45)
        grupos_ord = qxr["grupo"].reset_index(drop=True)
        for i in grupos_ord.index[grupos_ord != grupos_ord.shift()][1:]:
            fig.add_vline(x=i - 0.5, line_dash="dash", line_color="#9e9e9e")
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
        else:
            st.info("Menos de 3 sprints no recorte — correlação não calculada.")
        st.caption(
            f"Correlação mínima em uso: {LIM_CORR}. Ajuste em "
            "🏠 Visão geral → 🧩 Quadro × Repo → Limiares de alerta.")

        st.caption(
            "Como ler: sprints com muitos commits e poucos cartões fechados "
            "indicam trabalho técnico fora do quadro; o contrário indica "
            "plano sem execução versionada.")

    # ---------------------------------------------------------------------
    # Concentração por tipo de trabalho
    # ---------------------------------------------------------------------
    st.markdown("---")
    st.subheader("Alguém está concentrado em um tipo de tarefa?")
    s1, s2 = st.columns(2)
    LIM_CONC = s1.slider(
        "% dos cartões da pessoa em um único tipo de trabalho",
        40, 100, 52)
    MIN_CART_CONC = s2.slider(
        "Mínimo de cartões por pessoa para avaliar concentração",
        3, 30, 9)

    tipo_por_rotulo = {
        "DOCUMENTATION": "Documentação", "CODE": "Código",
        "DESIGN": "Design", "BUG": "Bug/Fix", "FIX": "Bug/Fix",
        "NEGÓCIOS": "Negócios", "USER-STORY": "User story",
        "PRESENTATION": "Apresentação", "CODE_REVIEW": "Code review",
        "REQUIREMENTS": "Requisitos", "TEST": "Teste", "DEPLOY": "Deploy"}

    cart = query(f"""
        SELECT f.grupo, f.cartao_numero, f.responsaveis_ids, f.rotulos
        FROM fato_cartoes f
        WHERE {grupos_cond} AND {sprint_cond('f.sk_sprint')}
          AND f.responsaveis_ids <> '' AND f.rotulos <> ''
    """)
    cart["pessoa"] = cart["responsaveis_ids"].str.split(";")
    cart["tipo"] = cart["rotulos"].str.split(";").map(
        lambda rs: sorted({tipo_por_rotulo[r.strip().upper()] for r in rs
                           if r.strip().upper() in tipo_por_rotulo}))
    conc = (cart.explode("pessoa").explode("tipo")
            .dropna(subset=["pessoa", "tipo"]))
    conc = conc[~conc["pessoa"].str.startswith("[")]

    base = (conc.groupby(["grupo", "pessoa"])["cartao_numero"].nunique()
            .rename("n_cartoes"))
    base = base[base >= MIN_CART_CONC]
    pct = (conc.groupby(["grupo", "pessoa", "tipo"])["cartao_numero"].nunique()
           .unstack("tipo", fill_value=0))
    pct = pct.loc[pct.index.isin(base.index)]

    if pct.empty:
        st.info(
            f"Nenhuma pessoa com pelo menos {MIN_CART_CONC} cartões "
            "com responsável e tipo de trabalho no filtro atual.")
    else:
        pct = pct.div(base.loc[pct.index], axis=0) * 100
        pct["top_pct"] = pct.max(axis=1)
        pct["top_tipo"] = pct.drop(columns="top_pct").idxmax(axis=1)
        pct = pct.join(base).reset_index()
        pct["concentrado"] = pct["top_pct"] > LIM_CONC
        pct = pct.sort_values(
            ["grupo", "top_pct"], ascending=[True, False])
        tipos_cols = [t for t in sorted(set(tipo_por_rotulo.values()))
                      if t in pct.columns]
        pct["linha"] = (
            pct["grupo"] + " · " + pct["pessoa"]
            + " (" + pct["n_cartoes"].astype(str) + ")"
            + pct["concentrado"].map({True: " ⚠", False: ""}))

        z = pct[tipos_cols].round(0)
        fig = go.Figure(go.Heatmap(
            z=z.to_numpy(), x=tipos_cols, y=pct["linha"],
            zmin=0, zmax=100, colorscale="Blues",
            text=z.astype(int).astype(str).to_numpy() + "%",
            texttemplate="%{text}",
            hovertemplate="%{y}<br>%{x}: %{z:.0f}% dos cartões<extra></extra>",
            colorbar=dict(title="% dos cartões")))
        fig.update_layout(
            title="% dos cartões de cada pessoa por tipo de trabalho "
                  "(entre parênteses: nº de cartões · ⚠ = acima do limiar)",
            height=max(320, 26 * len(pct) + 160))
        fig.update_yaxes(autorange="reversed")
        fig.update_xaxes(side="top")
        fig.update_layout(margin=dict(t=150), title_y=0.98)
        st.plotly_chart(fig, use_container_width=True)

        for grupo_nome, sub in pct.groupby("grupo"):
            acima = sub[sub["concentrado"]]
            if acima.empty:
                st.success(
                    f"**{grupo_nome}** — ninguém acima de {LIM_CONC}% em um "
                    f"único tipo ({len(sub)} pessoas avaliadas).")
            else:
                lista = "; ".join(
                    f"{r.pessoa} ({r.top_pct:.0f}% {r.top_tipo}, "
                    f"{r.n_cartoes} cartões)" for r in acima.itertuples())
                st.warning(
                    f"**{grupo_nome}** — {len(acima)} de {len(sub)} pessoas "
                    f"concentradas em um tipo: {lista}.")
        st.caption(
            "Considera todos os cartões atribuídos à pessoa (responsável "
            "atual) que têm rótulo de tipo; rótulos de artefato (ART.*), "
            "tamanho e coluna ficam de fora. Cartão com mais de um tipo conta "
            "em cada um, então a linha pode somar mais de 100%.")

    # ---------------------------------------------------------------------
    # Arrasto em lote no quadro
    # ---------------------------------------------------------------------
    st.markdown("---")
    st.subheader("Os cartões são arrastados em lote?")
    lote_gap_min, lote_min_cartoes = 10, 3

    mov = query(f"""
        SELECT f.grupo, p.pessoa_id AS pessoa, f.cartao_numero,
               f.ocorrido_em, f.sk_sprint_evento, s.sprint
        FROM fato_kanban_eventos f
        JOIN dim_pessoa p ON p.sk_pessoa = f.sk_pessoa
        LEFT JOIN dim_sprint s ON s.sk_sprint = f.sk_sprint_evento
        WHERE {grupos_cond} AND f.tipo_evento = 'coluna' AND f.acao = 'add'
          AND p.eh_placeholder = 0
        ORDER BY f.grupo, p.pessoa_id, f.ocorrido_em
    """)
    chave = [mov["grupo"], mov["pessoa"]]
    gap = mov.groupby(["grupo", "pessoa"])["ocorrido_em"].diff()
    novo_lote = gap.isna() | (gap > pd.Timedelta(minutes=lote_gap_min))
    mov["lote"] = novo_lote.groupby(chave).cumsum()
    mov["cartoes_no_lote"] = mov.groupby(["grupo", "pessoa", "lote"])[
        "cartao_numero"].transform("nunique")
    mov["em_lote"] = mov["cartoes_no_lote"] >= lote_min_cartoes

    no_filtro = mov["sk_sprint_evento"].isin(sk_sel)
    if sem_sprint:
        no_filtro |= mov["sk_sprint_evento"].isna()
    mov = mov[no_filtro].copy()
    mov["sprint"] = mov["sprint"].fillna("(fora)")

    if mov.empty:
        st.info("Sem movimentos de coluna no filtro atual.")
    else:
        cols = st.columns(max(1, mov["grupo"].nunique()))
        ajuda_lote = (
            f"Lote = mesma pessoa movendo {lote_min_cartoes} ou mais cartões "
            f"diferentes entre colunas com intervalo de até {lote_gap_min} min "
            "entre movimentos consecutivos. Considera só movimentos (add) em "
            "colunas do quadro, sem [bot]/[externo]; os lotes são calculados "
            "sobre todo o histórico, e o filtro de sprint só recorta o que é "
            "exibido.")
        for col, (grupo_nome, sub) in zip(cols, mov.groupby("grupo")):
            lotes = sub[sub["em_lote"]].drop_duplicates(
                ["pessoa", "lote"])
            col.metric(
                f"{grupo_nome} — movimentos em lote",
                f"{100 * sub['em_lote'].mean():.0f}%",
                f"{len(lotes)} lotes · maior com "
                f"{int(sub['cartoes_no_lote'].max())} cartões",
                delta_color="off", delta_arrow="off", help=ajuda_lote)

        por_sprint = (mov.groupby(["grupo", "sprint"])
                      .agg(movimentos=("em_lote", "size"),
                           em_lote=("em_lote", "sum")).reset_index())
        por_sprint["pct"] = 100 * por_sprint["em_lote"] / por_sprint["movimentos"]
        ordem = sprints_df["sprint"].drop_duplicates().tolist() + ["(fora)"]
        fig = px.bar(
            por_sprint, x="sprint", y="pct", color="grupo", barmode="group",
            custom_data=["em_lote", "movimentos"],
            title="% dos movimentos de coluna feitos em lote, por sprint",
            labels={"sprint": "Sprint", "pct": "% dos movimentos em lote",
                    "grupo": "Grupo"},
            color_discrete_map=CORES_GRUPO,
            category_orders={"sprint": ordem, "grupo": sorted(grupos_sel)})
        fig.update_traces(
            hovertemplate="%{y:.0f}% (%{customdata[0]} de "
                          "%{customdata[1]} movimentos)")
        fig.update_xaxes(type="category")
        fig.update_yaxes(range=[0, 100])
        st.plotly_chart(fig, use_container_width=True)
