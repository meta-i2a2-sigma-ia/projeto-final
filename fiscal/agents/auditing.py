"""Tools that focus on auditing outputs: ranking de riscos, relatórios, etc."""

from __future__ import annotations

from typing import List, Optional
try:
    from langchain.tools import Tool
except ImportError:
    from langchain_core.tools import Tool

from fiscal.domain import ValidationResult, offenders_by, run_core_validations, summarize_issues
from .context import AgentDataContext
from .helpers import build_maior_nota_tool


def build_auditing_tools(
    ctx: AgentDataContext,
    cached_results: Optional[List[ValidationResult]] = None,
) -> List[Tool]:
    def get_results() -> List[ValidationResult]:
        meta_results = ctx.metadata.get("validation_results")
        if meta_results is not None:
            return meta_results
        if cached_results is not None:
            ctx.metadata["validation_results"] = cached_results
            return cached_results
        df = ctx.require_dataframe()
        results = run_core_validations(df)
        ctx.metadata["validation_results"] = results
        return results

    def resumo_riscos(_: str = "") -> str:
        try:
            results = get_results()
        except ValueError as exc:
            return str(exc)
        summary = summarize_issues(results)
        if summary.empty:
            return "Sem riscos significativos identificados na auditoria automatizada."
        summary["prioridade"] = summary["severidade"].map({"alta": "Alta", "media": "Média", "baixa": "Baixa"})
        ordered = summary.sort_values(["severidade", "ocorrencias"], ascending=[True, False])
        return ordered.to_markdown(index=False)

    def maiores_agressores(_: str = "") -> str:
        try:
            results = get_results()
        except ValueError as exc:
            return str(exc)
        emitentes = offenders_by(results, "razao_emitente")
        destinatarios = offenders_by(results, "razao_destinatario")
        parts = []
        if not emitentes.empty:
            parts.append("### Emitentes com mais apontamentos\n" + emitentes.head(10).to_markdown(index=False))
        if not destinatarios.empty:
            parts.append("### Destinatários com mais apontamentos\n" + destinatarios.head(10).to_markdown(index=False))
        return "\n\n".join(parts) if parts else "Não foi possível identificar recorrência por emitente/destinatário."

    def gerar_relatorio(_: str = "") -> str:
        try:
            results = get_results()
        except ValueError as exc:
            return str(exc)
        blocks = [
            "RELATÓRIO DE AUDITORIA FISCAL",
            "- Escopo: notas fiscais eletrônicas carregadas no módulo fiscal.",
            "- Objetivo: sinalizar inconsistências críticas para correção antes da escrituração.",
        ]
        summary = summarize_issues(results)
        if summary.empty:
            blocks.append("Nenhuma inconsistência relevante foi encontrada.")
        else:
            blocks.append("Síntese das regras violadas:")
            blocks.append(summary.to_markdown(index=False))
        emitentes = offenders_by(results, "razao_emitente")
        if not emitentes.empty:
            blocks.append("Emitentes com maior reincidência:")
            blocks.append(emitentes.head(5).to_markdown(index=False))
        destinatarios = offenders_by(results, "razao_destinatario")
        if not destinatarios.empty:
            blocks.append("Destinatários mais impactados:")
            blocks.append(destinatarios.head(5).to_markdown(index=False))
        blocks.append("Recomenda-se repassar a lista para os responsáveis e atualizar cadastros/parametrizações fiscais.")
        return "\n\n".join(blocks)

    return [
        Tool.from_function(
            func=resumo_riscos,
            name="resumo_riscos",
            description="Resumo das regras de auditoria violadas com severidade e quantidade de ocorrências.",
        ),
        Tool.from_function(
            func=maiores_agressores,
            name="maiores_agressores",
            description="Mostra os emitentes e destinatários com maior número de apontamentos fiscais.",
        ),
        Tool.from_function(
            func=gerar_relatorio,
            name="relatorio_auditoria",
            description="Gera um relatório textual consolidado com as principais inconsistências e recomendações.",
        ),
        build_maior_nota_tool(ctx, name="maior_nota"),
    ]
