# Examples — Plugging in Your Own Agent

This directory contains a sample LangGraph customer-support agent in two
versions — `v1_brusque` and `v2_polite` — so the Compare view has a clear
story: v2 beats v1 on politeness by a wide margin.

---

## Running the example agents

### 1. Install dependencies

The LangGraph deps are an optional extra to keep the core install lean:

```bash
pip install -e ".[examples]"
```

You also need an Anthropic API key:

```bash
export ANTHROPIC_API_KEY=sk-...
```

### 2. Seed the database

```bash
python scripts/seed.py
```

This registers both agent versions (`customer_support_v1` / `customer_support_v2`),
the `customer_support` suite (20 cases), and the `json_extraction` suite (15 cases).

### 3. Start the stack and run an eval

```bash
make demo        # starts FastAPI + Streamlit
```

In the UI:
1. Open the **customer_support** suite.
2. Select **customer_support_v1**, hit **Run**.
3. Run again with **customer_support_v2**.
4. Open the **Compare** tab → politeness delta should be clearly positive for v2.

---

## Adapter contracts

Agent Eval Lab supports two adapter types. Both expect the same input/output shape.

### HTTP adapter

Register an agent that exposes a `POST /chat` endpoint:

**Request body** (JSON):
```json
{"role": "user", "content": "Where is my order?"}
```

**Response body** (JSON):
```json
{
  "response": "Your order shipped on Monday.",
  "turns": [
    {"role": "user",    "content": "Where is my order?"},
    {"role": "assistant","content": "Your order shipped on Monday."}
  ],
  "tokens": 42
}
```

`turns` is optional but required for the trace drawer. `tokens` is optional.

**Register via seed script:**
```python
register_agent_version(
    "my_http_agent",
    "http",
    {"url": "http://localhost:8000/chat", "timeout_s": 30},
    session,
)
```

### Python adapter

Register a Python callable in any importable module:

```python
# myproject/my_agent.py

_model = None   # lazy-init avoids loading the model on import

def run_agent(input_dict: dict) -> dict:
    global _model
    if _model is None:
        _model = load_my_expensive_model()

    response_text = _model.chat(input_dict["content"])
    return {
        "response": response_text,
        "turns": [
            {"role": "user",     "content": input_dict["content"]},
            {"role": "assistant","content": response_text},
        ],
        "tokens": None,
    }
```

**Entrypoint string format:** `"<dotted.module.path>:<function_name>"`

**Register via seed script:**
```python
register_agent_version(
    "my_python_agent",
    "python",
    {"entrypoint": "myproject.my_agent:run_agent"},
    session,
)
```

> **Important:** run `python scripts/seed.py` from the repo root so that
> `myproject/` is on `sys.path`. Alternatively, install your package with
> `pip install -e .` before seeding.

---

## v1 vs v2 compare story

| Version | System prompt style | Expected polite score |
|---------|--------------------|-----------------------|
| `customer_support_v1` | Terse, no apologies | ~2 / 5 |
| `customer_support_v2` | Warm, empathetic | ~4.5 / 5 |

After running both versions against the `customer_support` suite, the
Compare tab will show a clear +2–3 point delta on the `polite` criterion,
while `concise` may drop slightly for v2 (more words = less concise).
This is the exact trade-off the heatmap is designed to surface.
