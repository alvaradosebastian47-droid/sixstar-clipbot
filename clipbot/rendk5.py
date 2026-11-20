# rendk5.py cfg.json -> <dir>/clip_v5.mp4 · v4 TikTok nativo + branding SIX STAR (línea neón, título en caja de color, logo, placa y crédito)
# rendk4 base: · Formato clips v4 "TikTok nativo" (Sebastian 19 nov 08:56, capturas de
# Nixstah, Formula, clip.lore, Metro, willonstream): cámara ARRIBA a lo ancho, juego ABAJO a lo ancho, UN título
# en minúscula normal (oración) en cajas blancas por línea con texto negro (TikTok Sans), emojis de Apple al final,
# centrado en la unión, fijo todo el clip. Sin subtítulos, sin stickers, sin logos.
# cfg: dir, src, ss, to, fps, cam[x,y,w,h], game[x,y,w,h], title (con emojis), seam(opcional), game_shift, cam_shift, style ("box"|"outline")
import json,sys,subprocess,os,re
A_=os.environ.get("CLIPBOT_ASSETS",os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),"assets"))
from PIL import Image,ImageDraw,ImageFont,ImageFilter
c=json.load(open(sys.argv[1],encoding="utf-8")); o=c["dir"]; os.makedirs(o,exist_ok=True); ss=c["ss"]; dur=round(c["to"]-ss,3); src=c["src"]
W,H=1080,1920; FT=A_+"/fonts/TikTokSans.ttf"; EM=A_+"/emoji/"
SEAM=c.get("seam",880); G=tuple(c.get("accent",[61,240,110])); EN=G[0]>200 and G[1]<150
FM=A_+"/fonts/Montserrat-BlackItalic.ttf"
cx,cy,cw,ch=c["cam"]; gx,gy,gw,gh=c["game"]
A=W/SEAM
if cw/ch>A: nw=int(ch*A); cx+=(cw-nw)//2+int(c.get("cam_shift",0)); cw=nw
else: nh=int(cw/A); cy+=(ch-nh)//2; ch=nh
GH=H-SEAM; B=W/GH
if gw/gh>B: nw=int(gh*B); gx+=(gw-nw)//2+int(c.get("game_shift",0)); gw=nw
else: nh=int(gw/B); gy+=(gh-nh)//2; gh=nh
cw-=cw%2; ch-=ch%2; gw-=gw%2; gh-=gh%2
def font(s):
    f=ImageFont.truetype(FT,s); f.set_variation_by_axes([36,100,620,0]); return f
# tokens: palabras y emojis
EMO_RE=re.compile("([\U0001F300-\U0001FAFF☀-➿])️?")
def tokens(t):
    out=[]
    for part in re.split(r"(\s+)",t):
        if not part or part.isspace(): continue
        pieces=[p for p in EMO_RE.split(part) if p]
        if out and all(EMO_RE.fullmatch(p) for p in pieces): out[-1]+=pieces   # emojis pegados a la última palabra
        else: out.append(pieces)
    return out
def emo_png(ch,size):
    p=EM+"%x.png"%ord(ch)
    return Image.open(p).convert("RGBA").resize((size,size),Image.LANCZOS) if os.path.exists(p) else None
def wwidth(word,f,s):
    return sum((s*1.08 if EMO_RE.fullmatch(p) else f.getlength(p)) for p in word)
S=c.get("size",64); MAXW=c.get("maxw",900)
f=font(S); sp=f.getlength(" ")
lines=[];cur=[];cw_=0
for w in tokens(c["title"]):
    ww=wwidth(w,f,S)
    if cur and cw_+sp+ww>MAXW: lines.append(cur); cur=[w]; cw_=ww
    else: cur.append(w); cw_+= (sp if len(cur)>1 else 0)+ww
if cur: lines.append(cur)
LH=int(S*1.22); PADX=int(S*0.42); PADY=int(S*0.16)
ov=Image.new("RGBA",(W,H),(0,0,0,0))
y0=SEAM-len(lines)*LH/2
style=c.get("style","box")
if style=="box":
    for i,ln in enumerate(lines):
        lw=sum(wwidth(w,f,S) for w in ln)+sp*(len(ln)-1); x=(W-lw)/2; yc=y0+i*LH+LH/2
        ImageDraw.Draw(ov).rounded_rectangle([x-PADX,yc-LH/2-PADY+2,x+lw+PADX,yc+LH/2+PADY-2],radius=int(S*0.28),fill=G+(255,))
