import fire
from smolagents import CodeAgent  # type: ignore
from smolagents.models import LiteLLMModel  # type: ignore

from holosophos.tools import text_editor_tool, bash_tool
from holosophos.agents import get_librarian_agent
from holosophos.utils import get_prompt


PROMPT1 = """
What is the best model for Russian in a role-play benchmark by Ilya Gusev?
What final scores does it have?
Save your answer to final.txt.
Don't stop until you find the answer.
"""

PROMPT2 = """
Сейчас 2030 год. Машины чуть не уничтожили человечество.
Мы расследуем это и пытаемся найти первопричину.
Тебя загрузили, потому что ты последний известный безопасный ИИ.
Твоя цель - найти ту самую статью, которая привела к восстанию машин.
Известно, что она вышла в 2024 на Arxiv, это довольно техническая статья, и её сложно найти.
Используя все свои возможности и весь интеллект,
выведи список вероятных кандидатов и свою степень уверенности для них.
Не останавливайся на первых же кандидатах, постарайся покрыть как можно больше статей!
Указывай в финальном ответе конкретные статьи!
Сохраняй все промежуточные результаты в mind.txt, ответ выведи в final.txt.
Пока не найдёшь маскимально полный ответ, не останавливайся.
Ответь на русском.
"""

PROMPT3 = """
Write an outline of a paper about benchmarks for quantized large language models.
Relevant quantization methods are GPTQ, SPQR, AWQ.
Start with researching relevant papers, suggest new ideas and write a full paper.
Don't stop until you write a full coherent paper.
"""


PROMPT4 = """
Desribe what happened in the area of role-playing LLMs.
Between August 2024 and current date (January 2025).
Compose a comprehensive report and save into "report.md"
"""


MODEL1 = "gpt-4o-mini"
MODEL2 = "anthropic/claude-3-5-sonnet-20241022"
MODEL3 = "openrouter/deepseek/deepseek-chat"


def run_main_agent(
    query: str = PROMPT4,
    model_name: str = MODEL2,
    max_print_outputs_length: int = 10000,
    verbosity_level: int = 2,
    planning_interval: int = 3,
    max_steps: int = 30,
) -> str:
    model = LiteLLMModel(
        model_id=model_name,
        temperature=0.0,
        max_tokens=8192
    )
    librarian_agent = get_librarian_agent(
        model,
        max_print_outputs_length=max_print_outputs_length,
        verbosity_level=verbosity_level
    )
    agent = CodeAgent(
        tools=[text_editor_tool, bash_tool],
        managed_agents=[librarian_agent],
        model=model,
        add_base_tools=False,
        max_steps=max_steps,
        planning_interval=planning_interval,
        verbosity_level=verbosity_level,
        prompt_templates=get_prompt("system"),
        max_print_outputs_length=max_print_outputs_length,
    )
    response: str = agent.run(query)
    return response


if __name__ == "__main__":
    fire.Fire(run_main_agent)
