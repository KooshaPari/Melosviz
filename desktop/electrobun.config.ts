import type { ElectrobunConfig } from "electrobun/bun";

const config: ElectrobunConfig = {
  app: {
    name: "MelosViz",
    identifier: "dev.phenotype.melosviz",
    version: "0.1.0",
    description: "Festival music-video visualizer — analyze WAV → render cinematic MP4",
    fileAssociations: [
      {
        ext: ["wav"],
        // macOS opens WAV files with MelosViz
        name: "WAV Audio File",
        role: "Editor",
      },
    ],
  },

  build: {
    bun: {
      entrypoint: "src/index.ts",
    },
    views: {
      main: {
        entrypoint: "views/main/index.ts",
      },
    },
    copy: {
      // bundle the Python backend alongside the app
      "../backend": "backend",
    },
    // App icon: all macOS sizes (16–1024) generated via rsvg-convert + iconutil
    // from assets/brand/logo.svg; electrobun runs iconutil to produce AppIcon.icns.
    mac: {
      icons: "assets/icons/MelosViz.iconset",
    },
  },
};

export default config;
