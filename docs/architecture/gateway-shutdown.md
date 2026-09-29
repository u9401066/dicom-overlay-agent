# Gateway shutdown: drain an idle, detached WebSocket

The [36dc3c6 frozen desktop run](../evidence/2026-09/frozen-regional-context-2026-09-29.md)
retained a two-second close timeout. No socket-buffer state was captured during
that original run, so its exact cause cannot be proven retrospectively.

## Reproduced failure mechanism

With the locked websockets16.0 library, a real loopback peer sends80 synthetic
events without the client consuming them. The default incoming-frame high/low
watermarks remain16/4. The receive queue demonstrably pauses reading; the old
`disconnect()` then times out without receiving a normal closing handshake.

The library documents that full frame buffers stop network reads until consumed:
[memory and buffers](https://websockets.readthedocs.io/en/16.0/topics/memory.html).
The [client API](https://websockets.readthedocs.io/en/16.0/reference/asyncio/client.html)
documents `recv()`, closing behavior, cancellation and concurrent-reader limits.
Increasing the queue or removing flow control is not part of this change.

## Source fix and boundaries

`disconnect()` first detaches its current socket and clears the connected state.
If no turn holds the send/receive lock, a temporary task consumes/discards incoming
messages from that old socket while the public `close()` handshake proceeds.
It does not parse messages, publish answers, append evidence, send chat requests,
or reconnect. Only a discarded-message count is logged; payloads are not logged.

The temporary reader yields after each message so a flooding peer cannot starve
the existing close deadline. Completion, timeout, transport errors and caller
cancellation all cancel and await that reader. An active turn retains its reader;
shutdown does not race it for responses. This does not redesign cancellation or
recovery of active model turns, and must not be described as such.

No dependency, Gateway protocol, image scope, schema or inference prompt changes.
Only public WebSocket calls are used by production code. Private library queue
state is inspected only by the regression test to establish real backpressure.

## Verification

The real-socket regression fails on the preceding implementation and closes with
normal code1000 on both peers after the source fix, with flow control unchanged.
Additional tests cover empty connections, active-turn ownership, repeated
disconnect, hung/flooding peers, explicit cancellation and no leftover drain task.
Focused shutdown/Gateway/Core2/evidence checks passed184 tests in3.07s; Ruff and
targeted mypy passed. Full source regression and fresh actual App acceptance are
pending at this implementation checkpoint. Existing packages/runtimes are not
silently updated or restarted.
