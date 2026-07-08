# Dark Mode Theme Toggle

## Overview

Many users work in low-light environments and have asked for a dark theme. We will add a dark mode to the application with a user-controlled toggle. The chosen theme must persist across visits, and on a user's very first visit we should respect the theme their operating system already prefers.

The dark theme applies globally across every page of the application so the experience is consistent, using our existing design tokens rather than bespoke per-screen palettes.

## Requirements

1. **Settings toggle** — Add a light/dark theme toggle control in the application's Settings page. Toggling it immediately switches the active theme.

2. **Persist preference** — Persist the user's selected theme to `localStorage` so the same theme is applied automatically on the user's next visit.

3. **Respect system preference on first load** — On the first load, when the user has no stored preference, honor the operating system setting via the `prefers-color-scheme` media query to choose the initial theme.

4. **Apply globally** — Apply the active theme consistently to all pages and shared components of the application.

## Out of Scope

- Per-component or per-page custom color themes
- User-defined custom palettes or theme editor
- Scheduled/automatic time-of-day switching
