# Deploy by hand on one server: push to GitHub, pull on the server

No CI, no registry: the server builds the images from the code it pulled.

```
your laptop ──git push──► GitHub ──git pull──► server
                                                 nginx (already installed): HTTPS :443 + login
                                                   └─► 127.0.0.1:8088  web container ─► platform-api
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

**7. Your nginx.** `deploy/single-vm/nginx-site.conf` has two ways:
- **A. Under a path of a site you already have** (`https://your-host/bsi/`): paste its two `location`
  blocks into that site's `server { }`. Build the web image for that path (see "Under a path" below).
- **B. On its own host name** (`https://bsi.example.internal/`): a separate `server { }` with its own
  certificate.

Both keep the two lines that matter: `auth_basic` (the login) and `proxy_set_header X-User-Id $remote_user`.
Without them anyone can act as any user. Then `sudo nginx -t && sudo systemctl reload nginx`.

**Under a path** (way A): the app must know its path when it is built, because it loads `/bsi/assets/...`
and calls `/bsi/api/...`. Build with:
```bash
BSI_BASE_PATH=/bsi/ deploy/single-vm/push-images.sh <dockerhub-user> v0.1.2   # laptop
# or, building on the server: put BSI_BASE_PATH=/bsi/ in .env
```
An image built for `/bsi/` only works under `/bsi/`, and one built for `/` only works at `/`.

**8. Images.** Pick one way:

- **Built on your laptop, pulled from Docker Hub.** Use this when the server can't download Python/npm
  packages. On the laptop:
  ```bash
  docker login
  deploy/single-vm/push-images.sh <dockerhub-user> v0.1.0    # builds for linux/amd64 and pushes
  ```
  Make the 3 repositories **private** on hub.docker.com. On the server, add to `.env`:
  ```ini
  BSI_IMAGES=docker.io/<dockerhub-user>
  BSI_TAG=v0.1.0
  ```
  then:
  ```bash
  sudo docker login                          # an access token with read-only scope is enough
  sudo docker compose --profile build pull   # --profile build: pulls agent-runner too
  ```
- **Built on the server:** `sudo docker compose --profile build build agent-runner` (it builds the
  others on `up --build`).

**9. Start**
```bash
cd /opt/bsi
sudo docker compose up -d --no-build      # with images from Docker Hub; use --build if built on the server
sudo docker compose ps                  # all "healthy"
# set the platform DB password (the init script uses a dev one), then restart platform-api:
sudo docker compose exec postgres psql -U bsi_admin -d postgres \
  -c "ALTER ROLE platform PASSWORD '$(sudo grep PLATFORM_DB_PASSWORD .env | cut -d= -f2)'"
sudo docker compose restart platform-api
```
Open `https://<server>/`. The browser asks for a login.

**10. Firewall:** open 443 (and 80 for the redirect) to your users only. 8000, 8088 and 5432 are already
bound to 127.0.0.1, so only your nginx reaches them.
```bash
sudo ufw allow OpenSSH && sudo ufw allow from 10.0.0.0/8 to any port 80,443 proto tcp && sudo ufw enable
```

## Every release

With images from Docker Hub. Laptop:
```bash
git commit -am "..." && git tag v0.2.0 && git push && git push --tags
deploy/single-vm/push-images.sh <dockerhub-user> v0.2.0
```
Server (git pull still brings the compose files, nginx config and DB init scripts):
```bash
cd /opt/bsi
sudo git pull
sudo sed -i 's/^BSI_TAG=.*/BSI_TAG=v0.2.0/' .env
sudo docker compose --profile build pull
sudo docker compose up -d --no-build      # migrations run on start
sudo docker compose logs -f platform-api
```

Built on the server instead: `sudo git pull`, `sudo docker compose --profile build build agent-runner`,
`sudo docker compose up -d --build`.

Rollback: set `BSI_TAG` back to the previous tag (and `sudo git checkout <that tag>`), then pull and
`up -d --no-build`. A rollback does **not** undo database migrations, so check
`services/platform-api/src/platform_api/migrations/versions/` before you roll back.

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
- Anyone with a shell on this server can call `127.0.0.1:8088` directly and set `X-User-Id` themselves.
  Only give server logins to people who are admins anyway.
