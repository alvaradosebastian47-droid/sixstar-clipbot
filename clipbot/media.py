"""Utilidades de video: probe, frames, detección de cámara (MediaPipe) y cortes en silencios."""
import json
import os
import subprocess

import numpy as np


def probe(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=width,height,r_frame_rate,codec_type",
                        "-show_entries", "format=duration", "-of", "json", path], capture_output=True, text=True)
    d = json.loads(r.stdout)
    v = next(s for s in d["streams"] if s["codec_type"] == "video")
    n, den = v["r_frame_rate"].split("/")
    return {"w": int(v["width"]), "h": int(v["height"]), "fps": float(n) / float(den or 1),
            "dur": float(d["format"]["duration"])}


def frames(path, times, out_dir, width=720):
    os.makedirs(out_dir, exist_ok=True)
    outs = []
    for i, t in enumerate(times):
        p = os.path.join(out_dir, f"f{i}.jpg")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(t), "-i", path, "-frames:v", "1",
                        "-vf", f"scale={width}:-2", "-q:v", "4", p], check=True)
        outs.append(p)
    return outs


def _read_frame(path, t, w, h):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(t), "-i", path, "-frames:v", "1",
                          "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
    if len(raw) != w * h * 3:
        return None
    return np.frombuffer(raw, np.uint8).reshape(h, w, 3)


YUNET = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "models",
                     "face_detection_yunet_2023mar.onnx")
YUNET_URL = ("https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/"
             "face_detection_yunet_2023mar.onnx")


def _faces(img):
    """Caras (x, y, w, h, score) con OpenCV YuNet; si no hay modelo, Haar cascade."""
    import cv2
    bgr = img[:, :, ::-1].copy()
    H, W = bgr.shape[:2]
    if not os.path.exists(YUNET):
        os.makedirs(os.path.dirname(YUNET), exist_ok=True)
        try:
            import urllib.request
            urllib.request.urlretrieve(YUNET_URL, YUNET)
        except Exception:
            pass
    if os.path.exists(YUNET):
        det = cv2.FaceDetectorYN.create(YUNET, "", (W, H), 0.6, 0.3, 5000)
        _, f = det.detect(bgr)
        return [] if f is None else [(r[0], r[1], r[2], r[3], r[-1]) for r in f]
    cas = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    g = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    return [(x, y, w, h, 1.0) for x, y, w, h in cas.detectMultiScale(g, 1.1, 6, minSize=(40, 40))]


def find_facecam(path, info=None, samples=6):
    """Devuelve la caja de la cámara del streamer [x,y,w,h] o None.

    Busca caras en varios cuadros; la cámara es donde la cara aparece de forma estable
    (se expande al tamaño típico de un overlay de webcam 16:9).
    """
    info = info or probe(path)
    W, H = info["w"], info["h"]
    boxes = []
    for k in range(samples):
        t = info["dur"] * (k + 0.5) / samples
        img = _read_frame(path, t, W, H)
        if img is None:
            continue
        fs = [f for f in _faces(img) if f[2] > W * 0.025]
        if fs:
            boxes.append(max(fs, key=lambda f: f[4] * f[2]))
    if len(boxes) < max(2, samples // 3):
        return None
    fx, fy, fw, fh = (float(np.median([b[i] for b in boxes])) for i in range(4))
    # si la cara es enorme, el stream es "solo cámara" (sin juego): no sirve
    if fw > W * 0.35:
        return None
    # una cara de webcam ocupa ~22-30% del ancho del overlay
    cw = min(W * 0.5, fw * 4.0)
    ch = cw * 9 / 16
    cx = fx + fw / 2 - cw / 2
    cy = fy + fh * 0.45 - ch / 2
    cx = int(max(0, min(W - cw, cx)))
    cy = int(max(0, min(H - ch, cy)))
    return [cx, cy, int(cw), int(ch)]


def game_box(info, cam):
    """Región del juego: todo el cuadro; el render recorta al centro y se aleja del lado de la cámara."""
    W, H = info["w"], info["h"]
    shift = 0
    if cam:
        cam_center = cam[0] + cam[2] / 2
        shift = int(W * 0.08) if cam_center < W / 2 else -int(W * 0.08)
    return [0, 0, W, H], shift


def speech_bounds(path, peak_t, before=(4, 12), after=(1, 3), lang=None):
    """Ajusta inicio/fin a pausas reales del habla (faster-whisper con VAD).

    Devuelve (ss, to) en segundos dentro del archivo. Empieza en una pausa 4-12 s antes del pico
    y termina en una pausa 1-3 s después.
    """
    from faster_whisper import WhisperModel
    wav = path + ".16k.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", path, "-ac", "1", "-ar", "16000", wav], check=True)
    model = WhisperModel("small", device=os.environ.get("CLIPBOT_WHISPER_DEVICE", "cpu"), compute_type="int8")
    segs, _ = model.transcribe(wav, language=lang, word_timestamps=True, vad_filter=True)
    words = [w for s in segs for w in (s.words or [])]
    text = " ".join(w.word.strip() for w in words)
    dur = probe(path)["dur"]
    gaps = [0.0] + [words[i].end for i in range(len(words) - 1) if words[i + 1].start - words[i].end > 0.25]
    starts = [g for g in gaps if peak_t - before[1] <= g <= peak_t - before[0]]
    ss = max(starts) if starts else max(0.0, peak_t - 8)
    ends = [words[i].end for i in range(len(words) - 1)
            if words[i + 1].start - words[i].end > 0.25 and peak_t + after[0] <= words[i].end <= peak_t + after[1] + 4]
    to = min(ends) + 0.4 if ends else min(dur, peak_t + 2.5)
    to = min(dur, max(to, ss + 12))
    if to - ss > 30:
        ss = to - 30
    return round(ss, 2), round(to, 2), text


def loudest_moment(path):
    """Segundo con más energía de audio (para clips de Twitch sin pico de chat)."""
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-ac", "1", "-ar", "8000", "-f", "s16le", "-"],
                         capture_output=True).stdout
    a = np.frombuffer(raw, np.int16).astype(float)
    if len(a) < 8000:
        return 0.0
    w = 800
    r = np.sqrt(np.convolve(a * a, np.ones(w) / w, "valid"))[::w]
    t = np.arange(len(r)) * 0.1
    m = (t > 2) & (t < t[-1] - 1)
    return float(t[int(np.argmax(np.where(m, r, 0)))])
