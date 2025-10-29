"""Domain-specific validation rules for Brazilian fiscal documents."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional

import pandas as pd

MANDATORY_COLUMNS = {
    "chave_acesso",
    "numero",
    "numero_item",
    "cfop",
    "ncm",
    "quantidade",
    "valor_unitario",
    "valor_total_item",
    "valor_total_nota",
}

_TOTAL_NOTA_FALLBACK = (
    "valor_total_nota",
    "valor_nota_fiscal",
)

CFOP_PREFIX_RULES = {
    "1": {"expected": ("5",), "label": "operação interna"},
    "2": {"expected": ("6",), "label": "operação interestadual"},
    "3": {"expected": ("7",), "label": "operação com exterior"},
}


@dataclass
class ValidationResult:
    identifier: str
    title: str
    severity: str
    conclusion: str
    details: pd.DataFrame


def run_core_validations(df: pd.DataFrame) -> List[ValidationResult]:
    checks: List[ValidationResult] = []

    missing_cols = MANDATORY_COLUMNS.difference(df.columns)
    if "valor_total_nota" in missing_cols and "valor_nota_fiscal" in df.columns:
        missing_cols.remove("valor_total_nota")
    if missing_cols:
        raise ValueError(f"Colunas obrigatórias ausentes: {', '.join(sorted(missing_cols))}.")

    duplicate_items = _detect_duplicate_items(df)
    if not duplicate_items.empty:
        checks.append(
            ValidationResult(
                identifier="duplicate_items",
                title="Itens duplicados na nota",
                severity="alta",
                conclusion="Foram identificados itens com mesma chave de acesso e número de item cadastrados mais de uma vez.",
                details=duplicate_items,
            )
        )

    cfop_mismatch = _detect_cfop_mismatch(df)
    if not cfop_mismatch.empty:
        checks.append(
            ValidationResult(
                identifier="cfop_destino",
                title="CFOP incompatível com o destino da operação",
                severity="alta",
                conclusion="Há documentos cujo CFOP não condiz com o destino informado (interno, interestadual ou exterior).",
                details=cfop_mismatch,
            )
        )

    ncm_invalid = _detect_invalid_ncm(df)
    if not ncm_invalid.empty:
        checks.append(
            ValidationResult(
                identifier="ncm_invalido",
                title="NCM inválido ou incompleto",
                severity="media",
                conclusion="Revise os códigos NCM abaixo; devem possuir oito dígitos e conter apenas números.",
                details=ncm_invalid,
            )
        )

    cnpj_inconsistent = _detect_cnpj_issues(df)
    if not cnpj_inconsistent.empty:
        checks.append(
            ValidationResult(
                identifier="cnpj_invalido",
                title="CNPJ emitente/destinatário inconsistente",
                severity="media",
                conclusion="CNPJs com quantidade de dígitos incorreta ou caracteres inválidos foram encontrados.",
                details=cnpj_inconsistent,
            )
        )

    item_total_mismatch = _detect_item_total_mismatch(df)
    if not item_total_mismatch.empty:
        checks.append(
            ValidationResult(
                identifier="valor_item_divergente",
                title="Valor total do item difere da multiplicação",
                severity="alta",
                conclusion="Em alguns itens o valor total informado não corresponde à multiplicação de quantidade por valor unitário.",
                details=item_total_mismatch,
            )
        )

    nota_total_mismatch = _detect_nota_total_mismatch(df)
    if not nota_total_mismatch.empty:
        checks.append(
            ValidationResult(
                identifier="valor_nota_divergente",
                title="Valor total da nota difere da soma dos itens",
                severity="alta",
                conclusion="Notas fiscais com divergência entre o valor total informado e a soma dos itens foram encontradas.",
                details=nota_total_mismatch,
            )
        )

    icms_issues = _detect_icms_mismatch(df)
    if not icms_issues.empty:
        checks.append(
            ValidationResult(
                identifier="icms_incoerente",
                title="ICMS incoerente",
                severity="media",
                conclusion="Os itens listados apresentam divergência entre base, alíquota e valor de ICMS.",
                details=icms_issues,
            )
        )

    return checks


def summarize_issues(results: Iterable[ValidationResult]) -> pd.DataFrame:
    rows = [
        {
            "regra": r.title,
            "id": r.identifier,
            "severidade": r.severity,
            "ocorrencias": len(r.details),
            "descricao": r.conclusion,
        }
        for r in results
    ]
    return pd.DataFrame(rows)


def offenders_by(results: Iterable[ValidationResult], group: str) -> pd.DataFrame:
    frames: List[pd.DataFrame] = []
    for res in results:
        if group not in res.details.columns:
            continue
        tmp = res.details.copy()
        tmp["regra"] = res.title
        frames.append(tmp[[group, "regra"]])
    if not frames:
        return pd.DataFrame()
    data = pd.concat(frames, ignore_index=True)
    top = data.value_counts().reset_index(name="ocorrencias").sort_values("ocorrencias", ascending=False)
    top.rename(columns={group: group}, inplace=True)
    return top


# -----------------------------
# Individual validations
# -----------------------------


def _detect_duplicate_items(df: pd.DataFrame) -> pd.DataFrame:
    subset = df[df.duplicated(subset=["chave_acesso", "numero_item"], keep=False)].copy()
    return subset[[
        "chave_acesso",
        "numero",
        "numero_item",
        "descricao_item",
        "valor_total_item",
    ]]


def _detect_cfop_mismatch(df: pd.DataFrame) -> pd.DataFrame:
    if "destino_operacao" not in df.columns:
        return pd.DataFrame()
    work = df[["chave_acesso", "numero", "numero_item", "cfop", "destino_operacao", "valor_total_item"]].copy()
    work["cfop_str"] = work["cfop"].astype(str).str.extract(r"(\d+)")
    work["cfop_prefix"] = work["cfop_str"].str.zfill(4).str[0]
    work["destino_codigo"] = work["destino_operacao"].str.extract(r"(\d)")

    def mismatch(row) -> bool:
        dest = row["destino_codigo"]
        if not dest or dest not in CFOP_PREFIX_RULES:
            return False
        cfop_prefix = row["cfop_str"][:1] if row["cfop_str"] else ""
        return cfop_prefix not in CFOP_PREFIX_RULES[dest]["expected"]

    mask = work.apply(mismatch, axis=1)
    issues = work[mask].copy()
    if issues.empty:
        return pd.DataFrame()
    issues["destino_esperado"] = issues["destino_codigo"].map(lambda c: CFOP_PREFIX_RULES[c]["expected"] if c in CFOP_PREFIX_RULES else ())
    return issues[[
        "chave_acesso",
        "numero",
        "numero_item",
        "cfop",
        "destino_operacao",
        "destino_esperado",
        "valor_total_item",
    ]]


def _detect_invalid_ncm(df: pd.DataFrame) -> pd.DataFrame:
    work = df[["chave_acesso", "numero", "numero_item", "ncm", "descricao_item"]].copy()
    work["ncm_str"] = work["ncm"].astype(str).str.replace(".0$", "", regex=True)
    mask = ~work["ncm_str"].str.fullmatch(r"\d{8}")
    issues = work[mask]
    return issues[["chave_acesso", "numero", "numero_item", "ncm", "descricao_item"]]


def _detect_cnpj_issues(df: pd.DataFrame) -> pd.DataFrame:
    cols = [c for c in ["cnpj_emitente", "cnpj_destinatario"] if c in df.columns]
    if not cols:
        return pd.DataFrame()
    target_cols = cols + ["chave_acesso", "numero", "valor_total_item"]
    work = df[target_cols].copy()
    output_rows: List[Dict[str, Optional[str]]] = []
    for _, row in work.iterrows():
        for col in cols:
            value = str(row[col]) if pd.notna(row[col]) else ""
            digits = "".join(filter(str.isdigit, value))
            if digits and len(digits) != 14:
                output_rows.append(
                    {
                        "chave_acesso": row["chave_acesso"],
                        "numero": row["numero"],
                        "campo": col,
                        "valor_original": value,
                        "quantidade_digitos": len(digits),
                        "valor_total_item": row.get("valor_total_item"),
                    }
                )
    return pd.DataFrame(output_rows)


def _detect_item_total_mismatch(df: pd.DataFrame) -> pd.DataFrame:
    work = df[[
        "chave_acesso",
        "numero",
        "numero_item",
        "quantidade",
        "valor_unitario",
        "valor_total_item",
        "descricao_item",
    ]].copy()
    work["quantidade"] = pd.to_numeric(work["quantidade"], errors="coerce")
    work["valor_unitario"] = pd.to_numeric(work["valor_unitario"], errors="coerce")
    work["valor_total_item"] = pd.to_numeric(work["valor_total_item"], errors="coerce")
    work.dropna(subset=["quantidade", "valor_unitario", "valor_total_item"], inplace=True)
    work["esperado"] = (work["quantidade"] * work["valor_unitario"]).round(2)
    work["diferenca"] = (work["valor_total_item"] - work["esperado"]).round(2)
    issues = work[work["diferenca"].abs() > 1.0]
    return issues[[
        "chave_acesso",
        "numero",
        "numero_item",
        "descricao_item",
        "quantidade",
        "valor_unitario",
        "valor_total_item",
        "esperado",
        "diferenca",
    ]]


def _detect_nota_total_mismatch(df: pd.DataFrame) -> pd.DataFrame:
    nota_total_col = next((c for c in _TOTAL_NOTA_FALLBACK if c in df.columns), None)
    if nota_total_col is None:
        return pd.DataFrame()
    work = df[["chave_acesso", "numero", "valor_total_item", nota_total_col]].copy()
    sums = work.groupby(["chave_acesso", "numero"], dropna=False)["valor_total_item"].sum().reset_index(name="soma_itens")
    ref = work.drop_duplicates(subset=["chave_acesso", "numero"])
    merged = pd.merge(ref, sums, on=["chave_acesso", "numero"], how="left")
    merged[nota_total_col] = pd.to_numeric(merged[nota_total_col], errors="coerce")
    merged["soma_itens"] = pd.to_numeric(merged["soma_itens"], errors="coerce")
    merged["diferenca"] = (merged[nota_total_col] - merged["soma_itens"]).round(2)
    issues = merged[merged["diferenca"].abs() > 1.0]
    return issues[[
        "chave_acesso",
        "numero",
        nota_total_col,
        "soma_itens",
        "diferenca",
    ]]


def _detect_icms_mismatch(df: pd.DataFrame) -> pd.DataFrame:
    required = {"aliquota_icms", "base_icms", "valor_icms"}
    if not required.issubset(df.columns):
        return pd.DataFrame()
    work = df[[
        "chave_acesso",
        "numero",
        "numero_item",
        "descricao_item",
        "base_icms",
        "aliquota_icms",
        "valor_icms",
    ]].copy()
    work[["base_icms", "aliquota_icms", "valor_icms"]] = work[["base_icms", "aliquota_icms", "valor_icms"]].apply(pd.to_numeric, errors="coerce")
    work.dropna(subset=["base_icms", "aliquota_icms", "valor_icms"], inplace=True)
    work["calculado"] = (work["base_icms"] * (work["aliquota_icms"] / 100.0)).round(2)
    work["diferenca"] = (work["valor_icms"] - work["calculado"]).round(2)
    issues = work[work["diferenca"].abs() > 1.0]
    return issues[[
        "chave_acesso",
        "numero",
        "numero_item",
        "descricao_item",
        "base_icms",
        "aliquota_icms",
        "valor_icms",
        "calculado",
        "diferenca",
    ]]
