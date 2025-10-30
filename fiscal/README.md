# Fiscal Agent

Aplicação Streamlit voltada à auditoria de documentos fiscais (NF-e) com suporte a agentes LangChain.

## Visão geral

- Upload de arquivos (CSV, XLSX, XML, ZIP) ou leitura via Supabase.
- Painel com métricas base (totais, CFOP/NCM, agregações por UF e CFOP).
- Ferramentas interativas para validações automáticas, ranking de ofensores, gráficos customizados e relatório PDF.
- Agente fiscal (OpenAI Functions + LangChain) com ferramentas especializadas:
  - Estatísticas (totais, agrupamentos, extremos, descrição numérica).
  - Nota extrema (maior/menor valor considerando `valor_nota_fiscal` ou soma item a item).
  - Recarga de dataset (upload/Supabase) e fallback semântico para perguntas abertas.

## Requisitos

- Python 3.10+
- Dependências listadas em `requirements.txt`
- Variáveis de ambiente mínimas: `OPENAI_API_KEY`, `OPENAI_MODEL` (ex.: `gpt-4o-mini`).
- Para Supabase: `SUPABASE_URL` e `SUPABASE_SERVICE_ROLE_KEY` (opcional).

## Instalação

```bash
pip install -r fiscal/requirements.txt
```

## Execução

```bash
streamlit run fiscal/app.py
```

### Docker

**Docker Compose**

```bash
cd fiscal
docker compose up --build
```

**Docker (build/run manual)**

```bash
cd fiscal
docker build -t fiscal-agent -f Dockerfile ..
docker run --rm -p 8502:8502 \
  -e OPENAI_API_KEY=... \
  -e OPENAI_MODEL=gpt-4o-mini \
  fiscal-agent
```

## Funcionalidades principais

1. **Carregamento de dados**
   - Upload persistido em `/tmp/sigma-ia2a/fiscal` para reuso.
   - Conexão Supabase com parâmetros configuráveis pela barra lateral.

2. **Resumo e gráficos**
   - Métricas gerais de notas, itens, emitentes/destinatários.
   - Tabelas Top CFOP/NCM.
   - Gráficos de valor agregado por UF e por CFOP.

3. **Validações e auditoria**
   - Execução das regras core (`run_core_validations`).
   - Ranking de maiores ofensores.
   - Ferramentas específicas (`listar_inconsistencias`, `detalhar_regra`, `resumo_riscos`, `maior_nota`, etc.).

4. **Agente fiscal**
   - Usa `AgentType.OPENAI_FUNCTIONS` com histórico em memória.
   - Sistema injeta persona/formatos e escolhe automaticamente as ferramentas adequadas.
   - Ferramenta semântica (`analise_semantica`) garante respostas mesmo sem regra específica.

5. **Relatórios**
   - Bloco “Conclusões automáticas”.
   - Geração de PDF consolidando gráficos e QA.

## Estrutura

```
fiscal/
├── agents/            # Orquestradores, ferramentas (data_access, statistics, semantic, helpers)
├── domain/            # Funções de carga, overview, validações
├── app.py             # Aplicação Streamlit
├── requirements.txt   # Dependências
└── README.md          # Este arquivo
```

## Personalização

- Ajuste do modelo via sidebar (`OPENAI_MODEL`).
- Inclusão de novas ferramentas: crie em `fiscal/agents/` e registre no orquestrador.
- Estilos/cores dos gráficos Plotly podem ser alterados diretamente em `app.py`.

## Troubleshooting

- **Erro ao carregar Supabase**: verifique URL/senha e se o schema está liberado (`public` ou `graphql_public`).
- **Agente pede novo upload**: confirme permissões de escrita em `/tmp`.
- **Respostas genéricas**: revise o `OPENAI_API_KEY` e o modelo informado; use ferramentas de estatística para reforçar contexto.

## Licença

Este projeto está licenciado sob os termos da Licença MIT. Consulte `LICENSE.md` para mais detalhes.
