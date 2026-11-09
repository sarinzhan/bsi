import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { api } from '../api/client';
import { applyToChat, applyToProjects } from '../api/chatReducer';
import type { Chat, Decision, Project } from '../api/types';
import ChatSidePanel from '../components/ChatSidePanel';
import MessageView from '../components/MessageView';
import StatusBadge from '../components/StatusBadge';

/** The user just opens a chat and asks. The agent decides which projects to create or change. */
export default function ChatPage() {
  const { systemId = 'superapp', chatId = 'new' } = useParams();
  const navigate = useNavigate();
  const [chat, setChat] = useState<Chat | null>(null);
  const [projects, setProjects] = useState<Record<string, Project>>({});
  const [decisions, setDecisions] = useState<Decision[]>([]);
  const [draft, setDraft] = useState('');
  const pendingText = useRef<string | null>(null); // first message of a new chat, sent after navigation
  const stopStream = useRef<(() => void) | null>(null);
  const bottom = useRef<HTMLDivElement>(null);

  // Load the chat and the projects it works in.
  useEffect(() => {
    if (chatId === 'new') {
      setChat(null);
      setProjects({});
      setDecisions([]);
      return;
    }
    let active = true;
    (async () => {
      try {
        const c = await api.getChat(chatId);
        const ps = await Promise.all(c.projectIds.map((id) => api.getProject(id)));
        const ds = await api.listDecisions(c.systemId);
        if (!active) return;
        setDecisions(ds.filter((d) => d.chatId === c.id));
        setChat(c);
        setProjects(Object.fromEntries(ps.map((p) => [p.id, p])));
      } catch {
        if (active) navigate(`/${systemId}/chats/new`, { replace: true });
      }
    })();
    return () => {
      active = false;
    };
  }, [chatId, systemId, navigate]);

  useEffect(() => () => stopStream.current?.(), []);

  const startAgent = (id: string, text: string) => {
    stopStream.current?.();
    stopStream.current = api.sendMessage(id, text, (event) => {
      setChat((c) => (c && c.id === id ? applyToChat(c, event) : c));
      setProjects((ps) => applyToProjects(ps, event));
      if (event.type === 'decision') {
        setDecisions((ds) => [event.decision, ...ds.filter((d) => d.id !== event.decision.id)]);
      }
    });
  };

  // A new chat was just created: send its first message once it is loaded.
  useEffect(() => {
    if (chat && pendingText.current) {
      const text = pendingText.current;
      pendingText.current = null;
      startAgent(chat.id, text);
    }
  }, [chat?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: 'smooth' });
  }, [chat?.messages]);

  const send = async (e?: FormEvent) => {
    e?.preventDefault();
    const text = draft.trim();
    if (!text) return;
    setDraft('');
    if (!chat) {
      const created = await api.createChat(systemId);
      pendingText.current = text;
      navigate(`/${systemId}/chats/${created.id}`);
    } else {
      startAgent(chat.id, text);
    }
  };

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      void send();
    }
  };

  const linked = (chat?.projectIds ?? []).map((id) => projects[id]).filter(Boolean);
  const working = chat?.status === 'working';

  return (
    <>
      <section className="chat-col" aria-label="Chat">
        <div className="chat-head">
          <h1>{chat ? chat.title : 'New chat'}</h1>
          {chat && chat.messages.length > 0 && <StatusBadge status={chat.status} />}
        </div>

        {chat && chat.messages.length > 0 && (
          <div className="working-in" aria-live="polite">
            <span className="muted">Working in:</span>
            {linked.length === 0 && <span className="muted">the agent is choosing…</span>}
            {linked.map((p) => (
              <Link key={p.id} to={`/${systemId}/projects/${p.id}`} className="project-chip">{p.name}</Link>
            ))}
          </div>
        )}

        <div className="messages">
          {!chat || chat.messages.length === 0 ? (
            <div className="empty-chat">
              <h2>What do you need?</h2>
              <p>Just describe it. The agent finds the right project in {systemId}, or creates a new one, and shows you where it works.</p>
            </div>
          ) : (
            chat.messages.map((m) => (
              <MessageView key={m.id} message={m} onAnswer={(callId, answer) => void api.answerToolCall(chat.id, callId, answer)} />
            ))
          )}
          <div ref={bottom} />
        </div>

        <div className="composer">
          <form onSubmit={send}>
            <label htmlFor="msg" style={{ position: 'absolute', left: -9999 }}>Message</label>
            <textarea
              id="msg"
              rows={3}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={onKeyDown}
              placeholder="e.g. Customers should be able to cancel an order · or: why does orders keep restarting?"
            />
            <div className="row">
              <span className="muted" style={{ fontSize: 12 }}>{systemId} · dev · Enter to send</span>
              <button type="submit" className="send" aria-label="Send" disabled={!draft.trim() || working}>↑</button>
            </div>
          </form>
        </div>
      </section>

      <ChatSidePanel systemId={systemId} projects={linked} decisions={decisions} />
    </>
  );
}
