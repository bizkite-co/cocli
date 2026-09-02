from __future__ import annotations
import os
import json
import logging
import socket
import time
import subprocess
from pathlib import Path
from datetime import datetime, UTC
from typing import Any, Optional, Sequence

from botocore.exceptions import ClientError

from .config import get_campaign_dir
from ..models.campaigns.worker_config import PiNodeConfig

logger = logging.getLogger(__name__)

# A compactor lock older than this is presumed to belong to a crashed process
# (hard kill, OOM, lost network) rather than a live one - stations
# CONCURRENCY.md §2.3/§4.1 "lease expiry": a dead lease is taken over by
# CAS-replace, never delete-then-create (C3). Picked to comfortably exceed
# a real compaction's runtime (Tailscale rsync + DuckDB fold) while still
# reclaiming a crashed lock in well under an hour.
LOCK_STALE_SECONDS = 1800


def _aws_cli_env() -> dict[str, str]:
    """Environment for the `aws` CLI subprocess calls in this module
    (recover_interrupted_run's legacy S3-staging path only - see
    acquire_staging/cleanup), with IoT STS credentials injected if
    available.

    The `aws` binary resolves its own credentials independently of
    boto3/get_boto3_session - env vars, ~/.aws/credentials, or IMDS - none
    of which this container populates, since its whole strategy is
    non-interactive IoT STS auth. Confirmed live 2026-08-19: an old
    interrupted run orphaned by the 2026-08-13 incident (see this
    module's acquire_staging docstring) could never be recovered because
    every `cocli index compact` invocation hit this exact gap first,
    before ever reaching a fresh compact - the .s3 property fix alone
    (boto3-only) didn't cover it.
    """
    from ..utils.aws_iot_auth import get_iot_sts_credentials

    env = os.environ.copy()
    creds = get_iot_sts_credentials()
    if creds:
        env["AWS_ACCESS_KEY_ID"] = creds["access_key"]
        env["AWS_SECRET_ACCESS_KEY"] = creds["secret_key"]
        env["AWS_SESSION_TOKEN"] = creds["token"]
    return env


