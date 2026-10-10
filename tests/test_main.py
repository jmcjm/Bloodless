import sys

from bloodless import __main__, cli, gui


def test_no_arguments_opens_the_window(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["bloodless"])
    monkeypatch.setattr(gui, "main", lambda: "window")
    monkeypatch.setattr(cli, "main", lambda: "command line")
    assert __main__.main() == "window"


def test_arguments_run_the_command_line(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["bloodless", "show"])
    monkeypatch.setattr(gui, "main", lambda: "window")
    monkeypatch.setattr(cli, "main", lambda: "command line")
    assert __main__.main() == "command line"
