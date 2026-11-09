import type { AccessChange, RoleChange, User, Chat, Decision, Project, Resource, Server, Skill, Step, SystemInfo } from './types';

// Static mock data. Replace with real backend calls later.

export const systems: SystemInfo[] = [
  { id: 'superapp', name: 'superapp', color: '#6B4EE6' },
  { id: 'tiffany', name: 'tiffany', color: '#D4790F' },
];

const READ = ['docker_inspect', 'docker_logs', 'docker_ps', 'docker_stats', 'file_read', 'folder_list'];
const WRITE = ['compose_restart', 'compose_run', 'docker_run', 'file_write'];

export const servers: Server[] = [
  { name: 'dev-docker-01', host: '10.20.1.11', runtime: 'Docker', runtimeVersion: '27', env: 'dev', memoryUsedGb: 20.5, memoryTotalGb: 32, usedFor: 'superapp dev · 9 containers', allowedTools: [...READ, ...WRITE] },
  { name: 'dev-docker-02', host: '10.20.1.12', runtime: 'Docker', runtimeVersion: '27', env: 'dev', memoryUsedGb: 9.6, memoryTotalGb: 32, usedFor: 'tiffany dev · 5 containers', allowedTools: [...READ, ...WRITE, 'ssh_exec'] },
  { name: 'stage-docker-01', host: '10.25.1.21', runtime: 'Docker', runtimeVersion: '27', env: 'stage', memoryUsedGb: 21, memoryTotalGb: 64, usedFor: 'superapp stage · 7 containers', allowedTools: [...READ, 'compose_restart'] },
  { name: 'prod-docker-01', host: '10.30.1.31', runtime: 'Docker', runtimeVersion: '27', env: 'prod', memoryUsedGb: 38, memoryTotalGb: 64, usedFor: 'superapp prod · 7 containers', allowedTools: ['docker_logs', 'docker_ps', 'docker_stats'] },
];

export const users: User[] = [
  { id: 'sarinzha', name: 'Sarinzha K.', roles: ['developer'] },
  { id: 'aibek', name: 'Aibek T.', roles: ['devops'] },
  { id: 'timur', name: 'Timur S.', roles: ['developer', 'devops'] },
  { id: 'dana', name: 'Dana M.', roles: ['admin'] },
];

export const roleChanges: RoleChange[] = [
  { user: 'timur', added: ['devops'], removed: [], by: 'Dana M.', reason: 'on call for releases this month', at: '2026-11-02T08:00:00Z' },
];

export const accessChanges: AccessChange[] = [
  { server: 'dev-docker-02', added: ['ssh_exec'], removed: [], by: 'Sarinzha K.', reason: 'tiffany dev is a sandbox, rebuilt from git when needed', at: '2026-11-06T09:12:00Z' },
];

export const resources: Record<string, Resource[]> = {
  superapp: [
    { name: 'orders-service', kind: 'app', image: 'superapp/orders-service:0.1.0', server: 'dev-docker-01', usage: '0.2 CPU · 410 MB', definedIn: 'compose.dev.yml:12', adr: 'ADR-0007', status: 'healthy' },
    { name: 'orders-db', kind: 'db', image: 'postgres:16-alpine', server: 'dev-docker-01', usage: '90 MB · disk 120 MB', definedIn: 'compose.dev.yml:26', adr: 'ADR-0007', status: 'healthy' },
    { name: 'auth-service', kind: 'app', image: 'superapp/auth-service:1.5.0', server: 'dev-docker-01', usage: '0.3 CPU · 520 MB', definedIn: 'compose.dev.yml:4', adr: 'ADR-0003', status: 'healthy' },
    { name: 'kafka', kind: 'broker', image: 'apache/kafka:3.8.1', server: 'dev-docker-01', usage: '1.1 GB · 5 topics', definedIn: 'compose.dev.yml:9', adr: 'ADR-0004', status: 'healthy' },
    { name: 'notification-service', kind: 'app', image: 'superapp/notification-service:0.2.0', server: 'dev-docker-01', usage: '0.1 CPU · 380 MB', definedIn: 'compose.dev.yml:40', adr: 'ADR-0005', status: 'healthy' },
    { name: 'traefik', kind: 'platform', image: 'traefik:v3.2', server: 'dev-docker-01', usage: '40 MB', definedIn: 'platform default', adr: 'routing + TLS', status: 'healthy' },
  ],
  tiffany: [
    { name: 'catalog-service', kind: 'app', image: 'tiffany/catalog-service:2.0.1', server: 'dev-docker-02', usage: '0.2 CPU · 450 MB', definedIn: 'compose.dev.yml:3', adr: 'ADR-0002', status: 'healthy' },
    { name: 'catalog-db', kind: 'db', image: 'postgres:16-alpine', server: 'dev-docker-02', usage: '150 MB', definedIn: 'compose.dev.yml:18', adr: 'ADR-0002', status: 'healthy' },
  ],
};

