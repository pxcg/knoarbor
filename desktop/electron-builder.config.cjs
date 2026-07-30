module.exports = {
  appId: "ai.knoarbor.desktop",
  artifactName: "${productName}-${version}-${arch}.${ext}",
  productName: "KnoArbor",
  directories: {
    output: "release",
  },
  afterPack: "./scripts/after-pack.cjs",
  files: ["out/**/*", "package.json"],
  extraResources: [
    {
      from: "../renderer/dist",
      to: "renderer",
    },
    {
      from: "resources/service",
      to: "service",
    },
    {
      from: "resources/icons",
      to: "icons",
      filter: ["*.png"],
    },
  ],
  mac: {
    category: "public.app-category.productivity",
    icon: "resources/icons/icon.icns",
    target: ["dmg", "zip"],
  },
  win: {
    icon: "resources/icons/icon.ico",
    target: ["nsis"],
  },
  nsis: {
    allowElevation: false,
    deleteAppDataOnUninstall: false,
    differentialPackage: true,
    guid: "ai.knoarbor.desktop",
    include: "installer.nsh",
    oneClick: true,
    perMachine: false,
  },
  linux: {
    icon: "resources/icons/icon.png",
  },
};
