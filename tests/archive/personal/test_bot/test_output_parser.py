"""tests/test_bot/test_output_parser.py — parse_claude_output() 단위 테스트."""
from src.bot.output_parser import parse_claude_output, CodexDispatch, ApprovalEvent


def test_no_markers():
    """마커 없는 텍스트 → 빈 결과."""
    result = parse_claude_output("일반 텍스트입니다.")
    assert result.text == "일반 텍스트입니다."
    assert result.codex_dispatches == []
    assert result.approval_request is None


def test_single_codex_dispatch():
    """CODEX_DISPATCH 1개 정상 파싱."""
    text = '[CODEX_DISPATCH]{"description": "작업 A", "task_doc": ".agent/task/P8-1.md"}[/CODEX_DISPATCH]'
    result = parse_claude_output(text)
    assert len(result.codex_dispatches) == 1
    d = result.codex_dispatches[0]
    assert d.description == "작업 A"
    assert d.task_doc == ".agent/task/P8-1.md"
    assert d.executor == "local"
    assert result.text == text  # 원본 보존


def test_multiple_codex_dispatches():
    """CODEX_DISPATCH 여러 개 → 리스트에 모두 포함 (병렬 배정)."""
    text = (
        '[CODEX_DISPATCH]{"description": "작업 A"}[/CODEX_DISPATCH]'
        " 중간 텍스트 "
        '[CODEX_DISPATCH]{"description": "작업 B", "executor": "worktree"}[/CODEX_DISPATCH]'
    )
    result = parse_claude_output(text)
    assert len(result.codex_dispatches) == 2
    assert result.codex_dispatches[0].description == "작업 A"
    assert result.codex_dispatches[0].task_doc is None
    assert result.codex_dispatches[0].executor == "local"
    assert result.codex_dispatches[1].description == "작업 B"
    assert result.codex_dispatches[1].executor == "worktree"
    assert result.codex_dispatches[1].file_scope == []


def test_codex_dispatch_with_file_scope():
    """file_scope가 있으면 list[str]로 파싱한다."""
    text = (
        '[CODEX_DISPATCH]'
        '{"description": "작업 A", "file_scope": ["src/bot/output_parser.py", "src/bot/codex_runner.py"]}'
        '[/CODEX_DISPATCH]'
    )
    result = parse_claude_output(text)
    assert len(result.codex_dispatches) == 1
    assert result.codex_dispatches[0].file_scope == [
        "src/bot/output_parser.py",
        "src/bot/codex_runner.py",
    ]


def test_codex_dispatch_invalid_file_scope_fail_open():
    """file_scope 타입이 잘못되면 예외 없이 []로 처리한다."""
    text = (
        '[CODEX_DISPATCH]'
        '{"description": "작업 A", "file_scope": "src/bot/output_parser.py"}'
        '[/CODEX_DISPATCH]'
    )
    result = parse_claude_output(text)
    assert len(result.codex_dispatches) == 1
    assert result.codex_dispatches[0].file_scope == []


def test_approval_request():
    """APPROVAL_REQUEST 1개 정상 파싱."""
    text = '[APPROVAL_REQUEST]{"question": "삭제 승인?", "context": "DB 삭제 예정"}[/APPROVAL_REQUEST]'
    result = parse_claude_output(text)
    assert result.approval_request is not None
    assert result.approval_request.question == "삭제 승인?"
    assert result.approval_request.context == "DB 삭제 예정"
    assert result.codex_dispatches == []


def test_mixed_dispatch_and_approval():
    """CODEX_DISPATCH + APPROVAL_REQUEST 혼합."""
    text = (
        '[CODEX_DISPATCH]{"description": "파서 구현"}[/CODEX_DISPATCH]'
        '[APPROVAL_REQUEST]{"question": "배포 승인?"}[/APPROVAL_REQUEST]'
    )
    result = parse_claude_output(text)
    assert len(result.codex_dispatches) == 1
    assert result.codex_dispatches[0].description == "파서 구현"
    assert result.approval_request is not None
    assert result.approval_request.question == "배포 승인?"
    assert result.approval_request.context == ""


def test_json_parse_failure_skip():
    """JSON 파싱 실패 → 해당 항목 skip, 나머지 정상 파싱, 예외 미전파."""
    text = (
        '[CODEX_DISPATCH]not valid json[/CODEX_DISPATCH]'
        '[CODEX_DISPATCH]{"description": "정상 작업"}[/CODEX_DISPATCH]'
        '[APPROVAL_REQUEST]{broken}[/APPROVAL_REQUEST]'
    )
    result = parse_claude_output(text)
    assert len(result.codex_dispatches) == 1
    assert result.codex_dispatches[0].description == "정상 작업"
    assert result.approval_request is None
    assert result.text == text  # 원본 보존
