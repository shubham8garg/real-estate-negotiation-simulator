# Instructor Session Guide — Exercises & Solutions
## Real Estate Negotiation Simulator Workshop (Follow-Up Session)

> **This is a follow-up session.** Students have already seen the actual code for each module.
> Today's focus: exercises and their solutions — what was asked, why it matters, and how it works.

---

## How to Use This Guide

- **Stage-setting** — Read the intro section aloud before showing any exercises for a module.
- **Exercise intro** — Present ALL exercises for a module first, then let students attempt them.
- **Solution walkthrough** — Walk through each solution after the exercise time is up.
- **Interactive breaks** — In solution code, press `ENTER` at each pause to advance. Run with `--fast` to skip pauses.

---

---

# MODULE 1 — Finite State Machines & Failure Modes

## Stage-Setting (Say This Before Exercises)

> "In the last session we saw two files: `naive_negotiation.py` and `state_machine.py`. We deliberately wrote the naive version with **10 known failure modes** — infinite loops, fragile regex, no guarantees. Then we fixed the core problem — termination — with a Finite State Machine.
>
> Today's exercises are about making sure you actually understand *why* the FSM solves what it does, and *how* to extend it without breaking its guarantees. The key insight is that the FSM's power comes from one simple mathematical fact: **terminal states have empty transition sets.** Once you're in AGREED or FAILED, there is literally no way out. The loop cannot continue.
>
> You'll also see which failure modes the FSM does NOT solve — because understanding the limits of each layer is just as important as understanding what it fixes."

**Key concepts to reinforce before exercises:**
- The FSM has exactly 4 states: IDLE → NEGOTIATING → {AGREED, FAILED}
- Termination proof = two properties: (1) terminal states have empty transitions, (2) turn counter is bounded
- The FSM controls *lifecycle*, not message content — that distinction matters a lot

---

## M1 Exercises — Introduce All At Once

### Exercise 1 — Add a TIMEOUT Terminal State `[Core]`

**What to say:**

> "Exercise 1 asks you to add a **fifth state** to the FSM: `TIMEOUT`. This fires when a wall-clock deadline is exceeded — say, 60 seconds total for the negotiation. This is a real production requirement. You can't let an agent negotiation run for hours just because the LLM is slow.
>
> The challenge is: **you must preserve the termination guarantee**. The FSM only guarantees termination because terminal states cannot be exited. If you add TIMEOUT but forget to give it an empty transition set, you've broken the guarantee. So the exercise isn't just 'add a state' — it's 'add a state *correctly*.'
>
> Here are the specific changes: (1) add TIMEOUT to the enum, (2) add `WALL_CLOCK_TIMEOUT` to FailureReason, (3) update the transition table — TIMEOUT must have an empty set, (4) add `deadline_seconds` and `start_time` to FSMContext, (5) check the clock in `process_turn()`, (6) update `is_terminal()` and `check_invariants()`."

**Hint to give if students are stuck:**
> "Start with the transition table. If you add `TIMEOUT` with empty `set()`, you've already done the hardest part."

**Reflection question to ask out loud:**
> "Quick question: does adding TIMEOUT *break* the termination guarantee? Think about it — TIMEOUT has an empty transition set. So once you enter it, where can you go? Nowhere. It's terminal. The guarantee holds."

---

### Exercise 2 — Compare Naive vs FSM `[Core]`

**What to say:**

> "Exercise 2 is analytical, not coding. You run both implementations and fill in a comparison table across all 10 failure modes.
>
> The interesting insight is that the FSM only directly fixes **three** of the ten failure modes: #3 (no state machine), #4 (no turn limits), #6 (no termination guarantee). The other seven are still present or only partially addressed.
>
> What's critical here is the **column to the right** of 'Fixed by FSM' — mapping each unsolved problem to the module that fixes it. M2 fixes hardcoded prices with MCP servers. M3 fixes raw strings and schema with TypedDict messages. M4 fixes structured protocol communication. This is the whole architecture story of the workshop in one table."

**What to point out while running the code:**
> "When you run `naive_negotiation.py`, notice how it loops with raw strings and uses regex to extract prices. When you run `state_machine.py`, watch the `is_terminal()` check and the `check_invariants()` output — that's your basic observability."

