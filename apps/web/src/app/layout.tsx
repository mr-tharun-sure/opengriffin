import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import "./globals.css";

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
  display: "swap",
});

const jetbrainsMono = JetBrains_Mono({
  variable: "--font-jetbrains-mono",
  subsets: ["latin"],
  display: "swap",
});

export const metadata: Metadata = {
  metadataBase: new URL("https://opengriffin.com"),
  title: "OpenGriffin — Self-evolving personal AI agent. OSS. Free forever.",
  description:
    "The personal AI agent that runs on your machine, remembers everything, schedules its own work, and gets smarter while you sleep. 21 AI providers, BYO key, Apache 2.0.",
  openGraph: {
    title: "OpenGriffin — Self-evolving personal agent",
    description:
      "OSS Telegram-first agent. 30 features. 21 providers BYO-key. Persistent memory, daily journal, skill hub, worker pool, dream cycle. Free forever.",
    url: "https://opengriffin.com",
    siteName: "OpenGriffin",
    type: "website",
    images: [
      {
        url: "/og.png",
        width: 1200,
        height: 630,
        alt: "OpenGriffin — the Claude-native personal agent that learns while you sleep",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: "OpenGriffin — Self-evolving personal agent",
    description:
      "OSS Telegram-first agent. 21 providers BYO-key. Persistent memory, daily journal, skill hub. Free forever.",
    images: ["/og.png"],
  },
};

// Runs before first paint to set the theme class — avoids a flash of the
// wrong theme. Defaults to light; honors a saved choice, else the OS setting.
const themeScript = `(function(){try{var t=localStorage.getItem('theme');if(!t){t=window.matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light';}if(t==='dark'){document.documentElement.classList.add('dark');}}catch(e){}})();`;

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${inter.variable} ${jetbrainsMono.variable} h-full antialiased`}
      suppressHydrationWarning
    >
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
