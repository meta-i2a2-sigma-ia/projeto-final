"""Semantic fallback tool that uses the LLM to reason sobre o DataFrame."""

from __future__ import annotations

from typing import Optional

import pandas as pd
from langchain.tools import StructuredTool
from langchain_core.language_models import BaseLanguageModel
from langchain_core.pydantic_v1 import BaseModel, Field

from .context import AgentDataContext


class SemanticQueryArgs(BaseModel):
    question: str = Field(..., description="Pergunta em linguagem natural sobre os dados carregados.")
    max_rows: Optional[int] = Field(
        default=15,
        ge=5,
        le=50,
        description="Quantidade máxima de linhas de amostra a serem usadas no contexto."
    )


def build_semantic_tool(ctx: AgentDataContext, llm: BaseLanguageModel) -> StructuredTool:
    def semantic_query(args: SemanticQueryArgs) -> str:
        try:
            df = ctx.require_dataframe()
        except ValueError as exc:
            return str(exc)

        sample = df.head(args.max_rows)
        summary_parts = []
        summary_parts.append(f"Linhas totais: {len(df)}")
        summary_parts.append(f"Colunas: {', '.join(df.columns.tolist())}")
        numeric = df.select_dtypes(include="number")
        if not numeric.empty:
            desc = numeric.describe().round(3).to_dict()
            summary_parts.append("Resumo numérico: " + str(desc))
        if df.index.name:
            summary_parts.append(f"Index name: {df.index.name}")

        sample_markdown = sample.to_markdown(index=False)
        prompt = (
            "Você é um analista fiscal respondendo perguntas sobre um DataFrame."
            " Use os dados abaixo para responder de forma direta, mencionando valores numéricos quando relevantes."
            " Se a resposta exigir cálculo, explique resumidamente como chegou ao valor."
            " Caso as informações não estejam presentes, informe claramente o que falta.\n\n"
            f"Pergunta: {args.question}\n"
            "Contexto (resumo):\n"
            f"{chr(10).join(summary_parts)}\n\n"
            "Amostra das primeiras linhas (markdown):\n"
            f"{sample_markdown}\n"
            "Resposta em português do Brasil, objetiva e citando valores numéricos."
        )
        try:
            response = llm.invoke(prompt)
        except Exception as exc:
            return f"Falha ao executar a análise semântica: {exc}"
        return response.content if hasattr(response, "content") else str(response)

    return StructuredTool.from_function(
        func=semantic_query,
        name="analise_semantica",
        description="Responde perguntas abertas sobre o dataset usando raciocínio em linguagem natural.",
    )
