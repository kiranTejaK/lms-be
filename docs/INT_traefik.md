# Traefik Setup & Configuration

## 1. Concept Overview

**What it is:** Traefik is a modern HTTP reverse proxy and load balancer natively integrated with container ecosystems (like Docker, Swarm, and Kubernetes). 

**Why it is used:** Instead of relying on a static configuration file (like traditional NGINX), Traefik automatically discovers services by reading container labels. It seamlessly handles HTTP/HTTPS routing, automatic TLS certificate generation via Let's Encrypt, and dynamic load balancing without requiring manual restarts or reloads when containers spin up or down.

---

## 2. Project Setup

In this project, Traefik is run as a centralized ingress controller across multiple stacks, which is why it uses an external Docker network. The application services then attach to this network to become discoverable.

### Global Network Setup (`docker-compose.yml`)
```yaml
networks:
  traefik-public:
    external: true
```
**Explanation:** 
By declaring `traefik-public` as an `external: true` network, we assume Traefik is already running on the host system, listening on ports 80 and 443. This allows our backend, frontend, and adminer services to connect to it securely and share port 80/443 with other potential apps on the same server.

### Enabling Service Discovery
For any service to be routed by Traefik, it must define explicit labels:
```yaml
  backend:
    # ...
    networks:
      - traefik-public
      - default
    labels:
      - traefik.enable=true
      - traefik.docker.network=traefik-public
```
**Explanation:** 
*   `traefik.enable=true`: Tells Traefik to expose this container.
*   `traefik.docker.network=traefik-public`: Tells Traefik explicitly which network to use for routing traffic to the container (preventing Gateway Timeouts if a container is attached to multiple networks).

---

## 3. Key Code Walkthrough

### Routing and HTTPS Redirection (Backend API)
We define routers for both HTTP and HTTPS, forcing traffic over secure connections.

