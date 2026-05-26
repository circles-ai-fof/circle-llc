import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "circles-ai.ai — Factory of Factories",
    short_name: "circles-ai",
    description:
      "Valida tu idea de negocio en 14 días con IA antes de construir",
    start_url: "/",
    display: "standalone",
    background_color: "#0B0F1A",
    theme_color: "#00D4FF",
    icons: [
      {
        src: "/favicon.ico",
        sizes: "any",
        type: "image/x-icon",
      },
    ],
  };
}
