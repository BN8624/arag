"""오케스트레이터 단계 공통 상수·예외.

orchestrator.py와 phase_* 믹스인 모듈들이 공유한다.
(순환 import 없이 어디서든 가져갈 수 있는 잎(leaf) 모듈로 유지할 것.)
"""

K_MAX_FIX = 3          # 층마다 자가수정 상한
PARTIAL_PASS_RATE = 0.8  # 부분 합격 출하: 성공 신호 통과 + pytest 통과율 하한
DESIGN_ATTEMPTS = 3    # 설계 1회 + 재설계 2회
DEFAULT_ROUNDS = 1     # 비평-개선 바퀴 (반복 다듬기는 1/10 비용인 improve가 담당.
                       #  부분 합격이면 루프가 자동으로 2바퀴까지 허용)
DEFAULT_MAX_CALLS = 60
DEFAULT_MAX_MINUTES = 40
TEST_FILE = "test_acceptance.py"


class RunAborted(Exception):
    """가드레일 발동으로 회차 종료."""