for i,ln in enumerate(lines):
    lw=sum(wwidth(w,f,S) for w in ln)+sp*(len(ln)-1); x=(W-lw)/2; yc=y0+i*LH+LH/2
    for k,w in enumerate(ln):
        for p in w:
            if EMO_RE.fullmatch(p):
                e=emo_png(p,int(S*1.0))
                if e: ov.alpha_composite(e,(int(x+S*0.04),int(yc-S*0.52)))
                x+=S*1.08
            else:
                d=ImageDraw.Draw(ov)
                if style=="box": d.text((x,yc+2),p,font=f,fill=(0,0,0),anchor="lm")
                else: d.text((x,yc+2),p,font=f,fill=(255,255,255),anchor="lm",stroke_width=int(S*0.09),stroke_fill=(0,0,0))
                x+=f.getlength(p)
        x+=sp
# --- branding SIX STAR ---
from PIL import ImageFilter as _F
gl=Image.new("RGBA",(W,H),(0,0,0,0)); gd=ImageDraw.Draw(gl); gd.rectangle([0,SEAM-5,W,SEAM+5],fill=G+(255,))
base=Image.new("RGBA",(W,H),(0,0,0,0)); base.alpha_composite(gl.filter(_F.GaussianBlur(10))); base.alpha_composite(gl)
bd=ImageDraw.Draw(base); bd.rectangle([0,SEAM-3,W,SEAM+3],fill=G+(255,))
base.alpha_composite(ov); ov=base
d=ImageDraw.Draw(ov)
# placa del streamer (arriba izq.) - discreta
FSB=A_+"/fonts/TikTokSans.ttf"
def tf(sz,wg):
    ff=ImageFont.truetype(FSB,sz); ff.set_variation_by_axes([36,100,wg,0]); return ff
