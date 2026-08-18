import logging
import os
import shutil
import subprocess
import threading
import time
from datetime import datetime, timezone
from typing import Optional

from backend.app.config import settings
from backend.app.graph.client import graph_client


logger = logging.getLogger("echotrace.engine.watchdog")


class StoreWatchdog(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True, name="hydradb-store-watchdog")
        self._stop_event = threading.Event()
        self.consecutive_failures = 0
        self.last_probe_at: Optional[str] = None
        self.last_recovery_at: Optional[str] = None
        self.recovery_count = 0

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        while not self._stop_event.wait(settings.hydradb_watchdog_interval):
            self.check_now()

    def check_now(self) -> bool:
        self.last_probe_at = datetime.now(timezone.utc).isoformat()
        if not graph_client.connected_to_hydradb or not graph_client.bolt_driver:
            if graph_client.store_degraded and graph_client.reconnect():
                graph_client.store_degraded = False
                graph_client.degraded_reason = None
                self.consecutive_failures = 0
                self.last_recovery_at = datetime.now(timezone.utc).isoformat()
                logger.info("HydraDB reconnected after store recovery")
                return True
            return False
        try:
            with graph_client.bolt_driver.session() as session:
                session.run(
                    "MATCH (n:EchoTraceNode) RETURN count(*) AS node_count",
                    timeout=settings.hydradb_probe_timeout,
                ).consume()
            self.consecutive_failures = 0
            return True
        except Exception as exc:
            self.consecutive_failures += 1
            graph_client.store_degraded = True
            graph_client.degraded_reason = str(exc)[:500]
            logger.error("HydraDB health probe failed: %s", exc)
            if self.consecutive_failures >= 2:
                self._recover()
            return False

    def _recover(self) -> None:
        if settings.hydradb_auto_reset and self._reset_local_store():
            self.consecutive_failures = 0
            graph_client.store_degraded = False
            graph_client.degraded_reason = None
            self.recovery_count += 1
            self.last_recovery_at = datetime.now(timezone.utc).isoformat()
            logger.warning("HydraDB local store auto-reset completed")
            return

        logger.error(
            "HydraDB remains degraded; switching to the internal graph engine. "
            "Run scripts/reset_store to restore HydraDB-backed mode."
        )
        if graph_client.bolt_driver:
            try:
                graph_client.bolt_driver.close()
            except Exception:
                pass
        graph_client.bolt_driver = None
        graph_client.connected_to_hydradb = False
        graph_client.store_degraded = True

    def _reset_local_store(self) -> bool:
        socket_path = settings.hydradb_docker_socket
        data_dir = settings.hydradb_local_data_dir
        if not os.path.exists(socket_path) or not os.path.isdir(data_dir):
            return False
        try:
            self._docker_post(f"/containers/{settings.hydradb_container_name}/stop?t=10")
            for name in ("store", "cache"):
                path = os.path.join(data_dir, name)
                if os.path.isdir(path):
                    shutil.rmtree(path)
                os.makedirs(path, exist_ok=True)
            self._docker_post(f"/containers/{settings.hydradb_container_name}/start")
            for _ in range(20):
                time.sleep(2)
                if graph_client.reconnect():
                    return True
        except Exception as exc:
            logger.exception("HydraDB auto-reset failed: %s", exc)
        return False

    def _docker_post(self, path: str) -> None:
        command = [
            "curl",
            "--fail",
            "--silent",
            "--show-error",
            "--unix-socket",
            settings.hydradb_docker_socket,
            "-X",
            "POST",
            f"http://localhost{path}",
        ]
        subprocess.run(command, check=True, capture_output=True, text=True, timeout=30)


store_watchdog = StoreWatchdog()
