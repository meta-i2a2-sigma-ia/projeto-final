"""Agent tools focusing on padrões e tendências."""

from __future__ import annotations

from typing import List

import pandas as pd
from langchain.tools import StructuredTool, Tool

from domain import (
    compute_advanced_analysis,
    detect_temporal_patterns,
    identify_value_frequencies,
    summarize_relationships,
)


def build_pattern_tools(df: pd.DataFrame) -> List[StructuredTool]:
    """Return tools for temporal trends, frequências e correlações."""

    numeric_cols = df.select_dtypes(include="number").columns.tolist()
    nonnum_cols = [c for c in df.columns if c not in numeric_cols]

    def temporal_trends_text() -> str:
        temporal = detect_temporal_patterns(df, numeric_cols)
        if not temporal.get("columns"):
            return "Nenhuma coluna temporal relevante foi detectada."
        lines = ["Colunas temporais identificadas: " + ", ".join(temporal["columns"])]
        if temporal.get("insights"):
            lines.append("Principais tendências:")
            lines.extend("- " + msg for msg in temporal["insights"])
        else:
            lines.append("Não foram encontradas tendências monotônicas fortes.")
        return "\n".join(lines)

    def temporal_trends_tool(_: str = "") -> str:
        return temporal_trends_text()

    def frequent_values_text() -> str:
        freq_df = identify_value_frequencies(df)
        if freq_df.empty:
            return "Não há dados suficientes para calcular frequências."
        return "Valores mais e menos frequentes por coluna:\n" + freq_df.to_string(index=False)

    def frequent_values_tool(_: str = "") -> str:
        return frequent_values_text()

    def relationship_summary_text() -> str:
        rel = summarize_relationships(df, numeric_cols, nonnum_cols)
        outputs = []
        correlations = rel.get("correlations", [])
        if correlations:
            outputs.append("Correlações numéricas relevantes:")
            for item in correlations:
                outputs.append(f"- {item['variaveis']} (|rho|≈{item['correlacao']})")
        else:
            outputs.append("Nenhuma correlação numérica destacada (|rho| ≥ 0.2).")

        categorical = rel.get("categorical", [])
        if categorical:
            outputs.append("Influências de categóricas sobre numéricas:")
            for item in categorical:
                outputs.append(
                    f"- {item['driver']} impacta {item['target']} (diferença média ≈ {item['diferenca_media']})"
                )
        else:
            outputs.append("Nenhuma categoria com impacto médio significativo detectado.")
        return "\n".join(outputs)

    def relationship_summary_tool(_: str = "") -> str:
        return relationship_summary_text()

    def holistic_patterns_text() -> str:
        analysis = compute_advanced_analysis(df)
        chunks = ["Resumo de padrões detectados automaticamente:"]
        temporal = analysis.get("temporal", {})
        if temporal.get("insights"):
            chunks.append("• Tendências temporais: " + "; ".join(temporal["insights"]))
        freq_df = analysis.get("frequencies")
        if isinstance(freq_df, pd.DataFrame) and not freq_df.empty:
            chunks.append("• Valores mais frequentes por coluna registrados (use a ferramenta `frequent_values` para detalhes).")
        rel = analysis.get("relationships", {})
        if rel.get("correlations"):
            top = rel["correlations"][0]
            chunks.append(
                f"• Correlação mais forte: {top['variaveis']} (|rho|≈{top['correlacao']})."
            )
        if len(chunks) == 1:
            chunks.append("Nenhum padrão robusto detectado além de distribuições básicas.")
        return "\n".join(chunks)

    def holistic_patterns_tool(_: str = "") -> str:
        return holistic_patterns_text()

    return [
        Tool.from_function(
            func=temporal_trends_tool,
            name="temporal_trends",
            description="Identifica colunas temporais e descreve padrões de tendência em relação a variáveis numéricas.",
        ),
        Tool.from_function(
            func=frequent_values_tool,
            name="frequent_values",
            description="Lista valores mais e menos frequentes por coluna do dataset.",
        ),
        Tool.from_function(
            func=relationship_summary_tool,
            name="relationship_summary",
            description="Explora correlações numéricas e influência de variáveis categóricas em métricas numéricas.",
        ),
        Tool.from_function(
            func=holistic_patterns_tool,
            name="holistic_patterns",
            description="Gera um resumo textual combinando tendências, frequências e correlações detectadas automaticamente.",
        ),
    ]
