"""One Pull key for a pane whose list comes from a remote store.

Press ``p``, bound to ``action_pull_remote``. The pane notifies, runs
``fetch_remote`` on a worker, then notifies the summary that method
returns. An exception becomes an error toast. The pane still renders
whatever it loaded before raising, so a partial read is not thrown away.

``fetch_remote`` returns a short success line, for example
``Pending: 1  Completed: 0  Total: 1``.

Used by Responses (S3 form intake), Queue detail (S3 queue mirror),
Cluster (S3 registry and heartbeats), and Tracking (GA4; the footer
says Pull GA4). Company detail keeps ``p`` for placing a call.
Recordings come from Twilio. Index detail reads the local mirror;
syncing those files stays on Admin → Sync Indexes.
"""

from __future__ import annotations

import logging
from typing import cast

from textual.widget import Widget

logger = logging.getLogger(__name__)


class RemotePullMixin:
    """Subclasses bind ``p`` to ``action_pull_remote`` and implement ``fetch_remote``.

    The binding stays on the screen so a pane can name the source in the
    footer (``Pull`` or ``Pull GA4``) without a second ``p`` handler.
    """

    def remote_pull_label(self) -> str:
        return "S3"

    async def fetch_remote(self) -> str:
        raise NotImplementedError

    def action_pull_remote(self) -> None:
        host = cast(Widget, self)
        host.notify(f"Pulling {self.remote_pull_label()}...")
        host.run_worker(self._run_remote_pull(), exclusive=True, name="remote_pull")

    async def _run_remote_pull(self) -> None:
        host = cast(Widget, self)
        label = self.remote_pull_label()
        try:
            summary = await self.fetch_remote()
        except Exception as exc:
            logger.warning("%s pull failed: %s", label, exc)
            host.notify(f"{label} pull failed: {exc}", severity="error")
            return
        if summary:
            host.notify(summary)
