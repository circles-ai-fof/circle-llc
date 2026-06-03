// Generate docs/organigrama.docx — Organigrama de Agentes Circle LLC FoF
// Run: node docs/generate_organigrama_docx.js
const fs = require('fs');
const path = require('path');
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  Header, Footer, AlignmentType, LevelFormat, HeadingLevel,
  BorderStyle, WidthType, ShadingType, PageNumber, PageBreak,
} = require('docx');

// ---------- helpers ----------
const COLORS = {
  bg:       'F8F9FB',
  text:     '0F172A',
  accent:   '1E40AF',
  workflow: 'D4ECFF', // azul claro
  defense:  'FFE0E0', // rojo claro
  hunter:   'FFF4CC', // amarillo claro
  analysis: 'D9F2E1', // verde claro
  orch:     'EDE0FF', // morado claro
  llm:      'E6F0FF',
  headerRow:'1E40AF',
  zebra:    'F1F5F9',
};

const border = { style: BorderStyle.SINGLE, size: 4, color: 'CBD5E1' };
const borders = { top: border, bottom: border, left: border, right: border,
                  insideHorizontal: border, insideVertical: border };

const P = (text, opts = {}) => new Paragraph({
  spacing: { before: 60, after: 60 },
  alignment: opts.align || AlignmentType.LEFT,
  children: [ new TextRun({ text, bold: !!opts.bold, italics: !!opts.italics,
                            size: opts.size || 20, color: opts.color || COLORS.text }) ],
});

const H1 = (text) => new Paragraph({
  heading: HeadingLevel.HEADING_1,
  spacing: { before: 240, after: 120 },
  children: [ new TextRun({ text, bold: true, size: 36, color: COLORS.accent }) ],
});

const H2 = (text, color) => new Paragraph({
  heading: HeadingLevel.HEADING_2,
  spacing: { before: 200, after: 100 },
  children: [ new TextRun({ text, bold: true, size: 28, color: color || COLORS.accent }) ],
});

const H3 = (text) => new Paragraph({
  heading: HeadingLevel.HEADING_3,
  spacing: { before: 160, after: 80 },
  children: [ new TextRun({ text, bold: true, size: 24, color: COLORS.text }) ],
});

const cell = (text, opts = {}) => new TableCell({
  borders,
  width: { size: opts.w, type: WidthType.DXA },
  shading: { fill: opts.fill || 'FFFFFF', type: ShadingType.CLEAR },
  margins: { top: 100, bottom: 100, left: 140, right: 140 },
  children: [ new Paragraph({
    children: [ new TextRun({ text, bold: !!opts.bold, size: opts.size || 18,
                              color: opts.color || COLORS.text }) ],
  })],
});

const headerCell = (text, w) => cell(text, { w, fill: COLORS.headerRow, color: 'FFFFFF', bold: true, size: 20 });

// ---------- agent tables ----------
const CONTENT_W = 9360; // letter 8.5x11 with 1" margins

// Workflow agents (7)
const workflowAgents = [
  ['idea_hunter',       'Step 1',  'Claude Sonnet 4.6', 'Genera IdeaSpec desde topic/trend'],
  ['idea_enricher',     'Step 1.5','Sonnet + Gemini',   'Sharpens vagueness + fact-check'],
  ['idea_maturer',      'Step 2',  'Claude Sonnet 4.6', 'ICP + value prop + riesgos'],
  ['market_validator',  'Step 3',  'Claude Sonnet 4.6', 'Disena test de mercado (landing+ads)'],
  ['landing_generator', 'Step 4a', 'Claude Haiku 4.5',  'Copy de landing (hero, CTA, copy)'],
  ['gate_decider',      'Step 4b', 'Ensemble 4-LLM',    'PASS/KILL/ITERATE final verdict'],
  ['source_scanner',    'Continuo','Claude Haiku 4.5',  'Destila signals de fuentes externas'],
];

// Defenses (3)
const defenses = [
  ['IdeaValidator (M11.3 + M11.4)', 'Step 2.5 pre-test',  'Claude Opus 4.5', 'Red-team killer pre-ads'],
  ['adversarial_callback (M11.1)',  'Post-gate borderline','xAI Grok 3-mini', 'Devil advocate selective'],
  ['CardValidator (M11.0)',         'Imagen de marketplace','Claude vision',  'Filtra mockups / fakes'],
];

