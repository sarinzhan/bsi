// Domain types shared by the UI and the (future) backend API.
// The AgentEvent union is the contract for the chat stream (SSE).

export type Env = 'dev' | 'stage' | 'prod';

export interface SystemInfo {
  id: string;
  name: string;
  color: string;
}

export interface Server {
  name: string;
  host: string;
  runtime: 'Docker'; // v1: Docker only. Kubernetes and Swarm come later.
  runtimeVersion: string;
  env: Env;
  memoryUsedGb: number;
  memoryTotalGb: number;
  usedFor: string;
  /** Tools the agent may call on this server, set in its settings. Empty = no access. */
  allowedTools: string[];
}

/** One change of a server's allowed tools, shown in its settings. */
export interface AccessChange {
  server: string;
  added: string[];
  removed: string[];
  by: string;
  reason: string;
  at: string; // ISO date-time
}

export type ResourceKind = 'app' | 'db' | 'broker' | 'platform';
export type ResourceStatus = 'healthy' | 'starting' | 'failed';

export interface Resource {
  name: string;
  kind: ResourceKind;
  image: string;
  server: string;
  usage: string;
  definedIn: string; // file:line that defines it
  adr: string; // decision that explains it
  status: ResourceStatus;
}

export type DecisionKind = 'feature' | 'change' | 'infrastructure' | 'fix';

/**
 * One entry of the system's decision log (ADR). Kept for the whole system, not per project:
 * stored as files in <system>/platform/docs/adr/ and shown on the History page.
 */
export interface Decision {
  id: string; // ADR-0007
  systemId: string;
  kind: DecisionKind;
  title: string;
  decision: string;
  why: string;
  rejected: string;
  skills: string[];
  projects: string[]; // project names it touched
  chatId?: string; // chat where it was decided
  version: string; // system version that shipped it, e.g. 2026.11.7-2
  author: string; // "agent · requested by Sarinzha K."
  createdAt: string; // ISO date-time
}

export interface FileChange {
  path: string;
  status: 'added' | 'modified';
  content: string;
  /** 1-based inclusive line range written by the agent, for highlighting */
  addedLines?: [number, number];
}

export type StepStatus = 'pending' | 'running' | 'done' | 'failed';

export interface Step {
  id: string;
  text: string;
  status: StepStatus;
}

export interface PlanItem {
  action: 'create' | 'reuse' | 'deploy';
  name: string;
  detail: string;
}

export interface UserMessage {
  id: string;
  role: 'user';
  text: string;
}

export interface AgentMessage {
  id: string;
  role: 'agent';
  text: string;
  skills?: string[];
  plan?: PlanItem[];
  steps?: Step[];
}

export type Message = UserMessage | AgentMessage | ToolMessage;

export type Status = 'working' | 'running' | 'waiting' | 'failed';

/** A conversation. The user just opens a chat; the agent decides which projects it works in. */
export interface ChatSummary {
  id: string;
  systemId: string;
  title: string;
  status: Status;
  projectIds: string[];
}

export interface Chat extends ChatSummary {
  messages: Message[];
}

/** Something that exists: a service with its repo and files. Chats change projects. */
export interface ProjectSummary {
  id: string;
  systemId: string;
  name: string;
  status: Status;
}

export interface Project extends ProjectSummary {
  description: string;
  repo: string;
  files: FileChange[];
  chatIds: string[];
}

export interface Skill {
  id: string;
  description: string;
  version: string;
  owner: string;
  usage: string;
  body: string;
}

/** Events the agent streams while it works on a message in a chat. */
export type AgentEvent =
  | { type: 'message'; message: Message }
  | { type: 'step'; messageId: string; step: Step }
  | { type: 'project'; project: Project } // the chat now works in this project (new or existing)
  | { type: 'file'; projectId: string; file: FileChange }
  | { type: 'decision'; decision: Decision } // goes to the system history
  | { type: 'status'; status: Status };

export type ToolKind = 'read' | 'write' | 'full';
export type ToolCallStatus = 'waiting' | 'denied' | 'running' | 'done' | 'failed';

/** One server tool call. Shown in the chat as an approval card, then with its output. */
export interface ToolCall {
  id: string;
  tool: string;
  kind: ToolKind;
  server: string;
  command: string; // exactly what the platform will run (secrets masked)
  reason?: string;
  status: ToolCallStatus;
  approvedBy?: string;
  output?: string;
}

export interface ToolMessage {
  id: string;
  role: 'tool';
  call: ToolCall;
}

export type ToolAnswer = 'allow_chat' | 'allow_once' | 'deny';

/** A row of the tools table (served by server-tools: GET /api/tools). */
export interface ServerToolInfo {
  name: string;
  kind: ToolKind;
  summary: string;
  params: string;
  approval: string;
}

export type Role = 'developer' | 'devops' | 'admin';

/** A platform user. Several roles add up; admin includes developer + devops. */
export interface User {
  id: string;
  name: string;
  roles: Role[];
}

export interface RoleChange {
  user: string;
  added: string[];
  removed: string[];
  by: string;
  reason: string;
  at: string;
}
