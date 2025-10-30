# EDA Agent

Aplicação Streamlit para análise exploratória de dados (EDA) com agentes LangChain.

## Visão Geral

- Upload de arquivos CSV e resumo instantâneo (tipos, estatísticas, correlações, faltantes).
- Dashboard interativo com gráficos e diagnóstico automático (padrões, frequências, outliers, clusters, relações).
- Agente de perguntas & respostas sobre o dataset com memória e ferramentas personalizadas.
- Geração de PDF com insights e gráficos selecionados.

## Requisitos

- Python 3.10+
- Dependências em `requirements.txt`
- `OPENAI_API_KEY` e `OPENAI_MODEL` (ex.: `gpt-4o-mini`) para usar o agente.
- Para Supabase (opcional): `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`.

## Instalação

```bash
pip install -r eda/requirements.txt
```

## Execução

```bash
streamlit run eda/app.py
```

### Docker

**Docker Compose**

```bash
cd eda
docker compose up --build
```

**Docker (build/run manual)**

```bash
cd eda
docker build -t eda-agent .
docker run --rm -p 8501:8501 \
  -e OPENAI_API_KEY=... \
  -e OPENAI_MODEL=gpt-4o-mini \
  eda-agent
```

## Funcionalidades

1. **Carregamento de dados**
   - Upload CSV (persistido em `/tmp/sigma-ia2a/eda`).
   - Conexão Supabase configurável via sidebar.

2. **Resumo e diagnóstico**
   - Métricas básicas (linhas, colunas, numéricas, não numéricas).
   - Estatísticas, faltantes, correlações, insights automáticos.
   - Gráficos gerados pelo usuário ou pelo agente, com suporte a ChartSpec.

3. **Agente EDA (LangChain)**
   - Ferramentas de descrição, padrões, anomalias, visualização.
   - Tool de recarga (upload/Supabase) e fallback semântico.
   - Memória conversacional via `ConversationBufferMemory`.

4. **Relatórios**
   - Conclusões automáticas e exportação em PDF.

## Estrutura

```
eda/
├── agents/            # Orquestrador e ferramentas (descriptive, patterns, anomalies, visualization, data_access)
├── domain/            # Funções de análise e ChartSpec
├── app.py             # Aplicação Streamlit
├── requirements.txt   # Dependências
└── README.md          # Este arquivo
```

## Personalização

- Ajuste do modelo via sidebar (`OPENAI_MODEL`).
- Novas ferramentas podem ser adicionadas em `eda/agents/` e registradas no orquestrador.
- Estilos de gráficos e diagnósticos podem ser modificados em `app.py`.

## Troubleshooting

- **Erro ao responder perguntas**: verifique `OPENAI_API_KEY` e o modelo configurado.
- **Supabase sem dados**: valide URL/credenciais e se o schema está exposto (`public` ou `graphql_public`).
- **Gráficos vazios**: assegure que o dataset tenha colunas compatíveis e que os tipos numéricos foram coercidos corretamente.

## Licença

Adapte conforme a licença do projeto principal.
