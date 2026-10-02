# Especificação de Requisitos do Dashboard — Processo PBL

* **Projeto:** Dashboard do Processo de Aprendizagem Baseada em Projetos (PBL)  
* **Stakeholder Principal (Cliente):** Professor Orientador (Prof.ª Vanessa Nunes — Instituto Ápice). 
* **Contexto Operacional:** Módulo de 10 semanas dividido em 5 Sprints quinzenais, com entregas impreterivelmente às sextas-feiras até às 23h59.
* **Necessidade Central:** Identificar, a cada sprint quinzenal, **onde e como intervir precocemente** para corrigir gargalos, desequilíbrios de esforço ou falhas na colaboração antes do início do próximo ciclo.
* **Arquitetura e Fonte de Dados:** Modelo Estrela (Star Schema) armazenado na pasta relacional/ (fato_commits, fato_cartoes, fato_merge_requests, dim_pessoa, dim_sprint, dim_projeto), estruturado no PostgreSQL (schema pbl) e Lakehouse DuckDB.
---
## 1. Diretrizes Estratégicas e Restrições Inegociáveis

* **Objeto de Observação:**  objeto observado é o processo de aprendizagem do grupo. As ferramentas (GitLab e Kanban) funcionam apenas como superfícies de observação que registram o rastro digital.
* **Autoridade Humana:** O painel é um instrumento de suporte à decisão pedagógica. Ele apresenta evidências e provocações, jamais emitindo vereditos, atribuindo notas ou gerando rankings automáticos.
* **Unidade de Análise:** A saída visual é sempre focada no **grupo**. A análise do indivíduo serve exclusivamente para entender o equilíbrio da distribuição interna do próprio grupo.
* **Respeito às Limitações dos Dados:** Atividades presenciais como discussões ou tarefas que não deixaram rastro digital não constituem ausência de trabalho, mas sim limitações da fonte de dado.
---
## 2. Requisitos Estruturados pelas Perguntas de Decisão
### Pergunta 1: O grupo trabalhou ao longo do módulo ou na véspera?
* **Pilar Pedagógico:** Colaboração e Cadência Temporal.
* **Objetivo da Decisão:** Identificar se o grupo mantém um ritmo de trabalho sustentável e contínuo ao longo das duas semanas de sprint ou se procrastina e acumula o esforço na véspera da entrega (quarta a sexta-feira).
* **Requisito (REQ-01):** O painel deve exibir o histograma diário de atividades (commits e movimentações de cartões) ao longo dos 14 dias da sprint.
* **Mapeamento da Fonte Relacional:** Cruzamento entre a tabela fato relacional/fato_commits.csv e a dimensão relacional/dim_sprint.csv.
* **Tratamento de Dados:** Utilização estrita do carimbo de data da escrita no servidor (data_servidor), evitando distorções provocadas por rebase ou alterações na data do computador local do aluno (data_autor).
* **Critério de Aceite:** O gráfico deve sinalizar visualmente a porcentagem de entregas realizadas nos últimos 2 dias da sprint em relação ao total.
* **Lacuna/Limitação:** O rastro digital não registra leituras de código, pesquisas ou reuniões de planejamento que antecedem a escrita efetiva de commits.
---
### Pergunta 2: O trabalho foi distribuído ou concentrado?
* **Pilar Pedagógico:** Contribuição e Equilíbrio de Participação.
* **Objetivo da Decisão:** Detectar se a produção do projeto está centralizada em apenas um integrante (gerando sobrecarga).
* **Requisito (REQ-02):** O painel deve apresentar a distribuição percentual de contribuição por membro dentro do grupo, isolando de forma transparente a fatia de autoria não resolvida.
* **Mapeamento da Fonte Relacional:** Cruzamento entre relacional/fato_commits.csv e relacional/dim_pessoa.csv.
* **Tratamento de Dados:** Exibição explícita da categoria [externo] (~21% dos commits) para identificar alterações enviadas via terminal local com e-mails não vinculados à conta institucional.
* **Critério de Aceite:** O painel deve exibir o índice de concentração integrante e o índice de concentração do grupo sem ordenar ou ranquear os grupos entre si em filas competitivas.
* **Lacuna/Limitação:** Atividades de *pair programming* no mesmo computador ou auxílio presencial entre colegas não são atribuídas aos dois alunos automaticamente.
---
### Pergunta 3: Como está o code review?
* **Pilar Pedagógico:** Colaboração, Integração e Qualidade Técnica.
* **Objetivo da Decisão:** Avaliar se a integração do código passa por um processo genuíno de revisão entre os pares antes de ser incorporado à branch principal.
* **Requisito (REQ-03):** O painel deve monitorar o ciclo de vida dos *Merge Requests* (MRs), destacando os revisores envolvidos, o tempo de permanência aberto e o volume de interação.
* **Mapeamento da Fonto Relacional:** Tabela fato relacional/fato_merge_requests.csv relacionando autor_id e revisores_ids com relacional/dim_pessoa.csv.
* **Métricas Analisadas:** Intervalo de tempo entre data_criacao e data_fechamento, quantidade de comentários (numero_comentarios) e identificação dos aprovadores.
* **Critério de Aceite:** Exibição do tempo médio de aprovação de MRs e identificação de MRs aprovados instantaneamente ou sem comentários de revisão.
* **Lacuna/Limitação:** A base de dados registra o número de comentários em um MR, mas não armazena o texto dos comentários, impossibilitando a análise automatizada da qualidade do feedback.

---

### Pergunta 4: O quadro reflete o repositório?
* **Pilar Pedagógico:** Coerência e Governança do Processo.
* **Objetivo da Decisão:** Garantir que o status das tarefas declaradas no quadro Kanban corresponda às entregas efetivas e rastreáveis no versionamento do código.
* **Requisito (REQ-04):** O painel deve cruzar os cartões movidos para a coluna de "Concluído/Done" com os commits e *merge requests* vinculados no mesmo período.
* **Mapeamento da Fonte Relacional:** Cruzamento entre relacional/fato_cartoes.csv, relacional/fato_kanban_movimento.csv e relacional/fato_commits.csv.
* **Critério de Aceite:** Sinalização gráfica de cartões marcados como concluídos que não possuem commits associados ou links para evidências externas.
* **Lacuna/Limitação:** Evidências anexadas como links externos (Google Colab, Google Drive) exigem verificação manual pelo orientador, pois o sistema armazena apenas a URL.
---
## 3. Matriz Resumo de Rastreabilidade de Requisitos

| Pergunta de Decisão | Requisito Relacionado | Tabela de Origem | Indicador / Métricas | Limitação Declarada |
| :--- | :--- | :--- | :--- | :--- |
| **1. Ritmo de Trabalho** | REQ-01 (Cadência Temporal) | fato_commits x dim_sprint | % de commits nos últimos 2 dias da sprint | Usa `data_servidor` por causa de *rebase*. |
| **2. Distribuição** | REQ-02 (Concentração) | fato_commits x dim_pessoa | Proporção por membro e isolamento da faixa `[externo]` | Não capta trabalho em pares presencial. |
| **3. Code Review** | REQ-03 (Integração) | fato_merge_requests x dim_pessoa | Tempo de vida do MR e número de comentários | Não contém o texto do comentário. |
| **4. Coerência** | REQ-04 (Kanban vs Git) | fato_cartoes x fato_commits | Taxa de cartões "Done" com rastro no Git/Links  | Links externos exigem checagem manual. |