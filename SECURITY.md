# Security

## Local-only bridge

ProBridge listens on `127.0.0.1` and has no authentication. Any local process can
connect while ArcGIS Pro is running. Keep the listener on loopback and do not
change the host to `0.0.0.0`.

## Arbitrary code execution

The `run_arcpy` command and MCP tool execute Python code supplied by the caller
with the permissions of the current Windows user. Only run trusted code from
trusted agents or clients. Treat access to the bridge as equivalent to local
shell access.

## Reporting a vulnerability

Please use the repository's private security advisory feature rather than a
public issue. Include the affected command, reproduction steps, and expected
impact.
