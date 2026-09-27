# SEBANG Design System (docs/design.md)

> 세방그룹 CI(Corporate Identity)를 기반으로 만든 범용 디자인 가이드입니다.
> 웹, 모바일 앱, 사내 툴, 프레젠테이션 등 어떤 프로젝트에도 그대로 적용할 수 있도록
> 컬러 토큰·타이포그래피·간격·컴포넌트 원칙·접근성 기준까지 정리했습니다.
>
> 출처: [세방그룹 CI/FONT](https://www.sebanggroup.com/client/ko/company/ci), [세방 CI 소개](https://www.sebang.com/contents/01_03.asp) — 세방전지(gbattery.com)를 포함한 세방그룹 계열사 공통 CI 체계입니다.

---

## 1. 브랜드 아이덴티티 개요

### 1.1 심볼의 의미
세방 CI 심볼은 알파벳 **`E`와 `B`**를 결합한 형태로, **"Extensive Bound"(확장된 경계)** 를 의미합니다.
회사가 지향하는 3가지 핵심 가치를 시각화한 것입니다.

- **변화 (Change)** — 기울어진 형태로 정체되지 않는 역동성을 표현
- **도전 (Challenge)** — 곡선과 직선이 균형을 이루는 구조로 안정감과 추진력을 동시에 표현
- **글로벌 (Globalization)** — 세계로 확장하는 기업 비전을 상징

### 1.2 로고 사용 원칙
- 심볼은 항상 **SEBANG Dark Gray 단색**으로만 사용합니다. (그러데이션, 다색 사용 금지)
- 곡선 타입페이스는 부드러움과 신뢰감을, 기울어진 형태는 속도감과 변화를 표현하므로 **로고 형태를 임의로 각지게 하거나 수직으로 세우는 등 변형하지 않습니다.**
- 최소 여백(clear space): 심볼 높이의 **1/2 이상**을 사방 여백으로 확보합니다.
- 최소 크기: 디지털 화면 기준 높이 **16px** 이하로 축소하지 않습니다. (가독성 저하 방지)
- 어두운 배경 위에서는 화이트 버전(1도 반전)을 사용하고, 컬러 배경 위에는 배치하지 않는 것을 원칙으로 합니다.

### 1.3 그룹 슬로건
> **"Logistics For Better Life"** — 세방그룹이 공식적으로 표방하는 브랜드 철학입니다.
> 개별 프로젝트/서비스의 카피라이팅은 이 철학(신뢰·확장·더 나은 삶에 대한 기여)의 톤앤매너를 벗어나지 않는 선에서 자유롭게 작성합니다.

---

## 2. 컬러 시스템

### 2.1 원색 (Primary Colors) — 무채색 계열
로고, 본문 텍스트, 배경 등 프로젝트의 기본 톤을 구성하는 색입니다.

| 이름 | HEX | RGB | CMYK | PANTONE(C) | 용도 |
|---|---|---|---|---|---|
| SEBANG Dark Gray | `#333F48` | 51, 63, 72 | 35, 0, 0, 90 | 432 C | 로고, 본문 텍스트, 헤드라인, 아이콘 |
| SEBANG Gray | `#A2AAAD` | 162, 170, 173 | 5, 0, 0, 32 | 429 C | 보조 텍스트(대형), 구분선, 비활성 요소 |
| SEBANG Light Gray | `#D0D0CE` | 208, 208, 206 | 0, 0, 0, 10 | Cool Gray 2 C | 배경면, 카드, 테두리 |

### 2.2 강조색 (Point Colors)
> **사용 규칙**: 포인트 컬러는 **동시에 두 색을 함께 사용하지 않으며**, 전체 디자인 면적의 **10% 이내**로 제한합니다. CTA 버튼, 강조 배지, 그래프 하이라이트 등 "시선을 끌 단 하나의 포인트"에만 사용하세요.

| 이름 | HEX | RGB | CMYK | PANTONE(C) | 용도 |
|---|---|---|---|---|---|
| SEBANG Green | `#0097A9` | 0, 151, 169 | 85, 5, 40, 0 | 7711 C | 성장/신뢰/기술 톤의 강조, 링크, 보조 CTA |
| SEBANG Orange | `#EB3300` | 235, 51, 0 | 0, 97, 85, 0 | 2028 C | 주요 CTA, 경고/긴급, 핵심 강조 |

### 2.3 메탈릭 (인쇄물 전용)
| 이름 | PANTONE | 용도 |
|---|---|---|
| Silver | 877 C | 프리미엄 인쇄물, 명함, 사이니지 |
| Gold | 871 C | 수상/기념 인쇄물 등 특별 용도 |

> 메탈릭 컬러는 인쇄(Pantone 별색) 전용이며, 화면(웹/앱) 디자인에는 사용하지 않습니다.

### 2.4 톤 스케일 (디지털 확장 팔레트)
공식 CI 5색(500 단계)을 기준으로 UI 상태(hover, pressed, disabled, 배경 tint 등) 구현을 위해 확장한 팔레트입니다. **500이 아닌 값은 공식 CI 색상이 아닌 디지털 프로젝트용 파생 색상**이며, 인쇄물에는 반드시 원색(2.1~2.2)을 사용하세요.

```
sebang-dark-gray : 50 #EFF0F0  100 #D6D9DA  200 #ADB2B6  300 #858C91  400 #5C656D
                    500 #333F48 (base)
                    600 #2B363D  700 #242C32  800 #1C2328  900 #14191D

sebang-gray      : 50 #F8F8F8  100 #ECEEEF  200 #DADDDE  300 #C7CCCE  400 #B5BBBD
                    500 #A2AAAD (base)
                    600 #8A9093  700 #717779  800 #595E5F  900 #414445

sebang-light-gray: 50 #FBFBFB  100 #F6F6F5  200 #ECECEB  300 #E3E3E2  400 #D9D9D8
                    500 #D0D0CE (base)
                    600 #B1B1AF  700 #929290  800 #727271  900 #535352

sebang-green     : 50 #EBF7F8  100 #CCEAEE  200 #99D5DD  300 #66C1CB  400 #33ACBA
                    500 #0097A9 (base)
                    600 #008090  700 #006A76  800 #00535D  900 #003C44

sebang-orange    : 50 #FDEFEB  100 #FBD6CC  200 #F7AD99  300 #F38566  400 #EF5C33
                    500 #EB3300 (base)
                    600 #C82B00  700 #A42400  800 #811C00  900 #5E1400
```

### 2.5 시맨틱 컬러 매핑 (라이트 모드 기준)
실제 프로덕트에서는 아래처럼 원색을 "역할"에 매핑해 사용합니다.

| 시맨틱 토큰 | 값 | 비고 |
|---|---|---|
| `color-bg-base` | `#FFFFFF` | 기본 배경 |
| `color-bg-surface` | `sebang-light-gray-50` `#FBFBFB` | 카드/패널 배경 |
| `color-border` | `sebang-light-gray-500` `#D0D0CE` | 구분선, 테두리 |
| `color-text-primary` | `sebang-dark-gray-500` `#333F48` | 본문/헤드라인 (대비 10.8:1) |
| `color-text-secondary` | `sebang-gray-700` `#717779` | 보조 텍스트 (대비 4.54:1) |
| `color-text-disabled` | `sebang-gray-400` `#B5BBBD` | 비활성 텍스트 |
| `color-brand-primary` | `sebang-dark-gray-500` `#333F48` | 1차 브랜드 컬러(로고/헤더) |
| `color-accent-primary` | `sebang-orange-500` `#EB3300` | 핵심 CTA (버튼 배경 + 흰 텍스트) |
| `color-accent-secondary` | `sebang-green-700` `#006A76` | 링크/보조 강조 (본문 크기에서도 사용 가능) |
| `color-success` | `sebang-green-600` `#008090` | 성공 상태 |
| `color-danger` | `sebang-orange-700` `#A42400` | 오류/경고 (본문 텍스트로도 사용 가능) |

다크 모드가 필요한 프로젝트는 배경/텍스트를 반전하되(`bg-base`↔`text-primary`), 포인트 컬러(orange/green)의 500 단계는 그대로 유지하고 어두운 배경에서는 400 단계(더 밝은 톤)를 사용해 대비를 확보하세요.

### 2.6 접근성(WCAG) 참고 대비율
> 흰 배경(`#FFFFFF`) 기준. **4.5:1 이상 = 일반 텍스트 통과, 3:1 이상 = 큰 텍스트(18pt+/14pt bold+)·아이콘·UI 컴포넌트 테두리 통과.**

| 색상 | 흰 배경 대비 | 판정 |
|---|---|---|
| Dark Gray `#333F48` | 10.80:1 | ✅ 본문 텍스트 사용 가능 |
| Gray `#A2AAAD` (500) | 2.36:1 | ❌ 텍스트 불가 — 구분선/비활성 용도만 |
| Gray-700 `#717779` | 4.54:1 | ✅ 보조 텍스트 사용 가능 |
| Orange `#EB3300` (500) | 4.19:1 | ⚠️ 큰 텍스트·버튼만 (일반 본문 텍스트로는 부족) |
| Orange-700 `#A42400` | 7.40:1 | ✅ 본문 텍스트로도 사용 가능 |
| Green `#0097A9` (500) | 3.50:1 | ⚠️ 큰 텍스트·아이콘·버튼만 |
| Green-700 `#006A76` | 6.34:1 | ✅ 본문 텍스트로도 사용 가능 |

**규칙**: 포인트 컬러를 작은 본문 텍스트 색상으로 쓸 때는 반드시 700 단계 이상을 사용하고, 버튼 배경처럼 면적이 큰 곳에서는 500 단계 + 흰색 텍스트 조합을 사용하세요.

---

## 3. 타이포그래피

### 3.1 전용 서체
CI 전용 서체는 **Sebang Gothic**(Regular / Bold)이며, "안정감 있는 골격 + 곡선과 직선이 균형을 이루는 스트로크"로 변화·도전·글로벌 가치를 표현합니다. 사내 브랜드/마케팅 공식 자료(명함, 간행물, 프레젠테이션 표지 등)에는 반드시 Sebang Gothic을 사용하세요.

### 3.2 제품/서비스 개발용 대체 서체
Sebang Gothic은 시스템 폰트로 배포되지 않으므로, 웹/앱 등 실제 제품 개발에서는 아래 대체 서체를 사용합니다. (라이선스 무료, 국문/영문 커버리지 우수)

| 용도 | 국문 | 영문/숫자 |
|---|---|---|
| 기본 (Primary) | Pretendard | Inter |
| 대체 (Fallback) | Noto Sans KR | Roboto |
| 시스템 폴백 | `system-ui`, `-apple-system` | `system-ui`, `-apple-system` |

```css
--font-family-base: "Pretendard", "Noto Sans KR", "Inter", system-ui,
  -apple-system, "Segoe UI", Roboto, sans-serif;
```

### 3.3 타입 스케일
8px 그리드에 맞춘 기본 스케일입니다. (rem 기준 1rem = 16px)

| 토큰 | 크기 | line-height | weight | 용도 |
|---|---|---|---|---|
| `text-display` | 2.5rem (40px) | 1.2 | 700 | 페이지 타이틀/히어로 |
| `text-h1` | 2rem (32px) | 1.25 | 700 | 섹션 제목 |
| `text-h2` | 1.5rem (24px) | 1.3 | 700 | 서브 섹션 제목 |
| `text-h3` | 1.25rem (20px) | 1.4 | 600 | 카드/블록 제목 |
| `text-body` | 1rem (16px) | 1.6 | 400 | 본문 |
| `text-body-sm` | 0.875rem (14px) | 1.5 | 400 | 보조 본문 |
| `text-caption` | 0.75rem (12px) | 1.4 | 400 | 캡션/타임스탬프 |
| `text-button` | 0.9375rem (15px) | 1 | 600 | 버튼 라벨 |

---

## 4. 레이아웃 & 간격

### 4.1 간격 스케일 (8px 베이스)
```
space-1: 4px   space-2: 8px   space-3: 12px  space-4: 16px
space-5: 24px  space-6: 32px  space-7: 48px  space-8: 64px
```

### 4.2 모서리 반경 (Border Radius)
```
radius-sm: 4px    /* input, badge, tag */
radius-md: 8px    /* button, card */
radius-lg: 16px   /* modal, large card */
radius-full: 999px /* pill, avatar */
```

### 4.3 그리드
- 웹: 12컬럼 그리드, 최대 폭 1280px, 거터 24px
- 모바일: 4컬럼 그리드, 좌우 마진 16px

---

## 5. 컴포넌트 원칙

- **버튼**: Primary 버튼은 `color-accent-primary`(오렌지) 배경 + 흰색 텍스트. Secondary 버튼은 `color-brand-primary`(Dark Gray) 아웃라인 + Dark Gray 텍스트. 한 화면에 Primary 버튼은 원칙적으로 1개만 배치(포인트 컬러 10% 룰과 동일한 맥락).
- **포커스/강조 상태**: hover는 -100 (한 단계 어둡게), pressed는 -200, disabled는 gray-300 배경 + gray-500 텍스트를 사용합니다.
- **그림자(Elevation)**: 브랜드 톤이 차분한 무채색 계열이므로 그림자도 저채도 다크그레이를 사용합니다. 예) `box-shadow: 0 2px 8px rgba(51,63,72,0.12)`.
- **아이콘**: 선 굵기 1.5–2px, 모서리는 로고와 통일감 있게 살짝 둥글게(rounded join) 처리합니다.
- **모션**: 로고의 "속도감" 컨셉을 반영해 이징은 `cubic-bezier(0.4, 0, 0.2, 1)`(ease-out) 기본, 지속시간은 마이크로 인터랙션 150–200ms, 화면 전환 250–300ms를 권장합니다.
- **데이터 시각화**: 카테고리 색상은 dark-gray → green → orange → gray-400 순으로 배정하고, 포인트 컬러(orange/green)는 강조하고 싶은 계열 1~2개에만 사용합니다.

