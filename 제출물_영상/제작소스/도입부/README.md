# 도입부(용어 설명) 제작 소스 — v11 (2026-10-22)
- 음성: ElevenLabs Sarah(`EXAVITQu4vr4xnSDxMaL`, eleven_multilingual_v2, with-timestamps)로 7문장을 한 번에 합성 → `intro_sarah.mp3`, 문장 시각은 `narr_intro.json`, 화면 타이밍은 `timing.json`(음성 시작 0.8초). 키는 `제출물_영상/.env.elevenlabs`(gitignore).
- 3D는 three.js 0.160.0(`npm i three@0.160.0` 후 `three.module.js`를 이 폴더에 복사), 렌더는 Playwright+Chrome.
- 순서: 로컬 서버(`python3 -m http.server 8765`) → `node render.mjs` → `python3 build.py`(BGM 덕킹·v9 본편 연결 → v11).
- 로고 png·폰트는 ../sebang_wordmark_*.png, frontend/app/fonts/PretendardVariable.woff2를 같은 폴더에 복사해 사용.
