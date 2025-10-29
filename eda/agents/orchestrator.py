"""High-level orchestrator that roteia perguntas entre agentes de domínio."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

import pandas as pd
# Compatibilidade com mudanças de namespace no LangChain
try:
    from langchain.memory import ConversationBufferMemory
except ModuleNotFoundError:
    try:
        from langchain.chains.conversation.memory import ConversationBufferMemory  # type: ignore
    except ModuleNotFoundError:
        try:
            from langchain_core.memory import ConversationBufferMemory  # type: ignore
        except ModuleNotFoundError as exc:
            raise ModuleNotFoundError(
                "Não foi possível importar ConversationBufferMemory. Verifique a instalação do pacote 'langchain'."
            ) from exc
from langchain_core.language_models import BaseLanguageModel

from .anomalies import build_anomaly_tools
from .base import build_agent
from .descriptive import build_descriptive_tools
from .patterns import build_pattern_tools
from .visualization import build_visual_tools


DOMAIN_LABELS = {
    "descritivo": "descritivo",
    "descricao": "descritivo",
    "description": "descritivo",
    "pattern": "padroes",
    "padrões": "padroes",
    "padroes": "padroes",
    "tendencias": "padroes",
    "tendência": "padroes",
    "outlier": "anomalias",
    "anomalia": "anomalias",
    "anomaly": "anomalias",
    "cluster": "anomalias",
    "visual": "visualizacao",
    "grafico": "visualizacao",
    "gráfico": "visualizacao",
    "chart": "visualizacao",
}

DOMAIN_DESCRIPTIONS = {
    "descritivo": "foco em estatísticas descritivas básicas",
    "padroes": "foco em padrões, tendências, frequências e correlações",
    "anomalias": "foco em detectar outliers e clusters",
    "visualizacao": "foco em recomendar ou preparar visualizações",
}


@dataclass
class OrchestratorResult:
    domain: str
    output: str
    intermediate_steps: list


class DomainOrchestrator:
    """Coordena agentes em diferentes perspectivas do EDA."""

    def __init__(
        self,
        *,
        df: pd.DataFrame,
        llm: BaseLanguageModel,
        memory: ConversationBufferMemory,
        verbose: bool = False,
    ) -> None:
        self.df = df
        self.llm = llm
        self.memory = memory
        self.verbose = verbose
        self._agents: Dict[str, Any] = {}

    # -----------------------------
    # Domain resolution
    # -----------------------------
    def _classify_domain(self, question: str) -> str:
        prompt = (
            "Classifique a pergunta do usuário em um domínio dentre: "
            "DESCRITIVO, PADROES, ANOMALIAS, VISUALIZACAO. "
            "Responda apenas com uma das quatro palavras listadas (use maiúsculas).\n"
            f"Pergunta: {question}"
        )
        try:
            resp = self.llm.invoke(prompt)
            label = (resp.content or "").strip().lower()
        except Exception:
            label = "descritivo"

        mapped = DOMAIN_LABELS.get(label, None)
        if mapped:
            return mapped
        if "visual" in label or "gráfico" in label:
            return "visualizacao"
        if "outlier" in label or "anom" in label or "cluster" in label:
            return "anomalias"
        if "padr" in label or "trend" in label:
            return "padroes"
        return "descritivo"

    # -----------------------------
    # Agent factory
    # -----------------------------
    def _get_agent(self, domain: str) -> AgentExecutor:
        if domain in self._agents:
            return self._agents[domain]

        tools_builder = {
            "descritivo": build_descriptive_tools,
            "padroes": build_pattern_tools,
            "anomalias": build_anomaly_tools,
            "visualizacao": build_visual_tools,
        }.get(domain)

        if not tools_builder:
            tools_builder = build_descriptive_tools
            domain = "descritivo"

        agent = build_agent(
            llm=self.llm,
            tools=tools_builder(self.df),
            memory=self.memory,
            verbose=self.verbose,
        )
        self._agents[domain] = agent
        return agent

    # -----------------------------
    # Public API
    # -----------------------------
    def answer(self, question: str, context: str) -> OrchestratorResult:
        domain = self._classify_domain(question)
        agent = self._get_agent(domain)

        domain_desc = DOMAIN_DESCRIPTIONS.get(domain, "")
        instructions = (
            "Você é um agente especializado em {desc}. Use as ferramentas disponíveis para responder.\n"
            "Siga as regras:\n"
            "1. Responda apenas em português (pt-BR), com linguagem natural e clara.\n"
            "2. Se um gráfico ajudar, utilize a ferramenta apropriada (quando disponível) para gerar um bloco CHART_SPEC.\n"
            "3. Indique medidas estatísticas relevantes (média, mediana, desvio) quando fizer sentido.\n"
            "4. Cite o impacto de outliers ou clusters quando aplicável."
        ).format(desc=domain_desc)

        prompt = (
            "VOCÊ DEVE RESPONDER SEMPRE EM PORTUGUÊS DO BRASIL.\n"
            "Evite termos em inglês e traduza conceitos técnicos quando apropriado.\n\n"
            f"Contexto analítico:\n{context}\n\n"
            f"Instruções do domínio:\n{instructions}\n\n"
            f"Pergunta do usuário: {question}"
        )

        result = agent.invoke({"input": prompt})
        return OrchestratorResult(
            domain=domain,
            output=result.get("output", ""),
            intermediate_steps=result.get("intermediate_steps", []),
        )