const doneSteps = (texts: string[]): Step[] => texts.map((text, i) => ({ id: 's' + i, text, status: 'done' }));

const me = 'agent · requested by Sarinzha K.';

/** The system-wide decision log, newest first. In the real platform: <system>/platform/docs/adr/*.md */
export const history: Decision[] = [
  {
    id: 'ADR-0009', systemId: 'superapp', kind: 'feature', title: 'Customers can cancel NEW orders',
    decision: 'CancelOrder use case and POST /orders/{id}/cancel. Only orders in status NEW can be cancelled.',
    why: 'Support gets ~30 cancel requests a day that are handled by hand.',
    rejected: 'cancelling paid orders (needs refunds, separate decision).',
    skills: ['spring-service'], projects: ['orders-service'], chatId: 'c-cancel',
    version: '2026.11.7-3', author: me, createdAt: '2026-11-07T16:40:00',
  },
  {
    id: 'ADR-0008', systemId: 'superapp', kind: 'change', title: 'notification-service listens to order status',
    decision: 'New listener for order-status-changed; SMS template per status.',
    why: 'Customers asked to be told when an order ships.',
    rejected: 'orders-service sending SMS itself (would duplicate the SMS provider client).',
    skills: ['spring-service', 'add-kafka'], projects: ['notification-service'], chatId: 'c-orders',
    version: '2026.11.7-2', author: me, createdAt: '2026-11-07T14:22:00',
  },
  {
    id: 'ADR-0007', systemId: 'superapp', kind: 'feature', title: 'New orders-service with its own database',
    decision: 'New project orders-service, new PostgreSQL orders-db; reuse kafka with a new topic order-status-changed.',
    why: 'Orders did not exist in superapp. Each service owns its data; a broker already runs in the system.',
    rejected: 'tables in auth-db, a second Kafka broker.',
    skills: ['architecture-decisions', 'add-postgres', 'deploy-compose'], projects: ['orders-service'], chatId: 'c-orders',
    version: '2026.11.7-1', author: me, createdAt: '2026-11-07T14:18:00',
  },
  {
    id: 'ADR-0006', systemId: 'superapp', kind: 'infrastructure', title: 'Deploy superapp dev with Docker Compose',
    decision: 'One compose file per environment, applied by the platform.',
    why: 'v1 of the platform supports Docker servers only; Compose keeps the whole environment in one readable file.',
    rejected: 'plain docker run commands (not one readable file).',
    skills: ['deploy-compose', 'readable-infra'], projects: ['auth-service', 'notification-service'],
    version: '2026.11.5-1', author: me, createdAt: '2026-11-05T11:02:00',
  },
  {
    id: 'ADR-0005', systemId: 'superapp', kind: 'feature', title: 'OTP login with a new notification-service',
    decision: 'auth-service issues and checks codes; new notification-service sends SMS from topic otp-requested.',
    why: 'Login by SMS code was requested; superapp had no SMS sender.',
    rejected: 'using sms-gateway from tiffany (different owners, different SLA).',
    skills: ['architecture-decisions', 'spring-service', 'add-kafka'], projects: ['auth-service', 'notification-service'], chatId: 'c-otp',
    version: '2026.11.4-2', author: me, createdAt: '2026-11-04T17:30:00',
  },
  {
    id: 'ADR-0004', systemId: 'superapp', kind: 'infrastructure', title: 'One Kafka broker for superapp dev',
    decision: 'Single-node Kafka 3.8 in KRaft mode, dev only.',
    why: 'Dev needs events, not high availability.',
    rejected: 'the shared prod cluster for dev traffic.',
    skills: ['add-kafka'], projects: [],
    version: '2026.11.4-1', author: me, createdAt: '2026-11-04T16:55:00',
  },
  {
    id: 'ADR-0002', systemId: 'tiffany', kind: 'feature', title: 'Catalog with its own database',
    decision: 'catalog-service and catalog-db on dev-docker-02.',
    why: 'First service of the tiffany system.',
    rejected: 'none considered.',
    skills: ['architecture-decisions', 'add-postgres'], projects: ['catalog-service'],
    version: '2026.11.2-1', author: me, createdAt: '2026-11-02T10:00:00',
  },
];

