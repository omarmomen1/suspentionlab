import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
  ]),
  {
    rules: {
      // CSRF enforcement: all backend calls must go through lib/api.ts
      // (apiFetch/apiJson) or AuthContext.fetchWithAuth so cookies and the
      // X-CSRF-Token header are always attached. Direct fetch() is allowed
      // only in the auth plumbing itself. "warn" until legacy pages migrate;
      // flip to "error" once the raw-fetch count reaches zero.
      "no-restricted-syntax": [
        "warn",
        {
          selector:
            "CallExpression[callee.name='fetch']",
          message:
            "Use apiFetch()/apiJson() from '@/lib/api' (or fetchWithAuth from AuthContext) instead of raw fetch — raw calls drop credentials and the CSRF header.",
        },
      ],
    },
  },
]);

export default eslintConfig;
