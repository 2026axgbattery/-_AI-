# 영상 제작 소스 (v8)
순서: 음성(ElevenLabs with-timestamps → narr.json) → render.mjs(인포그래픽 프레임, timing_v8.json) → rec.mjs(MODE=A/B/C 앱 녹화, 문장별 마크) → clips.py(마크·문장 시간에 맞춰 클립 재배치) → final8.py(BGM 덕킹 + 합성).
경로는 작업 폴더(frames/, rec*/ 등) 기준이라, 임시 폴더에 이 파일들을 복사하고 node/ffmpeg가 PATH에 있는 상태에서 실행한다.
앱 녹화는 임시 서버(백엔드 8010 AX_DB_PROFILE=rec + 프런트 3010)와 더미 데이터 업로드·분석 실행이 선행돼야 한다.
