// Lint das aplicações React. As dependências NÃO estão no package.json de propósito: o container
// `web` do compose roda `npm install` a cada subida, e ferramenta de CI ali dentro só faria a demo
// demorar mais para começar. Instale sob demanda, como no script de acessibilidade:
//
//   npm i --no-save --legacy-peer-deps eslint@9 typescript-eslint@8 @eslint/js eslint-plugin-react-hooks@5 globals
//   npm run lint
//
// A régua é curta por escolha: `react-hooks` (dependência faltando no useEffect, hook dentro de if —
// bugs de verdade, difíceis de ver na revisão) e os erros básicos de TypeScript. Regra de formatação
// fica de fora; o que o Prettier resolveria não vale um passo vermelho na CI.
import js from "@eslint/js";
import tseslint from "typescript-eslint";
import reactHooks from "eslint-plugin-react-hooks";
import globals from "globals";

export default tseslint.config(
  { ignores: ["dist", "dev-dist", "node_modules", "scripts/**"] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ["**/*.{ts,tsx}"],
    languageOptions: { ecmaVersion: 2022, globals: globals.browser },
    plugins: { "react-hooks": reactHooks },
    rules: {
      ...reactHooks.configs.recommended.rules,
      // `_` na frente é a convenção do repositório para "existe por contrato, não uso".
      "@typescript-eslint/no-unused-vars": ["error", { argsIgnorePattern: "^_", varsIgnorePattern: "^_" }],
    },
  },
);
