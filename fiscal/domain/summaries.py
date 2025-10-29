"""High-level summaries tailored for fiscal (NF-e) datasets."""

from __future__ import annotations

from datetime import datetime
from typing import Dict

import pandas as pd


def fiscal_overview(df: pd.DataFrame) -> Dict[str, object]:
    notas = df[["chave_acesso", "numero", "valor_total_nota", "data_emissao"]].drop_duplicates()
    notas["valor_total_nota"] = pd.to_numeric(notas["valor_total_nota"], errors="coerce")

    total_notas = notas["chave_acesso"].nunique(dropna=True)
    total_emitentes = df.get("cnpj_emitente").nunique(dropna=True) if "cnpj_emitente" in df else 0
    total_destinatarios = df.get("cnpj_destinatario").nunique(dropna=True) if "cnpj_destinatario" in df else 0

    valores_itens = pd.to_numeric(df.get("valor_total_item"), errors="coerce")
    valor_total_itens = float(valores_itens.sum(skipna=True)) if valores_itens is not None else 0.0
    valor_total_notas = float(notas["valor_total_nota"].sum(skipna=True)) if "valor_total_nota" in notas else 0.0

    mensal = _timeline(notas, "data_emissao", "valor_total_nota")
    by_cfop = _top(df, "cfop", "valor_total_item")
    by_ncm = _top(df, "ncm", "valor_total_item")
    by_emitente = _top(df, "razao_emitente", "valor_total_item")
    by_dest = _top(df, "razao_destinatario", "valor_total_item")

    return {
        "total_notas": int(total_notas),
        "total_itens": int(len(df)),
        "total_emitentes": int(total_emitentes),
        "total_destinatarios": int(total_destinatarios),
        "valor_total_itens": round(valor_total_itens, 2),
        "valor_total_notas": round(valor_total_notas, 2),
        "valor_medio_nota": round(valor_total_notas / total_notas, 2) if total_notas else 0.0,
        "timeline": mensal,
        "top_cfop": by_cfop,
        "top_ncm": by_ncm,
        "top_emitentes": by_emitente,
        "top_destinatarios": by_dest,
    }


def _timeline(df: pd.DataFrame, date_col: str, value_col: str) -> pd.DataFrame:
    if date_col not in df or value_col not in df:
        return pd.DataFrame()
    work = df[[date_col, value_col]].dropna()
    if work.empty:
        return pd.DataFrame()

    def _safe_parse(value) -> datetime:
        if isinstance(value, datetime):
            return value
        try:
            return pd.to_datetime(value)
        except Exception:
            return pd.NaT

    work[date_col] = work[date_col].apply(_safe_parse)
    work = work.dropna(subset=[date_col])
    if work.empty:
        return pd.DataFrame()
    resampled = (
        work.groupby(work[date_col].dt.to_period("M"))[value_col]
        .sum()
        .reset_index()
        .rename(columns={date_col: "competencia", value_col: "valor"})
    )
    resampled["competencia"] = resampled["competencia"].astype(str)
    return resampled


def _top(df: pd.DataFrame, column: str, value_column: str, limit: int = 10) -> pd.DataFrame:
    if column not in df:
        return pd.DataFrame()
    work = df[[column]].copy()
    if value_column in df:
        work[value_column] = pd.to_numeric(df[value_column], errors="coerce")
    else:
        work[value_column] = 1
    if work.empty:
        return pd.DataFrame()
    agg = (
        work.groupby(column)[value_column]
        .sum()
        .reset_index()
        .sort_values(value_column, ascending=False)
    )
    return agg.head(limit)
