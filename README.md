# Relatório Técnico - Agentes Autônomos

## 0. Vídeo Explicativo do projeto
[![Watch the video](https://i.ytimg.com/vi/zImwQmLr59s/hqdefault.jpg)](https://youtu.be/zImwQmLr59s)

## O Projeto

![000.1-projeto.png](fiscal/images/000.1-projeto.png)

![000.2-projeto.png](fiscal/images/000.2-projeto.png)


## 1. Frameworks Utilizados
- **Streamlit**: interface web para upload de CSV, configuração de credenciais e interação direta com o agente EDA.
- **LangChain**: construção do orquestrador e dos agentes de domínio (descritivo, padrões, anomalias, visualização) com memória conversacional.
- **OpenAI Chat API**: modelo linguístico para interpretar perguntas e produzir respostas em português, incluindo geração de gráficos via `CHART_SPEC`.
- **Plotly + Kaleido**: renderização de gráficos interativos e exportação para imagens utilizadas no relatório PDF.
- **scikit-learn / pandas / numpy**: suporte analítico (clusters, correlações, estatísticas, manipulação do DataFrame). 

### 1.1 Desenho de solução
![diagram-soluction.png](fiscal/images/diagram-soluction.png)

## 2. Estrutura da Solução
- `app.py`: ponto central da aplicação Streamlit (upload de dados, EDA automático, interface de perguntas, geração de PDF).
- `agents/orchestrator.py`: orquestrador que classifica a intenção da pergunta e delega para o agente especializado correspondente.
- `agents/*.py`: implementações dos agentes com ferramentas específicas (estatísticas, padrões, outliers, geração de CHART_SPEC).
- `domain/analysis.py` e `domain/charts.py`: funções reutilizáveis para diagnósticos, correlações, outliers e utilidades de gráfico.
- Dockerfile + docker-compose: empacotamento da aplicação com todas as dependências, respeitando variáveis de ambiente via `.env`.

## 3. Fluxo de Uso
1. O usuário carrega um CSV (ou consulta Supabase) e informa as chaves diretamente na UI ou via `.env`.
2. O app executa um módulo inicial (tipos, estatísticas, valores ausentes, correlações) e exibe diagnósticos automáticos (padrões temporais, outliers, clusters).
3. Cada pergunta é enviada ao orquestrador LangChain, que chama o agente adequado e responde sempre em português.
4. Quando apropriado, o agente gera um bloco `CHART_SPEC` e a UI desenha o gráfico correspondente com Plotly.
5. O botão “Gerar conclusões do agente” produz um resumo automático dos principais achados.
6. O botão “Gerar PDF” consolida perguntas, respostas, conclusões e até 6 gráficos em `Agentes Autônomos - Relatório da Atividade Extra.pdf`.

## 4. Perguntas de Exemplo e Respostas
- **“Existem valores atípicos nos dados?”** – usa `outlier_report` e relata contagens, limites e sugestões de tratamento.
- **“Como esses outliers afetam a análise?”** – discute impacto nas médias, percentuais e recomendações práticas.
- **“Podemos remover, transformar ou investigar esses outliers?”** – sugere remoção, winsorização e transformações log.
- **Pergunta com gráfico** (ex.: “Gerar um gráfico de correlação das variáveis numéricas”) – retorna `CHART_SPEC` e cria o gráfico automaticamente.
- **“Quais as conclusões finais do agente?”** – o botão dedicado gera um resumo em linguagem natural que também vai para o PDF.

## 5. Conclusões do Agente
O agente mantém memória via `ConversationBufferMemory`, permitindo respostas contextualizadas e conclusões coerentes. Essa memória é utilizada para: 
- Relembrar perguntas anteriores ao gerar insights;
- Produzir o resumo final a partir das interações já realizadas;
- Exportar perguntas, respostas e gráficos relevantes para o PDF final.

## 6. Observações
- Antes de gerar o PDF, acione pelo menos quatro perguntas (uma delas com gráfico) e execute “Gerar conclusões do agente”.
- Preencha `OPENAI_API_KEY`, `SUPABASE_URL` e `SUPABASE_SERVICE_ROLE_KEY` (via `.env` ou UI) antes do upload dos dados.
- Recompile a imagem Docker com `docker compose build --no-cache app` sempre que alterar `app.py`, `agents/` ou `domain/`.

## 7. Diagramas

### 7.1 - Integração - Fluxo de integração entre agentes
```mermaid
sequenceDiagram
participant U as Usuário (Streamlit)
participant UI as fiscal/app.py
participant Orc as FiscalOrchestrator
participant LLM as ChatOpenAI (OPENAI_FUNCTIONS)
participant Tools as Ferramentas (dados/estatísticas/semântica)

      U->>UI: Digita pergunta ("Qual a maior nota?")
      UI->>Orc: answer(question, context)

      Orc->>LLM: Classificação de domínio<br/>(VALIDACAO/AUDITORIA/INTEGRACAO)
      LLM-->>Orc: Domínio sugerido

      Orc->>Orc: Seleciona persona e system_message<br/>Monta prompt base

      Orc->>Tools: Carrega toolset do domínio<br/>+ ferramentas comuns (estatísticas, nota_extrema, analise_semantica, recarga)

      Orc->>LLM: Invoca agente (prompt com contexto + pergunta)
      alt Agente decide usar ferramenta
          LLM->>Tools: Executa tool específica<br/>(ex.: nota_extrema)
          Tools-->>LLM: Resultado numérico/textual
      end

      LLM-->>Orc: Resposta final formatada<br/>(**Resumo/Evidências/Observação**)
      Orc-->>UI: OrchestratorResult (domínio + output + passos)
      UI-->>U: Exibe resposta e cadeia de passos (se habilitado)
```

### 7.2 C4 - Visão de Contexto
```mermaid
graph TD
    U[Usuário Analista]
    SYS[[Sistema EDA/Fiscal Autônomo]]
    LLM[OpenAI Chat API]
    SUPA[Supabase]
    CSV[Arquivos CSV]

    U --> SYS
    SYS --> LLM
    SYS --> SUPA
    U --> CSV
    SYS --> CSV
```

### 7.3 C4 - Visão de Containers
```mermaid
graph TD
    subgraph AmbienteLocal[Workspace do Usuário]
        U[Usuário]
        UI[Streamlit Web App]
        DF[Pandas DataFrame]
        AGENTS[Agentes LangChain]
    end

    subgraph Nuvem
        LLM[OpenAI Chat API]
        SUPA[Supabase - opcional]
    end

    U --> UI
    UI --> DF
    UI --> AGENTS
    AGENTS --> DF
    AGENTS --> LLM
    UI --> SUPA
    UI -->|Exporta| PDF[(Relatório PDF)]
```

### 7.4 C4 - Visão de Componentes (Container Streamlit)
```mermaid
graph TD
    subgraph StreamlitApp[Container: Streamlit EDA/Fiscal]
        UI[Camada UI - app.py - Streamlit]
        ORCH[Orquestrador - LangChain DomainOrchestrator]
        TOOLS[Agentes de Domínio]
        ANALYSIS[Módulo domain/analysis]
        CHARTS[Módulo domain/charts]
    end

    UI --> ORCH
    UI --> ANALYSIS
    ORCH --> TOOLS
    TOOLS --> ANALYSIS
    TOOLS --> CHARTS
    ORCH -->|LLM| LLM[(OpenAI Chat API)]
    UI --> DF[(Pandas DataFrame)]
    DF --> ANALYSIS
    UI --> PDF[(Relatório PDF)]
```



## 8. Módulo Fiscal (NF-e)
- App dedicado localizado em `fiscal/app.py`, com dependências em `fiscal/requirements.txt`.
- Replica as capacidades do módulo com foco em documentos fiscais: upload de CSV/XLSX/XML/ZIP, leitura Supabase, validador automático, agente LangChain e geração de PDF.
- Principais validações: CFOP x destino, NCM, CNPJ, cálculo de ICMS, divergência de totais e duplicidade de itens.
- Agentes especializados: Validação, Auditoria e Integração com ERPs (Domínio, Alterdata, Protheus).
- Execução local: `streamlit run fiscal/app.py` (defina `OPENAI_API_KEY` e, se necessário, credenciais do Supabase).

## 9. Execução com Docker

| Módulo | Docker Compose | Docker Standalone |
|--------|----------------|-------------------|
| **EDA** | `cd eda && docker compose up --build` | `cd eda && docker build -t eda-agent . && docker run --rm -p 8501:8501 -e OPENAI_API_KEY=... eda-agent` |
| **Fiscal** | `cd fiscal && docker compose up --build` | `cd fiscal && docker build -t fiscal-agent -f Dockerfile .. && docker run --rm -p 8502:8502 -e OPENAI_API_KEY=... fiscal-agent` |

- Crie um arquivo `.env` (ou exporte variáveis) com `OPENAI_API_KEY`, `OPENAI_MODEL` e, opcionalmente, `SUPABASE_URL` e `SUPABASE_SERVICE_ROLE_KEY` antes de subir os containers.
- Para atualizar a imagem após mudanças de código, execute `docker compose build --no-cache` no diretório do módulo correspondente.
