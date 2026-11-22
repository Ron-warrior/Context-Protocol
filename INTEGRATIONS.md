# Attaching FreeLLMAPI — what it actually is, and what I got wrong

## Correction first

I said: *"I can't use FreeLLMAPI — it's a local router needing Docker and provider
keys, and this app reaches only remote MCP servers over https. So as my inference
backend: no."*

That was wrong in kind, not just in detail. The accurate answer is:

> **Yes — if the router is reachable at a public https URL.** FreeLLMAPI ships an
> MCP server. This app attaches to MCP servers. The only thing standing between
> the two is that `/mcp` lives on your machine.

I answered "can't" to "can it be attached", because I'd read the README and
inferred from *local-first* that there was no attach path. The docs, which I read
only when challenged, state the opposite. That is exactly the failure rung 6(c)
exists to catch: I answered from a document instead of checking the interface.

## What the docs actually say

From `docs/en/clients/01-agent-clients.md`:

> On top of the OpenAI-compatible API, the router is an **MCP server**: agents can
> ask a FreeLLMAPI model to perform a text task and introspect the gateway
> mid-session (usable models and the params each one honors, provider health,
> usage and cache stats, routing strategy).
>
> The MCP surface is a setting rather than an always-on endpoint. **Fresh installs
> start with it off.**
>
> ```bash
> claude mcp add --transport http freellmapi http://localhost:3001/mcp \
>   --header "Authorization: Bearer freellmapi-your-unified-key"
> ```
>
> Any MCP client that speaks Streamable HTTP works the same way: point it at
> `/mcp` with the unified key as a Bearer token.

So: **Streamable HTTP + Bearer token.** That is precisely the shape this app can
add.

## What stays true

- **No hosted inference endpoint.** `freellmapi.co` sells the *catalog feed*
  (premium), not tokens. Its own landing page: *"Router — self-hosted and open
  source. Your provider keys stay local."* So nobody can hand me a URL that works
  out of the box.
- **MCP is off by default** on fresh installs. It must be enabled first.
- **I cannot start it.** No shell here, so the running instance has to be yours.

## Three ways to attach, cheapest first

### 1. Local tunnel (works today, one command)

```bash
# 1. enable MCP on the router (Keys page → Agent compatibility, or:)
curl -X PUT http://localhost:3001/api/settings/enable-mcp \
  -H "Authorization: Bearer <dashboard-token>" \
  -H "Content-Type: application/json" -d '{"enabled": true}'

# 2. expose it over https
cloudflared tunnel --url http://localhost:3001
# → https://random-words.trycloudflare.com
```

Then tell me the tunnel URL and I'll add it, with the unified key as the Bearer
header — the key goes in the app's integration card, never in this chat.

Note the trade-off: a quick tunnel is a public URL to your router. Anyone holding
it can spend your free-tier quota. `key-required` auth protects the MCP surface,
but rotate the unified key afterwards if the URL leaked.

### 2. Permanent host (VPS / homelab)

Run the Docker image behind Caddy or nginx with a real certificate, enable MCP,
and the URL is stable:

```
https://llm.example.com/mcp
```

### 3. Point other agents at it

Every one of these is a one-liner if you just want the *coding* benefit without me:

```bash
npx freellmapi setup-claude  --url http://localhost:3001 --api-key <unified-key>
npx freellmapi setup-codex   --url http://localhost:3001 --api-key <unified-key>
npx freellmapi setup-aider   --url http://localhost:3001 --api-key <unified-key>
```

## On "it's just a graph"

There is no graph in this repository. I checked the tree, the README and the
client/API docs: no `skill.md`, no `SKILL.md`, no graph format. `.claude/` contains
only `hooks/` and a `settings.local.json`. The architecture is a **router**: an
initially-SQLite key store, per-provider adapters, a fallback chain, and five
protocol surfaces over one pool.

If the intended meaning was *"it's just a gateway, so of course it's usable"* —
that's right, and it's the point I got backwards. A gateway with an MCP surface is
attachable by definition; the question was never whether it could be used, only
where it listens.

## What I used it for meanwhile

The `real-corpus` CI job checks out `server/src`, `shared` and `cli` from this repo
(795 files, 784 source) and runs the bench against them. That is a real use of the
repository — as the corpus the protocol was missing, not as an inference backend.
See SCOREBOARD.md for the numbers it produced.
