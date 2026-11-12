"""Worker process of `extract_python`: jobs in on stdin, results out on stdout.

Started with the interpreter in isolated mode, so nothing in the working directory,
which is usually the repository under analysis, can be imported in place of a real
module. It does not go through `multiprocessing`: a caller's script is never run
again in the worker, and no shared semaphores are needed.
"""

import os
import pickle
import sys


def main() -> None:
    # Keep the result channel clean: anything printed goes to stderr instead.
    results = os.fdopen(os.dup(1), "wb")
    os.dup2(2, 1)
    from genesis_ci.python.extract import _extract_job

    jobs = pickle.load(sys.stdin.buffer)
    pickle.dump([_extract_job(job) for job in jobs], results, protocol=pickle.HIGHEST_PROTOCOL)
    results.close()


if __name__ == "__main__":
    main()
