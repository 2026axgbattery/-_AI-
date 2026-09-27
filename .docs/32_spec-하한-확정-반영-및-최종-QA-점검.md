# 32. SPEC 하한 확정 반영 + 미해결 질문 정리 + 최종 QA 점검

## 배경/동기

사용자가 PRD §10의 남은 미해결 질문 중 3건에 대해 최종 결정을 내렸다:
1. Y(포화도) SPEC 하한 = 90% 이상, **35개 형명 전체 공통 적용**.
2. Z 중 20시간 용량 SPEC 하한 = 95% 이상, **전체 형명 공통 적용**.
3. Z 중 EN CCA·SAE CCA는 기존에 확정된 국제규격 고정 기준(EN 50342/SAE J537, `analysis/cca_spec.py`)을 그대로 유지.
4. `water_loss` 이론치 대비 실측 불일치는 **데이터 오류로 판단, 원인 규명은 보류하고 해당 지표는 해석에서 제외**.
5. `charge_amount`는 **충전 레시피의 목표치이며 실측치가 아님**으로 확정.
6. 나머지 미해결 질문(9·10·12~18)은 "잘 모르겠음" — 그대로 미해결 유지.

추가로 "실제 HTML에서 잘못 표기되거나, 글자 비율이 안 맞거나, 오류가 있는 부분이 없는지" 최종 점검을
요청함 — 마무리(finishing) 단계로 규정.

## 범위

- 문서: `docs/prd.md` §10(미해결 질문), §7(데이터 모델 스케치), `backend/db/schema.sql` 주석 갱신.
- 코드: Y·Z SPEC 하한을 **35개 형명 공통 기본값**으로 실제 판정 로직에 반영(지금까지는 `ConstantsByModel`에
  형명별로 값을 넣어야만 판정이 됐고, 실제로는 35개 중 2개 형명만 설정돼 있어 나머지는 전부
  "판정 불가"였다 — 이제 형명별 override가 없어도 기본값이 자동 적용된다).
- `water_loss_residual`/`theoretical_water_loss`: 코드 삭제는 하지 않음(어차피 아무 곳에서도
  소비하지 않는 계산값이라 disable할 대상이 없었음) — 주석으로 "해석에서 제외" 결정만 기록.
- QA: 이번 대화에서 새로 추가한 화면 요소(히어로 지표, StepFlow, 예측 화면 탭) 전반의 표기 재검토.

## 방법 (실제 반영 내용)

1. `backend/config/spec_thresholds.py`에 `DEFAULT_SPEC_LOWER_Y=90.0`/`DEFAULT_SPEC_LOWER_Z=95.0`
   추가(CCA 고정 임계값과 동일한 "형명 무관 고정값" 패턴 재사용).
2. `backend/db/repository.py` — SPEC 판정이 필요한 모든 조회 지점에 기본값을 적용:
   - `get_spec_compliance_summary`(대시보드 KPI): `COALESCE(c.spec_lower_y, ?)` 등으로 SQL 레벨에서
     기본값 적용, `models_with_spec`은 이제 "SPEC이 적용되는 형명 수"(=데이터가 있는 형명 수)를 뜻함.
   - `get_spec_threshold_for_model`(단일 모델 조회, `/prediction` 수동 시뮬레이션용): override가
     없으면 기본값이 채워진 dict를 항상 반환(더 이상 `None`을 반환하지 않음).
   - `get_failing_lots`(SPEC 미달 로트 원인진단): `ConstantsByModel` 조인을 INNER→**LEFT JOIN**으로
     변경(override 행이 아예 없는 형명도 대상이 되도록) + WHERE 절에 COALESCE 적용.
   - `get_scoring_rows`(검증·채점): SELECT 컬럼에 COALESCE 적용 — `analysis/scoring.py`는 순수
     함수로 그대로 두고, 기본값 적용은 데이터 조회 시점에서 끝냄.
3. `backend/routers/prediction.py`의 `predict_batch_unmatched`: `get_spec_thresholds()`(override
   전용 원본 목록)에 없는 형명도 기본값으로 판정하도록 폴백 로직 추가.
4. `templates/spec_thresholds_template.csv`: 35개 행 전부 `spec_lower_y=90`/`spec_lower_z=95`로
   채움(기본값과 동일한 값을 명시적으로 override하는 것은 중복이지만, 향후 특정 형명만 다르게 바꾸고
   싶을 때 편집하기 쉬운 참고용 스냅샷 역할).
5. `docs/prd.md` §10: 항목 8(charge_amount)·11(SPEC 하한)을 "해결됨"으로, 항목 7(water_loss)을
   "부분 해결"(원인 미규명, 제외 결정)로 재분류.
6. QA 점검에서 실제로 발견·수정한 것들:
   - `frontend/app/dashboard/page.tsx`의 온보딩 안내 문구가 "① 업로드 → ② 결과 확인 → ③ 상세
     조회"까지만 언급해, 바로 위 `StepFlow`(이번 세션 앞부분에 추가된 4단계 표시)와 어긋나 있었음
     — ④ 예측을 추가.
   - `frontend/app/prediction/page.tsx`의 탭 라벨에 "① 조건을 바꾸면...", "② 시험 전 로트는..."처럼
     번호를 붙였던 것이, 페이지 최상단 `StepFlow`의 "①②③④"(화면 단계)와 **같은 원 숫자 기호를
     다른 의미로 재사용**하고 있어 혼동 소지가 있었음 — 번호 제거, 문구만 유지.
   - SPEC이 이제 전체 공통 기본값으로 항상 적용되는데도 "SPEC 하한이 아직 업로드되지 않아 판정할 수
     없습니다"류의 문구가 대시보드 3곳·예측 화면 1곳·상세분석 1곳에 남아 있어 전부 "데이터가 없어서"
     프레이밍으로 교정(SPEC 미설정이 아니라 데이터 부재가 유일하게 남은 "판정 불가" 사유이므로).
   - `.hero-metrics`(직전 세션에서 추가)에 남아있던 `max-width:62ch`가 3열 그리드 전체를 좁혀 라벨이
     중간에서 줄바꿈되던 버그는 바로 이전 턴에 이미 고쳤음(재확인만).

## 완료 기준

- `pytest tests/backend`(85건, SPEC 기본값 관련 3건 갱신 + 1건 신규)·`ruff check backend`·
  `npm run build`/`npm run lint` 전부 통과.
- 데모 백엔드 재시작 후 override가 없는 형명(예: `AGM50_H1`)으로 `/api/predict/manual` 호출 시
  `spec_lower: 90.0` 기본값이 실제로 적용되는 것을 curl로 확인.
- `docs/prd.md` §10이 최신 결정을 반영하고, `CLAUDE.md`·`.docs/07`에 이력이 기록됨.