nm=c["name"]; pl=c["platform"].upper(); pc=(83,252,24) if pl.startswith("KICK") else ((255,0,0) if pl.startswith("YOUTUBE") else (169,112,255))
lay=Image.new("RGBA",(W,H),(0,0,0,0)); ld=ImageDraw.Draw(lay)
f1=tf(28,650); f2=tf(22,500)
w1=ld.textlength(nm,font=f1); w2=ld.textlength(pl.title(),font=f2)
x0,y0=44,284; ww=26+w1+14+w2+22
ld.rounded_rectangle([x0,y0,x0+ww,y0+48],radius=24,fill=(0,0,0,120))
ld.ellipse([x0+14,y0+19,x0+24,y0+29],fill=pc+(255,))
ld.text((x0+34,y0+24),nm,font=f1,fill=(255,255,255,235),anchor="lm")
ld.text((x0+34+w1+12,y0+25),pl.title(),font=f2,fill=(255,255,255,170),anchor="lm")
# crédito del gameplay (abajo der.) - discreto
f3=tf(24,500); cr=c.get("credit") or (("kick.com/" if pl.startswith("KICK") else ("youtube.com/@" if pl.startswith("YOUTUBE") else "twitch.tv/"))+c["user"])
cw3=ld.textlength(cr,font=f3)
ld.rounded_rectangle([W-44-cw3-28,1452,W-44,1492],radius=20,fill=(0,0,0,110))
ld.text((W-44-cw3-14,1472),cr,font=f3,fill=(255,255,255,200),anchor="lm")
# marca de agua SIX STAR (arriba der.) - discreta
lp=A_+"/logos/logo_en_pink_1024.png" if EN else A_+"/logos/logo_sixstar_1024.png"
lg=Image.open(lp).convert("RGBA").resize((46,46),Image.LANCZOS)
mk=Image.new("L",lg.size,0); ImageDraw.Draw(mk).ellipse([0,0,45,45],fill=255)
from PIL import ImageChops
lg.putalpha(ImageChops.multiply(lg.getchannel("A"),mk))
f4=tf(22,700); wt="SIXSTAR"; w4=ld.textlength(wt,font=f4)
wx=W-44-46-10-w4
wm=Image.new("RGBA",(W,H),(0,0,0,0)); wmd=ImageDraw.Draw(wm)
wm.alpha_composite(lg,(int(wx+w4+10),285))
wmd.text((wx,308),wt,font=f4,fill=(255,255,255,255),anchor="lm")
a_=wm.getchannel("A").point(lambda v:int(v*0.7)); wm.putalpha(a_)
lay.alpha_composite(wm)
ov.alpha_composite(lay)
ov.save(o+"/ov5.png")
r=subprocess.run(["ffmpeg","-hide_banner","-ss",str(ss),"-t",str(dur),"-i",src,"-af","loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json","-f","null","-"],capture_output=True,text=True).stderr
m=json.loads(r[r.rfind("{"):r.rfind("}")+1])
ln_=f"loudnorm=I=-14:TP=-1.5:LRA=11:measured_I={m['input_i']}:measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true"
I="minterpolate=fps=60:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1:scd=fdiff:scd_threshold=8," if c.get("fps",60)<50 else "fps=60,"
# --- subtítulos palabra por palabra (opcional: "subs": true, "lang": "en"/"es") ---
SUBF=""
if c.get("subs"):
    wav=o+"/sub.wav"; subprocess.run(["ffmpeg","-v","error","-y","-ss",str(ss),"-t",str(dur),"-i",src,"-ac","1","-ar","16000",wav],check=True)
    from faster_whisper import WhisperModel
    wm=WhisperModel("small",device=os.environ.get("CLIPBOT_WHISPER_DEVICE","cpu"),compute_type="int8")
    _sg,_=wm.transcribe(wav,language=c.get("lang","en"),word_timestamps=True,vad_filter=True)
    W=[_w for _s in _sg for _w in (_s.words or []) if _w.word.strip()]
    def at(t): t=max(0,t); return "%d:%02d:%02d.%02d"%(t//3600,(t%3600)//60,int(t%60),int((t*100)%100))
    hx="&H00%02X%02X%02X"%(G[2],G[1],G[0])
    ev=[]; _i=0
    while _i<len(W):
        _g=W[_i:_i+3]
        if len(_g)>1 and _g[-1].start-_g[0].end>0.8: _g=_g[:1]
        for _k,_w in enumerate(_g):
            _st=_w.start; _en=_g[_k+1].start if _k+1<len(_g) else _w.end+0.15
            txt=" ".join(("{\\c%s}"%hx+_x.word.strip().upper()+"{\\c&H00FFFFFF}") if _j==_k else _x.word.strip().upper() for _j,_x in enumerate(_g))
            ev.append("Dialogue: 0,%s,%s,S,,0,0,0,,%s"%(at(_st),at(_en),txt))
        _i+=len(_g)
    ass="[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\n\n[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\nStyle: S,Montserrat ExtraBold,66,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,0,0,0,0,100,100,0,0,1,6,2,2,60,60,300,1\n\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"+"\n".join(ev)+"\n"
    open(o+"/subs.ass","w",encoding="utf-8").write(ass); SUBF=",ass='"+(o+"/subs.ass").replace("\\","/").replace(":","\\:")+"'"
BL=""
for i,(bx,by,bw,bh,b0,b1) in enumerate(c.get("blurs",[])):
    b0=max(0,b0-ss); b1=b1-ss
    BL+=f"[s{i}]split[s{i}a][s{i}b];[s{i}b]crop={bw}:{bh}:{bx}:{by},boxblur=20:2[s{i}c];[s{i}a][s{i}c]overlay={bx}:{by}:enable='between(t,{b0},{b1})'[s{i+1}];"
NB=len(c.get("blurs",[]))
fc=(f"[0:v]{I}null[s0];{BL}[s{NB}]split=2[a][b];"
    f"[a]crop={cw}:{ch}:{cx}:{cy},scale=1080:{SEAM}:flags=lanczos,unsharp=5:5:0.5:5:5:0.0[cam];"
    f"[b]crop={gw}:{gh}:{gx}:{gy},scale=1080:{GH}:flags=lanczos,unsharp=5:5:0.5:5:5:0.0,eq=saturation=1.05:contrast=1.03[g];"
    f"color=black:s=1080x1920:r=60:d={dur}[bk];[bk][cam]overlay=0:0[v0];[v0][g]overlay=0:{SEAM}[v1];[v1][1:v]overlay=0:0{SUBF},format=yuv420p[vout];"
    f"[0:a]{ln_},aresample=48000,aformat=channel_layouts=stereo[aout]")
cmd=["ffmpeg","-v","error","-y","-ss",str(ss),"-t",str(dur),"-i",src,"-loop","1","-i",o+"/ov5.png","-filter_complex",fc,"-map","[vout]","-map","[aout]","-t",str(dur),"-r","60",
 "-c:v","libx264","-profile:v","high","-pix_fmt","yuv420p","-preset",c.get("preset","slow"),"-crf",str(c.get("crf",12)),"-maxrate","25M","-bufsize","50M",
 "-color_primaries","bt709","-color_trc","bt709","-colorspace","bt709","-c:a","aac","-b:a","320k","-ar","48000","-ac","2","-movflags","+faststart",o+"/clip_v5.mp4"]
if "--ov" in sys.argv: print("ov",lines); sys.exit()
subprocess.run(cmd,check=True); print("done",o,dur)