const ordersCompose = [
  '# superapp · dev · written by the agent, applied by the platform',
  '# Why each service exists: docs/adr/',
  'services:',
  '  auth-service:                    # ADR-0003',
  '    image: registry/superapp/auth-service:1.5.0',
  '    env_file: [env/auth-service.env]',
  '    depends_on: [auth-db, kafka]',
  '',
  '  kafka:                           # ADR-0004',
  '    image: apache/kafka:3.8.1',
  '',
  '  orders-service:                  # ADR-0007 (new)',
  '    image: registry/superapp/orders-service:0.1.0',
  '    environment:',
  '      DB_URL: jdbc:postgresql://orders-db:5432/orders',
  '      KAFKA_BOOTSTRAP: kafka:9092',
  '    env_file: [env/orders-service.env]   # secrets from Vault, not in git',
  '    depends_on:',
  '      orders-db: { condition: service_healthy }',
  '    healthcheck:',
  '      test: ["CMD", "curl", "-f", "http://localhost:8080/actuator/health"]',
  '    deploy:',
  '      resources:',
  '        limits: { cpus: "1", memory: 768M }',
  '',
  '  orders-db:                       # ADR-0007 (new)',
  '    image: postgres:16-alpine',
  '    env_file: [env/orders-db.env]',
  '    volumes: [orders-db-data:/var/lib/postgresql/data]',
  '    healthcheck:',
  '      test: ["CMD", "pg_isready", "-U", "orders"]',
  '',
  'volumes:',
  '  orders-db-data:',
].join('\n');

const ordersAdrFile = [
  '# ADR-0007: Storage and events for orders-service',
  '',
  'Status: accepted by the agent',
  '',
  '## Decision',
  '- New PostgreSQL 16 container orders-db',
  '- Reuse the existing kafka, new topic order-status-changed',
  '- Docker Compose on dev-docker-01',
  '',
  '## Rejected',
  '- Tables inside auth-db: two services sharing one database',
  '- A second Kafka broker: one already runs in this system',
].join('\n');

export function initialProjects(): Project[] {
  return [
    {
      id: 'orders-service',
      systemId: 'superapp',
      name: 'orders-service',
      status: 'running',
      description: 'Orders and order status; sends status changes to Kafka.',
      repo: 'superapp/orders-service',
      files: [
        { path: 'infra/compose.dev.yml', status: 'modified', content: ordersCompose, addedLines: [12, 34] },
        { path: 'docs/adr/0007-orders-storage.md', status: 'added', content: ordersAdrFile },
      ],
      chatIds: ['c-orders', 'c-cancel'],
    },
    {
      id: 'auth-service',
      systemId: 'superapp',
      name: 'auth-service',
      status: 'running',
      description: 'Login with OTP, JWT tokens.',
      repo: 'superapp/auth-service',
      files: [],
      chatIds: ['c-otp'],
    },
    {
      id: 'notification-service',
      systemId: 'superapp',
      name: 'notification-service',
      status: 'running',
      description: 'Sends SMS for OTP codes and order updates.',
      repo: 'superapp/notification-service',
      files: [],
      chatIds: ['c-otp', 'c-orders'],
    },
    {
      id: 'catalog-service',
      systemId: 'tiffany',
      name: 'catalog-service',
      status: 'running',
      description: 'Product catalog.',
      repo: 'tiffany/catalog-service',
      files: [],
      chatIds: [],
    },
  ];
}

