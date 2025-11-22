import { useMemo } from 'react';

export type RadarMetric = {
  key: string;
  label: string;
  invert?: boolean;
};

export type RadarSeries = {
  label: string;
  values: Record<string, number>;
  color?: string;
};

type RadarChartProps = {
  metrics: RadarMetric[];
  series: RadarSeries[];
  size?: number;
};

const DEFAULT_COLORS = ['#4cc38a', '#3c82f6', '#f59e0b', '#f97316'];

export default function RadarChart({ metrics, series, size = 320 }: RadarChartProps): JSX.Element | null {
  const data = useMemo(() => {
    if (!metrics.length || !series.length) {
      return null;
    }
    const center = size / 2;
    const padding = 32;
    const radius = (size - padding * 2) / 2;
    const angleStep = (Math.PI * 2) / metrics.length;
    const maxByMetric: Record<string, number> = {};
    metrics.forEach((metric) => {
      const maxValue = series.reduce((max, item) => {
        const value = item.values[metric.key] ?? 0;
        return value > max ? value : max;
      }, 0);
      maxByMetric[metric.key] = maxValue || 1;
    });

    const gridLevels = 4;
    const gridPolygons = Array.from({ length: gridLevels }, (_, level) => {
      const ratio = (level + 1) / gridLevels;
      return metrics
        .map((metric, index) => {
          const angle = angleStep * index;
          const x = center + Math.sin(angle) * ratio * radius;
          const y = center - Math.cos(angle) * ratio * radius;
          return `${x},${y}`;
        })
        .join(' ');
    });

    const axisLines = metrics.map((metric, index) => {
      const angle = angleStep * index;
      const x = center + Math.sin(angle) * radius;
      const y = center - Math.cos(angle) * radius;
      return { x1: center, y1: center, x2: x, y2: y, metric };
    });

    const polygons = series.map((serie, serieIndex) => {
      const path = metrics
        .map((metric, index) => {
          const rawValue = serie.values[metric.key] ?? 0;
          const maxValue = maxByMetric[metric.key] || 1;
          let ratio = maxValue > 0 ? rawValue / maxValue : 0;
          if (metric.invert) {
            ratio = 1 - ratio;
          }
          ratio = Math.max(0, Math.min(1, ratio));
          const angle = angleStep * index;
          const x = center + Math.sin(angle) * ratio * radius;
          const y = center - Math.cos(angle) * ratio * radius;
          return `${x},${y}`;
        })
        .join(' ');
      const color = serie.color ?? DEFAULT_COLORS[serieIndex % DEFAULT_COLORS.length];
      return { path, color, label: serie.label };
    });

    const labels = metrics.map((metric, index) => {
      const angle = angleStep * index;
      const x = center + Math.sin(angle) * (radius + 18);
      const y = center - Math.cos(angle) * (radius + 18);
      return { x, y, text: metric.label };
    });

    return { center, gridPolygons, axisLines, polygons, labels };
  }, [metrics, series, size]);

  if (!data) return null;

  return (
    <figure style={{ maxWidth: size, margin: '0 auto' }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img">
        <g fill="none" stroke="#2b3547" strokeWidth="1" opacity={0.6}>
          {data.gridPolygons.map((points, index) => (
            <polygon key={`grid-${index}`} points={points} />
          ))}
        </g>
        <g stroke="#3b4252" strokeWidth="1" opacity={0.6}>
          {data.axisLines.map((axis, index) => (
            <line key={`axis-${index}`} x1={axis.x1} y1={axis.y1} x2={axis.x2} y2={axis.y2} />
          ))}
        </g>
        {data.polygons.map((polygon, index) => (
          <polygon
            key={`serie-${index}`}
            points={polygon.path}
            fill={polygon.color}
            opacity={0.35}
            stroke={polygon.color}
            strokeWidth="2"
          />
        ))}
        <g fontSize="12" fill="#cbd5f5" textAnchor="middle">
          {data.labels.map((label, index) => (
            <text key={`label-${index}`} x={label.x} y={label.y}>
              {label.text}
            </text>
          ))}
        </g>
      </svg>
      <figcaption style={{ marginTop: '0.5rem', fontSize: '0.85rem' }}>
        {series.map((serie, index) => {
          const color = serie.color ?? DEFAULT_COLORS[index % DEFAULT_COLORS.length];
          return (
            <span key={serie.label} style={{ marginRight: '1rem', display: 'inline-flex', alignItems: 'center' }}>
              <span
                style={{
                  width: '0.9rem',
                  height: '0.9rem',
                  backgroundColor: color,
                  display: 'inline-block',
                  marginRight: '0.4rem',
                  borderRadius: '0.2rem',
                }}
              />
              {serie.label}
            </span>
          );
        })}
      </figcaption>
    </figure>
  );
}

