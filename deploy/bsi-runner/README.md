# bsi-runner VM: where agent containers run

Nothing of superAI is installed here except Docker. platform-api (on bsi-app) starts one container per
agent run through this machine's Docker API. The containers hold only their run token.

## 1. Docker API over mutual TLS (only platform-api may use it)

Follow https://docs.docker.com/engine/security/protect-access/ : create a CA, a server certificate for
this host and a client certificate for platform-api. `/etc/docker/daemon.json`:

```json
{
  "hosts": ["unix:///var/run/docker.sock", "tcp://0.0.0.0:2376"],
  "tlsverify": true,
  "tlscacert": "/etc/docker/tls/ca.pem",
  "tlscert": "/etc/docker/tls/server-cert.pem",
  "tlskey": "/etc/docker/tls/server-key.pem"
}
```

Put `ca.pem`, `cert.pem`, `key.pem` (the client side) on bsi-app in `/etc/superai/docker-tls/`.
Firewall: port 2376 open for bsi-app's IP only.

## 2. The network agent containers use

```bash
docker network create --driver bridge superai-agent-sandbox
```

Not `--internal`: the containers must reach bsi-app, which is another machine. The firewall below
does the limiting instead.

## 3. Firewall: agent containers may reach bsi-app:8000 and :8100, nothing else

Docker sends container traffic through the `DOCKER-USER` chain. With `BSI_APP_IP` set to bsi-app's
private address and `NET` to the subnet of `superai-agent-sandbox` (`docker network inspect`):

```bash
iptables -I DOCKER-USER -s "$NET" -j DROP                                         # everything else
iptables -I DOCKER-USER -s "$NET" -d "$BSI_APP_IP" -p tcp --dport 8100 -j ACCEPT  # server-tools /mcp
iptables -I DOCKER-USER -s "$NET" -d "$BSI_APP_IP" -p tcp --dport 8000 -j ACCEPT  # platform-api
iptables -I DOCKER-USER -s "$NET" -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
```

(`-I` inserts at the top, so the last line runs first.) No internet, no target servers, no other
company hosts. Make the rules persistent (`iptables-persistent` or your config management).

Check from a test container:

```bash
docker run --rm --network superai-agent-sandbox curlimages/curl:8.10.1 -m 5 http://$BSI_APP_IP:8100/health  # works
docker run --rm --network superai-agent-sandbox curlimages/curl:8.10.1 -m 5 https://example.com             # times out
```

## 4. Optional, stronger isolation: gVisor

Install `runsc` (https://gvisor.dev/docs/user_guide/install/) and register it as a Docker runtime.
Then platform-api's DockerSandbox can pass `runtime="runsc"` (one line).

## 5. Pre-pull the agent image on every release

```bash
docker pull registry/superai/agent-runner:$BSI_VERSION
```
