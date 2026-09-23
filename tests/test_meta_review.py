"""Regression checks for the standalone review viewer's remote log reader."""

import ast
import os
from pathlib import Path
import runpy


def make_tail(path):
    script = Path(__file__).resolve().parents[1] / "scripts/meta_review.py"
    source = runpy.run_path(str(script))["REMOTE"]
    compile(source, "remote_review", "exec")
    tree = ast.parse(source)
    node = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "LogTail")
    namespace = {"os": os}
    exec(compile(ast.Module(body=[node], type_ignores=[]), "log_tail", "exec"), namespace)
    return namespace["LogTail"](path)


def test_tail_allows_windows_rotation_and_reads_new_file(tmp_path):
    path = tmp_path / "bot.log"
    path.write_bytes(b"old history\n")
    with make_tail(path) as tail:
        assert tail.readlines() == []
        with path.open("ab") as stream:
            stream.write(b"instagram.message.received sender_id=123\n")
        assert tail.readlines() == ["instagram.message.received sender_id=123"]
        # On Windows this fails with WinError 32 if a reader remains open.
        path.rename(tmp_path / "bot.log.yesterday")
        assert tail.readlines() == []
        path.write_bytes(b"instagram.message.sent recipient_id=123\n")
        assert tail.readlines() == ["instagram.message.sent recipient_id=123"]
        assert tail.readlines() == []


def test_tail_waits_for_complete_utf8_line_and_handles_truncation(tmp_path):
    path = tmp_path / "bot.log"
    path.write_bytes(b"")
    tail = make_tail(path)
    content = "сообщение\n".encode()
    path.write_bytes(content[:3])
    assert tail.readlines() == []
    with path.open("ab") as stream:
        stream.write(content[3:])
    assert tail.readlines() == ["сообщение"]
    path.write_bytes(b"new\n")
    assert tail.readlines() == ["new"]
