"""
Streamlit + LangChain EDA Agent (string-friendly)
=================================================

Features
--------
- Upload any CSV (1st row = header).
- Instant EDA summary (schema, stats, missing, correlations).
- Graph builder (histogram, box, scatter, line, bar, correlation heatmap).
- LangChain-powered DataFrame Agent with memory to answer questions about the data.
- Optional dataset-specific helpers if columns like `Time`, `Class`, `Amount` exist.
- Generate a PDF report summarizing Q&A + selected charts.

Requirements (pip)
------------------
streamlit
pandas
numpy
plotly
kaleido          # for Plotly -> image export (PDF generation)
fpdf2            # PDF generation
langchain
langchain-openai # or replace with your provider
langchain-experimental
Supabase         # Supabase Python client

Run
---
export OPENAI_API_KEY=sk-...  # or set in .streamlit/secrets.toml
streamlit run streamlit_langchain_eda_app.py

Notes
-----
- This app does not require any database; it runs locally.
- If you can't or don't want to use OpenAI, you can swap ChatOpenAI by another LangChain LLM.
"""

import io
import os
import sys
import textwrap
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from supabase import create_client

# PDF
from fpdf import FPDF

# LangChain (swap the provider if needed)
from langchain_openai import ChatOpenAI
# Compatibilidade com mudanças recentes do LangChain
try:
    from langchain.memory import ConversationBufferMemory
except ModuleNotFoundError:
    try:
        from langchain.chains.conversation.memory import ConversationBufferMemory  # type: ignore
    except ModuleNotFoundError:
        try:
            from langchain_core.memory import ConversationBufferMemory  # type: ignore
        except ModuleNotFoundError as exc:
            raise ModuleNotFoundError(
                "Não foi possível importar ConversationBufferMemory. Verifique a instalação do pacote 'langchain'."
            ) from exc

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from agents import AgentDataContext, DomainOrchestrator
from domain import (
    ChartSpec,
    OUTLIER_SUGGESTIONS,
    coerce_numeric,
    compute_advanced_analysis,
    dataframe_signature,
    eda_overview,
    extract_chart_spec_from_text,
    normalize_chart_spec,
    readable_dtype,
)

def get_supabase_client() -> Any:
    """Create Supabase client from st.secrets or environment.
    Uses service role key for simplicity (do NOT expose in public apps)."""
    url = get_secret_or_env("SUPABASE_URL", "")
    key = get_secret_or_env("SUPABASE_SERVICE_ROLE_KEY", "")
    if not url or not key:
        raise RuntimeError("Configure SUPABASE_URL e SUPABASE_SERVICE_ROLE_KEY via variáveis de ambiente.")
    return create_client(url, key)


def load_supabase_table(schema: str, table: str, limit: int = 20000) -> pd.DataFrame:
    sb = get_supabase_client()
    if sb is None:
        raise RuntimeError("Configure SUPABASE_URL e SUPABASE_SERVICE_ROLE_KEY em st.secrets ou env.")

    limit = int(limit or 20000)
    if limit <= 0:
        raise ValueError("'limit' deve ser maior que zero.")
    schema_normalized = (schema or "public").strip() or "public"
    allowed_schemas = {"public", "graphql_public"}
    if schema_normalized not in allowed_schemas:
        allowed = ", ".join(sorted(allowed_schemas))
        raise ValueError(
            "O endpoint REST do Supabase aceita apenas schemas "
            f"{allowed}. Ajuste PG_SCHEMA ou exponha o schema desejado no Supabase."
        )

    table_ref = sb.table(table)

    chunk_size = 50000
    all_rows: list[dict[str, Any]] = []
    for start in range(0, limit, chunk_size):
        end = min(start + chunk_size - 1, limit - 1)
        response = table_ref.select("*").range(start, end).execute()
        error = getattr(response, "error", None)
        if error:
            raise RuntimeError(f"Erro Supabase: {error}")
        rows = response.data or []
        if not rows:
            break
        all_rows.extend(rows)
        if len(rows) < (end - start + 1):
            break

    df = pd.DataFrame(all_rows)
    return df

