import json,subprocess,glob
n=json.load(open('narr.json'))
def phrase(k,sub):
    t=n[k]['text'];return n[k]['st'][t.index(sub)]
def build(mode,windows,out):
    mk=[x-0.3 for x in json.load(open(f'marks{mode}.json'))];src=glob.glob(f'rec{mode}/*.webm')[0]
    assert len(windows)==len(mk)-2 or len(windows)==len(mk)-1,(len(windows),len(mk))
    parts=[];fc=[]
    segs=[(mk[i],mk[i+1]) for i in range(len(windows))]
    # 마지막 구간은 마지막 mark(여유 0.3s 포함)까지
    for i,((a,b),w) in enumerate(zip(segs,windows)):
        r=b-a
        if r>w:
            f=r/w;print(mode,i,'speed',round(f,2),'rec',round(r,1),'win',round(w,1))
            fc.append(f"[0:v]trim=start={a}:end={b},setpts=(PTS-STARTPTS)*{w/r:.5f},fps=30[p{i}]")
        else:
            print(mode,i,'freeze',round(w-r,1),'rec',round(r,1),'win',round(w,1))
            fc.append(f"[0:v]trim=start={a}:end={b},setpts=PTS-STARTPTS,fps=30,tpad=stop_mode=clone:stop_duration={w-r+0.05:.3f},trim=duration={w:.3f},setpts=PTS-STARTPTS[p{i}]")
        parts.append(f"[p{i}]")
    fc.append("".join(parts)+f"concat=n={len(parts)}:v=1:a=0,scale=1920:1080,format=yuv420p[v]")
    subprocess.run(["ffmpeg","-v","error","-y","-i",src,"-filter_complex",";".join(fc),"-map","[v]","-c:v","libx264","-crf","17",out],check=True)
    print(out,round(sum(windows),2))
def wins(k,lead=0.7,pre=0.3,tail=0.7):
    s=n[k]['sent'];D=n[k]['D'];st=[x[0] for x in s]
    w=[st[1]-lead+pre]+[st[i+1]-st[i] for i in range(1,len(st)-1)]+[D+tail-(st[-1]-lead)]
    return w
build('A',wins('n5'),'clipA.mp4')
build('B',wins('n52'),'clipB.mp4')
# C: n6의 3번째 문장만. 클립 시작=문장3 시작-0.4, 끝=D+0.7
s3=n['n6']['sent'][2][0];D=n['n6']['D'];a=phrase('n6','공정 데이터만');b=phrase('n6','한 번에')
c0=s3-0.4
build('C',[a-0.2-c0,b-a,D+0.7-(b-0.2)],'clipC.mp4')
