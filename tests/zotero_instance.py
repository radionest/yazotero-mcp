"""Zotero test instance management for isolated E2E testing.

Provides automatic provisioning, lifecycle management, and zombie cleanup
for isolated Zotero 7+ instances running on configurable ports.

Usage:
    guard = ZoteroProcessGuard()
    guard.cleanup_stale()
    pool = ZoteroInstancePool(zotero_bin=Path("/usr/bin/zotero"), guard=guard)
    instance = pool.acquire()
    # ... run tests against instance.port ...
    pool.release_all()
"""

import atexit
import logging
import os
import shutil
import signal
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

logger = logging.getLogger(__name__)

# --- Constants ---

DEFAULT_PORT_RANGE_START = 23200
DEFAULT_PORT_RANGE_END = 23210
DEFAULT_STARTUP_TIMEOUT = 30.0
HEALTH_CHECK_INTERVAL = 0.5

# Zotero preference keys (centralized for compatibility monitoring)
PREF_HTTP_ENABLED = "extensions.zotero.httpServer.enabled"
PREF_HTTP_PORT = "extensions.zotero.httpServer.port"
PREF_CHECK_UPDATES = "extensions.zotero.startup.checkForUpdates"


# --- Value objects ---


@dataclass(frozen=True, slots=True)
class ZoteroPrefs:
    """Preferences for a Zotero test instance's prefs.js."""

    port: int

    def render(self) -> str:
        """Render as Mozilla prefs.js content."""
        return (
            f'user_pref("{PREF_HTTP_ENABLED}", true);\n'
            f'user_pref("{PREF_HTTP_PORT}", {self.port});\n'
            f'user_pref("{PREF_CHECK_UPDATES}", false);\n'
        )


@dataclass(frozen=True, slots=True)
class PidEntry:
    """Parsed content of a PID file."""

    pid: int
    port: int
    profile_dir: Path

    def serialize(self) -> str:
        """Serialize to a simple text format (one field per line)."""
        return f"{self.pid}\n{self.port}\n{self.profile_dir}\n"

    @classmethod
    def deserialize(cls, text: str) -> "PidEntry":
        """Deserialize from text format. Raises ValueError on bad input."""
        lines = text.strip().splitlines()
        if len(lines) < 3:
            raise ValueError(f"Expected 3 lines in PID file, got {len(lines)}")
        return cls(
            pid=int(lines[0]),
            port=int(lines[1]),
            profile_dir=Path(lines[2]),
        )


# --- Process guard ---


class ZoteroProcessGuard:
    """Tracks Zotero test processes via PID files for zombie cleanup.

    PID files are stored in a shared temp directory. On each test session start,
    cleanup_stale() kills leftover processes from crashed previous runs.
    An atexit handler provides a second cleanup layer for normal exits.
    """

    def __init__(self, pid_dir: Path | None = None) -> None:
        self._pid_dir = pid_dir or Path(tempfile.gettempdir()) / "yazot-test-pids"
        self._pid_dir.mkdir(parents=True, exist_ok=True)
        atexit.register(self._atexit_cleanup)

    @property
    def pid_dir(self) -> Path:
        return self._pid_dir

    def register(self, entry: PidEntry) -> None:
        """Write a PID file for a running instance."""
        pid_file = self._pid_dir / f"zotero-{entry.port}.pid"
        pid_file.write_text(entry.serialize())

    def deregister(self, port: int) -> None:
        """Remove PID file for a port."""
        pid_file = self._pid_dir / f"zotero-{port}.pid"
        pid_file.unlink(missing_ok=True)

    def cleanup_stale(self) -> int:
        """Kill stale processes from previous runs. Returns count killed."""
        killed = 0
        for pid_file in self._pid_dir.glob("zotero-*.pid"):
            try:
                entry = PidEntry.deserialize(pid_file.read_text())
                if _is_process_running(entry.pid):
                    os.kill(entry.pid, signal.SIGTERM)
                    killed += 1
                    logger.info(
                        "Killed stale Zotero process PID=%d port=%d",
                        entry.pid,
                        entry.port,
                    )
                if entry.profile_dir.exists():
                    shutil.rmtree(entry.profile_dir, ignore_errors=True)
            except (ValueError, OSError) as exc:
                logger.debug("Failed to clean PID file %s: %s", pid_file, exc)
            finally:
                pid_file.unlink(missing_ok=True)
        return killed

    def _atexit_cleanup(self) -> None:
        """Called on Python exit to clean up any remaining processes."""
        try:
            self.cleanup_stale()
        except Exception:
            logger.debug("atexit cleanup failed", exc_info=True)


# --- Instance ---


