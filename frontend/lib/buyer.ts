/** model_name(예: AGM70_H2)의 접미부에서 바이어/스펙 구분 코드를 추출 —
 * `backend/analysis/derive.py`의 `extract_buyer_code_from_model_name`과 동일한 정규식.
 * 바이어는 별도 저장 컬럼이 아니라 model_name에서 그때그때 파생하는 값이다(docs/prd.md §10-19). */
export function extractBuyerCode(modelName: string): string | null {
  const match = /^[A-Za-z]+\d+_([A-Za-z]+)/.exec(modelName);
  return match ? match[1] : null;
}
