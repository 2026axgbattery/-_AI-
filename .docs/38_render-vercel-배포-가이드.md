# 38. Render(백엔드) + Vercel(프런트) 배포 가이드 (심사용)

`.docs/37_심사용-외부배포-전환-계획.md`의 후속 실행 가이드. 계정 연동·대시보드 조작은
Claude가 대신 실행할 수 없어 사용자가 직접 따라야 하는 수동 단계다.

## 0. 전제

- 배포되는 DB는 **빈 상태**로 시작한다(심사자가 `/upload`에서 CSV를 직접 올려 테스트).
- 실제 현장 raw data(사외반출 금지 대상)는 이 배포에 절대 올리지 않는다 — `templates/`의
  빈 양식 CSV만 참고용으로 존재.
- Render 무료 웹서비스는 디스크가 휘발성이다: 15분 무통신 시 슬립되고, 슬립 해제(재시작) 시
  SQLite 파일(`backend/db/app.db`)이 초기화된다. 심사 중 상태가 사라지면 다시 업로드하면 된다.

## 1. 백엔드 — Render

1. GitHub 저장소를 Render에 연결(Render 대시보드 → New → Web Service → 이 repo 선택).
2. Render가 저장소 루트의 `render.yaml`을 인식하면 Blueprint로 자동 구성된다. 자동 인식이
   안 되면 수동으로 아래 값을 입력:
   - **Environment**: Python 3
   - **Build Command**: `pip install -r backend/requirements.txt`
   - **Start Command**: `uvicorn backend.main:app --host 0.0.0.0 --port $PORT`
3. 환경변수 `ALLOWED_ORIGINS`는 일단 비워두고 배포 → 부여된 Render URL을 확인
   (예: `https://ax-backend-xxxx.onrender.com`).
4. 2번(아래)에서 Vercel URL이 나오면 Render 환경변수 `ALLOWED_ORIGINS`에 그 주소를 넣고
   재배포한다(콤마로 여러 origin 구분 가능, 예: `https://foo.vercel.app,https://foo-git-main.vercel.app`).
5. `https://<render-url>/api/health` 접속해 `{"status": "ok"}` 확인.

## 2. 프런트엔드 — Vercel

1. Vercel에서 같은 GitHub 저장소를 Import, **Root Directory를 `frontend`로 지정**.
2. Environment Variables에 추가:
   - `NEXT_PUBLIC_API_BASE_URL` = 1번에서 확인한 Render URL(끝에 슬래시 없이, 예:
     `https://ax-backend-xxxx.onrender.com`)
3. Deploy 실행 → 발급된 Vercel URL을 Render의 `ALLOWED_ORIGINS`에 추가(1-4 참조)하고
   Render를 재배포한다.
4. Vercel URL로 접속해 `/upload`에서 CSV 업로드가 실제로 되는지 확인(브라우저 개발자도구
   Network 탭에서 CORS 에러가 없는지 확인).

## 3. 로컬 개발 워크플로우 회귀 없음

- `frontend/.env.local`을 만들지 않으면(또는 비워두면) `NEXT_PUBLIC_API_BASE_URL`이 비어 있어
  기존과 동일하게 `http://127.0.0.1:8000`을 바라본다.
- 백엔드도 `ALLOWED_ORIGINS`를 설정하지 않으면 기존과 동일하게 `http://localhost:3000`만 허용한다.
- 즉 로컬 실행 명령어(`CLAUDE.md` "실행 방법" 절)는 그대로 유효하다.

## 4. 남은 제약(심사 전 인지해 둘 것)

- Render 무료 티어는 슬립/재시작 시 데이터가 사라진다 — 장기 운영용이 아니라 "심사 기간 한정" 배포.
- 실제 서비스로 전환하려면 SQLite 대신 영속 디스크(Render 유료 플랜의 Persistent Disk) 또는
  별도 DB로 전환이 필요하다(이번 범위 밖).
