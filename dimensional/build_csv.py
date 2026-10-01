"""Gera os CSVs do modelo estrela em dimensional/csv a partir dos dados brutos de dados/.

Modelo (item 8 de modelagem/modelagem_logica.md):
- chaves substitutas sk_* inteiras, atribuídas em ordem de chave natural;
  sk = -1 representa N/A e cada dimensão tem a linha correspondente;
- dim_sprint e dim_quadro_coluna são dimensões conformadas (sem atributo de
  grupo): as linhas repetidas entre grupos são deduplicadas. Em dim_sprint, a
  variante com inicio_em/prazo_em preenchidos prevalece — as janelas de data
  do ciclo (fonte G03, único grupo com datas) valem para todos os grupos;
  o grupo segue identificável nas fatos pelas dimensões degeneradas;
- multivalorados permanecem como listas separadas por ';';
- fato_kanban_eventos deduplica eventos repetidos (chave grupo + cartao_numero
  + ocorrido_em + acao + coluna, mantendo a primeira linha).

Saída: UTF-8 com BOM, separador ',', todos os campos entre aspas, fim de
linha CRLF. Para regenerar: python dimensional/build_csv.py
"""
from __future__ import annotations

import csv
import os
import shutil
import tempfile
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "dados"
OUT = ROOT / "dimensional" / "csv"
TMP = Path(tempfile.mkdtemp(prefix="dimensional_csv_", dir=OUT.parent))

MESES = ["Janeiro", "Fevereiro", "Marco", "Abril", "Maio", "Junho",
         "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
DIAS_SEMANA = ["Domingo", "Segunda-feira", "Terca-feira", "Quarta-feira",
               "Quinta-feira", "Sexta-feira", "Sabado"]


def read_raw(name: str) -> list[dict[str, str]]:
    with open(SRC / f"{name}.csv", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))
    header = rows[0]
    return [dict(zip(header, r)) for r in rows[1:]]


def sk_data(ts: str) -> str:
    """sk_data (AAAAMMDD) a partir da parte de data do timestamp original."""
    return ts[:10].replace("-", "") if ts else "-1"


