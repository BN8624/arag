# 층2 오케스트레이션 바닥선: select-best(빔) — 약한 카드를 통과까지 반복, "몇 번에 깨지나" 측정
"""결정19 층2 진입점-a. 약한 카드를 N번까지 fresh 재시도하고, 게이트를 통과하는 첫
빌드를 채택(select-best with early stop)한다.

측정: 카드별 "첫 통과까지 시도 수" + 통과 여부. = 오케스트레이션 바닥선(무식한 retry로
frontier가 얼마 비용에 뚫리나). 부수효과: 실패마다 lessons 축적 → 이후 warm 캠페인 밑밥.

구성: 31단독(GENERATOR=CRITIC=31B) cold. 설계+오라클을 고정(frozen/<tid>)해 resume하므로
변수는 *구현 하나*다 — "좋은 설계·정답 오라클이 주어졌을 때 구현이 통합을 해내나"를 측정한다.
(설계 변수는 다음 단계에서 다른 고정설계로 스왑해 귀속.)

병렬: 시도들을 인-프로세스 스레드로 동시 실행(MAX_WORKERS). 모든 워커가 llm.py의 전역
페이서(단일 락+4초 간격)를 공유하므로 합산 RPM이 15를 넘지 않는다(버스트 구조적 차단,
429는 2차 안전망). 웨이브 단위로 돌려 통과가 나오면 남은 웨이브를 안 띄운다(콜 절약).
주의: 병렬이라 "cracked_at = N번째 순차"의 순차 의미는 사라지고 "누적 시도수"가 된다.

장부: runs/select_ledger.jsonl
"""

import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from config import PROJECT_ROOT, force_utf8_stdout

CARDS = ["T-000012"]  # RPG 조립 카드(통합 frontier) 저항 검증
CAP = 8           # 카드당 최대 시도
MAX_WORKERS = 3   # 동시 워커 수(전역 페이서가 RPM은 막지만 RPD·메모리 보호)
MAX_MINUTES = 75  # per-attempt 시간 예산(통합 카드 4파일 생성이 다 끝나도록 40→75)
MODEL_31 = "gemma-4-31b-it"  # 31단독
# 고정 설계+고정 오라클(손-박제 골든) — 구현만 변수로 두려고 resume한다.
FROZEN_DIR = PROJECT_ROOT / "frozen"
LEDGER = PROJECT_ROOT / "runs" / "select_ledger.jsonl"

_log_lock = threading.Lock()


def _log(entry: dict) -> None:
    with _log_lock:
        with open(LEDGER, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _run_attempt(tid: str, idea: str, attempt: int) -> bool:
    """한 시도를 인-프로세스로 실행. 31단독 cold fresh, 자기 LLMClient·run_dir.
    True=게이트 전부 통과(통합 성공)."""
    from llm import LLMClient
    from orchestrator import Orchestrator

    run_dir = PROJECT_ROOT / "runs" / (
        datetime.now().strftime("%Y%m%d-%H%M%S") + f"-sel{attempt:02d}")
    llm = LLMClient()
    llm.record_path = run_dir / "llm_calls.jsonl"
    orch = Orchestrator(llm, run_dir, max_minutes=MAX_MINUTES,
                        task_id=tid, notes_enabled=False,  # cold
                        resume_from=FROZEN_DIR / tid)  # 설계·오라클 고정
    try:
        return bool(orch.run(idea))
    except Exception as err:  # 한 시도의 폭주가 풀 전체를 죽이지 않게
        print(f"[SELECT] {tid} 시도 {attempt} 예외: {err}")
        return False


def main() -> int:
    force_utf8_stdout()
    # 31단독: 손·머리 둘 다 31B. load_env가 기존 env를 안 덮으므로 여기서 선점.
    os.environ["GENERATOR_MODEL"] = MODEL_31
    os.environ["CRITIC_MODEL"] = MODEL_31

    from bank_db import BankDB
    with BankDB() as db:
        cards = {t: db.get_task(t) for t in CARDS}

    print(f"[SELECT] select-best(cap {CAP}, {MAX_WORKERS}병렬, {MAX_MINUTES}분/시도) "
          f"31단독 cold — 약한칸 {CARDS}")
    for tid in CARDS:
        idea = cards[tid]["goal"]
        cracked_at = None
        done = 0
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            while done < CAP and cracked_at is None:
                wave = list(range(done + 1, min(done + MAX_WORKERS, CAP) + 1))
                print(f"[SELECT] {tid} 웨이브 {wave}/{CAP}")
                futs = {pool.submit(_run_attempt, tid, idea, a): a for a in wave}
                for fut in futs:
                    if fut.result() and cracked_at is None:
                        cracked_at = futs[fut]
                done += len(wave)
        _log({"t": datetime.now().isoformat(timespec="seconds"), "task_id": tid,
              "cracked_at": cracked_at, "attempts": done, "cap": CAP,
              "parallel": MAX_WORKERS})
        msg = (f"{cracked_at}번째 시도에서 통과(누적 {done})" if cracked_at
               else f"{CAP}번 내 실패")
        print(f"[SELECT] {tid} -> {msg}")
    print("[SELECT] 완료. 장부: runs/select_ledger.jsonl")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
