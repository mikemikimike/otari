/**
 * The one place a sidebar row's shape is decided.
 *
 * Every row in either rail goes through `navRowClass`: the leaves, a group's
 * expand trigger, the "Back to" link at the head of the organization rail, the
 * Organization row in the footer, and the collapsed icon buttons. Keeping them
 * in one module is what stops the rail drifting a row at a time, and it mirrors
 * `otari-ai/frontend/src/app/navigationRowStyles.ts` so the two shells stay
 * recognizably the same file at M5.
 *
 * Three decisions worth knowing before editing:
 *
 * **44px is the floor, everywhere.** `min-h-11` rather than vertical padding, so
 * a row with a longer label that wraps grows instead of squashing, and so a row
 * is a comfortable touch target on the mobile drawer without a second rule.
 *
 * **Hover and selection move in opposite directions off the rail.** The rail
 * itself is `--color-background-muted`. An unselected row hovers to
 * `surface-subtle`, which is a step *toward* the page in light mode and a step
 * away in dark; a selected row sits on `surface-alt` (that is
 * `--color-surface-muted`), which in light mode is lighter than the rail. Dark
 * mode needs the explicit `dark:bg-surface`: there `surface-muted` and the rail
 * are within a couple of units of lightness, so the selected chip would be
 * invisible, while `surface` is clearly darker than the rail. This is the
 * navigation design's ramp, not an invention: the selected row is a lifted chip,
 * not a tinted one, which is why it is no longer `bg-primary-subtle`.
 *
 * **A nested child is indented with padding, not a narrower box.** `3.125rem` is
 * the parent's icon lane (0.75rem padding + 1rem icon + 0.75rem gap) plus
 * 0.625rem, so a child's label starts past where its parent's label starts and
 * the row's fill still spans the rail.
 */

const ROW_BASE =
  "flex min-h-11 w-full items-center gap-3 rounded-lg px-3 text-sm font-medium leading-[1.375rem] transition-colors duration-150 ease-out motion-reduce:transition-none"

const ROW_RESTING =
  "text-muted hover:bg-surface-subtle hover:text-foreground focus-visible:bg-surface-subtle focus-visible:text-foreground"

const ROW_SELECTED = "bg-surface-alt text-foreground dark:bg-surface"

/** The class list for one sidebar row. */
export function navRowClass({
  isActive = false,
  collapsed = false,
  nested = false,
}: {
  isActive?: boolean
  collapsed?: boolean
  nested?: boolean
} = {}): string {
  return [
    ROW_BASE,
    isActive ? ROW_SELECTED : ROW_RESTING,
    nested ? "pl-[3.125rem]" : "",
    collapsed ? "min-w-11 justify-center px-0" : "",
  ]
    .filter(Boolean)
    .join(" ")
}

/** The heading above a group of rows. 32px of label supplies the group's air. */
export const NAV_SECTION_HEADING_CLASS =
  "flex min-h-8 items-center px-3 text-overline"

/** A row's leading glyph, at the size the design draws it. */
export const NAV_ICON_CLASS = "h-4 w-4 shrink-0"