---

## 6. 디자인 토큰 (개발 적용용)

### 6.1 CSS Custom Properties
```css
:root {
  /* Primary (neutral) */
  --sebang-dark-gray: #333F48;
  --sebang-gray: #A2AAAD;
  --sebang-light-gray: #D0D0CE;

  /* Point colors */
  --sebang-green: #0097A9;
  --sebang-green-700: #006A76;
  --sebang-orange: #EB3300;
  --sebang-orange-700: #A42400;

  /* Semantic */
  --color-bg-base: #FFFFFF;
  --color-bg-surface: #FBFBFB;
  --color-border: var(--sebang-light-gray);
  --color-text-primary: var(--sebang-dark-gray);
  --color-text-secondary: #717779;
  --color-text-disabled: #B5BBBD;
  --color-accent-primary: var(--sebang-orange);
  --color-accent-secondary: var(--sebang-green-700);
  --color-success: #008090;
  --color-danger: var(--sebang-orange-700);

  /* Typography */
  --font-family-base: "Pretendard", "Noto Sans KR", "Inter", system-ui, sans-serif;

  /* Spacing */
  --space-1: 4px; --space-2: 8px; --space-3: 12px; --space-4: 16px;
  --space-5: 24px; --space-6: 32px; --space-7: 48px; --space-8: 64px;

  /* Radius */
  --radius-sm: 4px; --radius-md: 8px; --radius-lg: 16px; --radius-full: 999px;
}
```

