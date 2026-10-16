"""Delivery retries; monotonic deadline and injectable clock for offline tests."""
import time


def run_delivery(jobs, send, duration, stop, status, result, persist, delay,
                 clock=time.monotonic, wait=None):
    wait = wait or stop.wait
    deadline = clock() + duration
    states = [(job, '尚未寄送') for job in jobs]
    pending = list(range(len(jobs)))
    backoff = 120
    round_number = 0
    persist(states)

    def alive():
        return not stop.is_set() and clock() < deadline

    def pause(seconds, label):
        until = min(clock() + seconds, deadline)
        while alive() and clock() < until:
            remaining = until - clock()
            status(f'{label}：剩餘 {int(remaining + 0.999)} 秒')
            if wait(min(1, remaining)):
                return False
        return alive()

    while pending and alive():
        if round_number:
            status(f'第 {round_number} 次重試，等待 {backoff // 60} 分鐘')
            if not pause(backoff, f'第 {round_number} 次重試等待中'):
                break
            backoff = min(backoff * 2, 7200)
        for position, index in enumerate(pending):
            if not alive():
                break
            job = jobs[index]
            status(f"{'首次寄送' if not round_number else '重試'}：{job['name']} ({position+1}/{len(pending)})")
            if not job.get('email'):
                ok, reason = False, '清單中未填寫 Email'
            else:
                ok, reason = send(job)
            states[index] = (job, '成功' if ok else reason)
            if ok:
                backoff = 120
            # Persist before auxiliary logging; preserve outcome if logging fails.
            persist(states)
            result(job, ok, reason)
            if position < len(pending) - 1 and not pause(delay(), '每封信間隔'):
                break
        pending = [i for i, (_, reason) in enumerate(states)
                   if 'server not connected' in reason.lower()]
        round_number += 1
    return states