// Cazador autonomo (4)
const hunters = [
  ['SourceDiscoveryAgent (M9.4)', 'Diario',  'Gemini Flash',     'Propone fuentes nuevas via search'],
  ['LinkFollowerAgent (M10.0)',   'Por signal','Heuristicos+RSS', 'Mina evidence_urls -> RSS escondidos'],
  ['executive-status (M15.0)',    'Diario 08UTC','Claude Sonnet 4.6','Briefing ejecutivo para CEO'],
  ['source_scanner queue',        'Cada 6h', 'Haiku 4.5',        'Smart queue auto-prioriza fuentes'],
];

// Analisis on-demand (8)
const analysis = [
  ['TrendGapAnalyzer (M5.0)',         'Claude Sonnet 4.6', 'First-mover gaps cross-country'],
  ['NicheScout (M5.2)',               'Claude Sonnet 4.6', 'Plan de entrada al sub-niche'],
  ['EventScorer (M5.3)',              'Claude Haiku 4.5',  'Ir o no a la feria / evento'],
  ['SleeperDetector (M5.4)',          'Claude Sonnet 4.6', 'Ideas dormidas que despiertan'],
  ['MultiAgentConsensus (M6.0)',      'Ensemble 4-LLM',    'Voting cross-agente'],
  ['ProductArbitrageEvaluator',       'Claude Haiku 4.5',  'Arbitrage cross-marketplace'],
  ['LinkAnalyzer',                    'Claude Haiku 4.5',  'Analisis de paginas/links externos'],
  ['IdeaAnalyzer',                    'Claude Sonnet 4.6', 'Deep-dive on-demand de una idea'],
];

const COL_W4 = [2600, 1900, 2300, 2560]; // workflow / defenses / hunters: 4 cols
const COL_W3 = [3400, 2300, 3660];        // analysis: 3 cols

function tableSection(rows, cols, headerLabels, palette) {
  const colWs = cols;
  const headerRow = new TableRow({ tableHeader: true, children:
    headerLabels.map((t, i) => headerCell(t, colWs[i])) });

  const dataRows = rows.map((r, idx) => new TableRow({ children: r.map((txt, i) =>
    cell(txt, { w: colWs[i], fill: idx % 2 ? COLORS.zebra : palette }))
  }));

  return new Table({
    width: { size: CONTENT_W, type: WidthType.DXA },
    columnWidths: colWs,
    rows: [headerRow, ...dataRows],
  });
}

// LLM providers
const llmRows = [
  ['Anthropic Claude', 'Sonnet 4.6 / Haiku 4.5 / Opus 4.5', 'Workflow body + IdeaValidator + ejecutivos'],
  ['OpenAI',           'GPT-4o-mini',                        'Voz #2 del ensemble (gate_decider)'],
  ['Google',           'Gemini Flash',                       'Search + fact-check + SourceDiscovery'],
  ['xAI Grok',         'Grok 3-mini',                        'Voz #4 + adversarial callback'],
];

