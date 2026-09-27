# PRD: AI 포화도 예측 / 전지 성능 최적화 웹앱

**작성 기준**: 세방전지 품질본부 창원 품질경영팀 3일 집체 PBL MVP + v1.1 확장
**담당자**: 김경준 주임 | **작성일**: 2026-09-10 | **최종 개정**: 2026-09-24(200줄 이하 축약본)

> 이 문서는 §1~§11 구조를 유지한 **축약본**이다. 각 결정의 상세 근거(더미 데이터 수치, 논의 경위)는
> `history/prd_2026-09-10_상세본.md`(원본)에 그대로 있다 — 결론이 궁금하면 이 문서, "왜 그렇게
> 정했는지" 경위가 궁금하면 원본을 보라. 섹션 번호(§1-1, §6-①~⑤, §10-1~20)는 코드 주석·다른
> 문서에서 그대로 인용하므로 절대 바꾸지 않는다.
>
> ⚠️ **더미 데이터 유의사항**: 이 문서의 구체 수치(상관계수 등)는 더미 데이터(`process_data.csv`
> 100행/`test_data.csv` 59행) 예시일 뿐, 실제 SPEC·임계값에 하드코딩하지 않는다. 확정되는 것은
> **구조와 방법론**(2단 캐스케이드, 무차원화, 판정·진단 로직)이지 개별 숫자가 아니다.

---

## 1. 문제 정의

창원 품질경영팀은 매월 전지 **포화도**를 관리하려고 공정/시험 데이터를 Excel로 취합해 **공정인자별로
개별 수작업 비교분석**을 한다. 고통 3가지: (1) 복합 인자를 개별로만 봐서 핵심 영향인자·우선순위가
경험적 판단에 좌우됨, (2) 분석 결과가 DB화되지 않아 매달 반복·재현 불가, (3) 시험은 샘플만 하므로
시험 전 로트는 포화도·성능을 사전에 알 방법이 없음.

**2단 캐스케이드**(X→Y→Z)가 (3)을 해소한다: 공정인자(X)만으로 포화도(Y)를 먼저 예측하고, X+Y로
성능(Z)까지 연달아 예측 — **시험을 한 번도 안 거친 로트도 X만 있으면 Y·Z를 다 얻는다.** "포화도가
성능으로 이어지는 매개 지표"라는 이 과제의 핵심 가설이다. 현재 월 1회·10시간이 여기 소요된다.

## 1-1. 핵심 용어 정의 (혼용 금지)

| 용어 | 정의 | 산출식 | 범위 |
|---|---|---|---|
| **포화도(saturation)** | 전해액/총 공극 부피 비율 | 공극 상수 필요(모델별 세퍼레이터·극판 공극률) | **확보 불투명**(§10-6) — 설계 기밀 가능성, 스트레치 목표 |
| **잔존율(retention rate)** | 전해액 주입량 대비 남은 액량 비율 — Y의 **근사 대체 지표** | `(fill_weight − water_loss) / fill_weight × 100` | 전 로트 즉시 산출 가능 |
| **capacity_rate** | 실측 20시간 용량/정격용량 — **Z 계열 지표**(포화도 아님, §10-1) | `discharge_amount / rated_capacity × 100` | 시험 매칭 로트만 |

**확정**: 공극 상수 미확보 → **Y = 잔존율(proxy)**, `saturation_basis='proxy_retention'`/`saturation_source='derived'` 항상 병기(§10-6 부분 해결 — basis는 모델마다 다르고 source는 계산+실측 병행이나, 정확한 계산식은 설계 기밀 가능성으로 확보 불투명). **Z 절대값 = `discharge_amount`(Ah)**, `capacity_rate`는 그 %.

## 2. 타겟 사용자

**김경준(품질경영팀, 운영자)**: 매월 CSV 업로드 + 수기입력 2항목(§6-②) + 회귀결과 보고. 로컬 PC, 사외반출 금지.
**생산기술팀(열람자)**: 입력 권한 없이 대시보드·원인진단만 열람. "우리 라인 부적합 원인을 바로 알고 싶다."