**Reflection question:**
> "Does the FSM help with observability at all? Look at `check_invariants()` and `__repr__` — yes, it gives you basic state visibility. But it doesn't record history. That's the difference between seeing where you ARE and understanding how you GOT there."

---

### Exercise 3 — Reimplement FSM in TypeScript `[Stretch]`

**What to say:**

> "This one is for anyone who finishes early or wants a deeper challenge. You're reimplementing the same FSM in TypeScript — not to learn TypeScript, but to prove a point: **the termination guarantee lives in the data structure, not in the language**.
>
> The transition table is a `Map<NegotiationState, Set<NegotiationState>>`. The terminal states have empty Sets. That's true in Python, TypeScript, Go, Rust, or anything else. The language is irrelevant. The mathematical structure is what matters."

---

## M1 Solutions — How to Walk Through Them

### Solution 1 — TIMEOUT State Walkthrough

**Before showing the solution, ask:**
> "Who was able to add TIMEOUT? What was the trickiest part?"
> *(Common answer: forgetting to update `is_terminal()` or forgetting to set `start_time` in `start()`)*

**Walk through in this order:**

**Step 1 — Show the enum change first:**
> "The change to the enum is tiny — one line. But it has a ripple effect everywhere the enum is used. This is why explicit state machines are better than implicit string comparisons — you get compile-time checking of all the places that need to change."

```python
class NegotiationState(Enum):
    IDLE        = auto()
    NEGOTIATING = auto()
    AGREED      = auto()
    FAILED      = auto()
    TIMEOUT     = auto()    # NEW — wall-clock deadline exceeded
```

**Step 2 — Show the transition table:**
> "This is the critical line. `TIMEOUT: set()` — empty set, no outgoing transitions. This single line is what preserves the termination guarantee. It's not magic, it's a data structure constraint."

```python
NegotiationState.TIMEOUT: set(),    # TERMINAL — no outgoing transitions
```

**Step 3 — Show the process_turn() check:**
> "Notice where this check goes — BEFORE the max_turns check. Wall-clock timeout is a harder constraint than turn count. We check it first."

```python
elapsed = time.time() - self.context.start_time
if elapsed > self.context.deadline_seconds:
    self.state = NegotiationState.TIMEOUT
    self.context.failure_reason = FailureReason.WALL_CLOCK_TIMEOUT
    return False
```

**Step 4 — Show is_terminal() update:**
> "If you forgot this, `is_terminal()` would return False for TIMEOUT, which means the graph would try to keep going. This is exactly the kind of bug that causes production incidents."

**Step 5 — Run the demo:**
```bash
python m1_baseline/state_machine.py
```
> "The existing scenarios still pass. TIMEOUT never fires in this fast demo because we're not running for 60 seconds. But the state exists and is reachable."

**Final talking point:**
> "The formal termination proof is two sentences: (1) TIMEOUT has empty transition set, so once entered it cannot be exited. (2) The deadline check provides an *additional* path to a terminal state, which can only make termination happen *sooner*, never later. QED."

---

### Solution 2 — Comparison Table Walkthrough

**Show the completed table and discuss these rows specifically:**

| Row | What to say |
|-----|-------------|
| #3, #4, #6 | "These three are the FSM's core wins. This is why we built the FSM." |
| #8 | "Hardcoded prices — the FSM doesn't touch this. This is exactly why M2 exists." |
| #1, #2, #5 | "Raw strings, no schema, regex parsing — all of these are message format problems. The FSM controls state, not messages. M3 fixes these with TypedDict." |
| #9 | "Partially — FSM gives us `__repr__` and `check_invariants()`. Full observability is M3's history list." |

> "The architecture insight here is **separation of concerns**: the FSM layer solves *one thing* — lifecycle. It doesn't try to solve data format, pricing, or observability. Each of those gets its own layer. This is why we have four modules."

---

---

# MODULE 2 — MCP Protocol

## Stage-Setting (Say This Before Exercises)

> "In Module 1 we fixed termination. But the agents were still using hardcoded prices — failure mode #8. In Module 2, we connected them to real data via the **Model Context Protocol (MCP)**.
>
> The key insight of MCP is simple: instead of agents hallucinating prices or relying on training data, they call a tool server to get real market data. The `@mcp.tool()` decorator does two things: it exposes a Python function as a callable tool over JSON-RPC, AND it auto-generates the JSON Schema for parameters using Python type hints. The LLM sees that schema, understands what the tool does, and decides when to call it.
>
> Today's exercises are about: (1) adding a new tool to a server, and (2) wiring it into an agent so the LLM can actually use it. These are the two sides of MCP — server-side (defining tools) and client-side (consuming them)."

