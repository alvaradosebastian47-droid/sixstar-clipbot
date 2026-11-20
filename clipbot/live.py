"""Grabación en vivo con Streamlink: buffer circular de N minutos por stream.

Cada stream se graba en segmentos de 10 s nombrados con la hora UNIX de inicio
(work/live/<login>/<epoch>.ts). Así un pico de chat (hora real) se corta del buffer
en segundos, sin esperar a que Twitch procese el VOD.
"""
import glob
import os
import signal
import subprocess
import time

PROCS = {}


def _dir(workdir, login):
    d = os.path.join(workdir, "live", login)
    os.makedirs(d, exist_ok=True)
    return d


def start(workdir, login):
    p = PROCS.get(login)
    if p and p.poll() is None:
        return
    d = _dir(workdir, login)
    cmd = (f"streamlink --twitch-disable-ads --stdout https://twitch.tv/{login} 1080p60,1080p,best "
           f"| ffmpeg -v error -i - -c copy -f segment -segment_time 10 -reset_timestamps 1 "
           f"-strftime 1 '{d}/%s.ts'")
    PROCS[login] = subprocess.Popen(cmd, shell=True, preexec_fn=os.setsid,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def stop(login):
    p = PROCS.pop(login, None)
    if p and p.poll() is None:
        os.killpg(os.getpgid(p.pid), signal.SIGTERM)


def sync(workdir, logins, buffer_minutes=15):
    """Mantiene grabando exactamente `logins`; borra segmentos viejos."""
    for l in list(PROCS):
        if l not in logins:
            stop(l)
    for l in logins:
        start(workdir, l)
    cutoff = time.time() - buffer_minutes * 60
    for f in glob.glob(os.path.join(workdir, "live", "*", "*.ts")):
        try:
            if int(os.path.basename(f)[:-3]) < cutoff:
                os.remove(f)
        except (ValueError, OSError):
            pass


def cut(workdir, login, t0, t1, out):
    """Corta [t0, t1] (hora UNIX) del buffer. Devuelve out o None si no hay cobertura."""
    d = _dir(workdir, login)
    segs = sorted((int(os.path.basename(f)[:-3]), f) for f in glob.glob(d + "/*.ts"))
    sel = [(t, f) for t, f in segs if t + 10 > t0 and t < t1]
    if not sel or sel[0][0] > t0 + 5:
        return None
    lst = out + ".txt"
    with open(lst, "w") as f:
        f.write("".join(f"file '{p}'\n" for _, p in sel))
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst,
                    "-ss", str(max(0, t0 - sel[0][0])), "-t", str(t1 - t0),
                    "-c:v", "libx264", "-crf", "10", "-preset", "veryfast", "-c:a", "aac", "-b:a", "320k", out],
                   check=True)
    return out
