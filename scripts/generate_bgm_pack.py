"""Generate studio-quality royalty-free BGM tracks for Shorts clipping & EdTech reels."""

import subprocess
import wave
from pathlib import Path
import numpy as np

SR = 44100
BGM_DIR = Path(r"E:\youtube-autopilot\assets\bgm")
BGM_DIR.mkdir(parents=True, exist_ok=True)


def _write_mp3(samples: np.ndarray, out_mp3: Path):
    samples = np.clip(samples, -0.95, 0.95)
    pcm = (samples * 32767.0).astype(np.int16)
    wav_path = out_mp3.with_suffix(".wav")
    with wave.open(str(wav_path), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes(pcm.tobytes())
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(wav_path), "-codec:a", "libmp3lame", "-b:a", "192k", str(out_mp3)],
        check=True,
        capture_output=True,
    )
    wav_path.unlink(missing_ok=True)
    print(f"Generated BGM: {out_mp3} ({out_mp3.stat().st_size} bytes)")


def _kick(length_samples: int, f_start=135.0, f_end=42.0) -> np.ndarray:
    t = np.arange(length_samples) / SR
    freq = f_end + (f_start - f_end) * np.exp(-t * 28.0)
    phase = 2.0 * np.pi * np.cumsum(freq) / SR
    env = np.exp(-t * 11.0)
    return np.tanh(1.8 * np.sin(phase) * env) * 0.75


def _snare(length_samples: int, rng: np.random.Generator) -> np.ndarray:
    t = np.arange(length_samples) / SR
    noise = rng.normal(0, 1, length_samples)
    body = np.sin(2 * np.pi * 190.0 * t) * np.exp(-t * 24.0)
    env = np.exp(-t * 18.0)
    return (noise * env * 0.45 + body * 0.45)


def _hihat(length_samples: int, rng: np.random.Generator) -> np.ndarray:
    t = np.arange(length_samples) / SR
    noise = rng.normal(0, 1, length_samples)
    # simple high-pass feel via diff
    hp = np.diff(noise, prepend=0.0)
    return hp * np.exp(-t * 55.0) * 0.16


def _add_hit(buf: np.ndarray, hit: np.ndarray, pos: int, gain=1.0, pan=0.5):
    if pos >= len(buf):
        return
    n = min(len(hit), len(buf) - pos)
    l_g = gain * np.cos(pan * np.pi / 2)
    r_g = gain * np.sin(pan * np.pi / 2)
    buf[pos : pos + n, 0] += hit[:n] * l_g
    buf[pos : pos + n, 1] += hit[:n] * r_g


def make_motivational_phonk(out_mp3: Path, dur_sec: float = 30.0):
    rng = np.random.default_rng(42)
    n = int(SR * dur_sec)
    t = np.arange(n) / SR
    buf = np.zeros((n, 2), dtype=np.float64)

    bpm = 128.0
    beat_s = 60.0 / bpm
    chords = [
        [220.0, 261.63, 329.63],  # Am
        [174.61, 220.0, 261.63],  # F
        [130.81, 196.0, 261.63],  # C
        [196.0, 246.94, 293.66],  # G
    ]
    roots = [55.0, 43.65, 65.41, 49.0]  # sub-bass roots

    bar_len = 4 * beat_s
    for idx in range(int(dur_sec / bar_len) + 1):
        c_freqs = chords[idx % len(chords)]
        root = roots[idx % len(roots)]
        s0 = int(idx * bar_len * SR)
        s1 = min(n, int((idx + 1) * bar_len * SR))
        if s0 >= n:
            break
        lt = t[s0:s1] - t[s0]
        env = np.minimum(1.0, lt / 0.15) * np.minimum(1.0, (bar_len - lt) / 0.15 + 0.25)
        pad = sum(np.sin(2 * np.pi * f * lt) + 0.3 * np.sin(4 * np.pi * f * lt) for f in c_freqs) / len(c_freqs)
        sub = np.tanh(1.4 * np.sin(2 * np.pi * root * lt))
        buf[s0:s1, 0] += pad * env * 0.20 + sub * 0.32
        buf[s0:s1, 1] += pad * env * 0.20 + sub * 0.32

    k = _kick(int(0.32 * SR))
    sn = _snare(int(0.22 * SR), rng)
    hh = _hihat(int(0.08 * SR), rng)
    total_steps = int(dur_sec / (beat_s / 2))
    for step in range(total_steps):
        pos = int(step * (beat_s / 2) * SR)
        if step % 2 == 0:
            _add_hit(buf, k, pos, gain=0.85, pan=0.5)
        if step % 4 == 2:
            _add_hit(buf, sn, pos, gain=0.55, pan=0.52)
        _add_hit(buf, hh, pos, gain=0.45 if step % 2 == 1 else 0.25, pan=0.45)

    _write_mp3(buf * 0.72, out_mp3)