```yaml
      # Define the target port inside the container
      - traefik.http.services.${STACK_NAME}-backend.loadbalancer.server.port=8000

      # HTTP Router: Listen on port 80, match the domain, and apply redirect middleware
      - traefik.http.routers.${STACK_NAME}-backend-http.rule=Host(`api.${DOMAIN}`)
      - traefik.http.routers.${STACK_NAME}-backend-http.entrypoints=http
      - traefik.http.routers.${STACK_NAME}-backend-http.middlewares=https-redirect

      # HTTPS Router: Listen on port 443, apply Let's Encrypt certificate
      - traefik.http.routers.${STACK_NAME}-backend-https.rule=Host(`api.${DOMAIN}`)
      - traefik.http.routers.${STACK_NAME}-backend-https.entrypoints=https
      - traefik.http.routers.${STACK_NAME}-backend-https.tls=true
      - traefik.http.routers.${STACK_NAME}-backend-https.tls.certresolver=le
```
*Logic Flow:*
1.  **Rule Mapping**: `Host('api.example.com')` tells Traefik to catch traffic for this subdomain.
2.  **HTTPS Enforcement**: HTTP traffic hits the `backend-http` router, which triggers the `https-redirect` middleware.
3.  **TLS Termination**: HTTPS traffic hits `backend-https`, where Traefik handles SSL termination using the `le` (Let's Encrypt) certificate resolver.
4.  **Load Balancing**: Traffic is forwarded to port `8000` on the backend container.

### Basic Authentication Middleware (Adminer)
For internal tools, we protect the route using Traefik's Basic Auth middleware:
```yaml
      # Adminer Basic Auth Setup
      - traefik.http.middlewares.adminer-auth.basicauth.users=${USERNAME}:${HASHED_PASSWORD}
      
      # Attach middleware to the router
      - traefik.http.routers.${STACK_NAME}-adminer-https.middlewares=adminer-auth
```
*Integration:* 
Before traffic reaches the `adminer` database UI, Traefik prompts the user for credentials. Only if they match the `USERNAME` and `HASHED_PASSWORD` will the request be forwarded to the container.

### Regex Redirects (Apex Domain to Dashboard)
We use Traefik's Regex Middleware to cleanly redirect users from the root domain (`example.com`) to the frontend app (`dashboard.example.com`):
```yaml
      # Catch traffic at the root domain
      - traefik.http.routers.${STACK_NAME}-root.rule=Host(`${DOMAIN}`)
      - traefik.http.routers.${STACK_NAME}-root.middlewares=redirect-to-dashboard
      - traefik.http.routers.${STACK_NAME}-root.service=noop@internal

      # Regex Middleware logic
      - traefik.http.middlewares.redirect-to-dashboard.redirectregex.regex=^https?://(www\.)?${DOMAIN}/(.*)
      - traefik.http.middlewares.redirect-to-dashboard.redirectregex.replacement=https://dashboard.${DOMAIN}/$${2}
      - traefik.http.middlewares.redirect-to-dashboard.redirectregex.permanent=true
```
*Integration:* 
By setting `service=noop@internal`, we tell Traefik that this router doesn't need to forward to a real container. Instead, it purely exists to trigger the regex redirect middleware.

---

## 4. End-to-End Flow

**Request Lifecycle in Traefik:**
1.  **DNS & Ingress:** The user navigates to `api.example.com`. The DNS resolves to the host machine's IP, where Traefik is listening on port 443.
2.  **Router Evaluation:** Traefik checks its dynamically generated routing table (built from Docker labels) and finds the `backend-https` router matches the `Host('api.example.com')` rule.
3.  **TLS & Middleware:** Traefik terminates the SSL connection using its Let's Encrypt certificates. It evaluates any attached middlewares (e.g., Auth, Rate Limiting).
4.  **Forwarding:** Traefik passes the raw HTTP request to the internal Docker IP of the `backend` container on port `8000`.
5.  **Response:** The FastAPI backend processes the request and sends the response back through Traefik to the user.

---

## 5. Design Decisions

*   **Label-based Configuration:** 
    *   *Benefit:* Keeps the routing logic, subdomains, and auth rules co-located with the service definition in `docker-compose.yml`. Developers don't have to edit a separate NGINX config when deploying a new microservice.
*   **External `traefik-public` Network:** 
    *   *Benefit:* Allows multiple distinct applications on the same server to share ports 80/443 through a single Traefik proxy.
*   **Automatic TLS Integration (`tls.certresolver=le`):** 
    *   *Benefit:* Completely removes the operational overhead of renewing SSL certificates manually or maintaining certbot cron jobs.

---

## 6. Alternatives & Trade-offs

| Approach | Pros | Cons | When to choose |
| :--- | :--- | :--- | :--- |
| **Traefik (Current)** | Dynamic discovery, auto-TLS, label-based config. | Steeper learning curve for complex regex/middleware syntax. | Dynamic Docker/Kubernetes environments with frequent container scaling. |
| **NGINX** | Industry standard, incredibly fast static file serving, highly customizable. | Requires static configuration files; needs external tools (docker-gen) for dynamic discovery. | Static deployments, heavy caching, or when raw performance is the absolute priority. |
| **Caddy** | Extremely simple `Caddyfile` syntax, built-in auto-TLS. | Less native Docker label integration compared to Traefik. | Simple deployments where a short, readable config file is preferred over Docker labels. |

---

## 7. Interview Questions & Answers

**Q1: How does Traefik route traffic to our Docker containers without a traditional config file like NGINX?**
*Answer:* Traefik hooks into the Docker daemon API. It automatically discovers running containers and reads specific Docker labels (e.g., `traefik.http.routers.my-app.rule=Host(...)`) to dynamically build its routing table in memory without needing manual configuration files or restarts.

**Q2: What is the purpose of defining `traefik-public` as an `external` network in `docker-compose.yml`?**
*Answer:* It means the network is created outside the scope of this specific compose file, usually by a central Traefik instance running on the host. This allows multiple different Docker Compose stacks to attach to the same Traefik proxy, allowing them to share ports 80 and 443 safely.

**Q3: How is HTTPS enforced in this setup?**
*Answer:* We defined an HTTP entrypoint router that catches traffic on port 80 and attaches a `redirectscheme` middleware configured for `https`. All HTTP requests are immediately intercepted by Traefik and redirected to port 443 before they even reach the container.

**Q4: If a container has multiple networks (e.g., `traefik-public` and `default`), how do you prevent Traefik from routing traffic to the wrong internal IP?**
*Answer:* We explicitly specify the `traefik.docker.network=traefik-public` label. This tells Traefik exactly which network interface to use when forwarding traffic. Without this, Traefik might pick the internal `default` network, resulting in 504 Gateway Timeouts.

---

## 8. Bonus Insights

*   **Common Mistake - 504 Gateway Timeouts:** The number one issue developers face is a 504 error. This almost always happens because the target container is not attached to the `traefik-public` network, or the `loadbalancer.server.port` label is pointing to the wrong internal port (e.g., pointing to 80 when the backend exposes 8000).
*   **Performance/Scaling Insight:** Traefik natively supports sticky sessions and weighted load balancing. In a Docker Swarm environment, if you scale the `backend` service to 5 replicas, Traefik instantly detects the 4 new IP addresses and begins round-robin load balancing traffic across them with zero configuration changes required.
