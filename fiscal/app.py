"""
Streamlit + LangChain Fiscal Agent
=================================

Este módulo oferece funcionalidades equivalentes ao EDA, mas orientadas para documentos fiscais brasileiros.

Recursos principais
-------------------
- Upload de arquivos CSV/XLSX/XML/ZIP de NF-e ou leitura via Supabase.
- Visão geral com métricas fiscais (total de notas, valores, CFOP/NCM).
- Validações automáticas (CFOP x destino, NCM, ICMS, totais etc.).
- Ranking dos maiores ofensores e relatório de auditoria.
- Construtor de gráficos e agente LangChain especializado em validação/auditoria/integracão.
- Geração de relatório PDF consolidando análises e respostas do agente.
"""

from __future__ import annotations

import os
import sys
import textwrap
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from fpdf import FPDF
from langchain_openai import ChatOpenAI

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# Fiscal domain imports
from fiscal.domain import (
    LoadedData,
    fiscal_overview,
    load_fiscal_dataframe,
    load_supabase_table,
    offenders_by,
    run_core_validations,
    summarize_issues,
)
from fiscal.agents import FiscalOrchestrator

# Reuse generic helpers from the EDA domain
if str(BASE_DIR.parent / "eda") not in sys.path:
    sys.path.insert(0, str(BASE_DIR.parent / "eda"))

from eda.domain import (  # type: ignore
    ChartSpec,
    coerce_numeric,
    extract_chart_spec_from_text,
    normalize_chart_spec,
    readable_dtype,
)


# -----------------------------
# General helpers
# -----------------------------

def get_secret_or_env(name: str, default: str = "") -> str:
    value = os.environ.get(name)
    if value not in (None, ""):
        return value
    try:
        return st.secrets[name]
    except Exception:
        return default


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
            st.warning("Sem colunas numéricas suficientes para calcular correlação.")
            return None
        corr = numeric_df.corr()
        fig = px.imshow(corr, text_auto=True, aspect="auto", color_continuous_scale="RdBu", zmin=-1, zmax=1)
    else:
        st.warning("Tipo de gráfico não suportado.")
        return None
    st.plotly_chart(fig, use_container_width=True)
    return fig


def save_plotly_png(fig, path: str):
    fig.write_image(path, scale=2)


def generate_pdf(path: str, overview: Dict[str, Any], summary_md: str, qa: List[Dict[str, str]], conclusions: str, image_paths: List[str]):
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
    add_title("Relatório Fiscal Automatizado")

    add_subtitle("1. Indicadores principais")
    resumo = (
        f"Notas analisadas: {overview['total_notas']}\n"
        f"Itens: {overview['total_itens']}\n"
        f"Valor total (notas): R$ {overview['valor_total_notas']:.2f}\n"
        f"Valor total (itens): R$ {overview['valor_total_itens']:.2f}"
    )
    add_paragraph(resumo)

    add_subtitle("2. Resumo das validações")
    add_paragraph(summary_md)

    add_subtitle("3. Perguntas e respostas do agente")
    for i, item in enumerate(qa, 1):
        add_paragraph(f"P{i}: {item['q']}")
        add_paragraph(f"R{i}: {item['a']}")
        pdf.ln(2)

    if image_paths:
        add_subtitle("4. Gráficos")
        for p in image_paths:
            try:
                pdf.add_page()
                pdf.image(p, w=180)
            except Exception:
                pass

    pdf.add_page()
    add_subtitle("5. Conclusões do agente")
    add_paragraph(conclusions)
    pdf.output(path)


def format_intermediate_steps(steps: List[Tuple[Any, Any]]) -> List[Dict[str, str]]:
    formatted: List[Dict[str, str]] = []
    for idx, item in enumerate(steps, start=1):
        action, observation = item if isinstance(item, tuple) and len(item) == 2 else (item, "")
        action_name = getattr(action, "tool", "pensamento")
        action_log = getattr(action, "log", str(action))
        formatted.append(
            {
                "passo": idx,
                "acao": action_name,
                "detalhes": action_log,
                "observacao": str(observation),
            }
        )
    return formatted


def reset_session_state():
    st.session_state.orchestrator = None
    st.session_state["orchestrator_model"] = None
    st.session_state["orchestrator_verbose"] = None
    st.session_state.agent_memory = None
    st.session_state.qa = []
    st.session_state.last_intermediate_steps = []
    st.session_state.charts = []
    st.session_state.conclusions = ""
    st.session_state.validation_results = None
    st.session_state.loaded_metadata = {}


