import type {
  AccessChange, AgentEvent, Chat, ChatSummary, HostKey, NewServer, Role, RoleChange, Server, ServerToolInfo, SystemInfo,
  ToolAnswer, User,
} from './types';
import { httpApi } from './http';

/** Everything the UI needs from platform-api (http.ts). All data lives in its Postgres database. */
export interface PlatformApi {
  /** Systems some server serves. None until the first server is added. */
  listSystems(): Promise<SystemInfo[]>;

  listChats(systemId: string): Promise<ChatSummary[]>;
  getChat(chatId: string): Promise<Chat>;
  createChat(systemId: string): Promise<Chat>;
  /** Starts the agent on a message. Returns a function that stops listening. */
  sendMessage(chatId: string, text: string, onEvent: (event: AgentEvent) => void): () => void;
  /** The developer's answer to a server tool approval card. */
  answerToolCall(chatId: string, callId: string, answer: ToolAnswer): Promise<void>;

  // ---- access ----
  getMe(): Promise<User>;
  /** Dev only: "Viewing as" switcher. Behind nginx the login decides who you are. */
  switchDevUser(id: string): Promise<void>;
  listUsers(): Promise<User[]>;
  /** Admins only. */
  setUserRoles(userId: string, roles: Role[], reason: string): Promise<User>;
  listRoleChanges(userId: string): Promise<RoleChange[]>;

  // ---- servers ----
  listServers(): Promise<Server[]>;
  /** The platform's SSH public key, for ~/.ssh/authorized_keys on the server (DevOps and admins). */
  platformPublicKey(): Promise<string>;
  /** Connects to host:port and reads its SSH host key, to show its fingerprint before saving. */
  fetchHostKey(host: string, port: number): Promise<HostKey>;
  addServer(server: NewServer): Promise<Server>;
  /** SSH in with the pinned key: Docker version and memory, or why it failed. */
  checkServer(name: string): Promise<Server>;
  /** The tools the agent may use there. Rejects ssh_exec on prod. */
  updateServerAccess(name: string, allowedTools: string[], reason: string): Promise<Server>;
  listAccessChanges(name: string): Promise<AccessChange[]>;
  /** The server tools that exist. */
  listServerTools(): Promise<ServerToolInfo[]>;
}

export const api: PlatformApi = httpApi;
