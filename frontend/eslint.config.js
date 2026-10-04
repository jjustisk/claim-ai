import pluginVue from 'eslint-plugin-vue'

/** @type {import('eslint').Linter.Config[]} */
export default [
  { ignores: ['dist/**', 'node_modules/**'] },
  ...pluginVue.configs['flat/essential'],
  {
    files: ['src/**/*.{js,vue}'],
    rules: {
      // Form objects are intentionally mutated via v-model on nested props.
      'vue/no-mutating-props': 'off',
      'vue/multi-word-component-names': 'off',
      'vue/no-unused-vars': 'warn',
      'no-unused-vars': ['warn', { argsIgnorePattern: '^_', caughtErrorsIgnorePattern: '^_', varsIgnorePattern: '^_' }],
    },
  },
]
