def _safe_load_dotenv() -> None:
    """
    .env 로딩을 선택적으로 수행.
    python-dotenv가 설치되지 않았으면 조용히 무시한다.
    """
    try:
        from dotenv import load_dotenv
    except ImportError:
        # CI나 최소 의존 환경에서는 dotenv가 없어도 동작해야 하므로 무시
        return
    else:
        load_dotenv()