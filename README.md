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
# 1. Clone and enter the project
git clone <repo-url> && cd assessment

# 2. Copy the env file and adjust if needed
cp .env.example .env

# 3. Start everything
make up
```

That's it. On first run this will:

1. Generate a self-signed SSL certificate
2. Pull the Ollama Docker image
3. Download the qwen2.5:3b model (~1.9 GB)
4. Seed the database with sample books, customers, and orders
5. Build & start the FastAPI app
6. Start Nginx on ports 80 (→ redirect) and 443 (HTTPS)

Open **https://localhost** and accept the browser warning (self-signed cert).

### Run Scripts

| Command | Description |
|---------|-------------|
| `make up` | Start all services (generates SSL cert on first run) |
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

# 3. Configure environment
cp .env.example .env          # then edit .env if needed

# 4. Seed the database
python db/seed.py

# 5. Run the server
uvicorn server.main:app --reload --port 8000
```

Open http://localhost:8000

## Database Seeding

The database is seeded automatically on first startup (both Docker and local). The seed script (`db/seed.py`) populates:

- **7 books** — Clean Code, The Pragmatic Programmer, The C Programming Language, Fluent Python, The Art of Computer Programming, The Clean Coder, Clean Architecture
- **3 customers** — John Doe, Jane Smith, Bob Johnson
- **4 sample orders**

Seeding is idempotent — running it again skips if data already exists.

To re-seed from scratch:

```bash
# Docker
make reset-db

# Local
rm -f db/library.db && python db/seed.py
```

## Environment Variables

All configuration lives in `.env` (see `.env.example` for reference).

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_HOST` | `sqlite:///./db/library.db` | Database connection string |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama endpoint |
| `OLLAMA_MODEL` | `qwen2.5:3b` | LLM model name |
| `APP_PORT` | `8000` | Server port |
| `APP_HOST` | `0.0.0.0` | Server bind address |
| `CORS_ORIGINS` | `*` | Allowed origins (comma-separated) |
| `OLLAMA_TEMPERATURE` | `0` | LLM temperature |
| `OLLAMA_NUM_PREDICT` | `2048` | Max tokens per response |
| `MAX_CHAT_HISTORY` | `20` | Messages included in agent context |

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
