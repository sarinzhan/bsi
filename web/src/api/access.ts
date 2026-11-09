import type { Role, ToolKind, User } from './types';

// Mirrors services/platform-api/src/platform_api/access/domain/roles.py (GET /api/roles).
// The UI uses it only to show or hide buttons; the backend decides.

export type Permission =
  | 'chat.use'
  | 'code.change'
  | 'server.read.approve'
  | 'server.write.approve'
  | 'server.any_command.approve'
  | 'deploy.approve'
  | 'servers.manage'
  | 'skills.manage'
  | 'users.manage';

export const permissionLabel: Record<Permission, string> = {
  'chat.use': 'Use chats, see code and history',
  'code.change': 'Let the agent change code (commits, merge requests)',
  'server.read.approve': 'Approve server reads (logs, files, container state)',
  'server.write.approve': 'Approve server changes (write file, run, restart)',
  'server.any_command.approve': 'Approve any command (ssh_exec)',
  'deploy.approve': 'Deploy services and resources (DBs, brokers)',
  'servers.manage': 'Manage servers and the tools the agent may use',
  'skills.manage': 'Edit skills',
  'users.manage': 'Give and take roles',
};

const DEVELOPER: Permission[] = ['chat.use', 'code.change', 'server.read.approve'];
const DEVOPS: Permission[] = [
  'chat.use', 'server.read.approve', 'server.write.approve', 'server.any_command.approve', 'deploy.approve', 'servers.manage',
];

export const rolePermissions: Record<Role, Permission[]> = {
  developer: DEVELOPER,
  devops: DEVOPS,
  admin: [...new Set([...DEVELOPER, ...DEVOPS, 'skills.manage', 'users.manage'] as Permission[])],
};

export const roleLabel: Record<Role, string> = { developer: 'Developer', devops: 'DevOps', admin: 'Admin' };
export const allRoles: Role[] = ['developer', 'devops', 'admin'];
export const allPermissions = Object.keys(permissionLabel) as Permission[];

/** Several roles = union of their permissions. */
export const can = (user: User | null | undefined, p: Permission) =>
  !!user && user.roles.some((r) => rolePermissions[r].includes(p));

const approvalFor: Record<ToolKind, Permission> = {
  read: 'server.read.approve',
  write: 'server.write.approve',
  full: 'server.any_command.approve',
};
export const canApproveTool = (user: User | null | undefined, kind: ToolKind) => can(user, approvalFor[kind]);
export const approvalPermission = (kind: ToolKind) => approvalFor[kind];

export const rolesText = (roles: Role[]) => roles.map((r) => roleLabel[r]).join(' + ');