**Key concepts to reinforce:**
- `@mcp.tool()` = auto-registration, auto-schema, auto-serialization
- Agents use a ReAct planning pattern: LLM decides WHICH tools to call, not hardcoded
- Information asymmetry: buyer sees pricing server, seller sees pricing + inventory (including secret floor price)

---

## M2 Exercises — Introduce All At Once

### Exercise 1 — Add a New MCP Tool `[Starter]`

**What to say:**

> "Exercise 1 is the simplest possible MCP exercise: add one function to the pricing server. The function calculates estimated property tax: price × rate = annual tax.
>
> The point isn't the math — it's the pattern. You'll see that `@mcp.tool()` is a three-line decorator that gives you: tool registration, JSON Schema generation from type hints, and return value serialization. You don't write any of that infrastructure. It's all automatic.
>
> After adding it, start the server and confirm it registers. That's the whole exercise — but understanding *why* it's that simple is the learning."

**Show the pattern to look for:**
> "Look at `get_market_price` and `calculate_discount` in `pricing_server.py`. Both have `@mcp.tool()`, typed parameters, and return a dict. Your new function follows exactly the same pattern."

---

### Exercise 2 — Wire the Tool into the Buyer Agent `[Core]`

**What to say:**

> "Exercise 2 is the more interesting half: adding the tool to the server is easy — but the agent also needs to *know the tool exists* to call it. That's what this exercise is about.
>
> The buyer agent uses a two-phase pattern: first, a 'planner' LLM call that decides which tools to call based on a prompt describing available tools. Second, the actual tool calls. You need to update **both** — the planner prompt (so GPT-4o knows the tool exists) and the system prompt (so the buyer agent knows to consider tax in its strategy).
>
> Notice what you do NOT need to change: the `call_pricing_mcp()` function. It's generic — it takes any tool name and arguments and calls the server. Adding a new tool doesn't change the transport layer at all. **That's the power of MCP**: server and client evolve independently."

**Reflection to tease before they start:**
> "Here's a question to think about while working: why do we let the LLM *decide* which tools to call, rather than hardcoding 'always call all three tools'? The answer involves token cost, relevance, and what happens when you have 20 tools instead of 3."

---

### Exercise 3 — Build an Appraisal Server `[Stretch]`

**What to say:**

> "The stretch exercise asks you to build an entire MCP server from scratch: `appraisal_server.py` with two tools — `get_comparable_sales()` and `get_appraisal_estimate()`. This is seller-only information (like `get_minimum_acceptable_price`), so it represents another layer of information asymmetry.
>
> The key design decision is: how many MCP servers should one agent connect to? The seller already connects to two — pricing and inventory. Adding a third means updating the seller's MCP client configuration. That's a real architectural choice in production systems."

---

## M2 Solutions — How to Walk Through Them

### Solution 1 — Tax Tool Walkthrough

**Before showing:**
> "Let's look at exactly what you needed to add. Three things: the decorator, the function signature, and the return dict."

**Show the code and explain each part:**

```python
@mcp.tool()
def get_property_tax_estimate(price: float, tax_rate: float = 0.02) -> dict:
    annual_tax = int(price * tax_rate)
    return {
        "price": price,
        "tax_rate": tax_rate,
        "estimated_annual_tax": annual_tax,
    }
```

> "The `@mcp.tool()` decorator does three things automatically:
> 1. **Registers** the function name as the tool name — no config file needed
> 2. **Inspects** the type hints to generate JSON Schema — `price: float` becomes `{"type": "number"}` in the schema
> 3. **Serializes** the return dict as a JSON text content block — no serialization code needed
>
> This is why MCP is powerful: the infrastructure is invisible. You write a Python function, and it becomes a networked tool."

**Run and verify:**
```bash
python m2_mcp/pricing_server.py
```

---

### Solution 2 — Buyer Prompt Wiring Walkthrough

**Walk through the two changes:**

**Change 1 — Planner prompt:**
> "This is where the LLM learns the tool exists. The planner prompt is a list of available tools with their argument schemas. Adding `get_property_tax_estimate` here means GPT-4o will consider it when deciding what to call."

