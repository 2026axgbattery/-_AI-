# 14. 실제 Raw Data 업로드 지원 계획

> **완료(2026-09-11)**: 아래 계획대로 `backend/etl/process_raw.py`·`backend/etl/test_raw.py`를 구현하고, 실제 두 원본 파일(공정 32,088행, 시험 12행)을 브라우저 업로드 화면으로 직접 올려 에러 없이 적재됨을 확인했다(`pytest tests/backend` 13건 통과, `ruff check backend` 통과). 이 문서는 컬럼 매핑 근거 자료로 계속 참조되므로 `history/`로 옮기지 않고 `.docs/`에 유지한다.
>
> **버그 수정(2026-09-11 추가)**: 세 번째 실제 raw data 파일(`AGM90_(조립3라인).xls`, 공정 데이터, 2279행)을 업로드하니 **파일 전체가 업로드 실패**하는 문제가 있었다. 원인: 이 파일에는 `Model Name` 셀이 완전히 빈 게 아니라 **공백 문자만 채워진 경우**(예: `"              "`)가 5행 있었는데, `pd.isna()` 기준으로는 이런 셀이 결측으로 잡히지 않아 파서가 이를 유효한 값으로 취급했고, 이후 `strip()`을 거치며 빈 문자열이 됐다. 빈 model_name으로 `parse_rated_capacity_from_model_name`을 호출하면 `ValueError`가 나는데 이걸 개별 행 단위로 잡지 않아서, 딱 5개 행의 문제로 2279행 전체 업로드가 실패했다. **수정**: `process_raw.py`/`test_raw.py` 둘 다 `lot_id`/`model_name`을 먼저 `strip()`한 뒤에 빈 문자열인지 확인하도록 변경(순서를 바꾼 것뿐, `_blank()` 자체는 그대로) — 이제 이런 행은 개별적으로 건너뛰고 나머지 2274행은 정상 적재된다(실제 파일로 재확인: 2274/2279행 적재, 브라우저 업로드 시 콘솔 에러 없음). 회귀 테스트: `tests/backend/test_process_raw.py::test_whitespace_only_model_name_is_skipped_not_crashed`, `tests/backend/test_test_raw.py::test_whitespace_only_lot_id_is_skipped_not_crashed`.

## 배경/동기

지금까지의 업로드 파이프라인은 `process_data.csv`/`test_data.csv` 형태(1로트=1행, 정해진 컬럼명)의 정제된 CSV만 가정하고 있었다. 사용자가 실제 현장에서 쓰는 원본 파일 두 개를 제공했다:

- `260811-0820 D라인 전체 고율방전 ★.xls` — 공정 라인 실적 데이터(향후 `process_data`로 들어갈 raw data). 32,088행 × 134컬럼, 2단 헤더(구분/시험항목 섹션명 + 세부 필드명), 컬럼 위치가 아니라 **(섹션, 필드) 라벨**로 의미가 정해짐.
- `AGM 시험현황_raw data.xlsx` — 시험 데이터(향후 `test_data`로 들어갈 raw data). 시트 1개(`3N+(현대)`)당 세로로 긴 시험항목 트리 + 가로로 샘플(로트) 20개인 **전치된(transposed)** 구조. 신뢰성 서브시험(EN CCA, SAE CCA, 부식, 수분소모 등)별로 선택된 일부 샘플만 값이 채워진다.

두 파일 모두 기존 `templates/spec_thresholds_template.csv` 같은 "빈 템플릿"이 아니라 **현장 설비/시스템이 그대로 뽑아낸 원본**이므로, 목표 스키마(`.docs/03_sqlite-스키마-설계.md`의 `ProcessData`/`TestData`)로 변환하는 파서가 필요하다.

## 분석 결과 요약 (컬럼 매핑)

### 공정 raw → `ProcessData`

| 목표 컬럼 | raw 소스 (섹션 / 필드) | 비고 |
|---|---|---|
| `lot_id` | `serial no` | |
| `model_name` | `Model Name` | |
| `line_no` | `Tinning` 섹션의 `Line No` (값 1~4) | `Model Name` 바로 뒤 `Line No`(값 1~7)는 다른 의미의 라인 코드라 제외 |
| `prod_date` | `Stacker Weight` 섹션 `Date/Time`의 날짜부 | 공정 최초 단계 타임스탬프 |
| `cell1~6_weight` | `Stacker Weight` 섹션 `Cell N Weight` | |
| `cell1~6_ginap` | `Stacker Force` 섹션 `Cell N Force` | "긴압" |
| `fill_weight` | `Filling` 섹션 `Fill Weight` | |
| `water_loss` | `Pre Test(Weight)` 섹션 `Water Loss` | |
| `voltage_1st` | `Pre Test(OCV)` 섹션 `Voltage` (숙성 전) | |
| `voltage_2nd` | `Final Test(HRD/OCV)` 섹션 `OCV` (숙성 후) | `Internal Res` 섹션은 전체 0% 채움이라 사용 불가 |
| `bath_no` | `Charging(Bath)` 섹션 `Bath No` | |
| `circuit_no` | `Charging(Bath)` 섹션 `Circiut No` | |
| `soaking_time_sec` | `Charging(Bath)` 섹션 `Soaking Time` (`"N분M초"`) | 정규식으로 초 단위 환산 |
| `aging_days` | `Aging Pallet` 섹션 `Aging End` − `Aging Start` | 두 값 모두 `yyyymmdd`가 기본이나, 일부 `Aging Start`는 `yyyymmddHHMMSS` 전체 타임스탬프로 저장돼 있어 **앞 8자리만 날짜로 파싱**해야 함(확인됨: End는 항상 8자리, Start는 8자리/14자리 혼재) |
| `electrolyte_temp` | **raw에 해당 컬럼 없음** | 사용자 확인: NULL로 적재하고 기존 수기입력(그룹 일괄 입력) UI로 채운다 |
| `tank_temp` | **raw에 해당 컬럼 없음** | 위와 동일 |
| `charge_amount` | **raw에 해당 컬럼 없음**(`Charging(Bath)`엔 시간/회로 정보만 있고 충전량(Ah) 필드가 없음) | 기존 수기입력 그룹 일괄 입력이 이미 `charge_amount`를 지원하도록 설계돼 있었음 — 동일하게 NULL 적재 후 수기입력으로 채운다 |