## 3. 목표와 비목표

**Goals**: X→Y→Z 2단 관계 정량화(회귀계수) + X만으로 Y·Z 연쇄 산출 · 월 10시간→2시간(80%↓) · 분석이력 SQLite 축적 · 미시험 로트 Y·Z 일괄 예측 · 부적합 로트 원인 자동지목+개선권고 · ①~⑤ 종단간 무오류 동작.

**Non-goals(→v2, 10월)**: R²/RMSE 정식 검증·train/val 분리 · 재학습 파이프라인 정식화 · 캐스케이드 vs 베이스라인 정량 비교 · `saturation_calc` 활성화 · 실운영 데이터 최종교체 검증 · 외부 API/LLM 연동(로컬 전용) · 사용자 인증·다중동시편집 인프라.

## 4. 사용자 스토리 (요지)

분석 담당자는 CSV 업로드만으로 자동 매칭 → 부족한 값(§6-②)만 채우면 → X→Y, X+Y→Z 회귀·VIF를 자동으로 얻고 → 매달 이력이 쌓이며 → 미시험 로트도 Y·Z를 일괄 예측받고 → 부적합 로트는 원인 인자·개선권고가 자동 지목되길 원한다. 열람자는 본인 라인 부적합의 원인·권고를 직접 확인하고 싶어 하고, 후임자는 전임자의 회귀계수·SPEC 기준을 그대로 이어받고 싶어 한다.

## 5. 기능 목록

| 구분 | 기능 |
|---|---|
| **MVP** | ① 업로드+자동매칭 · ② 수기입력(그룹 일괄) · ③-1 X→Y 회귀+VIF · ③-2 X+Y→Z 회귀+X→Z 베이스라인 · ③-3 형명별 상세비교 · ③-4 형명별 Y 추이 · KPI 대시보드+이력저장 · ④-1/② 미매칭 로트 Y·Z 일괄예측 · ⑤ SPEC 판정+원인 자동지목 |
| **v1.1(완료)** | SAE/EN CCA(Z2/Z3) 이중예측 · 충전 STEP 이탈도(X 신규) · EN/SAE CCA 규격 고정기준 합격배지 |
| **v2(10월)** | R²/RMSE 정식검증 · 재학습 파이프라인 · 캐스케이드 vs 베이스라인 정량비교 · `saturation_calc` 활성화 |
| **이후** | 이상 사전예측 · 사내망 다중사용자 배포 · 역할기반 접근제어 |

## 6. MVP 기능별 요구사항

**① 업로드·매칭**: 공정/시험 CSV 업로드(파일선택+드래그드롭), `lot_id` 자동 조인, 미매칭 다수는 **정상**(매칭률만 표시), 필수컬럼 누락 시 업로드 차단. 매칭 결과 화면 하단에 ②가 바로 이어짐(별도 페이지 아님) — 단 회귀 실행은 명시 버튼 필요(자동 아님).

**② 수기입력**(①과 같은 화면): 대상은 **전해액온도·수조온도 2항목뿐**(2026-09-21부터 — 충전량은 `ChargeProgramSpec`(형명·바이어별 충전 STEP 기준표)가 대체해 제외됨). MT(V)/MT(A)는 수기입력 대상 아님(test_data 매칭 시만 자동 채움, §10-5). 그룹화 기준: **형명+생산일자**(같은 형명이 같은 날 같은 수조에 투입되므로). 기본은 미입력 로트만 반영, "덮어쓰기" 체크 시 확인 다이얼로그 후 전체 반영. 미입력 남은 로트는 1단 회귀 대상에서 자동 제외.

