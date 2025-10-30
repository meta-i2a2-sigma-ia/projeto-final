"""Tools that focus on auditing outputs: ranking de riscos, relatórios, etc."""

from __future__ import annotations

from typing import List, Optional

import pandas as pd
try:
    from langchain.tools import Tool
except ImportError:
    from langchain_core.tools import Tool

from fiscal.domain import ValidationResult, offenders_by, run_core_validations, summarize_issues
from .context import AgentDataContext


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

    def maior_nota(_: str = "") -> str:
        try:
            df = ctx.require_dataframe()
        except ValueError as exc:
            return str(exc)

        valor_cols = [
            "valor_total_nota",
            "valor_nota_fiscal",
            "valor_total",
        ]
        valor_col = next((col for col in valor_cols if col in df.columns), None)
        if valor_col is None:
            return (
                "Não foi possível identificar uma coluna de valor da nota (procure por 'valor_total_nota' ou 'valor_nota_fiscal')."
            )

        notas = df[[valor_col]].copy()
        notas[valor_col] = pd.to_numeric(notas[valor_col], errors="coerce")
        notas = notas.dropna(subset=[valor_col])
        if notas.empty:
            return "Não há valores numéricos válidos para calcular a maior nota."

        chave_col = "chave_acesso" if "chave_acesso" in df.columns else None
        numero_col = "numero" if "numero" in df.columns else None
        emitente_col = "razao_emitente" if "razao_emitente" in df.columns else None

        if chave_col:
            agrupado = df[[chave_col, valor_col]].copy()
            agrupado[valor_col] = pd.to_numeric(agrupado[valor_col], errors="coerce")
            agrupado = agrupado.dropna(subset=[valor_col])
            if agrupado.empty:
                return "Não há valores válidos após consolidar as notas."
            soma = agrupado.groupby(chave_col, as_index=False)[valor_col].sum()
            top_row = soma.loc[soma[valor_col].idxmax()]
            chave = str(top_row[chave_col])
            valor = float(top_row[valor_col])
            ref_rows = df[df[chave_col] == top_row[chave_col]]
        else:
            idx = notas[valor_col].idxmax()
            valor = float(notas.loc[idx, valor_col])
            ref_rows = df.loc[[idx]]
            chave = None

        numero = None
        if numero_col and numero_col in ref_rows.columns:
            numero = ref_rows[numero_col].dropna().astype(str).head(1).tolist()
            numero = numero[0] if numero else None

        emitente = None
        if emitente_col and emitente_col in ref_rows.columns:
            emitente = ref_rows[emitente_col].dropna().astype(str).head(1).tolist()
            emitente = emitente[0] if emitente else None

        partes = [f"Maior nota encontrada: R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")]
        if numero:
            partes.append(f"Número: {numero}")
        if chave:
            partes.append(f"Chave de acesso: {chave}")
        if emitente:
            partes.append(f"Emitente: {emitente}")
        return " | ".join(partes)

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
        Tool.from_function(
            func=maior_nota,
            name="maior_nota",
            description="Retorna a maior nota fiscal (valor total), incluindo número, chave e emitente quando disponíveis.",
        ),
    ]
