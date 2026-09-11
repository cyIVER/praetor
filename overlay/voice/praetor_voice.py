#!/usr/bin/env python3
"""praetor-voice: local wake word -> speech-to-text -> Hermes -> text-to-speech.

Design (PRAETOR-SPEC decisions 6, 15, 17): openWakeWord stays resident (~150 MB);
faster-whisper and Piper are loaded on first use and dropped after idle_unload_seconds.
Brain: the JARVIS voice relay over Tailscale ([brain] mode = "remote") or the local
Hermes CLI ([brain] mode = "local"). No metered API anywhere.
Push-to-talk: SIGUSR1 starts a listen without a wake word (praetor-voice ptt).
"""
from __future__ import annotations
import json, os, queue, signal, subprocess, sys, threading, time, tomllib, urllib.request
from pathlib import Path

CFG = Path("/etc/praetor/praetor.toml")
STATE = Path.home() / ".local/state/praetor"
MODELS = Path.home() / ".local/share/praetor/voice/models"
RATE = 16000
FRAME = 1280  # 80 ms at 16 kHz, openWakeWord's native chunk


def cfg(path: str, default):
    try:
        node = tomllib.loads(CFG.read_text())
        for p in path.split("."):
            node = node[p]
        return node
    except Exception:
        return default


def log(msg: str) -> None:
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def notify(title: str, body: str) -> None:
    subprocess.Popen(["notify-send", "-a", "Praetor", title, body[:300]],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def chime(kind: str) -> None:
    f = MODELS / f"chime-{kind}.wav"
    if f.exists():
        subprocess.Popen(["pw-play", str(f)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


class Brain:
    """remote: JARVIS voice relay (SSE). local: hermes chat -q."""
    def __init__(self):
        # voice.brain: "local" (hermes chat -q on this machine) or "remote" (JARVIS voice relay).
        self.mode = cfg("voice.brain", "local")
        self.url = cfg("voice.relay_url", "")
        tokf = Path.home() / ".config/praetor/voice-relay.token"
        self.token = tokf.read_text().strip() if tokf.exists() else ""

    def ask(self, text: str) -> str:
        if self.mode == "remote" and self.url and self.token:
            return self._remote(text)
        return self._local(text)

    def _remote(self, text: str) -> str:
        req = urllib.request.Request(self.url.rstrip("/") + "/voice/chat/stream",
                                     data=json.dumps({"message": text}).encode(),
                                     headers={"Authorization": f"Bearer {self.token}",
                                              "Content-Type": "application/json"})
        reply, event = "", ""
        with urllib.request.urlopen(req, timeout=300) as r:
            for raw in r:
                line = raw.decode("utf-8", "replace").rstrip("\n")
                if line.startswith("event:"):
                    event = line[6:].strip()
                elif line.startswith("data:") and event in ("assistant.completed", "assistant.delta"):
                    try:
                        d = json.loads(line[5:].strip())
                    except json.JSONDecodeError:
                        continue
                    if event == "assistant.completed" and d.get("content"):
                        reply = d["content"]
                    elif event == "assistant.delta":
                        reply += d.get("delta") or d.get("content") or ""
        return reply.strip() or "I got no answer from mission control."

    def _local(self, text: str) -> str:
        # -Q: quiet/programmatic output (no banner, box art, or session footer).
        out = subprocess.run(["hermes", "chat", "-Q", "--oneshot", "-q", text],
                             capture_output=True, text=True, timeout=300)
        reply = (out.stdout or "").strip()
        if not reply:
            reply = (out.stderr or "").strip()[-500:]
        return reply[-2000:] or "Hermes returned nothing."


class Speech:
    """Lazy-loaded STT (faster-whisper) and TTS (Piper) with idle unload."""
    def __init__(self):
        self.stt = None
        self.tts_voice = MODELS / f"{cfg('voice.piper_voice', 'en_US-lessac-medium')}.onnx"
        self.last_used = 0.0
        self.idle = int(cfg("voice.idle_unload_seconds", 300))

    def _touch(self):
        self.last_used = time.time()

    def transcribe(self, audio) -> str:
        if self.stt is None:
            from faster_whisper import WhisperModel
            size = cfg("voice.stt_model", "small")
            log(f"loading faster-whisper {size} (int8)")
            self.stt = WhisperModel(size, device="cpu", compute_type="int8", download_root=str(MODELS))
        self._touch()
        segments, _ = self.stt.transcribe(audio, language="en", beam_size=1, vad_filter=True)
        return " ".join(s.text.strip() for s in segments).strip()

    def say(self, text: str) -> None:
        self._touch()
        if not self.tts_voice.exists():
            log(f"piper voice missing: {self.tts_voice}"); return
        piper = str(Path(sys.executable).parent / "piper")
        p = subprocess.Popen([piper, "--model", str(self.tts_voice), "--output-raw"],
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        play = subprocess.Popen(["pw-play", "--rate", "22050", "--format", "s16", "--channels", "1", "--raw", "-"],
                                stdin=p.stdout, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        p.stdin.write(text.encode()); p.stdin.close(); play.wait()

    def maybe_unload(self):
        if self.stt is not None and time.time() - self.last_used > self.idle:
            log("unloading STT after idle"); self.stt = None


class Mic:
    """Capture from PipeWire's default source via pw-record: follows the user's chosen input
    (headset, laptop mic) and avoids PortAudio's raw-ALSA device picking, which delivered
    silence from the onboard DMIC and never saw USB headsets."""
    def __init__(self, q: queue.Queue, np):
        self.q, self.np = q, np
        self.proc = subprocess.Popen(
            ["pw-record", "--rate", str(RATE), "--channels", "1", "--format", "s16", "-"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0)
        threading.Thread(target=self._pump, daemon=True).start()

    def _pump(self):
        need = FRAME * 2
        while True:
            buf = self.proc.stdout.read(need)
            if not buf:
                log("pw-record ended; restarting capture in 2s"); time.sleep(2)
                self.proc = subprocess.Popen(
                    ["pw-record", "--rate", str(RATE), "--channels", "1", "--format", "s16", "-"],
                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0)
                continue
            while len(buf) < need:
                more = self.proc.stdout.read(need - len(buf))
                if not more:
                    break
                buf += more
            self.q.put(self.np.frombuffer(buf, dtype="int16").copy())


class Listener:
    def __init__(self):
        import numpy as np
        from openwakeword.model import Model
        self.np = np
        models = cfg("voice.wake_models", ["hey_jarvis"])
        self.oww = Model(wakeword_models=list(models), inference_framework="onnx")
        self.threshold = float(cfg("voice.wake_threshold", 0.5))
        self.q: queue.Queue = queue.Queue()
        self.ptt = threading.Event()
        self.speech = Speech(); self.brain = Brain()
        self.busy = threading.Lock()

    def record_utterance(self, max_s=15.0, silence_s=1.2, thresh=0.012):
        """Collect audio until trailing silence. Returns float32 mono at 16 kHz in [-1, 1]."""
        np = self.np; chunks = []; started = time.time(); last_voice = time.time()
        while True:
            try:
                c = self.q.get(timeout=1.0)
            except queue.Empty:
                break
            f = c.astype("float32") / 32768.0
            chunks.append(f)
            rms = float(np.sqrt(np.mean(f * f)))
            if rms > thresh:
                last_voice = time.time()
            if time.time() - last_voice > silence_s and time.time() - started > 1.5:
                break
            if time.time() - started > max_s:
                break
        return np.concatenate(chunks) if chunks else np.zeros(0, "float32")

    def handle(self, why: str):
        if not self.busy.acquire(blocking=False):
            return
        try:
            chime("listen"); log(f"listening ({why})")
            with self.q.mutex:
                self.q.queue.clear()
            audio = self.record_utterance()
            chime("done")  # capture finished; now transcribing
            log(f"captured {len(audio) / RATE:.1f}s")
            if len(audio) < RATE * 0.5:
                log("too short"); return
            text = self.speech.transcribe(audio)
            if not text:
                log("heard nothing"); self.speech.say(cfg("voice.nothing_phrase", "I did not catch that.")); return
            log(f"heard: {text}"); notify("You said", text)
            ack = cfg("voice.ack_phrase", "On it.")
            if ack:
                self.speech.say(ack)  # spoken feedback before the brain starts thinking
            reply = self.brain.ask(text)
            log(f"reply: {reply[:200]}"); notify("Praetor", reply)
            self.speech.say(reply)
        except Exception as e:
            log(f"error: {repr(e)}"); notify("Praetor voice error", str(e))
        finally:
            self.busy.release()

    def run(self):
        signal.signal(signal.SIGUSR1, lambda *_: self.ptt.set())
        STATE.mkdir(parents=True, exist_ok=True)
        (STATE / "voice.pid").write_text(str(os.getpid()))
        log(f"ready: wake={cfg('voice.wake_models', ['hey_jarvis'])} brain={self.brain.mode}")
        Mic(self.q, self.np)
        if True:
            while True:
                if self.ptt.is_set():
                    self.ptt.clear()
                    threading.Thread(target=self.handle, args=("push-to-talk",), daemon=True).start()
                if self.busy.locked():
                    # A handler owns the microphone queue while it records; do not drain it here.
                    time.sleep(0.05); continue
                try:
                    frame = self.q.get(timeout=0.5)
                except queue.Empty:
                    self.speech.maybe_unload(); continue
                scores = self.oww.predict(frame)
                best = max(scores.values()) if scores else 0.0
                if best >= self.threshold:
                    self.oww.reset()
                    threading.Thread(target=self.handle, args=("wake word",), daemon=True).start()
                elif best >= 0.2:
                    log(f"wake near-miss score {best:.2f} (threshold {self.threshold})")
                self.speech.maybe_unload()


if __name__ == "__main__":
    if not cfg("voice.enabled", True):
        log("voice disabled in praetor.toml"); sys.exit(0)
    Listener().run()
