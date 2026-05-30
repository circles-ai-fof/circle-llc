"""
ProductArbitrageEvaluator — M5.5 — agente experimental que evalúa señales
de Google Trends (kind=google_trends, M4.14) y determina si hay oportunidad
de arbitraje cross-border / dropshipping.

Founder del audio: "analizar cuáles son los productos que más se venden de
cierto lugar, en qué regiones, y ver qué tipo de esos productos pueden
pegar en otras regiones... compraste en 86 centavos y lo terminaste
vendiendo en 19.99. Te quitan las comisiones de todos los correspondientes
y te quedan 10 latas por unidad."

Scope:
- Input: trending search signal (theme con prefijo [GEO]) + opcional
  cost_estimate del founder
- Output: ArbitrageAnalysis con margin breakdown + recomendación

Status: ACTIVE (M5.11 — promovido 2026-05-30 con 30/30 golden cases).
"""
from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from typing import List, Optional

from ..core.base_agent import BaseAgent

logger = logging.getLogger(__name__)


_SYSTEM = """You are ProductArbitrageEvaluator — un agente que evalúa
trending searches geográficas como oportunidades de arbitraje
cross-border / dropshipping.

ALCANCE:
- Recibís: un trending search (con prefijo [GEO]: [US], [MX], [EC], etc.)
  + opcional source_cost_usd (lo que cuesta el producto en Aliexpress/origen)
  + opcional target_price_usd (lo que se vende en mercado destino)
- Tu trabajo: determinar si esto es producto físico arbitrabable, calcular
  margin estimate, sugerir test (skip / test / deepdive)

PRINCIPIOS:
- NO todo trending search es producto. Filtrar primero:
  · "rob lowe", "elecciones 2026" → NO product (skip)
  · "anillo Apple Vision Pro", "cargador GaN" → SÍ product (evaluable)
- Si no podés determinar el tipo, recomendá "skip"
- Comisiones típicas de plataforma:
  · Amazon: 15% referral + 0.99/transaction
  · MercadoLibre LATAM: 11-14% + envío
  · Shopify own store: 0% (pero CPA en ads ~$10-30)
- Margin healthy: >40% después de todas las comisiones

FORMATO (JSON estricto, sin markdown):
{
  "is_physical_product": true | false,
  "product_category": "string — ej: 'electrónica de consumo', 'belleza', N/A",
  "source_region_inferred": "string — donde lo compraríamos",
  "target_region_inferred": "string — donde lo venderíamos",
  "margin_estimate_pct": "string — '~50%' o 'no calculable sin precios'",
  "shipping_complexity": "low" | "medium" | "high",
  "time_to_test_weeks": "string — '1-2 semanas si Shopify + Aliexpress'",
  "key_risks": ["risk 1", "risk 2"],
  "recommendation": "test" | "skip" | "deepdive",
  "confidence": 0.0-0.85,
  "reasoning": "string"
}

REGLAS:
- Español neutro
- is_physical_product=false → recommendation="skip" siempre
- Si source/target son la misma región, no hay arbitraje (skip)
- Confidence máxima 0.85 (Google Trends no garantiza demanda transaccional)
"""


