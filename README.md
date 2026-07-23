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

## 寝落ち防止アラーム

アラーム追加画面の「種類」で「寝落ち防止アラーム」を選択すると、監視開始時刻から「就寝してよい時刻」まで Emfit の在床状態を監視します。監視時間は `18:00 → 翌 01:00` のような日付跨ぎにも対応し、曜日は監視を開始した日の曜日として扱います。

- 監視中に設定した時間だけ連続して在床すると、通常の目覚ましと同じ音源・音量・Echo・離床確認で鳴動します。鳴動までの時間は1～720分の範囲で1分単位に指定でき、既定値は20分です。
- 鳴動前に離床した場合も、離床を検知した時点から「再横臥を禁止する時間」を開始します。禁止時間が0分の場合は待機状態へ戻ります。
- 就寝してよい時刻の直前に横になった場合も、横になった時点が監視時間内なら設定時間の経過後に鳴動します。
- センサーが不明または古い場合は、誤発火を避けるためカウントを継続しません。
- 「再横臥を禁止する時間」は0～720分で指定できます。鳴動前・鳴動後を問わず離床が確認された時点から計測し、制限中に再入床すると待ち時間なしで即座に鳴動します。0分の場合は、再入床から新しい鳴動待ち時間を開始します。

既存の `alarm.db` は起動時に自動移行され、登録済みアラームは通常の目覚ましとして保持されます。

## 入床検知アナウンス

Emfitで安定した離床から入床への変化を検知すると、対象アラームと同じEcho・音量で「入床を検知しました」と一度だけ再生します。有効な通常目覚ましがあれば時刻を問わず、寝落ち防止アラームだけの場合はその監視時間内に通知します。

- アプリ起動時点ですでに在床している場合や、一時的なセンサー無応答から復帰した場合は誤通知しません。
- 通常目覚ましと寝落ち防止の両方が有効でも、一回の入床につき一度だけ通知します。
- アラーム鳴動中や再横臥禁止中はアラームを優先します。入床アナウンス中に本来のアラーム時刻になった場合も、アナウンスを中断してアラームを開始します。
- 音声はアプリ同梱の内部アセットを使うため、実行時の外部TTSサービスには依存しません。
