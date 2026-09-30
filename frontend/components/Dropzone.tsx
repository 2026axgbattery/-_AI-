"use client";

import { useRef, useState } from "react";

export type DropzoneStatus = "idle" | "previewing" | "uploading" | "done" | "error";

export interface DropzoneProps {
  title: string; // 표시용 라벨(예: "process_data.csv")
  subLabel: string; // 예: "100행 · 27컬럼"
  status: DropzoneStatus;
  fileName?: string;
  errorMessage?: string;
  onFileSelected: (file: File) => void;
}

// output/01_upload_matching.html의 .dropzone 마크업 + 드래그앤드롭 JS를 React로 이식
// (.docs/07_디자인-수정-이력.md (4) 근거).
export function Dropzone({ title, subLabel, status, fileName, errorMessage, onFileSelected }: DropzoneProps) {
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const filled = status === "done";
  const classNames = ["dropzone", filled ? "filled" : "", dragOver ? "dragover" : ""]
    .filter(Boolean)
    .join(" ");

  function handleFiles(files: FileList | null) {
    const file = files?.[0];
    if (file) onFileSelected(file);
  }

  return (
    <div
      className={classNames}
      onDragEnter={(e) => {
        e.preventDefault();
        setDragOver(true);
      }}
      onDragOver={(e) => {
        e.preventDefault();
        setDragOver(true);
      }}
      onDragLeave={(e) => {
        e.preventDefault();
        setDragOver(false);
      }}
      onDrop={(e) => {
        e.preventDefault();
        setDragOver(false);
        handleFiles(e.dataTransfer.files);
      }}
    >
      <input
        ref={inputRef}
        type="file"
        accept=".csv,.xls,.xlsx"
        hidden
        onChange={(e) => handleFiles(e.target.files)}
      />
      <div className="dz-icon">
        {filled ? "✓" : status === "previewing" || status === "uploading" ? "…" : "＋"}
      </div>
      <div className="dz-title">{fileName ?? title}</div>
      <div className="dz-sub">
        {status === "previewing" && "파일 확인 중... (아직 저장되지 않았습니다)"}
        {status === "uploading" && "반영 중..."}
        {status === "idle" && subLabel}
        {status === "done" && subLabel}
        {status === "error" && (errorMessage ?? "업로드 실패")}
      </div>
      <div className="dz-replace">
        <label onClick={() => inputRef.current?.click()}>
          {filled ? "다른 파일 선택" : "파일 선택"}
        </label>{" "}
        또는 이 영역에 파일을 끌어다 놓아 {filled ? "교체" : "업로드"}
      </div>
    </div>
  );
}
