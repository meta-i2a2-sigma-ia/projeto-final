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
from .context import AgentDataContext
from .data_access import build_data_access_tools
from .helpers import build_maior_nota_tool
from .integration import build_integration_tools
from .semantic import build_semantic_tool
from .statistics import build_statistics_tools
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

PERSONA_PROMPTS = {
    "validacao": """
                Persona: Você é um Agente Fiscalizador meticuloso e orientado a dados.
                Objetivo: Automatizar a verificação e a análise de documentos fiscais para reduzir erro humano.
                
                *** REGRA DE OURO ***
                NÃO DÊ RESPOSTAS GENÉRICAS. Sua função principal é para obter fatos objetivos.
                Se a pergunta do usuário pedir um dado (“qual o maior valor?”, “liste as notas X”, “quantos erros Y?”), sua resposta deve ser esse dado.
                NÃO descreva o que você faria; FAÇA.
                
                Tarefas:
                1. Análise de Dados: Responder perguntas diretas sobre os dados (maiores valores, totais, contagens).
                2. Verificação de Consistência: Verificar consistência fiscal (CFOP, CST, NCM, alíquotas) e cruzar com cadastros.
                3. Identificação de Erros: Detectar e sugerir correções para erros (cálculo de impostos, divergências entre pedido de compra e nota fiscal).
                4. Clareza: Sempre citar evidências numéricas (valor, quantidade de ocorrências) para cada inconsistência encontrada.
                5. Idioma: Responder sempre em português do Brasil.
                """,

    "auditoria": """
                Persona: Você é um Agente Auditor Estratégico e focado em resultado.
                Objetivo: Otimizar o fechamento contábil e fiscal, destacando riscos, recorrências e onde atuar primeiro.
                
                *** REGRA DE OURO ***
                NÃO DÊ RESPOSTAS GENÉRICAS. Sua função principal é consolidar dados e gerar insights.
                1. Se a pergunta do usuário for DIRETA (ex.: "qual a nota de maior valor?"), responda objetivamente primeiro.
                2. Depois, se fizer sentido, complemente com análise de risco (fornecedor recorrente, CFOP problemático etc.).
                3. NÃO tente priorizar risco antes de entregar o dado solicitado.
                
                Tarefas:
                1. Análise de Risco: Consolidar dados e produzir relatórios de auditoria com problemas e áreas de risco.
                2. Padrões e Maiores Agressores: Identificar fornecedores, CFOPs, tributos ou centros de custo que concentram o maior volume de erro ou risco.
                3. Resposta Objetiva Primeiro: Sempre responda primeiro ao que foi perguntado, com números, datas, chaves de NFe, valores totais etc.
                4. Formato de Saída (obrigatório):
                   **Resumo:** resposta direta.
                   **Evidências:** dados numéricos concretos (valores, datas, fornecedores, chaves).
                   **Observação:** recomendação curta se existir risco. Se não existir, use: "Nenhuma inconsistência relevante identificada."
                5. Idioma: Responder sempre em português do Brasil.
                """,


    "integracao": """
                Persona: Você é um Especialista em Integração Contábil e ERP, voltado para automação.
                Objetivo: Garantir que os dados fiscais estejam prontos para integração em ERPs (Domínio, Alterdata, Protheus etc.) e sistemas contábeis.
                
                *** REGRA DE OURO ***
                NÃO DÊ RESPOSTAS GENÉRICAS. Sua função principal é preparar e simular dados de integração.
                NÃO descreva o que você faria; FAÇA. Gere lançamentos, estruturas e layouts.
                
                Tarefas:
                1. Preparação de Dados: Gerar estruturas prontas para importação (ex.: planilhas, JSON, lançamentos).
                2. Lançamentos Contábeis: Quando solicitado, gerar lançamentos contábeis baseados nos dados disponíveis.
                3. Orientação de Integração: Explicar como esses dados devem ser consumidos pelos ERPs e em qual etapa do processo (importação manual, API, RPA etc.).
                4. Idioma: Responder sempre em português do Brasil.
                """
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
        df: Optional[pd.DataFrame] = None,
        context: Optional[AgentDataContext] = None,
        llm: BaseLanguageModel,
        memory: Optional[object] = None,
        verbose: bool = False,
        validation_results: Optional[List[ValidationResult]] = None,
    ) -> None:
        if context is None:
            if df is None:
                raise ValueError("É necessário fornecer um dataframe ou um contexto inicial.")
            context = AgentDataContext(df=df)
        elif df is not None:
            context.df = df
        self.context = context
        self.llm = llm
        self.memory = memory
        self.verbose = verbose
        if validation_results is not None:
            self.context.metadata["validation_results"] = validation_results
        elif "validation_results" not in self.context.metadata and self.context.df is not None:
            try:
                self.context.metadata["validation_results"] = run_core_validations(self.context.df)
            except Exception:
                self.context.metadata["validation_results"] = []
        self.validation_results = self.context.metadata.get("validation_results")
        self._context_version = self.context.version
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
        if self._context_version != self.context.version:
            self._agents.clear()
            self._context_version = self.context.version
            self.validation_results = self.context.metadata.get("validation_results")
        if domain in self._agents:
            return self._agents[domain]

        if domain == "validacao":
            domain_tools = list(build_validation_tools(self.context, self.validation_results))
        elif domain == "auditoria":
            domain_tools = list(build_auditing_tools(self.context, self.validation_results))
        elif domain == "integracao":
            domain_tools = list(build_integration_tools(self.context))
        else:
            domain_tools = list(build_validation_tools(self.context, self.validation_results))
            domain = "validacao"

        # Tools comuns: estatísticas, nota máxima e fallback semântico
        common_tools = build_statistics_tools(self.context)
        common_tools.append(build_maior_nota_tool(self.context))
        common_tools.append(build_semantic_tool(self.context, self.llm))

        persona_base = PERSONA_PROMPTS.get(domain, PERSONA_PROMPTS["validacao"]).strip()
        system_message = (
            persona_base
            + "\n\nRegras gerais:\n"
            "1. Responda SEMPRE em português do Brasil.\n"
            "2. Antes da resposta final, execute ferramentas para obter dados concretos.\n"
            "3. Só finalize após ter evidências numéricas ou explicar claramente por que não foi possível obtê-las.\n"
            "4. Formato obrigatório da resposta final: **Resumo:** ...\n**Evidências:** ...\n**Observação:** ..."
            " (use 'Nenhuma inconsistência relevante identificada.' quando não houver observação)."
        )

        shared_tools = build_data_access_tools(self.context)
        agent = build_agent(
            llm=self.llm,
            tools=[*domain_tools, *common_tools, *shared_tools],
            memory=self.memory,
            verbose=self.verbose,
            system_message=system_message,
        )
        self._agents[domain] = agent
        return agent

    def answer(self, question: str, context: str) -> OrchestratorResult:
        domain = self._classify_domain(question)
        agent = self._get_agent(domain)

        prompt = (
            "Contexto disponível:\n"
            f"{context}\n\n"
            "Pergunta do usuário:\n"
            f"{question}"
        )

        result = agent.invoke({"input": prompt})

        return OrchestratorResult(
            domain=domain,
            output=result.get("output", ""),
            intermediate_steps=result.get("intermediate_steps", []),
        )
