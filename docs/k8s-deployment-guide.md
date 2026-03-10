# CivPulse K8s Deployment Guide

How to deploy a new microservice alongside voter-api on the CivPulse k3s cluster.

This guide covers what already exists (reference only) and what you need to create to deploy your app.

---

## 1. Cluster Overview

| Property | Value |
|---|---|
| **Distribution** | k3s (lightweight Kubernetes) |
| **Node** | `thor` — single node, 40 CPU cores, ~200 GB RAM |
| **Storage class** | `local-path` (default, Rancher provisioner) |
| **HA** | None — single-node cluster, no multi-node scheduling concerns |
| **GitOps** | ArgoCD watches GitHub repos and auto-syncs manifests |
| **Container registry** | GHCR (`ghcr.io/civicpulse/<repo>`) |

---

## 2. Namespace Layout

These namespaces already exist. Do **not** recreate them.

| Namespace | Purpose | Label |
|---|---|---|
| `civpulse-prod` | Production workloads | `env=production` |
| `civpulse-dev` | Development workloads | `env=development` |
| `civpulse-gis` | Shared GIS resources | `env=shared` |
| `civpulse-infra` | Platform services (Traefik, cloudflared, observability) | — |
| `argocd` | ArgoCD GitOps controller | — |

Your app deploys into `civpulse-dev` (dev) and `civpulse-prod` (prod). No new namespaces needed.

---

## 3. Traffic Flow

```
Internet → Cloudflare DNS → Cloudflare Tunnel → cloudflared pods → Traefik → IngressRoute → your Service
```

**Key points:**

- **Cloudflare Tunnel** terminates TLS at the edge — there is **no TLS in-cluster**
- **Traefik** is the sole ingress controller, using CRD-based `IngressRoute` (not standard `Ingress`)
- **cloudflared** runs 2 replicas in `civpulse-infra`, connects to Cloudflare via a tunnel token secret
- Traefik entrypoint is `web` (port 80) — no `websecure` needed
- Traefik's `kubernetesCRD` provider is enabled with `allowCrossNamespace: true`, and `kubernetesIngress` is disabled

**What you need for your app:**

1. A **Cloudflare DNS CNAME** record pointing your hostname to the existing tunnel
2. A **Traefik IngressRoute** in your app's namespace

---

## 4. Database

- **External PostgreSQL 15+ with PostGIS 3.x** (not running in-cluster)
- Accessible at: `postgresql.civpulse-infra.svc.cluster.local:5432`
- Backed by a headless Service + static Endpoints pointing to Tailscale IP `100.67.17.69`
- Each app gets its **own database** on the shared PostgreSQL instance
- Connection string format:
  ```
  postgresql+asyncpg://<user>:<password>@postgresql.civpulse-infra.svc.cluster.local:5432/<your_db>
  ```
- **Action required**: Request a new database + credentials from the infra admin before deploying

---

## 5. Identity

- **Zitadel** (OIDC/OAuth2 identity platform) at `auth.civpulse.org`
- Available for apps that want centralized auth
- voter-api currently uses its own JWT auth — Zitadel adoption is optional

---

## 6. Observability

All observability infrastructure already exists. Your app benefits automatically from some of it.

| Layer | Stack | Notes |
|---|---|---|
| **Logs** | Grafana Alloy (DaemonSet) → Loki | Pod logs collected automatically — no setup needed |
| **Traces** | OTLP → Alloy → Tempo | Send traces to `alloy.civpulse-infra.svc.cluster.local:4317` (gRPC) or `:4318` (HTTP) |
| **Metrics** | VictoriaMetrics | Request a scrape config addition for your app's metrics endpoint |
| **Dashboards** | Grafana | Internal access only (Tailscale) |
| **Container logs** | Dozzle | Internal access only (Tailscale) |

---

## 7. ArgoCD GitOps

ArgoCD watches GitHub repos and auto-syncs Kubernetes manifests to the cluster.

- Each app needs an `argocd/` directory in its repo with ArgoCD `Application` manifests
- Sync policy: `automated` with `prune: true` and `selfHeal: true`
- `CreateNamespace=false` — namespaces must already exist before the first sync
- ArgoCD lives in the `argocd` namespace

