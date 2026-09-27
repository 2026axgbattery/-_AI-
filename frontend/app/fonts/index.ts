import localFont from "next/font/local";
import { Inter } from "next/font/google";

// docs/design.md §3.3 — 국문 Pretendard(로컬 자가호스팅, 외부 CDN 호출 없음) + 영문/숫자 Inter.
export const pretendard = localFont({
  src: "./PretendardVariable.woff2",
  variable: "--font-pretendard",
  display: "swap",
  weight: "45 920",
});

export const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});
