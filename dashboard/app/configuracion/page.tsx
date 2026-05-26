export default function ConfiguracionPage() {
  const settings = [
    {
      section: "API Backend",
      items: [
        { key: "API_URL", value: "http://localhost:8000", editable: true, description: "URL del servidor FastAPI" },
        { key: "API_VERSION", value: "v1", editable: false, description: "Versión del API" },
        { key: "TIMEOUT_MS", value: "30000", editable: true, description: "Timeout por request en ms" },
      ],
    },
    {
      section: "EvidenceGateWorkflow",
      items: [
        { key: "MAX_STEPS", value: "5", editable: false, description: "Agentes en el pipeline" },
        { key: "MODEL", value: "claude-sonnet-4-6", editable: false, description: "Modelo Claude activo" },
        { key: "MAX_TOKENS", value: "2048", editable: true, description: "Tokens máximos por agente" },
        { key: "TEMPERATURE", value: "0.3", editable: true, description: "Temperatura del modelo" },
      ],
    },
    {
      section: "Dashboard",
      items: [
        { key: "DEMO_MODE", value: "true", editable: true, description: "Usar datos simulados (sin API real)" },
        { key: "REFRESH_INTERVAL", value: "30s", editable: true, description: "Intervalo de recarga automática" },
        { key: "LOCALE", value: "es-EC", editable: false, description: "Localización" },
      ],
    },
  ];

  return (
    <div className="p-6 space-y-6 max-w-3xl mx-auto">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-white">Configuración</h1>
        <p className="text-sm text-gray-500 mt-0.5">
          Ajustes del dashboard y conexión con el backend
        </p>
      </div>

      {/* Demo mode banner */}
      <div
        className="rounded-xl border px-4 py-3 flex items-center gap-3"
        style={{ backgroundColor: "rgba(255, 184, 0, 0.08)", borderColor: "rgba(255, 184, 0, 0.25)" }}
      >
        <svg className="w-4 h-4 flex-shrink-0" style={{ color: "#FFB800" }} fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
        </svg>
        <span className="text-sm" style={{ color: "#FFB800" }}>
          Modo demo activo — los runs no se envían al backend real. Activa la API en el bloque de configuración.
        </span>
      </div>

      {/* Settings sections */}
      <div className="space-y-5">
        {settings.map((section) => (
          <div
            key={section.section}
            className="rounded-xl border overflow-hidden"
            style={{ backgroundColor: "#111827", borderColor: "#1E2A3A" }}
          >
            <div className="px-4 py-3 border-b" style={{ borderColor: "#1E2A3A" }}>
              <h2 className="text-sm font-semibold text-gray-300">{section.section}</h2>
            </div>
            <div className="divide-y divide-border">
              {section.items.map((item) => (
                <div key={item.key} className="px-4 py-3 flex items-center justify-between gap-4">
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-mono text-gray-300">{item.key}</p>
                    <p className="text-xs text-gray-600 mt-0.5">{item.description}</p>
                  </div>
                  <div className="flex items-center gap-2">
                    {item.editable ? (
                      <span
                        className="font-mono text-xs px-2.5 py-1 rounded border cursor-pointer hover:border-opacity-60 transition-colors"
                        style={{ backgroundColor: "#0B0F1A", borderColor: "#1E2A3A", color: "#00D4FF" }}
                      >
                        {item.value}
                      </span>
                    ) : (
                      <span
                        className="font-mono text-xs px-2.5 py-1 rounded"
                        style={{ backgroundColor: "#0B0F1A", color: "#6B7280" }}
                      >
                        {item.value}
                      </span>
                    )}
                    {item.editable && (
                      <span
                        className="text-xs px-1.5 py-0.5 rounded"
                        style={{ backgroundColor: "rgba(0, 212, 255, 0.1)", color: "#00D4FF" }}
                      >
                        edit
                      </span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>

      {/* Version info */}
      <div className="flex items-center justify-between text-xs text-gray-600">
        <span>circles-ai.ai Dashboard v0.1.0</span>
        <span>EvidenceGateWorkflow · R01–R17</span>
      </div>
    </div>
  );
}
