/* eslint-env node */
module.exports = {
  root: true,
  parser: '@typescript-eslint/parser',
  plugins: ['@typescript-eslint'],
  extends: [
    'eslint:recommended',
    'plugin:@typescript-eslint/recommended',
    'prettier'
  ],
  env: { browser: true, es2021: true, node: true },
  rules: {
    '@typescript-eslint/no-explicit-any': 'off'
  },
  ignorePatterns: ['dist', 'node_modules', 'src-tauri']
}