**③-1 X→Y 회귀**: X는 **`process_data.csv` 컬럼만**(MT(V)/(A)는 test_data 전용이라 미매칭 로트에 없음 → 제외, 참고지표로만 시험로트 한정 사용, §10-5). **1단 X셋**: `electrolyte_temp`·`tank_temp`·`soaking_time_sec`·`aging_days`·`formation_dv`(=voltage_2nd−voltage_1st)·`cell_weight_mean/std`·`charge_ratio`·`charge_program_deviation_pct`(신규, 충전 STEP 기준 대비 이탈%, 기준표 없으면 NULL→해당 로트 제외). **`fill_weight`/`water_loss`는 Y 정의 변수라 반드시 제외**(포함 시 상관−1.0 항등식). `bath_no`/`circuit_no`는 통제변수(회귀계수 대상 아님). `charge_amount` 대신 `charge_ratio` 사용(정격용량 상관 0.995→0.043로 해소, §10-2). VIF 산출·표시 필수.

**③-2 X+Y→Z 회귀+베이스라인**: **Z=`discharge_amount`**(Ah 확정, §10-1). 학습은 반드시 **실측 Y**로(Ŷ 학습 시 오차 누적). 운영 추론 시에만 Ŷ 투입, 결과에 "Ŷ 기반" 플래그. **베이스라인(X→Z 직접회귀)를 병행 구축**해 캐스케이드 우위를 나중에 검증할 수 있게 함(정량비교는 v2). 시험매칭 로트만 학습데이터, 미매칭은 순수 추론 대상. **1단은 매달, 2단·베이스라인은 시험주기(월/분기)에만 재학습** — 화면에 stage별 최근 학습시점 분리 표시(`AnalysisRun.is_latest_for_stage`).

**③ 공통 — 감액 분해**: `theoretical_water_loss = 0.336 × overcharge_ah`, `water_loss_residual = water_loss − theoretical`. 잔차 +면 증발/누액 의심, 0 근방 정상, −면 화성부족/계량오류(AGM은 VRLA라 산소재결합으로 작게 나올 수 있음). 더미셋은 이론치 대비 실측이 ~139배 커 **SOP 미확인 상태**(§10-7) — 구조만 구현, 절대값 해석은 "참고용, 검증 전" 표기.

**③-3 형명별 상세**: 35개 형명(6개 용량군)을 X 인자평균·Y·Z 한 표로 비교, 반드시 무차원 인자로(원본값 비교 금지). 미시험 형명은 "미시험"으로 부적합과 구분. AnalysisRun을 `model_name` group-by한 조회 화면(별도 학습 없음).

**③-4 형명별 Y 추이**: `ProcessData`/`TestData`/`LotDerived`는 append-only 누적(덮어쓰지 않음). `prod_date` 기준 일/월/연 집계, SPEC 하한선 병기, 연간 추이는 최소 2개년 필요. 단순 시계열 조회(회귀와 무관).

**④ 예측**: ④-1 미매칭 로트 X→Y 일괄산출 + 수동 조건입력 Y 계산. ④-2 Ŷ+X를 2단에 투입해 Z 일괄예측("Ŷ 기반" 플래그).

**⑤ SPEC 판정·원인진단**: Y·Z 각각 모델별 SPEC 하한과 비교해 pass/fail(§10-11 하한값 자체는 미확정). 부적합 로트는 "회귀계수×SPEC이탈도" 기준 원인 인자 자동지목(Y/Z 인자셋 다를 수 있음, §10-12 동률처리 미확정) + 규칙기반 개선권고("주액량 증대"로만 귀결되지 않게 설계). **EN/SAE CCA 규격 배지는 이 SPEC 판정과 별개 로직**(형명 무관 고정 전압·시간 임계값 — EN: 10초 전압≥7.5V AND 6.0V까지≥90초 / SAE: 7.2V까지≥30초, `analysis/cca_spec.py`) — 표본 극소로 원인진단 대상은 아니고 참고 배지로만 노출.

## 7. 데이터 모델 스케치

> append-only(`Lot`/`ProcessData`/`TestData`/`LotDerived`는 매달 새 레코드로 누적, 동일 `lot_id` 재업로드는 이상상태로 경고). 전체 DDL은 `.docs/03_sqlite-스키마-설계.md`.

