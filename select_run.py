# 층2 오케스트레이션 바닥선: select-best(빔) — 약한 카드를 통과까지 반복, "몇 번에 깨지나" 측정
"""결정19 층2 진입점-a. 약한 카드를 N번까지 fresh 재시도하고, 게이트를 통과하는 첫
빌드를 채택(select-best with early stop)한다.

측정: 카드별 "첫 통과까지 시도 수" + 통과 여부. = 오케스트레이션 바닥선(무식한 retry로
frontier가 얼마 비용에 뚫리나). 부수효과: 실패마다 lessons 축적 → 이후 warm 캠페인 밑밥.

구성: 31단독(GENERATOR=CRITIC=31B) cold. 설계+오라클을 고정(frozen/<tid>)해 resume하므로
변수는 *구현 하나*다 — "좋은 설계·정답 오라클이 주어졌을 때 구현이 통합을 해내나"를 측정한다.
(설계 변수는 다음 단계에서 다른 고정설계로 스왑해 귀속.)

병렬: 시도들을 인-프로세스 스레드로 동시 실행(width). 워커=키 — 각 워커가 KeyPool에서
키 하나를 체크아웃해 그 키로 LLMClient를 만들고, 끝나면 반납한다. 키마다 쿼터(RPM 15)가
독립이라 진짜 병렬이 된다(키별 페이서가 같은 키 콜만 4초 직렬). 연속 리필: CAP개 시도를
한 번에 제출하고 슬롯이 비면 자동으로 다음을 당긴다(웨이브 배리어 없음). 첫 통과가 나오면
아직 시작 안 한 시도를 취소하고, 이미 도는 시도만 흘려보낸다(콜 절약).
주의: 병렬이라 "cracked_at = N번째 순차"의 순차 의미는 사라지고 "누적 시도수"가 된다.

장부: runs/select_ledger.jsonl
"""

import json
import os
import threading
from concurrent.futures import CancelledError, ThreadPoolExecutor, as_completed
from datetime import datetime

from config import PROJECT_ROOT, force_utf8_stdout, get_api_keys

CARDS = ["T-000012"]  # RPG 조립 카드(통합 frontier) 저항 검증
CAP = 8           # 카드당 최대 시도
MAX_MINUTES = 75  # per-attempt 시간 예산(통합 카드 4파일 생성이 다 끝나도록 40→75)
MODEL_31 = "gemma-4-31b-it"  # 31단독
MODEL_26 = "gemma-4-26b-a4b-it"  # 26B = 손
# 구성(arm): 머리·손 모델 매핑. 같은 frozen·오라클에 구성만 바꿔 비용↔통과율 비교한다.
ARMS = {
    "31solo": {"GENERATOR_MODEL": MODEL_31, "CRITIC_MODEL": MODEL_31},  # 신뢰 베이스라인
    "4home":  {"GENERATOR_MODEL": MODEL_26, "CRITIC_MODEL": MODEL_31},  # #4 26손/31머리
}
# 고정 설계+고정 오라클(손-박제 골든) — 구현만 변수로 두려고 resume한다.
FROZEN_DIR = PROJECT_ROOT / "frozen"
LEDGER = PROJECT_ROOT / "runs" / "select_ledger.jsonl"

_log_lock = threading.Lock()


def _log(entry: dict) -> None:
    with _log_lock:
        with open(LEDGER, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _run_attempt(tid: str, idea: str, attempt: int, frozen: str,
                 key: str) -> bool:
    """한 시도를 인-프로세스로 실행. cold, 자기 LLMClient(주입된 key에 바인딩)·
    run_dir(모델은 main이 env로 선점한 arm을 따른다). frozen=고정 설계·오라클
    디렉토리명(frozen/<frozen>). True=게이트 전부 통과."""
    from llm import LLMClient
    from orchestrator import Orchestrator

    run_dir = PROJECT_ROOT / "runs" / (
        datetime.now().strftime("%Y%m%d-%H%M%S") + f"-sel{attempt:02d}")
    llm = LLMClient(api_key=key)
    llm.record_path = run_dir / "llm_calls.jsonl"
    orch = Orchestrator(llm, run_dir, max_minutes=MAX_MINUTES,
                        task_id=tid, notes_enabled=False,  # cold
                        resume_from=FROZEN_DIR / frozen)  # 설계·오라클 고정
    try:
        return bool(orch.run(idea))
    except Exception as err:  # 한 시도의 폭주가 풀 전체를 죽이지 않게
        print(f"[SELECT] {tid} 시도 {attempt} 예외: {err}")
        return False


def main(argv=None) -> int:
    import sys
    force_utf8_stdout()
    # argv[1]=frozen 디렉토리명(기본 T-000012=설계A), argv[2]=arm(기본 31solo),
    # argv[3]=width(동시 워커수, 기본=키수와 CAP 중 작은 쪽).
    args = list(argv or sys.argv[1:])
    frozen = (args[0:1] or ["T-000012"])[0]
    arm = (args[1:2] or ["31solo"])[0]
    if arm not in ARMS:
        print(f"[SELECT] 알 수 없는 arm={arm!r}. 가능: {list(ARMS)}")
        return 2
    # load_env가 기존 env를 안 덮으므로 여기서 선점한다.
    for k, v in ARMS[arm].items():
        os.environ[k] = v

    from llm import KeyPool
    keys = get_api_keys()
    pool = KeyPool(keys)
    width = int(args[2]) if len(args) > 2 else min(len(keys), CAP)

    from bank_db import BankDB
    with BankDB() as db:
        cards = {t: db.get_task(t) for t in CARDS}

    print(f"[SELECT] select-best(cap {CAP}, width {width}/{len(keys)}키, "
          f"{MAX_MINUTES}분/시도) "
          f"arm={arm}({ARMS[arm]['GENERATOR_MODEL']}/{ARMS[arm]['CRITIC_MODEL']}) "
          f"cold — 약한칸 {CARDS}, 고정설계={frozen}")

    started_lock = threading.Lock()
    for tid in CARDS:
        idea = cards[tid]["goal"]
        cracked_at = None
        started = 0  # 실제로 키를 잡고 돈 시도 수(취소된 건 제외) = 누적 시도수

        def worker(attempt: int, _tid=tid, _idea=idea) -> bool:
            # 워커=키: 풀에서 키 하나를 빌려 그 키로만 26·31 콜, 끝나면 반납
            nonlocal started
            with pool.checkout() as key:
                with started_lock:
                    started += 1
                return _run_attempt(_tid, _idea, attempt, frozen, key)

        with ThreadPoolExecutor(max_workers=width) as ex:
            futs = {ex.submit(worker, a): a for a in range(1, CAP + 1)}
            for fut in as_completed(futs):
                a = futs[fut]
                try:
                    ok = fut.result()
                except CancelledError:
                    continue
                if ok and cracked_at is None:
                    cracked_at = a
                    # 첫 통과 — 아직 시작 안 한 시도는 취소(콜 절약), 도는 건 흘려보냄
                    for f in futs:
                        if not f.done():
                            f.cancel()

        _log({"t": datetime.now().isoformat(timespec="seconds"), "task_id": tid,
              "frozen": frozen, "arm": arm, "models": ARMS[arm],
              "cracked_at": cracked_at, "attempts": started,
              "cap": CAP, "parallel": width, "keys": len(keys)})
        msg = (f"{cracked_at}번째 시도에서 통과(누적 {started})" if cracked_at
               else f"{CAP}번 내 실패(누적 {started})")
        print(f"[SELECT] {tid} -> {msg}")
    print("[SELECT] 완료. 장부: runs/select_ledger.jsonl")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
