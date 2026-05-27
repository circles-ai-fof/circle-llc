import type { Metadata } from "next";
import "./globals.css";
import AuthGuard from "@/components/AuthGuard";
import AuthenticatedShell from "@/components/AuthenticatedShell";

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
      <body className="h-screen overflow-hidden bg-surface text-gray-100">
        <AuthGuard>
          <AuthenticatedShell>{children}</AuthenticatedShell>
        </AuthGuard>
      </body>
    </html>
  );
}
