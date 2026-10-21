import json,subprocess,numpy as np,wave
T=json.load(open("timing_v8.json"));n=json.load(open("narr.json"));SR=44100
V="/Users/junny_macbook/무제 폴더/제출물_영상/"
B=V+"BGM후보/A_Calm-Ambient-1_cynicmusic.mp3"
load=lambda p:np.frombuffer(subprocess.check_output(["ffmpeg","-v","error","-i",p,"-f","f32le","-ac","2","-ar",str(SR),"-"]),dtype=np.float32).reshape(-1,2)
N=int(T["TOT"]*SR);nar=np.zeros((N,2),np.float32)
parts=[("n3",T["T0"]),("n4",T["T1"]),("n5",T["T2"]),("n52",T["T52"]),("n6",T["T3"]),("n7",T["T4"])]
for k,t0 in parts:
    a=load(V+f"음성_본편/{k}.mp3");i=int(t0*SR);nar[i:i+len(a)]+=a[:N-i]
bgm=load(B)
if len(bgm)<N:
    xf=SR;w_=np.linspace(0,1,xf)[:,None];o=bgm
    while len(o)<N+xf: o=np.vstack([o[:-xf],o[-xf:]*(1-w_)+bgm[:xf]*w_,bgm[xf:]])
    bgm=o
bgm=bgm[:N].copy()
t=np.arange(N)/SR;target=np.zeros(N)
for k,a in parts: target[(t>=a-0.15)&(t<=a+n[k]["D"]+0.1)]=-20.0
g=np.zeros(N);cur=0.0;ka=1-np.exp(-3/(0.3*SR));kr=1-np.exp(-3/(0.8*SR))
for i in range(N):
    tg=target[i];k=ka if tg<cur else kr;cur+=(tg-cur)*k;g[i]=cur
env=np.ones(N);fi=int(2*SR);fo=int(2*SR);env[:fi]*=np.linspace(0,1,fi)**2;env[-fo:]*=np.linspace(1,0,fo)
mix=nar+bgm*((10**(g/20))*env*0.5)[:,None]
pk=float(np.abs(mix).max());print("peak",pk)
if pk>0.95: mix*=0.95/pk
w=wave.open("mix_v8.wav","wb");w.setnchannels(2);w.setsampwidth(2);w.setframerate(SR);w.writeframes((mix*32767).astype("<i2").tobytes());w.close()
TOT=T["TOT"]
s6=n["n6"]["sent"][2][0]
clips=[("clipA.mp4",T["T2"]-0.3,T["T2"]+n["n5"]["D"]+0.7),("clipB.mp4",T["T52"]-0.3,T["T52"]+n["n52"]["D"]+0.7),("clipC.mp4",T["T3"]+s6-0.4,T["T3"]+n["n6"]["D"]+0.7)]
fc=[];chain="[0:v]";en=[]
for i,(f,a,b) in enumerate(clips):
    fc.append(f"[{i+1}:v]fps=30,format=yuva420p,setpts=PTS-STARTPTS+{a}/TB,fade=t=in:st={a}:d=0.5:alpha=1,fade=t=out:st={b-0.4}:d=0.4:alpha=1[c{i}]")
    fc.append(f"{chain}[c{i}]overlay=eof_action=pass[o{i}]");chain=f"[o{i}]"
    en.append(f"between(t,{a+0.5},{b-0.4})")
fc.append(f"[4:v]format=rgba[chip];{chain}[chip]overlay=x=60:y=1000:enable='{'+'.join(en)}',fade=t=out:st={TOT-0.8}:d=0.8[v]")
out=V+"하이브리드_최종_v9.mp4"
args=["ffmpeg","-y","-v","error","-framerate","30","-i","frames/f%05d.jpg"]
for f,a,b in clips: args+=["-i",f]
args+=["-loop","1","-i","chip.png","-i","mix_v8.wav","-filter_complex",";".join(fc),"-map","[v]","-map","5:a","-t",str(TOT),"-c:v","libx264","-preset","medium","-crf","18","-pix_fmt","yuv420p","-c:a","aac","-b:a","192k",out]
subprocess.run(args,check=True)
print(subprocess.check_output(["ffprobe","-v","error","-show_entries","format=duration,size","-of","csv=p=0",out]).decode())