def format_intermediate_steps(steps: List[Tuple[Any, Any]]) -> List[Dict[str, str]]:
    formatted: List[Dict[str, str]] = []
    for idx, item in enumerate(steps, start=1):
        action, observation = item if isinstance(item, tuple) and len(item) == 2 else (item, "")
        action_name = getattr(action, "tool", "pensamento")
        action_log = getattr(action, "log", str(action))
        formatted.append({
            "passo": idx,
            "acao": action_name,
            "detalhes": action_log,
            "observacao": str(observation),
        })
    return formatted


# -----------------------------
# EDA helpers
# -----------------------------

def render_chart(df: pd.DataFrame, spec: ChartSpec):
    if spec.kind == "Histogram":
        fig = px.histogram(df, x=spec.x, nbins=spec.bins or 30, color=spec.color, marginal="box")
    elif spec.kind == "Box":
        fig = px.box(df, x=spec.color if spec.color else None, y=spec.y or spec.x, points="outliers")
    elif spec.kind == "Scatter":
        fig = px.scatter(df, x=spec.x, y=spec.y, color=spec.color, trendline="ols")
    elif spec.kind == "Line":
        fig = px.line(df, x=spec.x, y=spec.y, color=spec.color)
    elif spec.kind == "Bar":
        if spec.aggfunc and spec.y:
            agg = getattr(df.groupby(spec.x)[spec.y], spec.aggfunc)()
            fig = px.bar(agg.reset_index(), x=spec.x, y=spec.y)
        else:
            fig = px.bar(df, x=spec.x, y=spec.y, color=spec.color)
    elif spec.kind == "Correlation heatmap":
        numeric_df = df.select_dtypes(include="number")
        if numeric_df.empty:
            st.warning("No h colunas numéricas suficientes para calcular correlao.")
            return None
        corr = numeric_df.corr()
        fig = px.imshow(corr, text_auto=True, aspect="auto", color_continuous_scale="RdBu", zmin=-1, zmax=1)
    else:
        st.warning("Tipo de gráfico não suportado.")
        return None

    st.plotly_chart(fig, use_container_width=True)
    return fig


def reset_agent_state():
    st.session_state.orchestrator = None
    st.session_state["orchestrator_model"] = None
    st.session_state["orchestrator_verbose"] = None
    st.session_state.agent_memory = ConversationBufferMemory(
        memory_key="chat_history", input_key="input", return_messages=True
    )
    st.session_state.qa = []
    st.session_state.last_intermediate_steps = []
    st.session_state.agent_recent_charts = []
    st.session_state.analysis_signature = None
    st.session_state.analysis_results = None


# -----------------------------
# LangChain Agent
# -----------------------------

# -----------------------------
# PDF report
# -----------------------------

def save_plotly_png(fig, path: str):
    # requires kaleido
    fig.write_image(path, scale=2)


def generate_pdf(path: str, framework: str, structure: str, qa: List[Dict[str, str]], conclusions: str, image_paths: List[str]):
    def pdf_text(value: str) -> str:
        return value.encode("latin-1", "replace").decode("latin-1")

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=12)

    def add_title(text: str):
        pdf.set_font("Helvetica", "B", 16)
        pdf.cell(0, 10, pdf_text(text), ln=1)

    def add_subtitle(text: str):
        pdf.set_font("Helvetica", "B", 13)
        pdf.cell(0, 8, pdf_text(text), ln=1)

    def add_paragraph(text: str):
        pdf.set_font("Helvetica", size=11)
        for line in textwrap.wrap(text, width=100):
            pdf.cell(0, 6, pdf_text(line), ln=1)

    pdf.add_page()
    add_title("Agentes Autônomos - Relatório da Atividade Extra")

    add_subtitle("1. Framework escolhida")
    add_paragraph(framework)

    add_subtitle("2. Como a solução foi estruturada")
    add_paragraph(structure)

    add_subtitle("3. Perguntas e respostas")
    for i, item in enumerate(qa, 1):
        add_paragraph(f"Q{i}: {item['q']}")
        add_paragraph(f"A{i}: {item['a']}")
        pdf.ln(2)

    if image_paths:
        add_subtitle("Gráficos")
        for p in image_paths:
            try:
                pdf.add_page()
                pdf.image(p, w=180)
            except Exception:
                pass

    pdf.add_page()
    add_subtitle("4. Conclusões do agente")
    add_paragraph(conclusions)

    add_subtitle("5. Observações")
    add_paragraph("Chaves/API foram omitidas do relatório. O link do agente é a URL pública do Streamlit.")

    pdf.output(path)

