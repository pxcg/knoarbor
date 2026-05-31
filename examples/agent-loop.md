# Agent Loop and Control Patterns

Agent Loop is the core execution pattern behind many tool-using AI agents. A typical loop follows this shape:

```text
user input -> model reasoning -> tool call -> observation -> next reasoning step -> final answer
```

The loop continues until the model no longer needs tools and can return a final response.

## Core Loop

The basic loop contains four responsibilities:

- Keep the conversation state.
- Ask the model for the next action.
- Execute requested tools.
- Feed tool results back into the model.

In pseudocode:

```python
messages = [{"role": "user", "content": user_input}]

while True:
    response = llm.chat(messages, tools=tools)
    if response.tool_calls:
        results = run_tools(response.tool_calls)
        messages.extend(results)
        continue
    return response.text
```

## Control Patterns

Agent systems often add structured control patterns on top of the basic loop:

- Prompt chaining: split a task into a sequence of model calls.
- Routing: classify the request and send it to the right handler.
- Parallelization: run independent subtasks at the same time.
- Orchestrator-workers: let one model plan and delegate work to specialized workers.
- Evaluator-optimizer: generate a draft, evaluate it, and improve it iteratively.

## Workflow vs Agent

A workflow is better when the steps are predictable and deterministic. An agent loop is better when the system must decide which tools to use, recover from partial results, and adapt its next step based on observations.

## Practical Guardrails

Production agent loops usually need:

- A maximum iteration count.
- Tool timeout and error handling.
- State persistence.
- Memory compaction.
- Audit logs for tool calls and final outputs.

Without these guardrails, an agent loop can waste tokens, repeat tool calls, or fail to explain why it reached a final answer.