```
Lot: lot_id(PK) · model_name(예 AGM105_S1, 정격용량 인코딩) · rated_capacity · line_no · prod_date · ingested_at

ProcessData(lot_id당 1행, append-only): cell1~6_weight/ginap · fill_weight·water_loss(Y산출원천, 1단X 제외)
  · voltage_1st/2nd · bath_no·circuit_no(통제변수) · soaking_time_sec·aging_days
  · electrolyte_temp·charge_amount·tank_temp(수기입력 가능 항목)

TestData(lot_id당 1행, 부분매칭): initial_voltage/resistance/weight/cca · rated_capacity
  · discharge_amount(Z 확정값) · charge_amount_20h · capacity_rate · charge_rate
  · mt_voltage/mt_current(시험전용, 1단X 제외) · sae_cca·en_cca(Z2/Z3, 방전량Ah)
  · en_cca_10s_voltage·en_cca_6v_hold_sec·sae_cca_7v2_hold_sec(CCA 규격판정용 체크포인트, §6-⑤)
  · tested_at(더미엔 없음, §10-14)

ConstantsByModel: model_name(PK) · rated_capacity · saturation_basis_target('cell'|'separator')
  · void_volume_separator/plate·free_volume·design_fill_weight·fill_sg(전부 확보 불투명, §10-6)
  · spec_lower_y·spec_lower_z(§10-11 미확정, NULL 허용)

ChargeProgramSpec(마스터, 재업로드 시 전체교체): rated_capacity · buyer_code('All'=전체적용)
  · program_label·is_variant·charge_hours·total_charge_ah·total_electricity_c·steps_json

LotDerived(lot_id PK): retention_rate(Y) · water_loss_rate/per_ah · theoretical_water_loss·water_loss_residual
  · fill_per_rated·charge_ratio(무차원화) · cell_weight_mean/std · formation_dv · charge_program_deviation_pct
  · saturation_calc(항상 NULL, §10-6) · saturation_basis('proxy_retention' 고정) · saturation_source('derived' 고정) · derived_at

AnalysisRun(이력): run_id(PK) · run_at · stage('x_to_y'|'xy_to_z'|'x_to_z_baseline'|'xy_to_sae_cca'|'xy_to_en_cca')
  · lot_range · correlation_matrix·regression_coefficients·vif(JSON) · r_squared(참고용) · is_latest_for_stage

Prediction: prediction_id(PK) · lot_id(FK, nullable) · run_id(FK) · target('y'|'z'|'sae_cca'|'en_cca')
  · predicted_value · input_y_source('measured'|'predicted') · source('manual'|'batch_unmatched') · predicted_at

SpecJudgment: lot_id/prediction_id(FK) · target(위와 동일 4종) · spec_result(pass|fail) · spec_thresholds_used(JSON)

CauseDiagnosis: lot_id/prediction_id(FK) · target(위와 동일) · ranked_factors(JSON, 계수×이탈도) · recommendation_text · generated_at
```

## 8. 엣지 케이스 (요지)

미매칭 다수=정상 / 매칭 0건=이상경고 / 수기입력 누락 로트=1단 제외 / 표본 부족=경고+저신뢰 명시 / 물리적 불가능 예측값=이상치 플래그 / SPEC 동시이탈=계수×이탈도 우선순위(동률 규칙 미확정, §10-12) / 모델 크기차=무차원 인자로 해소 / Y구성변수를 X 재사용 금지(완전공선) / water_loss 이론치 불일치=SOP 확인 전 보류 플래그 / 동일 bath·circuit=조/회로별 잔차 별도표시 / VIF 잔존=경고 / 2단 예측 Ŷ오차전파="Ŷ 기반" 플래그 구분 / X·Y·Z 갱신주기 상이=stage별 학습시점 분리표시 / 동일 lot_id 재업로드=이상상태 경고 / 연간추이 1개년뿐=안내로 대체(보간 금지) / SQLite 동시접근=쓰기 담당자·열람 읽기전용 / 외부전송 시도=애초에 네트워크 호출 없음 / SPEC 미설정=판정불가 안내.

