# superAI

AI-driven platform: a developer describes what they need in a chat, the agent
decides what to create (services, databases, brokers), writes readable code and
infrastructure files (Compose / Kubernetes YAML), and the platform applies them
to servers that humans provide.

## Layout

- `web/` — React frontend (Vite + TypeScript). Uses a mock API for now.

## Run the frontend

    cd web
    npm install
    npm run dev      # http://localhost:5173
