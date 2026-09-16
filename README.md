# ChatGPT Watchdog

AI Task Continuity & Auto-Recovery System

## Status

Current development stage: **Sprint 1 / V1.0.0 Working Increment**

This project monitors long-running ChatGPT or AI research work, detects likely stalls, and can trigger a controlled resume action while recording incidents for later improvement.

## Core principles

- Monitor real progress, not merely message activity.
- Separate state judgment from UI / agent control through adapters.
- Never retry forever.
- Every incident becomes input for the next version.
- Every Sprint must preserve a working increment.
- **No EXE, No Release.** The official Windows deliverable must be a runnable `.exe` that does not require Python to be installed.

## V1.0 scope

- Arm / Disarm watchdog
- Configurable timeout
- Configurable retry limit
- Basic RUNNING / STALLED state handling
- Controlled Resume command
- Runtime log
- Incident log
- Adapter abstraction
- Windows build path

## Planned architecture

```text
ChatGPT / AI UI
      ↑↓
Sensor / Actuator Adapter
      ↑↓
Watchdog Bridge
      ↑↓
State & Stall Engine
      ↓
Retry / Cooldown / Incident Log
```

Hermes Agent / Computer Use is treated as a pluggable adapter, not as a hard dependency for V1.0.

## Project recovery

The project keeps a master handover prompt in Google Drive so that a new ChatGPT conversation or another agent can resume the project after a failure or context loss.

Development rule: **No Content, No Subfolder.**
