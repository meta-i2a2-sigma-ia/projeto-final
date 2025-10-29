"""Tools that assist with ERP integration guidance."""

from __future__ import annotations

from typing import Dict, List

import pandas as pd
try:
    from langchain.tools import Tool
except ImportError:
    from langchain_core.tools import Tool

ERP_GUIDES: Dict[str, Dict[str, str]] = {
    "dominio": {
        "descricao": "Sincronização via importação de XML/JSON e rotinas de boletim fiscal.",
        "metodo": "Utilize o importador da Domínio (MFD) com layout NF-e 4.0. Automação via API REST requer credenciais do WebService Domínio.",
        "observacoes": "Valide CFOP e CST antes da importação; informe códigos do IBGE para município.",
    },
    "alterdata": {
        "descricao": "Integração pelo TAF (Tratamento Automático Fiscal) com agendamento de jobs.",
        "metodo": "Disponibilize os XMLs em diretório monitorado pelo TAF ou utilize o conector Alterdata Bridge.",
        "observacoes": "Confira parametrização de natureza da operação e códigos de serviço, pois divergências travam a importação.",
    },
    "protheus": {
        "descricao": "Integração com TOTVS Protheus usando APIs REST ou rotina SIGAFIS.",
        "metodo": "Envie o XML para a API REST 'MSFiscal' ou utilize job programado no módulo SIGAFIS (programa FISA030).",
        "observacoes": "Mapeie NCM e CFOP para as TES correspondentes. Ajuste cadastros de clientes antes do recebimento.",
    },
}


def build_integration_tools(df: pd.DataFrame) -> List[Tool]:
    def listar(_: str = "") -> str:
        lines = ["Integrações suportadas:"]
        for erp, meta in ERP_GUIDES.items():
            lines.append(f"- {erp.title()}: {meta['descricao']}")
        lines.append("Envie o nome do ERP para obter detalhes específicos.")
        return "\n".join(lines)

    def detalhar(erp: str) -> str:
        key = erp.strip().lower()
        meta = ERP_GUIDES.get(key)
        if not meta:
            return "ERP não catalogado. Informe Domínio, Alterdata ou Protheus."
        return (
            f"ERP: {erp.title()}\n"
            f"Descrição: {meta['descricao']}\n"
            f"Método sugerido: {meta['metodo']}\n"
            f"Cuidados: {meta['observacoes']}"
        )

    def checklist(_: str = "") -> str:
        return (
            "Checklist de integração fiscal:\n"
            "1. Validar cadastros de emitentes/destinatários (CNPJ, IE, endereço).\n"
            "2. Revisar CFOP x destino e códigos NCM.\n"
            "3. Gerar lote de XMLs assinados e armazenar com a mesma chave de acesso.\n"
            "4. Executar importação no ERP escolhido e conferir logs.\n"
            "5. Reprocessar notas com erro e emitir relatório para o time responsável."
        )

    return [
        Tool.from_function(
            func=listar,
            name="listar_erps",
            description="Lista ERPs suportados com visão geral de integração fiscal.",
        ),
        Tool.from_function(
            func=detalhar,
            name="detalhar_erp",
            description="Recebe o nome do ERP (Domínio, Alterdata, Protheus) e descreve o método de integração sugerido.",
        ),
        Tool.from_function(
            func=checklist,
            name="checklist_integracao",
            description="Retorna checklist resumido para integração de notas fiscais com ERPs.",
        ),
    ]
