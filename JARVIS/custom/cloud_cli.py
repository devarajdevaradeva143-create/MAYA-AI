"""``maya-cloud`` — explicit, opt-in Gemini access.

This is deliberately a **separate command** from ``maya``. Nothing here runs
automatically and nothing is sent until the user confirms the exact payload.

Usage:
    maya-cloud status
    maya-cloud set-key                    # hidden prompt → .env
    maya-cloud set-key --from-env --force # automation
    maya-cloud ask "Explain CMake in two lines"
    maya-cloud ask "Summarise this" --file notes.md --yes
    maya-cloud ask "..." --dry-run        # show the request, send nothing
    maya-cloud chat
"""

from __future__ import annotations

import os
from pathlib import Path

import click

from .tools import cloud
from .tools.security import security as security_manager

CLOUD_LOCKED_MESSAGE = (
    "Maya is locked. Cloud access is disabled until you unlock.\n"
    "  maya security unlock <pin>\n"
    "  maya security unlock --face\n"
    "  maya security unlock --voice"
)


class LockedCloudGroup(click.Group):
    """Refuse cloud sends while the Maya session is locked.

    ``maya-cloud`` is a separate command, but a locked session must not leak
    local files to Gemini through it. Status stays available (no key shown).
    """

    def invoke(self, ctx: click.Context):
        args = [*ctx._protected_args, *ctx.args]
        before_separator = args[: args.index("--")] if "--" in args else args
        asks_help = any(arg in ("-h", "--help") for arg in before_separator)
        if args and not asks_help:
            security_manager.reload()
            if security_manager.is_session_locked() and args[0] != "status":
                raise click.ClickException(CLOUD_LOCKED_MESSAGE)
        return super().invoke(ctx)


def _emit(message: str = "") -> None:
    click.echo(message)


def _read_file(path: str) -> str:
    file_path = Path(path).expanduser()
    if not file_path.is_file():
        raise click.ClickException(f"File not found: {path}")
    return file_path.read_text(encoding="utf-8", errors="ignore")


def _preview(prompt: str, files: list[str]) -> None:
    """Show exactly what will leave the laptop, before it leaves."""
    _emit("About to send to Google Gemini (cloud):")
    _emit(f"  model: {cloud.model_name()}")
    _emit(f"  characters: {len(prompt)}")
    if files:
        _emit(f"  files: {', '.join(files)}")
    _emit("  --- prompt preview ---")
    preview = prompt if len(prompt) <= 600 else prompt[:600] + "\n... (truncated)"
    for line in preview.splitlines() or [""]:
        _emit(f"  | {line}")
    _emit("  ----------------------")


@click.group(cls=LockedCloudGroup)
def main() -> None:
    """Maya cloud (Gemini) — separate, permission-first command."""


@main.command()
def status() -> None:
    """Show whether a Gemini key is configured (never prints the key)."""
    st = cloud.status()
    _emit("Cloud (Gemini) Status:")
    _emit(f"  configured: {'yes' if st['configured'] else 'no'}")
    if st["configured"]:
        _emit(f"  key: {st['key_preview']}")
    else:
        _emit(f"  add {cloud.ENV_KEY}=... to {st['env_file']}")
    _emit(f"  model: {st['model']}")
    _emit(f"  endpoint: {st['endpoint']}")
    _emit(f"  env file: {st['env_file']} ({'found' if st['env_file_exists'] else 'missing'})")
    _emit(f"  online log: {st['log_path']}")


@main.command(name="set-key")
@click.option("--from-env", is_flag=True, help="Read GEMINI_API_KEY from the environment.")
@click.option("--force", is_flag=True, help="Replace an existing key without asking.")
def set_key(from_env: bool, force: bool) -> None:
    """Store the Gemini API key in the project .env (hidden input)."""
    if cloud.status()["configured"] and not force:
        click.confirm(f"A {cloud.ENV_KEY} is already configured. Replace it?", abort=True)

    if from_env:
        key = os.environ.get(cloud.ENV_KEY, "").strip()
        if not key:
            raise click.ClickException(f"{cloud.ENV_KEY} is not set in this shell.")
    else:
        key = click.prompt("Gemini API key", hide_input=True, confirmation_prompt=True)

    result = cloud.save_api_key(key)
    if not result["ok"]:
        raise click.ClickException(result["error"])

    _emit(f"Saved {cloud.ENV_KEY} to {result['path']} (value not printed).")
    if not result.get("looks_google"):
        _emit("Warning: the key does not start with 'AIza' — check it is a Gemini API key.")
    _emit("Check it with: maya-cloud status")


@main.command()
@click.argument("prompt")
@click.option("--file", "files", multiple=True, help="Attach a file explicitly.")
@click.option("--system", default=None, help="Optional system instruction.")
@click.option("--model", default=None, help="Override the configured model.")
@click.option("--yes", is_flag=True, help="Skip the confirmation prompt.")
@click.option("--dry-run", is_flag=True, help="Show the request and send nothing.")
@click.option("--no-log", is_flag=True, help="Do not write to memory/online.")
def ask(prompt: str, files, system, model, yes, dry_run, no_log) -> None:
    """Send one prompt to Gemini and print the reply."""
    text = prompt
    if files:
        chunks = []
        for name in files:
            chunks.append(f"\n\n--- file: {name} ---\n{_read_file(name)}")
        text = prompt + "".join(chunks)

    _preview(text, list(files))

    if dry_run:
        _emit("Dry run — nothing was sent.")
        return

    if not yes:
        click.confirm("Send this to Gemini?", abort=True)

    try:
        reply = cloud.ask(text, system=system, model=model)
    except cloud.CloudError as exc:
        raise click.ClickException(str(exc))

    _emit("")
    _emit(reply)

    if not no_log:
        saved = cloud.log_exchange(text, reply, model)
        if saved:
            _emit(f"\n[logged to {saved}]")


@main.command()
@click.option("--system", default=None, help="Optional system instruction.")
@click.option("--no-log", is_flag=True, help="Do not write to memory/online.")
def chat(system, no_log) -> None:
    """Interactive cloud chat. Confirms once, then sends each message."""
    _emit("Cloud chat with Gemini — every message leaves the laptop.")
    _emit("Type 'exit' to stop.")
    click.confirm("Enable cloud chat?", abort=True)

    while True:
        try:
            prompt = click.prompt("You", type=str)
        except (click.Abort, EOFError):
            break
        if prompt.strip().lower() in {"exit", "quit", ":q"}:
            break
        if not prompt.strip():
            continue
        try:
            reply = cloud.ask(prompt, system=system)
        except cloud.CloudError as exc:
            _emit(f"[cloud error] {exc}")
            continue
        _emit(f"Maya (cloud): {reply}")
        if not no_log:
            cloud.log_exchange(prompt, reply)


if __name__ == "__main__":
    main()
