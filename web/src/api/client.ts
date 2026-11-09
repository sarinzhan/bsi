import type {
  AccessChange, AgentEvent, Role, RoleChange, User, Chat, ChatSummary, Decision, Project, ProjectSummary, Resource, Server, ServerToolInfo, Skill, SystemInfo, ToolAnswer,
} from './types';
import { mockApi } from './mock';

/**
 * Everything the UI needs from the platform backend.
 * Today it is implemented by mockApi. A real implementation will use
 * fetch() for the queries and an EventSource (SSE) for sendMessage.
 */
export interface PlatformApi {
  listSystems(): Promise<SystemInfo[]>;

  listChats(systemId: string): Promise<ChatSummary[]>;
  getChat(chatId: string): Promise<Chat>;
  createChat(systemId: string): Promise<Chat>;
  /** Starts the agent on a message. Returns a function that stops listening. */
  sendMessage(chatId: string, text: string, onEvent: (event: AgentEvent) => void): () => void;
  /** The developer's answer to a server tool approval card. */
  answerToolCall(chatId: string, callId: string, answer: ToolAnswer): Promise<void>;

  listProjects(systemId: string): Promise<ProjectSummary[]>;
  getProject(projectId: string): Promise<Project>;

  /** The system's decision log (ADRs), newest first. */
  listDecisions(systemId: string): Promise<Decision[]>;

  // ---- access (platform-api `access` module) ----
  getMe(): Promise<User>;
  /** Dev only: "Viewing as" switcher. In prod the user comes from company SSO. */
  switchDevUser(id: string): Promise<void>;
  listUsers(): Promise<User[]>;
  /** Admins only. */
  setUserRoles(userId: string, roles: Role[], reason: string): Promise<User>;
  listRoleChanges(userId: string): Promise<RoleChange[]>;

  listServers(): Promise<Server[]>;
  /** Server settings (platform admins): the tools the agent may use. Rejects ssh_exec on prod. */
  updateServerAccess(name: string, allowedTools: string[], reason: string): Promise<Server>;
  listAccessChanges(name: string): Promise<AccessChange[]>;
  /** Served by the server-tools service (GET /api/tools). */
  listServerTools(): Promise<ServerToolInfo[]>;
  listResources(systemId: string): Promise<Resource[]>;
  listSkills(): Promise<Skill[]>;
}

export const api: PlatformApi = mockApi;
