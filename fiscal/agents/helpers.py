"""Shared helper tools for fiscal agents."""

from __future__ import annotations

from typing import Optional

import pandas as pd
from langchain.tools import StructuredTool

from .context import AgentDataContext


def _note_key_column(df: pd.DataFrame) -> Optional[str]:
    if "chave_acesso" in df.columns:
        return "chave_acesso"
    if "numero" in df.columns:
        return "numero"
    return None


def _compute_note_totals(df: pd.DataFrame) -> Optional[pd.DataFrame]:
    chave_col = _note_key_column(df)
    if chave_col is None:
        return None

    if "valor_nota_fiscal" in df.columns:
        notas = df[[chave_col, "valor_nota_fiscal"]].copy()
        notas["valor_nota_fiscal"] = pd.to_numeric(notas["valor_nota_fiscal"], errors="coerce")
        notas = notas.dropna(subset=["valor_nota_fiscal"])
        if notas.empty:
            return None
        agg = notas.groupby(chave_col, as_index=False)["valor_nota_fiscal"].max()
        return agg.rename(columns={"valor_nota_fiscal": "valor_nota"})

    item_series: Optional[pd.Series] = None
    if "valor_total_item" in df.columns:
        item_series = pd.to_numeric(df["valor_total_item"], errors="coerce")
    elif {"quantidade", "valor_unitario"}.issubset(df.columns):
        qtd = pd.to_numeric(df["quantidade"], errors="coerce")
        unit = pd.to_numeric(df["valor_unitario"], errors="coerce")
        item_series = qtd * unit

    if item_series is None:
        return None

    notas = df[[chave_col]].copy()
    notas["_valor_item"] = item_series
    notas = notas.dropna(subset=["_valor_item"])
    if notas.empty:
        return None

    agg = notas.groupby(chave_col, as_index=False)["_valor_item"].sum()
    return agg.rename(columns={"_valor_item": "valor_nota"})


def build_maior_nota_tool(ctx: AgentDataContext, name: str = "nota_extrema") -> StructuredTool:
    """Return a tool that finds the highest or lowest nota fiscal value."""

    def nota_extrema(tipo: str = "maior") -> str:
        """Calcula a nota fiscal de maior ou menor valor conforme o argumento 'tipo'."""

        try:
            df = ctx.require_dataframe()
        except ValueError as exc:
            return str(exc)

        token = (tipo or "maior").strip().lower()
        mode = "menor" if token in {"menor", "min", "minimo", "mínimo"} else "maior"

        totals = _compute_note_totals(df)
        if totals is None or totals.empty:
            return (
                "Não foi possível calcular o valor total das notas (verifique colunas 'valor_nota_fiscal', 'valor_total_item' ou 'quantidade'/'valor_unitario')."
            )

        chave_col = totals.columns[0]
        valor_col = "valor_nota"
        idx = totals[valor_col].idxmin() if mode == "menor" else totals[valor_col].idxmax()
        target = totals.loc[idx]
        chave_val = target[chave_col]
        valor = float(target[valor_col])

        ref_rows = df[df[chave_col] == chave_val] if chave_col in df.columns else df

        numero = None
        if "numero" in ref_rows.columns:
            numero = ref_rows["numero"].dropna().astype(str).head(1).tolist()
            numero = numero[0] if numero else None

        emitente = None
        if "razao_emitente" in ref_rows.columns:
            emitente = ref_rows["razao_emitente"].dropna().astype(str).head(1).tolist()
            emitente = emitente[0] if emitente else None

        titulo = "Menor nota" if mode == "menor" else "Maior nota"
        partes = [f"{titulo} encontrada: R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")]
        if chave_col == "chave_acesso":
            partes.append(f"Chave de acesso: {chave_val}")
        if numero:
            partes.append(f"Número: {numero}")
        elif chave_col == "numero":
            partes.append(f"Número: {chave_val}")
        if emitente:
            partes.append(f"Emitente: {emitente}")
        return " | ".join(partes)

    return StructuredTool.from_function(
        func=nota_extrema,
        name=name,
        description=(
            "Retorna a nota fiscal de maior (padrão) ou menor valor, considerando 'valor_nota_fiscal' quando disponível ou a soma de itens (quantidade × valor_unitario)."
        ),
    )
