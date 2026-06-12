"""26B 장애 복구 감시 + 배치 자동 재시작 (1회성 감시자).

구글 API의 26B(generator)만 500을 뱉는 장애 상황에서 띄워두는 도구.
주기적으로 26B에 1콜 핑을 보내고, 성공하면 배치를 자동 시작한 뒤 종료한다.

안전장치:
  - 종료예약(STOP_AFTER_RUN)이 켜져 있으면 시작하지 않고 물러난다
  - 이미 뭔가 돌고 있으면(런/배치) dashboard.launch_batch의 busy 검사가 거부
  - 최대 감시 시간(기본 6시간)을 넘기면 포기하고 종료

사용법:
    python watch_resume.py                # 15분 간격, 회복 시 20회차 배치
    python watch_resume.py --runs 5 --interval-min 30
"""

import argparse
import sys
import time
from datetime import datetime

from config import STOP_FILE, force_utf8_stdout


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def ping_generator() -> tuple[bool, str]:
    """26B에 최소 1콜. (성공 여부, 응답/에러 요약)."""
    from llm import LLMClient
    try:
        text = LLMClient(max_calls=2).generate(
            "generator", "Reply with exactly: PONG")
        return True, text.strip().replace("\n", " ")[:40]
    except Exception as err:  # noqa: BLE001 - 장애 종류 불문 "아직 안 됨"
        return False, str(err)[:160]


def main() -> int:
    force_utf8_stdout()
    parser = argparse.ArgumentParser(description="26B recovery watcher")
    parser.add_argument("--runs", type=int, default=20,
                        help="회복 시 시작할 배치 회차 수 (기본 20)")
    parser.add_argument("--interval-min", type=float, default=15,
                        help="핑 간격(분, 기본 15)")
    parser.add_argument("--max-hours", type=float, default=6,
                        help="최대 감시 시간(기본 6시간)")
    args = parser.parse_args()

    deadline = time.time() + args.max_hours * 3600
    attempt = 0
    print(f"[{_now()}] watching for 26B recovery "
          f"(every {args.interval_min} min, up to {args.max_hours} h, "
          f"then batch --runs {args.runs})")
    while True:
        attempt += 1
        ok, info = ping_generator()
        if ok:
            print(f"[{_now()}] attempt {attempt}: 26B recovered ({info!r})")
            if STOP_FILE.exists():
                print(f"[{_now()}] stop flag is armed - NOT starting a batch")
                return 0
            from dashboard import launch_batch
            started, message = launch_batch(args.runs)
            print(f"[{_now()}] batch start: {started} - {message}")
            return 0 if started else 1
        print(f"[{_now()}] attempt {attempt}: 26B still down - {info}")
        if time.time() >= deadline:
            print(f"[{_now()}] max watch time exceeded - giving up")
            return 1
        time.sleep(args.interval_min * 60)


if __name__ == "__main__":
    sys.exit(main())
