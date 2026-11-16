<!-- SPDX-License-Identifier: AGPL-3.0-only -->
# Pranix on Oracle Cloud Always Free (D66)

One Ampere A1 server runs everything: Caddy (HTTPS) → Pranix, plus an optional private local
model. Cost: nothing. DuckDNS gives the name, Let's Encrypt the certificate, Oracle the server.

```
Internet ──443──▶ Caddy ──▶ pranix:8000 (app + API + engine)
                               └──▶ llm:8080 (optional, internal only, never published)
```

**Stay inside the free limits, always:** one VM.Standard.A1.Flex with **2 OCPUs and 12 GB**, created in
your **home region**. Never go above that, even during the trial.

## 1. Create the server (Oracle console)

1. **Compute → Instances → Create instance.**
2. **Image:** Canonical Ubuntu 24.04. **Shape:** Ampere → `VM.Standard.A1.Flex`, **2 OCPUs, 12 GB**.
3. **Networking:** create a new VCN with a public subnet, and assign a public IPv4 address.
4. **SSH keys:** upload your public key, or download the generated private key and keep it safe.
5. **Boot volume:** the default 50 GB is enough.
6. "Out of host capacity" is a temporary shortage of free Arm servers. Try another availability domain,
   or try again later. **Don't upgrade the account** to get around it; that puts a card on it.

Write down the **public IP**.

## 2. Open ports 80 and 443 (two places)

Both firewalls must allow the traffic. Opening only the first is the most common mistake.

**a) Oracle network (console):** Networking → Virtual cloud networks → your VCN → Security →
default security list → **Add ingress rules**, with source `0.0.0.0/0`:

| Protocol | Destination port |
|---|---|
| TCP | 80 |
| TCP | 443 |
| UDP | 443 (optional; HTTP/3) |

**b) The server's own firewall.** SSH in (`ssh ubuntu@<public-ip>`) and run:
```sh
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT
sudo iptables -I INPUT 6 -m state --state NEW -p udp --dport 443 -j ACCEPT
sudo netfilter-persistent save
```

## 3. Install Docker

```sh
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker "$USER"
exit                     # log out and SSH back in, so the group change applies
docker run --rm hello-world
```

## 4. Name: DuckDNS

1. Sign in at https://www.duckdns.org and create a subdomain, e.g. `pranix`. Set its IP to the server's public IP.
2. On the server, save the subdomain and token where only you can read them:
   ```sh
   printf 'DUCKDNS_DOMAIN=pranix\nDUCKDNS_TOKEN=<your-token>\n' > ~/.duckdns && chmod 600 ~/.duckdns
   ```
3. Keep the record current (cheap insurance in case the IP ever changes):
   ```sh
   (crontab -l 2>/dev/null; echo "*/5 * * * * $HOME/Pranix/deploy/oracle/duckdns-update.sh") | crontab -
   ```

## 5. Configure and start Pranix

```sh
git clone https://github.com/iamrajharshit/Pranix.git ~/Pranix
cd ~/Pranix/deploy/oracle
cp env.example .env && chmod 600 .env
openssl rand -hex 32     # run three times: log pepper, chart-key pepper, LLM key
nano .env                # domain, peppers, optional Gemini/Groq keys, LLM_API_KEY
docker compose up -d --build
```

The first build compiles the ephemeris library, downloads the place data and builds the web app. On
2 cores it can take **20 minutes or more**; later builds reuse most layers.

**Check it:**
- Open `https://<name>.duckdns.org/readyz`; it should say `ready`. The first visit may take a few
  seconds while Caddy gets the certificate.
- Open `https://<name>.duckdns.org/` and make a chart.
- `docker compose ps` should show `pranix` as healthy.

**Library text:** `PRANIX_ENV=prod` serves only owner-approved library entries. Serving drafts on the
public site (`PRANIX_LIBRARY_ALLOW_DRAFTS=true`) is the owner's decision; see `env.example`.

## 6. Optional: the private local model

```sh
docker compose --profile llm up -d     # first start downloads the model (~5.4 GB) into a volume
docker image inspect ghcr.io/ggml-org/llama.cpp:server --format '{{.Architecture}}'   # must say arm64
docker compose logs -f llm             # wait for "server is listening"
```
If the architecture says `amd64`, or the logs show `exec format error`, build an ARM image from source
and point Compose at it:
```sh
docker build -t llama-server-arm64 --target server -f .devops/cpu.Dockerfile https://github.com/ggml-org/llama.cpp.git
echo 'LLM_IMAGE=llama-server-arm64' >> .env && docker compose --profile llm up -d
```
Quick test, from inside the private network (the model has no public port):
```sh
docker compose exec pranix python -c "import os,urllib.request as u; r=u.Request('http://llm:8080/v1/models', headers={'Authorization':'Bearer '+os.environ.get('LLM_API_KEY','')}); print(u.urlopen(r).status)"
```
It prints `200`; the key reaches the container through `.env`. The app doesn't call the model yet; the
gateway provider and benchmark come in a later change.

Expected memory: OS ~1 GB, Pranix ≤2 GB, Caddy <0.25 GB, model ~6 GB, so about 8–9 GB of 12. Check
with `docker stats --no-stream`. The model is capped at 1.5 cores with low CPU priority, so charts stay quick.

## 7. Keeping it running

- **Update:** `cd ~/Pranix && git pull && cd deploy/oracle && docker compose up -d --build && docker image prune -f`
- **Backups:** Oracle includes 5 free volume backups. After setup works, take one: Storage → Block volumes →
  Boot volumes → your volume → Create manual backup. Pranix keeps no user data on the server (guest charts
  are temporary; accounts live in Neon), so a backup only saves setup time.
- **Idle reclamation:** Oracle may reclaim an A1 server that is idle for 7 days (CPU, network **and**
  memory all under 20%). With the model loaded, memory stays well above 20% (about 2.4 GB of 12) as real
  use. Don't run "fake load" scripts; they work around Oracle's policy.
- **Fallback:** if this server is lost, the same image runs on Render's free tier (Docker, `infra/Dockerfile`,
  health check `/healthz`, same environment variables) at `<name>.onrender.com`.

## Privacy

- Caddy writes **no access logs** (see `Caddyfile`), and Pranix logs only route patterns. Don't add a `log`
  directive: URLs can contain typed place text and map coordinates.
- `.env` and `~/.duckdns` hold secrets: `chmod 600`, never commit, never paste into chats.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| Site doesn't load at all | Port 80/443 not open in **both** firewalls (step 2), or DuckDNS points at the wrong IP |
| Certificate error / Caddy logs "challenge failed" | Port 80 closed, or DNS not yet updated; wait a few minutes, then `docker compose restart caddy` |
| `/readyz` says not ready | `docker compose logs pranix`: look for `selftest.result` and `geo.missing` |
| Every visitor is rate-limited together | `PRANIX_TRUST_PROXY` isn't `true` for the pranix service |
| Email from Oracle about an idle instance | Model not running; `docker compose --profile llm up -d` |
| `exec format error` | An amd64 image on the ARM server; see step 6 |
