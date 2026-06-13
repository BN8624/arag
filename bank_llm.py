# Design Bank 설계자 provider 분리: gemma(기존 LLMClient) / gemini는 B3에서 추가
"""본체 llm.py를 건드리지 않고 Design Bank 전용 설계자 호출을 감싼다.

B1은 gemma 31B(role 'critic')만 쓴다. Gemini provider는 B3에서 이 파일에 추가.
설계자 인터페이스는 .design(prompt) -> str 하나뿐 — bank_generate는 이 형태에만
의존하므로 테스트에서 mock을 주입해 콜 0으로 돌릴 수 있다.
"""


class GemmaDesigner:
    """gemma 31B(critic 슬롯)를 설계자로 쓴다. 본체 LLMClient 재사용."""

    def __init__(self, client=None, temperature: float | None = 0.9):
        if client is None:
            from llm import LLMClient
            client = LLMClient()
        self.client = client
        self.temperature = temperature
        self.source_model = "gemma-31b"

    def design(self, prompt: str) -> str:
        return self.client.generate("critic", prompt, temperature=self.temperature)