// ---------- document ----------
const children = [

  // Cover
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 2400, after: 240 },
    children: [ new TextRun({ text: 'Circle LLC — Factory of Factories',
                              bold: true, size: 44, color: COLORS.accent }) ]}),
  new Paragraph({ alignment: AlignmentType.CENTER,
    children: [ new TextRun({ text: 'Organigrama de Agentes & Orquestador',
                              bold: true, size: 36, color: COLORS.text }) ]}),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 240 },
    children: [ new TextRun({ text: '20 agentes activos · 4 LLM providers · 29 ADRs',
                              italics: true, size: 24, color: '475569' }) ]}),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 120 },
    children: [ new TextRun({ text: 'Documento generado: 2026-06-03 · dominio: circles-ai.ai',
                              italics: true, size: 20, color: '64748B' }) ]}),
  new Paragraph({ children: [ new PageBreak() ] }),

  // ============ 1. Orquestador ============
  H1('1. Orquestador (chassis)'),
  P('El orquestador NO es un Governor dinamico (ADR-029). Es un workflow LINEAR de 4 pasos con 7 agentes encadenados deterministicamente. La unica ramificacion permitida es selectiva, hard-coded y one-shot (ADR-028).', { size: 22 }),

  H3('Componentes del chassis'),
  tableSection([
    ['EvidenceGateWorkflow', 'orchestrator/workflows/evidence_gate.py', 'LINEAR — Step 1 -> 1.5 -> 2 -> 2.5 -> 3 -> 4a -> 4b'],
    ['BaseAgent',            'orchestrator/core/base_agent.py',          'Prompt caching + mock_mode + schema validation'],
    ['MultiLLMDispatcher',   'orchestrator/core/multi_llm.py',           'Ensemble Claude+GPT+Gemini+Grok (gate_decider)'],
    ['SignalsStore',         'orchestrator/core/storage.py',             'SQLite + auto-tune + persistent volume'],
    ['SecurityValidator',    'orchestrator/core/security_validator.py',  '13 heuristicos antes de scrape'],
    ['PromptInjectionScanner','orchestrator/core/prompt_injection.py',   '27 patrones x 4 severidades EN+ES'],
  ], COL_W3, ['Componente', 'Path', 'Funcion'], COLORS.orch),

  new Paragraph({ children: [new PageBreak()] }),

  // ============ 2. Workflow ============
  H1('2. Capa Workflow — 7 agentes lineales'),
  P('Cada paso del EvidenceGateWorkflow tiene un agente unico con scope exclusivo (ver SCOPES.md). El verdict final es ensemble 4-LLM con regla 2-2 tie -> ITERATE forzado (M9.0).', { size: 22 }),
  tableSection(workflowAgents, COL_W4,
    ['Agente', 'Posicion', 'LLM', 'Funcion'], COLORS.workflow),

  // ============ 3. Defensas ============
  H2('3. Defensas + filtros (3 agentes)', 'B91C1C'),
  P('Cortocircuitos selectivos del workflow. Ningun agente de defensa puede modificar el body lineal — solo emitir verdicts MATAR / DEGRADAR / REVISAR.', { size: 22 }),
  tableSection(defenses, COL_W4,
    ['Agente', 'Cuando dispara', 'LLM', 'Funcion'], COLORS.defense),

  new Paragraph({ children: [new PageBreak()] }),

  // ============ 4. Cazador autonomo ============
  H1('4. Cazador autonomo (4 agentes)'),
  P('Capa que opera fuera del workflow principal. Hace crecer el grafo de fuentes y senales sin intervencion manual.', { size: 22 }),
  tableSection(hunters, COL_W4,
    ['Agente', 'Cadencia', 'LLM', 'Funcion'], COLORS.hunter),

  // ============ 5. Analisis on-demand ============
  H2('5. Analisis on-demand (8 agentes)', '047857'),
  P('Agentes que se invocan desde el dashboard cuando el operador o el cron nightly los pide. Auto-tune activo (M14.0) para que las paginas Migajas/Oportunidades nunca queden vacias.', { size: 22 }),
  tableSection(analysis, COL_W3,
    ['Agente', 'LLM', 'Funcion'], COLORS.analysis),

  new Paragraph({ children: [new PageBreak()] }),

  // ============ 6. LLM providers ============
  H1('6. LLM providers — quien hace que'),
  P('El orquestador trabaja con 4 proveedores en paralelo. Provider order del ensemble: Claude -> OpenAI -> Gemini -> Grok. Cada uno opcional; el sistema degrada gracefully si falta una key.', { size: 22 }),
  tableSection(llmRows, COL_W3,
    ['Proveedor', 'Modelo', 'Rol en el sistema'], COLORS.llm),

  // ============ 7. Reglas / Anti-patterns ============
  H1('7. Reglas operativas y anti-patterns'),
  H3('Reglas R01-R29 (resumen)'),
  ...[
    'R06 — mock_mode=True obligatorio en CI',
    'R07 — Schema validation Pydantic en outputs de agentes',
    'R08 — Prompt caching activo en todos los system prompts',
    'R10 — outcome_insights writable=False hasta N>=3 fabricas',
    'R12 — minimo 30 golden cases antes de activar un agente nuevo',
    'R28 — source_scanner destila signals (no decide PASS/KILL)',
    'R29 — Nunca construir sin landing+ads validados (evidence-gate)',
  ].map(t => P('  ' + t, { size: 20 })),

  H3('Anti-patterns prohibidos'),
  ...[
    'NO crear un Governor que decida dinamicamente que agente llamar (ADR-029)',
    'NO anadir agentes de _deferred/ sin ADR aprobado',
    'NO bypassear security_validator.validate_url() en ingestion',
    'NO pasar contenido scraped a un LLM sin prompt_injection.scan_for_injection()',
    'NO multi-tenant en SQLite — diferir a Postgres+RLS en M17+',
  ].map(t => P('  ' + t, { size: 20, color: 'B91C1C' })),

  new Paragraph({ children: [new PageBreak()] }),

  // ============ Summary ============
  H1('Resumen ejecutivo'),
  tableSection([
    ['Agentes activos',     '20'],
    ['LLM providers',       '4 (Anthropic + OpenAI + Google + xAI)'],
    ['ADRs formalizados',   '29'],
    ['Reglas R01-R29',      '29'],
    ['Source kinds activos','15'],
    ['Tests verdes',        '1078'],
    ['Crons GitHub',        '5 (auto-scan, auto-analyze, db-backup, executive-briefing, weekly-digest)'],
    ['Backend live',        'Railway con persistent volume'],
    ['Dashboard live',      'dashboard.circles-ai.ai con SSL'],
    ['Outcome DB',          'INACTIVA (M17+ cuando N>=3 fabricas)'],
  ], [3600, 5760], ['Indicador', 'Valor'], COLORS.workflow),

  P('Refactor guiado por revision Aishwarya Naresh Reganti (LevelUp Labs). Filosofia: stay at the simplest level that handles 90% of your cases.',
    { italics: true, size: 20 }),
];