## 9. 성공 지표

시간단축(10h→2h, 80%↓) · 파이프라인 완결성(①~⑤ 종단간 무오류 1회 이상) · 예측 커버리지(미매칭 로트 Y·Z 산출률 100%) · 캐스케이드+베이스라인 둘 다 구현(정량비교는 v2) · 이상로트 탐지(`water_loss_residual` 상대순위로 1건 이상) · 재현성(규칙기반 100% 동일결과) · 이력 누락없이 축적. R²/RMSE·캐스케이드 정량비교는 의도적으로 이번 MVP 기준에서 제외(v2).

## 10. 미해결 질문 (Open Questions, 번호 고정 — 코드·문서에서 인용됨)

**해결됨**: 1) Z=`discharge_amount`, capacity_rate는 %표현, charge_amount_20h는 Z 아님(§10-1). 2) 정규화는 물리적 무차원화(charge_ratio 등)로 확정. 3) 모델 수는 28개 아닌 **35개**. 4) `fill_weight`/`water_loss`는 1단 X에서 반드시 제외. 5) MT(V)/(A)는 시험전용 측정값(완성전압 편차·간이 CCA), 1단 X 제외 확정. 19) `model_name` 접미문자=바이어/스펙 구분코드로 확정 채택(`ChargeProgramSpec.buyer_code`에 반영).

**부분 해결**: 6) 포화도 basis는 모델마다 다르게 관리, source는 계산+실측 병행 확인됨 — 계산식 자체는 확보 불투명(설계기밀 가능성). 20) 수기입력 통합화면 확정, 단 **그룹값과 다른 예외 로트 편집 경로는 미해결**(개별편집 API는 존치·화면 미연결).

**여전히 담당자 확인 필요**: 7) water_loss 측정 SOP(이론치 대비 실측 ~139배 불일치 원인). 8) charge_amount가 레시피 목표치인지 실측치인지. 9) 화성 후 비중 데이터 확보 가능성. 10) 모델별 공극부피 상수 확보 가능성. 11) Y·Z SPEC 하한값(모델별). 12) 원인 인자 동률 처리 규칙. 13) 유관부서 열람 경로(IP 공유 vs 파일 공유). 14) `tested_at` 실제 데이터 존재 여부. 15) 시험주기 정확한 확정(MVP는 이벤트 기반 재학습으로 대응). 16) 형명별 최소 표본 임계값 n(예시 5). 17) 상관계수에 p-value 배지 표시 여부. 18) 포화도 정의의 SOC·압착률 전제조건.

## 11. 관련 문서

| 문서 | 내용 | 위치 |
|---|---|---|
| 도메인 상수 | 화성 반응 상수, 액 질량 역산식 | `docs/domain-constants.md` |
| 상관관계 신뢰성 검증 | p-value 유의성 재검증, 표본크기 문제 | `docs/correlation-reliability-review.md` |
| 과제개발기획서 | 실행 로드맵·기술전략 부록 | `docs/AX전문가과정_과제개발기획서_창원품질경영팀 김경준 주임_v2.docx` |
| 아키텍처 | Next.js/FastAPI 폴더구조·화면-API 매핑 | `.docs/02_nextjs-fastapi-구현-아키텍처.md` |
| 스키마 설계(DDL) | §7을 `CREATE TABLE`로 구체화 | `.docs/03_sqlite-스키마-설계.md` |
| 기술 스택 정의서 | 배포환경·라이브러리·로드맵 | `.docs/04_기술-스택-정의서.md` |
| 3일 실행계획(완료, 참고용) | Day1~3 완료기준 | `history/phase/phase_01~03_plan.md` |
| PRD 상세본(원본, 참고용) | 모든 결정의 논의 경위·더미데이터 수치 | `history/prd_2026-09-10_상세본.md` |
| 구현 현황 전체 | v1.1까지 전체 변경이력 | `CLAUDE.md` "저장소 현재 상태" |
