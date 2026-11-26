module.exports = {
  root: true,
  env: { browser: true, es2022: true, node: true },
  extends: ["eslint:recommended", "plugin:react/recommended", "plugin:react-hooks/recommended"],
  parserOptions: { ecmaVersion: "latest", sourceType: "module", ecmaFeatures: { jsx: true } },
  settings: { react: { version: "18.3" } },
  globals: { vi: "readonly", describe: "readonly", it: "readonly", expect: "readonly", test: "readonly" },
  rules: { "react/prop-types": "off", "react/react-in-jsx-scope": "off" },
};
