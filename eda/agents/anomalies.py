"""Agent tools focusing on detecção de anomalias e clusters."""

from __future__ import annotations

from typing import List

import pandas as pd
from langchain.tools import StructuredTool, Tool

from domain import (
    OUTLIER_SUGGESTIONS,
    detect_clusters,
    detect_outliers,
)
from .context import AgentDataContext


def build_anomaly_tools(ctx: AgentDataContext) -> List[StructuredTool]:
    numeric_cols_cache = {"value": None}

    def get_df() -> pd.DataFrame:
        df = ctx.require_dataframe()
        return df

    def numeric_cols(df: pd.DataFrame) -> list[str]:
        cached = numeric_cols_cache.get("value")
        if cached is not None and cached.get("id") is id(df):
            return cached["cols"]
        cols = df.select_dtypes(include="number").columns.tolist()
        numeric_cols_cache["value"] = {"id": id(df), "cols": cols}
        return cols

    def outlier_report_text(df: pd.DataFrame) -> str:
        out_df = detect_outliers(df, numeric_cols(df))
        if out_df.empty:
            return "Nenhum outlier relevante foi detectado usando o critério de 1.5 IQR."
        message = ["Outliers identificados por coluna:", out_df.to_string(index=False)]
        message.append("Sugestões de tratamento:")
        message.extend(f"- {tip}" for tip in OUTLIER_SUGGESTIONS)
        return "\n".join(message)

    def outlier_report_tool(_: str = "") -> str:
        try:
            df = get_df()
        except ValueError as exc:
            return str(exc)
        return outlier_report_text(df)

    def cluster_report_text(df: pd.DataFrame) -> str:
        clusters = detect_clusters(df, numeric_cols(df))
        status = clusters.get("status")
        if status == "missing_dependency":
            return "scikit-learn não está instalado; instale para habilitar clusterização."
        if status == "not_enough_features":
            return "É necessário pelo menos duas colunas numéricas para avaliar clusters."
        if status == "not_enough_rows":
            return "Amostra insuficiente (<50 linhas) para clusterizar com confiabilidade."
        if status == "ok":
            sizes = clusters.get("cluster_sizes", {})
            parts = [
                f"Clusterização sugeriu {clusters['k']} grupos (silhouette≈{clusters['silhouette']}).",
                "Distribuição de tamanhos:" + ", ".join(f"Cluster {k}: {v}" for k, v in sizes.items()),
            ]
            return "\n".join(parts)
            return "Nenhuma estrutura de cluster consistente foi encontrada."

    def cluster_report_tool(_: str = "") -> str:
        try:
            df = get_df()
        except ValueError as exc:
            return str(exc)
        return cluster_report_text(df)

    tools = [
        Tool.from_function(
            func=outlier_report_tool,
            name="outlier_report",
            description="Gera um relatório sobre valores atípicos (outliers) utilizando o critério de 1.5 IQR e sugere tratamentos.",
        ),
        Tool.from_function(
            func=cluster_report_tool,
            name="cluster_report",
            description="Avalia a existência de clusters usando K-Means e retorna o número de grupos sugerido.",
        ),
    ]
    return tools
