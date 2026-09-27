"""실제 현장 raw data(.xls/.xlsx)를 목표 스키마로 변환하는 순수 Python 모듈.

`backend/analysis/`와 같은 원칙: 웹 프레임워크·DB에 의존하지 않는다. 라우터(`backend/routers/upload.py`)만
이 모듈을 호출한다. 근거: `.docs/14_raw-data-업로드-지원-계획.md`.
"""
