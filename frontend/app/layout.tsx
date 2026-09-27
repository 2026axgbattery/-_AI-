import type { Metadata } from "next";
import "@/lib/theme.css";
import "./components.css";
import { pretendard, inter } from "./fonts";

export const metadata: Metadata = {
  title: "AI 포화도 예측 시스템",
  description: "세방전지 품질경영팀 · 창원공장 — 전지 포화도(Y)·20시간 용량(Z) 예측/진단",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="ko" className={`${pretendard.variable} ${inter.variable}`}>
      <body>{children}</body>
    </html>
  );
}