def make_emotional_lofi(out_mp3: Path, dur_sec: float = 32.0):
    rng = np.random.default_rng(7)
    n = int(SR * dur_sec)
    t = np.arange(n) / SR
    buf = np.zeros((n, 2), dtype=np.float64)

    bpm = 84.0
    beat_s = 60.0 / bpm
    bar_len = 4 * beat_s
    # Warm nostalgic minor-7th progression
    chords = [
        [261.63, 311.13, 392.00, 466.16],  # Cm7
        [207.65, 261.63, 311.13, 392.00],  # Abmaj7
        [233.08, 293.66, 349.23, 415.30],  # Bb7
        [196.00, 233.08, 293.66, 349.23],  # Gm7
    ]
    roots = [65.41, 51.91, 58.27, 49.00]

    for idx in range(int(dur_sec / bar_len) + 1):
        c_freqs = chords[idx % len(chords)]
        root = roots[idx % len(roots)]
        s0 = int(idx * bar_len * SR)
        s1 = min(n, int((idx + 1) * bar_len * SR))
        if s0 >= n:
            break
        lt = t[s0:s1] - t[s0]
        # Warm electric piano attack + soft sustain
        ep = np.zeros_like(lt)
        for j, f in enumerate(c_freqs):
            delay = j * 0.045
            l_lt = np.maximum(0.0, lt - delay)
            note_env = (lt >= delay) * np.exp(-l_lt * 0.75) * np.minimum(1.0, l_lt / 0.03)
            ep += (np.sin(2 * np.pi * f * l_lt) + 0.18 * np.sin(4 * np.pi * f * l_lt)) * note_env
        ep /= len(c_freqs)
        sub = np.sin(2 * np.pi * root * lt) * np.exp(-lt * 0.35)
        buf[s0:s1, 0] += ep * 0.38 + sub * 0.25
        buf[s0:s1, 1] += ep * 0.36 + sub * 0.25

    k = _kick(int(0.30 * SR), f_start=110.0, f_end=45.0)
    sn = _snare(int(0.18 * SR), rng)
    hh = _hihat(int(0.07 * SR), rng)
    for step in range(int(dur_sec / (beat_s / 2))):
        pos = int(step * (beat_s / 2) * SR)
        if step % 8 in (0, 3):
            _add_hit(buf, k, pos, gain=0.65, pan=0.5)
        if step % 8 in (2, 6):
            _add_hit(buf, sn, pos, gain=0.32, pan=0.53)
        _add_hit(buf, hh, pos, gain=0.22, pan=0.45)

    _write_mp3(buf * 0.78, out_mp3)


def make_energetic_upbeat(out_mp3: Path, dur_sec: float = 30.0):
    rng = np.random.default_rng(99)
    n = int(SR * dur_sec)
    buf = np.zeros((n, 2), dtype=np.float64)

    bpm = 118.0
    beat_s = 60.0 / bpm
    arp_notes = [523.25, 659.25, 783.99, 659.25, 440.00, 523.25, 659.25, 587.33]
    k = _kick(int(0.28 * SR))
    sn = _snare(int(0.18 * SR), rng)
    hh = _hihat(int(0.06 * SR), rng)

    for step in range(int(dur_sec / (beat_s / 2))):
        pos = int(step * (beat_s / 2) * SR)
        note_f = arp_notes[step % len(arp_notes)]
        nl = min(int(0.24 * SR), n - pos)
        if nl > 0:
            lt = np.arange(nl) / SR
            pluck = (np.sin(2 * np.pi * note_f * lt) + 0.25 * np.sin(4 * np.pi * note_f * lt)) * np.exp(-lt * 9.0)
            _add_hit(buf, pluck, pos, gain=0.26, pan=0.42 if step % 2 == 0 else 0.58)
        if step % 2 == 0:
            _add_hit(buf, k, pos, gain=0.72, pan=0.5)
        if step % 4 == 2:
            _add_hit(buf, sn, pos, gain=0.45, pan=0.5)
        _add_hit(buf, hh, pos, gain=0.35, pan=0.48)

    _write_mp3(buf * 0.75, out_mp3)


if __name__ == "__main__":
    make_motivational_phonk(BGM_DIR / "bgm_motivational_phonk.mp3")
    make_emotional_lofi(BGM_DIR / "bgm_emotional_lofi.mp3")
    make_energetic_upbeat(BGM_DIR / "bgm_energetic_upbeat.mp3")
