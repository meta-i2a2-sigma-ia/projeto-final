"""Utilities for loading and normalizing fiscal documents (NF-e, NFC-e, etc)."""

from __future__ import annotations

import io
import json
import unicodedata
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import pandas as pd

try:
    from supabase import create_client as _create_supabase_client
except Exception:  # pragma: no cover - optional dependency only when Supabase is used
    _create_supabase_client = None

_ALLOWED_SUPABASE_SCHEMAS = {"public", "graphql_public"}


# -----------------------------
# Public API
# -----------------------------

@dataclass
class LoadedData:
    """Structured payload with the raw DataFrame and metadata about the source."""

    dataframe: pd.DataFrame
    source: str
    metadata: Dict[str, Any]


_REQUIRED_ITEM_COLUMNS = {
    "chave_acesso",
    "numero_item",
    "cfop",
    "ncm",
    "quantidade",
    "valor_unitario",
    "valor_total_item",
}


def load_fiscal_dataframe(
    *,
    file_bytes: bytes,
    filename: str,
    sheet_name: Optional[str] = None,
) -> LoadedData:
    """Load fiscal data from CSV, XLSX, JSON or NF-e XML/ZIP file.

    Parameters
    ----------
    file_bytes:
        Raw bytes uploaded by Streamlit (or other UI).
    filename:
        Name of the uploaded file. Used to infer the loader.
    sheet_name:
        Optional Excel sheet name. Defaults to the first sheet.
    """

    name_lower = filename.lower()
    if name_lower.endswith(".csv"):
        df = pd.read_csv(io.BytesIO(file_bytes))
        return LoadedData(_normalize_dataframe(df), source="csv", metadata={"filename": filename})

    if name_lower.endswith((".xls", ".xlsx")):
        try:
            df = pd.read_excel(io.BytesIO(file_bytes), sheet_name=sheet_name)
        except ImportError as exc:  # pragma: no cover - depends on optional engine
            raise RuntimeError(
                "Dependência ausente para leitura de planilhas. Instale 'openpyxl' (ou 'xlrd' para .xls)."
            ) from exc
        return LoadedData(_normalize_dataframe(df), source="excel", metadata={"filename": filename})

    if name_lower.endswith(".json"):
        payload = json.loads(file_bytes.decode("utf-8"))
        df = pd.DataFrame(payload)
        return LoadedData(_normalize_dataframe(df), source="json", metadata={"filename": filename})

    if name_lower.endswith(".xml"):
        rows = _parse_nfe_xml(file_bytes)
        df = pd.DataFrame(rows)
        return LoadedData(_normalize_dataframe(df), source="xml", metadata={"filename": filename})

    if name_lower.endswith(".zip"):
        rows: List[Dict[str, Any]] = []
        with zipfile.ZipFile(io.BytesIO(file_bytes)) as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                if info.filename.lower().endswith(".xml"):
                    rows.extend(_parse_nfe_xml(zf.read(info)))
        if not rows:
            raise ValueError("Nenhum arquivo XML de nota fiscal encontrado dentro do zip.")
        df = pd.DataFrame(rows)
        return LoadedData(_normalize_dataframe(df), source="zip_xml", metadata={"filename": filename, "n_docs": len(rows)})

    raise ValueError(f"Formato de arquivo não suportado: {filename}")


# -----------------------------
# Supabase helper (shared with Streamlit app)
# -----------------------------

