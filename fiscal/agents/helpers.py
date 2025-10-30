"""Shared helper tools for fiscal agents."""

from __future__ import annotations

from typing import Optional

import pandas as pd
from langchain.tools import StructuredTool

from .context import AgentDataContext


def build_maior_nota_tool(ctx: AgentDataContext, name: str = "nota_extrema") -> StructuredTool:
    """Return a tool that finds the highest or lowest nota fiscal value."""

    def maior_nota(tipo: str = "maior") -> str:
        """Calcula a nota fiscal de maior ou menor valor conforme o argumento 'tipo'."""
        try:
            df = ctx.require_dataframe()
        except ValueError as exc:
            return str(exc)

        token = (tipo or "maior").strip().lower()
        mode = "menor" if token in {"menor", "min", "minimo", "mínimo"} else "maior"

        valor_col: Optional[str] = None
        for candidate in ("valor_total_nota", "valor_nota_fiscal", "valor_total"):
            if candidate in df.columns:
                valor_col = candidate
                break
        if valor_col is None:
            return (
                "Não encontrei uma coluna de valor total da nota (procure por 'valor_total_nota' ou 'valor_nota_fiscal')."
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
            if mode == "menor":
                top_row = soma.loc[soma[valor_col].idxmin()]
            else:
                top_row = soma.loc[soma[valor_col].idxmax()]
            chave = str(top_row[chave_col])
            valor = float(top_row[valor_col])
            ref_rows = df[df[chave_col] == top_row[chave_col]]
        else:
            idx = notas[valor_col].idxmin() if mode == "menor" else notas[valor_col].idxmax()
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

        titulo = "Menor nota" if mode == "menor" else "Maior nota"
        partes = [f"{titulo} encontrada: R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")]
        if numero:
            partes.append(f"Número: {numero}")
        if chave:
            partes.append(f"Chave de acesso: {chave}")
        if emitente:
            partes.append(f"Emitente: {emitente}")
        return " | ".join(partes)

    return StructuredTool.from_function(
        func=maior_nota,
        name=name,
        description=(
            "Retorna a nota fiscal de maior (padrão) ou menor valor, apresentando número, chave de acesso e emitente quando disponíveis."
        ),
    )
