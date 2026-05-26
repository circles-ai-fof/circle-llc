import { notFound } from "next/navigation";
import { factories, getFactory, listFactorySlugs } from "@/lib/factories";
import LeadForm from "@/components/LeadForm";
import type { Metadata } from "next";

type Params = { slug: string };

export async function generateStaticParams() {
  return listFactorySlugs().map((slug) => ({ slug }));
}

export async function generateMetadata({
  params,
}: {
  params: Promise<Params>;
}): Promise<Metadata> {
  const { slug } = await params;
  const f = getFactory(slug);
  if (!f) return { title: "Fábrica no encontrada — circles-ai.ai" };
  return {
    title: `${f.title} — circles-ai.ai`,
    description: f.subheadline,
    openGraph: {
      title: f.headline,
      description: f.subheadline,
      url: `https://circles-ai.ai/f/${f.slug}`,
      type: "website",
    },
  };
}

export default async function FactoryPage({
  params,
}: {
  params: Promise<Params>;
}) {
  const { slug } = await params;
  const f = getFactory(slug);
  if (!f) notFound();

  return (
    <main
      style={{
        minHeight: "100vh",
        background:
          "radial-gradient(ellipse at top, rgba(0,212,255,0.08), transparent 60%), #0B0F1A",
        color: "#fff",
        paddingBottom: 80,
      }}
    >
      {/* HERO */}
      <section
        style={{
          maxWidth: 920,
          margin: "0 auto",
          padding: "96px 24px 48px",
          textAlign: "center",
        }}
      >
        <div
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 8,
            padding: "6px 14px",
            borderRadius: 999,
            background: "rgba(0,212,255,0.1)",
            border: "1px solid rgba(0,212,255,0.3)",
            color: "#00D4FF",
            fontSize: 12,
            fontWeight: 500,
            marginBottom: 24,
            letterSpacing: 0.5,
          }}
        >
          <span style={{ width: 6, height: 6, borderRadius: 999, background: "#00D4FF" }} />
          {f.status === "active"
            ? "Fábrica en evidencia activa · 14 días"
            : f.status === "iterate"
              ? "En iteración"
              : "Pausada"}
        </div>

        <h1
          style={{
            fontSize: 56,
            fontWeight: 800,
            lineHeight: 1.1,
            letterSpacing: -1,
            marginBottom: 24,
          }}
        >
          {f.headline}
        </h1>

        <p
          style={{
            fontSize: 20,
            color: "#94a3b8",
            lineHeight: 1.5,
            maxWidth: 720,
            margin: "0 auto 36px",
          }}
        >
          {f.subheadline}
        </p>

        <div style={{ maxWidth: 480, margin: "0 auto" }}>
          <LeadForm slug={f.slug} ctaText={f.cta_text} />
        </div>

        <p style={{ color: "#64748b", fontSize: 13, marginTop: 16 }}>
          {f.social_proof}
        </p>
      </section>

      {/* VALUE PROPS */}
      <section style={{ maxWidth: 920, margin: "0 auto", padding: "32px 24px" }}>
        <h2
          style={{
            fontSize: 14,
            color: "#00D4FF",
            letterSpacing: 1.5,
            textAlign: "center",
            marginBottom: 32,
          }}
        >
          QUÉ INCLUYE
        </h2>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
            gap: 16,
          }}
        >
          {f.value_props.map((vp, i) => (
            <div
              key={i}
              style={{
                background: "#0F1525",
                border: "1px solid #1e293b",
                borderRadius: 12,
                padding: 20,
              }}
            >
              <div
                style={{
                  width: 32,
                  height: 32,
                  borderRadius: 8,
                  background: "rgba(0,212,255,0.15)",
                  color: "#00D4FF",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  fontWeight: 700,
                  fontSize: 14,
                  marginBottom: 12,
                }}
              >
                {i + 1}
              </div>
              <p style={{ fontSize: 14, color: "#cbd5e1", lineHeight: 1.5 }}>{vp}</p>
            </div>
          ))}
        </div>
      </section>

      {/* PROBLEM/SOLUTION */}
      <section
        style={{
          maxWidth: 920,
          margin: "0 auto",
          padding: "48px 24px",
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: 20,
        }}
      >
        <div
          style={{
            background: "rgba(255,68,68,0.08)",
            border: "1px solid rgba(255,68,68,0.2)",
            borderRadius: 12,
            padding: 24,
          }}
        >
          <div style={{ color: "#FF4444", fontSize: 12, fontWeight: 600, letterSpacing: 1, marginBottom: 8 }}>
            EL PROBLEMA
          </div>
          <p style={{ color: "#cbd5e1", fontSize: 14, lineHeight: 1.6 }}>
            {f.problem_statement}
          </p>
        </div>
        <div
          style={{
            background: "rgba(0,229,160,0.08)",
            border: "1px solid rgba(0,229,160,0.2)",
            borderRadius: 12,
            padding: 24,
          }}
        >
          <div style={{ color: "#00E5A0", fontSize: 12, fontWeight: 600, letterSpacing: 1, marginBottom: 8 }}>
            LA SOLUCIÓN
          </div>
          <p style={{ color: "#cbd5e1", fontSize: 14, lineHeight: 1.6 }}>
            {f.proposed_solution}
          </p>
        </div>
      </section>

      {/* TARGET */}
      <section style={{ maxWidth: 920, margin: "0 auto", padding: "32px 24px", textAlign: "center" }}>
        <div
          style={{
            display: "inline-block",
            background: "#0F1525",
            border: "1px solid #1e293b",
            borderRadius: 12,
            padding: "20px 32px",
          }}
        >
          <div style={{ color: "#94a3b8", fontSize: 12, letterSpacing: 1, marginBottom: 8 }}>
            ESTO ES PARA
          </div>
          <p style={{ color: "#fff", fontSize: 16, fontWeight: 500 }}>{f.target_market}</p>
        </div>
      </section>

      {/* FINAL CTA */}
      <section style={{ maxWidth: 480, margin: "0 auto", padding: "48px 24px", textAlign: "center" }}>
        <h3 style={{ fontSize: 28, fontWeight: 700, marginBottom: 12 }}>
          ¿Te interesa? Déjanos tu email.
        </h3>
        <p style={{ color: "#94a3b8", fontSize: 14, marginBottom: 24 }}>
          Si suficientes personas como tú dicen "sí" en los próximos 14 días, lo construimos.
          Si no, archivamos la idea y te avisamos. <strong>Sin spam.</strong>
        </p>
        <LeadForm slug={f.slug} ctaText={f.cta_text} variant="bottom" />
      </section>

      <footer
        style={{
          maxWidth: 920,
          margin: "60px auto 0",
          padding: "32px 24px",
          borderTop: "1px solid #1e293b",
          textAlign: "center",
          color: "#64748b",
          fontSize: 12,
        }}
      >
        <a href="/" style={{ color: "#00D4FF", textDecoration: "none" }}>
          circles-ai.ai
        </a>{" "}
        — Fábrica de Fábricas · Validamos ideas con evidencia antes de construir
      </footer>
    </main>
  );
}
