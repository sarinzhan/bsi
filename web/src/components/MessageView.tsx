import type { Message, PlanItem, Step, ToolAnswer } from '../api/types';
import ToolCallCard from './ToolCallCard';

const actionLabel: Record<PlanItem['action'], string> = { create: '+', reuse: '=', deploy: '→' };
const stepIcon: Record<Step['status'], string> = { done: '✓', running: '●', pending: '○', failed: '✗' };

export default function MessageView({ message, onAnswer }: { message: Message; onAnswer?: (callId: string, answer: ToolAnswer) => void }) {
  if (message.role === 'tool') {
    const call = message.call;
    return <ToolCallCard call={call} onAnswer={onAnswer ? (a) => onAnswer(call.id, a) : undefined} />;
  }
  if (message.role === 'user') {
    return <div className="msg-user">{message.text}</div>;
  }
  return (
    <div className="msg-agent">
      <div className="ai" aria-hidden="true">AI</div>
      <div className="body">
        {message.skills && message.skills.length > 0 && (
          <div className="skills-row">
            <span className="muted">Skills:</span>
            {message.skills.map((s) => (
              <span key={s} className="chip">{s}</span>
            ))}
          </div>
        )}
        <p>{message.text}</p>
        {message.plan && message.plan.length > 0 && (
          <div className="card plan">
            <div className="plan-head">Decisions</div>
            {message.plan.map((p) => (
              <div key={p.name} className="plan-row">
                <b>{actionLabel[p.action]} {p.name}</b> · {p.detail}
              </div>
            ))}
          </div>
        )}
        {message.steps && message.steps.length > 0 && (
          <div className="card steps" aria-live="polite">
            {message.steps.map((s) => (
              <div key={s.id} className={`step ${s.status}`}>
                <span className="icon">{stepIcon[s.status]}</span>
                <span>{s.status === 'running' ? s.text + '…' : s.text}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
