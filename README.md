# luc-plan

`luc-plan` adds a user-visible planning workflow to luc using only runtime package surfaces. It gives the model an `update_plan` tool, stores the current plan in luc extension session storage, emits timeline notes when the plan changes, and exposes a read-only Plan inspector tab.

## Runtime surfaces

This package includes:

- `luc.extension/v1` host (`extensions/plan.yaml`, `extensions/host.py`) for session state, diffing, markdown rendering, timeline notes, and prompt context.
- `luc.tool/v2` hosted tools:
  - `update_plan` creates or updates the current plan.
  - `plan_status` shows the current plan.
- `luc.ui/v1` Plan inspector tab and `Open Plan` command.
- `luc.prompt/v1` guidance that tells the model when and how to use `update_plan`.

No luc core changes are required.

## Install

From the package repository:

```sh
luc pkg install github.com/lutefd/luc-plan@latest
```

During local development, install from a local checkout:

```sh
luc pkg install ../luc-plan --scope user
```

After installing or updating the package, reload luc:

```sh
luc reload
```

You can also use luc's interactive reload shortcut if available in your client.

## Usage

For multi-step work, ambiguous work, or tasks that require several tool calls, the prompt extension instructs the AI to call `update_plan`. Trivial one-step requests should not create a plan.

Plan updates are shown separately as timeline notes. The assistant should not repeat the full plan in normal chat unless you ask for it.

To inspect the current plan manually:

1. Run the `Open Plan` command from luc's command palette, or open the runtime inspector tab named **Plan**.
2. The Plan tab renders the output of `plan_status` as markdown.

You can also ask the model to show the current plan; it may call `plan_status`.

## Plan behavior

An initial `update_plan` emits a **Created Plan** timeline note. Later updates emit **Updated Plan** notes that summarize:

- added items
- removed items
- status changes
- text changes
- reordered items

Current item statuses are rendered as:

- `[ ]` pending
- `▶️` active
- `[x]` done
- `[!]` blocked
- `[-]` canceled

## Privacy and storage

The current plan is stored in luc session extension storage for the `plan` extension. It persists across extension host restarts within the same luc session. The package only injects compact hidden prompt context when a plan exists, for example the current item statuses and text.

## Troubleshooting

If the tools, prompt guidance, or Plan tab do not appear after install or update, reload luc:

```sh
luc reload
```

If the Plan tab is empty, no plan has been created yet. Start a multi-step task or ask the model to create a plan.

If `update_plan` rejects an update, check that every item has a non-empty stable `id`, non-empty `text`, a valid `status`, and that ids are not duplicated.

## Development

This repository is itself a luc package. Install it from a sibling checkout during development:

```sh
luc pkg install ../luc-plan --scope user
luc reload
```

The Python host has no third-party dependencies. A quick syntax check is:

```sh
python3 -m py_compile extensions/host.py
```