# 1) Adicione esse helper perto do topo do arquivo:
def get_secret_or_env(name: str, default: str = "") -> str:
    # Prefere env vars; se não tiver, tenta secrets; se não tiver, devolve default.
    v = os.environ.get(name)
    if v not in (None, ""):
        return v
    try:
        # isso s roda se realmente existir secrets.toml
        return st.secrets[name]
    except Exception:
        return default


def get_openai_temperature(default: float = 0.3) -> float:
    """Return the model temperature with graceful fallback when misconfigured."""
    raw_value = get_secret_or_env("OPENAI_TEMPERATURE", str(default))
    try:
        value = float(raw_value)
    except (TypeError, ValueError):
        st.warning("OPENAI_TEMPERATURE inválido; usando padrão %.1f." % default)
        return default
    # clamp to a sensible range supported by OpenAI
    return max(0.0, min(value, 2.0))


# -----------------------------
# Streamlit UI
# -----------------------------
st.set_page_config(page_title="EDA Agent - CSV + LangChain", layout="wide")
st.title("🔍 EDA Agent - CSV + LangChain + Streamlit")

default_allow = os.environ.get("ALLOW_DANGEROUS_CODE", "0").lower() in ("1", "true", "yes", "on")

with st.sidebar:
    st.header("Configuração")
    api_key = st.text_input("OPENAI_API_KEY", type="password",value=get_secret_or_env("OPENAI_API_KEY", ""))
    if api_key:
        os.environ["OPENAI_API_KEY"] = api_key
    model = st.text_input("Modelo (OpenAI)", value=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"))
    if model:
        os.environ["OPENAI_MODEL"] = model

    st.markdown("---")
    source = st.radio("Fonte de dados", ["Supabase", "CSV"], index=0, horizontal=True)

    # shared placeholders
    uploaded = None
    df_loader_trigger = False
    supabase_params = {}

    if source == "Supabase":
        url_default = get_secret_or_env("SUPABASE_URL", "")
        key_default = get_secret_or_env("SUPABASE_SERVICE_ROLE_KEY", "")
        st.text_input("SUPABASE_URL", value=url_default, key="sb_url")
        st.text_input("SUPABASE_SERVICE_ROLE_KEY", type="password", value=key_default, key="sb_key")
        schema = st.text_input("Schema", value=os.environ.get("PG_SCHEMA", "public"))
        table = st.text_input("Tabela", value=os.environ.get("DEFAULT_TABLE", "s3_creditcard"))
        limit = st.number_input("Limite de linhas", min_value=100, max_value=1_000_000, value=20000, step=1000,
                                help="Evite carregar tudo de uma vez em tabelas grandes.")
        if st.button("Carregar dados"):
            # store env so downstream libs also see them
            os.environ["SUPABASE_URL"] = st.session_state.sb_url
            os.environ["SUPABASE_SERVICE_ROLE_KEY"] = st.session_state.sb_key
            supabase_params.update(dict(schema=schema.strip() or "public",
                                        table=table.strip(), limit=int(limit)))
            df_loader_trigger = True
    else:
        st.caption("Envie um CSV para começar. Para JSON/NDJSON, converta para CSV antes.")
        uploaded = st.file_uploader("CSV", type=["csv"], accept_multiple_files=False)

    st.markdown("---")
    st.checkbox(
        "Permitir execução de código do agente (perigoso)",
        key="allow_code_toggle",
        value=st.session_state.get("allow_code_toggle", default_allow),
        help="O agente usa um REPL Python para operar no DataFrame. Use apenas em ambiente controlado."
    )
    st.checkbox(
        "Exibir cadeia de raciocínio (CoT)",
        key="show_cot_toggle",
        value=st.session_state.get("show_cot_toggle", False),
        help="Mostra o passo a passo gerado pelo agente. útil para auditoria."
    )

allow_code = st.session_state.get("allow_code_toggle", default_allow)
show_cot = st.session_state.get("show_cot_toggle", False)

if "df" not in st.session_state:
    st.session_state.df = None
if "agent_context" not in st.session_state:
    st.session_state.agent_context = AgentDataContext()
if "orchestrator" not in st.session_state:
    st.session_state.orchestrator = None
if "agent_memory" not in st.session_state:
    st.session_state.agent_memory = ConversationBufferMemory(
        memory_key="chat_history", input_key="input", return_messages=True
    )
if "charts" not in st.session_state:
    st.session_state.charts = []  # list of (title, fig)
if "qa" not in st.session_state:
    st.session_state.qa = []  # list of {q, a}
if "conclusions" not in st.session_state:
    st.session_state.conclusions = ""
if "analysis_signature" not in st.session_state:
    st.session_state.analysis_signature = None
if "analysis_results" not in st.session_state:
    st.session_state.analysis_results = None
if "last_intermediate_steps" not in st.session_state:
    st.session_state.last_intermediate_steps = []
if "agent_recent_charts" not in st.session_state:
    st.session_state.agent_recent_charts = []

col_left, col_right = st.columns([2, 1])

# Load data: Supabase or CSV
if df_loader_trigger:
    try:
        df = load_supabase_table(**supabase_params)
        if df.empty:
            st.warning("Tabela vazia ou não encontrada.")
        df = coerce_numeric(df)
        st.session_state.df = df
        context = st.session_state.agent_context
        context.df = df
        context.metadata.clear()
        context.metadata.update(
            {
                "source": "supabase",
                "supabase_schema": supabase_params.get("schema"),
                "supabase_table": supabase_params.get("table"),
                "limit": supabase_params.get("limit"),
                "supabase_limit": supabase_params.get("limit"),
            }
        )
        context.bump_version()
        reset_agent_state()
        st.success(f"Tabela carregada: {supabase_params['schema']}.{supabase_params['table']} • {df.shape[0]} linhas × {df.shape[1]} colunas")
    except Exception as e:
        st.error(f"Falha ao ler Supabase: {e}")
        st.stop()
elif uploaded is not None:
    try:
        raw_bytes = uploaded.getvalue()
        df = pd.read_csv(io.BytesIO(raw_bytes))
        df = coerce_numeric(df)
        st.session_state.df = df
        context = st.session_state.agent_context
        context.df = df
        context.metadata.clear()
        context.metadata.update(
            {
                "source": "upload",
                "filename": uploaded.name,
                "raw_bytes": raw_bytes,
            }
        )
        context.bump_version()
        reset_agent_state()
        st.success(f"Arquivo carregado: {uploaded.name} • {df.shape[0]} linhas × {df.shape[1]} colunas")
    except Exception as e:
        st.error(f"Falha ao ler CSV: {e}")
        st.stop()

# If data loaded, show EDA
if st.session_state.df is not None:
    df = st.session_state.df

    signature = dataframe_signature(df)
    if st.session_state.analysis_signature != signature:
        st.session_state.analysis_signature = signature
        try:
            st.session_state.analysis_results = compute_advanced_analysis(df)
        except Exception as exc:
            st.session_state.analysis_results = {"error": str(exc)}
    analysis = st.session_state.analysis_results or {}

    with col_left:
        st.subheader("📦 Visão Geral")
        eda = eda_overview(df)
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Linhas", eda["n_rows"])
        m2.metric("Colunas", eda["n_cols"])
        m3.metric("Numéricas", len(eda["numeric_cols"]))
        m4.metric("Não numéricas", len(eda["non_numeric_cols"]))
        st.dataframe(df.head(20))

        st.expander("Tipos de dados").write(pd.DataFrame({"coluna": df.columns, "dtype": [readable_dtype(df[c].dtype) for c in df.columns]}))
        st.expander("Estatísticas").write(eda["describe"])
        st.expander("Valores ausentes (%)").write((eda["missing"] * 100).round(2))
        if not eda["corr"].empty:
            st.subheader("Correlação (numéricas)")
            fig_corr = px.imshow(eda["corr"], text_auto=True, aspect="auto", color_continuous_scale="RdBu", zmin=-1, zmax=1)
            st.plotly_chart(fig_corr, use_container_width=True)
            st.session_state.charts.append(("Correlação", fig_corr))

        st.subheader("🔎 Diagnósticos automatizados")
        if isinstance(analysis, dict) and analysis.get("error"):
            st.error(f"Falha ao gerar diagnósticos: {analysis['error']}")
        else:
            tab_patterns, tab_freq, tab_outliers, tab_clusters, tab_rel = st.tabs(
                ["Padrões/Tendências", "Frequências", "Outliers", "Clusters", "Relações"]
            )

            with tab_patterns:
                temporal = (analysis or {}).get("temporal", {})
                cols = temporal.get("columns", [])
                if cols:
                    st.write("Colunas temporais detectadas:", ", ".join(cols))
                    if temporal.get("insights"):
                        for insight in temporal["insights"]:
                            st.markdown(f"- {insight}")
                    else:
                        st.write("Nenhum padrão monotônico evidente — revise gráficos de linha para confirmar.")
                else:
                    st.write("Nenhuma coluna temporal detectada ou padrões relevantes.")

            with tab_freq:
                freq_df = (analysis or {}).get("frequencies")
                if isinstance(freq_df, pd.DataFrame) and not freq_df.empty:
                    st.dataframe(freq_df)
                else:
                    st.write("Distribuições uniformes ou sem dados suficientes para frequência.")

            with tab_outliers:
                out_df = (analysis or {}).get("outliers")
                if isinstance(out_df, pd.DataFrame) and not out_df.empty:
                    st.dataframe(out_df)
                    st.markdown("**Sugestões de tratamento**")
                    for tip in OUTLIER_SUGGESTIONS:
                        st.markdown(f"- {tip}")
                else:
                    st.write("Nenhum outlier relevante encontrado pelas regras de IQR.")

            with tab_clusters:
                clusters = (analysis or {}).get("clusters", {})
                status = clusters.get("status")
                if status == "ok":
                    st.success(
                        f"Clusterização sugere {clusters['k']} grupos (silhouette≈{clusters['silhouette']})."
                    )
                    st.write("Tamanho dos clusters:")
                    st.json(clusters.get("cluster_sizes", {}))
                elif status == "missing_dependency":
                    st.warning("Instale scikit-learn para habilitar a detecção automática de clusters.")
                elif status == "not_enough_features":
                    st.info("É necessário pelo menos duas variáveis numéricas para detectar clusters.")
                elif status == "not_enough_rows":
                    st.info("Amostra insuficiente (<50 linhas) para clusterizar com confiabilidade.")
                else:
                    st.write("Nenhuma estrutura de clusters evidente detectada.")

            with tab_rel:
                rel = (analysis or {}).get("relationships", {})
                correlations = rel.get("correlations", [])
                categorical = rel.get("categorical", [])
                if correlations:
                    st.markdown("**Correlação numérica destacada**")
                    st.dataframe(pd.DataFrame(correlations))
                else:
                    st.write("Nenhuma correlação numérica relevante (|rho| ≥ 0,2).")
                if categorical:
                    st.markdown("**Influência de categóricas sobre numéricas**")
                    st.dataframe(pd.DataFrame(categorical))
                else:
                    st.write("Nenhuma categoria com impacto médio significativo detectado.")

        # Quick helpers for creditcard dataset if present
        if {"Amount", "Class"}.issubset(df.columns):
            st.subheader("Atalhos - Fraude em Cartão (se aplicável)")
            fig_amt = px.histogram(df, x="Amount", nbins=60, color="Class", barmode="overlay")
            st.plotly_chart(fig_amt, use_container_width=True)
            st.session_state.charts.append(("Distribuição de Amount por Class", fig_amt))

            fraud_rate = (df["Class"].mean() * 100.0)
            st.info(f"Taxa de fraude (Class=1): {fraud_rate:.4f}%")

            if "Time" in df.columns:
                fig_time = px.scatter(df.sample(min(len(df), 5000), random_state=42), x="Time", y="Amount", color="Class", opacity=0.6)
                st.plotly_chart(fig_time, use_container_width=True)
                st.session_state.charts.append(("Time vs Amount (amostra)", fig_time))

    with col_right:
        st.subheader("📊 Construtor de Gráficos")
    kind = st.selectbox("Tipo", ["Histogram", "Box", "Scatter", "Line", "Bar", "Correlation heatmap"])
    x = st.selectbox("X", [None] + df.columns.tolist())
    y = st.selectbox("Y", [None] + df.columns.tolist())
    color = st.selectbox("Cor (categoria)", [None] + df.columns.tolist())
    bins = st.number_input("Bins (hist)", min_value=5, max_value=200, value=30)
    aggfunc = st.selectbox("Agregação (Bar)", [None, "sum", "mean", "count", "median"]) if kind == "Bar" else None

    if st.button("Renderizar gráfico"):
        spec = ChartSpec(kind=kind, x=x, y=y, color=color, bins=bins, aggfunc=aggfunc)
        fig = render_chart(df, spec)
        if fig is not None:
            st.session_state.charts.append((f"{kind} ({x} vs {y})", fig))

    st.subheader("🧠 Pergunte ao agente sobre os dados")
    q = st.text_input("Pergunta (ex.: 'Qual a média de Amount por Class?')")
    ask_clicked = st.button("Perguntar")
    if ask_clicked:
        if not q:
            st.warning("Descreva a pergunta que deseja fazer ao agente.")
        elif not os.environ.get("OPENAI_API_KEY"):
            st.error("Defina OPENAI_API_KEY na barra lateral para usar o agente.")
        elif not allow_code:
            st.error("Para usar o agente com cálculos, marque o toggle 'Permitir execução de código...'.")
        else:
            needs_refresh = (
                st.session_state.orchestrator is None
                or st.session_state.get("orchestrator_verbose") != show_cot
                or st.session_state.get("orchestrator_model") != os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
            )
            if needs_refresh:
                llm = ChatOpenAI(
                    model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
                    temperature=get_openai_temperature(),
                )
                st.session_state.orchestrator = DomainOrchestrator(
                    context=st.session_state.agent_context,
                    llm=llm,
                    memory=st.session_state.agent_memory,
                    verbose=show_cot,
                )
                st.session_state["orchestrator_verbose"] = show_cot
                st.session_state["orchestrator_model"] = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

            analysis_context = []
            if isinstance(analysis, dict) and not analysis.get("error"):
                num_cols = analysis.get("numeric_cols", [])[:8]
                cat_cols = analysis.get("non_numeric_cols", [])[:6]
                if num_cols:
                    analysis_context.append("Colunas numéricas principais: " + ", ".join(num_cols))
                if cat_cols:
                    analysis_context.append("Colunas categóricas principais: " + ", ".join(cat_cols))
                temporal_tips = (analysis.get("temporal", {}) or {}).get("insights", [])
                for insight in temporal_tips[:2]:
                    analysis_context.append("Insight temporal: " + insight)
                rel_tips = (analysis.get("relationships", {}) or {}).get("correlations", [])
                for item in rel_tips[:2]:
                    analysis_context.append(
                        f"Correlação relevante: {item['variaveis']} (|rho|≈{item['correlacao']})"
                    )

            context_block = "\n".join(f"- {line}" for line in analysis_context) if analysis_context else "- Sem resumo adicional disponível."
            context_message = "Contexto rápido:\n" + context_block
            with st.spinner("Roteando entre os agentes de domínio..."):
                try:
                    orchestrator_result = st.session_state.orchestrator.answer(q, context_message)
                except Exception as exc:
                    st.error(f"Falha ao executar agentes: {exc}")
                    st.session_state.last_intermediate_steps = []
                    orchestrator_result = None

            if orchestrator_result is None:
                st.warning("Os agentes não conseguiram processar a pergunta. Tente reformular ou verificar os dados.")
            else:
                st.caption(f"Domínio acionado: **{orchestrator_result.domain.upper()}**")
                answer_text = orchestrator_result.output
                st.session_state.last_intermediate_steps = orchestrator_result.intermediate_steps
                cleaned_answer, chart_dict = extract_chart_spec_from_text(answer_text)
                st.write(cleaned_answer)

                qa_record = {"q": q, "a": cleaned_answer, "domain": orchestrator_result.domain}
                if chart_dict:
                    qa_record["chart_spec"] = chart_dict
                st.session_state.qa.append(qa_record)

                if chart_dict:
                    spec_obj = normalize_chart_spec(chart_dict)
                    chart_title = chart_dict.get("title") if isinstance(chart_dict, dict) else None
                    if spec_obj is None:
                        st.warning("O agente sinalizou um gráfico, mas o CHART_SPEC está inválido.")
                    else:
                        st.markdown("**Gráfico gerado pelo agente**")
                        fig = render_chart(df, spec_obj)
                        if fig is not None:
                            title = chart_title or f"{spec_obj.kind} ({spec_obj.x} vs {spec_obj.y})"
                            st.session_state.charts.append((title, fig))
                            st.session_state.agent_recent_charts.append(title)

            if show_cot and st.session_state.last_intermediate_steps:
                formatted_steps = format_intermediate_steps(st.session_state.last_intermediate_steps)
                with st.expander("Cadeia de raciocínio (CoT)"):
                    for item in formatted_steps:
                        st.write(f"Passo {item['passo']} — ferramenta: {item['acao']}")
                        st.code(item["detalhes"])
                        st.write(f"Observação: {item['observacao']}")

    if st.button("Gerar conclusões do agente"):
        if not os.environ.get("OPENAI_API_KEY"):
            st.error("Defina OPENAI_API_KEY na barra lateral.")
        else:
            llm = ChatOpenAI(
                model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
                temperature=get_openai_temperature(),
            )
            eda_summary = eda_overview(df)
            prompt = (
                "Você é um analista de dados. Com base no resumo EDA abaixo, descreva insights, padrões, possíveis outliers e sugestões de próximos passos.\n\n"
                f"Resumo rápido:\n"
                f"linhas={eda_summary['n_rows']}, colunas={eda_summary['n_cols']}, numéricas={len(eda_summary['numeric_cols'])}\n"
                f"topo describe={eda_summary['describe'].head(10).to_string()}\n"
            )
            try:
                resp = llm.invoke(prompt)
                st.session_state.conclusions = resp.content
            except Exception as e:
                st.session_state.conclusions = f"Erro ao concluir: {e}"
        if st.session_state.conclusions:
            st.success("Conclusões geradas!")
            st.write(st.session_state.conclusions)

    st.subheader("📝 Gerar PDF do relatório")
    pdf_name = st.text_input("Nome do arquivo", value="Agentes Autônomos - Relatório da Atividade Extra.pdf")
    if st.button("Gerar PDF"):
        img_paths = []
        out_dir = "_export"
        os.makedirs(out_dir, exist_ok=True)
        for i, (title, fig) in enumerate(st.session_state.charts[:6], 1):
            path = os.path.join(out_dir, f"fig_{i}.png")
            try:
                save_plotly_png(fig, path)
                img_paths.append(path)
            except Exception as e:
                st.warning(f"Falhou exportar gráfico '{title}': {e}")

        framework = "LangChain (agentes/LLM) + Streamlit (UI) + Plotly (gráficos)."
        structure = (
            "O app carrega CSV, gera EDA básico, permite construir gráficos, "
            "e usa um agente LangChain para responder perguntas sobre o DataFrame. "
            "O histórico (Q&A) e os gráficos selecionados são consolidados em um PDF."
        )
        qa_copy = st.session_state.qa[-4:] if st.session_state.qa else []
        conclusions = st.session_state.conclusions or "(Conclua pelo botão 'Gerar conclusões do agente')."

        try:
            generate_pdf(pdf_name, framework, structure, qa_copy, conclusions, img_paths)
            with open(pdf_name, "rb") as f:
                st.download_button("Baixar PDF", data=f, file_name=pdf_name, mime="application/pdf")
        except Exception as e:
            st.error(f"Falhou gerar PDF: {e}")


else:
    st.info("Envie um arquivo CSV para começar.")