```
- get_property_tax_estimate: {"price": number, "tax_rate": number}
```

> "Notice the rule we added: 'Call get_property_tax_estimate to factor in annual holding costs.' This is prompt engineering — we're guiding the LLM toward when this tool is appropriate."

**Change 2 — System prompt:**
> "The system prompt shapes the agent's overall negotiation strategy. Adding 'Reference property tax estimates to strengthen your negotiation position' teaches the buyer *why* tax matters — high tax = higher holding cost = lower price you can offer. The LLM connects these dots."

**Answer the reflection question:**
> "Why ReAct planning instead of hardcoded calls? Three reasons:
> 1. **Token cost**: calling all tools every round wastes API budget on data you may not need
> 2. **Relevance**: in round 1, market price matters most; tax becomes relevant when fine-tuning a near-final offer
> 3. **Scalability**: with 20 tools, hardcoding becomes unmanageable. ReAct scales naturally — the LLM picks what's relevant."

---

---

# MODULE 3 — LangGraph Multi-Agent Orchestration

## Stage-Setting (Say This Before Exercises)

> "Modules 1 and 2 gave us termination guarantees and real market data. Module 3 is where we add **orchestration**: a formal workflow that manages the entire negotiation as a stateful graph.
>
> LangGraph IS a state machine — but for workflows, not individual states. The StateGraph has nodes (agents doing work), edges (fixed connections), and conditional edges (routing functions that decide which path to take based on state). The history list with `Annotated[list, operator.add]` gives us an append-only audit trail of every round.
>
> The exercises today are about **modifying the graph's behavior** — specifically, the routing logic and the business rules inside nodes. These are the two places where you inject domain logic into a LangGraph workflow."

**Key concepts to reinforce:**
- Nodes read state, do work, return partial updates — LangGraph merges them
- Routers are pure functions: read state, return a string key, no side effects
- `Annotated[list, operator.add]` is the LangGraph pattern for append-only lists
- The graph topology: START → init → buyer ↔ seller loop → END

---

## M3 Exercises — Introduce All At Once

### Exercise 1 — Add a Deadlock-Breaker Conditional Edge `[Core]`

**What to say:**

> "Exercise 1 targets a real problem: agents can get stuck in a standoff — buyer offers 440K, seller counters 470K, and they just repeat those same prices round after round until max_rounds runs out. We're wasting API calls and time.
>
> The fix goes in `route_after_seller()` — the routing function that decides whether to loop back to the buyer or end the negotiation. You'll add a stale-price check: look at the last 4 history entries (2 full rounds), and if both buyer and seller prices haven't changed, force termination.
>
> The critical constraint: **routers must be pure functions**. No side effects, no state mutations. The router only reads state and returns 'continue' or 'end'. It cannot set `status = 'deadlocked'` — that would be a side effect. The graph handles the rest."

**Key insight to emphasize:**
> "This is the difference between a routing rule and business logic. The router enforces the *structural* rule: 'no progress means no continuation.' Business logic (like what price to offer) stays in the agent nodes."

---

### Exercise 2 — Add Automatic Convergence Accept `[Core]`

**What to say:**

> "Exercise 2 adds business logic *inside* a node rather than in a router. The scenario: buyer offers 458K, seller counters 465K — they're only 1.5% apart. At this point, letting them negotiate more is wasteful. Better to auto-agree at the midpoint: 461.5K.
>
> The change goes in `seller_node()`, after the seller has computed its counter-offer but before returning the state update. At that moment, you know both prices — buyer's offer (from state) and seller's counter (just computed). Calculate the gap percentage. If ≤ 2%, set `new_status = 'agreed'` and compute the midpoint.
>
> After this change, `route_after_seller()` will see `status = 'agreed'` and route to END. The auto-accept just needs to update `new_status` and `agreed_price` — the routing logic handles itself."

**Reflection to tease:**
> "What's the right threshold? 0%? 10%? Think about the trade-off: lower threshold = agents negotiate longer = potentially better price. Higher threshold = faster resolution = but you might leave money on the table."

---

### Exercise 3 — State Persistence with SQLite `[Stretch]`

**What to say:**

> "The stretch exercise adds checkpointing: pause a negotiation mid-session, kill the process, and resume from where you left off. LangGraph has first-class support for this via `AsyncSqliteSaver`. The negotiation state is serialized to SQLite at each node boundary.
>
> This maps directly to real use cases: multi-day negotiations, session recovery after crashes, audit trails for compliance. The implementation is just a few lines — pass the checkpointer to `graph.compile()` — but understanding *why* it works teaches you about LangGraph's execution model."

