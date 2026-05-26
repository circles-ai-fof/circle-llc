import type { Metadata } from "next";
import "./globals.css";
import Navbar from "@/components/Navbar";
import Footer from "@/components/Footer";

export const metadata: Metadata = {
  title: "circles-ai.ai — Factory of Factories",
  description:
    "Valida tu idea de negocio en 14 días con IA antes de construir",
  keywords: ["startup", "validación", "IA", "idea de negocio", "LATAM", "evidencia"],
  openGraph: {
    title: "circles-ai.ai — Factory of Factories",
    description:
      "Valida tu idea de negocio en 14 días con IA antes de construir",
    type: "website",
    url: "https://circles-ai.ai",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="es">
      <body className="bg-bg text-text-primary antialiased">
        <Navbar />
        <main>{children}</main>
        <Footer />
      </body>
    </html>
  );
}