export function initialChats(): Chat[] {
  return [
    {
      id: 'c-orders',
      systemId: 'superapp',
      title: 'Orders with SMS on status change',
      status: 'running',
      projectIds: ['orders-service', 'notification-service'],
      messages: [
        { id: 'm1', role: 'user', text: "Create an orders service: customers place orders, and when an order's status changes we send them an SMS." },
        {
          id: 'm2',
          role: 'agent',
          text: "Here's what I decided. Everything is written as files you can read, and recorded in ADR-0007.",
          skills: ['architecture-decisions', 'spring-service', 'add-postgres', 'deploy-compose'],
          plan: [
            { action: 'create', name: 'orders-service', detail: 'Spring Boot, hexagonal rules' },
            { action: 'create', name: 'orders-db', detail: 'PostgreSQL 16: each service owns its data' },
            { action: 'reuse', name: 'notification-service', detail: 'new listener for order-status-changed' },
            { action: 'deploy', name: 'Docker Compose', detail: 'dev-docker-01, 9.8 GB free' },
          ],
          steps: doneSteps([
            'Wrote orders-service (14 files, tests green)',
            'Updated infra/compose.dev.yml (+23 lines)',
            'Validated: format, limits, health checks, no scripts',
            'Platform applied: docker compose up -d',
            'orders-service healthy',
          ]),
        },
      ],
    },
    {
      id: 'c-cancel',
      systemId: 'superapp',
      title: 'Cancel an order',
      status: 'running',
      projectIds: ['orders-service'],
      messages: [
        { id: 'm3', role: 'user', text: 'Customers should be able to cancel an order while it is still NEW.' },
        {
          id: 'm4',
          role: 'agent',
          text: 'Found it in orders-service. Code change only: a CancelOrder use case and POST /orders/{id}/cancel.',
          skills: ['spring-service'],
          steps: doneSteps(['Changed orders-service', 'mvn verify green', 'Platform redeployed orders-service']),
        },
      ],
    },
    {
      id: 'c-otp',
      systemId: 'superapp',
      title: 'OTP login',
      status: 'running',
      projectIds: ['auth-service', 'notification-service'],
      messages: [
        { id: 'o1', role: 'user', text: 'Add OTP login: users sign in with a code from SMS.' },
        {
          id: 'o2',
          role: 'agent',
          text: 'Done: auth-service has /otp/request and /otp/verify; I created notification-service to send the SMS.',
          steps: doneSteps(['Changed auth-service', 'Created notification-service', 'Deployed to dev']),
        },
      ],
    },
  ];
}

export const skills: Skill[] = [
  {
    id: 'architecture-decisions', version: 'v4', owner: 'platform team',
    description: 'What to create, what to reuse, write an ADR', usage: 'Loaded in every chat',
    body: [
      '1. Read docs/system.yaml and docs/adr/ of this system first.',
      '2. Reuse before you create: if a running broker or cache fits, use it.',
      '3. Each service owns its own database. Never share tables.',
      '4. Pick the runtime from the servers assigned to the environment.',
      '5. If less than 2 GB stays free on the server, stop and tell the developer.',
      '6. Write docs/adr/NNNN-<title>.md: context, decision, rejected options.',
    ].join('\n'),
  },
  {
    id: 'spring-service', version: 'v7', owner: 'backend guild',
    description: 'Spring Boot, DDD + hexagonal, use cases', usage: 'Used in 23 chats',
    body: [
      'Start from template spring-boot-service v3. Do not change its layout.',
      'domain/        entities, value objects. No Spring, no JPA.',
      'application/   one class per use case, method execute()',
      'adapter/in     REST controllers, Kafka listeners',
      'adapter/out    JPA, Kafka producers, HTTP clients',
      'Flyway migrations must be backward compatible.',
      'Done = mvn verify is green, including ArchUnit.',
    ].join('\n'),
  },
  {
    id: 'readable-infra', version: 'v3', owner: 'platform team',
    description: 'Only readable formats, no scripts', usage: 'Enforced by the platform validator',
    body: [
      'Allowed (v1): Docker Compose files only. Kubernetes and Swarm come later.',
      'Never: deploy shell scripts, generated YAML, secrets in files, image tag latest.',
      'Every service has an ADR comment, memory/CPU limits and a health check.',
      'You never apply files yourself. The platform validates and applies.',
    ].join('\n'),
  },
  {
    id: 'deploy-compose', version: 'v3', owner: 'platform team',
    description: 'Docker servers', usage: 'superapp dev, tiffany dev',
    body: [
      'One file per environment: infra/compose.<env>.yml.',
      'Use the network the platform created: <system>-<env>.',
      'Public HTTP goes through Traefik labels, never published ports.',
      'Run docker compose config and fix every warning before finishing.',
    ].join('\n'),
  },
  {
    id: 'add-postgres', version: 'v2', owner: 'platform team',
    description: 'When and how to add a database', usage: 'Created 9 databases',
    body: [
      'One database container per service: <service>-db.',
      'Image postgres:16-alpine, named volume, health check pg_isready.',
      'Credential names in env/*.env.example; values come from Vault.',
      'Never change the major version of a running database.',
    ].join('\n'),
  },
];
