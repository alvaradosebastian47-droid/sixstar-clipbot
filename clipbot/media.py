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


CAM_ASPECT = 1080 / 880   # zona de cámara del render v5 (ancho 1080, unión en y=880)


def _border(prof, lo, hi, nearest_to):
    """Índice de un borde de overlay en `prof` (fracción de píxeles con salto fuerte) dentro de [lo, hi)."""
    lo, hi = max(1, int(lo)), min(len(prof) - 1, int(hi))
    if hi <= lo:
        return None
    # un borde de overlay es una línea delgada y constante: pico alto y muy por encima de su vecindario
    idx = [i for i in range(lo, hi) if prof[i] > 0.45 and prof[i] >= prof[i - 1] and prof[i] >= prof[i + 1]
           and prof[i] > 2.5 * float(np.median(prof[max(0, i - 15):i + 16]))]
    return min(idx, key=lambda i: abs(i - nearest_to)) if idx else None


def find_facecam(path, info=None, t0=None, t1=None, samples=10):
    """Caja de la cámara del streamer [x,y,w,h] (ya en la proporción de la zona de cámara) o None.

    - Solo mira el tramo [t0, t1] que se va a publicar.
    - La cámara es donde la cara aparece en el MISMO lugar en casi todos los cuadros; caras del juego
      o de videos que el streamer está viendo se mueven y se ignoran. Si el diseño del stream cambia
      dentro del tramo (p. ej. pasa a cámara completa), devuelve None: mejor no publicar que publicar mal.
    - Busca los bordes reales del recuadro de la webcam y centra el recorte en la(s) cara(s).
    """
    info = info or probe(path)
    W, H = info["w"], info["h"]
    t0 = 0.0 if t0 is None else max(0.0, t0)
    t1 = info["dur"] if t1 is None else min(info["dur"], t1)
    frames_, dets = [], []
    for k in range(samples):
        img = _read_frame(path, t0 + (t1 - t0) * (k + 0.5) / samples, W, H)
        if img is None:
            continue
        frames_.append(img.mean(axis=2).astype(np.int16))
        dets.append([f for f in _faces(img) if f[2] > W * 0.02])
    n = len(frames_)
    if n < 4:
        return None
    # agrupa caras por posición: el grupo presente en más cuadros es la webcam
    allf = [f for d in dets for f in d]
    best, best_hits = None, 0
    for f in allf:
        cx, cy = f[0] + f[2] / 2, f[1] + f[3] / 2
        hits = sum(1 for d in dets if any(abs(g[0] + g[2] / 2 - cx) < 0.5 * f[2] and
                                          abs(g[1] + g[3] / 2 - cy) < 0.5 * f[3] for g in d))
        if hits > best_hits or (hits == best_hits and best is not None and f[4] > best[4]):
            best, best_hits = f, hits
    if best is None or best_hits < 0.7 * n:
        return None  # sin cara estable: no hay webcam o el diseño cambia en el tramo
    group = [g for d in dets for g in d if abs(g[0] + g[2] / 2 - best[0] - best[2] / 2) < 0.5 * best[2]
             and abs(g[1] + g[3] / 2 - best[1] - best[3] / 2) < 0.5 * best[3]]
    fx, fy, fw, fh = (float(np.median([g[i] for g in group])) for i in range(4))
    # cara enorme = stream "solo cámara" (sin juego): no sirve para el formato cámara + juego
    if fw > W * 0.12:
        return None
    # otras caras estables al lado (webcam compartida por 2 personas)
    mates = []
    for f in allf:
        if abs(f[1] - fy) < fh and 0.6 * fw < f[2] < 1.6 * fw and abs(f[0] - fx) > fw:
            cnt = sum(1 for d in dets if any(abs(g[0] - f[0]) < 0.5 * f[2] and abs(g[1] - f[1]) < 0.5 * f[3] for g in d))
            if cnt >= 0.7 * n and all(abs(m[0] - f[0]) > fw for m in mates):
                mates.append(f)
    # bordes del recuadro: líneas con salto de brillo fuerte y constante en todos los cuadros
    face_l = min([fx] + [m[0] for m in mates])
    face_r = max([fx + fw] + [m[0] + m[2] for m in mates])
    # se mide solo en la franja de la cara: ahí el borde del recuadro seguro pasa
    G = np.stack(frames_)
    ys = slice(int(max(0, fy)), int(min(H, fy + fh)))
    xs = slice(int(max(0, face_l)), int(min(W, face_r)))
    colp = (np.abs(np.diff(G[:, ys, :], axis=2)) > 8).mean(axis=(0, 1))   # bordes verticales
    rowp = (np.abs(np.diff(G[:, :, xs], axis=1)) > 8).mean(axis=(0, 2))   # bordes horizontales
    L = _border(colp, face_l - 4 * fw, face_l - 0.4 * fw, face_l)
    R = _border(colp, face_r + 0.4 * fw, face_r + 4 * fw, face_r)
    T = _border(rowp, fy - 3 * fh, fy - 0.4 * fh, fy)
    B = _border(rowp, fy + fh * 1.4, fy + 4.5 * fh, fy + fh)
    L = (L + 1) if L is not None else max(0.0, face_l - 1.6 * fw)
    R = R if R is not None else min(float(W), face_r + 1.6 * fw)
    T = (T + 1) if T is not None else max(0.0, fy - 1.3 * fh)
    B = B if B is not None else min(float(H), fy + fh + 2.2 * fh)
    # el recorte más grande con la proporción de la zona de cámara que quepa en el recuadro,
    # centrado en las caras (y con la cara un poco arriba del centro)
    rw, rh = R - L, B - T
    cw, ch = (rh * CAM_ASPECT, rh) if rw / rh > CAM_ASPECT else (rw, rw / CAM_ASPECT)
    ccx = (face_l + face_r) / 2
    x = min(max(L, ccx - cw / 2), R - cw)
    y = min(max(T, fy + fh * 0.5 - ch * 0.42), B - ch)
    return [int(x), int(y), int(cw) - int(cw) % 2, int(ch) - int(ch) % 2]


def game_is_dark(path, info, cam, t0, t1, samples=5, min_luma=14):
    """True si el juego (todo menos la cámara) está casi negro en el tramo: carga, pausa, pantalla negra."""
    W, H = info["w"], info["h"]
    vals = []
    for k in range(samples):
        img = _read_frame(path, t0 + (t1 - t0) * (k + 0.5) / samples, W, H)
        if img is None:
            continue
        m = np.ones((H, W), bool)
        x, y, w, h = cam
        m[y:y + h, x:x + w] = False
        vals.append(float(img.mean(axis=2)[m].mean()))
    return bool(vals) and float(np.median(vals)) < min_luma


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
