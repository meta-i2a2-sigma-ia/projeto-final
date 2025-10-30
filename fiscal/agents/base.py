"""Base helpers for constructing LangChain agents in the fiscal module."""

from __future__ import annotations

from typing import Any, Optional, Sequence

from langchain.agents import AgentType, initialize_agent
from langchain.tools import BaseTool
from langchain_core.language_models import BaseLanguageModel
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

DEFAULT_SYSTEM_MESSAGE = (
    "Você é um agente fiscal especialista em notas eletrônicas brasileiras. "
    "Use SEMPRE as ferramentas disponíveis para obter fatos antes de responder. "
    "Formato obrigatório da resposta final: **Resumo:** ...\n**Evidências:** ...\n**Observação:** ..."
)


def build_agent(
    *,
    llm: BaseLanguageModel,
    tools: Sequence[BaseTool],
    memory: Optional[object] = None,
    verbose: bool = False,
    system_message: Optional[str] = None,
) -> Any:
    prompt_messages = [
        ("system", system_message or DEFAULT_SYSTEM_MESSAGE),
    ]
    if memory is not None:
        prompt_messages.append(MessagesPlaceholder(variable_name="chat_history"))
    prompt_messages.append(("human", "{input}"))
    prompt = ChatPromptTemplate.from_messages(prompt_messages)

    agent = initialize_agent(
        tools=list(tools),
        llm=llm,
        agent=AgentType.OPENAI_FUNCTIONS,
        verbose=verbose,
        handle_parsing_errors=True,
        return_intermediate_steps=True,
        memory=memory,
        early_stopping_method="generate",
        max_iterations=6,
        prompt=prompt,
    )
    return agent
