"use client";
import { Area, AreaChart, Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

const axis = { fontSize: 11, fill: "#6b7090" };

export function AreaSeries({ data, x, y, color = "#5b3df5", height = 180, format }: { data: any[]; x: string; y: string; color?: string; height?: number; format?: (v: number) => string }) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={data} margin={{ top: 6, right: 8, left: -12, bottom: 0 }}>
        <defs>
          <linearGradient id={`g${y}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity={0.28} />
            <stop offset="100%" stopColor={color} stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid stroke="#e4e6ef" vertical={false} />
        <XAxis dataKey={x} tick={axis} tickLine={false} axisLine={false} />
        <YAxis tick={axis} tickLine={false} axisLine={false} tickFormatter={format} width={56} />
        <Tooltip formatter={(v: number) => (format ? format(v) : v)} contentStyle={{ borderRadius: 8, borderColor: "#d9dce8", fontSize: 12 }} />
        <Area type="monotone" dataKey={y} stroke={color} strokeWidth={2} fill={`url(#g${y})`} />
      </AreaChart>
    </ResponsiveContainer>
  );
}

export function Bars({ data, x, y, color = "#5b3df5", height = 220, format, horizontal }: { data: any[]; x: string; y: string; color?: string; height?: number; format?: (v: number) => string; horizontal?: boolean }) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} layout={horizontal ? "vertical" : "horizontal"} margin={{ top: 6, right: 12, left: horizontal ? 8 : -12, bottom: 0 }}>
        <CartesianGrid stroke="#e4e6ef" horizontal={!horizontal} vertical={!!horizontal} />
        {horizontal ? (
          <>
            <XAxis type="number" tick={axis} tickLine={false} axisLine={false} tickFormatter={format} />
            <YAxis type="category" dataKey={x} tick={axis} tickLine={false} axisLine={false} width={120} />
          </>
        ) : (
          <>
            <XAxis dataKey={x} tick={axis} tickLine={false} axisLine={false} />
            <YAxis tick={axis} tickLine={false} axisLine={false} tickFormatter={format} width={56} />
          </>
        )}
        <Tooltip formatter={(v: number) => (format ? format(v) : v)} contentStyle={{ borderRadius: 8, borderColor: "#d9dce8", fontSize: 12 }} />
        <Bar dataKey={y} fill={color} radius={horizontal ? [0, 4, 4, 0] : [4, 4, 0, 0]} maxBarSize={36} />
      </BarChart>
    </ResponsiveContainer>
  );
}
