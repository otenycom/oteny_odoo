"""
The work queue that workers pull test classes from.

The master writes one empty file per test class into a queue directory,
named ``<index>__<class key>`` with the index in the order the classes
should be taken (longest first, from the timing stats). A worker claims the
next class by renaming its file into its own ``claimed/<worker>/`` directory.
``os.rename`` is atomic on POSIX, so two workers can never take the same
class: the loser gets FileNotFoundError and moves on to the next file.

This replaces the static per-worker batches: a worker that finishes early
simply takes the next class, so the makespan no longer depends on how good
last run's duration estimates were. Each class still runs entirely on one
worker (its setUpClass data is shared by its tests).
"""

import os

QUEUE_DIR = "queue"
CLAIMED_DIR = "claimed"


def create_queue(tmpdir, class_keys):
    """Write the queue files for ``class_keys`` (already in pull order).

    Returns the queue directory. The width of the index keeps lexical order
    equal to pull order for any queue size that fits the width.
    """
    queue_dir = os.path.join(tmpdir, QUEUE_DIR)
    os.makedirs(queue_dir, exist_ok=True)
    os.makedirs(os.path.join(tmpdir, CLAIMED_DIR), exist_ok=True)
    width = max(4, len(str(len(class_keys))))
    for index, key in enumerate(class_keys):
        with open(os.path.join(queue_dir, f"{index:0{width}d}__{key}"), "w"):
            pass
    return queue_dir


def claim_next(queue_dir, worker_id, wanted=None):
    """Take the next class off the queue for ``worker_id``.

    ``wanted`` limits the claim to class keys this worker can run (the
    classes in its discovered suite). Returns the class key, or None when
    nothing claimable is left.
    """
    claimed_dir = os.path.join(os.path.dirname(queue_dir), CLAIMED_DIR, str(worker_id))
    os.makedirs(claimed_dir, exist_ok=True)
    try:
        names = sorted(os.listdir(queue_dir))
    except FileNotFoundError:
        return None
    for name in names:
        key = name.split("__", 1)[1] if "__" in name else name
        if wanted is not None and key not in wanted:
            continue
        try:
            os.rename(os.path.join(queue_dir, name), os.path.join(claimed_dir, name))
        except FileNotFoundError:
            continue  # another worker took it first
        return key
    return None


def remaining(queue_dir):
    """How many classes are still unclaimed."""
    try:
        return len(os.listdir(queue_dir))
    except FileNotFoundError:
        return 0
