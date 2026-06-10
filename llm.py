"""API 콜 래퍼. 쿼터 4원칙 중 1·4를 여기서 강제한다.

- 순차 호출 (단일 스레드 전제, 동시 호출 없음)
- 콜 간 최소 간격 4초 (RPM 15 보호)
- 429 백오프 재시도
- 회차당 콜 수 상한 (가드레일)
"""

import re
import time

from config import get_api_key, get_model

MIN_INTERVAL_SEC = 4.0
MAX_RETRIES = 4
BACKOFF_BASE_SEC = 20.0  # 429 시 대기: 20, 40, 80, ...


class CallBudgetExceeded(Exception):
    """회차당 API 콜 상한 초과."""


class EmptyResponse(Exception):
    """모델이 빈 응답을 반환."""


def _is_rate_limit(err: Exception) -> bool:
    code = getattr(err, "code", None) or getattr(err, "status_code", None)
    if code == 429:
        return True
    return "429" in str(err) or "RESOURCE_EXHAUSTED" in str(err)


def _is_transient(err: Exception) -> bool:
    code = getattr(err, "code", None) or getattr(err, "status_code", None)
    if isinstance(code, int) and code >= 500:
        return True
    return bool(re.search(r"\b(500|502|503|504)\b", str(err)))


class LLMClient:
    def __init__(self, max_calls: int | None = None):
        # import을 여기서 해서, API를 안 쓰는 코드(게이트 등)는 SDK 없이도 돈다
        from google import genai

        self._client = genai.Client(api_key=get_api_key())
        self._last_call_at = 0.0
        self.call_count = 0
        self.max_calls = max_calls

    def _wait_interval(self) -> None:
        elapsed = time.monotonic() - self._last_call_at
        if elapsed < MIN_INTERVAL_SEC:
            time.sleep(MIN_INTERVAL_SEC - elapsed)

    def generate(self, role: str, prompt: str, temperature: float | None = None) -> str:
        """role('generator'|'critic')의 모델로 1콜. 텍스트를 반환한다."""
        if self.max_calls is not None and self.call_count >= self.max_calls:
            raise CallBudgetExceeded(
                f"call budget exhausted ({self.call_count}/{self.max_calls})"
            )
        model = get_model(role)
        config = {}
        if temperature is not None:
            config["temperature"] = temperature

        last_err: Exception | None = None
        for attempt in range(MAX_RETRIES + 1):
            self._wait_interval()
            try:
                self._last_call_at = time.monotonic()
                resp = self._client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=config or None,
                )
                self.call_count += 1
                text = getattr(resp, "text", None)
                if not text or not text.strip():
                    raise EmptyResponse(f"empty response from {model}")
                return text
            except EmptyResponse:
                raise
            except Exception as err:  # noqa: BLE001 - SDK 예외 타입이 유동적
                last_err = err
                if attempt >= MAX_RETRIES:
                    break
                if _is_rate_limit(err):
                    wait = BACKOFF_BASE_SEC * (2 ** attempt)
                    print(f"[WAIT] rate limited (429), retrying in {wait:.0f}s "
                          f"(attempt {attempt + 1}/{MAX_RETRIES})")
                    time.sleep(wait)
                elif _is_transient(err):
                    wait = 5.0 * (2 ** attempt)
                    print(f"[WAIT] server error, retrying in {wait:.0f}s "
                          f"(attempt {attempt + 1}/{MAX_RETRIES})")
                    time.sleep(wait)
                else:
                    raise
        raise RuntimeError(f"API call failed after {MAX_RETRIES} retries: {last_err}")
