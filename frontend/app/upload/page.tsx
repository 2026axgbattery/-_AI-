"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { TopBar } from "@/components/TopBar";
import { Dropzone, type DropzoneStatus } from "@/components/Dropzone";
import {
  apiClient,
  ApiError,
  type ManualFieldGroup,
  type UploadBatch,
  type UploadResult,
  type UploadSummary,
} from "@/lib/api-client";

interface FileState {
  status: DropzoneStatus;
  fileName?: string;
  errorMessage?: string;
  warningMessage?: string;
}

const IDLE: FileState = { status: "idle" };

/** 업로드 미리보기(.docs/35) — 파일을 실제로 반영하기 전, 같은 파싱/검증 로직으로 "이렇게
 * 해석했습니다"를 먼저 보여주고 사용자가 확인해야 반영되도록 하기 위한 대기 상태. */
interface PendingPreview {
  file: File;
  result: UploadResult;
}

export default function UploadPage() {
  const [processState, setProcessState] = useState<FileState>(IDLE);
  const [testState, setTestState] = useState<FileState>(IDLE);
  const [summary, setSummary] = useState<UploadSummary | null>(null);

  const [manualStatus, setManualStatus] = useState<{
    total_lots: number;
    incomplete_lot_ids: string[];
    complete_lots: number;
  } | null>(null);
  const [climateGroups, setClimateGroups] = useState<ManualFieldGroup[]>([]);

  const [climateModel, setClimateModel] = useState("");
  const [climateDate, setClimateDate] = useState("");
  const [electrolyteValue, setElectrolyteValue] = useState("");
  const [tankValue, setTankValue] = useState("");
  const [climateOverwrite, setClimateOverwrite] = useState(false);
  const [climateMsg, setClimateMsg] = useState<string | null>(null);
  const [climateLoading, setClimateLoading] = useState(false);

  const [batches, setBatches] = useState<UploadBatch[]>([]);
  const [batchMsg, setBatchMsg] = useState<string | null>(null);
  const [deletingBatchId, setDeletingBatchId] = useState<number | null>(null);
  const [deletingAll, setDeletingAll] = useState(false);

  // 업로드 이력 — 날짜별 그룹핑(매일 지속 업로드해도 한눈에 보이도록). batches는 백엔드에서
  // uploaded_at DESC로 이미 정렬돼 오므로, Map 삽입 순서를 그대로 쓰면 날짜도 최신순으로 유지된다.
  const todayStr = useMemo(() => new Date().toISOString().slice(0, 10), []);
  const batchGroups = useMemo(() => {
    const map = new Map<string, UploadBatch[]>();
    for (const b of batches) {
      const dateKey = b.uploaded_at.slice(0, 10);
      const list = map.get(dateKey);
      if (list) list.push(b);
      else map.set(dateKey, [b]);
    }
    return Array.from(map.entries()).map(([date, items]) => ({
      date,
      items,
      processCount: items
        .filter((i) => i.file_type === "process")
        .reduce((sum, i) => sum + i.remaining_row_count, 0),
      testCount: items
        .filter((i) => i.file_type === "test")
        .reduce((sum, i) => sum + i.remaining_row_count, 0),
    }));
  }, [batches]);

  const refreshSummary = useCallback(async () => {
    try {
      setSummary(await apiClient.getUploadSummary());
    } catch {
      // 초기 진입 시 아직 업로드가 없으면 total_lots=0으로 정상 응답되므로 별도 처리 불필요
    }
  }, []);

  const refreshManualFields = useCallback(async () => {
    try {
      const [status, climate] = await Promise.all([
        apiClient.getManualFieldsStatus(),
        apiClient.getManualFieldGroups("electrolyte_temp"),
      ]);
      setManualStatus(status);
      setClimateGroups(climate);
    } catch {
      // 데이터가 아직 없으면 groups는 빈 배열로 응답됨
    }
  }, []);

  const refreshBatches = useCallback(async () => {
    try {
      setBatches(await apiClient.getUploadBatches());
    } catch {
      // 데이터가 아직 없으면 빈 배열로 응답됨
    }
  }, []);

  useEffect(() => {
    // 최초 진입 시 서버 상태 조회(마운트 시 1회 fetch) — setState는 fetch 완료 후 비동기로
    // 일어나므로 실질적인 문제는 없다. eslint-plugin-react-hooks의 set-state-in-effect 규칙은
    // 이 표준적인 "on mount fetch" 패턴까지 과탐지하므로 이 줄에서만 비활성화한다.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    refreshSummary();
    refreshManualFields();
    refreshBatches();
  }, [refreshSummary, refreshManualFields, refreshBatches]);

  const [processPreview, setProcessPreview] = useState<PendingPreview | null>(null);
  const [testPreview, setTestPreview] = useState<PendingPreview | null>(null);
  const [processConfirming, setProcessConfirming] = useState(false);
  const [testConfirming, setTestConfirming] = useState(false);

  /** 파일을 고르면 바로 반영하지 않고 dry_run=true로 먼저 조회 — 실제 반영과 같은 파싱/검증
   * 로직을 그대로 태우므로 "이렇게 해석했습니다"가 실제 결과와 항상 일치한다(.docs/35). */
  async function handleProcessFile(file: File) {
    setProcessState({ status: "previewing" });
    setProcessPreview(null);
    try {
      const result = await apiClient.uploadProcessCsv(file, { dryRun: true });
      setProcessState(IDLE);
      setProcessPreview({ file, result });
    } catch (err) {
      setProcessState({ status: "error", errorMessage: describeUploadError(err) });
    }
  }

  async function handleTestFile(file: File) {
    setTestState({ status: "previewing" });
    setTestPreview(null);
    try {
      const result = await apiClient.uploadTestCsv(file, { dryRun: true });
      setTestState(IDLE);
      setTestPreview({ file, result });
    } catch (err) {
      setTestState({ status: "error", errorMessage: describeUploadError(err) });
    }
  }

  async function handleConfirmProcessUpload() {
    if (!processPreview) return;
    setProcessConfirming(true);
    setProcessState({ status: "uploading" });
    try {
      const result = await apiClient.uploadProcessCsv(processPreview.file);
      const duplicates = result.duplicate_lot_ids ?? [];
      setProcessState({
        status: "done",
        fileName: processPreview.file.name,
        warningMessage:
          duplicates.length > 0
            ? `${duplicates.length}건은 이미 등록된 lot_id입니다 — 데이터는 append-only로 계속 누적되므로, ` +
              `같은 lot_id를 다시 업로드하면 같은 로트의 공정 데이터가 중복으로 쌓여 분석에 영향을 줄 수 있습니다. ` +
              `같은 파일을 실수로 다시 올린 것은 아닌지 확인하세요. ` +
              `(예: ${duplicates.slice(0, 3).join(", ")}${duplicates.length > 3 ? " 외" : ""})`
            : undefined,
      });
      setProcessPreview(null);
      await Promise.all([refreshSummary(), refreshManualFields(), refreshBatches()]);
    } catch (err) {
      setProcessState({ status: "error", errorMessage: describeUploadError(err) });
    } finally {
      setProcessConfirming(false);
    }
  }

  async function handleConfirmTestUpload() {
    if (!testPreview) return;
    setTestConfirming(true);
    setTestState({ status: "uploading" });
    try {
      const result = await apiClient.uploadTestCsv(testPreview.file);
      const skipped = result.skipped_unknown_lot ?? [];
      setTestState({
        status: "done",
        fileName: testPreview.file.name,
        warningMessage:
          skipped.length > 0
            ? `${skipped.length}건은 일치하는 공정 데이터(lot_id)가 아직 없어 매칭에서 제외됐습니다 — ` +
              `공정 데이터를 먼저 업로드했는지 확인 후 이 시험 파일을 다시 업로드하면 매칭됩니다. ` +
              `(예: ${skipped.slice(0, 3).join(", ")}${skipped.length > 3 ? " 외" : ""})`
            : undefined,
      });
      setTestPreview(null);
      await Promise.all([refreshSummary(), refreshBatches()]);
    } catch (err) {
      setTestState({ status: "error", errorMessage: describeUploadError(err) });
    } finally {
      setTestConfirming(false);
    }
  }

  function handleCancelProcessPreview() {
    setProcessPreview(null);
    setProcessState(IDLE);
  }

  function handleCancelTestPreview() {
    setTestPreview(null);
    setTestState(IDLE);
  }

  async function handleDeleteBatch(batch: UploadBatch) {
    const label = batch.file_type === "process" ? "공정 데이터" : "시험 데이터";
    if (
      !window.confirm(
        `${label} 업로드(${batch.filename}, ${batch.uploaded_at})를 삭제할까요? ` +
          (batch.file_type === "process"
            ? "이 업로드로만 존재하던 로트는 매칭·수기입력·파생값까지 함께 삭제됩니다."
            : "해당 로트들은 다시 미매칭 상태로 돌아갑니다.")
      )
    ) {
      return;
    }
    setBatchMsg(null);
    setDeletingBatchId(batch.batch_id);
    try {
      await apiClient.deleteUploadBatch(batch.batch_id);
      setBatchMsg(`${batch.filename} 삭제 완료.`);
      await Promise.all([refreshSummary(), refreshManualFields(), refreshBatches()]);
    } catch (err) {
      setBatchMsg(describeUploadError(err));
    } finally {
      setDeletingBatchId(null);
    }
  }

  async function handleDeleteAll() {
    if (
      !window.confirm(
        "업로드된 모든 데이터(공정·시험 데이터, 매칭 결과, 수기입력, 파생값)를 전부 삭제합니다. 되돌릴 수 없습니다. 계속할까요?"
      )
    ) {
      return;
    }
    setBatchMsg(null);
    setDeletingAll(true);
    try {
      await apiClient.deleteAllUploadData();
      setBatchMsg("전체 삭제 완료.");
      setProcessState(IDLE);
      setTestState(IDLE);
      await Promise.all([refreshSummary(), refreshManualFields(), refreshBatches()]);
    } catch (err) {
      setBatchMsg(describeUploadError(err));
    } finally {
      setDeletingAll(false);
    }
  }

  const climateModelOptions = useMemo(
    () => Array.from(new Set(climateGroups.map((g) => g.model_name))).sort(),
    [climateGroups]
  );
  const climateDateOptions = climateGroups.filter((g) => g.model_name === climateModel);
  const selectedClimateGroup = climateDateOptions.find((g) => g.prod_date === climateDate);

  async function handleClimateSubmit() {
    if (!climateModel || !climateDate) return;
    if (
      climateOverwrite &&
      !window.confirm(
        `이미 값이 있는 로트까지 포함해 ${selectedClimateGroup?.total ?? 0}건 전체를 덮어씁니다. 계속할까요?`
      )
    ) {
      return;
    }
    let parsedElectrolyte: number | null = null;
    let parsedTank: number | null = null;
    if (electrolyteValue) {
      parsedElectrolyte = parseFloat(electrolyteValue);
      if (Number.isNaN(parsedElectrolyte)) {
        setClimateMsg(`전해액온도 값이 숫자가 아닙니다: "${electrolyteValue}"`);
        return;
      }
    }
    if (tankValue) {
      parsedTank = parseFloat(tankValue);
      if (Number.isNaN(parsedTank)) {
        setClimateMsg(`수조온도 값이 숫자가 아닙니다: "${tankValue}"`);
        return;
      }
    }
    setClimateMsg(null);
    setClimateLoading(true);
    try {
      const group = { model_name: climateModel, prod_date: climateDate };
      const updated: string[] = [];
      if (parsedElectrolyte !== null) {
        const res = await apiClient.batchUpdateManualField(
          "electrolyte_temp",
          group,
          parsedElectrolyte,
          climateOverwrite
        );
        updated.push(...res.updated_lot_ids);
      }
      if (parsedTank !== null) {
        const res = await apiClient.batchUpdateManualField(
          "tank_temp",
          group,
          parsedTank,
          climateOverwrite
        );
        updated.push(...res.updated_lot_ids);
      }
      setClimateMsg(`${new Set(updated).size}건에 반영했습니다.`);
      setElectrolyteValue("");
      setTankValue("");
      await Promise.all([refreshManualFields(), refreshSummary()]);
    } catch (err) {
      setClimateMsg(describeUploadError(err));
    } finally {
      setClimateLoading(false);
    }
  }

  const totalLots = manualStatus?.total_lots ?? 0;
  const incompleteCount = manualStatus?.incomplete_lot_ids.length ?? 0;
  const completeCount = manualStatus?.complete_lots ?? 0;
  const completionRate = totalLots ? ((completeCount / totalLots) * 100).toFixed(1) : "0.0";

  const climateTargetCount = climateOverwrite
    ? (selectedClimateGroup?.total ?? 0)
    : (selectedClimateGroup?.missing ?? 0);

  const step1Done = Boolean(summary && summary.total_lots > 0);
  const step2Done = Boolean(manualStatus && manualStatus.total_lots > 0 && incompleteCount === 0);

  return (
    <>
      <div className="dummy-banner">
        이 화면의 파일명·건수·컬럼은 실제 업로드된 CSV를 기준으로 계산됩니다. 매칭 결과·건수는 업로드마다 다시 계산됩니다.
      </div>

      <div className="app">
        <TopBar active="업로드" />

        <div className="page-head">
          <h1>공정·시험 데이터 업로드</h1>
          <p>
            공정 데이터와 시험 데이터 CSV를 파일 선택 또는 <b>끌어다 놓기(드래그앤드롭)</b>로 업로드하면
            lot_id 기준으로 자동 매칭합니다. 매칭 후 비어있는 수기입력 항목까지 이 화면에서 바로 채울 수
            있습니다. 1단(X→Y) 예측에는 공정 데이터 컬럼만 사용됩니다.
          </p>
        </div>

        <div className="steps">
          <div className={`step ${step1Done ? "done" : "active"}`}>
            <span className="step-num">{step1Done ? "✓" : "1"}</span> 업로드·매칭
          </div>
          <span className="step-sep" />
          <div className={`step ${step2Done ? "done" : step1Done ? "active" : ""}`}>
            <span className="step-num">{step2Done ? "✓" : "2"}</span> 수기입력
          </div>
          <span className="step-sep" />
          <div className={`step ${step2Done ? "active" : ""}`}>
            <span className="step-num">3</span> 1단·2단 분석 실행
          </div>
        </div>

        <div className="grid-2">
          <div className="card">
            <div className="card-head">
              <h3>공정 데이터 (process_data.csv)</h3>
              {processState.status === "done" && <span className="badge badge-ok">업로드 완료</span>}
              {processState.status === "error" && <span className="badge badge-warn">업로드 실패</span>}
            </div>
            <Dropzone
              title="process_data.csv"
              subLabel="lot_id, model_name, electrolyte_temp 등 27컬럼 필요"
              status={processState.status}
              fileName={processState.fileName}
              errorMessage={processState.errorMessage}
              onFileSelected={handleProcessFile}
            />
            {processState.warningMessage && (
              <div className="alert warn" style={{ marginTop: "var(--space-3)", marginBottom: 0 }}>
                <span>⚠️</span>
                <div>{processState.warningMessage}</div>
              </div>
            )}
            {processPreview && (
              <UploadPreviewCard
                lines={[
                  `총 ${processPreview.result.row_count}행 중 신규 로트 ${processPreview.result.inserted_lots ?? 0}건`,
                  `중복 lot_id ${(processPreview.result.duplicate_lot_ids ?? []).length}건`,
                  `형명 인식 실패 등으로 건너뜀 ${(processPreview.result.skipped_invalid_rows ?? []).length}건`,
                ]}
                details={(processPreview.result.skipped_invalid_rows ?? [])
                  .slice(0, 5)
                  .map((r) => `${r.lot_id ?? "(lot_id 없음)"}: ${r.reason}`)}
                confirming={processConfirming}
                onConfirm={handleConfirmProcessUpload}
                onCancel={handleCancelProcessPreview}
              />
            )}
          </div>

          <div className="card">
            <div className="card-head">
              <h3>시험 데이터 (test_data.csv)</h3>
              {testState.status === "done" && <span className="badge badge-ok">업로드 완료</span>}
              {testState.status === "error" && <span className="badge badge-warn">업로드 실패</span>}
            </div>
            <Dropzone
              title="test_data.csv"
              subLabel="lot_id, discharge_amount 등 12컬럼 필요"
              status={testState.status}
              fileName={testState.fileName}
              errorMessage={testState.errorMessage}
              onFileSelected={handleTestFile}
            />
            {testState.warningMessage && (
              <div className="alert warn" style={{ marginTop: "var(--space-3)", marginBottom: 0 }}>
                <span>⚠️</span>
                <div>{testState.warningMessage}</div>
              </div>
            )}
            {testPreview && (
              <UploadPreviewCard
                lines={[
                  `총 ${testPreview.result.row_count}행 중 매칭 반영 ${testPreview.result.inserted_test_rows ?? 0}건`,
                  `일치하는 공정 데이터 없어 제외 ${(testPreview.result.skipped_unknown_lot ?? []).length}건`,
                ]}
                details={(testPreview.result.skipped_unknown_lot ?? []).slice(0, 5)}
                confirming={testConfirming}
                onConfirm={handleConfirmTestUpload}
                onCancel={handleCancelTestPreview}
              />
            )}
          </div>
        </div>

        <div className="alert">
          <span>ℹ️</span>
          <div>
            <b>미매칭 로트는 정상 상태입니다.</b> 시험은 전수가 아닌 샘플로 진행되므로, 공정 데이터에는
            있지만 시험 데이터가 없는 로트가 다수 발생할 수 있습니다.
          </div>
        </div>

        {summary && summary.total_lots > 0 && (
          <>
            <div className="match-summary">
              <div className="match-card ok">
                <div className="label">
                  매칭 성공 <span className="status-chip ok">완료</span>
                </div>
                <div className="value">{summary.matched}건</div>
                <div className="progress-track">
                  <div className="progress-fill" style={{ width: `${summary.match_rate}%` }} />
                </div>
                <div className="note">공정 {summary.total_lots}건 중 시험 결과와 매칭된 로트</div>
              </div>
              <div className="match-card">
                <div className="label">
                  미매칭 (시험 미실시) <span className="status-chip unknown">참고</span>
                </div>
                <div className="value">{summary.unmatched}건</div>
                <div className="note">④ 예측 화면에서 X만으로 Y·Z 일괄 산출 대상으로 이관됩니다</div>
              </div>
              <div className="match-card">
                <div className="label">매칭률</div>
                <div className="value">{summary.match_rate}%</div>
              </div>
            </div>

            <div className="card">
              <div className="card-head">
                <h3>매칭 결과 미리보기</h3>
                <span className="hint">전체 {summary.total_lots}건 중 {summary.preview_rows.length}건 표시</span>
              </div>
              <table>
                <thead>
                  <tr>
                    <th>lot_id</th>
                    <th>모델</th>
                    <th>공정 데이터</th>
                    <th>시험 데이터</th>
                    <th>상태</th>
                  </tr>
                </thead>
                <tbody>
                  {summary.preview_rows.map((row) => (
                    <tr key={row.lot_id}>
                      <td className="cell-lot">{row.lot_id}</td>
                      <td>{row.model_name}</td>
                      <td>{row.has_process ? "✓" : "—"}</td>
                      <td>{row.has_test ? "✓" : "—"}</td>
                      <td>
                        {row.has_test ? (
                          <span className="status-pill matched">
                            <span className="dot" />매칭
                          </span>
                        ) : (
                          <span className="status-pill unmatched">
                            <span className="dot" />미매칭
                          </span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="section-divider">
              <div className="num">2</div>
              <div>
                <h2>수기입력 — 매칭 후 남은 값 채우기</h2>
                <div className="sub">
                  수기입력 대상은 전해액온도·수조온도 2개 항목뿐입니다. CSV에 값이 있으면 자동으로
                  채워지며, 비어있는 로트는 아래 그룹 일괄 입력으로 한 번에 채웁니다. (충전량은
                  형명·바이어별 충전 STEP 기준표 업로드로 대체됨 — 상세분석 화면 참조)
                </div>
              </div>
            </div>

            <div className="summary-row">
              <div className="sum-card ok">
                <div className="label">
                  입력 완료 <span className="status-chip ok">완료</span>
                </div>
                <div className="value">{completeCount}건</div>
              </div>
              <div className={`sum-card ${incompleteCount > 0 ? "warn" : "ok"}`}>
                <div className="label">
                  직접 입력 필요{" "}
                  <span className={`status-chip ${incompleteCount > 0 ? "warn" : "ok"}`}>
                    {incompleteCount > 0 ? "확인 필요" : "완료"}
                  </span>
                </div>
                <div className="value">{incompleteCount}건</div>
              </div>
              <div className="sum-card">
                <div className="label">1단(X→Y) 분석 대상 확정</div>
                <div className="value">{completeCount}건</div>
              </div>
              <div className="sum-card">
                <div className="label">입력 완료율</div>
                <div className="value">{completionRate}%</div>
              </div>
            </div>

            {incompleteCount > 0 && (
              <div className="alert warn">
                <span>⚠️</span>
                <div>
                  <b>미입력 항목이 남아있는 로트 {incompleteCount}건</b>은 1단(X→Y) 분석 대상에서 자동
                  제외됩니다. 아래 그룹 일괄 입력으로 값을 채우면 즉시 대상에 포함됩니다.
                </div>
              </div>
            )}

            <div className="card">
              <div className="card-head">
                <h3>그룹 일괄 입력</h3>
                <span className="hint">
                  같은 그룹의 로트는 화성 레시피·수조 운용을 공유한다는 전제로 값 하나를 그룹 전체에 한
                  번에 반영합니다
                </span>
              </div>
              <div className="group-panel-grid">
                <div className="group-panel">
                  <div className="gp-title">
                    전해액온도·수조온도(℃) <span className="gp-key">형명 + 생산일자 단위</span>
                  </div>
                  <p className="gp-desc">
                    같은 형명이 같은 날 같은 수조에 함께 투입되어 충전되므로, <code>model_name</code> +{" "}
                    <code>prod_date</code> 조합으로 그룹화합니다.
                  </p>
                  <div className="gp-row">
                    <label>형명 선택</label>
                    <select
                      value={climateModel}
                      onChange={(e) => {
                        setClimateModel(e.target.value);
                        setClimateDate("");
                      }}
                    >
                      <option value="">형명을 선택하세요</option>
                      {climateModelOptions.map((m) => (
                        <option key={m} value={m}>
                          {m}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div className="gp-row">
                    <label>생산일자 선택</label>
                    <select
                      value={climateDate}
                      onChange={(e) => setClimateDate(e.target.value)}
                      disabled={!climateModel}
                    >
                      <option value="">생산일자를 선택하세요</option>
                      {climateDateOptions.map((g) => (
                        <option key={g.prod_date} value={g.prod_date}>
                          {g.prod_date} (전체 {g.total}건 · 미입력 {g.missing}건)
                        </option>
                      ))}
                    </select>
                  </div>
                  {selectedClimateGroup && (
                    <div className="gp-preview">
                      이 형명·날짜(<b>{climateModel} · {climateDate}</b>)의 로트{" "}
                      <b>{selectedClimateGroup.total}건</b> 중 미입력{" "}
                      <span className="pending">{selectedClimateGroup.missing}건</span>
                    </div>
                  )}
                  <div className="gp-value-row">
                    <div className="gp-row">
                      <label>전해액온도(℃)</label>
                      <input
                        type="text"
                        placeholder="예: 31.2"
                        value={electrolyteValue}
                        onChange={(e) => setElectrolyteValue(e.target.value)}
                      />
                    </div>
                    <div className="gp-row">
                      <label>수조온도(℃)</label>
                      <input
                        type="text"
                        placeholder="예: 27.6"
                        value={tankValue}
                        onChange={(e) => setTankValue(e.target.value)}
                      />
                    </div>
                  </div>
                  <div className="gp-row" style={{ flexDirection: "row", alignItems: "center", gap: "6px" }}>
                    <input
                      type="checkbox"
                      id="climate-overwrite"
                      checked={climateOverwrite}
                      onChange={(e) => setClimateOverwrite(e.target.checked)}
                    />
                    <label htmlFor="climate-overwrite" style={{ marginBottom: 0 }}>
                      이미 값이 있는 로트도 덮어쓰기
                    </label>
                  </div>
                  <div className="gp-actions">
                    <button
                      className="btn btn-primary btn-sm"
                      disabled={
                        !climateModel ||
                        !climateDate ||
                        (!electrolyteValue && !tankValue) ||
                        climateTargetCount === 0 ||
                        climateLoading
                      }
                      onClick={handleClimateSubmit}
                    >
                      {climateLoading
                        ? "반영 중..."
                        : `${climateOverwrite ? "전체" : "미입력"} ${climateTargetCount}건에 일괄 반영`}
                    </button>
                  </div>
                  {climateMsg && <div className="gp-preview">{climateMsg}</div>}
                </div>
              </div>
            </div>

            <div className="action-bar">
              <button className="btn btn-secondary" onClick={() => window.location.reload()}>
                다시 업로드
              </button>
              <a
                className="btn btn-primary"
                href="/dashboard"
                title="분석 대시보드로 이동해 1단·2단 회귀를 실행합니다"
              >
                1단·2단 분석 실행 ({completeCount}건)
              </a>
            </div>
          </>
        )}

        <div className="card">
          <div className="card-head">
            <h3>업로드 이력</h3>
            <span className="hint">지금까지 업로드한 파일을 확인하고, 선택 삭제하거나 전체 삭제할 수 있습니다</span>
          </div>
          {batchGroups.length === 0 ? (
            <div style={{ fontSize: "0.8125rem", color: "var(--color-text-secondary)" }}>
              업로드된 파일이 없습니다.
            </div>
          ) : (
            batchGroups.map((g) => (
              <details key={g.date} className="upload-day-group" open={g.date === todayStr}>
                <summary className="upload-day-summary">
                  <span className="upload-day-date">
                    {g.date}
                    {g.date === todayStr && <span className="today-tag">오늘</span>}
                  </span>
                  <span className="upload-day-counts">
                    공정 {g.processCount}건 · 시험 {g.testCount}건 · 파일 {g.items.length}개
                  </span>
                </summary>
                <table>
                  <thead>
                    <tr>
                      <th>종류</th>
                      <th>파일명</th>
                      <th>건수</th>
                      <th>업로드 시각</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {g.items.map((b) => (
                      <tr key={b.batch_id}>
                        <td>{b.file_type === "process" ? "공정 데이터" : "시험 데이터"}</td>
                        <td>{b.filename}</td>
                        <td>
                          {b.remaining_row_count}건
                          {b.remaining_row_count !== b.row_count && ` (업로드 당시 ${b.row_count}건)`}
                        </td>
                        <td>{b.uploaded_at.slice(11)}</td>
                        <td>
                          <button
                            className="btn btn-secondary btn-sm"
                            disabled={deletingBatchId !== null || deletingAll}
                            onClick={() => handleDeleteBatch(b)}
                          >
                            {deletingBatchId === b.batch_id ? "삭제 중..." : "삭제"}
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </details>
            ))
          )}
          {batchMsg && <div className="gp-preview" style={{ marginTop: "var(--space-3)" }}>{batchMsg}</div>}
          <div className="action-bar" style={{ marginTop: "var(--space-4)", paddingTop: 0, borderTop: "none" }}>
            <button
              className="btn btn-secondary"
              disabled={batches.length === 0 || deletingBatchId !== null || deletingAll}
              onClick={handleDeleteAll}
            >
              {deletingAll ? "삭제 중..." : "전체 삭제"}
            </button>
          </div>
        </div>

        <div className="foot-note">
          전 구간 로컬 처리, 외부 전송 없음. 형명 접미 문자를 &quot;바이어 코드&quot;로 간주하는 가정은
          담당자 확인 전까지 잠정 설계입니다(<code>docs/prd.md</code> §10-19).
        </div>
      </div>
    </>
  );
}

/** 업로드 미리보기 확인 카드(.docs/35) — dry_run=true로 받아온 요약을 보여주고, 사용자가
 * "반영하기"를 눌러야 실제 커밋이 일어난다. 공정/시험 데이터 두 Dropzone이 요약 문구·상세
 * 목록만 다르고 카드 구조·버튼은 동일해 하나로 공유한다. */
function UploadPreviewCard({
  lines,
  details,
  confirming,
  onConfirm,
  onCancel,
}: {
  lines: string[];
  details: string[];
  confirming: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <div
      className="alert"
      style={{ marginTop: "var(--space-3)", marginBottom: 0, flexDirection: "column", alignItems: "stretch" }}
    >
      <div style={{ display: "flex", gap: "var(--space-3)" }}>
        <span>📋</span>
        <div>
          <b>미리보기 — 아직 저장되지 않았습니다.</b>
          <ul style={{ margin: "var(--space-2) 0 0", paddingLeft: "1.2em" }}>
            {lines.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
          {details.length > 0 && (
            <div style={{ marginTop: "var(--space-2)", color: "var(--color-text-secondary)" }}>
              예: {details.join(" · ")}
            </div>
          )}
        </div>
      </div>
      <div style={{ display: "flex", gap: "var(--space-2)", marginTop: "var(--space-3)", justifyContent: "flex-end" }}>
        <button className="btn btn-secondary btn-sm" onClick={onCancel} disabled={confirming}>
          취소
        </button>
        <button className="btn btn-primary btn-sm" onClick={onConfirm} disabled={confirming}>
          {confirming ? "반영 중..." : "반영하기"}
        </button>
      </div>
    </div>
  );
}

function describeUploadError(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.detail && typeof err.detail === "object" && "missing_columns" in (err.detail as object)) {
      const cols = (err.detail as { missing_columns: string[] }).missing_columns;
      return `누락된 컬럼: ${cols.join(", ")}`;
    }
    return typeof err.detail === "string" ? err.detail : JSON.stringify(err.detail);
  }
  if (err instanceof Error) {
    if (err.message === "Failed to fetch") {
      return "백엔드 서버에 연결할 수 없습니다 — 서버가 켜져 있는지 확인 후 다시 시도해 주세요.";
    }
    return err.message;
  }
  return "알 수 없는 오류가 발생했습니다";
}
