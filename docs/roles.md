# Roles

Three roles. A user can have several; permissions add up. **Admin = Developer + DevOps + users and skills.**
Source of truth: `services/platform-api/src/platform_api/access/domain/roles.py` (the UI only mirrors it).

| permission | Developer | DevOps | Admin |
|---|:-:|:-:|:-:|
| Use chats, see code and history | ✓ | ✓ | ✓ |
| Let the agent change code (commits, merge requests) | ✓ | — | ✓ |
| Approve server **reads** (logs, files, container state) | ✓ | ✓ | ✓ |
| Approve server **changes** (file_write, docker_run, compose_run, compose_restart) | — | ✓ | ✓ |
| Approve **any command** (ssh_exec) | — | ✓ | ✓ |
| **Deploy** services and resources (DBs, brokers) | — | ✓ | ✓ |
| Manage **servers** and the tools the agent may use on them | — | ✓ | ✓ |
| Edit **skills** | — | — | ✓ |
| Give and take **roles** | — | — | ✓ |

Typical combinations: developer · devops · developer + devops (on call) · admin.

## How it plays out

- A developer asks "why does orders keep restarting?". The agent's **read** calls are approved by the developer.
  The **restart** card shows "Waiting for DevOps": a devops or admin approves it (or it is denied after 5 minutes).
- A developer asks for a new feature. The agent writes code and opens a merge request; the **deploy** waits for
  a devops/admin approval.
- A user with developer + devops does both alone: still one approval card per change, so there is a record.

## Rules

- A user may have no role (signed in, can do nothing). The last admin cannot lose the admin role.
- Only admins change roles, with a reason. Every change is logged (who, added, removed, why, when).
- Unknown user or permission = denied. The backend decides; the UI only hides buttons.
- Sign-in: user name + password on BSI's login page; a JWT sent as a Bearer token. Admins add users with a temporary
  password and can reset it; the user must pick their own at the next sign-in. Company SSO can replace it later.
