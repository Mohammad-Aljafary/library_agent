# Library Desk Agent

A conversational AI agent for managing a library's books, customers, and orders using FastAPI, LangChain, and Ollama.

## Features

- 📚 Search books by title or author
- 🛒 Create and manage orders
- 📦 Add items to existing orders
- 📊 View inventory and order status
- 💬 Multi-session chat support
- 🔄 Real-time streaming responses
- 🔒 HTTPS with Nginx reverse proxy

## Tech Stack

- **Backend**: FastAPI, SQLAlchemy, LangChain
- **Frontend**: Vanilla JavaScript (Server-Sent Events)
- **LLM**: Ollama (qwen2.5:3b)
- **Database**: SQLite
- **Proxy**: Nginx with self-signed TLS

## Quick Start (Docker)

Prerequisites: **Docker** and **Docker Compose**

```bash
make up
```

That's it. On first run this will:

1. Generate a self-signed SSL certificate
2. Pull the Ollama Docker image
3. Download the qwen2.5:3b model (~1.9 GB)
4. Build & start the FastAPI app
5. Start Nginx on ports 80 (→ redirect) and 443 (HTTPS)

Open **https://localhost** and accept the browser warning (self-signed cert).

### Other commands

| Command | Description |
|---------|-------------|
| `make up` | Start all services |
| `make down` | Stop all services |
| `make restart` | Restart everything |
| `make logs` | Tail all logs |
| `make logs-app` | Tail app logs only |
| `make ps` | Show running containers |
| `make clean` | Remove containers, volumes & images |
| `make reset-db` | Wipe and re-seed the database |
| `make pull-model` | Update the LLM model |
| `make shell` | Shell into the app container |
| `make help` | List all commands |

## Local Development (without Docker)

```bash
# 1. Install & start Ollama
curl -fsSL https://ollama.ai/install.sh | sh
ollama pull qwen2.5:3b

# 2. Python environment
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env

# 3. Seed database & run
python db/seed.py
uvicorn server.main:app --reload --port 8000
```

Open http://localhost:8000

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_HOST` | `sqlite:///./db/library.db` | Database connection |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama endpoint |
| `OLLAMA_MODEL` | `qwen2.5:3b` | LLM model name |

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/session/new` | Create a new session |
| GET | `/sessions` | List all sessions |
| GET | `/session/{id}/messages` | Get messages for a session |
| DELETE | `/session/{id}` | Delete a session |
| POST | `/chat` | Send a message (JSON) |
| POST | `/chat/stream` | Send a message (SSE stream) |
| GET | `/health` | Health check |

## Agent Tools

| Tool | Description |
|------|-------------|
| `find_books(q, by)` | Search books by title or author |
| `create_order(customer_id, items)` | Create a new order |
| `add_to_order(order_id, items)` | Add items to an existing order |
| `restock_book(isbn, qty)` | Add stock |
| `update_price(isbn, price)` | Change a book's price |
| `order_status(order_id)` | Check order details |
| `list_orders()` | List all orders |
| `inventory_summary()` | Inventory overview |

## Project Structure

```
├── app/                 # Frontend
│   ├── index.html
│   └── main.js
├── db/                  # Database
│   ├── tables.py
│   └── seed.py
├── server/              # Backend
│   ├── main.py
│   ├── agent.py
│   └── tools.py
├── prompts/
│   └── system_prompt.txt
├── nginx/
│   └── nginx.conf
├── Dockerfile
├── docker-compose.yml
├── Makefile
└── requirements.txt
```

## Troubleshooting

**Model not responding**
```bash
make logs-ollama        # check Ollama output
make pull-model         # re-pull model
make restart            # restart everything
```

**Database issues**
```bash
make reset-db
```

**Port conflict on 80/443**
```bash
sudo lsof -i :443      # find what's using the port
```

Edit `docker-compose.yml` ports if needed (e.g. `8443:443`).

## License

MIT
