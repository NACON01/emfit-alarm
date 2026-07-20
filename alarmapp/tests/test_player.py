from __future__ import annotations

import json
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
def test_stream_active_matches_mpv_pid_and_caches(monkeypatch):
    class FakeProcess:
        pid = 4321
        def poll(self): return None

    pw_calls = []
    payload = [{"type": "PipeWire:Interface:Node", "info": {"props": {"application.process.id": "4321"}}}]
    monkeypatch.setattr(player.subprocess, "Popen", lambda args: FakeProcess())
    monkeypatch.setattr(
        player.subprocess,
        "run",
        lambda args, **kwargs: pw_calls.append(args) or SimpleNamespace(returncode=0, stdout=json.dumps(payload)),
    )
    alarm_player = player.BtPlayer("Miku-Miku Echo", "")
    alarm_player.play("/sounds/alarm.mp3", 1.0)
    alarm_player._play_started_ts -= player._PW_STREAM_START_GRACE_SEC

    assert alarm_player.stream_active() is True
    assert alarm_player.stream_active() is True
    assert pw_calls == [["pw-dump"]]


def test_stream_active_returns_unknown_during_start_grace(monkeypatch):
    pw_calls = []
    monkeypatch.setattr(player.subprocess, "Popen", lambda args: SimpleNamespace(pid=4321, poll=lambda: None))
    monkeypatch.setattr(player.subprocess, "run", lambda args, **kwargs: pw_calls.append(args))
    alarm_player = player.BtPlayer("Miku-Miku Echo", "")

    assert alarm_player.play("/sounds/alarm.mp3", 1.0) is True
    assert alarm_player.stream_active() is None
    assert pw_calls == []


def test_stream_active_returns_unknown_on_pw_dump_failure(monkeypatch):
    monkeypatch.setattr(
        player.subprocess,
        "run",
        lambda args, **kwargs: (_ for _ in ()).throw(FileNotFoundError("pw-dump")),
    )
    alarm_player = player.BtPlayer("Miku-Miku Echo", "")

    assert alarm_player.stream_active() is None


def test_restart_bt_stack_resets_connection_state(monkeypatch):
    calls = []
    sleeps = []
    monkeypatch.setattr(player.time, "sleep", lambda seconds: sleeps.append(seconds))
    monkeypatch.setattr(
        player.subprocess,
        "run",
        lambda args, **kwargs: calls.append((args, kwargs)) or SimpleNamespace(returncode=0, stderr=""),
    )
    alarm_player = player.BtPlayer("Miku-Miku Echo", "AA:BB:CC:DD:EE:FF")
    alarm_player._last_connected_check = 123.0
    alarm_player._connected = True

    assert alarm_player.restart_bt_stack() is True
    assert calls[0][0] == ["sudo", "-n", "systemctl", "restart", "bluetooth"]
    assert calls[0][1]["timeout"] == 20
    assert sleeps == [3]
    assert alarm_player._last_connected_check == 0.0
    assert alarm_player._connected is False


def test_restart_bt_stack_failure_is_nonfatal(monkeypatch):
    monkeypatch.setattr(
        player.subprocess,
        "run",
        lambda args, **kwargs: SimpleNamespace(returncode=1, stderr="not permitted"),
    )
    alarm_player = player.BtPlayer("Miku-Miku Echo", "AA:BB:CC:DD:EE:FF")

    assert alarm_player.restart_bt_stack() is False


def test_reconnect_cycles_bluetooth_connection(monkeypatch):
    calls = []
    monkeypatch.setattr(player.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(
        player.subprocess,
        "run",
        lambda args, **kwargs: calls.append(args) or SimpleNamespace(returncode=0, stdout=""),
    )
    alarm_player = player.BtPlayer("Miku-Miku Echo", "AA:BB:CC:DD:EE:FF")

    assert alarm_player.reconnect() is True
    assert calls == [
        ["bluetoothctl", "disconnect", "AA:BB:CC:DD:EE:FF"],
        ["bluetoothctl", "connect", "AA:BB:CC:DD:EE:FF"],
    ]