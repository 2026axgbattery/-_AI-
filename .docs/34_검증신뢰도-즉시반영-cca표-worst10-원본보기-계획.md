# 34. 검증 신뢰도 즉시 반영 + CCA 관계표 Worst 10·원본 데이터 별도 화면

## 배경/동기
사용자가 대시보드 스크린샷 2장으로 두 가지를 지적했다.

1. "검증 신뢰도" 카드가 분석을 실행해도 계속 "미채점"으로 남아 있고, "검증 자세히 보기 →"를
   눌러도 아무것도 펼쳐지지 않는다.
2. "포화도(Y) ↔ CCA(저온시동전류) 관계 확인" 표에 로트가 아주 많을 때 전부 나열돼 있고,
   "팀장 피드백 반영"이라는 사용자에게 불필요한 문구가 노출돼 있다.

## 원인
1. `handleRunAnalysis`(1·2단 회귀 실행)는 `refresh()`만 호출해 "가장 최근 채점 결과 조회"만
   할 뿐, 채점 자체(`POST /api/scoring/run`)는 별도 "다시 채점" 버튼을 눌러야만 실행된다 —
   분석을 처음 실행한 시점에는 채점 이력 자체가 없어 카드가 계속 "미채점"으로 보인다.
   또한 "검증 자세히 보기" 링크가 `#evidence`(가장 바깥 `evidence-toggle` details 자체의 id)로
   걸려 있는데, 앵커가 가리키는 대상이 `<details>` 그 자체일 때는 브라우저가 그 조상 details를
   강제로 펼치는 대상이 아니라서(스펙상 "닫힌 details의 후손"에만 강제 오픈이 적용됨) 실제로는
   아무 것도 펼쳐지지 않는다. 게다가 그 안에 채점 섹션도 별도의 닫힌 `<details className="evidence">`로
   한 번 더 감싸여 있어 이중으로 닫혀 있었다.
2. `repository.get_y_vs_cca_pairs`는 SAE/EN CCA 실측값이 있는 로트를 개수 제한 없이 전부
   반환한다 — 최근 AGM60/70 더미 데이터가 형명당 5,000건 규모로 커지면서 표가 수백~수천 행이
   될 수 있다.

## 범위
- `/dashboard`
  - `handleRunAnalysis`가 회귀 실행 직후 4개 채점 target을 함께 실행하도록 변경.
  - "검증 자세히 보기" 링크가 실제로 두 겹의 details를 모두 펼치도록 앵커 대상을 안쪽
    콘텐츠 div로 이동.
  - "포화도(Y)↔CCA" 표: 위쪽에 EN/SAE 규격 기준 대비 여유가 가장 적은(불합격 우선) 10건만
    표시, "팀장 피드백 반영" 문구 제거, 표 아래 "전체 원본 데이터 보기 →"(새 창) 링크 추가.
- 백엔드: `GET /api/analysis/y-vs-cca`에 `limit`·`sort=worst` 쿼리 파라미터 추가(EN/SAE 각각의
  기준 대비 여유율을 계산해 가장 나쁜 순 정렬), `total_count` 필드 추가. 기존 무제한 호출과의
  하위 호환을 위해 파라미터 생략 시 기존과 동일하게 전체를 lot_id 순으로 반환.
- 신규 프런트 라우트 `/dashboard/y-vs-cca`: `detail-analysis/lots/[model]` 새 창 raw data
  화면과 동일한 패턴으로 전체 로트를 페이지네이션 없이 표시(상한 2,000건, 기존
  `FULL_VIEW_LIMIT` 관례 재사용).

## 완료 기준
- `pytest tests/backend` / `ruff check backend` 통과(백엔드 쿼리 파라미터 추가에 대한 테스트
  포함).
- `npm run build` / `npm run lint` 통과.
- 데모 백엔드로 `GET /api/analysis/y-vs-cca?limit=10&sort=worst` curl 확인.
