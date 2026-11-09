import type { FileChange } from '../api/types';

/** Read-only file view with the agent's lines highlighted. */
export default function CodeView({ file }: { file: FileChange }) {
  const lines = file.content.split('\n');
  const [from, to] = file.addedLines ?? [0, -1];
  return (
    <div className="code">
      <div className="code-head">
        <span>{file.path}</span>
        <span style={{ marginLeft: 'auto', color: '#9aa1ae' }}>{file.status}</span>
      </div>
      <div className="code-body">
        {lines.map((text, i) => {
          const n = i + 1;
          const added = n >= from && n <= to;
          return (
            <div key={i} className={added ? 'line added' : 'line'}>
              <span className="n">{n}</span>
              <span className="m">{added ? '+' : ''}</span>
              <span className="t">{text}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