### 6.2 JSON 토큰 (Figma Tokens / Style Dictionary 호환)
```json
{
  "color": {
    "sebang": {
      "dark-gray": { "value": "#333F48" },
      "gray": { "value": "#A2AAAD" },
      "light-gray": { "value": "#D0D0CE" },
      "green": { "value": "#0097A9" },
      "green-700": { "value": "#006A76" },
      "orange": { "value": "#EB3300" },
      "orange-700": { "value": "#A42400" }
    },
    "semantic": {
      "bg-base": { "value": "#FFFFFF" },
      "bg-surface": { "value": "#FBFBFB" },
      "border": { "value": "{color.sebang.light-gray}" },
      "text-primary": { "value": "{color.sebang.dark-gray}" },
      "text-secondary": { "value": "#717779" },
      "accent-primary": { "value": "{color.sebang.orange}" },
      "accent-secondary": { "value": "{color.sebang.green-700}" }
    }
  }
}
```

---

## 7. 금지 사항 (Don'ts)

1. 포인트 컬러(오렌지/그린)를 동시에 같은 화면의 주 강조색으로 함께 사용하지 않는다.
2. 로고/심볼에 그림자, 그러데이션, 외곽선(stroke)을 추가하거나 비율을 왜곡하지 않는다.
3. `sebang-gray`(500) 원색을 본문 텍스트 색상으로 사용하지 않는다 (대비 부족).
4. 인쇄물에는 디지털 확장 팔레트(50~900 tint/shade)가 아닌 원색 Pantone 값을 사용한다.
5. 메탈릭(실버/골드)을 화면(웹/앱) UI에 사용하지 않는다.

---

## 8. 출처 및 참고
- [세방그룹 CI / FONT](https://www.sebanggroup.com/client/ko/company/ci)
- [세방 CI 소개](https://www.sebang.com/contents/01_03.asp)
- Pantone 색상 변환 참고: [Pantone 432 C](https://www.crispedge.com/color/333f48/), [Pantone 429 C](https://icolorpalette.com/color/pantone-429-c/), [Pantone Cool Gray 2 C](https://pantonetools.com/color-directory/pantone-cool-gray-2-c), [Pantone 7711 C](https://icolorpalette.com/color/pantone-7711-c), [Pantone 2028 C](https://icolorpalette.com/color//pantone-2028-c)

> 참고: 세방전지 공식 사이트(gbattery.com)의 CI 페이지는 자동 보안 인증(봇 차단)으로 직접 접근이 되지 않아, 동일한 사이트 구조를 사용하는 세방그룹 공식 CI 페이지의 공개된 CI 규정을 기준으로 작성했습니다. 실제 배터리 사업부 전용 서브 브랜드 요소(제품 로고 등)가 별도로 있다면 해당 자료로 이 문서의 컬러/서체 값을 보완해 주세요.