const doc = new Document({
  creator: 'Circle LLC',
  title: 'Organigrama de Agentes — FoF',
  description: 'Catalogo organizacional de los 20 agentes y 4 LLM providers del orquestador',
  styles: {
    default: { document: { run: { font: 'Calibri', size: 22 } } },
    paragraphStyles: [
      { id: 'Heading1', name: 'Heading 1', basedOn: 'Normal', next: 'Normal', quickFormat: true,
        run: { size: 36, bold: true, font: 'Calibri', color: COLORS.accent },
        paragraph: { spacing: { before: 280, after: 140 }, outlineLevel: 0 } },
      { id: 'Heading2', name: 'Heading 2', basedOn: 'Normal', next: 'Normal', quickFormat: true,
        run: { size: 28, bold: true, font: 'Calibri', color: COLORS.accent },
        paragraph: { spacing: { before: 200, after: 100 }, outlineLevel: 1 } },
      { id: 'Heading3', name: 'Heading 3', basedOn: 'Normal', next: 'Normal', quickFormat: true,
        run: { size: 24, bold: true, font: 'Calibri', color: COLORS.text },
        paragraph: { spacing: { before: 160, after: 80 }, outlineLevel: 2 } },
    ],
  },
  sections: [{
    properties: {
      page: {
        size: { width: 12240, height: 15840 }, // US Letter
        margin: { top: 1080, right: 1440, bottom: 1080, left: 1440 },
      },
    },
    headers: {
      default: new Header({ children: [ new Paragraph({
        alignment: AlignmentType.RIGHT,
        children: [ new TextRun({ text: 'Circle LLC · Factory of Factories · Organigrama',
                                  italics: true, size: 18, color: '64748B' }) ],
      })]}),
    },
    footers: {
      default: new Footer({ children: [ new Paragraph({
        alignment: AlignmentType.CENTER,
        children: [
          new TextRun({ text: 'Pagina ', size: 18, color: '64748B' }),
          new TextRun({ children: [PageNumber.CURRENT], size: 18, color: '64748B' }),
          new TextRun({ text: ' de ', size: 18, color: '64748B' }),
          new TextRun({ children: [PageNumber.TOTAL_PAGES], size: 18, color: '64748B' }),
          new TextRun({ text: '   ·   circles-ai.ai   ·   2026-06-03',
                        size: 18, color: '64748B' }),
        ],
      })]}),
    },
    children,
  }],
});

Packer.toBuffer(doc).then(buf => {
  const out = path.join(__dirname, 'organigrama.docx');
  fs.writeFileSync(out, buf);
  console.log('WROTE', out, buf.length, 'bytes');
});
