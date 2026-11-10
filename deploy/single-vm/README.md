# Deploy by hand on one server: push to GitHub, pull on the server

No CI, no registry: the server builds the images from the code it pulled.

```
your laptop ──git push──► GitHub ──git pull──► server
                                                 nginx (already installed): HTTPS :443 + login
                                                   └─► 127.0.0.1:8080  web container ─► platform-api
                                                 docker compose: postgres, platform-api, web, agent containers
```

Login is nginx basic auth in the server's own nginx (stopgap until company SSO). platform-api runs in dev
mode behind it, and nginx sets `X-User-Id` from the login, so nobody can act as another user.

## Once: on your laptop

```bash
# create an EMPTY private repo on github.com first (no README), then:
git remote add origin git@github.com:<you>/bsi.git
git push -u origin main
```

## Once: on the server (Ubuntu 22.04/24.04)

**1. Docker and git**
```bash
curl -fsSL https://get.docker.com | sudo sh
sudo apt-get install -y git apache2-utils     # apache2-utils: htpasswd. nginx is already there.
```

**2. Read-only access to the GitHub repo (deploy key)**
```bash
sudo ssh-keygen -t ed25519 -N "" -f /root/.ssh/github_bsi
sudo cat /root/.ssh/github_bsi.pub
# GitHub -> repo -> Settings -> Deploy keys -> Add (leave "Allow write access" OFF)
sudo tee -a /root/.ssh/config <<'EOF'
Host github.com
  IdentityFile /root/.ssh/github_bsi
EOF
sudo git clone git@github.com:<you>/bsi.git /opt/bsi
```

**3. Users and servers, before the first start.** `config/users.yaml` and `config/servers.yaml`
fill an empty database **once**. Afterwards change them in the web app. Put your real people and
servers there, commit, push, and `git pull` on the server.

**4. Secrets** (never in git)
```bash
cd /opt/bsi
sudo tee .env >/dev/null <<EOF
COMPOSE_FILE=docker-compose.yml:docker-compose.agents.yml:deploy/single-vm/compose.yml
POSTGRES_ADMIN_PASSWORD=$(openssl rand -hex 24)
PLATFORM_DB_PASSWORD=$(openssl rand -hex 24)
ANTHROPIC_API_KEY=sk-ant-...
EOF
sudo chmod 600 .env
```

**5. SSH key for your servers.** The platform logs in to them with this key.
```bash
sudo mkdir -p -m 700 /etc/bsi/ssh
sudo ssh-keygen -t ed25519 -N "" -C BSI -f /etc/bsi/ssh/id_ed25519
# on each target server: add id_ed25519.pub to ~/.ssh/authorized_keys of the user the platform logs in as
sudo sh -c 'ssh-keyscan -t ed25519 10.20.1.11 10.20.1.12 > /etc/bsi/ssh/known_hosts'   # your servers
```
(platform-api runs as root here because it uses the Docker socket, so root-owned files are fine.)

**6. Logins.** The user name must be the user's id in `config/users.yaml`.
```bash
sudo htpasswd -cB /etc/nginx/bsi.htpasswd sarinzha     # -c only for the first user
sudo htpasswd -B  /etc/nginx/bsi.htpasswd aibek
sudo chown root:www-data /etc/nginx/bsi.htpasswd && sudo chmod 640 /etc/nginx/bsi.htpasswd
```

**7. Your nginx.** Edit `server_name` and the certificate paths in `deploy/single-vm/nginx-site.conf`
(use the certificate your nginx already has, or one from your company CA), then:
```bash
sudo cp deploy/single-vm/nginx-site.conf /etc/nginx/sites-available/bsi
sudo ln -s /etc/nginx/sites-available/bsi /etc/nginx/sites-enabled/bsi
sudo nginx -t && sudo systemctl reload nginx
```
If another site on this nginx already listens on 80/443 with the same `server_name`, change the name.

**8. Start**
```bash
cd /opt/bsi
sudo docker compose --profile build build agent-runner
sudo docker compose up -d --build
sudo docker compose ps                  # all "healthy"
# set the platform DB password (the init script uses a dev one), then restart platform-api:
sudo docker compose exec postgres psql -U bsi_admin -d postgres \
  -c "ALTER ROLE platform PASSWORD '$(sudo grep PLATFORM_DB_PASSWORD .env | cut -d= -f2)'"
sudo docker compose restart platform-api
```
Open `https://<server>/`. The browser asks for a login.

**9. Firewall:** open 443 (and 80 for the redirect) to your users only. 8000, 8080 and 5432 are already
bound to 127.0.0.1, so only your nginx reaches them.
```bash
sudo ufw allow OpenSSH && sudo ufw allow from 10.0.0.0/8 to any port 80,443 proto tcp && sudo ufw enable
```

## Every release

Laptop:
```bash
git push
git tag v0.1.0 && git push --tags      # optional, makes rollback easy
```
Server:
```bash
cd /opt/bsi
sudo git pull
sudo docker compose --profile build build agent-runner
sudo docker compose up -d --build       # migrations run on start
sudo docker compose logs -f platform-api
```

Rollback: `sudo git checkout v0.0.9` and the same two build commands. A rollback does **not** undo
database migrations, so check `services/platform-api/src/platform_api/migrations/versions/` before you roll back.

## Backups (cron, nightly)

```bash
# /etc/cron.d/bsi-backup
0 3 * * * root cd /opt/bsi && docker compose exec -T postgres pg_dump -U bsi_admin -Fc platform > /var/backups/bsi-$(date +\%F).dump && find /var/backups -name 'bsi-*.dump' -mtime +14 -delete
```
Restore: `docker compose exec -T postgres pg_restore -U bsi_admin -d platform --clean < file.dump`.

## Limits of this setup

- **Basic auth is not SSO**: shared passwords, no 2FA. Keep 443 inside the company network or VPN.
- **AI runs next to the SSH key.** Agent containers run on this server, and platform-api uses the
  Docker socket, which gives root on this server. Agent containers only call the server tools and are
  locked down. The two-VM setup in `deploy/README.md` removes this risk.
- **The Anthropic API key is inside agent containers** (no model proxy yet).
- The "Viewing as" switcher still shows in the web app, but it does nothing: nginx decides who you are.
- Anyone with a shell on this server can call `127.0.0.1:8080` directly and set `X-User-Id` themselves.
  Only give server logins to people who are admins anyway.
