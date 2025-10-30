"""Descriptive statistics agent tools."""

from __future__ import annotations

from typing import List

import pandas as pd
from langchain.tools import StructuredTool, Tool

from domain import eda_overview, readable_dtype
from .context import AgentDataContext


def build_descriptive_tools(ctx: AgentDataContext) -> List[StructuredTool]:
    """Return tools focused on descriptive analytics for the dataframe."""

    def dataset_profile_text(df: pd.DataFrame) -> str:
        overview = eda_overview(df)
        lines = [
            "Resumo do conjunto de dados:",
            f"- Linhas: {overview['n_rows']}",
            f"- Colunas: {overview['n_cols']}",
            f"- Numéricas: {len(overview['numeric_cols'])}",
            f"- Não numéricas: {len(overview['non_numeric_cols'])}",
        ]

        dtype_rows = [
            f"  • {col}: {readable_dtype(df[col].dtype)}" for col in df.columns
        ]
        lines.append("Tipos por coluna:\n" + "\n".join(dtype_rows))

        desc = overview["describe"].fillna("-")
        desc = desc[[c for c in desc.columns if c in {"count", "mean", "std", "min", "25%", "50%", "75%", "max"}]]
        try:
            lines.append("Estatísticas principais:\n" + desc.to_string())
        except Exception:
            lines.append("Estatísticas principais indisponíveis.")

        missing = (overview["missing"] * 100).round(2)
        if not missing.empty:
            lines.append("Percentual de valores ausentes:\n" + missing.to_string())

        return "\n".join(lines)

    def dataset_profile_tool(_: str = "") -> str:
        try:
            df = ctx.require_dataframe()
        except ValueError as exc:
            return str(exc)
        return dataset_profile_text(df)

    def column_summary(column: str) -> str:
        try:
            df = ctx.require_dataframe()
        except ValueError as exc:
            return str(exc)
        if column not in df.columns:
            return f"Coluna '{column}' não encontrada."
        series = df[column]
        info = [f"Resumo da coluna '{column}':", f"- Tipo: {readable_dtype(series.dtype)}"]
        info.append(f"- Valores únicos: {series.nunique(dropna=True)}")
        info.append(f"- Valores ausentes: {series.isna().sum()} ({series.isna().mean():.2%})")
        if pd.api.types.is_numeric_dtype(series):
            stats = series.describe()
            info.extend(
                [
                    f"- Média: {stats.get('mean', float('nan')):.4g}",
                    f"- Mediana: {stats.get('50%', float('nan')):.4g}",
                    f"- Desvio padrão: {stats.get('std', float('nan')):.4g}",
                    f"- Mínimo: {stats.get('min', float('nan')):.4g}",
                    f"- Máximo: {stats.get('max', float('nan')):.4g}",
                ]
            )
        else:
            top = series.value_counts(dropna=False).head(5)
            info.append("- Valores mais frequentes:\n" + top.to_string())
        return "\n".join(info)

    tools = [
        Tool.from_function(
            func=dataset_profile_tool,
            name="dataset_profile",
            description="Retorna um resumo geral do dataset carregado, com tipos, contagens e estatísticas centrais.",
        ),
        StructuredTool.from_function(
            func=column_summary,
            name="column_summary",
            description="Recebe o nome de uma coluna e devolve estatísticas detalhadas sobre ela.",
        ),
    ]
    return tools
