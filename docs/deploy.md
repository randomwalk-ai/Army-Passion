# Deploying Army Passion

The whole app runs on **one server** with Docker. Caddy sits in front: it gets
a free HTTPS certificate, asks for a password, and sends `/api/*` to the
backend and everything else to the frontend.

```
Internet ──HTTPS──► Caddy (password + certificate)        ports 80, 443
                      ├── /api/*, /health → backend   (FastAPI, port 8000 inside)
                      └── everything else → frontend  (Next.js, port 3000 inside)
                                              backend → db (PostgreSQL + PostGIS)
                                                      → redis
                                                      → storage volume (documents)
```

Only Caddy can be reached from the internet. The database has no public port.

| File | What it is |
|---|---|
| `docker-compose.prod.yml` | All five services, volumes, health checks, log limits |
| `backend/Dockerfile` | The API; runs database migrations on every start |
| `frontend/Dockerfile` | The screens (Next.js standalone build) |
| `deploy/Caddyfile` | HTTPS, password, routing, security headers |
| `.env.production.example` | Every setting, explained. Copy to `.env.production` on the server |
| `deploy/backup.sh` | Database backup, keeps the last 14 |

> **There is no login yet.** The whole site is behind one shared password
> (Caddy basic auth). Real accounts and roles are still to be built. The data
> is mock data only — do not load real family data until login exists.

---

## 1. Get a server and a domain (once)

1. DigitalOcean → **Create Droplet**: Ubuntu 24.04, region **Bangalore (BLR1)**,
   **4 GB RAM** (Basic, ~$24/month). 2 GB is too small to build the frontend.
   Add your SSH key. Turn on **Backups**.
2. Buy a domain (or use a sub-domain you own) and add an **A record** pointing
   at the droplet's IP address. Wait until `ping your-domain` shows that IP.

## 2. Prepare the server (once)

SSH in (`ssh root@YOUR-IP`), then:

```bash
# Docker
curl -fsSL https://get.docker.com | sh

# Firewall: SSH and web only
ufw allow OpenSSH && ufw allow 80 && ufw allow 443/tcp && ufw allow 443/udp && ufw --force enable

# The code
git clone https://github.com/randomwalk-ai/Army-Passion.git /opt/army-passion
cd /opt/army-passion
git checkout feature/dashboard-and-cea    # or main, once merged
```

## 3. Fill in the settings (once)

```bash
cp .env.production.example .env.production
openssl rand -hex 24    # copy into POSTGRES_PASSWORD
openssl rand -hex 32    # copy into SECRET_KEY
docker run --rm caddy:2.8-alpine caddy hash-password --plaintext 'CHOOSE-A-PASSWORD' | base64 -w0
                        # copy into BASIC_AUTH_HASH
nano .env.production    # also set SITE_ADDRESS (your domain) and ACME_EMAIL
```

`.env.production` is ignored by git. Never commit it.

## 4. Start it

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --build
```

The first build takes a few minutes. Check that everything is up:

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production ps
```

`backend` and `db` should say **healthy**. Open `https://your-domain` and log
in with `BASIC_AUTH_USER` and the password you chose.

**First time only — load the mock data:**

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production exec backend python -m seed.generate
```

(It refuses to run if families already exist. `--reset` wipes everything —
never use it once real work has been entered.)

---

## Everyday

To save typing, set an alias once: `alias ap='docker compose -f docker-compose.prod.yml --env-file .env.production'`

| Task | Command (from `/opt/army-passion`) |
|---|---|
| Update to the latest code | `git pull && ap up -d --build` |
| See logs | `ap logs -f backend` (or `frontend`, `caddy`) |
| Restart one part | `ap restart backend` |
| Stop everything | `ap down` (data is kept in volumes) |
| Back up the database now | `sh deploy/backup.sh` |
| Change the site password | new hash into `.env.production`, then `ap up -d caddy` |

Database migrations run automatically every time the backend starts.

### Nightly backups

```bash
crontab -e
# add:
0 2 * * * cd /opt/army-passion && sh deploy/backup.sh >> backups/backup.log 2>&1
```

Backups land in `/opt/army-passion/backups/`. Copy them off the server now
and then (or rely on DigitalOcean's droplet backups as well).

Restore one:

```bash
gunzip -c backups/army_passion_2026-11-04_0200.sql.gz | ap exec -T db psql -U army -d army_passion
```

### Where the data lives

Docker volumes, which survive rebuilds and `ap down`:

- `db_data` — the database
- `storage` — uploaded documents (until blob storage is connected)
- `caddy_data` — the HTTPS certificate

`ap down -v` **deletes** them. Don't.

---

## Trying it on your own computer first

```bash
cp .env.production.example .env.production
# set: SITE_ADDRESS=:80  HTTP_PORT=8088  HTTPS_PORT=8443
#      ACME_EMAIL=test@example.com and the passwords as above
docker compose -p ap-test -f docker-compose.prod.yml --env-file .env.production up -d --build
# open http://localhost:8088
docker compose -p ap-test -f docker-compose.prod.yml --env-file .env.production down -v   # clean up
```

`SITE_ADDRESS=:80` means plain HTTP with no certificate — only for testing.

---

## Later

- **Login and roles** (admin, colonel, officer, volunteer) to replace the shared password.
- **Blob storage:** finish `S3Storage` in `backend/app/services/storage.py`,
  set `STORAGE_PROVIDER=s3` and the `S3_*` values, and copy the files from
  the `storage` volume to the bucket.
- **Managed database** (DigitalOcean Managed PostgreSQL supports PostGIS): put
  its address in `DATABASE_URL` and remove the `db` service.