Currently deployed ArgoCD Applications:
- `voter-api-dev` (Synced/Healthy)
- `voter-api-prod` (Synced/Healthy)
- `contact-api` (Synced/Healthy)

---

## 8. What You Need to Create

Your repo needs the following files. Each section includes a copyable YAML template with `<PLACEHOLDER>` markers.

### a. Dockerfile

Multi-stage build: builder stage installs dependencies, runtime stage runs lean.

```dockerfile
# Stage 1: Builder
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

# Install dependencies first (layer caching)
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-install-project --no-dev

# Copy source and install project
COPY README.md ./
COPY src/ src/
# Include Alembic if your app uses database migrations:
# COPY alembic/ alembic/
# COPY alembic.ini ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable

# Stage 2: Runtime
FROM python:3.13-slim-bookworm

# Install system libraries your app needs (remove if not needed):
# RUN apt-get update && apt-get install -y --no-install-recommends \
#     libgdal-dev libgeos-dev libproj-dev \
#     && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy only the virtual environment from builder
COPY --from=builder /app/.venv /app/.venv
# Include Alembic if using migrations:
# COPY --from=builder /app/alembic /app/alembic
# COPY --from=builder /app/alembic.ini /app/alembic.ini

ARG GIT_COMMIT=unknown
ENV PATH="/app/.venv/bin:$PATH" \
    GIT_COMMIT=${GIT_COMMIT}

EXPOSE 8000

CMD ["uvicorn", "<APP_MODULE>:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
```

**Placeholders:**
- `<APP_MODULE>` — your app's Python module path (e.g., `my_app.main`)

### b. `.github/workflows/build-push.yaml`

CI workflow that builds, pushes to GHCR, and updates the image tag in deployment manifests.

```yaml
name: Build and push Docker image

on:
  push:
    branches: [main]
    paths-ignore:
      - 'k8s/**'  # Avoid infinite loops from image tag updates

concurrency:
  group: deploy-${{ github.ref }}
  cancel-in-progress: false

env:
  REGISTRY: ghcr.io
  IMAGE_NAME: ${{ github.repository }}

jobs:
  build-push:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write

    steps:
      - uses: actions/checkout@v4

      - name: Log in to GHCR
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Extract metadata
        id: meta
        uses: docker/metadata-action@v5
        with:
          images: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}
          tags: |
            type=sha,prefix=sha-
            type=raw,value=latest

      - name: Build and push
        uses: docker/build-push-action@v6
        with:
          context: .
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
          build-args: |
            GIT_COMMIT=${{ github.sha }}

  deploy:
    needs: build-push
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@v4
        with:
          token: ${{ secrets.GITHUB_TOKEN }}
          fetch-depth: 0

      - name: Update image tag in manifests
        run: |
          SHORT_SHA=$(echo "${{ github.sha }}" | cut -c1-7)
          REPO=$(echo "${{ github.repository }}" | tr '[:upper:]' '[:lower:]')
          IMAGE="ghcr.io/${REPO}:sha-${SHORT_SHA}"
          sed -i "s|image: ghcr.io/${REPO}:.*|image: ${IMAGE}|g" k8s/apps/<APP_NAME>-dev/deployment.yaml
          sed -i "s|image: ghcr.io/${REPO}:.*|image: ${IMAGE}|g" k8s/apps/<APP_NAME>-prod/deployment.yaml

      - name: Commit and push
        run: |
          SHORT_SHA=$(echo "${{ github.sha }}" | cut -c1-7)
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add k8s/apps/<APP_NAME>-dev/deployment.yaml k8s/apps/<APP_NAME>-prod/deployment.yaml
          git diff --staged --quiet || git commit -m "chore: update <APP_NAME> image to sha-${SHORT_SHA} [skip ci]"
          git pull --rebase origin main
          git push
```

**Placeholders:**
- `<APP_NAME>` — your app name (e.g., `contact-api`)

**How it works:**

1. On push to `main`, builds a Docker image tagged `sha-<short-sha>` and `latest`
2. Pushes to `ghcr.io/<org>/<repo>`
3. Updates the image tag in both dev and prod deployment manifests
4. Commits with `[skip ci]` to avoid triggering another build
5. ArgoCD detects the manifest change and syncs the new image to the cluster

