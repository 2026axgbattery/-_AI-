import json,subprocess,numpy as np,wave
T=json.load(open("timing.json"));SR=44100
V="/Users/junny_macbook/무제 폴더/제출물_영상/"
B=V+"BGM후보/A_Calm-Ambient-1_cynicmusic.mp3"
load=lambda p:np.frombuffer(subprocess.check_output(["ffmpeg","-v","error","-i",p,"-f","f32le","-ac","2","-ar",str(SR),"-"]),dtype=np.float32).reshape(-1,2)
N_D=json.load(open("narr_intro.json"))["D"];TOT=T["end"];N=int(TOT*SR);nar=np.zeros((N,2),np.float32)
a=load("intro_sarah.mp3");k=int(0.8*SR);nar[k:k+len(a)]+=a[:N-k]
bgm=load(B)[:N].copy()
t=np.arange(N)/SR;target=np.zeros(N)
target[(t>=0.8-0.15)&(t<=0.8+N_D+0.1)]=-20.0
g=np.zeros(N);cur=0.0;ka=1-np.exp(-3/(0.3*SR));kr=1-np.exp(-3/(0.8*SR))
for i in range(N):
    tg=target[i];k=ka if tg<cur else kr;cur+=(tg-cur)*k;g[i]=cur
env=np.ones(N);fi=int(1.5*SR);fo=int(1.2*SR);env[:fi]*=np.linspace(0,1,fi)**2;env[-fo:]*=np.linspace(1,0,fo)
mix=nar*1.0+bgm*((10**(g/20))*env*0.5)[:,None]
pk=float(np.abs(mix).max());print("peak",pk)
if pk>0.95: mix*=0.95/pk
w=wave.open("mix_intro.wav","wb");w.setnchannels(2);w.setsampwidth(2);w.setframerate(SR);w.writeframes((mix*32767).astype("<i2").tobytes());w.close()
# 도입부 mp4
subprocess.run(["ffmpeg","-y","-v","error","-framerate","30","-i","frames/f%05d.jpg","-i","mix_intro.wav","-t",str(TOT),"-vf","fade=t=in:st=0:d=0.4","-c:v","libx264","-preset","medium","-crf","18","-pix_fmt","yuv420p","-c:a","aac","-b:a","192k","intro.mp4"],check=True)
# 본편(v9) 이어붙이기
out=V+"하이브리드_최종_v11.mp4"
subprocess.run(["ffmpeg","-y","-v","error","-i","intro.mp4","-i",V+"하이브리드_최종_v9.mp4","-filter_complex","[0:v][0:a][1:v][1:a]concat=n=2:v=1:a=1[v][a]","-map","[v]","-map","[a]","-c:v","libx264","-preset","medium","-crf","18","-pix_fmt","yuv420p","-c:a","aac","-b:a","192k",out],check=True)
print(subprocess.check_output(["ffprobe","-v","error","-show_entries","format=duration,size","-of","csv=p=0",out]).decode())
