"use client";

/**
 * The superadmin's usage panels.
 *
 * Colour decisions, so they are not re-litigated by eye later:
 *
 * * Every chart here is **single-series magnitude** — tokens, by day or by
 *   entity. So there is no categorical palette to get wrong, one hue per chart
 *   is the whole scheme, and no legend is needed (each title names its series).
 * * Two hues are in play only because the operation and model breakdowns sit
 *   side by side and are different questions: blue and orange, each its own
 *   one-hue context. Both pairs validate on the app's real surfaces (white
 *   card in light, #282d3c card in dark): CVD ΔE 24.7 light / 26.8 dark,
 *   normal-vision 33.6 / 31.8, all ≥ 3:1 against the surface.
 * * Dark steps are *selected* for the dark surface, not an automatic flip of
 *   the light ones.
 * * Series colour never carries text. Values and labels stay on the app's ink
 *   tokens; the coloured mark beside them carries identity.
 *
 * The per-organization table under the bars is not decoration either — it is
 * the non-visual reading of the same data.
 */

import { useMemo } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { formatInr } from "@/lib/organizations-client";
import type {
  SuperAdminAnalytics,
  UsagePoint,
  UsageSlice,
  OrganizationUsageRow,
} from "@/lib/organizations-client";

/** Compact token counts: axis ticks and bar labels have no room for 1,240,000. */
function compact(n: number): string {
  if (Math.abs(n) >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (Math.abs(n) >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return String(n);
}

function shortDate(iso: string): string {
  const d = new Date(`${iso}T00:00:00`);
  return d.toLocaleDateString(undefined, { day: "numeric", month: "short" });
}

/**
 * Shared tooltip. Recharts' default paints its label in the series colour,
 * which is exactly the "text wears the series colour" mistake — this one keeps
 * text on ink tokens and lets a small swatch carry identity.
 */
function VizTooltip({
  active,
  payload,
  label,
  swatch,
  formatLabel,
}: any) {
  if (!active || !payload?.length) return null;
  const row = payload[0].payload;
  return (
    <div className="rounded-lg border border-border bg-popover px-3 py-2 text-xs shadow-md">
      <p className="mb-1 font-medium text-popover-foreground">
        {formatLabel ? formatLabel(label ?? row.label) : (label ?? row.label)}
      </p>
      <p className="flex items-center gap-2 text-muted-foreground">
        <span
          aria-hidden
          className="inline-block h-2 w-2 rounded-full"
          style={{ background: swatch }}
        />
        <span className="tabular-nums text-popover-foreground">
          {(row.tokens ?? 0).toLocaleString()}
        </span>
        tokens
      </p>
      {typeof row.cost_inr === "number" && (
        <p className="text-muted-foreground">
          <span className="tabular-nums text-popover-foreground">
            {formatInr(row.cost_inr)}
          </span>{" "}
          estimated
        </p>
      )}
      {typeof row.calls === "number" && (
        <p className="mt-0.5 text-muted-foreground">
          <span className="tabular-nums">{row.calls.toLocaleString()}</span> calls
        </p>
      )}
    </div>
  );
}

function StatTile({
  label,
  value,
  hint,
}: {
  label: string;
  value: string;
  hint?: string;
}) {
  return (
    <Card>
      <CardContent className="p-4">
        <p className="text-xs font-medium text-muted-foreground">{label}</p>
        {/* Proportional figures: a standalone number, not a column to align. */}
        <p className="mt-1 text-2xl font-semibold text-foreground">{value}</p>
        {hint && <p className="mt-0.5 text-xs text-muted-foreground">{hint}</p>}
      </CardContent>
    </Card>
  );
}

const RANGES = [7, 30, 90] as const;

export function UsageAnalytics({
  data,
  days,
  onDaysChange,
}: {
  data: SuperAdminAnalytics;
  days: number;
  onDaysChange: (days: number) => void;
}) {
  const { totals, trend, by_organization, by_operation, by_model } = data;

  // A flat all-zero series would still draw a filled band across the card,
  // which reads as "steady low usage" rather than "nothing yet".
  const hasTrend = useMemo(() => trend.some((p: UsagePoint) => p.tokens > 0), [trend]);
  const topOrgs = useMemo(
    () => by_organization.filter((o: OrganizationUsageRow) => o.tokens > 0).slice(0, 8),
    [by_organization],
  );

  return (
    <div
      className={cn(
        "space-y-6",
        // Viz tokens, defined once. Dark steps are chosen for the dark card
        // surface, not derived from the light ones.
        "[--viz-1:#2a78d6] [--viz-2:#eb6834]",
        "dark:[--viz-1:#3987e5] dark:[--viz-2:#d95926]",
        "[--viz-grid:#e1e0d9] dark:[--viz-grid:#3a3f4e]",
        "[--viz-axis:#898781]",
      )}
    >
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        {/* Spend first. Tokens are the mechanism; rupees are the decision —
            "should we raise this school's cap" is answered in currency, and a
            seven-digit token count answers nothing. */}
        <StatTile
          label="Estimated spend"
          value={formatInr(totals.total_cost_inr)}
          hint="Approximate — excludes cached-input discounts"
        />
        <StatTile
          label="Tokens used"
          value={totals.total_tokens.toLocaleString()}
          hint={
            totals.unassigned_tokens > 0
              ? `${compact(totals.unassigned_tokens)} not tied to a school`
              : undefined
          }
        />
        <StatTile
          label="Schools"
          value={String(totals.organization_count)}
          hint={
            totals.organization_count !== totals.active_organization_count
              ? `${totals.active_organization_count} active`
              : undefined
          }
        />
        <StatTile label="Members" value={String(totals.member_count)} />
        <StatTile
          label="Awaiting approval"
          value={String(totals.pending_member_count)}
          hint={totals.pending_member_count > 0 ? "Needs a decision" : undefined}
        />
      </div>

      <Card>
        <CardHeader className="flex-row items-start justify-between gap-4 space-y-0">
          <div>
            <CardTitle>Token usage over time</CardTitle>
            <CardDescription>
              Daily totals across every school, last {days} days.
            </CardDescription>
          </div>
          {/* Filters in one row above the plot. */}
          <div className="flex shrink-0 gap-1" role="group" aria-label="Time range">
            {RANGES.map((r) => (
              <button
                key={r}
                type="button"
                onClick={() => onDaysChange(r)}
                aria-pressed={days === r}
                className={cn(
                  "rounded-md px-2.5 py-1 text-xs font-medium transition-colors",
                  days === r
                    ? "bg-foreground text-background"
                    : "text-muted-foreground hover:bg-muted hover:text-foreground",
                )}
              >
                {r}d
              </button>
            ))}
          </div>
        </CardHeader>
        <CardContent>
          {!hasTrend ? (
            <EmptyPlot message="No tokens have been spent in this window yet." />
          ) : (
            <ResponsiveContainer width="100%" height={260}>
              <AreaChart data={trend} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
                <defs>
                  <linearGradient id="tokenFill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="var(--viz-1)" stopOpacity={0.22} />
                    <stop offset="100%" stopColor="var(--viz-1)" stopOpacity={0.02} />
                  </linearGradient>
                </defs>
                {/* Recessive grid: horizontal hairlines only. */}
                <CartesianGrid
                  vertical={false}
                  stroke="var(--viz-grid)"
                  strokeDasharray="0"
                />
                <XAxis
                  dataKey="date"
                  tickFormatter={shortDate}
                  tickLine={false}
                  axisLine={false}
                  minTickGap={28}
                  tick={{ fill: "var(--viz-axis)", fontSize: 11 }}
                />
                <YAxis
                  tickFormatter={compact}
                  tickLine={false}
                  axisLine={false}
                  width={48}
                  tick={{ fill: "var(--viz-axis)", fontSize: 11 }}
                />
                <Tooltip
                  cursor={{ stroke: "var(--viz-axis)", strokeWidth: 1 }}
                  content={
                    <VizTooltip
                      swatch="var(--viz-1)"
                      formatLabel={(v: string) =>
                        new Date(`${v}T00:00:00`).toLocaleDateString(undefined, {
                          weekday: "short",
                          day: "numeric",
                          month: "short",
                        })
                      }
                    />
                  }
                />
                <Area
                  type="monotone"
                  dataKey="tokens"
                  stroke="var(--viz-1)"
                  strokeWidth={2}
                  fill="url(#tokenFill)"
                  // ≥ 8px hit target on hover, no dot on every point.
                  dot={false}
                  activeDot={{ r: 4, strokeWidth: 2, stroke: "var(--card)" }}
                />
              </AreaChart>
            </ResponsiveContainer>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Heaviest schools</CardTitle>
          <CardDescription>
            All-time token spend per organization. The table below is the same data.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {topOrgs.length === 0 ? (
            <EmptyPlot message="No school has spent a token yet." />
          ) : (
            <ResponsiveContainer width="100%" height={Math.max(160, topOrgs.length * 40)}>
              <BarChart
                data={topOrgs}
                layout="vertical"
                margin={{ top: 0, right: 48, bottom: 0, left: 8 }}
                barCategoryGap={6}
              >
                <CartesianGrid horizontal={false} stroke="var(--viz-grid)" />
                <XAxis type="number" hide />
                <YAxis
                  type="category"
                  dataKey="name"
                  width={140}
                  tickLine={false}
                  axisLine={false}
                  tick={{ fill: "var(--viz-axis)", fontSize: 11 }}
                />
                <Tooltip
                  cursor={{ fill: "var(--viz-grid)", fillOpacity: 0.4 }}
                  content={<VizTooltip swatch="var(--viz-1)" />}
                />
                <Bar
                  dataKey="tokens"
                  fill="var(--viz-1)"
                  // Rounded data-end only; the baseline end stays square.
                  radius={[0, 4, 4, 0]}
                  barSize={18}
                  label={{
                    position: "right",
                    // Recharts hands the label formatter a RenderableText,
                    // which is wider than `number`.
                    formatter: (v: unknown) => compact(Number(v) || 0),
                    fill: "var(--viz-axis)",
                    fontSize: 11,
                  }}
                />
              </BarChart>
            </ResponsiveContainer>
          )}
        </CardContent>
      </Card>

      <div className="grid gap-6 lg:grid-cols-2">
        <BreakdownCard
          title="Where tokens go"
          description="By pipeline stage, all time."
          slices={by_operation}
          color="var(--viz-1)"
        />
        <BreakdownCard
          title="By model"
          description="Which model spent them, all time."
          slices={by_model}
          color="var(--viz-2)"
        />
      </div>
    </div>
  );
}

function BreakdownCard({
  title,
  description,
  slices,
  color,
}: {
  title: string;
  description: string;
  slices: UsageSlice[];
  color: string;
}) {
  const rows = slices.filter((s) => s.tokens > 0).slice(0, 8);

  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      <CardContent>
        {rows.length === 0 ? (
          <EmptyPlot message="Nothing recorded yet." />
        ) : (
          <ResponsiveContainer width="100%" height={Math.max(160, rows.length * 38)}>
            <BarChart
              data={rows}
              layout="vertical"
              margin={{ top: 0, right: 48, bottom: 0, left: 8 }}
              barCategoryGap={6}
            >
              <CartesianGrid horizontal={false} stroke="var(--viz-grid)" />
              <XAxis type="number" hide />
              <YAxis
                type="category"
                dataKey="label"
                width={130}
                tickLine={false}
                axisLine={false}
                tick={{ fill: "var(--viz-axis)", fontSize: 11 }}
              />
              <Tooltip
                cursor={{ fill: "var(--viz-grid)", fillOpacity: 0.4 }}
                content={<VizTooltip swatch={color} />}
              />
              <Bar
                dataKey="tokens"
                radius={[0, 4, 4, 0]}
                barSize={16}
                label={{
                  position: "right",
                  formatter: (v: unknown) => compact(Number(v) || 0),
                  fill: "var(--viz-axis)",
                  fontSize: 11,
                }}
              >
                {/* One hue per chart — Cell exists only so the fill resolves
                    the CSS variable per bar rather than once at series level. */}
                {rows.map((r) => (
                  <Cell key={r.label} fill={color} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        )}
      </CardContent>
    </Card>
  );
}

function EmptyPlot({ message }: { message: string }) {
  return (
    <div className="flex h-[160px] items-center justify-center rounded-lg border border-dashed border-border">
      <p className="text-sm text-muted-foreground">{message}</p>
    </div>
  );
}
