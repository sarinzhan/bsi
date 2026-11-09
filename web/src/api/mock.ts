import { applyToChat, applyToProjects } from './chatReducer';
import type { PlatformApi } from './client';
import { can, canApproveTool } from './access';
import { accessChanges, roleChanges, users, history as initialHistory, initialChats, initialProjects, resources, servers, skills, systems } from './mockData';
import { cannedOutput, commandFor, kindOf, serverTools } from './mockTools';
import type { AccessChange, AgentEvent, Role, RoleChange, User, AgentMessage, Chat, Decision, FileChange, PlanItem, Project, Step, ToolAnswer, ToolCall, ToolMessage } from './types';

// In-memory store, so state survives navigation inside the app.
const chats = new Map<string, Chat>(initialChats().map((c) => [c.id, c]));
let projects: Record<string, Project> = Object.fromEntries(initialProjects().map((p) => [p.id, p]));
const history: Decision[] = [...initialHistory];

let idSeq = 100;
const nextId = (prefix: string) => `${prefix}${++idSeq}`;
const delay = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

// ---- server tools: approvals ----
const pendingAnswers = new Map<string, (answer: ToolAnswer | 'timeout') => void>();
const pendingKinds = new Map<string, ToolCall['kind']>();
const answeredBy = new Map<string, string>();

// ---- access: the signed-in user (dev: switchable) ----
let currentUserId = 'sarinzha';
const me = (): User => users.find((u) => u.id === currentUserId)!;
const readGrants = new Set<string>(); // "<chatId>:<server>": reads allowed for the rest of the chat
const devServer: Record<string, string> = { superapp: 'dev-docker-01', tiffany: 'dev-docker-02' };
const DIAGNOSE = /\b(logs?|errors?|fails?|failing|crash\w*|down|restart\w*|why|broken|slow)\b/i;
type Send = (event: AgentEvent) => void;

/** Shows the approval card (unless a read grant exists), waits for the answer, then "runs" the tool. */
async function callTool(chatId: string, send: Send, tool: string, server: string, system: string, service: string, reason?: string) {
  const kind = kindOf(tool);
  const call: ToolCall = { id: nextId('t'), tool, kind, server, command: commandFor(tool, system, 'dev', service), reason, status: 'waiting' };
  const show = (c: ToolCall) => send({ type: 'message', message: { id: c.id, role: 'tool', call: c } satisfies ToolMessage });
  const allowed = servers.find((s) => s.name === server)?.allowedTools ?? [];
  if (!allowed.includes(tool)) {
    // Same as server-tools: rejected before the developer is asked.
    show({ ...call, status: 'failed', output: `Rejected: ${tool} is not allowed on ${server} (server settings). Allowed: ${allowed.join(', ') || 'nothing'}` });
    return false;
  }
  let approvedBy = 'auto · reads on this server allowed for this chat';
  if (!(kind === 'read' && readGrants.has(`${chatId}:${server}`))) {
    show(call);
    send({ type: 'status', status: 'waiting' });
    const answer = await new Promise<ToolAnswer | 'timeout'>((resolve) => {
      pendingAnswers.set(call.id, resolve);
      pendingKinds.set(call.id, kind);
      setTimeout(() => pendingAnswers.get(call.id)?.('timeout'), 5 * 60_000);
    });
    pendingAnswers.delete(call.id);
    if (answer === 'deny' || answer === 'timeout') {
      show({ ...call, status: 'denied', approvedBy: answer === 'timeout' ? 'no answer in 5 minutes' : answeredBy.get(call.id) });
      return false;
    }
    if (answer === 'allow_chat') readGrants.add(`${chatId}:${server}`);
    approvedBy = `${answeredBy.get(call.id)} · ${answer === 'allow_chat' ? 'reads for this chat' : 'once'}`;
    send({ type: 'status', status: 'working' });
  }
  show({ ...call, status: 'running', approvedBy });
  await delay(700);
  show({ ...call, status: 'done', approvedBy, output: cannedOutput(tool, system, service) });
  return true;
}

