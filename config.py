""".env 파일에서 API 키를 읽는다. 외부 패키지 의존성 없음.

사용법:
    from config import get_api_key
    key = get_api_key()

직접 실행하면 키가 제대로 읽히는지 점검한다:
    python config.py
"""

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
ENV_PATH = PROJECT_ROOT / ".env"
PLACEHOLDER = "your-api-key-here"

# 모델 ID 기본값. check_api.py로 실제 사용 가능한 ID를 확인한 뒤
# .env의 GENERATOR_MODEL / CRITIC_MODEL로 재정의할 수 있다.
DEFAULT_MODELS = {
    "generator": "gemma-4-26b-a4b-it",  # 26B = 손 (구현. MoE, active 4B)
    "critic": "gemma-4-31b-it",     # 31B = 머리 (설계·비평)
}


def force_utf8_stdout() -> None:
    """윈도우 콘솔 cp949 인코딩 사고 방지. 스크립트 진입점에서 호출."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def load_env(path: Path = ENV_PATH) -> bool:
    """KEY=VALUE 형식의 .env 파일을 읽어 환경변수로 넣는다.

    이미 설정된 환경변수는 덮어쓰지 않는다. 파일이 없으면 False.
    """
    if not path.exists():
        return False
    # utf-8-sig: 윈도우 메모장이 붙이는 BOM까지 처리
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value
    return True


def get_api_key() -> str:
    """구글 AI Studio API 키를 반환한다. 없거나 미설정이면 RuntimeError."""
    load_env()
    key = os.environ.get("GOOGLE_API_KEY", "").strip()
    if not key or key == PLACEHOLDER:
        raise RuntimeError(
            "GOOGLE_API_KEY is not set. "
            "Copy .env.example to .env and put your API key in it."
        )
    return key


def get_model(role: str) -> str:
    """역할('generator'|'critic')에 해당하는 모델 ID를 반환한다."""
    if role not in DEFAULT_MODELS:
        raise ValueError(f"unknown role: {role!r} (use 'generator' or 'critic')")
    load_env()
    env_name = f"{role.upper()}_MODEL"
    return os.environ.get(env_name, DEFAULT_MODELS[role]).strip()


def main() -> int:
    if not ENV_PATH.exists():
        print("[ERROR] .env file not found.")
        print("        Copy .env.example to .env and put your API key in it.")
        return 1
    try:
        key = get_api_key()
    except RuntimeError:
        print("[ERROR] GOOGLE_API_KEY is missing or still the placeholder.")
        print("        Open .env and replace 'your-api-key-here' with your real key.")
        return 1
    masked = key[:4] + "..." + key[-4:] if len(key) >= 12 else "(too short?)"
    print(f"[OK] GOOGLE_API_KEY loaded: {masked} ({len(key)} chars)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