# -----------------------------
# Streamlit layout
# -----------------------------
st.set_page_config(page_title="Fiscal Agent - NF-e + LangChain", layout="wide")
st.title("🧾 Fiscal Agent - Auditoria Automática de NF-e")

with st.sidebar:
    st.header("Configuração")
    api_key = st.text_input("OPENAI_API_KEY", type="password", value=get_secret_or_env("OPENAI_API_KEY", ""))
    if api_key:
        os.environ["OPENAI_API_KEY"] = api_key
    model = st.text_input("Modelo (OpenAI)", value=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"))
    if model:
        os.environ["OPENAI_MODEL"] = model

    st.markdown("---")
    source = st.radio("Fonte de dados", ["Supabase", "Arquivo"], index=1, horizontal=True)
    df_loader_trigger = False
    supabase_params: Dict[str, Any] = {}
    uploaded = None

    if source == "Supabase":
        url_default = get_secret_or_env("SUPABASE_URL", "")
        key_default = get_secret_or_env("SUPABASE_SERVICE_ROLE_KEY", "")
        st.text_input("SUPABASE_URL", value=url_default, key="sb_url")
        st.text_input("SUPABASE_SERVICE_ROLE_KEY", type="password", value=key_default, key="sb_key")
        schema = st.text_input("Schema", value=os.environ.get("PG_SCHEMA", "public"))
        table = st.text_input("Tabela", value=os.environ.get("DEFAULT_TABLE", "fiscal_docs"))
        limit = st.number_input(
            "Limite de linhas",
            min_value=100,
            max_value=1_000_000,
            value=20000,
            step=1000,
        )
        if st.button("Carregar dados"):
            os.environ["SUPABASE_URL"] = st.session_state.sb_url
            os.environ["SUPABASE_SERVICE_ROLE_KEY"] = st.session_state.sb_key
            df_loader_trigger = True
            supabase_params.update(dict(schema=schema.strip() or "public", table=table.strip(), limit=int(limit)))
    else:
        st.caption("Aceitamos CSV, XLSX, XML ou ZIP com XMLs de NF-e.")
        uploaded = st.file_uploader("Arquivo fiscal", type=["csv", "xls", "xlsx", "xml", "zip", "json"], accept_multiple_files=False)

    st.markdown("---")
    st.checkbox(
        "Exibir cadeia de raciocínio (CoT)",
        key="show_cot_toggle",
        value=st.session_state.get("show_cot_toggle", False),
        help="Mostra as etapas executadas pelo agente (útil para auditoria interna).",
    )

show_cot = st.session_state.get("show_cot_toggle", False)

if "df" not in st.session_state:
    st.session_state.df = None
if "agent_memory" not in st.session_state:
    st.session_state.agent_memory = None
if "qa" not in st.session_state:
    st.session_state.qa = []
if "charts" not in st.session_state:
    st.session_state.charts = []
if "last_intermediate_steps" not in st.session_state:
    st.session_state.last_intermediate_steps = []
if "conclusions" not in st.session_state:
    st.session_state.conclusions = ""

col_main, col_side = st.columns([2.3, 1])

# -----------------------------
# Data loading
# -----------------------------
if df_loader_trigger:
    try:
        df = load_supabase_table(**supabase_params)
        if df.empty:
            st.warning("Tabela vazia ou não encontrada.")
        df = coerce_numeric(df)
        st.session_state.df = df
        st.session_state.loaded_metadata = {"source": "supabase", **supabase_params}
        st.success(
            f"Tabela carregada: {supabase_params['schema']}.{supabase_params['table']} • {df.shape[0]} linhas × {df.shape[1]} colunas"
        )
        reset_session_state()
    except Exception as exc:
        st.error(f"Erro ao carregar do Supabase: {exc}")
        st.stop()
elif uploaded is not None:
    try:
        raw_bytes = uploaded.read()
        loaded = load_fiscal_dataframe(file_bytes=raw_bytes, filename=uploaded.name)
        df = coerce_numeric(loaded.dataframe)
        st.session_state.df = df
        st.session_state.loaded_metadata = {"source": loaded.source, **loaded.metadata}
        reset_session_state()
        st.success(f"Arquivo carregado: {uploaded.name} • {df.shape[0]} linhas × {df.shape[1]} colunas")
    except Exception as exc:
        st.error(f"Falha ao processar arquivo: {exc}")
        st.stop()

# -----------------------------
# Main view
# -----------------------------
if st.session_state.df is not None:
    df = st.session_state.df

    with col_main:
        st.subheader("📦 Visão Geral Fiscal")
        try:
            overview = fiscal_overview(df)
        except Exception as exc:
            st.error(f"Não foi possível calcular a visão geral: {exc}")
            overview = {}

        if overview:
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Notas", overview.get("total_notas", len(df)))
            m2.metric("Itens", overview.get("total_itens", len(df)))
            m3.metric("Emitentes", overview.get("total_emitentes", 0))
            m4.metric("Destinatários", overview.get("total_destinatarios", 0))
            m5, m6 = st.columns(2)
            m5.metric("Valor total (notas)", f"R$ {overview.get('valor_total_notas', 0):,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
            m6.metric("Valor total (itens)", f"R$ {overview.get('valor_total_itens', 0):,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))

            timeline = overview.get("timeline")
            if isinstance(timeline, pd.DataFrame) and not timeline.empty:
                st.plotly_chart(px.bar(timeline, x="competencia", y="valor", title="Valor mensal das notas"), use_container_width=True)

            top_cfop = overview.get("top_cfop")
            top_ncm = overview.get("top_ncm")
            if isinstance(top_cfop, pd.DataFrame) and not top_cfop.empty:
                st.write("Top CFOP por valor")
                st.dataframe(top_cfop)
            if isinstance(top_ncm, pd.DataFrame) and not top_ncm.empty:
                st.write("Top NCM por valor")
                st.dataframe(top_ncm)

        st.dataframe(df.head(30))
        st.expander("Tipos de dados").write(
            pd.DataFrame({"coluna": df.columns, "dtype": [readable_dtype(df[c].dtype) for c in df.columns]})
        )

        # Validações
        st.subheader("✅ Validações Automáticas")
        if st.session_state.validation_results is None:
            try:
                st.session_state.validation_results = run_core_validations(df)
            except Exception as exc:
                st.error(f"Falha ao executar validações: {exc}")
                st.session_state.validation_results = []
        results = st.session_state.validation_results or []
        summary_df = summarize_issues(results)
        if summary_df.empty:
            st.success("Nenhuma inconsistência relevante identificada.")
        else:
            st.dataframe(summary_df)
            for res in results:
                with st.expander(f"{res.title} ({res.severity})"):
                    st.write(res.conclusion)
                    st.dataframe(res.details)

        st.subheader("🚨 Maiores agressores")
        if results:
            offenders_emit = offenders_by(results, "razao_emitente")
            offenders_dest = offenders_by(results, "razao_destinatario")
            if not offenders_emit.empty:
                st.write("Emitentes com mais apontamentos")
                st.dataframe(offenders_emit.head(20))
            if not offenders_dest.empty:
                st.write("Destinatários com mais apontamentos")
                st.dataframe(offenders_dest.head(20))
        else:
            st.write("Carregue validações para gerar o ranking.")

        st.subheader("📊 Construtor de Gráficos")
        numeric_cols = df.select_dtypes(include="number").columns.tolist()
        kind = st.selectbox("Tipo", ["Histogram", "Box", "Scatter", "Line", "Bar", "Correlation heatmap"])
        x = st.selectbox("Eixo X", [None] + df.columns.tolist())
        y = st.selectbox("Eixo Y", [None] + df.columns.tolist())
        color = st.selectbox("Cor", [None] + df.columns.tolist())
        bins = st.number_input("Bins (hist)", min_value=5, max_value=120, value=30)
        aggfunc = st.selectbox("Agregação (Bar)", [None, "sum", "mean", "count", "median"]) if kind == "Bar" else None
        spec = ChartSpec(kind=kind, x=x, y=y, color=color, bins=bins, aggfunc=aggfunc)
        if st.button("Gerar gráfico manual"):
            fig = render_chart(df, spec)
            if fig is not None:
                st.session_state.charts.append((f"{kind} - {x}/{y}", fig))

    with col_side:
        st.subheader("🤖 Agente Fiscal")
        context_message = """
        Você está atuando sobre um conjunto de notas fiscais. Utilize dados estruturados disponíveis e as validações automáticas.
        Quando fizer recomendações, cite CFOP, NCM ou valores específicos quando possível.
        """.strip()
        if st.session_state.orchestrator is None:
            try:
                llm = ChatOpenAI(model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"), temperature=0)
            except Exception as exc:
                st.error(f"Falha ao inicializar LLM: {exc}")
                llm = None
            if llm is not None:
                st.session_state.orchestrator = FiscalOrchestrator(
                    df=df,
                    llm=llm,
                    memory=st.session_state.agent_memory,
                    validation_results=st.session_state.validation_results,
                )

        q = st.text_area("Pergunte ao agente fiscal", max_chars=1200)
        if st.button("Enviar pergunta"):
            if not os.environ.get("OPENAI_API_KEY"):
                st.error("Defina OPENAI_API_KEY na barra lateral.")
            elif not q.strip():
                st.warning("Digite uma pergunta antes de enviar.")
            elif st.session_state.orchestrator is None:
                st.error("Agente não inicializado.")
            else:
                try:
                    orchestrator_result = st.session_state.orchestrator.answer(q, context_message)
                except Exception as exc:
                    st.error(f"Falha ao executar agentes: {exc}")
                    orchestrator_result = None
                if orchestrator_result is None:
                    st.warning("Os agentes não conseguiram processar a pergunta.")
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
                            st.warning("O agente solicitou um CHART_SPEC inválido.")
                        else:
                            st.markdown("**Gráfico sugerido pelo agente**")
                            fig = render_chart(df, spec_obj)
                            if fig is not None:
                                title = chart_title or f"{spec_obj.kind} ({spec_obj.x} vs {spec_obj.y})"
                                st.session_state.charts.append((title, fig))

        if show_cot and st.session_state.last_intermediate_steps:
            formatted_steps = format_intermediate_steps(st.session_state.last_intermediate_steps)
            with st.expander("Cadeia de raciocínio (CoT)"):
                for item in formatted_steps:
                    st.write(f"Passo {item['passo']} — ferramenta: {item['acao']}")
                    st.code(item["detalhes"])
                    st.write(f"Observação: {item['observacao']}")

        st.subheader("🧠 Conclusões automáticas")
        if st.button("Gerar conclusões do agente"):
            if not os.environ.get("OPENAI_API_KEY"):
                st.error("Defina OPENAI_API_KEY na barra lateral.")
            else:
                try:
                    llm = ChatOpenAI(model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"), temperature=0)
                    summary_text = summary_df.to_markdown(index=False) if not summary_df.empty else "Sem inconsistências."
                    prompt = (
                        "Você é um auditor fiscal. Com base no resumo das validações abaixo, elabore conclusões, riscos prioritários e próximos passos.\n\n"
                        f"Resumo das regras:\n{summary_text}\n\n"
                        "Se possível indique notas ou emitentes recorrentes."
                    )
                    resp = llm.invoke(prompt)
                    st.session_state.conclusions = resp.content
                except Exception as exc:
                    st.session_state.conclusions = f"Erro ao concluir: {exc}"
        if st.session_state.conclusions:
            st.write(st.session_state.conclusions)

        st.subheader("📝 Gerar relatório PDF")
        pdf_name = st.text_input("Nome do arquivo", value="relatorio-fiscal.pdf")
        if st.button("Gerar PDF"):
            img_paths: List[str] = []
            out_dir = "_export_fiscal"
            os.makedirs(out_dir, exist_ok=True)
            for i, (title, fig) in enumerate(st.session_state.charts[:6], 1):
                path = os.path.join(out_dir, f"fig_{i}.png")
                try:
                    save_plotly_png(fig, path)
                    img_paths.append(path)
                except Exception as exc:
                    st.warning(f"Falha ao exportar gráfico '{title}': {exc}")
            nota_total_col = "valor_total_nota" if "valor_total_nota" in df.columns else (
                "valor_nota_fiscal" if "valor_nota_fiscal" in df.columns else None
            )
            overview_copy = overview if overview else {
                "total_notas": len(df),
                "total_itens": len(df),
                "valor_total_notas": float(pd.to_numeric(df.get(nota_total_col), errors='coerce').sum()) if nota_total_col else 0.0,
                "valor_total_itens": float(pd.to_numeric(df.get("valor_total_item"), errors='coerce').sum()),
            }
            summary_text = summary_df.to_markdown(index=False) if not summary_df.empty else "Sem inconsistências."
            qa_copy = st.session_state.qa[-4:] if st.session_state.qa else []
            conclusions = st.session_state.conclusions or "(Utilize o botão 'Gerar conclusões do agente'.)"
            try:
                generate_pdf(pdf_name, overview_copy, summary_text, qa_copy, conclusions, img_paths)
                with open(pdf_name, "rb") as handle:
                    st.download_button(
                        "Baixar PDF",
                        data=handle,
                        file_name=pdf_name,
                        mime="application/pdf",
                    )
            except Exception as exc:
                st.error(f"Falha ao gerar PDF: {exc}")
else:
    st.info("Carregue um arquivo fiscal ou conecte-se ao Supabase para iniciar a análise.")
