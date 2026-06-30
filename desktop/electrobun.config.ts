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
      // electrobun's view build only transpiles index.ts → index.js; it does NOT
      // copy the HTML shell.  Without this entry, views://main/index.html resolves
      // to a missing file and the webview 404s (blank window).
      "views/main/index.html": "views/main/index.html",
    },
    // App icon: all macOS sizes (16–1024) generated via rsvg-convert + iconutil
    // from assets/brand/logo.svg; electrobun runs iconutil to produce AppIcon.icns.
    mac: {
      icons: "assets/icons/MelosViz.iconset",
    },
  },

  scripts: {
    // Creates a uv venv with melosviz[analysis,bridge] deps inside the bundled
    // backend directory so the app can run librosa/fastapi/uvicorn without
    // relying on whatever python3 happens to be on the user's PATH.
    postBuild: "scripts/postBuild.ts",
  },
};

export default config;
