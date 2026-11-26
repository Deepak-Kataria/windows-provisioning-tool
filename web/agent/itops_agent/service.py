"""Windows service wrapper (pywin32). The service runs as LocalSystem, starts automatically,
and restarts itself on failure."""
import asyncio
import logging
import subprocess
import sys

import servicemanager
import win32event
import win32service
import win32serviceutil

from .client import Agent
from .state import State

SERVICE_NAME = "ITOpsAgent"
DISPLAY_NAME = "IT Provisioning Agent"


class AgentService(win32serviceutil.ServiceFramework):
    _svc_name_ = SERVICE_NAME
    _svc_display_name_ = DISPLAY_NAME
    _svc_description_ = "Runs approved provisioning actions sent by the IT Provisioning server."

    def __init__(self, args):
        super().__init__(args)
        self.stop_event = win32event.CreateEvent(None, 0, 0, None)
        self.loop: asyncio.AbstractEventLoop | None = None
        self.agent: Agent | None = None

    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        if self.loop and self.agent:
            self.loop.call_soon_threadsafe(self.agent.stop)
        win32event.SetEvent(self.stop_event)

    def SvcDoRun(self):
        from .__main__ import setup_logging

        setup_logging(console=False)
        state = State.load()
        if state is None:
            logging.error("service started but agent is not enrolled")
            return
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.agent = Agent(state)
        servicemanager.LogInfoMsg(f"{SERVICE_NAME} started")
        self.loop.run_until_complete(self.agent.run_forever())
        self.loop.close()


def _set_recovery() -> None:
    # restart after 10s, 30s, 60s; reset failure count after a day
    subprocess.run(
        ["sc.exe", "failure", SERVICE_NAME, "reset=", "86400", "actions=",
         "restart/10000/restart/30000/restart/60000"],
        check=False, capture_output=True,
    )


def manage(op: str) -> int:
    if op == "install":
        exe = sys.executable
        frozen = getattr(sys, "frozen", False)
        win32serviceutil.InstallService(
            None if frozen else f"{__name__}.AgentService",
            SERVICE_NAME,
            DISPLAY_NAME,
            startType=win32service.SERVICE_AUTO_START,
            exeName=exe if frozen else None,
            exeArgs="service-run" if frozen else None,
            description=AgentService._svc_description_,
        )
        _set_recovery()
        print("Service installed.")
    elif op == "start":
        win32serviceutil.StartService(SERVICE_NAME)
        print("Service started.")
    elif op == "stop":
        win32serviceutil.StopService(SERVICE_NAME)
        print("Service stopped.")
    elif op == "remove":
        win32serviceutil.RemoveService(SERVICE_NAME)
        print("Service removed.")
    return 0


def run_as_service() -> None:
    """Entry point when the frozen exe is launched by the Service Control Manager."""
    servicemanager.Initialize()
    servicemanager.PrepareToHostSingle(AgentService)
    servicemanager.StartServiceCtrlDispatcher()
