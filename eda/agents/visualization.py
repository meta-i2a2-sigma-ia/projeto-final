"""Tools para auxiliar na definição de gráficos."""

from __future__ import annotations

import json
from typing import List, Optional

from pandas import DataFrame
from langchain.tools import StructuredTool, Tool

from .context import AgentDataContext


def build_visual_tools(ctx: AgentDataContext) -> List[StructuredTool]:
    def list_chart_columns_text(df: DataFrame) -> str:
        return "Colunas disponíveis para gráficos: " + ", ".join(df.columns)

    def list_chart_columns_tool(_: str = "") -> str:
        try:
            df = ctx.require_dataframe()
        except ValueError as exc:
            return str(exc)
        return list_chart_columns_text(df)

    def create_chart_spec(
        kind: str,
        x: str,
        y: Optional[str] = None,
        color: Optional[str] = None,
        bins: Optional[int] = None,
        agg: Optional[str] = None,
        title: Optional[str] = None,
    ) -> str:
        try:
            df = ctx.require_dataframe()
        except ValueError as exc:
            return str(exc)
        if kind not in {"Histogram", "Box", "Scatter", "Line", "Bar", "Correlation heatmap"}:
            return "Tipo de gráfico inválido. Utilize Histogram, Box, Scatter, Line, Bar ou Correlation heatmap."
        if x not in df.columns:
            return f"Coluna X '{x}' não encontrada no dataset."
        if y and y not in df.columns:
            return f"Coluna Y '{y}' não encontrada no dataset."
        if color and color not in df.columns:
            return f"Coluna de cor '{color}' não encontrada no dataset."
        payload = {
            "kind": kind,
            "x": x,
            "y": y,
            "color": color,
            "bins": bins,
            "agg": agg,
            "title": title or f"{kind} ({x}{' vs ' + y if y else ''})",
        }
        return "<<CHART_SPEC>>" + json.dumps(payload) + "<<END_CHART_SPEC>>"

    return [
        Tool.from_function(
            func=list_chart_columns_tool,
            name="list_chart_columns",
            description="Lista rapidamente todas as colunas disponíveis para construção de gráficos.",
        ),
        StructuredTool.from_function(
            func=create_chart_spec,
            name="create_chart_spec",
            description=(
                "Gera um bloco CHART_SPEC pronto para uso especificando tipo de gráfico, eixos, cor e agregação. "
                "Use quando desejar que o app renderize automaticamente o gráfico sugerido."
            ),
        ),
    ]
