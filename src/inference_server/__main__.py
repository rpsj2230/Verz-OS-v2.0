"""`python -m inference_server`: read the environment, build the supervisor and serve.

Exits non-zero with the reason on a configuration that cannot run, which is what a container whose
environment was written by hand needs to do: a server that started on a half-read configuration
would answer, and be wrong in a way the application cannot see.

Task ids: M7.2.1, M7.3.3
"""

from __future__ import annotations

import os
import signal
import sys

from inference_server.config import ConfigError, from_environment
from inference_server.gateway import serve
from inference_server.supervisor import Supervisor


def main() -> int:
    """Run until told to stop, then end whatever part is loaded."""
    try:
        config = from_environment(os.environ)
    except ConfigError as error:
        print(f"the model server cannot start: {error}", file=sys.stderr)
        return 2
    supervisor = Supervisor(config)
    server = serve(config, supervisor)

    def stop(_signal: int, _frame: object) -> None:
        # `shutdown` must be called from another thread than the one in `serve_forever`.
        import threading

        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        server.serve_forever()
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