class CompactManager:
    """
    Implements the Freeze-Ingest-Merge-Commit (FIMC) pattern for sharded indexes.

    WAL sources are staged directly from each Pi node (Tailscale rsync) into
    local processing/{run_id}/{host}/ - see isolate_wal(). The S3 lock
    (compact.lock) is kept regardless: it must stay reachable from any future
    compactor placement (Pi, short-lived Fargate task, or this dev machine),
    not just wherever compaction happens to run today (stations CONCURRENCY.md
    §4.1 - the lock is a liveness mechanism, not tied to any one host).
    """

    def __init__(self, campaign_name: str, index_name: str = "google_maps_prospects", log_file: Optional[Path] = None):
        self.campaign_name = campaign_name
        self.index_name = index_name
        self.run_id = f"run_{int(time.time())}"
        self.log_file = log_file

        # Local Paths derived via paths single-source-of-truth
        from .paths import paths
        self.index_paths = paths.campaign(campaign_name).index(index_name)
        self.data_root = paths.campaign(campaign_name).path
        self.index_dir = self.index_paths.path
        self.checkpoint_path = self.index_paths.checkpoint
        self.checkpoint_filename = self.index_paths.checkpoint_filename

        self.local_proc_dir = self.index_dir / "processing" / self.run_id

        # S3 Paths
        self.s3_index_prefix = f"campaigns/{campaign_name}/indexes/{index_name}/"
        self.s3_checkpoint_key = self.s3_index_prefix + self.checkpoint_filename
        self.s3_wal_prefix = self.s3_index_prefix + "wal/"
        self.s3_proc_prefix = self.s3_index_prefix + f"processing/{self.run_id}/"
        self.s3_lock_key = self.s3_index_prefix + "compact.lock"

        # True only when acquire_staging() actually pulled this run's batch
        # from S3 - i.e. the legacy interrupted-run recovery path
        # (IndexService.recover_interrupted_run). A normal run stages
        # directly from the Pis via isolate_wal() and never touches S3
        # processing/, so cleanup() must not assume it needs to either.
        self._used_s3_staging: bool = False

        # S3 Client
        self._s3: Any = None
        self._bucket = self._load_bucket_name()

    def _load_bucket_name(self) -> str:
        """Loads bucket name from campaign config.toml"""
        import tomllib
        camp_dir = get_campaign_dir(self.campaign_name)
        if camp_dir:
            config_path = camp_dir / "config.toml"
            if config_path.exists():
                with open(config_path, "rb") as f:
                    data = tomllib.load(f)
                    bucket = data.get("aws", {}).get("data_bucket_name") or data.get("data_bucket_name")
                    if bucket:
                        return str(bucket)
        return ""

    @property
    def s3(self) -> Any:
        if self._s3 is None:
            # Confirmed live 2026-08-19: a bare boto3.client("s3") only
            # works if boto3's default credential chain finds something
            # (env vars, ~/.aws/credentials, IMDS) - none of which apply
            # inside the worker container, whose whole strategy is
            # non-interactive IoT STS auth (see get_boto3_session). Every
            # other S3 touchpoint in this codebase goes through that
            # helper; this one didn't, so `cocli index compact` failed
            # with a raw NoCredentialsError the moment it needed S3
            # (compact.lock acquisition) run from inside the container -
            # the exact place this command actually needs to run, since
            # WAL never syncs to the dev machine.
            from .config import load_campaign_config
            from .reporting import get_boto3_session

            config = load_campaign_config(self.campaign_name)
            session = get_boto3_session(config)
            self._s3 = session.client("s3")
        return self._s3

    def acquire_lock(self) -> bool:
        """Creates an atomic lock on S3 using If-None-Match, or takes over a
        stale one via CAS-replace (stations C3: expired leases are taken
        over by CAS, never delete-then-create).

        Today, a crashed compactor (hard kill, not a handled exception - a
        clean exception still hits release_lock() in run()'s/IndexService's
        finally) leaves this lock stuck forever with no path to reclaim it.
        Any lock older than LOCK_STALE_SECONDS is treated as crashed and
        taken over. If the stale lock's own run_id still has a local
        processing/{run_id}/ batch on this machine, that run_id is adopted
        so isolate_wal() resumes topping it up instead of starting a fresh,
        empty run and stranding it (the incident this ticket fixes).
        """
        logger.info(f"Attempting to acquire compaction lock: {self.s3_lock_key}")
        lock_data = {
            "run_id": self.run_id,
            "created_at": datetime.now(UTC).isoformat(),
            "host": os.uname().nodename
        }
        try:
            self.s3.put_object(
                Bucket=self._bucket,
                Key=self.s3_lock_key,
                Body=json.dumps(lock_data),
                IfNoneMatch='*'
            )
            logger.info("Lock acquired successfully.")
            return True
        except ClientError as e:
            if e.response['Error']['Code'] != 'PreconditionFailed':
                logger.error(f"Failed to acquire lock: {e}")
                return False
            return self._take_over_stale_lock_if_possible(lock_data)

    def _take_over_stale_lock_if_possible(self, new_lock_data: dict[str, str]) -> bool:
        try:
            resp = self.s3.get_object(Bucket=self._bucket, Key=self.s3_lock_key)
            existing = json.loads(resp["Body"].read())
            etag = resp["ETag"]
        except Exception as e:
            logger.warning(f"Compaction lock exists but couldn't be read: {e}")
            return False

        try:
            age = (datetime.now(UTC) - datetime.fromisoformat(existing["created_at"])).total_seconds()
        except (KeyError, ValueError) as e:
            logger.warning(f"Compaction lock has an unreadable created_at ({e}); treating as live.")
            return False

        if age < LOCK_STALE_SECONDS:
            logger.warning(
                f"Compaction lock already exists (age {age:.0f}s, held by "
                f"{existing.get('host')}, run {existing.get('run_id')}). Another process is running."
            )
            return False

        stale_run_id = existing.get("run_id")
        logger.warning(
            f"Compaction lock is stale (age {age:.0f}s, held by {existing.get('host')}, "
            f"run {stale_run_id}) - treating as a crashed run and taking over."
        )
        try:
            self.s3.put_object(
                Bucket=self._bucket,
                Key=self.s3_lock_key,
                Body=json.dumps(new_lock_data),
                IfMatch=etag,
            )
        except ClientError as e:
            logger.warning(f"Lost the race taking over the stale lock: {e}")
            return False

        if stale_run_id:
            recovered_dir = self.index_dir / "processing" / stale_run_id
            if recovered_dir.exists() and any(recovered_dir.iterdir()):
                logger.info(f"Resuming crashed run {stale_run_id} - local batch found at {recovered_dir}.")
                self.run_id = stale_run_id
                self.local_proc_dir = recovered_dir
                self.s3_proc_prefix = self.s3_index_prefix + f"processing/{self.run_id}/"

        logger.info("Lock acquired successfully (stale takeover).")
        return True

    def release_lock(self) -> None:
        """Removes the compaction lock from S3."""
        try:
            self.s3.delete_object(Bucket=self._bucket, Key=self.s3_lock_key)
            logger.info("Lock released.")
        except Exception as e:
            logger.error(f"Failed to release lock: {e}")

    def isolate_wal(self, nodes: Optional[Sequence[PiNodeConfig]] = None) -> int:
        """Stages each Pi node's WAL directly into processing/{run_id}/{host}/
        over Tailscale (rsync) - no S3 relay for the WAL payload itself.

        Nothing is deleted here. Local index_dir/wal/, naked-root USV/CSV
        files, and the Pi's own WAL are all left exactly as found - stations
        C9 (source deletion only after commit): the only safe place to purge
        sources is cleanup(), after commit_remote() has actually succeeded.
        (The old version of this method deleted local WAL and naked-root
        USVs unconditionally, before merge() ever ran - the same defect this
        whole ticket is about, just a second instance of it.)

        `nodes` must be resolved by the caller (application/services -
        core/ may not import ClusterService per the import-linter contract).
        Returns the number of files staged for this run - callers use this
        to decide whether there's anything to compact.

        A node whose hostname matches this process's own (COCLI_HOSTNAME,
        same idiom as worker_service/operation_service/queue/filesystem use
        to self-identify) is never rsync'd - its WAL is already on this
        filesystem (bind-mounted into the container same as everywhere else
        under index_dir), so shipping it to itself over SSH would just be a
        loopback network hop for data already in hand. It's already counted
        below regardless (the unconditional index_dir/wal scan every run
        does, for exactly this "already local" case) - skipping the rsync
        here doesn't skip folding it, just the pointless network round trip
        (and, previously, a hard dependency on an SSH identity that never
        needed to exist). Confirmed live 2026-08-19: roadmap's single-node
        compact was blocked on provisioning exactly that identity.
        """
        self.local_proc_dir.mkdir(parents=True, exist_ok=True)
        staged = 0
        local_hostname = (os.getenv("COCLI_HOSTNAME") or socket.gethostname()).split(".")[0]

        for node in nodes or []:
            host = node.hostname
            target = node.ip_address or host

            if host.split(".")[0] == local_hostname:
                logger.info(f"{host} is the local node - WAL already on disk, skipping rsync.")
                continue

            node_dir = self.local_proc_dir / host
            node_dir.mkdir(parents=True, exist_ok=True)
            remote_path = (
                f"mstouffer@{target}:repos/data/campaigns/{self.campaign_name}"
                f"/indexes/{self.index_name}/wal/"
            )
            logger.info(f"Staging {self.index_name} WAL from {host}...")
            try:
                result = subprocess.run(
                    [
                        "rsync", "-avzu",
                        # A freshly-deployed worker container has an empty
                        # known_hosts, so a bare rsync-over-ssh fails with
                        # "Host key verification failed" the first time it
                        # talks to any peer (including itself, when a
                        # single-node campaign "syncs" from its own host) -
                        # confirmed live 2026-08-19. accept-new (not the
                        # weaker "no") still detects a key that later
                        # changes on an already-trusted host, it just
                        # doesn't require a prior interactive TOFU prompt
                        # for these already-Tailscale-trusted internal nodes.
                        "-e", "ssh -o StrictHostKeyChecking=accept-new -o ConnectTimeout=15",
                        remote_path, str(node_dir) + "/",
                    ],
                    capture_output=True, text=True, timeout=300,
                )
            except subprocess.TimeoutExpired:
                logger.warning(f"WAL rsync from {host} timed out - skipping this cycle.")
                node_dir.rmdir()
                continue

            if result.returncode != 0:
                logger.warning(f"WAL rsync from {host} failed: {result.stderr.strip()}")
                node_dir.rmdir()
                continue

            node_files = [p for p in node_dir.rglob("*.usv") if p.is_file()]
            if node_files:
                staged += len(node_files)
                logger.info(f"Staged {len(node_files)} WAL files from {host}.")
            else:
                node_dir.rmdir()

        # Legitimate fold sources already sitting in index_dir/wal or as
        # naked root USVs (stations_runtime._collect_prospect_usv_sources
        # scans both directly) are picked up by merge() as-is - no need to
        # move them into local_proc_dir, and definitely not to delete them
        # here before they've been folded.
        local_wal = self.index_dir / "wal"
        local_wal_count = len(list(local_wal.glob("*.usv"))) if local_wal.exists() else 0
        naked_count = sum(
            1 for f in self.index_dir.glob("*.usv")
            if f.name not in (self.checkpoint_filename, "validation_errors.usv")
        )
        staged += local_wal_count + naked_count

        logger.info(f"Isolation complete: {staged} files staged (Pi-fetched + existing local sources).")
        return staged

    def acquire_staging(self) -> None:
        """Syncs the processing/run_id/ folder from S3 to local disk using AWS CLI.

        Only used by IndexService.recover_interrupted_run() - the legacy path
        for finishing an already-isolated S3 batch left over from before this
        fix (e.g. the two batches orphaned by the 2026-08-13 incident: normal
        runs now stage directly from the Pis via isolate_wal() and never
        populate S3 processing/ in the first place). Sets
        _used_s3_staging so cleanup() knows this run also owns an S3
        processing/ prefix to remove, on top of its local batch.

        Must raise on failure, not just log: callers proceed straight to merge()
        assuming local_proc_dir reflects what was isolated on S3. A swallowed
        sync failure leaves local_proc_dir empty, so merge() sees "no sources"
        and silently re-commits the checkpoint unchanged - then cleanup() purges
        the S3 processing/ prefix, permanently losing the isolated batch with
        the CLI reporting success throughout.
        """
        logger.info(f"Acquiring staging data to {self.local_proc_dir}...")
        self.local_proc_dir.mkdir(parents=True, exist_ok=True)

        src = f"s3://{self._bucket}/{self.s3_proc_prefix}"
        from contextlib import nullcontext
        with open(self.log_file, "a") if self.log_file else nullcontext() as f:
            subprocess.run(
                ["aws", "s3", "sync", src, str(self.local_proc_dir), "--quiet"],
                stdout=f, stderr=f, check=True, env=_aws_cli_env(),
            )
        self._used_s3_staging = True
        logger.info("Staging data acquired.")

    def _write_schema_sidecar_first(self) -> None:
        """Enforces Frictionless Data policy by writing datapackage.json sidecar BEFORE data writes."""
        try:
            if self.index_name == "google_maps_prospects":
                from ..models.campaigns.indexes.google_maps_prospect import GoogleMapsProspect
                GoogleMapsProspect.write_datapackage(self.campaign_name, output_dir=self.index_dir)
                logger.info(f"Sidecar datapackage.json written first for {self.index_name}")
        except Exception as e:
            logger.warning(f"Schema sidecar write failed for {self.index_name}: {e}")

    def merge(self) -> None:
        """Fold local WAL/staging into prospects.usv via stations commit path.

        DuckDB performs the scale LWW fold; stations PathBackend CAS-commits
        CURRENT and protect_path hardens ratified artifacts. S3 isolate/stage
        still feed ``local_proc_dir`` before this runs.
        """
        self._write_schema_sidecar_first()

        from cocli.core.stations_runtime import compact_prospects_local

        staging: list[Path] = []
        if self.local_proc_dir.exists():
            staging.append(self.local_proc_dir)

        ok = compact_prospects_local(
            self.index_dir,
            checkpoint_path=self.checkpoint_path,
            staging_dirs=staging or None,
            compactor_id=self.run_id,
        )
        if ok:
            logger.info(
                "Prospects merge via stations commit path → %s",
                self.checkpoint_path,
            )
            return

        # Fallback: empty staging/WAL — nothing to fold (legacy no-op)
        logger.info("No local prospect sources to merge via stations.")


        
    def commit_remote(self) -> None:
        """Uploads the new checkpoint to S3."""
        logger.info("Uploading updated checkpoint to S3...")
        self.s3.upload_file(str(self.checkpoint_path), self._bucket, self.s3_checkpoint_key)
        logger.info(f"S3 Checkpoint updated at {self.s3_checkpoint_key}.")


    def cleanup(self) -> None:
        """Purges now-folded sources - only ever called after commit_remote()
        has succeeded (stations C9: source deletion only post-commit).

        Local: this run's Pi-fetched batch (local_proc_dir), whatever was
        sitting in index_dir/wal, and naked-root USVs (all three were valid
        fold inputs per stations_runtime._collect_prospect_usv_sources, and
        are now safely represented in the committed checkpoint). Naked-root
        CSVs are never fold inputs - always safe to discard, any time.

        Remote: only when _used_s3_staging is set (the legacy
        recover_interrupted_run() path) - a normal run never populated S3
        processing/ in the first place, so there's nothing there to remove
        and no reason to pay for another aws CLI subprocess/credential
        round-trip in the common case.
        """
        logger.info("Cleaning up staging layers...")

        if self._used_s3_staging:
            src = f"s3://{self._bucket}/{self.s3_proc_prefix}"
            try:
                from contextlib import nullcontext
                with open(self.log_file, "a") if self.log_file else nullcontext() as f:
                    subprocess.run(
                        ["aws", "s3", "rm", src, "--recursive", "--quiet"],
                        stdout=f, stderr=f, check=True, env=_aws_cli_env(),
                    )
            except Exception as e:
                logger.error(f"Failed to cleanup S3 staging: {e}")

        import shutil
        if self.local_proc_dir.exists():
            shutil.rmtree(self.local_proc_dir)

        local_wal = self.index_dir / "wal"
        if local_wal.exists():
            shutil.rmtree(local_wal)
            local_wal.mkdir(parents=True, exist_ok=True)

        for f_path in self.index_dir.glob("*.usv"):
            if f_path.name not in (self.checkpoint_filename, "validation_errors.usv"):
                f_path.unlink()
        for f_path in self.index_dir.glob("*.csv"):
            f_path.unlink()

        logger.info("Cleanup complete.")

    def run(self, nodes: Optional[Sequence[PiNodeConfig]] = None) -> None:
        """Executes the full compaction lifecycle. Not currently wired to any
        CLI/service caller - IndexService.compact() orchestrates these same
        steps itself (with interrupted-run recovery around them); kept here
        as the reference sequence for the class's own contract."""
        if not self.acquire_lock():
            return

        try:
            moved = self.isolate_wal(nodes=nodes)
            if moved > 0:
                self.merge()
                self.commit_remote()
                self.cleanup()
            else:
                logger.info("Nothing to compact.")
        finally:
            self.release_lock()
