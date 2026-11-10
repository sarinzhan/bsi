import type { ServerToolInfo, ToolKind } from './types';

// Mirrors platform-api's tools module (GET /api/servers/tools and the commands it builds).

const approval: Record<ToolKind, string> = {
  read: 'once per server per chat · developer, devops or admin',
  write: 'every time, with a reason · devops or admin',
  full: 'every time, exact command shown · devops or admin · never on prod',
};

const t = (name: string, kind: ToolKind, params: string, summary: string): ServerToolInfo => ({
  name, kind, params, summary, approval: approval[kind],
});

export const serverTools: ServerToolInfo[] = [
  t('folder_list', 'read', 'server, path?', 'List a folder inside the system folder.'),
  t('file_read', 'read', 'server, path, from_line?, lines?≤500', 'Read lines of a file (.env: names only).'),
  t('docker_ps', 'read', 'server', 'Containers of this system and environment.'),
  t('docker_logs', 'read', 'server, service, since?≤24h, tail?≤500', 'Logs of a compose service.'),
  t('docker_inspect', 'read', 'server, service', 'Container details, env values removed.'),
  t('docker_stats', 'read', 'server', "CPU and memory of this system's containers."),
  t('file_write', 'write', 'server, path, content, reason', 'Write a file atomically, keep a .bak copy. Commit the same change to git.'),
  t('docker_run', 'write', 'server, image, args?, env?, reason', 'Run a one-off container (--rm) on the system network.'),
  t('compose_run', 'write', 'server, service, args, reason', 'Run a one-off command in a compose service (e.g. a migration).'),
  t('compose_restart', 'write', 'server, service, reason', 'Restart a compose service.'),
  t('ssh_exec', 'full', 'server, command, reason, timeout_s?≤300', 'Any shell command. Never on prod; only when the other tools cannot answer.'),
];

export const kindOf = (tool: string): ToolKind => serverTools.find((x) => x.name === tool)?.kind ?? 'read';

/** The same fixed commands platform-api's tools module builds. */
export function commandFor(tool: string, system: string, env: string, service = ''): string {
  const project = `${system}-${env}`;
  const container =
    `c=$(docker ps -aq --filter label=com.docker.compose.project=${project} ` +
    `--filter label=com.docker.compose.service=${service} | head -n1); ` +
    `[ -n "$c" ] || { echo 'no container for ${service}' >&2; exit 4; }`;
  switch (tool) {
    case 'docker_ps':
      return `docker ps -a --filter label=com.docker.compose.project=${project} --format '{{json .}}'`;
    case 'docker_logs':
      return `${container}; docker logs --since 1h --tail 200 "$c" 2>&1`;
    case 'compose_restart':
      return `cd /opt/bsi/${system}/${env} && docker compose -p ${project} restart ${service}`;
    default:
      return tool;
  }
}

export function cannedOutput(tool: string, system: string, service: string): string {
  const p = `${system}-dev`;
  switch (tool) {
    case 'docker_ps':
      return [
        `{"Names":"${p}-${service}-1","State":"restarting","Status":"Restarting (1) 8 seconds ago"}`,
        `{"Names":"${p}-${service.replace('-service', '-db')}-1","State":"running","Status":"Up 2 hours (healthy)"}`,
      ].join('\n');
    case 'docker_logs':
      return [
        'exit 0',
        '10:01:12 INFO  Starting Application',
        '10:01:15 WARN  HikariPool-1 - Connection is not available, request timed out after 30000ms',
        '10:01:15 ERROR Application run failed: maximum pool size 2 reached, 14 waiting',
        '10:01:15 ERROR password=*** (masked by the platform)',
        '10:01:16 INFO  Shutting down',
      ].join('\n');
    case 'compose_restart':
      return `exit 0\n Container ${p}-${service}-1  Restarting\n Container ${p}-${service}-1  Started`;
    default:
      return 'exit 0';
  }
}