Uses `GITHUB_TOKEN` for GHCR auth — no extra secrets needed.

### c. Kubernetes Manifests

Create two directories:
```
k8s/apps/<APP_NAME>-dev/
k8s/apps/<APP_NAME>-prod/
```

Each directory contains 3 manifests + 1 example file.

#### `deployment.yaml`

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: <APP_NAME>
  namespace: <NAMESPACE>           # civpulse-dev or civpulse-prod
  labels:
    app: <APP_NAME>
spec:
  replicas: 1
  selector:
    matchLabels:
      app: <APP_NAME>
  template:
    metadata:
      labels:
        app: <APP_NAME>
    spec:
      automountServiceAccountToken: false
      securityContext:
        runAsNonRoot: true
        runAsUser: 65534
        runAsGroup: 65534
        fsGroup: 65534
        seccompProfile:
          type: RuntimeDefault
      # Include initContainers only if your app runs database migrations:
      initContainers:
        - name: migrate
          image: ghcr.io/<ORG>/<REPO>:<IMAGE_TAG>
          imagePullPolicy: Always
          command: ["<MIGRATION_COMMAND>"]    # e.g., ["alembic", "upgrade", "head"]
          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: false     # Migrations may write temp files
            capabilities:
              drop:
                - ALL
          envFrom:
            - secretRef:
                name: <APP_NAME>-secret
          resources:
            requests:
              memory: "256Mi"
              cpu: "100m"
              ephemeral-storage: "50Mi"
            limits:
              memory: "512Mi"
              cpu: "500m"
      containers:
        - name: <APP_NAME>
          image: ghcr.io/<ORG>/<REPO>:<IMAGE_TAG>
          imagePullPolicy: Always
          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities:
              drop:
                - ALL
          ports:
            - containerPort: <APP_PORT>      # Convention: 8000
          envFrom:
            - secretRef:
                name: <APP_NAME>-secret
          env:
            - name: LOG_LEVEL
              value: "<LOG_LEVEL>"           # DEBUG for dev, INFO for prod
            - name: ENVIRONMENT
              value: "<ENVIRONMENT>"         # development or production
            # Add app-specific non-secret env vars here
          resources:
            requests:
              memory: "256Mi"
              cpu: "100m"
              ephemeral-storage: "50Mi"
            limits:
              memory: "512Mi"
              cpu: "500m"
          livenessProbe:
            httpGet:
              path: <HEALTH_ENDPOINT>        # e.g., /api/v1/health
              port: <APP_PORT>
            initialDelaySeconds: 15
            periodSeconds: 30
          readinessProbe:
            httpGet:
              path: <HEALTH_ENDPOINT>
              port: <APP_PORT>
            initialDelaySeconds: 10
            periodSeconds: 10
```

**Placeholders:**
- `<APP_NAME>` — your app name (e.g., `contact-api`)
- `<NAMESPACE>` — `civpulse-dev` or `civpulse-prod`
- `<ORG>/<REPO>` — GitHub org/repo (e.g., `civicpulse/contact-api`)
- `<IMAGE_TAG>` — initial tag (CI will update this automatically)
- `<MIGRATION_COMMAND>` — your migration command; remove `initContainers` entirely if not needed
- `<APP_PORT>` — your app's listening port (convention: `8000`)
- `<HEALTH_ENDPOINT>` — your health check path
- `<LOG_LEVEL>` — `DEBUG` for dev, `INFO` for prod
- `<ENVIRONMENT>` — `development` or `production`

#### `service.yaml`

```yaml
apiVersion: v1
kind: Service
metadata:
  name: <APP_NAME>
  namespace: <NAMESPACE>
  labels:
    app: <APP_NAME>
spec:
  type: ClusterIP
  ports:
    - port: <APP_PORT>
      targetPort: <APP_PORT>
      protocol: TCP
  selector:
    app: <APP_NAME>
```

#### `ingress.yaml`

Traefik IngressRoute CRD — **not** a standard `Ingress` resource.

```yaml
# Traefik IngressRoute for <APP_NAME>
# Traffic path: Cloudflare → cloudflared → Traefik → <APP_NAME>
apiVersion: traefik.io/v1alpha1
kind: IngressRoute
metadata:
  name: <APP_NAME>
  namespace: <NAMESPACE>