class ZoteroInstance:
    """Manages a single isolated Zotero test instance.

    Creates a temporary profile directory with custom prefs.js,
    launches Zotero via xvfb-run (if needed), and polls until the
    HTTP API is ready.
    """

    def __init__(
        self,
        port: int,
        zotero_bin: Path,
        guard: ZoteroProcessGuard,
        *,
        use_xvfb: bool = True,
        startup_timeout: float = DEFAULT_STARTUP_TIMEOUT,
    ) -> None:
        self._port = port
        self._zotero_bin = zotero_bin
        self._guard = guard
        self._use_xvfb = use_xvfb
        self._startup_timeout = startup_timeout
        self._process: subprocess.Popen[bytes] | None = None
        self._profile_dir: Path | None = None

    @property
    def port(self) -> int:
        return self._port

    @property
    def profile_dir(self) -> Path | None:
        return self._profile_dir

    @property
    def pid(self) -> int | None:
        return self._process.pid if self._process else None

    def start(self) -> None:
        """Start Zotero instance. Raises RuntimeError on failure."""
        self._validate_binaries()

        self._profile_dir = Path(
            tempfile.mkdtemp(prefix=f"yazot-test-{self._port}-")
        )

        # Write prefs.js
        prefs = ZoteroPrefs(port=self._port)
        (self._profile_dir / "prefs.js").write_text(prefs.render())

        # Build command
        cmd = self._build_command()

        # Launch
        self._process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        self._guard.register(
            PidEntry(
                pid=self._process.pid,
                port=self._port,
                profile_dir=self._profile_dir,
            )
        )

        # Wait for readiness
        if not self._wait_for_ready():
            self.stop()
            raise RuntimeError(
                f"Zotero failed to start on port {self._port} "
                f"within {self._startup_timeout}s"
            )

        logger.info(
            "Zotero instance started on port %d (PID %d)",
            self._port,
            self._process.pid,
        )

    def stop(self) -> None:
        """Stop the instance and clean up."""
        if self._process is not None:
            self._terminate_process()
            self._process = None

        self._guard.deregister(self._port)

        if self._profile_dir is not None and self._profile_dir.exists():
            shutil.rmtree(self._profile_dir, ignore_errors=True)
            self._profile_dir = None

        logger.info("Zotero instance stopped on port %d", self._port)

    def health_check(self) -> bool:
        """Check if the HTTP API is responding."""
        url = f"http://localhost:{self._port}/api/users/0/items?limit=1"
        try:
            with urlopen(url, timeout=2) as resp:  # noqa: S310
                return resp.status == 200
        except (URLError, OSError):
            return False

    def _validate_binaries(self) -> None:
        """Check that required binaries exist."""
        if not (self._zotero_bin.exists() or shutil.which(str(self._zotero_bin))):
            raise RuntimeError(f"Zotero binary not found: {self._zotero_bin}")
        if self._use_xvfb and not shutil.which("xvfb-run"):
            raise RuntimeError(
                "xvfb-run not found. Install xvfb package or set DISPLAY."
            )

    def _build_command(self) -> list[str]:
        """Build the command line for launching Zotero."""
        cmd: list[str] = []
        if self._use_xvfb:
            cmd.extend(["xvfb-run", "-a"])
        cmd.extend([
            str(self._zotero_bin),
            "-profile",
            str(self._profile_dir),
            "-no-remote",
            "-datadir",
            "profile",
        ])
        return cmd

    def _wait_for_ready(self) -> bool:
        """Poll health_check until ready or timeout."""
        deadline = time.monotonic() + self._startup_timeout
        while time.monotonic() < deadline:
            if self._process is not None and self._process.poll() is not None:
                return False
            if self.health_check():
                return True
            time.sleep(HEALTH_CHECK_INTERVAL)
        return False

    def _terminate_process(self) -> None:
        """Gracefully terminate, then force kill if needed."""
        assert self._process is not None
        try:
            self._process.terminate()
            self._process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self._process.kill()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                logger.warning("Process PID=%d unresponsive after SIGKILL", self._process.pid)
        except OSError:
            pass
        finally:
            if self._process.stderr:
                self._process.stderr.close()


# --- Pool ---


class ZoteroInstancePool:
    """Pool of isolated Zotero instances.

    Manages a range of ports, lazily starting instances on acquire().
    """

    def __init__(
        self,
        zotero_bin: Path,
        guard: ZoteroProcessGuard,
        *,
        port_range_start: int = DEFAULT_PORT_RANGE_START,
        port_range_end: int = DEFAULT_PORT_RANGE_END,
        use_xvfb: bool = True,
        startup_timeout: float = DEFAULT_STARTUP_TIMEOUT,
    ) -> None:
        self._zotero_bin = zotero_bin
        self._guard = guard
        self._use_xvfb = use_xvfb
        self._startup_timeout = startup_timeout
        self._available_ports = list(range(port_range_start, port_range_end + 1))
        self._active: dict[int, ZoteroInstance] = {}

    def acquire(self) -> ZoteroInstance:
        """Acquire a running instance. Raises RuntimeError if pool exhausted."""
        if not self._available_ports:
            active_ports = sorted(self._active.keys())
            raise RuntimeError(
                f"All ports in the pool are in use: {active_ports}"
            )

        port = self._available_ports.pop(0)
        instance = ZoteroInstance(
            port=port,
            zotero_bin=self._zotero_bin,
            guard=self._guard,
            use_xvfb=self._use_xvfb,
            startup_timeout=self._startup_timeout,
        )
        instance.start()
        self._active[port] = instance
        return instance

    def release(self, instance: ZoteroInstance) -> None:
        """Stop and release an instance back to the pool."""
        instance.stop()
        self._active.pop(instance.port, None)
        if instance.port not in self._available_ports:
            self._available_ports.append(instance.port)

    def release_all(self) -> None:
        """Stop all active instances."""
        for instance in list(self._active.values()):
            try:
                self.release(instance)
            except Exception:
                logger.warning(
                    "Failed to release instance on port %d",
                    instance.port,
                    exc_info=True,
                )

    @property
    def active_count(self) -> int:
        return len(self._active)

    @property
    def available_count(self) -> int:
        return len(self._available_ports)


# --- Helpers ---


def _is_process_running(pid: int) -> bool:
    """Check if a process is running by PID."""
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def detect_xvfb_needed() -> bool:
    """Auto-detect whether xvfb-run is needed (no DISPLAY set)."""
    if os.environ.get("DISPLAY"):
        return False
    if not shutil.which("xvfb-run"):
        raise RuntimeError(
            "No DISPLAY set and xvfb-run not found. "
            "Install xvfb or run with a display server."
        )
    return True
