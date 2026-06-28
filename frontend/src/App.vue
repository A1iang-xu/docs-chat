<script setup lang="ts">
import AppSidebar from '@/components/AppSidebar.vue'
</script>

<template>
  <div class="app-layout">
    <AppSidebar />
    <main class="main-content">
      <router-view />
    </main>
  </div>
</template>

<style>
/* ============================================================
   PRIMITIVES (theme-independent)
   ============================================================ */
:root {
  --brand-50: #fafafa;
  --brand-100: #f4f4f5;
  --brand-200: #e4e4e7;
  --brand-300: #d4d4d8;
  --brand-400: #a1a1aa;
  --brand-500: #71717a;
  --brand-600: #52525b;
  --brand-700: #3f3f46;
  --brand-800: #27272a;
  --brand-900: #18181b;

  --background-50: #ffffff;
  --background-100: #fafafa;
  --background-200: #f5f5f5;
  --background-300: #e5e5e5;
  --background-400: #d4d4d4;
  --background-500: #a3a3a3;
  --background-600: #404040;
  --background-700: #262626;
  --background-800: #171717;
  --background-900: #0a0a0a;

  --text-50: #fafafa;
  --text-100: #ededed;
  --text-200: #d4d4d4;
  --text-300: #a1a1a1;
  --text-400: #858585;
  --text-500: #6e6e6e;
  --text-600: #525252;
  --text-700: #404040;
  --text-800: #171717;
  --text-900: #0a0a0a;

  --icon-50: #fafafa;
  --icon-100: #e5e5e5;
  --icon-200: #d4d4d4;
  --icon-300: #b0b0b0;
  --icon-400: #8f8f8f;
  --icon-500: #6e6e6e;
  --icon-600: #525252;
  --icon-700: #404040;
  --icon-800: #262626;
  --icon-900: #0a0a0a;

  /* ============================================================
     SEMANTIC ROLE TOKENS — light theme
     ============================================================ */
  --background: var(--background-50);
  --card: var(--background-50);
  --popover: var(--background-50);
  --muted: var(--background-100);

  --foreground: var(--brand-900);
  --card-foreground: var(--brand-900);
  --popover-foreground: var(--brand-900);
  --primary-foreground: var(--brand-50);
  --secondary-foreground: var(--brand-900);
  --muted-foreground: var(--brand-500);
  --accent-foreground: var(--brand-900);
  --destructive-foreground: var(--background-50);
  --sidebar-foreground: var(--brand-900);
  --sidebar-primary-foreground: var(--brand-50);
  --sidebar-accent-foreground: var(--brand-900);

  --primary: var(--brand-900);
  --secondary: var(--brand-100);
  --accent: var(--brand-100);
  --input: var(--brand-200);
  --ring: var(--brand-900);

  --border: var(--brand-200);
  --border-strong: var(--brand-300);

  --success: #16a34a;
  --success-foreground: var(--background-50);
  --success-subtle: #f0fdf4;
  --success-border: #bbf7d0;
  --success-text: #15803d;

  --destructive: #dc2626;
  --destructive-subtle: #fef2f2;
  --destructive-border: #fecaca;
  --destructive-text: #b91c1c;

  --warning: #d97706;
  --warning-subtle: #fffbeb;
  --warning-border: #fde68a;
  --warning-text: #92400e;

  --brand-subtle: var(--brand-100);
  --brand-border: var(--brand-300);

  --chart-1: var(--brand-200);
  --chart-2: var(--brand-400);
  --chart-3: var(--brand-600);
  --chart-4: var(--brand-800);
  --chart-5: var(--brand-900);

  --sidebar: var(--brand-50);
  --sidebar-primary: var(--brand-900);
  --sidebar-accent: var(--brand-100);
  --sidebar-border: var(--brand-200);
  --sidebar-ring: var(--brand-400);

  --font-sans: 'Geist', ui-sans-serif, system-ui, sans-serif;
  --font-mono: 'Geist Mono', ui-monospace, monospace;
  --tracking-normal: 0em;
  --tracking-tight: -0.012em;

  --radius: 0.75rem;
  --radius-sm: 0.375rem;
  --radius-lg: 1rem;

  --shadow-2xs: 0 1px 0 0 rgba(0, 0, 0, 0.04);
  --shadow-xs: 0 1px 1px 0 rgba(0, 0, 0, 0.04);
  --shadow-sm: 0 1px 2px 0 rgba(0, 0, 0, 0.05), 0 1px 1px 0 rgba(0, 0, 0, 0.03);
  --shadow: 0 2px 4px 0 rgba(0, 0, 0, 0.06), 0 1px 2px 0 rgba(0, 0, 0, 0.03);
  --shadow-md: 0 4px 8px -2px rgba(0, 0, 0, 0.07), 0 2px 4px -1px rgba(0, 0, 0, 0.04);
  --shadow-lg: 0 12px 20px -6px rgba(0, 0, 0, 0.08), 0 4px 8px -2px rgba(0, 0, 0, 0.04);
  --shadow-xl: 0 24px 40px -10px rgba(0, 0, 0, 0.10), 0 8px 16px -4px rgba(0, 0, 0, 0.06);
  --shadow-2xl: 0 32px 56px -14px rgba(0, 0, 0, 0.14);

  --spacing: 0.25rem;
}

