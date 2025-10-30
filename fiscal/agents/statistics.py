"""Statistical tools for fiscal datasets."""

from __future__ import annotations

from typing import Iterable, List

import pandas as pd
from langchain.tools import StructuredTool, Tool
from langchain_core.pydantic_v1 import BaseModel, Field

from .context import AgentDataContext


class TotalArgs(BaseModel):
    column: str = Field(..., description="Coluna numérica a somar")


class GroupAggregateArgs(BaseModel):
    group_by: str = Field(..., description="Coluna categórica para agrupar")
    value: str = Field(..., description="Coluna numérica para agregar")
    agg: str = Field(
        default="sum",
        description="Operação: sum, mean, median, min, max, count",
    )
    top: int = Field(default=10, ge=1, le=200, description="Quantidade de linhas a retornar")


class ExtremesArgs(BaseModel):
    column: str = Field(..., description="Coluna numérica a analisar")
    top: int = Field(default=5, ge=1, le=50, description="Quantidade de itens extremos")


def _coerce_numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def build_statistics_tools(ctx: AgentDataContext) -> List[Tool]:
    def totalizador(args: TotalArgs) -> str:
        try:
            df = ctx.require_dataframe()
        except ValueError as exc:
            return str(exc)
        column = args.column
        if column not in df.columns:
            return f"Coluna '{column}' não encontrada."
        values = _coerce_numeric(df[column])
        total = values.sum(skipna=True)
        count = values.count()
        return (
            f"Total de {column}: R$ {total:,.2f} (linhas válidas: {count})"
            .replace(",", "X").replace(".", ",").replace("X", ".")
        )

    def group_aggregate(args: GroupAggregateArgs) -> str:
        try:
            df = ctx.require_dataframe()
        except ValueError as exc:
            return str(exc)
        if args.group_by not in df.columns:
            return f"Coluna de agrupamento '{args.group_by}' não encontrada."
        if args.value not in df.columns:
            return f"Coluna numérica '{args.value}' não encontrada."
        values = _coerce_numeric(df[args.value])
        grouped = df.assign(_value=values).groupby(args.group_by)['_value']
        agg = args.agg.lower().strip()
        allowed: Iterable[str] = {"sum", "mean", "median", "min", "max", "count"}
        if agg not in allowed:
            return f"Operação '{args.agg}' inválida. Use: sum, mean, median, min, max, count."
        if agg == "count":
            result = grouped.count().sort_values(ascending=False)
        else:
            result = getattr(grouped, agg)().sort_values(ascending=False)
        head = result.head(args.top)
        df_result = head.reset_index()
        df_result.columns = [args.group_by, f"{args.value}_{agg}"]
        return df_result.to_markdown(index=False)

    def extremos(args: ExtremesArgs) -> str:
        try:
            df = ctx.require_dataframe()
        except ValueError as exc:
            return str(exc)
        if args.column not in df.columns:
            return f"Coluna '{args.column}' não encontrada."
        values = _coerce_numeric(df[args.column])
        with_values = df.assign(_value=values).dropna(subset=["_value"])
        if with_values.empty:
            return "Não há valores numéricos válidos para analisar."
        min_rows = with_values.nsmallest(args.top, "_value")
        max_rows = with_values.nlargest(args.top, "_value")
        def _format(df_part: pd.DataFrame, titulo: str) -> str:
            display = df_part.drop(columns=["_value"]).copy()
            display[args.column] = df_part["_value"].map(lambda v: f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
            return f"### {titulo}\n" + display.head(args.top).to_markdown(index=False)
        return _format(max_rows, "Maiores valores") + "\n\n" + _format(min_rows, "Menores valores")

    def describe(_: str = "") -> str:
        try:
            df = ctx.require_dataframe()
        except ValueError as exc:
            return str(exc)
        numeric = df.select_dtypes(include="number")
        if numeric.empty:
            return "Não há colunas numéricas para descrever."
        desc = numeric.describe().transpose()
        return desc.to_markdown()

    return [
        StructuredTool.from_function(
            func=totalizador,
            name="totalizar_coluna",
            description="Retorna o somatório de uma coluna numérica.",
        ),
        StructuredTool.from_function(
            func=group_aggregate,
            name="agrupar_e_agregar",
            description="Agrupa por uma coluna categórica e aplica agregação (sum, mean, median, min, max, count) sobre outra coluna.",
        ),
        StructuredTool.from_function(
            func=extremos,
            name="extremos_coluna",
            description="Lista os maiores e menores valores de uma coluna numérica.",
        ),
        Tool.from_function(
            func=describe,
            name="descrever_numericas",
            description="Retorna estatísticas descritivas (count, mean, std, min, quartis, max) das colunas numéricas.",
        ),
    ]