---

### Exercise 4 — Inspector Agent Capstone `[Stretch]`

**What to say:**

> "This is the hardest exercise and ties all four modules together. You're adding a third agent — a property inspector — as a new LangGraph node. When buyer and seller reach 'agreed', instead of going straight to END, the graph routes through `inspector_node()` first.
>
> The inspector calls its own MCP server (`inspection_server.py`) with `inspect_property()` and `get_repair_estimate()` tools. If the inspection passes, the deal goes through. If it fails (major defects), the status becomes 'inspection_failed' and the negotiation either ends or restarts.
>
> What makes this a capstone is that you're applying all four modules: M1's terminal states (inspection_failed is a new terminal state), M2's MCP pattern (new inspection server), M3's graph nodes and routing, and optionally M4's A2A protocol if you want the inspector to be a separate networked agent."

---

## M3 Solutions — How to Walk Through Them

### Solution 1 — Deadlock-Breaker Walkthrough

**Before showing, ask:**
> "Who added the deadlock detection? What was the tricky part?"
> *(Common: accessing `history` correctly, filtering by agent name)*

**Show the complete function and walk through it:**

```python
def route_after_seller(state: dict) -> Literal["continue", "end"]:
    status = state.get("status", "negotiating")

    if status != "negotiating":
        return "end"

    round_number = state.get("round_number", 0)
    max_rounds = state.get("max_rounds", 5)

    if round_number >= max_rounds:
        return "end"

    # NEW: Stale-price deadlock detection
    history = state.get("history", [])
    if len(history) >= 4:
        recent = history[-4:]
        buyer_prices = [e.get("price") for e in recent if e.get("agent") == "buyer"]
        seller_prices = [e.get("price") for e in recent if e.get("agent") == "seller"]

        if (len(buyer_prices) >= 2 and len(seller_prices) >= 2
                and buyer_prices[-1] == buyer_prices[-2]
                and seller_prices[-1] == seller_prices[-2]):
            print(f"[LangGraph Router] Stale prices detected — forcing deadlock")
            return "end"

    return "continue"
```

**Walk through line by line:**

> "`history[-4:]` — why 4? Because one full round = buyer entry + seller entry. Two rounds = 4 entries. We need at least two rounds of data to detect a repeat.

> `e.get('agent') == 'buyer'` — filtering by agent. The history list has interleaved buyer and seller entries, so we separate them to compare buyer prices against buyer prices.

> `buyer_prices[-1] == buyer_prices[-2]` — comparing the two most recent prices for each agent. If both are identical, neither side is moving.

> The `print()` here is the one place where a router has a side effect — logging. This is acceptable. What's not acceptable is mutating state or calling external APIs."

**Answer the reflection:**
> "Could this accidentally end a winning negotiation? Yes, theoretically — if an agent was about to change its price on round 3 after being stuck for 2. But LLM agents rarely do this; they either move each round or explicitly walk away. To reduce false positives: check `history[-6:]` with 3 rounds instead of 2."

**Run with interactive pauses:**
```bash
python m3_langgraph_multiagents/main_langgraph_multiagent.py --rounds 5
```

---

### Solution 2 — Convergence Accept Walkthrough

**Show the new block inside `seller_node()`:**

```python
# SOLUTION: Convergence auto-accept
if new_status == "negotiating":
    buyer_offer = state.get("buyer_current_offer", 0)
    seller_counter = seller_message.get("price", 0)

    if buyer_offer > 0 and seller_counter > 0:
        gap_pct = abs(seller_counter - buyer_offer) / max(seller_counter, buyer_offer)
        if gap_pct <= 0.02:
            midpoint = (buyer_offer + seller_counter) / 2
            agreed_price = round(midpoint)
            new_status = "agreed"
            print(f"[LangGraph] Auto-accept: offers within {gap_pct:.1%}, agreeing at ${agreed_price:,.0f}")
```

**Walk through the logic:**

> "Two guard conditions: `if new_status == 'negotiating'` — we only apply this when neither side has already agreed or rejected. And `if buyer_offer > 0 and seller_counter > 0` — we need both prices to be real values, not the initial zeros.

