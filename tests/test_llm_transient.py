"""콜 래퍼의 일시 장애 분류 테스트 (콜 0)."""

from llm import _is_rate_limit, _is_transient


def test_transient_5xx_by_message():
    assert _is_transient(RuntimeError("500 INTERNAL"))
    assert _is_transient(RuntimeError("got 503 from server"))


def test_transient_socket_errors_by_message():
    # SDK가 소켓 에러를 자기 예외로 감싸면 isinstance에 안 걸린다 —
    # 메시지로 잡는지 확인 (WinError 10054 즉사 실관측)
    class SdkError(Exception):
        pass

    assert _is_transient(SdkError("[WinError 10054] 현재 연결은 원격 호스트에 "
                                  "의해 강제로 끊겼습니다"))
    assert _is_transient(SdkError("Connection reset by peer"))
    assert _is_transient(SdkError("request timed out"))


def test_transient_excludes_client_errors():
    assert not _is_transient(RuntimeError("400 INVALID_ARGUMENT"))
    assert not _is_transient(RuntimeError("permission denied"))


def test_rate_limit_not_transient_path():
    err = RuntimeError("429 RESOURCE_EXHAUSTED")
    assert _is_rate_limit(err)
    assert not _is_transient(err)
