#!/usr/bin/env python3
"""praetor-voice: local wake word -> speech-to-text -> Hermes -> text-to-speech.

Design (PRAETOR-SPEC decisions 6, 15, 17): openWakeWord stays resident (~150 MB);
faster-whisper and Piper are loaded on first use and dropped after idle_unload_seconds.
Brain: the JARVIS voice relay over Tailscale ([brain] mode = "remote") or the local
Hermes CLI ([brain] mode = "local"). No metered API anywhere.
Push-to-talk: SIGUSR1 starts a listen without a wake word (praetor-voice ptt).
"""
from __future__ import annotations
import json, os, queue, signal, subprocess, sys, threading, time, tomllib, urllib.error, urllib.request
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

    VOICE_SYSTEM = ("You are Praetor's voice on a Linux laptop (Hyprland). Answer in one to three short spoken "
                    "sentences of plain text: no markdown, lists, code blocks or URLs read aloud. If asked to open "
                    "or show something, do it with a shell command such as `uwsm-app -- firefox URL` or "
                    "`uwsm-app -- APP`, then say what you opened.")

    def ask(self, text: str) -> str:
        self.cancelled = False
        if self.mode == "remote" and self.url and self.token:
            return self._remote(text)
        return self._local(text)

    def stream(self, text: str):
        """Yield reply text deltas from the local Hermes API server (mode "api"): a persistent
        session, so no per-turn startup cost, and tokens arrive as they are generated."""
        self.cancelled = False
        base = cfg("voice.api_url", "http://127.0.0.1:8642").rstrip("/")
        keyf = Path.home() / ".config/praetor/hermes-api.key"
        key = keyf.read_text().strip() if keyf.exists() else ""
        session = cfg("voice.api_session", "praetor-voice")
        hdr = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        try:  # idempotent: 200/201 on create, 409 if it already exists
            urllib.request.urlopen(urllib.request.Request(
                f"{base}/api/sessions", data=json.dumps({"session_id": session, "title": "Praetor voice",
                "source": "praetor"}).encode(), headers=hdr), timeout=10).read()
        except urllib.error.HTTPError:
            pass
        payload = {"message": text, "system_message": cfg("voice.prompt_prefix", self.VOICE_SYSTEM)}
        req = urllib.request.Request(f"{base}/api/sessions/{session}/chat/stream",
                                     data=json.dumps(payload).encode(), headers=hdr)
        self.resp = urllib.request.urlopen(req, timeout=300)
        event, got_delta, completed = "", False, ""
        for raw in self.resp:
            if self.cancelled:
                break
            line = raw.decode("utf-8", "replace").rstrip("\n")
            if line.startswith("event:"):
                event = line[6:].strip(); continue
            if not line.startswith("data:"):
                continue
            try:
                d = json.loads(line[5:].strip())
            except json.JSONDecodeError:
                continue
            if event == "assistant.delta" and d.get("delta"):
                got_delta = True; yield d["delta"]
            elif event == "assistant.completed":
                completed = d.get("content") or ""
            elif event in ("done", "run.completed") and event == "done":
                break
        if not got_delta and completed and not self.cancelled:
            yield completed

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
        # -Q: quiet/programmatic output. It still prints a "session_id: ..." line first; drop it.
        # Voice favours latency: reasoning effort is configurable and defaults to none.
        cmd = ["hermes", "chat", "-Q", "--oneshot", "--reasoning", cfg("voice.reasoning", "none")]
        model = cfg("voice.model", "")
        if model:  # a faster model for spoken turns than the one coding sessions use
            cmd += ["-m", model]
            if cfg("voice.provider", ""):
                cmd += ["--provider", cfg("voice.provider", "")]
        toolsets = cfg("voice.toolsets", "")
        if toolsets:
            cmd += ["-t", toolsets]
        prefix = cfg("voice.prompt_prefix", (
            "Voice mode on a Linux laptop (Hyprland). Answer in one to three short spoken sentences, plain "
            "text, no markdown or lists. If the user asks you to open or show something, do it with a shell "
            "command such as `uwsm-app -- firefox URL` or `uwsm-app -- APP`, then say what you opened. "
            "User said: "))
        self.proc = subprocess.Popen(cmd + ["-q", prefix + text], stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE, text=True)
        try:
            out, err = self.proc.communicate(timeout=300)
        except subprocess.TimeoutExpired:
            self.proc.kill(); return "Hermes took too long."
        if self.cancelled:
            return ""
        lines = [l for l in (out or "").splitlines() if l.strip() and not l.startswith("session_id:")]
        reply = "\n".join(lines).strip()
        if not reply:
            reply = (err or "").strip()[-500:]
        return reply[-2000:] or "Hermes returned nothing."

    def cancel(self) -> None:
        """Barge-in while thinking: kill the in-flight Hermes call or close the stream."""
        self.cancelled = True
        p = getattr(self, "proc", None)
        if p is not None and p.poll() is None:
            p.kill()
        r = getattr(self, "resp", None)
        if r is not None:
            try:
                r.close()
            except Exception:
                pass


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

    def say(self, text: str, cancel: threading.Event | None = None) -> None:
        """Speak text sentence by sentence: synthesise sentence n+1 while sentence n plays, so the
        first words start after one short synthesis instead of the whole reply. `cancel` stops
        playback between (or during) sentences for barge-in."""
        self._touch()
        cancel = cancel or threading.Event()
        import re
        parts = [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", text) if s.strip()]
        # Group short sentences into ~200-character chunks: the first chunk starts speech quickly,
        # later chunks keep Kokoro's phrasing natural instead of clipping every sentence.
        sentences, cur = [], ""
        for s in parts:
            if cur and len(cur) + len(s) > 200:
                sentences.append(cur); cur = s
            else:
                cur = f"{cur} {s}".strip()
        if cur:
            sentences.append(cur)
        if not sentences:
            return
        if cfg("voice.tts", "piper") == "kokoro":
            try:
                return self._say_kokoro_stream(sentences, cancel)
            except Exception as e:
                log(f"kokoro failed ({repr(e)}), falling back to piper")
        self._say_piper(text)

    def _say_piper(self, text: str) -> None:
        if not self.tts_voice.exists():
            log(f"piper voice missing: {self.tts_voice}"); return
        piper = str(Path(sys.executable).parent / "piper")
        p = subprocess.Popen([piper, "--model", str(self.tts_voice), "--output-raw"],
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        play = subprocess.Popen(["pw-play", "--rate", "22050", "--format", "s16", "--channels", "1", "--raw", "-"],
                                stdin=p.stdout, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        p.stdin.write(text.encode()); p.stdin.close(); play.wait()

    def _say_kokoro(self, text: str) -> None:
        """Kokoro (82M, CPU) via kokoro-onnx: far more natural than Piper, ~500 MB when loaded."""
        if getattr(self, "kokoro", None) is None:
            from kokoro_onnx import Kokoro
            log("loading kokoro")
            self.kokoro = Kokoro(str(MODELS / "kokoro-v1.0.onnx"), str(MODELS / "voices-v1.0.bin"))
        voice = cfg("voice.kokoro_voice", "bm_george")
        lang = "en-gb" if voice.startswith("b") else "en-us"
        samples, rate = self.kokoro.create(text, voice=voice, speed=float(cfg("voice.kokoro_speed", 1.0)), lang=lang)
        play = subprocess.Popen(["pw-play", "--rate", str(rate), "--format", "f32", "--channels", "1", "--raw", "-"],
                                stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        play.stdin.write(samples.astype("float32").tobytes()); play.stdin.close(); play.wait()

    def _say_kokoro_stream(self, sentences: list[str], cancel: threading.Event) -> None:
        if getattr(self, "kokoro", None) is None:
            from kokoro_onnx import Kokoro
            log("loading kokoro")
            self.kokoro = Kokoro(str(MODELS / "kokoro-v1.0.onnx"), str(MODELS / "voices-v1.0.bin"))
        voice = cfg("voice.kokoro_voice", "bm_george")
        lang = "en-gb" if voice.startswith("b") else "en-us"
        speed = float(cfg("voice.kokoro_speed", 1.0))
        clips: queue.Queue = queue.Queue(maxsize=2)

        def synth():
            for s in sentences:
                if cancel.is_set():
                    break
                try:
                    clips.put(self.kokoro.create(s, voice=voice, speed=speed, lang=lang))
                except Exception as e:
                    log(f"kokoro synth error: {repr(e)}")
            clips.put(None)

        threading.Thread(target=synth, daemon=True).start()
        # One continuous player for the whole reply: clips are appended to its stdin as they are
        # synthesised, so there are no gaps between chunks and the phrasing matches a single pass.
        self.player = None
        try:
            while True:
                item = clips.get()
                if item is None or cancel.is_set():
                    break
                samples, rate = item
                if self.player is None:
                    self.player = subprocess.Popen(
                        ["pw-play", "--rate", str(rate), "--format", "f32", "--channels", "1", "--raw", "-"],
                        stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                try:
                    self.player.stdin.write(samples.astype("float32").tobytes()); self.player.stdin.flush()
                except BrokenPipeError:
                    break
            if self.player is not None:
                try:
                    self.player.stdin.close()
                except BrokenPipeError:
                    pass
                while self.player.poll() is None:
                    if cancel.is_set():
                        self.player.kill(); break
                    time.sleep(0.05)
        finally:
            self.player = None

    def piper_clip(self, text: str):
        import numpy as np
        piper = str(Path(sys.executable).parent / "piper")
        out = subprocess.run([piper, "--model", str(self.tts_voice), "--output-raw"], input=text.encode(),
                             capture_output=True, timeout=120).stdout
        return np.frombuffer(out, dtype="int16").astype("float32") / 32768.0, 22050

    def streamer(self, cancel: threading.Event) -> "StreamSpeaker":
        """Incremental speech: feed sentences as they arrive from a streaming reply."""
        if getattr(self, "kokoro", None) is None and cfg("voice.tts", "piper") == "kokoro":
            from kokoro_onnx import Kokoro
            log("loading kokoro")
            self.kokoro = Kokoro(str(MODELS / "kokoro-v1.0.onnx"), str(MODELS / "voices-v1.0.bin"))
        self._touch()
        return StreamSpeaker(self, cancel)

    def stop(self) -> None:
        """Barge-in: kill whatever is playing right now."""
        p = getattr(self, "player", None)
        if p is not None and p.poll() is None:
            p.kill()

    def maybe_unload(self):
        if self.stt is not None and time.time() - self.last_used > self.idle:
            log("unloading STT after idle"); self.stt = None
        if getattr(self, "kokoro", None) is not None and time.time() - self.last_used > self.idle:
            log("unloading kokoro after idle"); self.kokoro = None


class StreamSpeaker:
    """Sentences in, continuous audio out. A synth thread turns queued sentences into clips; the
    player thread appends clips to one pw-play process. First audio starts after the first
    sentence's synthesis, while the model is still generating the rest."""
    def __init__(self, speech: Speech, cancel: threading.Event):
        self.speech, self.cancel = speech, cancel
        self.sentences: queue.Queue = queue.Queue()
        self.clips: queue.Queue = queue.Queue(maxsize=3)
        self.voice = cfg("voice.kokoro_voice", "bm_george")
        self.lang = "en-gb" if self.voice.startswith("b") else "en-us"
        self.speed = float(cfg("voice.kokoro_speed", 1.0))
        self.t_synth = threading.Thread(target=self._synth, daemon=True)
        self.t_play = threading.Thread(target=self._play, daemon=True)
        self.t_synth.start(); self.t_play.start()

    def feed(self, sentence: str) -> None:
        if sentence.strip():
            self.sentences.put(sentence.strip())

    def finish(self) -> None:
        self.sentences.put(None)
        self.t_play.join()

    def _synth(self):
        while True:
            s = self.sentences.get()
            if s is None or self.cancel.is_set():
                break
            try:
                k = getattr(self.speech, "kokoro", None)
                if k is not None:
                    self.clips.put(k.create(s, voice=self.voice, speed=self.speed, lang=self.lang))
                else:  # Piper backend: synthesise via the CLI into raw s16 @ 22050 and convert
                    self.clips.put(self.speech.piper_clip(s))
            except Exception as e:
                log(f"synth error: {repr(e)}")
        self.clips.put(None)

    def _play(self):
        player = None
        try:
            while True:
                item = self.clips.get()
                if item is None or self.cancel.is_set():
                    break
                samples, rate = item
                if player is None:
                    player = subprocess.Popen(
                        ["pw-play", "--rate", str(rate), "--format", "f32", "--channels", "1", "--raw", "-"],
                        stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    self.speech.player = player
                try:
                    player.stdin.write(samples.astype("float32").tobytes()); player.stdin.flush()
                except BrokenPipeError:
                    break
            if player is not None:
                try:
                    player.stdin.close()
                except BrokenPipeError:
                    pass
                while player.poll() is None:
                    if self.cancel.is_set():
                        player.kill(); break
                    time.sleep(0.05)
        finally:
            self.speech.player = None


class Mic:
    """Capture from PipeWire's default source via pw-record: follows the user's chosen input
    (headset, laptop mic) and avoids PortAudio's raw-ALSA device picking, which delivered
    silence from the onboard DMIC and never saw USB headsets."""
    def __init__(self, q: queue.Queue, np):
        self.q, self.np = q, np
        self.proc = subprocess.Popen(
            ["pw-record", "--raw", "--rate", str(RATE), "--channels", "1", "--format", "s16", "-"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0)
        threading.Thread(target=self._pump, daemon=True).start()

    def _pump(self):
        need = FRAME * 2
        while True:
            buf = self.proc.stdout.read(need)
            if not buf:
                log("pw-record ended; restarting capture in 2s"); time.sleep(2)
                self.proc = subprocess.Popen(
                    ["pw-record", "--raw", "--rate", str(RATE), "--channels", "1", "--format", "s16", "-"],
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
        # Wake models: openWakeWord's built-ins by name (hey_jarvis...) or Praetor's own trained
        # models by name when <name>.onnx exists in the models folder (hey_praetor).
        models = []
        for m in cfg("voice.wake_models", ["hey_jarvis"]):
            custom = MODELS / f"{m}.onnx"
            models.append(str(custom) if custom.exists() else m)
        self.oww = Model(wakeword_models=models, inference_framework="onnx")
        self.threshold = float(cfg("voice.wake_threshold", 0.5))
        self.q: queue.Queue = queue.Queue()
        self.ptt = threading.Event()
        self.speech = Speech(); self.brain = Brain()
        self.busy = threading.Lock()
        self.phase = "idle"            # idle | recording | thinking | speaking
        self.cancel = threading.Event()

    def record_utterance(self, max_s=15.0, silence_s=1.2, thresh=0.012, onset_wait=0.0):
        """Collect audio until trailing silence. Returns float32 mono at 16 kHz in [-1, 1].
        onset_wait > 0: wait up to that many seconds for speech to start (follow-up turns);
        return empty audio if nobody speaks."""
        np = self.np; chunks = []; started = time.time(); last_voice = time.time()
        floor_frames = []  # first ~0.3 s measures the room noise floor; speech must rise above it
        heard_voice = False
        while True:
            if onset_wait and not heard_voice and time.time() - started > onset_wait:
                return np.zeros(0, "float32")
            try:
                c = self.q.get(timeout=1.0)
            except queue.Empty:
                break
            f = c.astype("float32") / 32768.0
            chunks.append(f)
            rms = float(np.sqrt(np.mean(f * f)))
            if len(floor_frames) < 4:
                floor_frames.append(rms)
                if len(floor_frames) == 4:
                    thresh = max(thresh, 3.0 * sum(floor_frames) / 4)
                    log(f"noise floor {sum(floor_frames) / 4:.4f}, voice threshold {thresh:.4f}")
                continue
            if rms > thresh:
                last_voice = time.time(); heard_voice = True
            if onset_wait and not heard_voice:
                continue  # still waiting for the follow-up to begin
            if time.time() - last_voice > silence_s and time.time() - started > 1.5:
                break
            if time.time() - started > max_s:
                break
        return np.concatenate(chunks) if chunks else np.zeros(0, "float32")

    def _say_fifo(self):
        """Other Praetor components (praetor-hands announce) write lines to ~/.local/state/praetor/voice.say
        and they are spoken in the assistant's voice, without starting a listening turn."""
        fifo = STATE / "voice.say"
        try:
            if fifo.exists() and not fifo.is_fifo():
                fifo.unlink()
            if not fifo.exists():
                os.mkfifo(fifo)
        except OSError as e:
            log(f"say fifo unavailable: {e!r}"); return
        while True:
            try:
                with open(fifo) as f:  # blocks until a writer opens it
                    for line in f:
                        text = line.strip()
                        if text and not self.busy.locked():
                            self.speech.say(text, threading.Event())
            except Exception as e:
                log(f"say fifo error: {e!r}"); time.sleep(1)

    def interrupt(self):
        """Barge-in: stop speaking or thinking, then listen again."""
        log("interrupt")
        self.cancel.set()
        self.brain.cancel()
        self.speech.stop()
        threading.Thread(target=self.handle, args=("interrupt",), daemon=True).start()

    def handle(self, why: str):
        # Wait briefly for a cancelled handler to unwind, then take over.
        if not self.busy.acquire(timeout=3.0):
            return
        cancel = self.cancel = threading.Event()
        followup = float(cfg("voice.followup_seconds", 6))
        try:
            turn = 0
            while True:
                turn += 1
                log(f"listening ({why if turn == 1 else 'follow-up'})")
                if turn == 1:
                    # Conversational acknowledgement instead of a chime (spoken; falls back to the chime
                    # if the list is empty). Follow-up turns just listen.
                    import random
                    greetings = cfg("voice.wake_replies", ["Yes?", "Go ahead.", "Listening.", "I'm here."])
                    if greetings:
                        self.phase = "speaking"; self.speech.say(random.choice(list(greetings)), cancel)
                    else:
                        chime("listen")
                self.phase = "recording"
                with self.q.mutex:
                    self.q.queue.clear()
                # After the first turn, wait a few seconds for a follow-up instead of a wake word.
                audio = self.record_utterance(onset_wait=followup if turn > 1 else 0.0)
                if turn > 1 and len(audio) == 0:
                    log("no follow-up; back to idle"); return
                if cfg("voice.done_chime", False):
                    chime("done")  # optional: capture finished; the streamed answer follows quickly anyway
                self.phase = "thinking"
                log(f"captured {len(audio) / RATE:.1f}s")
                if len(audio) < RATE * 0.5:
                    log("too short"); return
                text = self.speech.transcribe(audio)
                if cancel.is_set():
                    return
                if not text:
                    log("heard nothing"); self.phase = "speaking"
                    self.speech.say(cfg("voice.nothing_phrase", "I did not catch that."), cancel); return
                log(f"heard: {text}"); notify("You said", text)
                if self.brain.mode == "api":
                    # Streaming path: speak each sentence as soon as the model finishes it.
                    import re
                    self.phase = "thinking"
                    speaker = self.speech.streamer(cancel); buf = ""; reply = ""; t0 = time.time(); first = None
                    for delta in self.brain.stream(text):
                        if cancel.is_set():
                            break
                        buf += delta; reply += delta
                        while True:
                            m = re.search(r"(?<=[.!?])\s+", buf)
                            if not m:
                                break
                            sentence, buf = buf[:m.start()], buf[m.end():]
                            if first is None:
                                first = time.time() - t0; log(f"first sentence after {first:.1f}s")
                            self.phase = "speaking"; speaker.feed(sentence)
                    if not cancel.is_set():
                        speaker.feed(buf)
                    speaker.finish()
                    log(f"reply: {reply[:200]}"); notify("Praetor", reply or "(no reply)")
                else:
                    ack = cfg("voice.ack_phrase", "On it.")
                    if ack:
                        self.phase = "speaking"; self.speech.say(ack, cancel)  # spoken feedback before thinking
                    self.phase = "thinking"
                    reply = self.brain.ask(text)
                    if cancel.is_set() or not reply:
                        return
                    log(f"reply: {reply[:200]}"); notify("Praetor", reply)
                    self.phase = "speaking"
                    self.speech.say(reply, cancel)
                if cancel.is_set() or followup <= 0:
                    return
        except Exception as e:
            log(f"error: {repr(e)}"); notify("Praetor voice error", str(e))
        finally:
            self.phase = "idle"
            self.busy.release()

    def run(self):
        signal.signal(signal.SIGUSR1, lambda *_: self.ptt.set())
        STATE.mkdir(parents=True, exist_ok=True)
        (STATE / "voice.pid").write_text(str(os.getpid()))
        log(f"ready: wake={cfg('voice.wake_models', ['hey_jarvis'])} brain={self.brain.mode}")
        Mic(self.q, self.np)
        threading.Thread(target=self._say_fifo, daemon=True).start()
        if True:
            while True:
                if self.ptt.is_set():
                    self.ptt.clear()
                    if self.phase in ("thinking", "speaking"):
                        self.interrupt()
                    elif self.phase == "idle":
                        threading.Thread(target=self.handle, args=("push-to-talk",), daemon=True).start()
                if self.phase == "recording":
                    # The handler owns the microphone queue while it records; do not drain it here.
                    time.sleep(0.05); continue
                try:
                    frame = self.q.get(timeout=0.5)
                except queue.Empty:
                    self.speech.maybe_unload(); continue
                # Wake-word detection keeps running while thinking or speaking so you can barge in.
                scores = self.oww.predict(frame)
                best = max(scores.values()) if scores else 0.0
                if best >= self.threshold:
                    self.oww.reset()
                    if self.phase in ("thinking", "speaking"):
                        self.interrupt()
                    elif self.phase == "idle":
                        threading.Thread(target=self.handle, args=("wake word",), daemon=True).start()
                elif best >= 0.2:
                    log(f"wake near-miss score {best:.2f} (threshold {self.threshold})")
                self.speech.maybe_unload()


if __name__ == "__main__":
    if not cfg("voice.enabled", True):
        log("voice disabled in praetor.toml"); sys.exit(0)
    Listener().run()