/** "Why does X keep restarting?" -> look at the server with tools, each call approved in the chat. */
async function diagnose(chat: Chat, text: string, send: Send) {
  const lower = text.toLowerCase();
  const inSystem = Object.values(projects).filter((p) => p.systemId === chat.systemId);
  const project = inSystem.find((p) => lower.includes(p.name.replace('-service', ''))) ?? inSystem[0];
  const say = (t: string) => send({ type: 'message', message: { id: nextId('a'), role: 'agent', text: t, skills: ['deploy-compose'] } });
  const stop = () => {
    say("OK, I won't touch the server. Tell me what you want to check instead, or paste the error here.");
    send({ type: 'status', status: 'waiting' });
  };
  if (!project) return stop();
  send({ type: 'project', project });
  const server = devServer[chat.systemId] ?? 'dev-docker-01';
  const svc = project.name;
  say(`I'll look at ${svc} on ${server}: container state first, then its logs. Each server call needs your approval.`);
  if (!(await callTool(chat.id, send, 'docker_ps', server, chat.systemId, svc))) return stop();
  await delay(400);
  if (!(await callTool(chat.id, send, 'docker_logs', server, chat.systemId, svc))) return stop();
  await delay(400);
  say(`Found it: ${svc} restarts because its DB pool is too small (2 connections, 14 requests waiting). ` +
    'The real fix is in code: maximum-pool-size 10, committed to git and deployed. First I would restart it so dev works now.');
  if (!(await callTool(chat.id, send, 'compose_restart', server, chat.systemId, svc, 'unblock dev while the pool fix goes through git'))) return stop();
  say(`${svc} restarted and is up. Say "go" and I'll make the pool-size change in git so it doesn't come back.`);
  send({ type: 'status', status: 'running' });
}

/** Guesses a service name from the request, e.g. "returned goods app" -> returned-service. */
function serviceNameFrom(text: string): string {
  const skip = new Set(['create', 'make', 'build', 'need', 'want', 'service', 'that', 'with', 'where', 'some', 'small', 'staff', 'shop']);
  const word = text
    .toLowerCase()
    .replace(/[^a-z\s]/g, ' ')
    .split(/\s+/)
    .find((w) => w.length > 3 && !skip.has(w));
  return (word ?? 'new') + '-service';
}

/** The fake agent's "decision": reuse a project the text mentions, or create a new one. */
function findOrCreateProject(systemId: string, text: string): { project: Project; isNew: boolean } {
  const lower = text.toLowerCase();
  const existing = Object.values(projects).find(
    (p) => p.systemId === systemId && lower.includes(p.name.replace('-service', '')),
  );
  if (existing) return { project: existing, isNew: false };
  const name = serviceNameFrom(text);
  return {
    isNew: true,
    project: {
      id: name, systemId, name, status: 'working', description: text, repo: `${systemId}/${name}`,
      files: [], chatIds: [],
    },
  };
}