def write_csv(name: str, header: list[str], rows: list[list[str]]) -> None:
    with open(TMP / f"{name}.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, quoting=csv.QUOTE_ALL, lineterminator="\r\n")
        w.writerow(header)
        w.writerows(rows)


# ---------------------------------------------------------------------------
# dim_grupo
# ---------------------------------------------------------------------------
grupos = sorted(read_raw("grupos"), key=lambda r: r["grupo"])
if len({r["grupo"] for r in grupos}) != len(grupos):
    raise ValueError("grupos.csv contém chave 'grupo' duplicada")
grupo_sk = {r["grupo"]: str(i) for i, r in enumerate(grupos, start=1)}
dim_grupo_rows = [[str(i), r["grupo"], r["branch_padrao"],
                   r["criado_em"], r["ultima_atividade_em"]]
                  for i, r in enumerate(grupos, start=1)]
dim_grupo_rows.append(["-1", "(N/A)", "", "", ""])
grupo_sk["(N/A)"] = "-1"

# ---------------------------------------------------------------------------
# dim_pessoa (inclui os placeholders [bot] e [externo])
# ---------------------------------------------------------------------------
pessoas = sorted(read_raw("pessoas"), key=lambda r: r["pessoa_id"])
if len({r["pessoa_id"] for r in pessoas}) != len(pessoas):
    raise ValueError("pessoas.csv contém chave 'pessoa_id' duplicada")
pessoa_sk = {r["pessoa_id"]: str(i) for i, r in enumerate(pessoas, start=1)}
dim_pessoa_rows = [[str(i), r["pessoa_id"], r["grupo"], grupo_sk[r["grupo"]],
                    r["papel"], r["situacao"], "0"]
                   for i, r in enumerate(pessoas, start=1)]
for sk, pid in ((len(pessoas) + 1, "[bot]"), (len(pessoas) + 2, "[externo]")):
    dim_pessoa_rows.append([str(sk), pid, "(N/A)", "-1", "placeholder", "", "1"])
    pessoa_sk[pid] = str(sk)

# ---------------------------------------------------------------------------
# dim_sprint — conformada: 1 linha por sprint do ciclo, sem grupo
# ---------------------------------------------------------------------------
por_sprint: dict[str, dict[str, str]] = {}
for r in read_raw("sprints"):
    atual = por_sprint.get(r["sprint"])
    if atual is None or (r["inicio_em"] and not atual["inicio_em"]):
        por_sprint[r["sprint"]] = r
sprints = sorted(por_sprint.values(), key=lambda r: r["sprint"])
sprint_sk = {r["sprint"]: str(i) for i, r in enumerate(sprints, start=1)}
dim_sprint_rows = [[sprint_sk[r["sprint"]], r["sprint"], r["situacao"],
                    r["inicio_em"], sk_data(r["inicio_em"]),
                    r["prazo_em"], sk_data(r["prazo_em"])]
                   for r in sprints]
dim_sprint_rows.append(["-1", "(sem sprint)", "", "", "-1", "", "-1"])
sprint_sk["(sem sprint)"] = "-1"

# ---------------------------------------------------------------------------
# dim_quadro_coluna — conformada: 1 linha por coluna do quadro, sem grupo
# ---------------------------------------------------------------------------
vistos: dict[tuple[str, str, str], dict[str, str]] = {}
for r in read_raw("quadro_colunas"):
    vistos.setdefault((r["quadro"], r["posicao"], r["coluna"]), r)
quadro = sorted(vistos.values(),
                key=lambda r: (r["quadro"], int(r["posicao"]), r["coluna"]))
colunas_distintas = {r["coluna"] for r in quadro}
if len(colunas_distintas) != len(quadro):
    raise ValueError("nome de coluna do quadro repetido em posições distintas — "
                     "o mapeamento por coluna precisa de revisão")
coluna_sk = {r["coluna"]: str(i) for i, r in enumerate(quadro, start=1)}
dim_quadro_coluna_rows = [[str(i), r["quadro"], r["posicao"], r["coluna"]]
                          for i, r in enumerate(quadro, start=1)]
dim_quadro_coluna_rows.append(["-1", "(n/a)", "-1", "(n/a)"])
coluna_sk["(n/a)"] = "-1"

# ---------------------------------------------------------------------------
# dim_data — calendário 2022-01-01 a 2026-12-31
# ---------------------------------------------------------------------------
dim_data_rows = []
dia = date(2022, 1, 1)
while dia <= date(2026, 12, 31):
    num = (dia.weekday() + 1) % 7  # domingo = 0 ... sábado = 6
    dim_data_rows.append([dia.strftime("%Y%m%d"), dia.isoformat(),
                          str(dia.year), str((dia.month - 1) // 3 + 1),
                          str(dia.month), MESES[dia.month - 1], str(dia.day),
                          str(num), DIAS_SEMANA[num],
                          "1" if num in (0, 6) else "0"])
    dia += timedelta(days=1)
dim_data_rows.append(["-1", "(sem data)", "-1", "-1", "-1", "", "-1", "-1", "", "-1"])

# ---------------------------------------------------------------------------
# fato_commits
# ---------------------------------------------------------------------------
commits = sorted(read_raw("commits"), key=lambda r: (r["grupo"], r["commit_id"]))
fato_commits_rows = [
    [grupo_sk[r["grupo"]], pessoa_sk[r["autor_id"]],
     sk_data(r["autorado_em"]), r["autorado_em"],
     sk_data(r["commitado_em"]), r["commitado_em"],
     r["e_merge"], r["linhas_adicionadas"], r["linhas_removidas"],
     r["linhas_total"], r["grupo"], r["commit_id"], r["titulo"].strip(),
     r["mensagem"]]
    for r in commits]

# ---------------------------------------------------------------------------
# fato_merge_requests
# ---------------------------------------------------------------------------
mrs = sorted(read_raw("merge_requests"),
             key=lambda r: (r["grupo"], int(r["mr_numero"])))
fato_mr_rows = [
    [grupo_sk[r["grupo"]], pessoa_sk[r["autor_id"]],
     pessoa_sk[r["merged_por_id"]] if r["merged_por_id"] else "-1",
     sprint_sk[r["sprint"]] if r["sprint"] else "-1",
     sk_data(r["criado_em"]), r["criado_em"],
     sk_data(r["atualizado_em"]), r["atualizado_em"],
     sk_data(r["merged_em"]), r["merged_em"],
     sk_data(r["fechado_em"]), r["fechado_em"],
     r["mr_numero"], r["titulo"], r["descricao"], r["situacao"],
     r["e_rascunho"], r["comentarios"], r["branch_origem"], r["branch_destino"],
     r["revisores_ids"], r["responsaveis_ids"], r["rotulos"], r["grupo"]]
    for r in mrs]

# ---------------------------------------------------------------------------
# fato_cartoes
# ---------------------------------------------------------------------------
cartoes = sorted(read_raw("cartoes"),
                 key=lambda r: (r["grupo"], int(r["cartao_numero"])))
fato_cartoes_rows = [
    [grupo_sk[r["grupo"]], pessoa_sk[r["autor_id"]],
     pessoa_sk[r["fechado_por_id"]] if r["fechado_por_id"] else "-1",
     sprint_sk[r["sprint"]] if r["sprint"] else "-1",
     sk_data(r["criado_em"]), r["criado_em"],
     sk_data(r["atualizado_em"]), r["atualizado_em"],
     sk_data(r["fechado_em"]), r["fechado_em"],
     sk_data(r["prazo_em"]), r["prazo_em"],
     r["cartao_numero"], r["titulo"], r["descricao"], r["situacao"],
     r["peso"], r["comentarios"], r["tempo_estimado_s"], r["tempo_gasto_s"],
     r["responsaveis_ids"], r["rotulos"], r["grupo"]]
    for r in cartoes]

# ---------------------------------------------------------------------------
# fato_kanban_eventos (dedupe dos eventos repetidos; ordem estável —
# empates de timestamp preservam a ordem do extrato)
# ---------------------------------------------------------------------------
eventos: dict[tuple[str, str, str, str, str], dict[str, str]] = {}
for r in read_raw("kanban_eventos"):
    eventos.setdefault((r["grupo"], r["cartao_numero"], r["ocorrido_em"],
                        r["acao"], r["coluna"]), r)
dedup = sorted(eventos.values(),
               key=lambda r: (r["grupo"], int(r["cartao_numero"]),
                              r["ocorrido_em"], r["acao"],
                              r["coluna"].casefold()))
fato_eventos_rows = []
for i, r in enumerate(dedup, start=1):
    col = r["coluna"]
    sk_col = coluna_sk.get(col, "-1") if col else "-1"
    tipo = ("vazio" if not col
            else "coluna" if sk_col != "-1" else "rotulo")
    fato_eventos_rows.append(
        [str(i), grupo_sk[r["grupo"]], pessoa_sk[r["pessoa_id"]], sk_col,
         sk_data(r["ocorrido_em"]), r["ocorrido_em"], r["grupo"],
         r["cartao_numero"], r["acao"], tipo, col])

# ---------------------------------------------------------------------------
# Escrita (em diretório temporário; publicação atômica ao final)
# ---------------------------------------------------------------------------
write_csv("dim_grupo",
          ["sk_grupo", "grupo", "branch_padrao", "criado_em",
           "ultima_atividade_em"], dim_grupo_rows)
write_csv("dim_pessoa",
          ["sk_pessoa", "pessoa_id", "grupo", "sk_grupo", "papel",
           "situacao", "eh_placeholder"], dim_pessoa_rows)
write_csv("dim_sprint",
          ["sk_sprint", "sprint", "situacao", "inicio_em", "sk_data_inicio",
           "prazo_em", "sk_data_prazo"], dim_sprint_rows)
write_csv("dim_quadro_coluna",
          ["sk_quadro_coluna", "quadro", "posicao", "coluna"],
          dim_quadro_coluna_rows)
write_csv("dim_data",
          ["sk_data", "data", "ano", "trimestre", "mes", "nome_mes", "dia",
           "dia_semana_num", "nome_dia_semana", "eh_fim_de_semana"],
          dim_data_rows)
write_csv("fato_commits",
          ["sk_grupo", "sk_autor", "sk_data_autorado", "autorado_em",
           "sk_data_commitado", "commitado_em", "e_merge",
           "linhas_adicionadas", "linhas_removidas", "linhas_total",
           "grupo", "commit_id", "titulo", "mensagem"], fato_commits_rows)
write_csv("fato_merge_requests",
          ["sk_grupo", "sk_autor", "sk_merged_por", "sk_sprint",
           "sk_data_criacao", "criado_em", "sk_data_atualizacao",
           "atualizado_em", "sk_data_merged", "merged_em",
           "sk_data_fechamento", "fechado_em", "mr_numero", "titulo",
           "descricao", "situacao", "e_rascunho", "comentarios",
           "branch_origem", "branch_destino", "revisores_ids",
           "responsaveis_ids", "rotulos", "grupo"], fato_mr_rows)
write_csv("fato_cartoes",
          ["sk_grupo", "sk_autor", "sk_fechado_por", "sk_sprint",
           "sk_data_criacao", "criado_em", "sk_data_atualizacao",
           "atualizado_em", "sk_data_fechamento", "fechado_em",
           "sk_data_prazo", "prazo_em", "cartao_numero", "titulo",
           "descricao", "situacao", "peso", "comentarios",
           "tempo_estimado_s", "tempo_gasto_s", "responsaveis_ids",
           "rotulos", "grupo"], fato_cartoes_rows)
write_csv("fato_kanban_eventos",
          ["sk_evento", "sk_grupo", "sk_pessoa", "sk_quadro_coluna",
           "sk_data_evento", "ocorrido_em", "grupo", "cartao_numero",
           "acao", "tipo_evento", "coluna"], fato_eventos_rows)

# Publica tudo de uma vez: só substitui os CSVs publicados depois de
# gerar todos sem erro (evita conjunto meio velho/meio novo).
OUT.mkdir(exist_ok=True)
try:
    for nome in ["dim_grupo", "dim_pessoa", "dim_sprint", "dim_quadro_coluna",
                 "dim_data", "fato_commits", "fato_merge_requests",
                 "fato_cartoes", "fato_kanban_eventos"]:
        os.replace(TMP / f"{nome}.csv", OUT / f"{nome}.csv")
except Exception:
    shutil.rmtree(TMP, ignore_errors=True)
    raise
TMP.rmdir()

for nome, rows in [("dim_grupo", dim_grupo_rows), ("dim_pessoa", dim_pessoa_rows),
                   ("dim_sprint", dim_sprint_rows),
                   ("dim_quadro_coluna", dim_quadro_coluna_rows),
                   ("dim_data", dim_data_rows),
                   ("fato_commits", fato_commits_rows),
                   ("fato_merge_requests", fato_mr_rows),
                   ("fato_cartoes", fato_cartoes_rows),
                   ("fato_kanban_eventos", fato_eventos_rows)]:
    print(f"{nome}: {len(rows)} registros")
print("regenere o lakehouse: python lakehouse/build_lakehouse.py")