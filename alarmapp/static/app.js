(function () {
  "use strict";

  const DAYS = ["月", "火", "水", "木", "金", "土", "日"];
  const DATE_DAYS = ["日曜日", "月曜日", "火曜日", "水曜日", "木曜日", "金曜日", "土曜日"];
  const stateTitles = {
    IDLE: "待機中",
    RINGING: "🔔 鳴動中",
    ACK_GRACE: "⏸ 一時停止中",
    OUT: "🚶 離床中",
    ENDED: "終了",
  };
  const endedText = {
    woke: "起床を確認しました",
    manual: "セッションを終了しました",
    timeout: "タイムアウトしました",
  };

  const $ = (id) => document.getElementById(id);
  const els = {
    liveClock: $("live-clock"),
    liveSeconds: $("live-seconds"),
    todayDate: $("today-date"),
    nextAlarmPill: $("next-alarm-pill"),
    sensorPill: $("sensor-pill"),
    sensorText: $("sensor-text"),
    ringingPanel: $("ringing-panel"),
    ringingTitle: $("ringing-title"),
    ringingLabel: $("ringing-label"),
    ringingMeta: $("ringing-meta"),
    stopRing: $("stop-ring"),
    testRing: $("test-ring"),
    testRealRing: $("test-real-ring"),
    alarmCount: $("alarm-count"),
    settingsToggle: $("settings-toggle"),
    settingsPanel: $("settings-panel"),
    settingsForm: $("settings-form"),
    settingsMessage: $("settings-message"),
    soundManagerFile: $("sound-manager-file"),
    managerDropZone: $("manager-drop-zone"),
    managerSelectedFileName: $("manager-selected-file-name"),
    managerAudioEditor: $("manager-audio-editor"),
    managerWaveformCanvas: $("manager-waveform-canvas"),
    managerWaveformWindow: $("manager-waveform-window"),
    managerTrimSelection: $("manager-trim-selection"),
    managerTrimDimLeft: $("manager-trim-dim-left"),
    managerTrimDimRight: $("manager-trim-dim-right"),
    managerTrimStartHandle: $("manager-trim-start-handle"),
    managerTrimEndHandle: $("manager-trim-end-handle"),
    managerTrimStartLabel: $("manager-trim-start-label"),
    managerTrimLengthLabel: $("manager-trim-length-label"),
    managerTrimEndLabel: $("manager-trim-end-label"),
    managerPreviewBtn: $("manager-preview-btn"),
    managerUploadFilename: $("manager-upload-filename"),
    managerDoUploadBtn: $("manager-do-upload-btn"),
    managerUploadStatus: $("manager-upload-status"),
    managerYoutubeUrl: $("manager-youtube-url"),
    managerYoutubeFilename: $("manager-youtube-filename"),
    managerDownloadYoutubeBtn: $("manager-download-youtube-btn"),
    managerYoutubeStatus: $("manager-youtube-status"),
    soundManagerList: $("sound-manager-list"),
    managerSoundPreviewPanel: $("manager-sound-preview-panel"),
    managerSoundPreviewTitle: $("manager-sound-preview-title"),
    managerSoundPreviewCurrent: $("manager-sound-preview-current"),
    managerSoundPreviewSeek: $("manager-sound-preview-seek"),
    managerSoundPreviewDuration: $("manager-sound-preview-duration"),
    soundManagerMessage: $("sound-manager-message"),
    alarmGrid: $("alarm-grid"),
    fabAdd: $("fab-add"),
    modalOverlay: $("modal-overlay"),
    modal: $("modal-alarm"),
    closeModal: $("close-modal"),
    cancelModal: $("cancel-modal"),
    form: $("alarm-form"),
    formError: $("form-error"),
    saveAlarm: $("save-alarm"),
    modalTitle: $("modal-title"),
    alarmId: $("alarm-id"),
    alarmKind: $("alarm-kind"),
    alarmTime: $("alarm-time"),
    alarmTimeLabel: $("alarm-time-label"),
    alarmMonitorStart: $("alarm-monitor-start"),
    alarmReentryBlockMin: $("alarm-reentry-block-min"),
    antiDozeTimeFields: $("anti-doze-time-fields"),
    antiDozeOptions: $("anti-doze-options"),
    alarmLabel: $("alarm-label"),
    alarmEnabled: $("alarm-enabled"),
    alarmWakeCheck: $("alarm-wake-check"),
    weekdayChips: $("weekday-chips"),
    soundTabs: $("sound-tabs"),
    soundList: $("alarm-sound-list"),
    soundPreviewPanel: $("alarm-sound-preview-panel"),
    soundPreviewTitle: $("alarm-sound-preview-title"),
    soundPreviewCurrent: $("alarm-sound-preview-current"),
    soundPreviewSeek: $("alarm-sound-preview-seek"),
    soundPreviewDuration: $("alarm-sound-preview-duration"),
    soundFile: $("alarm-sound-file"),
    soundUrl: $("alarm-sound-url"),
    youtubeUrl: $("alarm-youtube-url"),
    youtubeFilename: $("alarm-youtube-filename"),
    downloadYoutubeBtn: $("download-youtube-btn"),
    youtubeStatus: $("alarm-youtube-status"),
    dropZone: $("drop-zone"),
    selectedFileName: $("selected-file-name"),
    audioEditor: $("audio-editor"),
    waveformWrap: $("waveform-wrap"),
    waveformCanvas: $("waveform-canvas"),
    waveformWindow: $("waveform-window"),
    trimSelection: $("trim-selection"),
    trimDimLeft: $("trim-dim-left"),
    trimDimRight: $("trim-dim-right"),
    trimStartHandle: $("trim-start-handle"),
    trimEndHandle: $("trim-end-handle"),
    trimStartLabel: $("trim-start-label"),
    trimLengthLabel: $("trim-length-label"),
    trimEndLabel: $("trim-end-label"),
    previewBtn: $("preview-btn"),
    uploadFilename: $("upload-filename"),
    doUploadBtn: $("do-upload-btn"),
    uploadStatus: $("upload-status"),
    volume: $("alarm-volume"),
    volumeOutput: $("alarm-volume-output"),
    devices: $("alarm-devices"),
    deleteAlarm: $("delete-alarm"),
    settings: {
      emfit_enabled: $("setting-emfit-enabled"),
      awake_confirm_sec: $("setting-awake-confirm-sec"),
      grace_sec: $("setting-grace-sec"),
      poll_sec: $("setting-poll-sec"),
      ring_volume: $("setting-ring-volume"),
      none_continue_sec: $("setting-none-continue-sec"),
      max_session_sec: $("setting-max-session-sec"),
      default_devices: $("setting-default-devices"),
      bt_mac: $("setting-bt-mac"),
      fallback_url: $("setting-fallback-url"),
      ring_volume_output: $("setting-ring-volume-output"),
    },
  };

  let alarms = [];
  let sounds = [];
  let deviceNames = ["Miku-Miku Echo"];
  let activeSoundTab = "existing";
  let selectedDays = new Set();
  let previousState = "IDLE";
  let currentSettings = {};
  let pollTimer = null;
  let refreshTimer = null;
  let closeModalTimer = null;
  let previewAudio = null;
  let previewButton = null;
  let previewName = "";
  let previewTimer = null;

  async function api(path, options = {}) {
    const headers = options.body instanceof FormData ? {} : { "Content-Type": "application/json" };
    const response = await fetch(path, { headers, ...options });
    if (!response.ok) {
      let detail = response.statusText;
      try {
        const data = await response.json();
        detail = data.detail || detail;
      } catch (_err) {
        /* keep status text */
      }
      throw new Error(detail);
    }
    const text = await response.text();
    return text ? JSON.parse(text) : null;
  }

  async function safeApi(path, options, fallback) {
    try {
      return await api(path, options);
    } catch (err) {
      console.warn(path, err);
      return fallback;
    }
  }

  function pad(value) {
    return String(value).padStart(2, "0");
  }

  function updateClock() {
    const now = new Date();
    els.liveClock.textContent = `${pad(now.getHours())}:${pad(now.getMinutes())}`;
    els.liveSeconds.textContent = pad(now.getSeconds());
    els.todayDate.textContent = `${now.getFullYear()}年${now.getMonth() + 1}月${now.getDate()}日 ${DATE_DAYS[now.getDay()]}`;
  }

  function formatDuration(seconds) {
    const value = Math.max(0, Math.round(Number(seconds) || 0));
    const hours = Math.floor(value / 3600);
    const minutes = Math.floor((value % 3600) / 60);
    const secs = value % 60;
    if (hours) return `${hours}時間${minutes}分`;
    if (minutes) return `${minutes}分${secs}秒`;
    return `${secs}秒`;
  }

  function safeSoundName(name, fallbackBase = "sound") {
    const raw = String(name || "");
    const parts = raw.split(/[\\/]/);
    const filename = parts[parts.length - 1] || "";
    const cleaned = filename.replace(/[\u0000-\u001f\u007f]+/g, "").replace(/^[._\s]+|[._\s]+$/g, "");
    if (cleaned) return cleaned;
    return fallbackBase;
  }

  function safeRenameBase(name) {
    const base = safeSoundName(name, "sound").replace(/\.[^.]*$/, "").replace(/^[._\s]+|[._\s]+$/g, "");
    return base || "sound";
  }

  function sensorStatus(emfit) {
    const inBed = emfit && emfit.in_bed;
    if (inBed === true) return "🛏 在床";
    if (inBed === false) return "🚶 離床";
    return "❓ 応答なし";
  }

  function setPanelStateClass(state) {
    els.ringingPanel.classList.remove("state-idle", "state-ringing", "state-ack_grace", "state-out", "state-ended");
    els.ringingPanel.classList.add(`state-${String(state || "IDLE").toLowerCase()}`);
  }

  function updateSensorPill(emfit) {
    if (!els.sensorPill) return;
    const inBed = emfit && emfit.in_bed;
    let cls = "sensor-none";
    let text = "センサー応答なし";
    if (inBed === true) {
      cls = "sensor-in";
      text = "在床";
    } else if (inBed === false) {
      cls = "sensor-out";
      text = "離床";
    }
    els.sensorPill.classList.remove("sensor-in", "sensor-out", "sensor-none");
    els.sensorPill.classList.add(cls);
    els.sensorText.textContent = text;
    els.sensorPill.title = emfit && emfit.label ? `emfit: ${emfit.label}` : "emfit 在床センサー";
  }

  function updateStatus(status) {
    const state = status.state || "IDLE";
    const alarm = status.next_alarm;
    const antiDoze = status.anti_doze || {};
    updateSensorPill(status.emfit);
    if (antiDoze.state === "COUNTING" && antiDoze.remaining_sec != null) {
      els.nextAlarmPill.textContent = `寝落ち防止まで ${formatDuration(antiDoze.remaining_sec)}`;
      els.nextAlarmPill.title = antiDoze.label || "寝落ち防止アラーム";
    } else if (antiDoze.state === "COOLDOWN" && antiDoze.cooldown_remaining_sec != null) {
      els.nextAlarmPill.textContent = `再横臥禁止 あと ${formatDuration(antiDoze.cooldown_remaining_sec)}`;
      els.nextAlarmPill.title = "この間に横になると即座にアラームが鳴ります";
    } else if (alarm) {
      els.nextAlarmPill.textContent = `次のアラームまで ${formatDuration(alarm.seconds_until)}`;
      els.nextAlarmPill.title = `${alarm.time} ${alarm.label || ""}`.trim();
    } else {
      els.nextAlarmPill.textContent = "アラームなし";
      els.nextAlarmPill.removeAttribute("title");
    }

    if (state !== previousState) {
      els.ringingPanel.classList.remove("flash");
      void els.ringingPanel.offsetWidth;
      els.ringingPanel.classList.add("flash");
    }
    previousState = state;

    setPanelStateClass(state);
    els.stopRing.classList.toggle("hidden", state === "IDLE" || state === "ENDED");

    if (state === "IDLE") {
      els.ringingPanel.classList.add("hidden");
      return;
    }

    const parts = [sensorStatus(status.emfit)];
    if (state === "RINGING") {
      parts.push(`経過 ${formatDuration(status.session_elapsed)}`);
    }
    if (state === "ACK_GRACE") {
      parts.push(`再鳴動まで ${formatDuration(status.grace_remaining)}`);
    }
    if (state === "OUT") {
      parts.push(`離床 ${formatDuration(status.out_elapsed)}`);
      const awakeConfirmSec = Number(currentSettings.awake_confirm_sec);
      if (awakeConfirmSec > 0) {
        const remaining = Math.max(0, awakeConfirmSec - (Number(status.continuous_out_sec) || 0));
        parts.push(`起床判定まで ${formatDuration(remaining)}`);
      } else {
        parts.push(`起床判定中`);
      }
    }
    if (status.ended_reason) {
      parts.push(endedText[status.ended_reason] || status.ended_reason);
    }

    const ringingLabels = {
      RINGING: "音量変更・本体長押し停止・スヌーズで一時停止（起きなければ再び鳴ります）。止めるにはベッドから出てください。",
      ACK_GRACE: "一時停止中：このまま在床だと再び鳴ります",
      OUT: "離床を確認中：このまま起きていれば終了します",
    };
    els.ringingTitle.textContent = stateTitles[state] || state;
    const sessionPrefix = status.session_kind === "anti_doze" ? "寝落ち防止：" : "";
    els.ringingLabel.textContent = endedText[status.ended_reason]
      || (ringingLabels[state] ? `${sessionPrefix}${ringingLabels[state]}` : "")
      || status.session_label
      || (alarm ? `${alarm.time} ${alarm.label || ""}`.trim() : "アラーム");
    els.ringingMeta.textContent = parts.join(" · ");
    els.ringingPanel.classList.remove("hidden");
  }

  async function pollStatus() {
    const status = await safeApi("/api/status", undefined, null);
    if (status) updateStatus(status);
  }

  function setLoading(el, isLoading) {
    if (!el) return;
    el.classList.toggle("loading", Boolean(isLoading));
    if ("disabled" in el) el.disabled = Boolean(isLoading);
  }

  async function withLoading(el, fn) {
    setLoading(el, true);
    try {
      return await fn();
    } finally {
      setLoading(el, false);
    }
  }

  function delay(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  function isComposingInput(event) {
    const target = event.target;
    return Boolean(
      event.isComposing ||
      event.keyCode === 229 ||
      (target && target.dataset && target.dataset.composing === "true")
    );
  }

  function trackComposition(input) {
    if (!input) return;
    input.dataset.composing = "false";
    input.addEventListener("compositionstart", () => {
      input.dataset.composing = "true";
    });
    input.addEventListener("compositionend", () => {
      requestAnimationFrame(() => {
        input.dataset.composing = "false";
      });
    });
  }

  function bindEnterToDownload(input, button) {
    if (!input || !button) return;
    trackComposition(input);
    input.addEventListener("keydown", (event) => {
      if (event.key !== "Enter") return;
      if (isComposingInput(event)) {
        event.stopPropagation();
        return;
      }
      event.preventDefault();
      event.stopPropagation();
      button.click();
    });
  }

  const AudioEditor = {
    buffer: null,
    source: null,
    playbackContext: null,
    dragMode: null,
    dragPointerId: null,
    dragStartValue: 0,
    dragStartTrimStart: 0,
    dragStartTrimEnd: 1000,
    trimStartValue: 0,
    trimEndValue: 1000,
    restartPreviewTimer: null,

    secToLabel(seconds) {
      const safeSeconds = Math.max(0, Number(seconds) || 0);
      const minutes = Math.floor(safeSeconds / 60);
      return `${minutes}:${(safeSeconds % 60).toFixed(1).padStart(4, "0")}`;
    },

    setStatus(message, type) {
      els.uploadStatus.textContent = message || "";
      els.uploadStatus.classList.toggle("success", type === "success");
      els.uploadStatus.classList.toggle("error", type === "error");
    },

    sanitizeWavName(name) {
      const raw = String(name || "alarm");
      const filename = raw.split(/[\\/]/).pop() || "alarm";
      const base = safeRenameBase(filename.replace(/\.[^.]*$/, "") || "alarm");
      return `${base}.wav`;
    },

    defaultDisplayName(name) {
      return safeSoundName(name || "alarm.wav", "alarm.wav");
    },

    getAudioContext() {
      const AudioContextCtor = window.AudioContext || window.webkitAudioContext;
      if (!AudioContextCtor) throw new Error("このブラウザは音声編集に対応していません");
      return new AudioContextCtor();
    },

    readFileAsArrayBuffer(file) {
      return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result);
        reader.onerror = () => reject(reader.error || new Error("ファイルを読み込めませんでした"));
        reader.readAsArrayBuffer(file);
      });
    },

    async decodeFile(file) {
      if (!file) {
        this.reset();
        return;
      }
      this.stopPreview();
      this.buffer = null;
      els.audioEditor.classList.remove("hidden");
      this.setStatus("デコード中...", "");
      try {
        const context = this.getAudioContext();
        const arrayBuffer = await this.readFileAsArrayBuffer(file);
        const decoded = await new Promise((resolve, reject) => {
          const result = context.decodeAudioData(arrayBuffer, resolve, reject);
          if (result && typeof result.then === "function") result.then(resolve, reject);
        });
        if (context.close) context.close();
        this.buffer = decoded;
        this.setTrimValues(0, 1000);
        els.uploadFilename.value = this.defaultDisplayName(file.name);
        this.drawWaveform();
        this.updateTrim();
        this.setStatus("", "");
        els.audioEditor.classList.remove("hidden");
      } catch (err) {
        console.warn("audio decode failed", err);
        this.reset();
        els.audioEditor.classList.remove("hidden");
        this.setStatus(`エラー: ${err.message || "デコードできませんでした"}`, "error");
      }
    },

    currentTrim() {
      if (!this.buffer) return { startSec: 0, endSec: 0 };
      const startSec = (this.trimStartValue / 1000) * this.buffer.duration;
      const endSec = (this.trimEndValue / 1000) * this.buffer.duration;
      return { startSec, endSec };
    },

    setTrimValues(start, end) {
      let nextStart = Math.max(0, Math.min(999, Math.round(Number(start) || 0)));
      let nextEnd = Math.max(1, Math.min(1000, Math.round(Number(end) || 0)));
      if (nextStart >= nextEnd) {
        if (nextEnd >= 1000) nextStart = 999;
        else nextEnd = nextStart + 1;
      }
      this.trimStartValue = nextStart;
      this.trimEndValue = nextEnd;
    },

    updateTrim(activePart) {
      if (!this.buffer) return;
      this.setTrimValues(this.trimStartValue, this.trimEndValue);
      const { startSec, endSec } = this.currentTrim();
      els.trimStartLabel.textContent = this.secToLabel(startSec);
      els.trimEndLabel.textContent = this.secToLabel(endSec);
      els.trimLengthLabel.textContent = this.secToLabel(Math.max(0, endSec - startSec));
      this.updateSelectionWindow(activePart);
      if (activePart && this.source) this.schedulePreviewRestart();
    },

    updateSelectionWindow(activePart) {
      const left = this.trimStartValue / 10;
      const width = (this.trimEndValue - this.trimStartValue) / 10;
      els.trimDimLeft.style.width = `${left}%`;
      els.trimDimRight.style.left = `${left + width}%`;
      els.trimDimRight.style.width = `${Math.max(0, 100 - left - width)}%`;
      els.trimSelection.style.left = `${left}%`;
      els.trimSelection.style.width = `${width}%`;
      els.trimStartHandle.classList.toggle("is-active", activePart === "start");
      els.trimEndHandle.classList.toggle("is-active", activePart === "end");
      els.trimSelection.classList.toggle("is-active", activePart === "move");
      els.trimStartHandle.setAttribute("aria-valuenow", String(this.trimStartValue));
      els.trimEndHandle.setAttribute("aria-valuenow", String(this.trimEndValue));
    },

    valueFromEvent(event) {
      const rect = els.waveformWindow.getBoundingClientRect();
      const point = event.touches && event.touches.length ? event.touches[0] : event;
      const ratio = Math.max(0, Math.min(1, (point.clientX - rect.left) / rect.width));
      return Math.round(ratio * 1000);
    },

    modeFromTarget(target, value) {
      if (target === els.trimStartHandle) return "start";
      if (target === els.trimEndHandle) return "end";
      if (target === els.trimSelection || els.trimSelection.contains(target)) return "move";
      const edgeTolerance = 28;
      const rect = els.waveformWindow.getBoundingClientRect();
      const pxPerValue = rect.width / 1000;
      const startDistance = Math.abs(value - this.trimStartValue) * pxPerValue;
      const endDistance = Math.abs(value - this.trimEndValue) * pxPerValue;
      if (startDistance <= edgeTolerance || endDistance <= edgeTolerance) {
        return startDistance <= endDistance ? "start" : "end";
      }
      if (value > this.trimStartValue && value < this.trimEndValue) return "move";
      return value <= this.trimStartValue ? "start" : "end";
    },

    applyDrag(value) {
      if (this.dragMode === "start") {
        this.setTrimValues(Math.min(value, this.trimEndValue - 1), this.trimEndValue);
      } else if (this.dragMode === "end") {
        this.setTrimValues(this.trimStartValue, Math.max(value, this.trimStartValue + 1));
      } else if (this.dragMode === "move") {
        const delta = value - this.dragStartValue;
        const length = this.dragStartTrimEnd - this.dragStartTrimStart;
        let start = this.dragStartTrimStart + delta;
        start = Math.max(0, Math.min(1000 - length, start));
        this.setTrimValues(start, start + length);
      }
      this.updateTrim(this.dragMode);
    },

    startDrag(event) {
      if (!this.buffer) return;
      event.preventDefault();
      const value = this.valueFromEvent(event);
      this.dragMode = this.modeFromTarget(event.target, value);
      this.dragPointerId = event.pointerId;
      this.dragStartValue = value;
      this.dragStartTrimStart = this.trimStartValue;
      this.dragStartTrimEnd = this.trimEndValue;
      if (els.waveformWindow.setPointerCapture && event.pointerId != null) {
        els.waveformWindow.setPointerCapture(event.pointerId);
      }
      if (this.dragMode !== "move") this.applyDrag(value);
      else this.updateTrim("move");
    },

    drag(event) {
      if (!this.dragMode) return;
      if (this.dragPointerId != null && event.pointerId != null && event.pointerId !== this.dragPointerId) return;
      event.preventDefault();
      this.applyDrag(this.valueFromEvent(event));
    },

    endDrag(event) {
      if (els.waveformWindow.releasePointerCapture && this.dragPointerId != null) {
        try {
          els.waveformWindow.releasePointerCapture(this.dragPointerId);
        } catch (_err) {
          /* pointer may already be released */
        }
      }
      this.dragMode = null;
      this.dragPointerId = null;
      this.updateTrim();
    },

    drawWaveform() {
      const canvas = els.waveformCanvas;
      if (!canvas || !this.buffer) return;
      const context = canvas.getContext("2d");
      const width = canvas.width;
      const height = canvas.height;
      const mid = height / 2;
      const channelData = [];
      for (let c = 0; c < this.buffer.numberOfChannels; c++) channelData.push(this.buffer.getChannelData(c));
      const samplesPerPixel = Math.max(1, Math.floor(this.buffer.length / width));
      context.clearRect(0, 0, width, height);
      context.fillStyle = getComputedStyle(document.documentElement).getPropertyValue("--bg-card2").trim() || "#21262d";
      context.fillRect(0, 0, width, height);
      context.strokeStyle = getComputedStyle(document.documentElement).getPropertyValue("--accent").trim() || "#20c997";
      context.lineWidth = 1;
      for (let x = 0; x < width; x++) {
        const start = x * samplesPerPixel;
        const end = Math.min(start + samplesPerPixel, this.buffer.length);
        let peak = 0;
        for (let i = start; i < end; i++) {
          for (let c = 0; c < channelData.length; c++) {
            const value = Math.abs(channelData[c][i]);
            if (value > peak) peak = value;
          }
        }
        const barHeight = Math.max(1, peak * (height - 8));
        context.beginPath();
        context.moveTo(x + 0.5, mid - barHeight / 2);
        context.lineTo(x + 0.5, mid + barHeight / 2);
        context.stroke();
      }
    },

    async togglePreview() {
      if (!this.buffer) return;
      if (this.source) {
        this.stopPreview();
        return;
      }
      const { startSec, endSec } = this.currentTrim();
      const duration = Math.max(0.01, endSec - startSec);
      const context = this.playbackContext || this.getAudioContext();
      this.playbackContext = context;
      if (context.state === "suspended" && context.resume) await context.resume();
      const source = context.createBufferSource();
      source.buffer = this.buffer;
      source.connect(context.destination);
      source.onended = () => {
        if (this.source === source) {
          this.source = null;
          els.previewBtn.textContent = "▶ プレビュー";
        }
      };
      this.source = source;
      els.previewBtn.textContent = "⏹ 停止";
      source.start(0, startSec, duration);
    },

    schedulePreviewRestart() {
      if (this.restartPreviewTimer) clearTimeout(this.restartPreviewTimer);
      this.restartPreviewTimer = setTimeout(() => {
        this.restartPreviewTimer = null;
        this.restartPreviewFromTrim();
      }, 80);
    },

    async restartPreviewFromTrim() {
      if (!this.buffer || !this.source) return;
      this.stopPreview({ keepButtonPlaying: true });
      try {
        await this.togglePreview();
      } catch (err) {
        console.warn("preview restart failed", err);
        this.stopPreview();
      }
    },

    stopPreview(options = {}) {
      if (this.restartPreviewTimer) {
        clearTimeout(this.restartPreviewTimer);
        this.restartPreviewTimer = null;
      }
      if (this.source) {
        const source = this.source;
        this.source = null;
        source.onended = null;
        try {
          source.stop();
        } catch (_err) {
          /* source may already be stopped */
        }
      }
      if (els.previewBtn && !options.keepButtonPlaying) els.previewBtn.textContent = "▶ プレビュー";
    },

    encodeWav(buffer, startSec, endSec) {
      const sampleRate = buffer.sampleRate;
      const numChannels = buffer.numberOfChannels;
      const startSample = Math.floor(startSec * sampleRate);
      const endSample = Math.min(Math.ceil(endSec * sampleRate), buffer.length);
      const numSamples = Math.max(0, endSample - startSample);
      const byteCount = numSamples * numChannels * 2;
      const arrayBuffer = new ArrayBuffer(44 + byteCount);
      const view = new DataView(arrayBuffer);
      this.writeStr(view, 0, "RIFF");
      view.setUint32(4, 36 + byteCount, true);
      this.writeStr(view, 8, "WAVE");
      this.writeStr(view, 12, "fmt ");
      view.setUint32(16, 16, true);
      view.setUint16(20, 1, true);
      view.setUint16(22, numChannels, true);
      view.setUint32(24, sampleRate, true);
      view.setUint32(28, sampleRate * numChannels * 2, true);
      view.setUint16(32, numChannels * 2, true);
      view.setUint16(34, 16, true);
      this.writeStr(view, 36, "data");
      view.setUint32(40, byteCount, true);
      let offset = 44;
      const channels = [];
      for (let c = 0; c < numChannels; c++) channels.push(buffer.getChannelData(c));
      for (let i = startSample; i < endSample; i++) {
        for (let c = 0; c < numChannels; c++) {
          const sample = Math.max(-1, Math.min(1, channels[c][i]));
          view.setInt16(offset, sample < 0 ? sample * 0x8000 : sample * 0x7FFF, true);
          offset += 2;
        }
      }
      return new Blob([arrayBuffer], { type: "audio/wav" });
    },

    writeStr(view, offset, str) {
      for (let i = 0; i < str.length; i++) view.setUint8(offset + i, str.charCodeAt(i));
    },

    async upload() {
      if (!this.buffer) {
        els.audioEditor.classList.remove("hidden");
        this.setStatus("まずファイルを選択してください", "error");
        return;
      }
      const originalText = els.doUploadBtn.textContent;
      const finalName = this.sanitizeWavName(els.uploadFilename.value);
      els.uploadFilename.value = finalName;
      setLoading(els.doUploadBtn, true);
      els.doUploadBtn.textContent = "アップロード中...";
      this.setStatus("", "");
      try {
        const { startSec, endSec } = this.currentTrim();
        const wavBlob = this.encodeWav(this.buffer, startSec, endSec);
        const formData = new FormData();
        formData.append("file", wavBlob, finalName);
        const response = await fetch("/api/sounds", { method: "POST", body: formData });
        if (!response.ok) throw new Error(String(response.status));
        let uploaded = null;
        try {
          uploaded = await response.json();
        } catch (_err) {
          /* upload endpoint may return an empty response */
        }
        const uploadedName = uploaded && uploaded.name ? uploaded.name : finalName;
        await loadSounds();
        ensureSoundOption(uploadedName);
        setSoundTab("existing");
        setSelectedSounds([uploadedName]);
        this.setStatus("✓ アップロード完了", "success");
        this.reset({ keepStatus: true });
      } catch (err) {
        this.setStatus(`エラー: ${err.message || "アップロードできませんでした"}`, "error");
      } finally {
        els.doUploadBtn.textContent = originalText;
        setLoading(els.doUploadBtn, false);
      }
    },

    reset(options = {}) {
      this.stopPreview();
      this.buffer = null;
      this.dragMode = null;
      this.dragPointerId = null;
      this.setTrimValues(0, 1000);
      if (els.soundFile) els.soundFile.value = "";
      if (els.selectedFileName) els.selectedFileName.textContent = "未選択";
      if (els.uploadFilename) els.uploadFilename.value = "";
      if (els.audioEditor) els.audioEditor.classList.add("hidden");
      if (els.trimStartLabel) els.trimStartLabel.textContent = "0:00.0";
      if (els.trimEndLabel) els.trimEndLabel.textContent = "0:00.0";
      if (els.trimLengthLabel) els.trimLengthLabel.textContent = "0:00.0";
      if (els.trimSelection) this.updateSelectionWindow();
      if (!options.keepStatus) this.setStatus("", "");
    },
  };

  function createManagedAudioEditor(refs) {
    return {
      buffer: null,
      source: null,
      playbackContext: null,
      dragMode: null,
      dragPointerId: null,
      dragStartValue: 0,
      dragStartTrimStart: 0,
      dragStartTrimEnd: 1000,
      trimStartValue: 0,
      trimEndValue: 1000,
      restartPreviewTimer: null,
      editingSoundName: null,

      secToLabel: AudioEditor.secToLabel,
      sanitizeWavName: AudioEditor.sanitizeWavName,
      defaultDisplayName: AudioEditor.defaultDisplayName,
      getAudioContext: AudioEditor.getAudioContext,
      readFileAsArrayBuffer: AudioEditor.readFileAsArrayBuffer,
      encodeWav: AudioEditor.encodeWav,
      writeStr: AudioEditor.writeStr,

      setStatus(message, type) {
        refs.uploadStatus.textContent = message || "";
        refs.uploadStatus.classList.toggle("success", type === "success");
        refs.uploadStatus.classList.toggle("error", type === "error");
      },

      async decodeArrayBuffer(arrayBuffer, displayName, options = {}) {
        this.stopPreview();
        this.buffer = null;
        refs.audioEditor.classList.remove("hidden");
        this.setStatus("デコード中...", "");
        try {
          const context = this.getAudioContext();
          const decoded = await new Promise((resolve, reject) => {
            const result = context.decodeAudioData(arrayBuffer, resolve, reject);
            if (result && typeof result.then === "function") result.then(resolve, reject);
          });
          if (context.close) context.close();
          this.buffer = decoded;
          this.editingSoundName = options.editingSoundName || null;
          this.setTrimValues(0, 1000);
          refs.uploadFilename.value = options.outputName || this.defaultDisplayName(displayName);
          refs.doUploadBtn.textContent = this.editingSoundName ? "トリミング保存" : "アップロード";
          this.drawWaveform();
          this.updateTrim();
          this.setStatus("", "");
          refs.audioEditor.classList.remove("hidden");
        } catch (err) {
          console.warn("manager audio decode failed", err);
          this.reset();
          refs.audioEditor.classList.remove("hidden");
          this.setStatus(`エラー: ${err.message || "デコードできませんでした"}`, "error");
        }
      },

      async decodeFile(file) {
        if (!file) {
          this.reset();
          return;
        }
        const arrayBuffer = await this.readFileAsArrayBuffer(file);
        await this.decodeArrayBuffer(arrayBuffer, file.name);
      },

      async loadExistingSound(sound, button) {
        setLoading(button, true);
        this.reset();
        this.setStatus("読み込み中...", "");
        try {
          const response = await fetch(sound.url || soundPreviewUrl(sound.name));
          if (!response.ok) throw new Error(response.statusText || String(response.status));
          const arrayBuffer = await response.arrayBuffer();
          const base = safeRenameBase(sound.name);
          const outputName = sound.name.toLowerCase().endsWith(".wav") ? sound.name : `${base}.wav`;
          await this.decodeArrayBuffer(arrayBuffer, sound.name, {
            editingSoundName: sound.name,
            outputName,
          });
          refs.audioEditor.scrollIntoView({ behavior: "smooth", block: "center" });
        } catch (err) {
          this.reset();
          this.setStatus(`エラー: ${err.message || "読み込めませんでした"}`, "error");
        } finally {
          setLoading(button, false);
        }
      },

      currentTrim() {
        if (!this.buffer) return { startSec: 0, endSec: 0 };
        return {
          startSec: (this.trimStartValue / 1000) * this.buffer.duration,
          endSec: (this.trimEndValue / 1000) * this.buffer.duration,
        };
      },

      setTrimValues(start, end) {
        let nextStart = Math.max(0, Math.min(999, Math.round(Number(start) || 0)));
        let nextEnd = Math.max(1, Math.min(1000, Math.round(Number(end) || 0)));
        if (nextStart >= nextEnd) {
          if (nextEnd >= 1000) nextStart = 999;
          else nextEnd = nextStart + 1;
        }
        this.trimStartValue = nextStart;
        this.trimEndValue = nextEnd;
      },

      updateTrim(activePart) {
        if (!this.buffer) return;
        this.setTrimValues(this.trimStartValue, this.trimEndValue);
        const { startSec, endSec } = this.currentTrim();
        refs.trimStartLabel.textContent = this.secToLabel(startSec);
        refs.trimEndLabel.textContent = this.secToLabel(endSec);
        refs.trimLengthLabel.textContent = this.secToLabel(Math.max(0, endSec - startSec));
        this.updateSelectionWindow(activePart);
        if (activePart && this.source) this.schedulePreviewRestart();
      },

      updateSelectionWindow(activePart) {
        const left = this.trimStartValue / 10;
        const width = (this.trimEndValue - this.trimStartValue) / 10;
        refs.trimDimLeft.style.width = `${left}%`;
        refs.trimDimRight.style.left = `${left + width}%`;
        refs.trimDimRight.style.width = `${Math.max(0, 100 - left - width)}%`;
        refs.trimSelection.style.left = `${left}%`;
        refs.trimSelection.style.width = `${width}%`;
        refs.trimStartHandle.classList.toggle("is-active", activePart === "start");
        refs.trimEndHandle.classList.toggle("is-active", activePart === "end");
        refs.trimSelection.classList.toggle("is-active", activePart === "move");
        refs.trimStartHandle.setAttribute("aria-valuenow", String(this.trimStartValue));
        refs.trimEndHandle.setAttribute("aria-valuenow", String(this.trimEndValue));
      },

      valueFromEvent(event) {
        const rect = refs.waveformWindow.getBoundingClientRect();
        const point = event.touches && event.touches.length ? event.touches[0] : event;
        const ratio = Math.max(0, Math.min(1, (point.clientX - rect.left) / rect.width));
        return Math.round(ratio * 1000);
      },

      modeFromTarget(target, value) {
        if (target === refs.trimStartHandle) return "start";
        if (target === refs.trimEndHandle) return "end";
        if (target === refs.trimSelection || refs.trimSelection.contains(target)) return "move";
        const edgeTolerance = 28;
        const rect = refs.waveformWindow.getBoundingClientRect();
        const pxPerValue = rect.width / 1000;
        const startDistance = Math.abs(value - this.trimStartValue) * pxPerValue;
        const endDistance = Math.abs(value - this.trimEndValue) * pxPerValue;
        if (startDistance <= edgeTolerance || endDistance <= edgeTolerance) {
          return startDistance <= endDistance ? "start" : "end";
        }
        if (value > this.trimStartValue && value < this.trimEndValue) return "move";
        return value <= this.trimStartValue ? "start" : "end";
      },

      applyDrag(value) {
        if (this.dragMode === "start") {
          this.setTrimValues(Math.min(value, this.trimEndValue - 1), this.trimEndValue);
        } else if (this.dragMode === "end") {
          this.setTrimValues(this.trimStartValue, Math.max(value, this.trimStartValue + 1));
        } else if (this.dragMode === "move") {
          const delta = value - this.dragStartValue;
          const length = this.dragStartTrimEnd - this.dragStartTrimStart;
          let start = this.dragStartTrimStart + delta;
          start = Math.max(0, Math.min(1000 - length, start));
          this.setTrimValues(start, start + length);
        }
        this.updateTrim(this.dragMode);
      },

      startDrag(event) {
        if (!this.buffer) return;
        event.preventDefault();
        const value = this.valueFromEvent(event);
        this.dragMode = this.modeFromTarget(event.target, value);
        this.dragPointerId = event.pointerId;
        this.dragStartValue = value;
        this.dragStartTrimStart = this.trimStartValue;
        this.dragStartTrimEnd = this.trimEndValue;
        if (refs.waveformWindow.setPointerCapture && event.pointerId != null) {
          refs.waveformWindow.setPointerCapture(event.pointerId);
        }
        if (this.dragMode !== "move") this.applyDrag(value);
        else this.updateTrim("move");
      },

      drag(event) {
        if (!this.dragMode) return;
        if (this.dragPointerId != null && event.pointerId != null && event.pointerId !== this.dragPointerId) return;
        event.preventDefault();
        this.applyDrag(this.valueFromEvent(event));
      },

      endDrag() {
        this.dragMode = null;
        this.dragPointerId = null;
        this.updateTrim();
      },

      drawWaveform() {
        const canvas = refs.waveformCanvas;
        if (!canvas || !this.buffer) return;
        const context = canvas.getContext("2d");
        const width = canvas.width;
        const height = canvas.height;
        const mid = height / 2;
        const channelData = [];
        for (let c = 0; c < this.buffer.numberOfChannels; c++) channelData.push(this.buffer.getChannelData(c));
        const samplesPerPixel = Math.max(1, Math.floor(this.buffer.length / width));
        context.clearRect(0, 0, width, height);
        context.fillStyle = getComputedStyle(document.documentElement).getPropertyValue("--bg-card2").trim() || "#21262d";
        context.fillRect(0, 0, width, height);
        context.strokeStyle = getComputedStyle(document.documentElement).getPropertyValue("--accent").trim() || "#20c997";
        context.lineWidth = 1;
        for (let x = 0; x < width; x++) {
          const start = x * samplesPerPixel;
          const end = Math.min(start + samplesPerPixel, this.buffer.length);
          let peak = 0;
          for (let i = start; i < end; i++) {
            for (let c = 0; c < channelData.length; c++) {
              const value = Math.abs(channelData[c][i]);
              if (value > peak) peak = value;
            }
          }
          const barHeight = Math.max(1, peak * (height - 8));
          context.beginPath();
          context.moveTo(x + 0.5, mid - barHeight / 2);
          context.lineTo(x + 0.5, mid + barHeight / 2);
          context.stroke();
        }
      },

      async togglePreview() {
        if (!this.buffer) return;
        if (this.source) {
          this.stopPreview();
          return;
        }
        const { startSec, endSec } = this.currentTrim();
        const duration = Math.max(0.01, endSec - startSec);
        const context = this.playbackContext || this.getAudioContext();
        this.playbackContext = context;
        if (context.state === "suspended" && context.resume) await context.resume();
        const source = context.createBufferSource();
        source.buffer = this.buffer;
        source.connect(context.destination);
        source.onended = () => {
          if (this.source === source) {
            this.source = null;
            refs.previewBtn.textContent = "▶ プレビュー";
          }
        };
        this.source = source;
        refs.previewBtn.textContent = "⏹ 停止";
        source.start(0, startSec, duration);
      },

      schedulePreviewRestart() {
        if (this.restartPreviewTimer) clearTimeout(this.restartPreviewTimer);
        this.restartPreviewTimer = setTimeout(() => {
          this.restartPreviewTimer = null;
          this.restartPreviewFromTrim();
        }, 80);
      },

      async restartPreviewFromTrim() {
        if (!this.buffer || !this.source) return;
        this.stopPreview({ keepButtonPlaying: true });
        try {
          await this.togglePreview();
        } catch (err) {
          console.warn("manager preview restart failed", err);
          this.stopPreview();
        }
      },

      stopPreview(options = {}) {
        if (this.restartPreviewTimer) {
          clearTimeout(this.restartPreviewTimer);
          this.restartPreviewTimer = null;
        }
        if (this.source) {
          const source = this.source;
          this.source = null;
          source.onended = null;
          try {
            source.stop();
          } catch (_err) {
            /* source may already be stopped */
          }
        }
        if (refs.previewBtn && !options.keepButtonPlaying) refs.previewBtn.textContent = "▶ プレビュー";
      },

      async upload() {
        if (!this.buffer) {
          refs.audioEditor.classList.remove("hidden");
          this.setStatus("まずファイルを選択してください", "error");
          return;
        }
        const originalText = refs.doUploadBtn.textContent;
        let saved = false;
        const finalName = this.sanitizeWavName(refs.uploadFilename.value);
        refs.uploadFilename.value = finalName;
        setLoading(refs.doUploadBtn, true);
        refs.doUploadBtn.textContent = "アップロード中...";
        this.setStatus("", "");
        try {
          const { startSec, endSec } = this.currentTrim();
          const wavBlob = this.encodeWav(this.buffer, startSec, endSec);
          const formData = new FormData();
          formData.append("file", wavBlob, finalName);
          let response;
          if (this.editingSoundName) {
            formData.append("final_name", finalName);
            response = await fetch(`/api/sounds/${encodeURIComponent(this.editingSoundName)}/trim`, {
              method: "POST",
              body: formData,
            });
          } else {
            response = await fetch("/api/sounds", { method: "POST", body: formData });
          }
          if (!response.ok) {
            let detail = response.statusText || String(response.status);
            try {
              const data = await response.json();
              detail = data.detail || detail;
            } catch (_err) {
              /* keep status text */
            }
            throw new Error(detail);
          }
          const uploaded = await response.json();
          const uploadedName = uploaded && uploaded.name ? uploaded.name : finalName;
          await loadSounds();
          ensureSoundOption(uploadedName);
          setSelectedSounds([uploadedName]);
          await loadAlarms();
          this.setStatus(this.editingSoundName ? "✓ トリミング保存完了" : "✓ アップロード完了", "success");
          saved = true;
          this.reset({ keepStatus: true });
        } catch (err) {
          this.setStatus(`エラー: ${err.message || "アップロードできませんでした"}`, "error");
        } finally {
          if (!saved) refs.doUploadBtn.textContent = originalText;
          setLoading(refs.doUploadBtn, false);
        }
      },

      reset(options = {}) {
        this.stopPreview();
        this.buffer = null;
        this.dragMode = null;
        this.dragPointerId = null;
        this.setTrimValues(0, 1000);
        refs.fileInput.value = "";
        refs.selectedFileName.textContent = "未選択";
        refs.uploadFilename.value = "";
        this.editingSoundName = null;
        refs.doUploadBtn.textContent = "アップロード";
        refs.audioEditor.classList.add("hidden");
        refs.trimStartLabel.textContent = "0:00.0";
        refs.trimEndLabel.textContent = "0:00.0";
        refs.trimLengthLabel.textContent = "0:00.0";
        this.updateSelectionWindow();
        if (!options.keepStatus) this.setStatus("", "");
      },
    };
  }

  const ManagerAudioEditor = createManagedAudioEditor({
    fileInput: els.soundManagerFile,
    selectedFileName: els.managerSelectedFileName,
    audioEditor: els.managerAudioEditor,
    waveformCanvas: els.managerWaveformCanvas,
    waveformWindow: els.managerWaveformWindow,
    trimSelection: els.managerTrimSelection,
    trimDimLeft: els.managerTrimDimLeft,
    trimDimRight: els.managerTrimDimRight,
    trimStartHandle: els.managerTrimStartHandle,
    trimEndHandle: els.managerTrimEndHandle,
    trimStartLabel: els.managerTrimStartLabel,
    trimLengthLabel: els.managerTrimLengthLabel,
    trimEndLabel: els.managerTrimEndLabel,
    previewBtn: els.managerPreviewBtn,
    uploadFilename: els.managerUploadFilename,
    doUploadBtn: els.managerDoUploadBtn,
    uploadStatus: els.managerUploadStatus,
  });

  function renderAlarmList() {
    els.alarmGrid.textContent = "";
    els.alarmCount.textContent = `${alarms.length}件のアラーム`;
    if (!alarms.length) {
      const empty = document.createElement("div");
      empty.className = "empty-state";
      empty.innerHTML = '<div class="empty-icon">＋</div><div>アラームなし</div>';
      const button = document.createElement("button");
      button.className = "button button-accent";
      button.type = "button";
      button.textContent = "+ 追加";
      button.addEventListener("click", () => openAlarmModal(null));
      empty.appendChild(button);
      els.alarmGrid.appendChild(empty);
      return;
    }

    alarms.forEach((alarm, index) => {
      const card = document.createElement("article");
      card.className = `alarm-card${alarm.enabled ? "" : " disabled"}`;
      card.tabIndex = 0;
      card.style.setProperty("--i", String(index));

      const head = document.createElement("div");
      head.className = "alarm-card-head";
      const content = document.createElement("div");
      content.className = "alarm-content";
      const time = document.createElement("div");
      time.className = "alarm-time";
      const antiDoze = alarm.alarm_kind === "anti_doze";
      time.textContent = antiDoze
        ? `${alarm.monitor_start || "--:--"} → ${alarm.time || "--:--"}`
        : alarm.time || "--:--";
      const label = document.createElement("div");
      label.className = "alarm-label";
      label.textContent = alarm.label || "Alarm";
      content.append(time, label);
      if (antiDoze) {
        const kind = document.createElement("span");
        kind.className = "kind-mini";
        kind.textContent = `寝落ち防止 · 再横臥禁止 ${Number(alarm.reentry_block_min) || 0}分`;
        content.appendChild(kind);
      }

      const toggleLabel = document.createElement("label");
      toggleLabel.className = "switch";
      toggleLabel.addEventListener("click", (event) => event.stopPropagation());
      const toggle = document.createElement("input");
      toggle.type = "checkbox";
      toggle.checked = Boolean(alarm.enabled);
      toggle.setAttribute("aria-label", `${alarm.label || alarm.time || "アラーム"}を切り替え`);
      toggle.addEventListener("change", async () => {
        await withLoading(toggleLabel, async () => {
          await safeApi(`/api/alarms/${alarm.id}/toggle`, { method: "POST" }, null);
          await loadAlarms();
          await pollStatus();
        });
      });
      const slider = document.createElement("span");
      slider.className = "slider";
      toggleLabel.append(toggle, slider);
      head.append(content, toggleLabel);

      const daysRow = document.createElement("div");
      daysRow.className = "weekday-mini-row";
      const days = new Set(Array.isArray(alarm.repeat_days) ? alarm.repeat_days.map(Number) : []);
      DAYS.forEach((day, dayIndex) => {
        const chip = document.createElement("span");
        chip.className = `day-mini${days.has(dayIndex) ? " active" : ""}`;
        chip.textContent = day;
        daysRow.appendChild(chip);
      });
      content.appendChild(daysRow);
      if (!alarm.enabled) {
        const disabled = document.createElement("span");
        disabled.className = "state-mini";
        disabled.textContent = "無効";
        content.appendChild(disabled);
      }

      card.addEventListener("click", () => openAlarmModal(alarm));
      card.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          openAlarmModal(alarm);
        }
      });
      card.appendChild(head);
      els.alarmGrid.appendChild(card);
    });
  }

  async function loadAlarms() {
    alarms = await safeApi("/api/alarms", undefined, []);
    renderAlarmList();
  }

  function normalizeSoundRefs(value) {
    if (Array.isArray(value)) return value.map(String).filter(Boolean);
    if (typeof value !== "string" || !value.trim()) return [];
    try {
      const parsed = JSON.parse(value);
      if (Array.isArray(parsed)) return parsed.map(String).filter(Boolean);
    } catch (_err) {
      /* plain single filename */
    }
    return [value];
  }

  function soundRefsForAlarm(alarm) {
    if (!alarm) return [];
    if (Array.isArray(alarm.sound_refs)) return alarm.sound_refs.map(String).filter(Boolean);
    if (alarm.sound_type === "random") return normalizeSoundRefs(alarm.sound_ref);
    if (alarm.sound_type === "upload" && alarm.sound_ref) return [String(alarm.sound_ref)];
    return [];
  }

  function selectedSoundValues() {
    if (!els.soundList) return [];
    return Array.from(els.soundList.querySelectorAll("input[type='checkbox']:checked"))
      .map((input) => input.value)
      .filter(Boolean);
  }

  function soundPreviewUrl(name) {
    return `/sounds/${encodeURIComponent(name)}`;
  }

  function formatAudioTime(seconds) {
    const value = Math.max(0, Number(seconds) || 0);
    const minutes = Math.floor(value / 60);
    const secs = Math.floor(value % 60);
    return `${minutes}:${String(secs).padStart(2, "0")}`;
  }

  function alarmPreviewPanelRefs() {
    return {
      panel: els.soundPreviewPanel,
      title: els.soundPreviewTitle,
      current: els.soundPreviewCurrent,
      seek: els.soundPreviewSeek,
      duration: els.soundPreviewDuration,
    };
  }

  function managerPreviewPanelRefs() {
    return {
      panel: els.managerSoundPreviewPanel,
      title: els.managerSoundPreviewTitle,
      current: els.managerSoundPreviewCurrent,
      seek: els.managerSoundPreviewSeek,
      duration: els.managerSoundPreviewDuration,
    };
  }

  function bindPreviewPanel(panelRefs) {
    if (!panelRefs || !panelRefs.seek || panelRefs.seek.dataset.bound === "true") return;
    panelRefs.seek.dataset.bound = "true";
    ["click", "pointerdown", "mousedown", "touchstart"].forEach((name) => {
      panelRefs.seek.addEventListener(name, (event) => event.stopPropagation());
    });
    panelRefs.seek.addEventListener("input", () => {
      if (!previewAudio || !previewButton) return;
      const refs = previewButton._previewRefs;
      if (!refs || refs.seek !== panelRefs.seek) return;
      const next = Number(panelRefs.seek.value) / 1000;
      if (Number.isFinite(next)) previewAudio.currentTime = next;
      updatePreviewSeek();
    });
  }

  function updatePreviewSeek() {
    if (!previewAudio || !previewButton) return;
    const refs = previewButton._previewRefs;
    if (!refs) return;
    const duration = Number(previewAudio.duration) || 0;
    const current = Number(previewAudio.currentTime) || 0;
    refs.current.textContent = formatAudioTime(current);
    refs.duration.textContent = duration ? formatAudioTime(duration) : "--:--";
    refs.seek.max = duration ? String(Math.round(duration * 1000)) : "1000";
    refs.seek.value = duration ? String(Math.round(current * 1000)) : "0";
  }

  function resetPreviewButton() {
    if (!previewButton) return;
    const refs = previewButton._previewRefs;
    previewButton.textContent = "▶";
    previewButton.classList.remove("is-playing");
    previewButton.setAttribute("aria-label", `${previewName || "音源"} をプレビュー`);
    if (refs) {
      refs.panel.classList.add("hidden");
      refs.title.textContent = "プレビュー";
      refs.seek.value = "0";
      refs.current.textContent = "0:00";
      refs.duration.textContent = "--:--";
    }
    previewButton = null;
    previewName = "";
  }

  function stopSoundPreview() {
    if (previewAudio) {
      previewAudio.pause();
      previewAudio.removeAttribute("src");
      previewAudio.load();
      previewAudio = null;
    }
    if (previewTimer) {
      clearInterval(previewTimer);
      previewTimer = null;
    }
    resetPreviewButton();
  }

  function createSoundPreviewControls(sound, options = {}) {
    const button = document.createElement("button");
    button.className = "sound-preview-button";
    button.type = "button";
    button.textContent = "▶";
    button.title = "プレビュー";
    button.setAttribute("aria-label", `${sound.name} をプレビュー`);

    const panel = options.panelRefs || alarmPreviewPanelRefs();
    bindPreviewPanel(panel);
    const refs = { button, ...panel, onError: options.onError };
    button._previewRefs = refs;
    button.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      toggleSoundPreview(sound, refs);
    });
    return refs;
  }

  async function toggleSoundPreview(sound, refs) {
    if (previewAudio && previewName === sound.name && previewButton === refs.button) {
      stopSoundPreview();
      return;
    }
    stopSoundPreview();
    previewName = sound.name;
    previewButton = refs.button;
    refs.button.textContent = "■";
    refs.button.classList.add("is-playing");
    refs.button.setAttribute("aria-label", `${sound.name} のプレビューを停止`);
    refs.title.textContent = sound.name;
    refs.panel.classList.remove("hidden");
    previewAudio = new Audio(soundPreviewUrl(sound.name));
    previewAudio.addEventListener("loadedmetadata", updatePreviewSeek);
    previewAudio.addEventListener("timeupdate", updatePreviewSeek);
    previewAudio.addEventListener("ended", stopSoundPreview, { once: true });
    previewAudio.addEventListener("error", () => {
      stopSoundPreview();
      if (refs.onError) refs.onError("プレビュー再生できませんでした。");
      else showFormError("プレビュー再生できませんでした。");
    }, { once: true });
    try {
      await previewAudio.play();
      updatePreviewSeek();
      previewTimer = setInterval(updatePreviewSeek, 250);
    } catch (err) {
      stopSoundPreview();
      if (refs.onError) refs.onError(err.message || "プレビュー再生できませんでした。");
      else showFormError(err.message || "プレビュー再生できませんでした。");
    }
  }

  function renderSoundChoices(preselect) {
    if (!els.soundList) return;
    stopSoundPreview();
    const selected = new Set((preselect || selectedSoundValues()).map(String));
    els.soundList.textContent = "";
    const sourceSounds = sounds.length ? sounds : [{ name: "alarm_long.mp3", size: 0 }];
    sourceSounds.forEach((sound, index) => {
      const row = document.createElement("div");
      row.className = "sound-choice";
      const main = document.createElement("label");
      main.className = "sound-choice-main";
      const input = document.createElement("input");
      input.type = "checkbox";
      input.value = sound.name;
      input.checked = selected.has(sound.name) || (!selected.size && index === 0);
      const text = document.createElement("span");
      text.textContent = sound.name;
      const preview = createSoundPreviewControls(sound, { panelRefs: alarmPreviewPanelRefs() });
      main.append(input, text);
      row.append(main, preview.button);
      els.soundList.appendChild(row);
    });
  }

  function setSelectedSounds(names) {
    const selected = new Set((names || []).map(String).filter(Boolean));
    if (!selected.size && sounds.length) selected.add(sounds[0].name);
    renderSoundChoices(Array.from(selected));
  }

  function ensureSoundOption(name) {
    if (!name || sounds.some((sound) => sound.name === name)) return;
    sounds.push({ name, size: 0, url: `/sounds/${encodeURIComponent(name)}` });
    renderSoundChoices([...selectedSoundValues(), name]);
  }

  function hasSound(name) {
    return sounds.some((sound) => sound.name === name);
  }

  function fallbackSoundName(excludedName) {
    const sound = sounds.find((item) => item.name !== excludedName);
    return sound ? sound.name : "alarm_long.mp3";
  }

  async function loadSounds() {
    const selected = selectedSoundValues();
    sounds = await safeApi("/api/sounds", undefined, []);
    renderSoundChoices(selected);
    renderSoundManager();
  }

  function formatBytes(size) {
    const value = Number(size) || 0;
    if (value >= 1024 * 1024) return `${(value / 1024 / 1024).toFixed(1)} MB`;
    if (value >= 1024) return `${Math.round(value / 1024)} KB`;
    return `${value} B`;
  }

  function setSoundManagerMessage(message, type) {
    if (!els.soundManagerMessage) return;
    els.soundManagerMessage.textContent = message || "";
    els.soundManagerMessage.classList.toggle("success", type === "success");
    els.soundManagerMessage.classList.toggle("error", type === "error");
  }

  function setStatusMessage(el, message, type) {
    if (!el) return;
    el.textContent = message || "";
    el.classList.toggle("success", type === "success");
    el.classList.toggle("error", type === "error");
  }

  function formatYouTubeJobStatus(job) {
    if (!job) return "待機中";
    if (job.state === "queued") return "待機中";
    if (job.state === "done") return `完了: ${job.result && job.result.name ? job.result.name : "取り込みました"}`;
    if (job.state === "error") return job.error || job.message || "取り込めませんでした";
    if (job.state === "processing") {
      return job.message ? `音声変換中: ${job.message}` : "音声変換中";
    }
    const parts = ["DL中"];
    if (job.percent != null) parts.push(`${Number(job.percent).toFixed(1)}%`);
    if (job.total) parts.push(`全体 ${job.total}`);
    if (job.speed) parts.push(job.speed);
    if (job.eta) parts.push(`残り ${job.eta}`);
    if (job.fragment) parts.push(job.fragment);
    if (parts.length === 1 && job.message) parts.push(job.message);
    return parts.join(" / ");
  }

  async function waitForYouTubeJob(job, statusEl) {
    let current = job;
    setStatusMessage(statusEl, formatYouTubeJobStatus(current), "");
    while (current && !["done", "error"].includes(current.state)) {
      await delay(700);
      current = await api(`/api/sounds/youtube/jobs/${encodeURIComponent(current.id)}`);
      setStatusMessage(statusEl, formatYouTubeJobStatus(current), current.state === "error" ? "error" : "");
    }
    if (!current || current.state !== "done" || !current.result) {
      throw new Error((current && (current.error || current.message)) || "取り込めませんでした");
    }
    return current.result;
  }

  async function downloadYouTubeSound(refs, options = {}) {
    const url = refs.urlInput.value.trim();
    if (!url) {
      setStatusMessage(refs.status, "YouTube URLを入力してください", "error");
      refs.urlInput.focus();
      return null;
    }
    const originalText = refs.button.textContent;
    refs.button.textContent = "DL中...";
    setLoading(refs.button, true);
    setStatusMessage(refs.status, "", "");
    try {
      const job = await api("/api/sounds/youtube/jobs", {
        method: "POST",
        body: JSON.stringify({
          url,
          filename: refs.filenameInput ? refs.filenameInput.value.trim() : "",
        }),
      });
      const downloaded = await waitForYouTubeJob(job, refs.status);
      await loadSounds();
      ensureSoundOption(downloaded.name);
      setSelectedSounds([downloaded.name]);
      if (options.switchToExisting !== false) setSoundTab("existing");
      if (refs.filenameInput) refs.filenameInput.value = "";
      refs.urlInput.value = "";
      setStatusMessage(refs.status, "✓ 取り込みました", "success");
      return downloaded;
    } catch (err) {
      setStatusMessage(refs.status, err.message || "取り込めませんでした", "error");
      return null;
    } finally {
      refs.button.textContent = originalText;
      setLoading(refs.button, false);
    }
  }

  function renderSoundManager() {
    if (!els.soundManagerList) return;
    stopSoundPreview();
    els.soundManagerList.textContent = "";
    if (!sounds.length) {
      const empty = document.createElement("div");
      empty.className = "sound-manager-empty";
      empty.textContent = "登録済み音源がありません";
      els.soundManagerList.appendChild(empty);
      return;
    }
    sounds.forEach((sound) => {
      const row = document.createElement("div");
      row.className = "sound-manager-row";

      const info = document.createElement("div");
      info.className = "sound-manager-info";
      const name = document.createElement("span");
      name.className = "sound-manager-name";
      name.textContent = sound.name;
      const size = document.createElement("span");
      size.className = "sound-manager-size";
      size.textContent = formatBytes(sound.size);
      info.append(name, size);

      const actions = document.createElement("div");
      actions.className = "sound-manager-actions";
      const preview = createSoundPreviewControls(sound, {
        panelRefs: managerPreviewPanelRefs(),
        onError: (message) => setSoundManagerMessage(message, "error"),
      });
      const trim = document.createElement("button");
      trim.className = "button button-ghost sound-action";
      trim.type = "button";
      trim.textContent = "トリミング";
      trim.addEventListener("click", () => ManagerAudioEditor.loadExistingSound(sound, trim));
      const rename = document.createElement("button");
      rename.className = "button button-ghost sound-action";
      rename.type = "button";
      rename.textContent = "名前変更";
      rename.addEventListener("click", () => beginRenameSound(row, sound));
      const remove = document.createElement("button");
      remove.className = "button button-danger sound-action";
      remove.type = "button";
      remove.textContent = "削除";
      remove.addEventListener("click", () => deleteSound(sound.name));
      actions.append(preview.button, trim, rename, remove);

      row.append(info, actions);
      els.soundManagerList.appendChild(row);
    });
  }

  function beginRenameSound(row, sound) {
    stopSoundPreview();
    row.classList.add("is-editing");
    row.textContent = "";

    const input = document.createElement("input");
    input.className = "sound-rename-input";
    input.type = "text";
    input.value = sound.name.replace(/\.[^.]*$/, "");
    input.setAttribute("aria-label", `${sound.name} の新しい名前`);
    input.dataset.composing = "false";

    const actions = document.createElement("div");
    actions.className = "sound-manager-actions";
    const save = document.createElement("button");
    save.className = "button button-accent sound-action";
    save.type = "button";
    save.textContent = "保存";
    const cancel = document.createElement("button");
    cancel.className = "button button-ghost sound-action";
    cancel.type = "button";
    cancel.textContent = "キャンセル";

    const commit = () => renameSound(sound.name, input.value, save);
    save.addEventListener("click", commit);
    cancel.addEventListener("click", renderSoundManager);
    input.addEventListener("compositionstart", () => {
      input.dataset.composing = "true";
    });
    input.addEventListener("compositionend", () => {
      requestAnimationFrame(() => {
        input.dataset.composing = "false";
      });
    });
    input.addEventListener("keydown", (event) => {
      if (event.isComposing || input.dataset.composing === "true" || event.keyCode === 229) return;
      if (event.key === "Enter") {
        event.preventDefault();
        commit();
      } else if (event.key === "Escape") {
        event.preventDefault();
        renderSoundManager();
      }
    });

    actions.append(save, cancel);
    row.append(input, actions);
    input.focus();
    input.select();
  }

  async function renameSound(name, nextName, button) {
    const trimmed = String(nextName || "").trim();
    if (!trimmed) {
      setSoundManagerMessage("名前を入力してください", "error");
      return;
    }
    const safeBase = safeRenameBase(trimmed);
    setLoading(button, true);
    setSoundManagerMessage("", "");
    try {
      const renamed = await api(`/api/sounds/${encodeURIComponent(name)}/rename`, {
        method: "POST",
        body: JSON.stringify({ new_name: safeBase }),
      });
      await loadSounds();
      await loadAlarms();
      if (renamed && renamed.name) setSelectedSounds([renamed.name]);
      setSoundManagerMessage("名前を変更しました", "success");
    } catch (err) {
      setSoundManagerMessage(err.message || "名前を変更できませんでした", "error");
      renderSoundManager();
    } finally {
      setLoading(button, false);
    }
  }

  async function deleteSound(name) {
    if (!window.confirm(`${name} を削除しますか？`)) return;
    stopSoundPreview();
    setSoundManagerMessage("", "");
    try {
      await api(`/api/sounds/${encodeURIComponent(name)}`, { method: "DELETE" });
      await loadSounds();
      await repointAlarmsAfterSoundDelete(name);
      await loadAlarms();
      setSoundManagerMessage("削除しました", "success");
    } catch (err) {
      setSoundManagerMessage(err.message || "削除できませんでした", "error");
    }
  }

  async function repointAlarmsAfterSoundDelete(deletedName) {
    const replacement = fallbackSoundName(deletedName);
    const targets = alarms.filter((alarm) => {
      if (alarm.sound_type === "upload") return alarm.sound_ref === deletedName;
      if (alarm.sound_type === "random") return soundRefsForAlarm(alarm).includes(deletedName);
      return false;
    });
    for (const alarm of targets) {
      let sound_type = "upload";
      let sound_ref = replacement;
      if (alarm.sound_type === "random") {
        const refs = soundRefsForAlarm(alarm).filter((name) => name !== deletedName);
        if (refs.length >= 2) {
          sound_type = "random";
          sound_ref = JSON.stringify(refs);
        } else if (refs.length === 1) {
          sound_ref = refs[0];
        }
      }
      await api(`/api/alarms/${alarm.id}`, {
        method: "PUT",
        body: JSON.stringify({
          label: alarm.label || "Alarm",
          time: alarm.time,
          repeat_days: Array.isArray(alarm.repeat_days) ? alarm.repeat_days : [],
          enabled: Boolean(alarm.enabled),
          wake_check: Boolean(alarm.wake_check),
          volume: Number(alarm.volume) || 1,
          devices: Array.isArray(alarm.devices) && alarm.devices.length ? alarm.devices : ["Miku-Miku Echo"],
          sound_type,
          sound_ref,
        }),
      });
    }
  }

  async function loadDevices(preselect) {
    const data = await safeApi("/api/devices", undefined, { names: [] });
    const merged = new Set(["Miku-Miku Echo", ...(Array.isArray(data.names) ? data.names : []), ...(preselect || [])]);
    deviceNames = Array.from(merged).filter(Boolean);
    renderDeviceOptions(preselect || ["Miku-Miku Echo"]);
  }

  function renderDeviceOptions(preselect) {
    const selected = new Set(preselect && preselect.length ? preselect : ["Miku-Miku Echo"]);
    els.devices.textContent = "";
    deviceNames.forEach((name) => {
      const label = document.createElement("label");
      label.className = "device-choice";
      const input = document.createElement("input");
      input.type = "checkbox";
      input.value = name;
      input.checked = selected.has(name);
      const text = document.createElement("span");
      text.textContent = name;
      label.append(input, text);
      els.devices.appendChild(label);
    });
  }

  function selectedDeviceValues() {
    const values = Array.from(els.devices.querySelectorAll("input:checked"))
      .map((input) => input.value)
      .filter(Boolean);
    return values.length ? values : ["Miku-Miku Echo"];
  }

  function sameDays(left, right) {
    if (left.length !== right.length) return false;
    return left.every((value, index) => value === right[index]);
  }

  function updatePresetChips() {
    const selected = Array.from(selectedDays).sort((a, b) => a - b);
    document.querySelectorAll(".preset").forEach((button) => {
      const days = button.dataset.days ? button.dataset.days.split(",").map(Number) : [];
      button.classList.toggle("active", sameDays(selected, days));
    });
  }

  function renderWeekdayChips() {
    els.weekdayChips.textContent = "";
    DAYS.forEach((label, index) => {
      const button = document.createElement("button");
      button.className = `chip${selectedDays.has(index) ? " active" : ""}`;
      button.type = "button";
      button.dataset.day = String(index);
      button.textContent = label;
      button.addEventListener("click", () => {
        if (selectedDays.has(index)) selectedDays.delete(index);
        else selectedDays.add(index);
        renderWeekdayChips();
        updatePresetChips();
      });
      els.weekdayChips.appendChild(button);
    });
    updatePresetChips();
  }

  function setDays(days) {
    selectedDays = new Set((days || []).map(Number).filter((day) => day >= 0 && day <= 6));
    renderWeekdayChips();
  }

  function setSoundTab(tabName) {
    activeSoundTab = tabName;
    els.soundTabs.classList.remove("tab-existing", "tab-upload", "tab-youtube", "tab-url");
    els.soundTabs.classList.add(`tab-${tabName}`);
    document.querySelectorAll(".tab[data-sound-tab]").forEach((tab) => {
      const active = tab.dataset.soundTab === tabName;
      tab.classList.toggle("active", active);
      tab.setAttribute("aria-selected", active ? "true" : "false");
    });
    ["existing", "upload", "youtube", "url"].forEach((name) => {
      const panel = $(`sound-${name}`);
      if (panel) panel.classList.toggle("hidden", name !== tabName);
    });
  }

  function updateVolumeOutput() {
    const value = Number(els.volume.value) || 0;
    els.volumeOutput.textContent = `${value}%`;
    els.volumeOutput.style.setProperty("--range-pos", `${value}%`);
  }

  function updateSettingsOutputs() {
    els.settings.ring_volume_output.textContent = `${Number(els.settings.ring_volume.value) || 0}%`;
  }

  function showFormError(message) {
    els.formError.textContent = message || "";
    els.formError.classList.toggle("visible", Boolean(message));
  }

  function updateAlarmKindFields() {
    const antiDoze = els.alarmKind.value === "anti_doze";
    els.antiDozeTimeFields.classList.toggle("hidden", !antiDoze);
    els.antiDozeOptions.classList.toggle("hidden", !antiDoze);
    els.alarmTimeLabel.textContent = antiDoze ? "就寝してよい時刻" : "時刻";
    els.alarmMonitorStart.required = antiDoze;
    els.alarmWakeCheck.disabled = antiDoze;
    if (antiDoze) els.alarmWakeCheck.checked = true;
  }

  async function openAlarmModal(alarm) {
    const editing = Boolean(alarm && alarm.id);
    showFormError("");
    els.modalTitle.textContent = editing ? "アラーム編集" : "アラーム追加";
    els.alarmId.value = editing ? alarm.id : "";
    els.alarmKind.value = editing ? alarm.alarm_kind || "wake" : "wake";
    els.alarmTime.value = editing ? alarm.time || "07:00" : "07:00";
    els.alarmMonitorStart.value = editing ? alarm.monitor_start || "18:00" : "18:00";
    els.alarmReentryBlockMin.value = editing ? Number(alarm.reentry_block_min) || 0 : 0;
    els.alarmLabel.value = editing ? alarm.label || "" : "";
    els.alarmEnabled.checked = editing ? Boolean(alarm.enabled) : true;
    els.alarmWakeCheck.checked = editing ? Boolean(alarm.wake_check) : true;
    updateAlarmKindFields();
    setDays(editing ? alarm.repeat_days || [] : []);
    els.volume.value = Math.round((editing ? Number(alarm.volume) || 1 : 1) * 100);
    updateVolumeOutput();
    els.soundUrl.value = editing && alarm.sound_type === "url" ? alarm.sound_ref || "" : "";
    if (els.youtubeUrl) els.youtubeUrl.value = "";
    if (els.youtubeFilename) els.youtubeFilename.value = "";
    setStatusMessage(els.youtubeStatus, "", "");
    AudioEditor.reset();

    const refs = editing && alarm.sound_type !== "url" ? soundRefsForAlarm(alarm) : [];
    const validRefs = refs.filter(hasSound);
    if (validRefs.length) {
      setSelectedSounds(validRefs);
    } else {
      setSelectedSounds([]);
      if (editing && refs.length) {
        showFormError("選択済みの音源が見つからないため、別の音源を選択しています。保存すると更新されます。");
      }
    }
    setSoundTab(editing && alarm.sound_type === "url" ? "url" : "existing");
    renderDeviceOptions(editing ? alarm.devices || ["Miku-Miku Echo"] : ["Miku-Miku Echo"]);
    loadDevices(editing ? alarm.devices || ["Miku-Miku Echo"] : ["Miku-Miku Echo"]);
    els.deleteAlarm.classList.toggle("hidden", !editing);

    if (closeModalTimer) clearTimeout(closeModalTimer);
    els.modalOverlay.classList.remove("hidden");
    els.modalOverlay.setAttribute("aria-hidden", "false");
    requestAnimationFrame(() => els.modalOverlay.classList.add("modal-open"));
    requestAnimationFrame(() => els.alarmTime.focus());
  }

  function closeAlarmModal() {
    AudioEditor.reset();
    stopSoundPreview();
    els.modalOverlay.classList.remove("modal-open");
    els.modalOverlay.setAttribute("aria-hidden", "true");
    closeModalTimer = setTimeout(() => {
      if (!els.modalOverlay.classList.contains("modal-open")) {
        els.modalOverlay.classList.add("hidden");
      }
    }, 280);
  }

  function isModalOpen() {
    return els.modalOverlay.classList.contains("modal-open");
  }

  async function soundPayload() {
    if (activeSoundTab === "url") {
      const url = els.soundUrl.value.trim();
      if (!url) throw new Error("URLを入力してください。");
      return { sound_type: "url", sound_ref: url };
    }
    if (activeSoundTab === "youtube") {
      const downloaded = await downloadYouTubeSound({
        urlInput: els.youtubeUrl,
        filenameInput: els.youtubeFilename,
        button: els.downloadYoutubeBtn,
        status: els.youtubeStatus,
      });
      if (!downloaded) throw new Error("YouTube音源を取り込めませんでした。");
      return { sound_type: "upload", sound_ref: downloaded.name };
    }
    if (activeSoundTab === "upload") {
      throw new Error("先に［アップロード］ボタンで音源を登録してください");
    }
    const selected = selectedSoundValues();
    if (!selected.length) throw new Error("音源を選択してください。");
    if (selected.length === 1) return { sound_type: "upload", sound_ref: selected[0] };
    return { sound_type: "random", sound_ref: JSON.stringify(selected) };
  }

  async function saveAlarm(event) {
    event.preventDefault();
    if (!event.submitter && document.activeElement && document.activeElement.closest(".youtube-import-panel")) return;
    showFormError("");
    if (!els.alarmTime.value) {
      showFormError("時刻を入力してください。");
      els.alarmTime.focus();
      return;
    }
    const antiDoze = els.alarmKind.value === "anti_doze";
    if (antiDoze && !els.alarmMonitorStart.value) {
      showFormError("監視開始時刻を入力してください。");
      els.alarmMonitorStart.focus();
      return;
    }
    if (antiDoze && els.alarmMonitorStart.value === els.alarmTime.value) {
      showFormError("監視開始時刻と就寝してよい時刻は別の時刻にしてください。");
      els.alarmMonitorStart.focus();
      return;
    }
    const reentryBlockMin = Number(els.alarmReentryBlockMin.value);
    if (antiDoze && (!Number.isInteger(reentryBlockMin) || reentryBlockMin < 0 || reentryBlockMin > 720)) {
      showFormError("再横臥を禁止する時間は0～720分で入力してください。");
      els.alarmReentryBlockMin.focus();
      return;
    }

    await withLoading(els.saveAlarm, async () => {
      try {
        const sound = await soundPayload();
        const payload = {
          alarm_kind: els.alarmKind.value,
          label: els.alarmLabel.value.trim() || "Alarm",
          time: els.alarmTime.value,
          monitor_start: antiDoze ? els.alarmMonitorStart.value : null,
          reentry_block_min: antiDoze ? reentryBlockMin : 0,
          repeat_days: Array.from(selectedDays).sort((a, b) => a - b),
          enabled: els.alarmEnabled.checked,
          wake_check: els.alarmWakeCheck.checked,
          volume: Number(els.volume.value) / 100,
          devices: selectedDeviceValues(),
          ...sound,
        };
        const id = els.alarmId.value;
        await api(id ? `/api/alarms/${id}` : "/api/alarms", {
          method: id ? "PUT" : "POST",
          body: JSON.stringify(payload),
        });
        closeAlarmModal();
        await loadSounds();
        await loadAlarms();
        await pollStatus();
      } catch (err) {
        showFormError(err.message || "保存できませんでした。");
      }
    });
  }

  async function deleteAlarm() {
    const id = els.alarmId.value;
    if (!id) return;
    await withLoading(els.deleteAlarm, async () => {
      try {
        await api(`/api/alarms/${id}`, { method: "DELETE" });
        closeAlarmModal();
        await loadAlarms();
        await pollStatus();
      } catch (err) {
        showFormError(err.message || "削除できませんでした。");
      }
    });
  }

  async function loadSettings() {
    const settings = await safeApi("/api/settings", undefined, null);
    if (!settings) return;
    currentSettings = settings;
    els.settings.emfit_enabled.checked = Boolean(settings.emfit_enabled);
    els.settings.awake_confirm_sec.value = settings.awake_confirm_sec == null ? "" : Math.round(Number(settings.awake_confirm_sec) / 60);
    els.settings.grace_sec.value = settings.grace_sec ?? "";
    els.settings.poll_sec.value = settings.poll_sec ?? "";
    els.settings.ring_volume.value = Math.round((Number(settings.ring_volume) || 0) * 100);
    els.settings.none_continue_sec.value = settings.none_continue_sec ?? "";
    els.settings.max_session_sec.value = settings.max_session_sec == null ? "" : Math.round(Number(settings.max_session_sec) / 60);
    els.settings.bt_mac.value = settings.bt_mac || "";
    els.settings.default_devices.value = Array.isArray(settings.default_devices)
      ? settings.default_devices.join(", ")
      : settings.default_devices || "";
    els.settings.fallback_url.value = settings.fallback_url || "";
    updateSettingsOutputs();
  }

  async function saveSettings(event) {
    event.preventDefault();
    if (!event.submitter && document.activeElement && document.activeElement.closest(".youtube-import-panel")) return;
    await withLoading($("save-settings"), async () => {
      const defaults = els.settings.default_devices.value
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean);
      const payload = {
        emfit_enabled: els.settings.emfit_enabled.checked,
        awake_confirm_sec: Number(els.settings.awake_confirm_sec.value) * 60,
        grace_sec: Number(els.settings.grace_sec.value),
        poll_sec: Number(els.settings.poll_sec.value),
        ring_volume: Number(els.settings.ring_volume.value) / 100,
        none_continue_sec: Number(els.settings.none_continue_sec.value),
        max_session_sec: Number(els.settings.max_session_sec.value) * 60,
        default_devices: defaults.length ? defaults : ["Miku-Miku Echo"],
        bt_mac: els.settings.bt_mac.value.trim(),
        fallback_url: els.settings.fallback_url.value.trim(),
      };
      try {
        await api("/api/settings", { method: "PUT", body: JSON.stringify(payload) });
        await loadSettings();
        els.settingsMessage.textContent = "✓ 保存しました";
        els.settingsMessage.classList.add("visible");
        setTimeout(() => els.settingsMessage.classList.remove("visible"), 1800);
      } catch (err) {
        els.settingsMessage.textContent = err.message || "保存できませんでした";
        els.settingsMessage.classList.add("visible");
      }
    });
  }

  function toggleSettings() {
    const collapsed = els.settingsPanel.classList.toggle("collapsed");
    els.settingsToggle.setAttribute("aria-expanded", collapsed ? "false" : "true");
  }

  function bindDropZone() {
    ["dragenter", "dragover"].forEach((name) => {
      els.dropZone.addEventListener(name, (event) => {
        event.preventDefault();
        els.dropZone.classList.add("drag-over");
      });
    });
    ["dragleave", "drop"].forEach((name) => {
      els.dropZone.addEventListener(name, (event) => {
        event.preventDefault();
        els.dropZone.classList.remove("drag-over");
      });
    });
    els.dropZone.addEventListener("drop", (event) => {
      const file = event.dataTransfer.files && event.dataTransfer.files[0];
      if (!file) return;
      const transfer = new DataTransfer();
      transfer.items.add(file);
      els.soundFile.files = transfer.files;
      els.selectedFileName.textContent = file.name;
      AudioEditor.decodeFile(file);
    });
    els.soundFile.addEventListener("change", () => {
      const file = els.soundFile.files[0];
      els.selectedFileName.textContent = file ? file.name : "未選択";
      AudioEditor.decodeFile(file);
    });
  }

  function bindManagerDropZone() {
    ["dragenter", "dragover"].forEach((name) => {
      els.managerDropZone.addEventListener(name, (event) => {
        event.preventDefault();
        els.managerDropZone.classList.add("drag-over");
      });
    });
    ["dragleave", "drop"].forEach((name) => {
      els.managerDropZone.addEventListener(name, (event) => {
        event.preventDefault();
        els.managerDropZone.classList.remove("drag-over");
      });
    });
    els.managerDropZone.addEventListener("drop", (event) => {
      const file = event.dataTransfer.files && event.dataTransfer.files[0];
      if (!file) return;
      const transfer = new DataTransfer();
      transfer.items.add(file);
      els.soundManagerFile.files = transfer.files;
      els.managerSelectedFileName.textContent = file.name;
      ManagerAudioEditor.decodeFile(file);
    });
    els.soundManagerFile.addEventListener("change", () => {
      const file = els.soundManagerFile.files[0];
      els.managerSelectedFileName.textContent = file ? file.name : "未選択";
      ManagerAudioEditor.decodeFile(file);
    });
  }

  function trapModalKeyboard(event) {
    if (!isModalOpen()) return;
    if (event.key === "Escape") {
      event.preventDefault();
      closeAlarmModal();
      return;
    }
    if (event.key !== "Tab") return;
    const focusable = Array.from(
      els.modal.querySelectorAll('button, input, select, textarea, [tabindex]:not([tabindex="-1"])')
    ).filter((node) => !node.disabled && node.offsetParent !== null);
    if (!focusable.length) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  function addRipple(event) {
    const target = event.target.closest("button, .chip, .device-choice, .drop-zone");
    if (!target || target.disabled || target.classList.contains("loading")) return;
    const rect = target.getBoundingClientRect();
    const ripple = document.createElement("span");
    ripple.className = "ripple";
    ripple.style.left = `${event.clientX - rect.left}px`;
    ripple.style.top = `${event.clientY - rect.top}px`;
    target.appendChild(ripple);
    ripple.addEventListener("animationend", () => ripple.remove(), { once: true });
  }

  function bindEvents() {
    els.testRing.addEventListener("click", () => withLoading(els.testRing, async () => {
      await safeApi("/api/ring/test", { method: "POST", body: JSON.stringify({ mode: "sound" }) }, null);
      await pollStatus();
    }));
    els.testRealRing.addEventListener("click", () => withLoading(els.testRealRing, async () => {
      await safeApi("/api/ring/test", { method: "POST", body: JSON.stringify({ mode: "real" }) }, null);
      await pollStatus();
    }));
    els.stopRing.addEventListener("click", () => withLoading(els.stopRing, async () => {
      await safeApi("/api/ring/stop", { method: "POST" }, null);
      await pollStatus();
    }));
    els.fabAdd.addEventListener("click", () => openAlarmModal(null));
    els.settingsToggle.addEventListener("click", toggleSettings);
    els.closeModal.addEventListener("click", closeAlarmModal);
    els.cancelModal.addEventListener("click", closeAlarmModal);
    els.modalOverlay.addEventListener("click", (event) => {
      if (event.target === els.modalOverlay) closeAlarmModal();
    });
    els.form.addEventListener("submit", saveAlarm);
    els.form.addEventListener("keydown", (event) => {
      if (isComposingInput(event)) return;
      if (event.target.closest(".youtube-import-panel") && event.key === "Enter") {
        event.preventDefault();
        return;
      }
      const tag = event.target.tagName;
      const type = event.target.type;
      if (event.key === "Enter" && tag !== "TEXTAREA" && tag !== "BUTTON" && type !== "file") {
        event.preventDefault();
        els.form.requestSubmit();
      }
    });
    els.deleteAlarm.addEventListener("click", deleteAlarm);
    els.alarmKind.addEventListener("change", updateAlarmKindFields);
    els.volume.addEventListener("input", updateVolumeOutput);
    els.settingsForm.addEventListener("submit", saveSettings);
    els.settings.ring_volume.addEventListener("input", updateSettingsOutputs);
    document.querySelectorAll(".preset").forEach((button) => {
      button.addEventListener("click", () => {
        const days = button.dataset.days ? button.dataset.days.split(",").map(Number) : [];
        setDays(days);
      });
    });
    document.querySelectorAll(".tab[data-sound-tab]").forEach((tab) => {
      tab.addEventListener("click", () => setSoundTab(tab.dataset.soundTab));
    });
    els.waveformWindow.addEventListener("pointerdown", (event) => AudioEditor.startDrag(event));
    els.managerWaveformWindow.addEventListener("pointerdown", (event) => ManagerAudioEditor.startDrag(event));
    document.addEventListener("pointermove", (event) => AudioEditor.drag(event));
    document.addEventListener("pointermove", (event) => ManagerAudioEditor.drag(event));
    document.addEventListener("pointerup", (event) => AudioEditor.endDrag(event));
    document.addEventListener("pointerup", (event) => ManagerAudioEditor.endDrag(event));
    document.addEventListener("pointercancel", (event) => AudioEditor.endDrag(event));
    document.addEventListener("pointercancel", (event) => ManagerAudioEditor.endDrag(event));
    els.previewBtn.addEventListener("click", () => AudioEditor.togglePreview());
    els.managerPreviewBtn.addEventListener("click", () => ManagerAudioEditor.togglePreview());
    els.doUploadBtn.addEventListener("click", () => AudioEditor.upload());
    els.managerDoUploadBtn.addEventListener("click", () => ManagerAudioEditor.upload());
    els.downloadYoutubeBtn.addEventListener("click", () => downloadYouTubeSound({
      urlInput: els.youtubeUrl,
      filenameInput: els.youtubeFilename,
      button: els.downloadYoutubeBtn,
      status: els.youtubeStatus,
    }));
    els.managerDownloadYoutubeBtn.addEventListener("click", () => downloadYouTubeSound({
      urlInput: els.managerYoutubeUrl,
      filenameInput: els.managerYoutubeFilename,
      button: els.managerDownloadYoutubeBtn,
      status: els.managerYoutubeStatus,
    }, { switchToExisting: false }));
    bindEnterToDownload(els.youtubeUrl, els.downloadYoutubeBtn);
    bindEnterToDownload(els.youtubeFilename, els.downloadYoutubeBtn);
    bindEnterToDownload(els.managerYoutubeUrl, els.managerDownloadYoutubeBtn);
    bindEnterToDownload(els.managerYoutubeFilename, els.managerDownloadYoutubeBtn);
    document.addEventListener("keydown", trapModalKeyboard);
    document.addEventListener("click", addRipple);
    bindDropZone();
    bindManagerDropZone();
  }

  async function init() {
    bindEvents();
    updateClock();
    setInterval(updateClock, 1000);
    renderWeekdayChips();
    updateVolumeOutput();
    updateSettingsOutputs();
    await Promise.all([loadSounds(), loadDevices(), loadAlarms(), loadSettings(), pollStatus()]);
    pollTimer = setInterval(pollStatus, 1000);
    refreshTimer = setInterval(() => {
      if (!isModalOpen()) loadAlarms();
    }, 5000);
  }

  window.addEventListener("beforeunload", () => {
    if (pollTimer) clearInterval(pollTimer);
    if (refreshTimer) clearInterval(refreshTimer);
  });
  document.addEventListener("DOMContentLoaded", init);
})();