컬럼별 결측률 편차가 크다(`Stacker Weight/Force` 65%, `Term Welding` 62%, `Charging(Bath)` 블록 51% 등) — 이는 라인마다 설비가 달라 일부 공정을 건너뛰기 때문으로 보이며, append-only 원칙 + 기존 수기입력 NULL 허용 설계로 그대로 수용 가능하다.

### 시험 raw → `TestData`

| 목표 컬럼 | raw 소스 | 비고 |
|---|---|---|
| `lot_id` | `제조로트` 행 | |
| `initial_voltage` | `전압` 행(초기상태) | |
| `initial_resistance` | `내부저항` 행(초기상태) | |
| `initial_weight` | `중량` 행(초기상태) | |
| `initial_cca` | `MT(A)` 행 | **사용자 확인**: 이 raw data 체계에서 MT(A)가 곧 CCA(콜드크랭킹) 측정치와 동일 개념 — `mt_current`와 동일 원본 값을 `initial_cca`에도 함께 반영 |
| `mt_voltage` | `MT(V)` 행 | |
| `mt_current` | `MT(A)` 행 | `initial_cca`와 동일 원본 셀 |
| `rated_capacity` | 시트 헤더(예: `AGM70`) 또는 `model_name` 정규식 파싱 | 기존 `analysis/derive.py`의 `parse_rated_capacity_from_model_name` 재사용 |
| `discharge_amount` | `20HR용량(1차)` 섹션 `방전량` | |
| `charge_amount_20h` | `20HR용량(1차)` 섹션 `충전량` | |
| `capacity_rate` | `20HR용량(1차)` 섹션 `용량(%)` | |
| `charge_rate` | `20HR용량(1차)` 섹션 `충전율(%)` | |

`20HR용량(1차)`이 비어 있는 샘플(신뢰성 서브시험 대상이 아니어서 아직 측정 안 됨 — 이번 시트 20개 중 8개)은 **행을 만들지 않고 건너뛴다**(초기상태만 있고 용량 데이터가 없는 로트는 test_data 자체가 아직 존재하지 않는 것과 같음).

## 범위

- `backend/etl/process_raw.py`, `backend/etl/test_raw.py`: 웹 프레임워크 비의존 순수 함수. `.xls`/`.xlsx` 파일을 읽어 `ingest_process_rows`/`ingest_test_rows`가 기대하는 dict 리스트로 변환.
  - 컬럼 위치가 아니라 (섹션 라벨, 필드 라벨) 매칭으로 대상 컬럼을 찾는다(향후 파일에서 컬럼 순서가 바뀌어도 견고하도록).
- `backend/requirements.txt`에 `openpyxl`(xlsx), `xlrd`(구 xls) 추가.
- `backend/routers/upload.py`: 기존 `POST /api/upload/process`, `POST /api/upload/test`가 파일 확장자로 CSV 경로/raw 파서 경로를 분기하도록 확장(엔드포인트 URL은 그대로 유지, 프런트 변경 최소화).
- `frontend/`: 업로드 드롭존이 `.xls`/`.xlsx`도 허용하도록 `accept` 속성 확장.
- `tests/backend/`: 두 파서에 대한 단위 테스트(soaking time 파싱, aging_days의 8자리/14자리 혼재 처리, 용량 데이터 없는 샘플 skip, MT(A)→initial_cca/mt_current 이중 반영).

## 완료 기준

- 두 실제 raw 파일을 API로 업로드했을 때 에러 없이 적재되고, `GET /api/upload/summary`에 반영된 행 수가 기대치(공정 32,088행, 시험 12행 — 이번 시트 기준)와 일치한다.
- `pytest tests/backend` 통과, `ruff check backend` 통과.
- 브라우저에서 실제 업로드 후 업로드 이력·매칭 요약이 정상 표시됨을 확인한다.
- 전해액온도/수조온도/충전량이 NULL로 들어간 로트가 기존 수기입력 그룹 일괄 입력 화면에 정상적으로 잡히는지 확인한다.
