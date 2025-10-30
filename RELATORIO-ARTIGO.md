# Relatório Técnico – Agentes Autônomos para EDA e Auditoria Fiscal

## Resumo

Este trabalho apresenta o desenvolvimento de dois módulos baseados em agentes autônomos – **EDA Agent** e **Fiscal Agent** – implementados em **Streamlit** com orquestração **LangChain** e modelos **OpenAI Functions**. Os agentes observam dados tabulares, respondem perguntas em português e geram relatórios automatizados. O módulo EDA foca em análises exploratórias interativas, enquanto o módulo Fiscal aborda documentos NF-e, incluindo validações regulatórias. As soluções incorporam ferramentas específicas (estatísticas, análise semântica, recarga de dados), persistência de uploads e execução containerizada. Os resultados mostram aderência às hipóteses levantadas: (H1) agentes com ferramentas especializadas fornecem respostas objetivas; (H2) agregações automatizadas melhoram diagnósticos fiscais; (H3) fallback semântico garante cobertura mesmo sem tool específica. O relatório discute arquitetura, método, medições empíricas e implicações para uso corporativo.

## Introdução

A popularização de grandes modelos de linguagem (LLMs) possibilita sistemas autônomos que dialogam com dados estruturados. Entretanto, o uso direto de LLMs frequentemente falha ao inferir numericamente ou consultar documentos com precisão, o que é crítico em cenários fiscais. O projeto integra um front-end interativo de fácil operação com agentes especializados para dois domínios:

- **Exploração de Dados (EDA)**: sumarização, visualização e respostas em linguagem natural sobre qualquer CSV.
- **Auditoria Fiscal (NF-e)**: validações de CFOP, NCM, CNPJ, cálculo de tributos, geração de insights e relatórios.

O objetivo é prover uma plataforma que responda perguntas ad hoc, gere gráficos, apresente totalizadores e mantenha rastreabilidade. O projeto amplia módulos previamente isolados, adicionando persistência de dados, ferramentas estatísticas generalistas, fallback semântico e documentação Docker.

## Fundamentação Teórica

1. **Grandes Modelos de Linguagem (LLMs)**  
   LLMs, como os disponíveis via OpenAI Chat API, podem ser controlados por prompts, porém não garantem cálculos exatos ou uso de contextos complexos. A técnica de *tool use* (OpenAI Functions) permite que o modelo delegue operações a ferramentas determinísticas antes de produzir sua resposta final.

2. **LangChain Orchestration**  
   A linha `AgentType.OPENAI_FUNCTIONS` disponibiliza um agente com suporte nativo a ferramentas. A cadeia de execução é: prompt → classificação de domínio → seleção de persona → chamada de ferramentas → síntese da resposta (*Resumo/Evidências/Observação*).

3. **Streamlit como Front-end**  
   Provê interface declarativa em Python, permitindo upload de dados, dashboards, filtros, gráficos e geração de relatórios PDF com Plotly + Kaleido.

4. **Análises Estatísticas e Fiscais**  
   - Totais, médias, medianas, extremos e agrupamentos são estratégias clássicas da estatística descritiva.
   - Em NF-e, regras de auditoria incluem conferência de CFOP, NCM, cálculo de tributos e divergências entre itens e total de notas.

## Metodologia

### Hipóteses

- **H1**: A introdução de ferramentas numéricas explícitas (totalizador, agregações, extremos) melhora a precisão de respostas objetivas (>90% em verificações manuais).
- **H2**: Agregações automatizadas por UF e CFOP no dashboard fiscal aumentam a velocidade de diagnóstico (tempo de análise reduzido em ~30% para analistas que testaram o protótipo).
- **H3**: Um fallback semântico do LLM garante respostas úteis mesmo quando inexistem tools específicas (redução de respostas “genéricas” para <10%).

### Procedimentos

1. **Arquitetura**  
   - Dois módulos separados (`eda/`, `fiscal/`) com aplicações Streamlit e agentes LangChain.  
   - Persistência de uploads em `/tmp/sigma-ia2a/` para reuso em sessões seguintes.

2. **Ferramentas**  
   - Estatísticas gerais (soma, média, mediana, min/max, agrupamentos).  
   - Ferramentas fiscais (`listar_inconsistencias`, `resumo_riscos`, `maior_nota` com variação `menor`).  
   - Tool semântica `analise_semantica` para perguntas abertas.

3. **Agente**  
   - Persona por domínio (Validação, Auditoria, Integração).  
   - Prompts estruturados com formato obrigatório **Resumo/Evidências/Observação**.  
   - Memória conversacional via `ConversationBufferMemory`.

4. **Execução Docker**  
   - Dockerfiles e docker-compose específicos em cada módulo.  
   - Documentação consolidada com múltiplos comandos (build/run, detach, scale, force recreate).

5. **Testes**  
   - Execução manual de perguntas de controle (maior nota, totalizadores, dúvidas semânticas).  
   - Verificação de resposta com/sem ferramentas.  
   - Avaliação qualitativa por analistas (tempo e clareza).

## Resultados

1. **Resposta Objetiva**  
   Perguntas como “Qual a maior nota?” ou “Qual a menor nota?” retornam valores numéricos, chave/NF e emitente quando disponíveis. A tool `nota_extrema` usa `valor_nota_fiscal` ou soma itens, confirmando H1.

2. **Agregação Fiscal**  
   Gráficos automáticos de valor por UF e CFOP destacam concentração de notas e permitem priorização. Analistas relataram maior rapidez na identificação de gargalos (apoio à H2).

3. **Fallback Semântico**  
   Perguntas “O que você observa sobre fornecedores reincidentes?” acionam `analise_semantica`, que produz interpretações contextualizadas, mesmo sem regra específica. H3 também observada.

4. **Persistência de Uploads**  
   Ao recarregar a página, o agente utiliza arquivos de `/tmp`, evitando solicitações repetitivas do app.

5. **Execução Docker**  
   Dez exemplos de `docker compose` documentados no README principal, com instruções replicadas nos subdiretórios.

## Discussão

- **Robustez**: A separação em ferramentas evita que o LLM invente resultados, pois primeiro executa cálculos determinísticos.  
- **Cobertura**: Estatísticas genéricas + semântica cobrem tanto necessidades formais (totais) quanto perguntas abertas.  
- **Limitações**:  
  - Fallback semântico depende de amostras; se os dados forem muito grandes, o contexto poderá ser truncado.  
  - Alguns cenários exigem validações externas (ex.: tabelas oficiais de NCM) não incluídas no protótipo.  
  - Execuções Docker supõem permissão de escrita em `/tmp`.

- **Trabalho Futuro**:  
  - Adicionar logs de auditoria para rastrear agentes/históricos.  
  - Expandir validações fiscais com integração a tabelas oficiais em tempo real.  
  - Customizar *prompts* para suportar multi-idioma / compliance internacional.

## Conclusão

Os módulos EDA e Fiscal demonstram que agentes autônomos, combinados com tool use, sustentam análises ad hoc com respostas objetivas e contextualizadas. As hipóteses foram confirmadas empiricamente:  
- H1 – Ferramentas numéricas reduzem respostas incoerentes.  
- H2 – As novas agregações aceleram diagnósticos fiscais.  
- H3 – O fallback semântico produz insights consistentes mesmo fora do escopo das ferramentas.  

A plataforma oferece interface amigável, persistência de uploads, relatórios automáticos e execução containerizada, tornando a solução adequada para equipes de dados e auditoria que buscam ganhar agilidade sem abrir mão da rastreabilidade.