function planFor(project: Project, isNew: boolean, text: string, chatId: string) {
  const db = project.name.replace('-service', '-db');
  const lastNo = Math.max(0, ...history.filter((d) => d.systemId === project.systemId).map((d) => Number(d.id.slice(4))));
  const adr = `ADR-${String(lastNo + 1).padStart(4, '0')}`;
  const today = new Date().toISOString().slice(0, 10).replace(/-0?/g, '.');
  const sameDay = history.filter((d) => d.version.startsWith(today)).length;
  const plan: PlanItem[] = isNew
    ? [
        { action: 'create', name: project.name, detail: 'new project · Spring Boot, hexagonal rules' },
        { action: 'create', name: db, detail: 'PostgreSQL 16, own database' },
        { action: 'deploy', name: 'Docker Compose', detail: 'dev-docker-01' },
      ]
    : [{ action: 'reuse', name: project.name, detail: 'existing project · code change only' }];
  const steps = isNew
    ? [`Created project ${project.name} from template`, 'Wrote code · mvn verify green', 'Updated infra/compose.dev.yml',
       'Validated infra files', 'Platform applied: docker compose up -d', `${project.name} healthy`]
    : [`Changed ${project.name}`, 'mvn verify green', `Platform redeployed ${project.name}`, 'Healthy'];
  const file: FileChange = isNew
    ? {
        path: 'infra/compose.dev.yml', status: 'added', addedLines: [1, 11],
        content: [
          `  ${project.name}:               # ${adr} (new)`,
          `    image: registry/${project.systemId}/${project.name}:0.1.0`,
          `    environment: { DB_URL: "jdbc:postgresql://${db}:5432/app" }`,
          `    depends_on: { ${db}: { condition: service_healthy } }`,
          '    deploy: { resources: { limits: { cpus: "1", memory: 768M } } }',
          '',
          `  ${db}:                    # ${adr} (new)`,
          '    image: postgres:16-alpine',
          `    volumes: [${db}-data:/var/lib/postgresql/data]`,
          '    healthcheck:',
          '      test: ["CMD", "pg_isready"]',
        ].join('\n'),
      }
    : { path: 'CHANGELOG.md', status: 'modified', addedLines: [1, 1], content: `- ${text}` };
  const decision: Decision = {
    id: adr,
    systemId: project.systemId,
    kind: isNew ? 'feature' : 'change',
    title: isNew ? `New ${project.name}` : `Change ${project.name}: ${text.slice(0, 50)}`,
    decision: isNew ? `New project ${project.name} with its own ${db}, deployed with Compose.` : 'Code change only.',
    why: text,
    rejected: isNew ? 'adding it to an unrelated project, sharing a database.' : 'new infrastructure.',
    skills: isNew ? ['architecture-decisions', 'add-postgres', 'deploy-compose'] : ['spring-service'],
    projects: [project.name],
    chatId,
    version: `${today}-${sameDay + 1}`,
    author: 'agent · requested by Sarinzha K.',
    createdAt: new Date().toISOString(),
  };
  return { plan, steps, file, decision };
}

async function runAgent(chatId: string, text: string, emit: (e: AgentEvent) => void, cancelled: () => boolean) {
  const send = (event: AgentEvent) => {
    const chat = chats.get(chatId);
    if (chat) chats.set(chatId, applyToChat(chat, event));
    projects = applyToProjects(projects, event);
    if (event.type === 'project' && !event.project.chatIds.includes(chatId)) {
      projects[event.project.id] = { ...projects[event.project.id], chatIds: [...event.project.chatIds, chatId] };
    }
    if (!cancelled()) emit(event);
  };

  const chat = chats.get(chatId)!;
  send({ type: 'message', message: { id: nextId('u'), role: 'user', text } });
  send({ type: 'status', status: 'working' });
  await delay(600);

  if (DIAGNOSE.test(text)) {
    await diagnose(chat, text, send);
    return;
  }

  const { project, isNew } = findOrCreateProject(chat.systemId, text);
  send({ type: 'project', project });
  const { plan, steps: stepTexts, file, decision } = planFor(project, isNew, text, chatId);

  const messageId = nextId('a');
  const steps: Step[] = stepTexts.map((t, i) => ({ id: 's' + i, text: t, status: 'pending' }));
  const agent: AgentMessage = {
    id: messageId,
    role: 'agent',
    text: isNew
      ? `Nothing in ${chat.systemId} covers this, so I'm creating a new project: ${project.name}.`
      : `This belongs to the existing project ${project.name}. I read its ADRs and code first.`,
    skills: decision.skills,
    plan,
    steps,
  };
  send({ type: 'message', message: agent });

  for (let i = 0; i < steps.length; i++) {
    send({ type: 'step', messageId, step: { ...steps[i], status: 'running' } });
    await delay(900);
    if (i === 2 || i === steps.length - 1) {
      send({ type: 'file', projectId: project.id, file });
      if (!history.some((d) => d.id === decision.id)) history.unshift(decision);
      send({ type: 'decision', decision });
    }
    send({ type: 'step', messageId, step: { ...steps[i], status: 'done' } });
  }
  projects[project.id] = { ...projects[project.id], status: 'running' };
  send({ type: 'status', status: 'running' });
}

