"""Command-line entry point for Minimal Harness."""

import argparse
import os
import sys
from pathlib import Path

from .agent import Agent
from .inspector import print_run
from .models import SearchConfig
from .openrouter import OpenRouterClient, OpenRouterError
from .pipeline import SearchPipeline
from .progress import ProgressTUI
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
    (("--task-manifest",), {"default": None}),
    (("--show-run",), {"default": None}),
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
    if args.show_run:
        sys.exit(print_run(Path(args.show_run)))
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
        _run_optimize(args)
        return
    _run_agent(args)


def _run_optimize(args: Arguments) -> None:
    """Run the search pipeline behind a live dashboard or plain output.

    Parameters
    ----------
    args : Arguments
        Parsed command-line options.

    Returns
    -------
    None
        The search runs and its outcome is displayed.
    """
    pipeline = SearchPipeline(_config(args))
    if _use_progress():
        ProgressTUI(pipeline, args.seed or "").run()
    else:
        _run_optimize_plain(pipeline, args)


def _use_progress() -> bool:
    """Return whether the interactive progress dashboard should run.

    Returns
    -------
    bool
        ``True`` only when standard output is a real terminal.
    """
    return sys.stdout.isatty()


def _run_optimize_plain(pipeline: SearchPipeline, args: Arguments) -> None:
    """Run the search pipeline and print result plus usage summary.

    Parameters
    ----------
    pipeline : SearchPipeline
        Configured search pipeline.
    args : Arguments
        Parsed command-line options.

    Returns
    -------
    None
        Result and usage are printed.
    """
    _print_result(pipeline.run(args.seed or ""))
    print(f"usage: {pipeline.client.usage_summary()}")


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
    agent.tools.questioner = _repl_questioner
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


def _repl_questioner(question: str, options: list[str]) -> str:
    """Ask a numbered question in the line-oriented REPL.

    Parameters
    ----------
    question : str
        Question text.
    options : list[str]
        Suggested answers.

    Returns
    -------
    str
        Selected option or typed answer.
    """
    print(f"? {question}")
    for index, option in enumerate(options, 1):
        print(f"  [{index}] {option}")
    print("  [0] type your own")
    return _repl_answer(input("answer> ").strip(), options)


def _repl_answer(raw: str, options: list[str]) -> str:
    """Resolve a typed REPL answer into option text.

    Parameters
    ----------
    raw : str
        Typed response.
    options : list[str]
        Suggested answers.

    Returns
    -------
    str
        Selected option or the typed text.
    """
    if raw.isdigit():
        index = int(raw)
        if 1 <= index <= len(options):
            return options[index - 1]
    return raw if raw else "no answer"


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
        _print_repl_suggestions(agent)
    return True


def _print_repl_suggestions(agent: Agent) -> None:
    """Print the agent's suggestions as a numbered list.

    Parameters
    ----------
    agent : Agent
        Agent whose suggestions should be shown.

    Returns
    -------
    None
        Suggestions are printed when present.
    """
    suggestions = getattr(agent.tools, "suggestions", None)
    agent.tools.suggestions = []
    if isinstance(suggestions, (list, tuple)) and suggestions:
        print("Suggestions:")
        for index, item in enumerate(suggestions, 1):
            print(f"  [{index}] {item}")


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
        iterations=args.iterations,
        target_score=args.target_score,
        use_docker=not args.no_docker,
        use_web_search=not args.no_web,
        task_manifest=args.task_manifest,
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
