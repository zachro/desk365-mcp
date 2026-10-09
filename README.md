# desk365-mcp

An [MCP](https://modelcontextprotocol.io) server for [Desk365](https://www.desk365.io), the help desk software. It lets an MCP client such as Claude Code or open-source/self-hosted LLMs work with your Desk365 tickets, contacts and knowledge base through the [Desk365 API (v3)](https://help.desk365.io/en/articles/desk365-api/).

It works with any Desk365 account. Everything specific to your account goes in an env file, so you don't need to change any code.

## Tools

| Tool | What it does |
| --- | --- |
| `ping` | Checks that the Desk365 API is up and reachable. It doesn't check your API key. |
| `list_tickets` | Lists tickets. It supports paging (30, 50 or 100 per page), sorting by created or updated time, `updated_since`, and filters on status, priority, type, group, assignee, category, subcategory, source, contact, company and custom dropdown fields. |
| `search_tickets` | Full-text search for tickets, sorted by relevance. It can search subjects and ticket numbers, descriptions, replies and notes, attachment names, custom fields, and contact and company names, and can include archived tickets. |
| `advanced_search_tickets` | Searches specific fields (subject, ticket number, or text custom fields) and returns tickets where every field matches. |
| `get_ticket_details` | Gets the full details of one ticket by ticket number, including its description and custom fields. |
| `get_ticket_conversations` | Gets a ticket's conversation history: contact and agent replies, public and private notes, and forwarded messages. Each type can be left out, and messages can be sorted oldest or newest first. |
| `create_ticket` | Creates a ticket for a contact's email address. It can set the description, status, priority, type, assignee, group, category, subcategory, form, custom fields, watchers and shared contacts. |
| `update_ticket` | Changes an existing ticket's contact, subject, description, SLA, status, priority, type, assignee, group, category, subcategory or custom fields, and adds or removes watchers and shared contacts. Fields that aren't set keep their current values. |
| `add_ticket_reply` | Sends a reply on a ticket, which is emailed to the contact. It supports CC/BCC, choosing the sending agent and from-address, notifying earlier CCs, and quoting earlier messages. |
| `add_ticket_note` | Adds a note to a ticket. Notes are private (agents only) by default; a public note is also sent to the contact. It can notify other agents and choose the agent the note is from. |
| `list_contacts` | Lists contacts 30 at a time, optionally only those in one company, sorted by name, title, company or email. |
| `get_contact_details` | Gets a contact's details by their primary or secondary email address. |
| `list_kb_articles` | Lists the titles of all live knowledge base articles. |
| `get_kb_article` | Gets a live knowledge base article's full content and links by its title. |

Each tool's docstring in `desk365_mcp/server.py` explains to the LLM when and how to use it.

## Requirements

- A Desk365 plan that includes API access (Standard, Plus or Premium).
- Your Desk365 API key, found under **Settings > Integrations > API** in Desk365. If you can't see it, ask your Desk365 administrator.
- Python 3.12+ and [uv](https://docs.astral.sh/uv/).

## Setup

```sh
git clone https://github.com/zachro/desk365-mcp.git
cd desk365-mcp
uv sync
cp .env.example .env
```

Then fill in `.env`:

| Variable | Description |
| --- | --- |
| `API_KEY` | Your Desk365 API key. |
| `SUBDOMAIN` | Your Desk365 subdomain: `yourcompany` in `https://yourcompany.desk365.io`. Each API key works only with its own subdomain. |

Both are required. You can also set this optional variable:

| Variable | Description |
| --- | --- |
| `DEFAULT_AGENT_EMAIL` | Email address of the agent that replies and notes are sent as when the LLM doesn't name one. If unset, they come from the owner of the API key. |

You can also set any of these as ordinary environment variables instead of using a file. Env files are ignored by git, so your key won't be committed.

## Running

```sh
uv run desk365-mcp
```

The server listens at `http://localhost:8000/` using the streamable HTTP transport.

### Stages

To keep settings for more than one Desk365 account or environment, create one env file per stage and pass `--stage`:

```sh
uv run desk365-mcp --stage dev    # loads dev.env
uv run desk365-mcp --stage beta   # loads beta.env
uv run desk365-mcp                # loads .env
```

The server won't start if the named stage file doesn't exist.

## Connecting an MCP client

Point your client at `http://localhost:8000/` while the server is running. For example, with Claude Code:

```sh
claude mcp add --transport http desk365 http://localhost:8000/
```

## Rate limits

Desk365 limits API calls by plan: 100 calls per hour on Standard, and 50 calls per minute on Plus and Premium. Every tool call makes one API request, and Desk365 counts each search request as 5 calls. The `list_tickets` docstring tells the LLM to use filters instead of paging through every ticket.

## Development

Run the tests:

```sh
uv run pytest
```

The tests mock the Desk365 API, so they need no API key or network access.

Project layout:

- `desk365_mcp/main.py`: command-line entry point (`desk365-mcp`) and `--stage` handling.
- `desk365_mcp/config.py`: loads and checks the env file.
- `desk365_mcp/server.py`: MCP tool definitions, their LLM-facing docstrings, and logging.
- `desk365_mcp/api.py`: Desk365 API calls and business logic.

To add a tool, put the API call in `api.py` and the tool in `server.py`. Write the tool's docstring for the LLM that will read it. FastMCP sends the text before `Args:` as the tool description and turns each `Args:` entry into that parameter's description. It drops any other section, such as `Returns:`. Desk365's published API schema doesn't always match real responses (for example, it lists `assign_to` where the API returns `assigned_to`), so check field names against a real response.

## License

[MIT](LICENSE)