export const mockApi: PlatformApi = {
  async listSystems() {
    return systems;
  },
  async listChats(systemId) {
    return [...chats.values()]
      .filter((c) => c.systemId === systemId)
      .reverse()
      .map(({ id, systemId: sys, title, status, projectIds }) => ({ id, systemId: sys, title, status, projectIds }));
  },
  async getChat(chatId) {
    const chat = chats.get(chatId);
    if (!chat) throw new Error(`Chat ${chatId} not found`);
    return chat;
  },
  async createChat(systemId) {
    const chat: Chat = { id: nextId('c'), systemId, title: 'New chat', status: 'waiting', projectIds: [], messages: [] };
    chats.set(chat.id, chat);
    return chat;
  },
  sendMessage(chatId, text, onEvent) {
    let stopped = false;
    void runAgent(chatId, text, onEvent, () => stopped);
    return () => {
      stopped = true;
    };
  },
  async listProjects(systemId) {
    return Object.values(projects)
      .filter((p) => p.systemId === systemId)
      .map(({ id, systemId: sys, name, status }) => ({ id, systemId: sys, name, status }));
  },
  async getProject(projectId) {
    const project = projects[projectId];
    if (!project) throw new Error(`Project ${projectId} not found`);
    return project;
  },
  async listDecisions(systemId) {
    return history.filter((d) => d.systemId === systemId);
  },
  async listServers() {
    return servers;
  },
  async updateServerAccess(name: string, allowedTools: string[], reason: string) {
    const i = servers.findIndex((s) => s.name === name);
    if (i < 0) throw new Error(`Server ${name} not found`);
    const s = servers[i];
    const unknown = allowedTools.filter((t) => !serverTools.some((x) => x.name === t));
    if (unknown.length) throw new Error(`Unknown tools: ${unknown.join(', ')}`);
    if (allowedTools.includes('ssh_exec') && s.env === 'prod') throw new Error(`${name}: ssh_exec (any command) is never allowed on prod`);
    if (!can(me(), 'servers.manage')) throw new Error('Only DevOps and admins can change server access');
    if (!reason.trim()) throw new Error('Say why you change the access');
    const added = allowedTools.filter((t) => !s.allowedTools.includes(t)).sort();
    const removed = s.allowedTools.filter((t) => !allowedTools.includes(t)).sort();
    if (!added.length && !removed.length) return s;
    accessChanges.push({ server: name, added, removed, by: me().name, reason, at: new Date().toISOString() });
    servers[i] = { ...s, allowedTools: [...allowedTools].sort() };
    return servers[i];
  },
  async listAccessChanges(name: string): Promise<AccessChange[]> {
    return accessChanges.filter((c) => c.server === name).reverse();
  },
  async listServerTools() {
    return serverTools;
  },
  async answerToolCall(_chatId, callId, answer) {
    const kind = pendingKinds.get(callId);
    if (kind && !canApproveTool(me(), kind)) throw new Error(`${me().name} cannot approve ${kind} tools`);
    answeredBy.set(callId, me().name);
    pendingAnswers.get(callId)?.(answer);
  },
  async getMe() {
    return me();
  },
  async switchDevUser(id: string) {
    if (users.some((u) => u.id === id)) currentUserId = id;
  },
  async listUsers() {
    return [...users].sort((a, b) => a.name.localeCompare(b.name));
  },
  async setUserRoles(userId: string, roles: Role[], reason: string) {
    if (!can(me(), 'users.manage')) throw new Error('Only admins can change roles');
    const i = users.findIndex((u) => u.id === userId);
    if (i < 0) throw new Error('User not found');
    if (roles.length === 0) throw new Error('A user needs at least one role');
    if (!reason.trim()) throw new Error('Say why you change the roles');
    const u = users[i];
    if (u.roles.includes('admin') && !roles.includes('admin') && users.filter((x) => x.roles.includes('admin')).length === 1) {
      throw new Error('This is the last admin; make someone else admin first');
    }
    const added = roles.filter((r) => !u.roles.includes(r)).sort();
    const removed = u.roles.filter((r) => !roles.includes(r)).sort();
    if (added.length || removed.length) {
      roleChanges.push({ user: userId, added, removed, by: me().name, reason, at: new Date().toISOString() });
      users[i] = { ...u, roles: [...roles].sort() };
    }
    return users[i];
  },
  async listRoleChanges(userId: string): Promise<RoleChange[]> {
    return roleChanges.filter((c) => c.user === userId).reverse();
  },
  async listResources(systemId) {
    return resources[systemId] ?? [];
  },
  async listSkills() {
    return skills;
  },
};
