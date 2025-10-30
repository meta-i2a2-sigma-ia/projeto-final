"""Tools focused on validation of fiscal documents."""

from __future__ import annotations

from typing import Dict, List, Optional

try:
    from langchain.tools import Tool
except ImportError:  # langchain >= 0.2 split_core
    from langchain_core.tools import Tool

from fiscal.domain import ValidationResult, run_core_validations, summarize_issues
from .context import AgentDataContext

_CORRECTIONS: Dict[str, str] = {
    "duplicate_items": "Verifique se o ERP exportou o mesmo item mais de uma vez. Ajuste a integração para garantir unicidade por chave de acesso + número do item.",
    "cfop_destino": "Revise o cadastro do CFOP em função do destino da operação. Operações interestaduais devem usar CFOP iniciado em 6 e operações internas em 5.",
    "ncm_invalido": "Consulte a tabela TIPI/NCM vigente (portal da Receita) e corrija os códigos para oito dígitos.",
    "cnpj_invalido": "Ajuste os cadastros de emitentes/destinatários garantindo 14 dígitos numéricos (ou 11 para CPF).",
    "valor_item_divergente": "Recalcule quantidade × valor unitário e atualize o valor total do item na nota ou no pedido de compra.",
    "valor_nota_divergente": "Confirme se houve descontos/acréscimos na nota e alinhe o total com a soma de itens.",
    "icms_incoerente": "Recalcule o ICMS usando base e alíquota corretas; atualize o XML ou parametrização fiscal.",
}


def build_validation_tools(
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

    def resumo(_: str = "") -> str:
        try:
            results = get_results()
        except ValueError as exc:
            return str(exc)
        summary = summarize_issues(results)
        if summary.empty:
            return "Nenhuma inconsistência relevante foi encontrada nas validações automáticas."
        return summary.to_markdown(index=False)

    def detalhes(rule_id: str) -> str:
        try:
            results = get_results()
        except ValueError as exc:
            return str(exc)
        index = {res.identifier: res for res in results}
        rule = index.get(rule_id.strip())
        if rule is None:
            available = ", ".join(index.keys()) or "nenhuma"
            return f"Regra '{rule_id}' não foi encontrada. Regras disponíveis: {available}."
        if rule.details.empty:
            return f"A regra {rule.title} não apresentou ocorrências."
        sample = rule.details.head(30)
        explanation = rule.conclusion
        body = sample.to_markdown(index=False)
        return f"{rule.title}\nResumo: {explanation}\nOcorrências (máx. 30 linhas):\n{body}"

    def sugerir_correcoes(rule_id: str) -> str:
        try:
            results = get_results()
        except ValueError as exc:
            return str(exc)
        index = {res.identifier: res for res in results}
        rule = index.get(rule_id.strip())
        tip = _CORRECTIONS.get(rule_id.strip(), "Documente o caso para revisão manual da equipe fiscal.")
        if rule is None:
            return tip
        return f"Para '{rule.title}': {tip}"

    return [
        Tool.from_function(
            func=resumo,
            name="listar_inconsistencias",
            description="Lista todas as inconsistências fiscais detectadas automaticamente (formato markdown).",
        ),
        Tool.from_function(
            func=detalhes,
            name="detalhar_regra",
            description="Recebe o identificador de uma regra (ex.: 'cfop_destino') e retorna amostras das notas/vendas afetadas.",
        ),
        Tool.from_function(
            func=sugerir_correcoes,
            name="sugerir_correcao",
            description="Informa ações recomendadas para endereçar uma regra específica (use o mesmo identificador da regra).",
        ),
    ]
