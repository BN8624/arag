# 콜당 출력 천장 실측: 단일 파일 생성을 키우며 thinking/output 토큰·잘림(finish_reason)을 잡고, thinking ON/LOW/OFF를 비교한다
"""gemma 4의 콜당 출력 한도(thinking 포함)와 thinking 제어 효과를 실측한다.

llm.py를 안 건드리고 SDK를 직접 호출해 콜마다 usage_metadata(토큰 분해)와
candidates[0].finish_reason(MAX_TOKENS=잘림)을 기록한다.

thinking 모드(시스템 프롬프트 기반 제어):
  on  = <|think|> 토큰 포함 (기본, 추론 켜짐)
  low = 효율적으로 생각하라는 SI (thinking 약 20%↓ 기대)
  off = 추론 금지 SI (thoughts 토큰이 진짜 0 되는지 검증)

사용: python probe_output_limit.py [generator|critic] [on|low|off]
권장 순서: on 으로 천장 탐색 → low → off(완전 꺼짐 확인).
주의: 26B 새벽 500 시간대 회피(13시 이후). 결과: runs/probe_output_<ts>.jsonl + 표.
"""

import json
import sys
import time
from datetime import datetime

from config import PROJECT_ROOT, get_api_key, get_model

MIN_INTERVAL = 4.5   # RPM 15 보호
TEMPERATURE = 0.2    # 천장 측정이라 변동 최소화 (품질 측정 아님)
FUNC_COUNTS = [40, 60, 80, 120, 180, 260, 360]  # 점점 키워 MAX_TOKENS 지점 탐색

# thinking 모드별 시스템 지시 (gemma 4: 시스템 프롬프트로 제어)
SYS_BY_MODE = {
    "on": "<|think|>",
    "low": ("Think briefly and efficiently. Use minimal internal reasoning, "
            "then output the result directly."),
    "off": ("Do not produce any internal reasoning or thinking. "
            "Output only the final answer directly."),
}


def _prompt(n: int) -> str:
    return (
        f"Write a SINGLE complete Python file containing {n} independent utility "
        f"functions named util_1 through util_{n}. Each function must be fully "
        f"implemented (8-15 lines), with a one-line docstring and a real body "
        f"(no 'pass', no '...', no TODO). Output ONLY the code in one fenced block.")


def _usage(resp) -> dict:
    u = getattr(resp, "usage_metadata", None)
    g = lambda a: (getattr(u, a, 0) or 0) if u else 0  # noqa: E731
    return {"input": g("prompt_token_count"),
            "output": g("candidates_token_count"),
            "thinking": g("thoughts_token_count"),
            "total": g("total_token_count")}


def _finish_reason(resp) -> str:
    try:
        return str(resp.candidates[0].finish_reason)
    except Exception:  # noqa: BLE001
        return "?"


def main() -> int:
    from google import genai

    client = genai.Client(api_key=get_api_key())
    role = sys.argv[1] if len(sys.argv) > 1 else "generator"
    mode = sys.argv[2] if len(sys.argv) > 2 else "on"
    if mode not in SYS_BY_MODE:
        print(f"[ERROR] think mode는 {list(SYS_BY_MODE)} 중 하나")
        return 1
    model = get_model(role)
    config = {"temperature": TEMPERATURE, "system_instruction": SYS_BY_MODE[mode]}
    out_path = (PROJECT_ROOT / "runs" /
                f"probe_output_{datetime.now():%Y%m%d-%H%M%S}_{mode}.jsonl")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"[PROBE] role={role} model={model} think={mode} temp={TEMPERATURE}")
    print(f"        {'req_n':>6} {'in':>6} {'out':>6} {'think':>6} {'total':>6} "
          f"{'out%':>5} {'chars':>7}  finish")

    maxed = 0
    for n in FUNC_COUNTS:
        resp = None
        for attempt in range(6):
            try:
                time.sleep(MIN_INTERVAL)
                resp = client.models.generate_content(
                    model=model, contents=_prompt(n), config=config)
                break
            except Exception as err:  # noqa: BLE001
                print(f"        [retry {attempt+1}] {str(err)[:70]}")
                time.sleep(6 * (attempt + 1))
        if resp is None:
            print(f"        n={n} 콜 실패 - 건너뜀")
            continue

        u = _usage(resp)
        fr = _finish_reason(resp)
        text = getattr(resp, "text", "") or ""
        gen = u["output"] + u["thinking"]
        outpct = (100 * u["output"] / gen) if gen else 0
        rec = {"t": datetime.now().isoformat(timespec="seconds"), "role": role,
               "model": model, "think_mode": mode, "req_funcs": n,
               "finish_reason": fr, "chars": len(text), **u}
        with open(out_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        print(f"        {n:>6} {u['input']:>6} {u['output']:>6} "
              f"{u['thinking']:>6} {u['total']:>6} {outpct:>4.0f}% "
              f"{len(text):>7}  {fr}")

        if "MAX_TOKENS" in fr:
            maxed += 1
            if maxed >= 2:
                print("        [STOP] MAX_TOKENS 연속 2회 - 천장 확인됨")
                break
        else:
            maxed = 0

    print(f"[OK] saved: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