spec:
  entryPoints:
    - web
  routes:
    - match: Host(`<HOSTNAME>.civpulse.org`)
      kind: Rule
      services:
        - name: <APP_NAME>
          port: <APP_PORT>
```

**Placeholders:**
- `<HOSTNAME>` — your app's public hostname prefix (e.g., `contactapi` for `contactapi.civpulse.org`)

For prod, you may want multiple host matches (e.g., `Host(\`myapp.civpulse.org\`) || Host(\`myapp-prod.civpulse.org\`)`).

#### `<APP_NAME>-secret.yaml.example`

This is documentation only — **never commit real secret values**.

```yaml
# <APP_NAME>-secret — DO NOT commit actual secret values!
#
# Create the secret using an env file (keeps credentials out of shell history):
#
# 1. Create a local env file (never commit this):
#
#    cat > /tmp/<APP_NAME>-<ENV>.env <<'EOF'
#    DATABASE_URL=postgresql+asyncpg://<user>:<password>@postgresql.civpulse-infra.svc.cluster.local:5432/<your_db>
#    JWT_SECRET_KEY=<your-jwt-secret-key-min-32-chars>
#    EOF
#    chmod 600 /tmp/<APP_NAME>-<ENV>.env
#
# 2. Create the secret from the env file:
#
#    kubectl create secret generic <APP_NAME>-secret \
#      --namespace <NAMESPACE> \
#      --from-env-file=/tmp/<APP_NAME>-<ENV>.env
#
# 3. Remove the temp file securely:
#
#    shred -u /tmp/<APP_NAME>-<ENV>.env
```

**Placeholders:**
- `<ENV>` — `dev` or `prod`
- Add all required keys for your app in the env file section

### d. ArgoCD Application Manifests

Create two files in `argocd/`:

#### `argocd/<APP_NAME>-dev-app.yaml`

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: <APP_NAME>-dev
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://github.com/<ORG>/<REPO>.git
    targetRevision: main
    path: k8s/apps/<APP_NAME>-dev
  destination:
    server: https://kubernetes.default.svc
    namespace: civpulse-dev
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=false
```

#### `argocd/<APP_NAME>-prod-app.yaml`

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: <APP_NAME>-prod
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://github.com/<ORG>/<REPO>.git
    targetRevision: main
    path: k8s/apps/<APP_NAME>-prod
  destination:
    server: https://kubernetes.default.svc
    namespace: civpulse-prod
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=false
```

### e. Cloudflare DNS

Add a CNAME record for your hostname pointing to the existing Cloudflare Tunnel.

This is a **manual step** in the Cloudflare dashboard:
1. Go to the CivPulse domain DNS settings
2. Add a CNAME record: `<HOSTNAME>.civpulse.org` → tunnel UUID (same as existing apps)
3. Ensure the record is proxied (orange cloud enabled)

---

## 9. Security Conventions

All pods in the cluster follow these hardening rules:

| Rule | Value | Notes |
|---|---|---|
| **Non-root** | `runAsUser: 65534` (`nobody`) | Pod-level `securityContext` |
| **Group** | `runAsGroup: 65534`, `fsGroup: 65534` | Consistent UID/GID |
| **Capabilities** | Drop `ALL` | No Linux capabilities granted |
| **Seccomp** | `RuntimeDefault` | System call filtering |
| **Read-only root** | `readOnlyRootFilesystem: true` | App containers |
| **Init containers** | `readOnlyRootFilesystem: false` | Only if migrations need temp files |
| **Privilege escalation** | `allowPrivilegeEscalation: false` | Always |
| **Service account** | `automountServiceAccountToken: false` | Unless your app needs RBAC |
| **Secrets** | Never committed to git | Created via `kubectl create secret generic --from-env-file` |
| **Secret cleanup** | `shred -u` temp files after creation | Don't leave plaintext credentials on disk |

---

## 10. Existing Apps as Reference

