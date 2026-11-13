export interface SampleTelemetryDataset {
  id: "spa_gt3" | "silverstone_gt3";
  filename: string;
  path: string;
  label: string;
  shortLabel: string;
  formatNote: string;
}

export const SAMPLE_TELEMETRY_DATASETS: SampleTelemetryDataset[] = [
  {
    id: "spa_gt3",
    filename: "sample_spa_gt3.csv",
    path: "/samples/sample_spa_gt3.csv",
    label: "Spa GT3 Sample (100 Hz)",
    shortLabel: "Spa GT3 CSV",
    formatNote: "Synthetic GT3 telemetry fixture (5,000 frames @ 100 Hz)",
  },
  {
    id: "silverstone_gt3",
    filename: "sample_silverstone_gt3.csv",
    path: "/samples/sample_silverstone_gt3.csv",
    label: "Silverstone GT3 Sample (100 Hz)",
    shortLabel: "Silverstone GT3 CSV",
    formatNote: "Synthetic GT3 telemetry fixture (5,000 frames @ 100 Hz)",
  },
];

export function isSampleTelemetryFilename(filename?: string | null): boolean {
  if (!filename) return false;
  const lower = filename.toLowerCase();
  return SAMPLE_TELEMETRY_DATASETS.some((ds) => lower.endsWith(ds.filename));
}

export async function fetchSampleCsvText(
  dataset: SampleTelemetryDataset
): Promise<string> {
  // Static public asset under /samples/ — must bypass API_BASE prefixing.
  // eslint-disable-next-line no-restricted-syntax
  const res = await fetch(dataset.path);
  if (!res.ok) {
    throw new Error(`Failed to load sample dataset (${dataset.filename})`);
  }
  return res.text();
}
