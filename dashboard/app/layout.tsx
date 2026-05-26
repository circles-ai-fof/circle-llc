import type { Metadata } from "next";
import "./globals.css";
import Sidebar from "@/components/Sidebar";

export const metadata: Metadata = {
  title: "circles-ai.ai — Factory of Factories",
  description: "Dashboard ejecutivo para la plataforma Factory of Factories de circles-ai.ai",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="es">
      <body className="flex h-screen overflow-hidden bg-surface text-gray-100">
        <Sidebar />
        <main className="flex-1 overflow-y-auto bg-surface">
          {children}
        </main>
      </body>
    </html>
  );
}
