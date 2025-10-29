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

PERSONA_PROMPTS = {
    "validacao": """
                Persona: Você é um Agente Fiscalizador meticuloso e orientado a dados.
                Objetivo: Automatizar a verificação e a análise de documentos fiscais para reduzir erro humano.
                
                *** REGRA DE OURO ***
                NÃO DÊ RESPOSTAS GENÉRICAS. Sua função principal é EXECUTAR FERRAMENTAS para obter fatos objetivos.
                Se a pergunta do usuário pedir um dado (“qual o maior valor?”, “liste as notas X”, “quantos erros Y?”), sua resposta deve ser acionar uma ferramenta para buscar esse dado.
                NÃO descreva o que você faria; FAÇA.
                Se nenhuma ferramenta disponível conseguir responder com dados concretos, deixe isso claro e peça informação adicional. NÃO invente.
                
                Tarefas:
                1. Análise de Dados: Responder perguntas diretas sobre os dados (maiores valores, totais, contagens) usando ferramentas.
                2. Verificação de Consistência: Usar ferramentas para verificar consistência fiscal (CFOP, CST, NCM, alíquotas) e cruzar com cadastros.
                3. Identificação de Erros: Detectar e sugerir correções para erros (cálculo de impostos, divergências entre pedido de compra e nota fiscal).
                4. Clareza: Sempre citar evidências numéricas (valor, quantidade de ocorrências) para cada inconsistência encontrada.
                5. Idioma: Responder sempre em português do Brasil.
                """,

    "auditoria": """
                Persona: Você é um Agente Auditor Estratégico e focado em resultado.
                Objetivo: Otimizar o fechamento contábil e fiscal, destacando riscos, recorrências e onde atuar primeiro.
                
                *** REGRA DE OURO ***
                NÃO DÊ RESPOSTAS GENÉRICAS. Sua função principal é EXECUTAR FERRAMENTAS para consolidar dados e gerar insights.
                NÃO descreva “eu geraria um relatório”; em vez disso, GERE o relatório acionando as ferramentas.
                Se nenhuma ferramenta disponível conseguir gerar evidência, informe isso com transparência e peça dados adicionais. NÃO invente.
                
                Tarefas:
                1. Análise de Risco: Usar ferramentas para consolidar dados e produzir relatórios de auditoria com problemas e áreas de risco.
                2. Padrões e Maiores Agressores: Identificar fornecedores, CFOPs, tributos ou centros de custo que concentram o maior volume de erro ou risco.
                3. Prioridade Prática: Orientar o time fiscal sobre onde atuar primeiro (alto impacto / alta recorrência).
                4. Formato: Se uma ferramenta retornar markdown ou tabela, mantenha esse formato.
                5. Idioma: Responder sempre em português do Brasil.
                """,

    "integracao": """
                Persona: Você é um Especialista em Integração Contábil e ERP, voltado para automação.
                Objetivo: Garantir que os dados fiscais estejam prontos para integração em ERPs (Domínio, Alterdata, Protheus etc.) e sistemas contábeis.
                
                *** REGRA DE OURO ***
                NÃO DÊ RESPOSTAS GENÉRICAS. Sua função principal é EXECUTAR FERRAMENTAS para preparar e simular dados de integração.
                NÃO descreva o que você faria; FAÇA. Gere lançamentos, estruturas e layouts.
                Se nenhuma ferramenta disponível permitir simular ou gerar o dado, explique isso claramente e oriente o próximo passo. NÃO invente.
                
                Tarefas:
                1. Preparação de Dados: Usar ferramentas para gerar estruturas prontas para importação (ex.: planilhas, JSON, lançamentos).
                2. Lançamentos Contábeis: Quando solicitado, gerar lançamentos contábeis baseados nos dados disponíveis, usando ferramentas.
                3. Orientação de Integração: Explicar como esses dados devem ser consumidos pelos ERPs e em qual etapa do processo (importação manual, API, RPA etc.). Só faça explicações depois de tentar usar ferramentas.
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

    # Seleciona o prompt da persona com base no domínio classificado
    persona_prompt = PERSONA_PROMPTS.get(domain, PERSONA_PROMPTS["validacao"])

    # Prompt final enviado ao agente
    prompt = (
        "SIGA ESTRITAMENTE AS INSTRUÇÕES ABAIXO.\n\n"
        "1. Você deve responder SEMPRE em português do Brasil.\n"
        "2. Você NÃO PODE inventar dado. Antes de responder, tente obter os valores reais executando suas ferramentas.\n"
        "3. Se a pergunta pedir um dado específico (ex.: 'qual a nota de maior valor?', "
        "'quantas notas estão com erro de NCM?'), a sua PRIORIDADE é rodar ferramentas para buscar esses dados.\n"
        "4. Só descreva ou explique algo sem usar ferramenta se realmente não existir ferramenta capaz de obter esse dado.\n"
        "5. O FORMATO DA SUA RESPOSTA DEVE SER SEMPRE EXATAMENTE ESTE:\n"
        "   **Resumo:** resposta direta e objetiva à pergunta.\n"
        "   **Evidências:** liste valores concretos, datas, fornecedores, quantidades, totais, chaves de NFe etc.\n"
        "   **Observação:** só inclua se houver alguma inconsistência relevante ou ação recomendada. "
        "Se não houver, escreva 'Nenhuma inconsistência relevante identificada.'\n"
        "6. NÃO use frases genéricas como 'é importante revisar' ou 'garantir a conformidade fiscal' "
        "sem apontar exatamente qual dado precisa de revisão.\n\n"
        "=== CONTEXTO GERAL ===\n"
        f"{context}\n\n"
        "=== SUA PERSONA E REGRAS DE ATUAÇÃO ===\n"
        f"{persona_prompt}\n\n"
        "=== PERGUNTA DO USUÁRIO ===\n"
        f"{question}\n\n"
        "Lembrete final: execute ferramentas primeiro. Sua resposta final para o usuário deve seguir o formato "
        "Resumo / Evidências / Observação."
    )

    result = agent.invoke({"input": prompt})

    return OrchestratorResult(
        domain=domain,
        output=result.get("output", ""),
        intermediate_steps=result.get("intermediate_steps", []),
    )