| App | Status | Location | Notes |
|---|---|---|---|
| **voter-api** | Dev + Prod | `k8s/apps/voter-api-{dev,prod}/` | Full reference: init container (migrations), multi-env, ArgoCD, CI/CD |
| **contact-api** | Dev only | Separate repo | Simpler example, deployed in `civpulse-dev` |

Both use the same patterns documented in this guide. voter-api is the most complete reference.

---

## 11. Deployment Checklist

Follow these steps in order when deploying a new app.

### Pre-deployment

- [ ] **Request database**: Ask infra admin to create a new database + credentials on the shared PostgreSQL instance
- [ ] **Choose hostname**: Pick a `<name>.civpulse.org` hostname for your app

### Repository setup

- [ ] **Dockerfile**: Create multi-stage Dockerfile (see [section 8a](#a-dockerfile))
- [ ] **CI workflow**: Create `.github/workflows/build-push.yaml` (see [section 8b](#b-githubworkflowsbuild-pushyaml))
- [ ] **Verify CI**: Push to `main`, confirm image appears at `ghcr.io/<org>/<repo>`

### Kubernetes manifests

- [ ] **Dev deployment**: Create `k8s/apps/<app>-dev/deployment.yaml` (see [section 8c](#deploymentyaml))
- [ ] **Dev service**: Create `k8s/apps/<app>-dev/service.yaml` (see [section 8c](#serviceyaml))
- [ ] **Dev ingress**: Create `k8s/apps/<app>-dev/ingress.yaml` (see [section 8c](#ingressyaml))
- [ ] **Dev secret example**: Create `k8s/apps/<app>-dev/<app>-secret.yaml.example` (see [section 8c](#app_name-secretyamlexample))
- [ ] **Prod manifests**: Duplicate the dev directory to `k8s/apps/<app>-prod/`, update namespace to `civpulse-prod`, `ENVIRONMENT` to `production`, and `LOG_LEVEL` to `INFO`

### Secrets

- [ ] **Create dev secret**: `kubectl create secret generic <app>-secret --namespace civpulse-dev --from-env-file=/tmp/<app>-dev.env`
- [ ] **Create prod secret**: `kubectl create secret generic <app>-secret --namespace civpulse-prod --from-env-file=/tmp/<app>-prod.env`
- [ ] **Shred env files**: `shred -u /tmp/<app>-dev.env /tmp/<app>-prod.env`

### ArgoCD

- [ ] **Dev ArgoCD app**: Create `argocd/<app>-dev-app.yaml` (see [section 8d](#d-argocd-application-manifests))
- [ ] **Prod ArgoCD app**: Create `argocd/<app>-prod-app.yaml`
- [ ] **Apply ArgoCD apps**: `kubectl apply -f argocd/<app>-dev-app.yaml -f argocd/<app>-prod-app.yaml`

### Cloudflare DNS

- [ ] **Add CNAME**: In Cloudflare dashboard, add `<hostname>.civpulse.org` CNAME pointing to the tunnel
- [ ] **Verify proxied**: Ensure the orange cloud (proxy) is enabled

### Verification

- [ ] **ArgoCD sync**: Check ArgoCD UI — app should show `Synced` and `Healthy`
- [ ] **Pod running**: `kubectl get pods -n civpulse-dev -l app=<app>`
- [ ] **Logs clean**: `kubectl logs -n civpulse-dev -l app=<app>`
- [ ] **HTTP response**: `curl https://<hostname>.civpulse.org/<health-endpoint>`
- [ ] **Repeat for prod**: Verify all of the above for `civpulse-prod`

---

## Appendix: Directory Structure

Here's the expected file layout in your repo after setup:

```
your-repo/
├── Dockerfile
├── .github/
│   └── workflows/
│       └── build-push.yaml
├── argocd/
│   ├── <app>-dev-app.yaml
│   └── <app>-prod-app.yaml
├── k8s/
│   └── apps/
│       ├── <app>-dev/
│       │   ├── deployment.yaml
│       │   ├── service.yaml
│       │   ├── ingress.yaml
│       │   └── <app>-secret.yaml.example
│       └── <app>-prod/
│           ├── deployment.yaml
│           ├── service.yaml
│           ├── ingress.yaml
│           └── <app>-secret.yaml.example
└── src/
    └── ...
```
