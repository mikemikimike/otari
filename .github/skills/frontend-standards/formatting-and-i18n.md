# Formatting numbers, money, and dates

Every user-visible number, cost, and timestamp goes through
`web/src/shared/helpers/format.ts`. That module is the only place the dashboard decides how a
value reads, which is what keeps a cost formatted the same way in a table cell, a stat tile,
and a share card.

Use what is there before adding anything: `formatNumber`, `formatCost`, `formatUsd`,
`formatUsdHeadline`, `formatTokens`, `formatPct`, `formatContext`, `formatDateTime`,
`formatReleaseDate`, `formatRelative`, `deltaFraction`.

## Use `Intl`, never string arithmetic

`Intl.NumberFormat` and `Intl.DateTimeFormat` are in the platform, handle grouping and
currency placement, and round the way a reader expects. `"$" + value.toFixed(2)` does not: it
loses grouping, and it rounds a sub-cent cost to `$0.00`, which for a per-request price is not
a rounding error but the whole value. `formatCost` is what handles that case (four fraction
digits below a cent), and it exists so no call site has to.

Construct a formatter once per module rather than once per render.

```ts
// Good
const COMPACT = new Intl.NumberFormat("en-US", { notation: "compact" })
export const formatCompact = (value: number) => COMPACT.format(value)

// Bad: a new formatter object on every row of every render
const cell = new Intl.NumberFormat("en-US").format(value)
```

## Locale

Formatters are pinned to `en-US`, deliberately. The dashboard's copy is US English (see
[AGENTS.md](../../../AGENTS.md)), and a mixed page (US wording, locale-formatted numbers) is
worse than a consistent one. It is also an operator tool where a number's shape is often
copied into a ticket or a support thread, and a value that changes shape by machine makes
those reports harder to compare. If localization ever arrives, it arrives here, in one module.

## Dates

The API sends UTC ISO strings. Parse them once, format for display, and never do timezone
arithmetic by hand: `new Date(); d.setHours(d.getHours() - 5)` breaks across DST and on any
machine that is not the author's.

`formatReleaseDate` shows the other half of that rule. Its input is a `YYYY-MM` or
`YYYY-MM-DD` calendar date with no time in it, so it formats the string directly rather than
constructing a `Date`, which would shift it a day west of UTC and show the wrong month at the
edges. **A date that is not an instant should not become a `Date`.**

Relative time (`formatRelative`) is for recency an operator reads at a glance. It is also the
one output that changes without the data changing, so the screenshot suite masks it (see
[testing.md](./testing.md)) and a test asserting on it needs a fixed clock.

## Placeholders

An absent value renders as the em dash placeholder these helpers already return, not as an
empty cell and not as `null`. Table columns stay aligned and a missing value is visibly
missing rather than possibly-still-loading. (The em dash here is a rendered character in
data, not prose punctuation, so it is outside the writing-style rule in
[AGENTS.md](../../../AGENTS.md).)