> The gap formula: `abs(seller - buyer) / max(seller, buyer)`. Why max? We want the gap as a percentage of the *higher* price. This gives us the worst-case gap. At 2% on a $485K property, that's about $9,700. That's within closing cost territory — often worth splitting rather than negotiating over."

**Show the threshold trade-off table:**

| Threshold | Behavior |
|-----------|----------|
| 0% | Almost never triggers — agents rarely offer identical prices |
| 2% (solution default) | Good balance — catches near-agreements |
| 5% | Triggers too early — could short-circuit good negotiations |
| 10% | Essentially skips negotiation |

**Run and show:**
```bash
python m3_langgraph_multiagents/main_langgraph_multiagent.py --rounds 5
```
> "Run this a few times. When you see `[LangGraph] Auto-accept: offers within X%, agreeing at $Y`, that's the convergence logic firing. The negotiation ends early instead of wasting remaining rounds."

---

---

# MODULE 4 — Google ADK + A2A Protocol

## Stage-Setting (Say This Before Exercises)

> "Modules 1-3 built a complete negotiation system, but all agents ran in the same process. Module 4 makes agents real networked services.
>
> Two new things here: **Google ADK** (Agent Development Kit) as the agent runtime, and **A2A Protocol** (Agent-to-Agent) as the communication standard. ADK gives us a standardized way to build agents with tools. A2A gives us a standardized way for those agents to talk to each other over HTTP.
>
> The key shift: in M3, buyer and seller were LangGraph nodes sharing a Python state dict. In M4, they're separate HTTP services. The seller runs in Terminal 1 as an HTTP server. The buyer runs in Terminal 2 and sends JSON-RPC requests to the seller's URL. They have no shared memory — all communication is over the network.
>
> The A2A protocol has two parts: **Agent Card discovery** (how a client finds what an agent can do, before connecting) and **message/send** (how it sends tasks and receives responses). Today you'll work with both."

**Key concepts to reinforce:**
- Agent Card at `/.well-known/agent-card.json` — the agent's identity document
- A2A uses JSON-RPC over HTTP — same principles as MCP but for whole agents, not tools
- ADK `MCPToolset` wraps MCP servers — so agents still get real market data, just via a different runtime
- `SESSION_REGISTRY` — each session gets its own agent instance, isolated state

---

## M4 Exercises — Introduce All At Once

### Exercise 1 — Fetch and Inspect the Agent Card `[Core]`

**What to say:**

> "Exercise 1 teaches A2A discovery. Before a buyer agent talks to a seller, it needs to know the seller exists and what it can do. The Agent Card is how agents announce themselves — it's a JSON document at a well-known URL that describes the agent's name, skills, capabilities, and how to reach it.
>
> You'll write a small Python script that fetches this card and prints it. The code is straightforward — async HTTP GET, parse JSON, pretty-print fields. The learning is in *comparing* this to MCP tool discovery: MCP uses `list_tools()` over an active session, A2A uses a static HTTP endpoint you can hit before any session starts.
>
> Think of the Agent Card as an agent's business card. You read it in the lobby before the meeting starts."

**Setup reminder:**
> "Remember: you need Terminal 1 running the seller server before your discovery script works. Two-terminal setup is the M4 pattern."

---

### Exercise 2 — Add a Negotiation History Endpoint `[Core]`

**What to say:**

> "Exercise 2 adds observability to the seller server — a `/history/{session_id}` REST endpoint that returns the agent's conversation history as JSON.
>
> The interesting part is the architecture: you're adding a REST endpoint *alongside* the A2A JSON-RPC endpoint, on the same FastAPI app. `A2AFastAPIApplication.build()` returns a standard FastAPI app object. You can add any routes to it before the server starts.
>
> This is a common pattern in production: your primary protocol (A2A JSON-RPC) handles agent communication, while secondary endpoints handle ops — health checks, metrics, history, debugging. They coexist on the same server."

**Reflection to tease:**
> "Should agent history be publicly accessible? Think about what the seller's conversation contains: its minimum acceptable price, its strategy, its reasoning. That's sensitive. In production, this endpoint needs authentication. Keep that in mind when you design your solution."

---

### Exercise 3 — Docker Deployment `[Stretch]`

**What to say:**