def load_supabase_table(schema: str, table: str, limit: int = 20000) -> pd.DataFrame:
    if _create_supabase_client is None:
        raise RuntimeError("Dependência do Supabase ausente. Instale 'supabase'.")

    url = _get_env("SUPABASE_URL")
    key = _get_env("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise RuntimeError("Configure SUPABASE_URL e SUPABASE_SERVICE_ROLE_KEY nas variáveis de ambiente.")

    schema_normalized = (schema or "public").strip() or "public"
    if schema_normalized not in _ALLOWED_SUPABASE_SCHEMAS:
        allowed = ", ".join(sorted(_ALLOWED_SUPABASE_SCHEMAS))
        raise ValueError(
            "Supabase PostgREST está configurado para aceitar apenas os schemas "
            f"{allowed}. Ajuste PG_SCHEMA para um desses valores ou exponha o schema desejado no Supabase."
        )

    client = _create_supabase_client(url, key)
    table_ref = client.table(table)

    chunk = 50000
    all_rows: List[Dict[str, Any]] = []
    for start in range(0, limit, chunk):
        end = min(start + chunk - 1, limit - 1)
        response = table_ref.select("*").range(start, end).execute()
        error = getattr(response, "error", None)
        if error:
            raise RuntimeError(f"Erro Supabase: {error}")
        data = response.data or []
        if not data:
            break
        all_rows.extend(data)
        if len(data) < (end - start + 1):
            break

    if not all_rows:
        return pd.DataFrame()
    return _normalize_dataframe(pd.DataFrame(all_rows))


# -----------------------------
# Internal helpers
# -----------------------------

_ENV_CACHE: Dict[str, str] = {}


def _get_env(name: str) -> str:
    if name in _ENV_CACHE:
        return _ENV_CACHE[name]
    from os import environ

    value = environ.get(name, "")
    _ENV_CACHE[name] = value
    return value


def _normalize_label(label: str) -> str:
    cleaned = (
        unicodedata.normalize("NFKD", str(label)).encode("ascii", "ignore").decode("ascii").lower()
    )
    for token in ["/", "\\", "-", "(", ")", "%", ":", ";"]:
        cleaned = cleaned.replace(token, " ")
    cleaned = "_".join(part for part in cleaned.replace("  ", " ").split() if part)
    return cleaned


_COLUMN_ALIASES = {
    "chave_de_acesso": "chave_acesso",
    "chave_de_acesso_item": "chave_acesso",
    "chave_de_acesso_nota": "chave_acesso",
    "modelo_nota": "modelo",
    "modelo_item": "modelo",
    "serie_nota": "serie",
    "serie_item": "serie",
    "numero_nota": "numero",
    "numero_item": "numero_nota",
    "natureza_da_operacao_nota": "natureza_operacao",
    "natureza_da_operacao_item": "natureza_operacao",
    "data_emissao_nota": "data_emissao",
    "data_emissao_item": "data_emissao",
    "evento_mais_recente": "evento_recente",
    "data_hora_evento_mais_recente": "data_evento_recente",
    "cpf_cnpj_emitente_nota": "cnpj_emitente",
    "cpf_cnpj_emitente_item": "cnpj_emitente",
    "razao_social_emitente_nota": "razao_emitente",
    "razao_social_emitente_item": "razao_emitente",
    "inscricao_estadual_emitente_nota": "ie_emitente",
    "uf_emitente_nota": "uf_emitente",
    "municipio_emitente_nota": "municipio_emitente",
    "cnpj_destinatario_nota": "cnpj_destinatario",
    "cnpj_destinatario_item": "cnpj_destinatario",
    "nome_destinatario_nota": "razao_destinatario",
    "nome_destinatario_item": "razao_destinatario",
    "uf_destinatario_nota": "uf_destinatario",
    "uf_destinatario_item": "uf_destinatario",
    "indicador_ie_destinatario_nota": "indicador_ie",
    "indicador_ie_destinatario_item": "indicador_ie",
    "destino_da_operacao_nota": "destino_operacao",
    "destino_da_operacao_item": "destino_operacao",
    "consumidor_final_nota": "consumidor_final",
    "presenca_do_comprador_nota": "presenca_comprador",
    "valor_nota_fiscal": "valor_total_nota",
    "numero_produto": "numero_item",
    "descricao_do_produto_servico": "descricao_item",
    "codigo_ncm_sh": "ncm",
    "ncm_sh_tipo_de_produto": "descricao_ncm",
    "cfop": "cfop",
    "quantidade": "quantidade",
    "unidade": "unidade",
    "valor_unitario": "valor_unitario",
    "valor_total": "valor_total_item",
    "aliquota_icms": "aliquota_icms",
    "valor_icms": "valor_icms",
    "base_calculo_icms": "base_icms",
    "aliquota_ipi": "aliquota_ipi",
    "valor_ipi": "valor_ipi",
    "base_calculo_ipi": "base_ipi",
}

_NUMERIC_COLUMNS = {
    "serie",
    "numero_nota",
    "valor_total_item",
    "valor_total_nota",
    "quantidade",
    "valor_unitario",
    "aliquota_icms",
    "valor_icms",
    "base_icms",
    "aliquota_ipi",
    "valor_ipi",
    "base_ipi",
}


def _normalize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    renamed: Dict[str, str] = {}
    for col in df.columns:
        norm = _normalize_label(col)
        canonical = _COLUMN_ALIASES.get(norm, norm)
        renamed[col] = canonical
    df = df.rename(columns=renamed)
    if df.columns.duplicated().any():
        # mantém a primeira ocorrência de cada coluna após normalização
        df = df.loc[:, ~df.columns.duplicated()].copy()

    # enforce consistent numeric types
    for col in df.columns:
        if col in _NUMERIC_COLUMNS:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        elif col in {"cfop", "ncm", "chave_acesso", "cnpj_emitente", "cnpj_destinatario"}:
            df[col] = df[col].astype(str).str.strip()

    if "numero_item" not in df.columns:
        df["numero_item"] = pd.NA

    return df


# -----------------------------
# XML parser
# -----------------------------

_NFE_NS = {
    "nfe": "http://www.portalfiscal.inf.br/nfe",
}


def _parse_nfe_xml(xml_bytes: bytes) -> List[Dict[str, Any]]:
    from xml.etree import ElementTree as ET

    root = ET.fromstring(xml_bytes)

    # Some XMLs wrap the NFe in <nfeProc>. Locate <infNFe> regardless of the wrapper.
    inf_nfe = root.find(".//nfe:infNFe", _NFE_NS)
    if inf_nfe is None:
        raise ValueError("Estrutura XML de NF-e inválida: elemento infNFe não encontrado.")

    data: Dict[str, Any] = {}
    data["chave_acesso"] = (inf_nfe.get("Id") or "").replace("NFe", "").strip()

    def get_text(path: str) -> str:
        node = inf_nfe.find(path, _NFE_NS)
        if node is None or node.text is None:
            return ""
        return node.text.strip()

    data.update(
        {
            "modelo": get_text("nfe:ide/nfe:mod"),
            "serie": get_text("nfe:ide/nfe:serie"),
            "numero": get_text("nfe:ide/nfe:nNF"),
            "natureza_operacao": get_text("nfe:ide/nfe:natOp"),
            "data_emissao": get_text("nfe:ide/nfe:dhEmi") or get_text("nfe:ide/nfe:dEmi"),
            "cnpj_emitente": get_text("nfe:emit/nfe:CNPJ") or get_text("nfe:emit/nfe:CPF"),
            "razao_emitente": get_text("nfe:emit/nfe:xNome"),
            "ie_emitente": get_text("nfe:emit/nfe:IE"),
            "uf_emitente": get_text("nfe:emit/nfe:enderEmit/nfe:UF"),
            "municipio_emitente": get_text("nfe:emit/nfe:enderEmit/nfe:xMun"),
            "cnpj_destinatario": get_text("nfe:dest/nfe:CNPJ") or get_text("nfe:dest/nfe:CPF"),
            "razao_destinatario": get_text("nfe:dest/nfe:xNome"),
            "uf_destinatario": get_text("nfe:dest/nfe:enderDest/nfe:UF"),
            "destino_operacao": get_text("nfe:ide/nfe:dest"),
            "consumidor_final": get_text("nfe:ide/nfe:indFinal"),
            "presenca_comprador": get_text("nfe:ide/nfe:indPres"),
            "valor_total_nota": get_text("nfe:total/nfe:ICMSTot/nfe:vNF"),
        }
    )

    rows: List[Dict[str, Any]] = []
    for det in inf_nfe.findall("nfe:det", _NFE_NS):
        prod = det.find("nfe:prod", _NFE_NS)
        imposto = det.find("nfe:imposto", _NFE_NS)
        item: Dict[str, Any] = data.copy()
        item["numero_item"] = det.get("nItem")
        if prod is not None:
            item.update(
                {
                    "descricao_item": _xml_text(prod, "nfe:xProd"),
                    "cfop": _xml_text(prod, "nfe:CFOP"),
                    "ncm": _xml_text(prod, "nfe:NCM"),
                    "quantidade": _to_float(_xml_text(prod, "nfe:qCom")),
                    "unidade": _xml_text(prod, "nfe:uCom"),
                    "valor_unitario": _to_float(_xml_text(prod, "nfe:vUnCom")),
                    "valor_total_item": _to_float(_xml_text(prod, "nfe:vProd")),
                }
            )
        if imposto is not None:
            icms = imposto.find(".//nfe:ICMS*", _NFE_NS)
            if icms is not None:
                item.update(
                    {
                        "aliquota_icms": _to_float(_xml_text(icms, "nfe:pICMS")),
                        "base_icms": _to_float(_xml_text(icms, "nfe:vBC")),
                        "valor_icms": _to_float(_xml_text(icms, "nfe:vICMS")),
                    }
                )
            ipi = imposto.find(".//nfe:IPITrib", _NFE_NS)
            if ipi is not None:
                item.update(
                    {
                        "aliquota_ipi": _to_float(_xml_text(ipi, "nfe:pIPI")),
                        "base_ipi": _to_float(_xml_text(ipi, "nfe:vBC")),
                        "valor_ipi": _to_float(_xml_text(ipi, "nfe:vIPI")),
                    }
                )
        rows.append(item)

    if not rows:
        rows.append(data)
    return rows


def _xml_text(parent, path: str) -> str:
    from xml.etree import ElementTree as ET

    node = parent.find(path, _NFE_NS)
    if node is None or node.text is None:
        return ""
    return node.text.strip()


def _to_float(value: str) -> Optional[float]:
    if not value:
        return None
    try:
        return float(value.replace(",", "."))
    except ValueError:
        return None