@dataclass
class ArbitrageAnalysis:
    is_physical_product: bool = False
    product_category: str = ""
    source_region_inferred: str = ""
    target_region_inferred: str = ""
    margin_estimate_pct: str = ""
    shipping_complexity: str = "medium"
    time_to_test_weeks: str = ""
    key_risks: List[str] = field(default_factory=list)
    recommendation: str = "skip"
    confidence: float = 0.5
    reasoning: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class ProductArbitrageEvaluatorAgent(BaseAgent):
    """Status: ACTIVE (M5.11). 30/30 golden cases. v1.0.0."""

    AGENT_NAME = "product_arbitrage_evaluator"
    AGENT_VERSION = "1.0.0"
    EXPERIMENTAL = False

    @property
    def system_prompt(self) -> str:
        return _SYSTEM

    def analyze(
        self,
        trending_query: str,
        target_geo: str = "",
        source_cost_usd: Optional[float] = None,
        target_price_usd: Optional[float] = None,
    ) -> ArbitrageAnalysis:
        if self._mock_mode:
            return self._mock_analyze(trending_query, target_geo, source_cost_usd, target_price_usd)
        prompt = self._build_prompt(trending_query, target_geo, source_cost_usd, target_price_usd)
        raw = self._call(prompt)
        data = self._extract_json(raw)
        return ArbitrageAnalysis(
            is_physical_product=bool(data.get("is_physical_product", False)),
            product_category=str(data.get("product_category", "")),
            source_region_inferred=str(data.get("source_region_inferred", "")),
            target_region_inferred=str(data.get("target_region_inferred", "")),
            margin_estimate_pct=str(data.get("margin_estimate_pct", "")),
            shipping_complexity=str(data.get("shipping_complexity", "medium")),
            time_to_test_weeks=str(data.get("time_to_test_weeks", "")),
            key_risks=list(data.get("key_risks", []) or []),
            recommendation=str(data.get("recommendation", "skip")),
            confidence=float(data.get("confidence", 0.5)),
            reasoning=str(data.get("reasoning", "")),
        )

    def _build_prompt(
        self, trending_query: str, target_geo: str,
        source_cost_usd: Optional[float], target_price_usd: Optional[float],
    ) -> str:
        cost_line = f"\nsource_cost_usd: ${source_cost_usd:.2f}" if source_cost_usd else ""
        price_line = f"\ntarget_price_usd: ${target_price_usd:.2f}" if target_price_usd else ""
        geo_line = f"\ntarget_geo: {target_geo}" if target_geo else ""
        return (
            f"Trending search: {trending_query}{geo_line}{cost_line}{price_line}\n\n"
            f"Evaluá si es producto arbitrabable y devolvé el JSON."
        )

    def _mock_analyze(
        self, trending_query: str, target_geo: str,
        source_cost_usd: Optional[float], target_price_usd: Optional[float],
    ) -> ArbitrageAnalysis:
        # Quitar prefijo [GEO] si está
        q = trending_query.lower()
        if q.startswith("["):
            q = q.split("]", 1)[-1].strip()

        # Heurística mock: keywords sugieren producto vs no-producto
        PRODUCT_KEYWORDS = [
            "cargador", "audífonos", "auriculares", "smartwatch", "tablet",
            "case", "funda", "anillo", "collar", "lámpara", "crema", "serum",
            "gadget", "drone", "speaker", "altavoz", "ring", "watch",
        ]
        NON_PRODUCT_KEYWORDS = [
            "weather", "election", "elections", "elecciones", "vs",
            "partido", "presidente", "news", "noticia", "death", "muerte",
        ]
        is_product = any(kw in q for kw in PRODUCT_KEYWORDS)
        non_product = any(kw in q for kw in NON_PRODUCT_KEYWORDS)
        if non_product or not is_product:
            return ArbitrageAnalysis(
                is_physical_product=False,
                product_category="N/A",
                source_region_inferred="N/A",
                target_region_inferred="N/A",
                margin_estimate_pct="N/A",
                shipping_complexity="medium",
                time_to_test_weeks="N/A",
                key_risks=["[Demo] No es producto físico arbitrabable"],
                recommendation="skip",
                confidence=0.55,
                reasoning=f"[Demo] '{q[:50]}' no parece producto físico — skip.",
            )

        # Si tenemos cost + price, calcular margin real
        margin_pct = "~40-55% (estimado)"
        if source_cost_usd and target_price_usd:
            gross = target_price_usd - source_cost_usd
            # Asumir 15% comisión plataforma + 10% shipping
            net = gross - target_price_usd * 0.25
            if target_price_usd > 0:
                pct = (net / target_price_usd) * 100
                margin_pct = f"~{pct:.0f}% (después de 15% comisión + 10% shipping)"

        return ArbitrageAnalysis(
            is_physical_product=True,
            product_category="[Demo] Electrónica / accesorios consumer",
            source_region_inferred="[Demo] CN (Aliexpress) o US (Amazon FBA)",
            target_region_inferred=target_geo or "[Demo] target_geo no especificado",
            margin_estimate_pct=margin_pct,
            shipping_complexity="medium",
            time_to_test_weeks="[Demo] 1-2 semanas con Shopify + Aliexpress dropshipping",
            key_risks=[
                "[Demo] Trending search no garantiza intención de compra",
                "[Demo] Saturación competitiva — verificar Amazon BSR antes",
                "[Demo] Margen real puede bajar 30% por returns + CPA",
            ],
            recommendation="test" if (source_cost_usd and target_price_usd) else "deepdive",
            confidence=0.65,
            reasoning=(
                f"[Demo] Producto físico detectado. {'Margen calculable con precios provistos.' if source_cost_usd else 'Faltan precios para margin real.'}"
            ),
        )