> "The stretch exercise takes everything to production: containerize the seller agent with Docker. The buyer runs locally, the seller runs in a container, and they communicate over HTTP. This is the real deployment pattern.
>
> The interesting challenge is network configuration: the buyer needs to reach the seller at `http://localhost:9102`. Inside Docker, 'localhost' means the container, not your machine. You need `--network host` or port mapping. That's a real production concern."

---

## M4 Solutions — How to Walk Through Them

### Solution 1 — Agent Card Fetch Walkthrough

**Before showing, run the setup:**

```bash
# Terminal 1:
python m4_adk_multiagents/a2a_protocol_seller_server.py --port 9102
```

**Show the complete script:**

```python
import asyncio, json, httpx

async def main():
    url = "http://127.0.0.1:9102/.well-known/agent-card.json"
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        card = response.json()

    print(f"Name:    {card['name']}")
    print(f"Version: {card['version']}")
    print(f"Skills:  {[s['name'] for s in card.get('skills', [])]}")
    print(json.dumps(card, indent=2))
```

**Walk through and explain:**

> "One HTTP GET to `/.well-known/agent-card.json`. This URL is standardized — any A2A-compliant agent serves its card at this path. It's like `robots.txt` for agents.

> The card contains: name, version, description, capabilities (streaming? push notifications?), skills (what the agent can do), and provider info.

> Now compare to MCP tool discovery: MCP uses `list_tools()` — you need an active connection to learn what tools exist. A2A uses a static HTTP endpoint — you can discover the agent with a single GET request before any session. That's earlier in the lifecycle and requires no authentication."

**Show the comparison table:**

| Aspect | MCP Tool Discovery | A2A Agent Card |
|--------|-------------------|----------------|
| Scope | Individual function | Entire agent + skills |
| Protocol | `list_tools()` over active session | HTTP GET to static URL |
| Timing | After connection | Before any connection |
| Schema | JSON Schema per parameter | Skill descriptions + examples |

---

### Solution 2 — History Endpoint Walkthrough

**Show where the code goes:**

> "The key insight: `app_builder.build()` returns a standard FastAPI `app`. You can add routes to a FastAPI app at any time before the server starts. So we add our REST route right after `build()`."

```python
app = app_builder.build(agent_card_url="/.well-known/agent-card.json", rpc_url="/")

# NEW: Add history endpoint for observability
@app.get("/history/{session_id}")
async def get_history(session_id: str):
    agents = SESSION_REGISTRY._agents
    agent = agents.get(session_id)
    if agent is None:
        return {"error": f"No session found: {session_id}", "sessions": list(agents.keys())}

    history = []
    for msg in agent.llm_messages:
        if isinstance(msg, dict) and msg.get("role") == "assistant":
            history.append({
                "role": msg["role"],
                "content": msg.get("content", "")[:300],
            })

    return {"session_id": session_id, "message_count": len(history), "history": history}
```

**Walk through key points:**

> "`SESSION_REGISTRY._agents` — this is a dict from session_id to `SellerAgentADK` instances. Each A2A session gets its own agent.

> `agent.llm_messages` — the agent's LLM conversation history. We filter to assistant messages only (the agent's responses) and truncate to 300 chars.

> Note: the session ID has a prefix. The orchestrator uses session `a2a_http_abc123`, but the registry key is `seller_a2a_a2a_http_abc123`. Check the server logs for the exact ID."

**Answer the reflection:**
> "Should this be public? No. This endpoint exposes sensitive negotiation data — the seller's strategy, its minimum price reasoning, its internal monologue. In production:
> - Add authentication (JWT or API key)
> - Rate limit the endpoint
> - Consider a logging sidecar (OpenTelemetry, Datadog) instead of a public REST endpoint
>
> But for debugging and observability during development, this pattern is extremely useful."

**Test the full flow:**
```bash
# Terminal 1: seller server
# Terminal 2: one round of negotiation
python m4_adk_multiagents/a2a_protocol_http_orchestrator.py --seller-url http://127.0.0.1:9102 --rounds 1
# Terminal 3: check history
curl http://127.0.0.1:9102/history/<session_id>
```

---

---

# Interactive Breaks in Solution Code

## What You Can Do

The main code files already support step-by-step mode:

