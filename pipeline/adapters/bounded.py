"""Run optional legacy providers in a killable worker, never stall publication."""
from multiprocessing import get_context


def _worker(connection, function, args):
    try:
        connection.send((True, function(*args)))
    except Exception as exc:
        connection.send((False, f"{type(exc).__name__}: {exc}"))
    finally:
        connection.close()


def call_with_timeout(function, args=(), seconds=45):
    context = get_context("spawn")
    receive, send = context.Pipe(duplex=False)
    process = context.Process(target=_worker, args=(send, function, args), daemon=True)
    process.start()
    send.close()
    try:
        if not receive.poll(seconds):
            raise TimeoutError(f"{function.__name__} exceeded {seconds}s")
        success, value = receive.recv()
        if not success:
            raise RuntimeError(value)
        return value
    finally:
        receive.close()
        if process.is_alive():
            process.terminate()
        process.join(timeout=2)


def collect_sectors():
    from pipeline.adapters.market_overview import _fetch_sectors, ak
    return _fetch_sectors(ak)
