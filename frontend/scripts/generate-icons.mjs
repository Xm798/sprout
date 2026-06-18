// Rasterizes the PWA icon SVGs in public/ into the PNGs referenced by the
// manifest. Uses @resvg/resvg-js because it renders SVG gradients correctly
// (ImageMagick's built-in renderer drops `fill="url(#...)"` and produces blank
// icons). Run with `npm run icons` after editing icon.svg / icon-maskable.svg.
import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { Resvg } from "@resvg/resvg-js";

const publicDir = join(dirname(fileURLToPath(import.meta.url)), "..", "public");

// [source SVG, output PNG, square size in px]
const targets = [
  ["icon.svg", "icon-192.png", 192],
  ["icon.svg", "icon-512.png", 512],
  ["icon.svg", "apple-touch-icon.png", 180],
  ["icon-maskable.svg", "icon-maskable-512.png", 512],
];

for (const [src, out, size] of targets) {
  const svg = readFileSync(join(publicDir, src));
  const resvg = new Resvg(svg, {
    fitTo: { mode: "width", value: size },
  });
  writeFileSync(join(publicDir, out), resvg.render().asPng());
  console.log(`${src} -> ${out} (${size}x${size})`);
}
