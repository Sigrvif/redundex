import concurrent.futures
import multiprocessing as mp
import os


class CancelledScan(Exception):
    pass


def run_jobs(fn, items, workers=None, cancel_event=None, progress_cb=None):
    results = []
    problems = []
    items = list(items)
    if not items:
        return results, problems
    n = workers or os.cpu_count() or 4
    ctx = mp.get_context("spawn")
    with concurrent.futures.ProcessPoolExecutor(max_workers=n, mp_context=ctx) as ex:
        futures = {ex.submit(fn, it): it for it in items}
        done = 0
        try:
            for fut in concurrent.futures.as_completed(futures):
                if cancel_event is not None and cancel_event.is_set():
                    raise CancelledScan()
                item = futures[fut]
                try:
                    results.append(fut.result())
                except concurrent.futures.BrokenExecutor as exc:
                    problems.append(
                        {"path": None, "error": f"worker pool crashed: {exc}"}
                    )
                    for f in futures:
                        f.cancel()
                    break
                except Exception as exc:
                    problems.append({"path": item, "error": str(exc)})
                done += 1
                if progress_cb is not None:
                    progress_cb(done, len(items))
        except CancelledScan:
            for f in futures:
                f.cancel()
            raise
    return results, problems
