# Deploy by hand on one server: push to GitHub, pull on the server

No CI, no registry: the server builds the images from the code it pulled.

```
your laptop ──git push──► GitHub ──git pull──► server
                                                 nginx (already installed): HTTPS :443 + login
                                                   └─► 127.0.0.1:8088  web container ─► platform-api
                                                 docker compose: postgres, platform-api, web, agent containers
```

Sign-in is BSI's own login page: user name + password (scrypt hashes in Postgres). It returns a JWT
(signed with `BSI_JWT_SECRET`) that the web app sends as `Authorization: Bearer …`. The first admin is created on first start (`admin` / `admin` unless you set
`BSI_ADMIN_USERNAME` / `BSI_ADMIN_PASSWORD`) and must pick a new password at the first sign-in. The server's
nginx only does HTTPS.

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
sudo apt-get install -y git                   # nginx is already there
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

**3. Nothing to prepare for users and servers.** The database starts empty except for the first admin
(step 4). That admin adds everyone else on the Users page, each with a temporary password that they change
at their first sign-in. Servers are added in the web app (Servers → Add server).

**4. Secrets** (never in git)
```bash
cd /opt/bsi
sudo tee .env >/dev/null <<EOF
COMPOSE_FILE=docker-compose.yml:docker-compose.agents.yml:deploy/single-vm/compose.yml
POSTGRES_ADMIN_PASSWORD=$(openssl rand -hex 24)
PLATFORM_DB_PASSWORD=$(openssl rand -hex 24)
ANTHROPIC_API_KEY=sk-ant-api03-...
BSI_ADMIN_USERNAME=admin            # the first admin (default admin)
BSI_ADMIN_PASSWORD=$(openssl rand -hex 12)   # its first password (default admin); changed at the first sign-in
BSI_JWT_SECRET=$(openssl rand -hex 32)       # signs sign-in tokens; changing it signs everyone out
EOF
sudo chmod 600 .env
```

**5. SSH key for your servers.** The platform logs in to them with this key.
```bash
sudo mkdir -p -m 700 /etc/bsi/ssh
sudo ssh-keygen -t ed25519 -N "" -C BSI -f /etc/bsi/ssh/id_ed25519
```
The web app shows this public key when you add a server, and you put it in that server's
`~/.ssh/authorized_keys`. It also fetches the server's host key, shows its fingerprint for you to compare, and
pins it in the database. You don't edit a `known_hosts` file.
(platform-api runs as root here because it uses the Docker socket, so root-owned files are fine.)

**6. Logins.** Nothing to set up on the server. After the first start, open BSI, sign in with
`BSI_ADMIN_USERNAME` / `BSI_ADMIN_PASSWORD` (`grep BSI_ADMIN .env`), pick your own password, then add users
on the Users page. Forgot a password? An admin clicks "Reset password" for that user. Changing
`BSI_ADMIN_PASSWORD` later does nothing once the admin has a password.

**7. Your nginx.** `deploy/single-vm/nginx-site.conf` has two ways:
- **A. Under a path of a site you already have** (`https://your-host/bsi/`): paste its two `location`
  blocks into that site's `server { }`. Build the web image for that path (see "Under a path" below).
- **B. On its own host name** (`https://bsi.example.internal/`): a separate `server { }` with its own
  certificate.

Keep it HTTPS: the sign-in token travels in every request. Then `sudo nginx -t && sudo systemctl reload nginx`.
Moving from the old basic-auth setup: remove the `auth_basic`, `auth_basic_user_file`, `X-User-Id` lines
and **`proxy_set_header Authorization ""`**: that last one deletes the sign-in token, so every request after
signing in would be "not signed in".

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
- **Behind a company proxy:** set `BSI_PROXY=http://<proxy>:<port>` in `.env`. Builds on the server and
  agent containers then use it.
  For the app under `/bsi/`, also put `BSI_BASE_PATH=/bsi/` in `.env`.
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

- **Passwords, not SSO**: no 2FA. 5 wrong passwords lock a user name for a minute. Keep 443 inside the
  company network or VPN.
- **AI runs next to the SSH key.** Agent containers run on this server, and platform-api uses the
  Docker socket, which gives root on this server. Agent containers only call the server tools and are
  locked down. The two-VM setup in `deploy/README.md` removes this risk.
- **The Anthropic API key is inside agent containers** (no model proxy yet).
- Anyone with root on this server can read the database and the `.env`. Only give server logins to
  people who are admins anyway.
