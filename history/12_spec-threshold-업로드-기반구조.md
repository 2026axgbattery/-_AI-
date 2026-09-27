# 12. SPEC 임계값(spec_lower_y/spec_lower_z) 업로드 기반구조

## 배경/동기

Y·Z 각각의 SPEC 판정(⑤, `prd.md` §6-⑤)은 형명별 SPEC 하한값(`ConstantsByModel.spec_lower_y`/`spec_lower_z`)이 있어야 가능하다. 이 값은 `prd.md` §10 Open Question #11에서 아직 담당자 확인 전 미확정 상태로 남아 있고, DDL(`.docs/03_sqlite-스키마-설계.md`)도 두 컬럼을 NULL 허용으로 설계해뒀다.

방금 별도로 논의한 결론(회귀·상관 분석은 SPEC 없이 데이터만으로 하고, SPEC은 ⑤ 판정 단계에서만 참조)에 따라, 회귀 로직(Day 2)에는 SPEC이 필요 없다. 다만 나중에 담당자가 형명별 SPEC 값을 확정해 전달했을 때 **바로 시스템에 반영할 수 있는 통로**가 있으면 Day 3(⑤ 구현) 착수가 빨라진다. 이번 작업은 그 통로 — SPEC 값을 담을 CSV 템플릿과, 그 CSV를 읽어 DB(`ConstantsByModel`)에 반영하는 최소 기반구조 — 를 미리 만들어두는 것이다.

## 범위

- **포함**: `templates/spec_thresholds_template.csv`(35개 형명이 미리 채워진 입력 양식), `POST /api/spec-thresholds/upload`(CSV 업로드 → 검증 → `ConstantsByModel` upsert), `GET /api/spec-thresholds`(현재 저장된 값 조회 — 향후 화면 연동용).
- **비범위**: SPEC 판정 로직(`judge_spec`, ⑤ 자체)·화면 UI(그룹 일괄 입력 화면 같은 프런트 연동)는 Day 3 범위로 남겨둔다. 이번 작업은 "값을 받아서 읽어 저장"까지만 한다. `void_volume_separator`/`void_volume_plate`/`free_volume` 등 나머지 `ConstantsByModel` 컬럼(포화도 실계산용, `domain-constants.md`에 따라 확보 자체가 불투명한 스트레치 목표)은 템플릿에 포함하지 않는다 — 이번 요청은 "스펙(SPEC)" 값에 한정된다.

## 방법

1. `templates/spec_thresholds_template.csv`: 컬럼 `model_name, rated_capacity, spec_lower_y, spec_lower_z`. `process_data.csv`에서 확인된 35개 형명·정격용량을 미리 채우고, `spec_lower_y`/`spec_lower_z`는 담당자가 채워 넣도록 빈 칸으로 둔다.
2. `backend/db/repository.py`에 `upsert_spec_thresholds`/`get_spec_thresholds` 추가: `model_name` 기준 upsert(값이 있는 컬럼만 갱신, 이미 저장된 다른 `ConstantsByModel` 컬럼은 건드리지 않음).
3. `backend/routers/spec_thresholds.py`(신규 라우터): 업로드 시 필수 컬럼(`model_name`, `spec_lower_y`, `spec_lower_z`) 검증 → 누락 시 400. `rated_capacity`가 비어 있으면 `derive.parse_rated_capacity_from_model_name`으로 보완.
4. `backend/main.py`에 라우터 등록.
5. curl로 템플릿 CSV 업로드 → `GET /api/spec-thresholds`로 반영 확인.

## 완료 기준

- 템플릿 CSV가 35개 형명을 모두 포함하고 `spec_lower_y`/`spec_lower_z`는 담당자가 바로 채워 넣을 수 있는 빈 칸 상태다.
- 템플릿을 값 채워서 업로드하면 `ConstantsByModel`에 반영되고, 비워둔 채 업로드해도(NULL) 오류 없이 저장된다(§10-11 미확정 상태를 그대로 반영).
- 기존 회귀·업로드 기능에 부작용이 없다(회귀 로직은 이 테이블을 참조하지 않으므로 영향 없음).
