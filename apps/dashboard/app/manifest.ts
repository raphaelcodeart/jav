import type { MetadataRoute } from "next";

// Lets "Aggiungi a schermata Home" on Android show the real app icon and
// name instead of a screenshot/generic globe -- icon.png/apple-icon.png
// (same directory) already cover iOS via Next's file-based favicon
// convention; this covers the Android/PWA "manifest" side of the same ask.
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Jav · Judo Arte e Vida",
    short_name: "Jav",
    start_url: "/login",
    display: "standalone",
    background_color: "#ffffff",
    theme_color: "#e43f21",
    icons: [
      { src: "/icon.png", sizes: "512x512", type: "image/png" },
      { src: "/apple-icon.png", sizes: "180x180", type: "image/png" },
    ],
  };
}
