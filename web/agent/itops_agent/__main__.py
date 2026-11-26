"""Agent command line.

  itops-agent enroll --server https://prov.example.com --code ABCD-EFGH-JKLM-NPQR
  itops-agent run                 foreground (Ctrl+C to stop); logs to console + file
  itops-agent status
  itops-agent service install|start|stop|remove     (Windows, needs admin)
  itops-agent forget              delete local enrollment (machine must be re-enrolled)
"""
import argparse
import asyncio
import logging
import logging.handlers
import os
import signal
import sys

from . import VERSION
from .client import Agent, EnrollError, check_server_url, enroll
from .paths import state_dir
from .state import State


def setup_logging(console: bool = True) -> None:
    d = state_dir()
    d.mkdir(parents=True, exist_ok=True)
    handlers: list[logging.Handler] = [
        logging.handlers.RotatingFileHandler(d / "agent.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    ]
    if console:
        handlers.append(logging.StreamHandler())
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s", handlers=handlers
    )


async def run_agent() -> int:
    state = State.load()
    if state is None:
        logging.error("not enrolled; run: itops-agent enroll --server URL --code CODE")
        return 2
    agent = Agent(state)
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, agent.stop)
        except NotImplementedError:  # Windows: Ctrl+C raises KeyboardInterrupt instead
            pass
    await agent.run_forever()
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["service-run"]:  # launched by the Service Control Manager (frozen exe)
        from . import service

        service.run_as_service()
        return 0
    p = argparse.ArgumentParser(prog="itops-agent", description=f"IT Provisioning agent {VERSION}")
    sub = p.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("enroll")
    e.add_argument("--server", required=True)
    e.add_argument("--code", required=True)
    e.add_argument("--insecure-http", action="store_true", help="allow http:// to a non-local host (testing only)")
    sub.add_parser("run")
    sub.add_parser("status")
    sub.add_parser("forget")
    s = sub.add_parser("service")
    s.add_argument("op", choices=["install", "start", "stop", "remove"])
    args = p.parse_args(argv)

    if args.cmd == "enroll":
        setup_logging()
        try:
            url = check_server_url(args.server, args.insecure_http)
            st = enroll(url, args.code)
        except (ValueError, EnrollError) as err:
            print(f"Enrollment failed: {err}", file=sys.stderr)
            return 1
        print(f"Enrolled. Machine id {st.machine_id}. State saved in {state_dir()}")
        return 0
    if args.cmd == "run":
        setup_logging()
        try:
            return asyncio.run(run_agent())
        except KeyboardInterrupt:
            return 0
    if args.cmd == "status":
        st = State.load()
        print(f"agent {VERSION}; state dir {state_dir()}")
        print(f"enrolled to {st.server_url} as {st.machine_id}" if st else "not enrolled")
        return 0
    if args.cmd == "forget":
        State.clear()
        print("Local enrollment removed.")
        return 0
    if args.cmd == "service":
        if os.name != "nt":
            print("Windows only", file=sys.stderr)
            return 1
        from . import service

        return service.manage(args.op)
    return 1


if __name__ == "__main__":
    sys.exit(main())
