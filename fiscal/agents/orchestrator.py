"""High-level orchestrator that routes fiscal questions across specialized agents."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import pandas as pd
from langchain.agents import AgentExecutor
from langchain_core.language_models import BaseLanguageModel

from fiscal.domain import ValidationResult, run_core_validations

from .auditing import build_auditing_tools
from .base import build_agent
from .integration import build_integration_tools
from .validation import build_validation_tools

DOMAIN_LABELS = {
    "validacao": "validacao",
    "validação": "validacao",
    "validar": "validacao",
    "auditoria": "auditoria",
    "auditing": "auditoria",
    "relatorio": "auditoria",
    "relatório": "auditoria",
    "risco": "auditoria",
    "integracao": "integracao",
    "integração": "integracao",
    "erp": "integracao",
}

DOMAIN_DESCRIPTIONS = {
    "validacao": "aplicar regras fiscais automáticas (CFOP, NCM, ICMS, totais)",
    "auditoria": "consolidar indicadores de risco e apontar maiores reincidências",
    "integracao": "orientar integração de notas em ERPs e fluxos operacionais",
}


@dataclass
class OrchestratorResult:
    domain: str
    output: str
    intermediate_steps: List


class FiscalOrchestrator:
    def __init__(
        self,
        *,
        df: pd.DataFrame,
        llm: BaseLanguageModel,
        memory: Optional[object] = None,
        verbose: bool = False,
        validation_results: Optional[List[ValidationResult]] = None,
    ) -> None:
        self.df = df
        self.llm = llm
        self.memory = memory
        self.verbose = verbose
        self.validation_results = validation_results or run_core_validations(df)
        self._agents: Dict[str, Any] = {}

    def _classify_domain(self, question: str) -> str:
        prompt = (
            "Classifique a pergunta em VALIDACAO, AUDITORIA ou INTEGRACAO. "
            "Responda somente com uma dessas palavras em maiúsculo.\n"
            f"Pergunta: {question}"
        )
        try:
            label = (self.llm.invoke(prompt).content or "").strip().lower()
        except Exception:
            label = "validacao"
        return DOMAIN_LABELS.get(label, "validacao")

    def _get_agent(self, domain: str) -> AgentExecutor:
        if domain in self._agents:
            return self._agents[domain]

        if domain == "validacao":
            tools = build_validation_tools(self.df, self.validation_results)
        elif domain == "auditoria":
            tools = build_auditing_tools(self.df, self.validation_results)
        elif domain == "integracao":
            tools = build_integration_tools(self.df)
        else:
            tools = build_validation_tools(self.df, self.validation_results)
            domain = "validacao"

        agent = build_agent(llm=self.llm, tools=tools, memory=self.memory, verbose=self.verbose)
        self._agents[domain] = agent
        return agent

    def answer(self, question: str, context: str) -> OrchestratorResult:
        domain = self._classify_domain(question)
        agent = self._get_agent(domain)
        domain_desc = DOMAIN_DESCRIPTIONS.get(domain, "")
        instructions = (
            "Você é um especialista em {desc}. Use as ferramentas disponíveis.\n"
            "Regras:\n"
            "1. Responda sempre em português do Brasil.\n"
            "2. Cite evidências numéricas (valores, quantidade de ocorrências) quando adequado.\n"
            "3. Caso uma ferramenta retorne markdown, mantenha o formato.\n"
            "4. Ofereça recomendações práticas para o time fiscal."
        ).format(desc=domain_desc)
        prompt = (
            "VOCÊ DEVE RESPONDER EM PORTUGUÊS.\n"
            f"Contexto:\n{context}\n\n"
            f"Instruções específicas:\n{instructions}\n\n"
            f"Pergunta: {question}"
        )
        result = agent.invoke({"input": prompt})
        return OrchestratorResult(
            domain=domain,
            output=result.get("output", ""),
            intermediate_steps=result.get("intermediate_steps", []),
        )
