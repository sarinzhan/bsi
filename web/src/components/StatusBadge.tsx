import type { Status } from '../api/types';

const labels: Record<Status, { text: string; tone: string }> = {
  working: { text: 'Agent working', tone: 'working' },
  running: { text: 'Running on dev', tone: 'ok' },
  waiting: { text: 'Needs attention', tone: 'warn' },
  failed: { text: 'Failed', tone: 'bad' },
};

export default function StatusBadge({ status }: { status: Status }) {
  const { text, tone } = labels[status];
  return <span className={`badge ${tone}`}>{text}</span>;
}

export const statusColor: Record<Status, string> = {
  working: 'var(--accent)',
  running: 'var(--ok)',
  waiting: '#c27a00',
  failed: 'var(--bad)',
};
