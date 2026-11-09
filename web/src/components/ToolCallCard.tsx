import { useState } from 'react';
import { canApproveTool } from '../api/access';
import type { ToolAnswer, ToolCall } from '../api/types';
import { useCurrentUser } from '../auth';

const verb: Record<ToolCall['kind'], string> = {
  read: 'wants to read',
  write: 'wants to CHANGE',
  full: 'wants to run a command on',
};

const statusText: Record<ToolCall['status'], string> = {
  waiting: 'Waiting for you',
  running: 'Running…',
  done: 'Done',
  failed: 'Failed',
  denied: 'Denied',
};

/**
 * Approval card for a server tool call.
 * Read tools: any developer, devops or admin; "Allow for this chat" is offered.
 * Write tools and any command: devops or admin only, every time. A developer sees who has to approve.
 */
export default function ToolCallCard({ call, onAnswer }: { call: ToolCall; onAnswer?: (answer: ToolAnswer) => void }) {
  const { user } = useCurrentUser();
  const [showOutput, setShowOutput] = useState(false);
  const rejected = call.status === 'failed' && (call.output ?? '').startsWith('Rejected');
  const waiting = call.status === 'waiting';
  const mayAnswer = waiting && !!onAnswer && canApproveTool(user, call.kind);
  const status = rejected ? 'Not allowed on this server' : waiting && !mayAnswer ? 'Waiting for DevOps' : statusText[call.status];

  return (
    <div className={`tool-call ${call.kind} ${call.status}`} role={mayAnswer ? 'alertdialog' : undefined} aria-label={`${call.tool} on ${call.server}`}>
      <div className="tool-head">
        <span className={`tool-kind ${call.kind}`}>{call.kind}</span>
        <span>
          The agent {verb[call.kind]} <b className="mono">{call.server}</b>
        </span>
        <span className={`tool-status ${call.status}`}>{status}</span>
      </div>
      <div className="tool-name mono">{call.tool}</div>
      <pre className="tool-command">{call.command}</pre>
      {call.reason && <div className="tool-reason">Reason: “{call.reason}”</div>}

      {mayAnswer && (
        <div className="tool-actions">
          {call.kind === 'read' && (
            <button type="button" className="btn primary" onClick={() => onAnswer!('allow_chat')}>Allow reads for this chat</button>
          )}
          <button type="button" className={call.kind === 'read' ? 'btn' : 'btn primary'} onClick={() => onAnswer!('allow_once')}>
            {call.kind === 'read' ? 'Allow once' : 'Allow'}
          </button>
          <button type="button" className="btn" onClick={() => onAnswer!('deny')}>Deny</button>
          <span className="muted" style={{ fontSize: 12 }}>No answer in 5 min = denied</span>
        </div>
      )}
      {waiting && !mayAnswer && (
        <div className="tool-needs">
          Server changes are approved by <b>DevOps</b> or an <b>admin</b>. They see this card in the chat; it waits up to 5 minutes.
        </div>
      )}

      {call.approvedBy && !waiting && <div className="muted tool-by">{call.status === 'denied' ? 'Denied' : 'Approved'} · {call.approvedBy}</div>}

      {rejected && <div className="tool-rejected">{call.output}</div>}

      {call.output && !rejected && (
        <div>
          <button type="button" className="link-btn" onClick={() => setShowOutput((v) => !v)} aria-expanded={showOutput}>
            {showOutput ? 'Hide output' : 'Show output'}
          </button>
          {showOutput && <pre className="tool-output">{call.output}</pre>}
        </div>
      )}
    </div>
  );
}
