"""Command-line entry point for Minimal Harness."""

import argparse
import os
import sys
from pathlib import Path

from .agent import Agent
from .models import SearchConfig
from .openrouter import OpenRouterClient, OpenRouterError
from .pipeline import SearchPipeline
from .provider import ProviderCatalog
from .session import Session
from .tui import TUI


class Arguments(argparse.Namespace):
    """Store parsed command-line options."""


OPTION_SPECS = [
    (("--optimize",), {"action": "store_true"}),
    (("--list-models",), {"action": "store_true"}),
    (("--free-only",), {"action": "store_true"}),
    (("--interactive",), {"action": "store_true"}),
    (("--tui",), {"action": "store_true"}),
    (("--session",), {}),
    (("--model",), {}),
    (("--workspace",), {"default": "."}),
    (("--max-turns",), {"type": int, "default": 24}),
    (("--iterations",), {"type": int, "default": 5}),
    (("--target-score",), {"type": float, "default": 1.0}),
    (("--no-docker",), {"action": "store_true"}),
    (("--no-web",), {"action": "store_true"}),
]


def main() -> None:
    """Parse arguments and dispatch the requested mode.

    Returns
    -------
    None
        The selected command writes its output.
    """
    _load_env()
    _dispatch(_parse_args())


def _parse_args() -> Arguments:
    """Parse command-line arguments.

    Returns
    -------
    Arguments
        Parsed command-line options.
    """
    parser = argparse.ArgumentParser(description="Run Minimal Harness")
    parser.add_argument("seed", nargs="?")
    _add_options(parser)
    return parser.parse_args(namespace=Arguments())


def _add_options(parser: argparse.ArgumentParser) -> None:
    """Add supported command-line options.

    Parameters
    ----------
    parser : argparse.ArgumentParser
        Parser to configure.

    Returns
    -------
    None
        Options are added in place.
    """
    for args, kwargs in OPTION_SPECS:
        parser.add_argument(*args, **kwargs)


def _dispatch(args: Arguments) -> None:
    """Dispatch model listing or agent execution.

    Parameters
    ----------
    args : Arguments
        Parsed command-line options.

    Returns
    -------
    None
        The selected command is executed.
    """
    if args.list_models:
        _print_models(args.free_only)
        return
    try:
        _run_mode(args)
    except OpenRouterError as exc:
        print(f"OpenRouter error: {exc}")
        sys.exit(1)


def _run_mode(args: Arguments) -> None:
    """Run answer, interactive, TUI, or optimization mode.

    Parameters
    ----------
    args : Arguments
        Parsed command-line options.

    Returns
    -------
    None
        The selected mode writes its output.
    """
    if args.optimize:
        _print_result(SearchPipeline(_config(args)).run(args.seed or ""))
        return
    _run_agent(args)


def _run_agent(args: Arguments) -> None:
    """Run the configured agent frontend.

    Parameters
    ----------
    args : Arguments
        Parsed command-line options.

    Returns
    -------
    None
        Agent output is printed.
    """
    _frontend(args, _new_agent(args))


def _new_agent(args: Arguments) -> Agent:
    """Create an agent from command-line options.

    Parameters
    ----------
    args : Arguments
        Parsed options.

    Returns
    -------
    Agent
        Configured agent.
    """
    return Agent(
        args.workspace,
        OpenRouterClient(args.model),
        args.max_turns,
        _session(args),
    )


def _frontend(args: Arguments, agent: Agent) -> None:
    """Dispatch one configured agent frontend.

    Parameters
    ----------
    args : Arguments
        Parsed options.
    agent : Agent
        Configured agent.

    Returns
    -------
    None
        Selected frontend runs in place.
    """
    if args.tui:
        TUI(agent).run()
    elif args.interactive:
        _repl(agent)
    else:
        print(agent.run(args.seed or ""))


def _session(args: Arguments) -> Session | None:
    """Create an optional persistent session.

    Parameters
    ----------
    args : Arguments
        Parsed command-line options.

    Returns
    -------
    Session or None
        Persistent session when requested.
    """
    return Session(args.session) if args.session else None


def _print_models(free_only: bool) -> None:
    """Print provider model identifiers.

    Parameters
    ----------
    free_only : bool
        Restrict output to free models.

    Returns
    -------
    None
        Identifiers are printed.
    """
    catalog = ProviderCatalog()
    models = catalog.free_models() if free_only else catalog.list_models()
    for model in models:
        print(model.get("id", "unknown"))


def _repl(agent: Agent) -> None:
    """Run the line-oriented interactive frontend.

    Parameters
    ----------
    agent : Agent
        Stateful agent.

    Returns
    -------
    None
        REPL runs until quit or EOF.
    """
    print("Minimal Harness interactive mode. Type /quit to exit.")
    while _repl_step(agent):
        pass


def _repl_step(agent: Agent) -> bool:
    """Process one REPL prompt.

    Parameters
    ----------
    agent : Agent
        Stateful agent.

    Returns
    -------
    bool
        Whether the REPL continues.
    """
    try:
        prompt = input("you> ")
    except EOFError:
        return False
    return _run_prompt(agent, prompt)


def _run_prompt(agent: Agent, prompt: str) -> bool:
    """Process one REPL prompt.

    Parameters
    ----------
    agent : Agent
        Stateful agent.
    prompt : str
        Input prompt.

    Returns
    -------
    bool
        Whether the REPL continues.
    """
    if prompt.strip() == "/quit":
        return False
    if prompt.strip():
        print(f"agent> {agent.run(prompt)}")
    return True


def _load_env() -> None:
    """Load local environment assignments.

    Returns
    -------
    None
        Environment is updated without overriding shell values.
    """
    path = Path(".env")
    if path.exists():
        for line in path.read_text().splitlines():
            _load_env_line(line)


def _load_env_line(line: str) -> None:
    """Load one environment assignment.

    Parameters
    ----------
    line : str
        Environment file line.

    Returns
    -------
    None
        A valid assignment is loaded.
    """
    text = line.strip()
    if "=" in text and not text.startswith("#"):
        key, value = text.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def _config(args: Arguments) -> SearchConfig:
    """Build optimization settings.

    Parameters
    ----------
    args : Arguments
        Parsed command-line options.

    Returns
    -------
    SearchConfig
        Configured optimization settings.
    """
    return SearchConfig(
        args.iterations,
        2,
        args.target_score,
        not args.no_docker,
        not args.no_web,
    )


def _print_result(result) -> None:
    """Print an optimization result.

    Parameters
    ----------
    result : SearchResult
        Completed search result.

    Returns
    -------
    None
        Result summary is printed.
    """
    winner = result.winner.candidate_id if result.winner else "none"
    score = result.winner.score if result.winner else 0.0
    print(f"winner={winner} score={score}")
    print(result.stop_reason)


if __name__ == "__main__":
    main()