| Module | Run Command | Interactive Flag |
|--------|-------------|-----------------|
| M1 | `python m1_baseline/state_machine.py` | Default is step-by-step, `--fast` to skip |
| M1 | `python m1_baseline/naive_negotiation.py` | Default is step-by-step, `--fast` to skip |
| M3 | `python m3_langgraph_multiagents/main_langgraph_multiagent.py` | Add `--step` for turn-by-turn pauses |
| M4 | `python m4_adk_multiagents/a2a_protocol_http_orchestrator.py --seller-url http://127.0.0.1:9102` | Add `--demo` for code walkthrough with pauses |

## Recommended Flow for Each Module's Solution Session

### M1 Solutions
1. Show the solution code in the editor (split-screen: exercise .md on left, state_machine.py on right)
2. Make the changes live while explaining each step
3. Run `python m1_baseline/state_machine.py` — it pauses at each step automatically
4. Press ENTER to advance through each scenario

### M2 Solutions
1. Show `pricing_server.py` — add the tax tool live
2. Show `buyer_simple.py` — update the prompts live
3. Run the full system: `python m3_langgraph_multiagents/main_langgraph_multiagent.py --rounds 2 --step`
4. Watch for the buyer's MCP tool calls — does it call `get_property_tax_estimate`?

### M3 Solutions
1. Show `langgraph_flow.py` — open `route_after_seller()` and `seller_node()`
2. Add the deadlock detection live (Ex1)
3. Add the convergence logic live (Ex2)
4. Run: `python m3_langgraph_multiagents/main_langgraph_multiagent.py --rounds 5 --step`
5. Each turn pauses at `[ENTER: next turn →]` — explain the graph routing decision shown

### M4 Solutions
1. Open two terminals side-by-side
2. Terminal 1: `python m4_adk_multiagents/a2a_protocol_seller_server.py --port 9102`
3. Terminal 2: `python m4_adk_multiagents/fetch_agent_card.py`
4. Show the agent card output and explain each field
5. Add the `/history` endpoint to the server live (restart required)
6. Run orchestrator for 1 round, then curl the history endpoint

---

## Key Transition Lines Between Modules

Use these to connect solutions across modules during the session:

- **After M1 solutions:** "We've proven termination. But prices are still hardcoded. That's where M2 comes in."
- **After M2 solutions:** "We have real data now. But agents still communicate with raw strings — no schema. M3 fixes that, and adds the graph-level workflow."
- **After M3 solutions:** "We have a complete, schema-validated, graph-orchestrated negotiation. But it's all in one process. M4 makes agents real network services."
- **After M4 solutions:** "This is what production multi-agent systems look like: independent services, standardized protocols, observable state, containerized deployment."

---

## Timing Guide

| Module | Intro + Exercises | Solution Walkthrough | Total |
|--------|------------------|---------------------|-------|
| M1 | 10 min intro + 15 min exercise time | 15 min | ~40 min |
| M2 | 8 min intro + 15 min exercise time | 12 min | ~35 min |
| M3 | 10 min intro + 20 min exercise time | 20 min | ~50 min |
| M4 | 10 min intro + 15 min exercise time | 15 min | ~40 min |
| **Total** | | | **~2.75 hours** |

---

## Common Student Questions and Answers

**Q: Why not just use `asyncio.sleep()` instead of a deadline check for TIMEOUT?**
> A: Sleep pauses the coroutine but doesn't bound the total time. A wall-clock check (`time.time()`) is correct for real deadlines. Also, sleep doesn't help if the LLM itself is slow — the timeout needs to be checked at the FSM level.

**Q: Why does MCP use JSON-RPC instead of REST?**
> A: JSON-RPC is better for tool calling because it supports method invocation with named parameters. REST is resource-oriented (CRUD). Tools are actions, not resources. A2A also uses JSON-RPC for the same reason.

**Q: In LangGraph, why can't I mutate state directly inside a router?**
> A: Routers are pure functions. LangGraph may cache their results or call them multiple times. Mutations would cause non-deterministic behavior. The contract is: routers read state, nodes mutate state.

**Q: What happens if two students' solutions have different convergence thresholds?**
> A: That's the point. Show both. The 2% default is a reasonable starting point for real estate, but the "right" threshold depends on market conditions, agent patience, and acceptable deal quality.

**Q: Can the A2A seller server handle multiple concurrent sessions?**
> A: Yes — `SESSION_REGISTRY` maintains one `SellerAgentADK` per session ID. But they all run on the same Python event loop. For true parallel load, you'd need multiple uvicorn workers or a process-based deployment.