/* ============================================================
   SEMANTIC ROLE TOKENS — dark theme
   ============================================================ */
.dark {
  --background: var(--brand-900);
  --card: var(--brand-800);
  --popover: var(--brand-800);
  --muted: var(--brand-800);

  --foreground: var(--brand-50);
  --card-foreground: var(--brand-50);
  --popover-foreground: var(--brand-50);
  --primary-foreground: var(--brand-900);
  --secondary-foreground: var(--brand-50);
  --muted-foreground: var(--brand-400);
  --accent-foreground: var(--brand-50);
  --destructive-foreground: var(--brand-50);
  --sidebar-foreground: var(--brand-50);
  --sidebar-primary-foreground: var(--brand-900);
  --sidebar-accent-foreground: var(--brand-50);

  --primary: var(--brand-50);
  --secondary: var(--brand-800);
  --accent: var(--brand-700);
  --input: var(--brand-700);
  --ring: var(--brand-300);

  --border: var(--brand-700);
  --border-strong: var(--brand-600);

  --success: #22c55e;
  --success-foreground: #052e16;
  --success-subtle: #0f2417;
  --success-border: #166534;
  --success-text: #4ade80;

  --destructive: #ef4444;
  --destructive-subtle: #2a1416;
  --destructive-border: #7f1d1d;
  --destructive-text: #fca5a5;

  --brand-subtle: var(--brand-800);
  --brand-border: var(--brand-700);

  --chart-1: var(--brand-700);
  --chart-2: var(--brand-500);
  --chart-3: var(--brand-300);
  --chart-4: var(--brand-200);
  --chart-5: var(--brand-50);

  --sidebar: var(--brand-800);
  --sidebar-primary: var(--brand-50);
  --sidebar-accent: var(--brand-700);
  --sidebar-border: var(--brand-700);
  --sidebar-ring: var(--brand-400);
}

/* ===== RESET & BASE ===== */
*, *::before, *::after {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}

html, body {
  height: 100%;
  overflow: hidden;
}

body {
  font-family: var(--font-sans);
  font-size: 14px;
  line-height: 1.6;
  color: var(--foreground);
  background: var(--background);
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

/* ===== APP LAYOUT ===== */
.app-layout {
  display: flex;
  height: 100vh;
  width: 100vw;
}

.main-content {
  margin-left: 240px;
  flex: 1;
  min-width: 0;
  height: 100vh;
  overflow-y: auto;
  background: var(--background);
}

/* ===== SCROLLBAR ===== */
::-webkit-scrollbar {
  width: 6px;
}

::-webkit-scrollbar-track {
  background: transparent;
}

::-webkit-scrollbar-thumb {
  background: var(--border-strong);
  border-radius: 3px;
}

::-webkit-scrollbar-thumb:hover {
  background: var(--muted-foreground);
}

::selection {
  background: rgba(24, 24, 27, 0.15);
}
</style>