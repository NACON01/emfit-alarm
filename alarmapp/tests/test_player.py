from __future__ import annotations

from types import SimpleNamespace

import player


def test_play_spawns_mpv_with_loop_and_volume(monkeypatch):
    commands = []

    class FakeProcess:
        def __init__(self, command):
            commands.append(command)
            self.returncode = None
        def poll(self):
            return self.returncode
        def terminate(self):
            self.returncode = 0
        def wait(self, timeout=None):
            return 0

    monkeypatch.setattr(player.subprocess, "Popen", FakeProcess)
    alarm_player = player.BtPlayer("Miku-Miku Echo", "")

    assert alarm_player.play("/sounds/alarm.mp3", 0.35) is True
    assert commands == [["mpv", "--no-video", "--really-quiet", "--loop=inf", "--volume=35", "/sounds/alarm.mp3"]]
    assert alarm_player.is_playing() is True


def test_play_non_loop_omits_loop(monkeypatch):
    command = []

    class FakeProcess:
        def poll(self): return None

    monkeypatch.setattr(player.subprocess, "Popen", lambda args: command.extend([args]) or FakeProcess())
    alarm_player = player.BtPlayer("Miku-Miku Echo", "")

    assert alarm_player.play("/sounds/short.mp3", 1.0, loop=False) is True
    assert "--loop=inf" not in command[0]


def test_ensure_connected_checks_and_caches(monkeypatch):
    calls = []
    info = SimpleNamespace(stdout="Connected: yes", returncode=0)
    monkeypatch.setattr(player.subprocess, "run", lambda args, **kwargs: calls.append(args) or info)
    alarm_player = player.BtPlayer("Miku-Miku Echo", "AA:BB:CC:DD:EE:FF")

    assert alarm_player.ensure_connected() is True
    assert alarm_player.ensure_connected() is True
    assert calls == [["bluetoothctl", "info", "AA:BB:CC:DD:EE:FF"]]