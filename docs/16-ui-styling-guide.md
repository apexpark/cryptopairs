# UI Styling Guide

## Purpose

Define consistent frontend patterns while allowing targeted use of selected component libraries.

## Hard Rules

1. `MUST` use one primary design system to avoid style and behavior conflicts.
2. `MUST` keep accessibility baseline (keyboard navigation, visible focus, contrast).
3. `MUST` preserve consistent spacing, typography, and color tokens via shared theme variables.
4. `MUST` avoid mixing component primitives with overlapping responsibilities in the same view.
5. `MUST` make data integrity and risk states visually explicit.

## Library Strategy

1. Primary foundation: `shadcn/ui` on top of `Radix UI`.
2. Optional targeted use:
- `Mantine` for specialized data-heavy controls if needed.
- `Chakra UI` only for isolated legacy widgets or if a clear gap exists.

3. If optional libraries are used:
- Wrap them behind internal UI adapters.
- Ensure token and theme alignment with the primary system.

## Required Visual States

1. Data integrity:
- `COMPLETE` (green)
- `PARTIAL_BACKFILLED` (amber)
- `INCOMPLETE` or `FAILED` (red)
- `STALE` (neutral warning)

2. Execution/risk:
- Safe/armed state
- Kill switch active state
- Strategy blocked state with explicit reason

## Component Guidance

1. Create shared primitives for:
- status badges
- metric cards
- table filters
- modal confirmations for risky actions

2. Standardize data grid behavior for sorting, pagination, and sticky columns.
3. Use chart components that support zoom, brush, and tooltips for trading analysis.

## Acceptance Checks

1. No duplicate modal, toast, or form primitives from competing libraries in same surface.
2. Theme tokens drive all colors and spacing.
3. Core dashboards are responsive and legible on desktop and tablet widths.
4. Risk-critical actions require explicit confirmation.

## Out Of Scope

1. Full white-label theming and customer branding.
2. Native mobile app design system.
