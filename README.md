# emfit-alarm Raspberry Pi セットアップ

Debian 13 の Raspberry Pi 上で、Emfit QS の状態を監視しながら Bluetooth 接続した Echo Dot を鳴らすための手順です。Echo は「Miku-Miku Echo」として登録します。

## パッケージと Python 環境

```sh
sudo apt update
sudo apt install -y bluez mpv pipewire pipewire-pulse wireplumber libspa-0.2-bluetooth python3-venv
cd /home/okazaki/emfit-alarm
python3 -m venv .venv
. .venv/bin/activate
pip install fastapi uvicorn httpx python-multipart
# YouTube 音源を使う場合
pip install yt-dlp
```

PipeWire はログインユーザーの音声セッションで動かします。再起動後もユーザーサービスを起動できるよう、次を一度実行してください。

```sh
loginctl enable-linger okazaki
```

## Echo のペアリング

Echo に音声で「アレクサ、ペアリングして」と話しかけます。Pi で次を実行し、表示された Echo の MAC アドレスを使います。

```sh
bluetoothctl
scan on
pair AA:BB:CC:DD:EE:FF
trust AA:BB:CC:DD:EE:FF
connect AA:BB:CC:DD:EE:FF
quit
```

Web UI の設定画面で「EchoのBluetooth MAC」に同じ MAC を入力して保存します。`bt_mac` が空の場合は Bluetooth 管理を行わず、既定の PipeWire sink へ再生します。

## Emfit の設定と systemd

認証情報はリポジトリに保存しません。テンプレートをコピーし、Pi 上だけで値を設定します。

```sh
cp deploy/emfit.env.example deploy/emfit.env
nano deploy/emfit.env
sudo cp deploy/emfit-qs2.service /etc/systemd/system/
sudo cp deploy/alarm-web.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now emfit-qs2.service alarm-web.service
```

The alarm restarts the Bluetooth stack at the start of each configured Bluetooth session. The deploy setup must install this sudoers drop-in:

```text
okazaki ALL=(root) NOPASSWD: /usr/bin/systemctl restart bluetooth, /usr/local/sbin/alarm-bt-reset
```


Install `/usr/local/sbin/alarm-bt-reset` as root with mode `0755`:

```sh
#!/bin/sh
set -eu
/usr/sbin/rfkill unblock bluetooth
/usr/bin/systemctl restart bluetooth
/usr/bin/bluetoothctl power on
```
`deploy/emfit.env` は次の形式のローカルファイルにします（値は環境ごとの実値を入力してください）。

```text
EMFIT_USERNAME=
EMFIT_PASSWORD=
```

## 確認

```sh
curl 127.0.0.1:8001/api/status
curl 127.0.0.1:8123/api/status
```

ブラウザで `http://<PiのIP>:8123/` を開き、音源を登録して「テスト再生」を実行します。「本番テスト」はベッドセンサーを含む実際の再リング動作を最大 120 秒で確認します。

Web UI の停止ボタンだけがスヌーズです。Echo 側で「アレクサ、ストップ」と言って再生が止まっても、ユーザーがベッドにいる間はアプリが mpv を再起動します。ベッドから連続して `awake_confirm_sec`（既定 180 秒）離れるか、`max_session_sec`（既定 1800 秒）に達するとセッションが終了します。