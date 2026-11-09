# AUTOCADSS MCP

MCP server for AutoCAD automation and headless DXF generation.

| Backend | Requires AutoCAD? | Screenshot |
|---------|-------------------|------------|
| **File IPC** | Yes, a running AutoCAD on Windows with an open drawing | Win32 PrintWindow |
| **ezdxf** | No, headless | matplotlib render |

AUTOCADSS runs alongside the original `autocad-mcp`: the package, environment variables, IPC file names and AutoLISP command are all separate.

## Install

```powershell
git clone https://github.com/souhaibsmadi42/AUTOCADSS-MCP.git
cd AUTOCADSS-MCP
uv sync
```

## Connect to Claude Code

```powershell
claude mcp add -s user AUTOCADSS -e AUTOCADSS_MCP_BACKEND=auto -- C:\path\to\AUTOCADSS-MCP\.venv\Scripts\python.exe -m autocadss_mcp
```

Restart the client after adding it, then call `system(operation="status")`.

## Use with a live AutoCAD

1. Open AutoCAD and a drawing.
2. Run `APPLOAD` and load `lisp-code/autocadss_dispatch.lsp`. Add it to the Startup Suite to load it automatically.
3. The command line shows `=== AUTOCADSS Dispatch loaded ===`.
4. Call `system(operation="init")` so the server switches to the File IPC backend.

Without a matching AutoCAD window, `auto` falls back to the headless ezdxf backend.

## Tools

| Tool | Operations |
|------|------------|
| `drawing` | `create`, `open`, `info`, `save`, `save_as_dxf`, `plot_pdf`, `purge`, `get_variables`, `undo`, `redo` |
| `entity` | `create_line`, `create_circle`, `create_polyline`, `create_rectangle`, `create_arc`, `create_ellipse`, `create_mtext`, `create_hatch`, `list`, `count`, `get`, `copy`, `move`, `rotate`, `scale`, `mirror`, `offset`, `array`, `fillet`, `chamfer`, `erase` |
| `layer` | `list`, `create`, `set_current`, `set_properties`, `freeze`, `thaw`, `lock`, `unlock` |
| `block` | `list`, `insert`, `insert_with_attributes`, `get_attributes`, `update_attribute`, `define` |
| `annotation` | `create_text`, `create_dimension_linear`, `create_dimension_aligned`, `create_dimension_angular`, `create_dimension_radius`, `create_leader` |
| `pid` | P&ID operations; symbol insertion needs the CAD Tools Online library at `C:\PIDv4-CTO\` |
| `view` | `zoom_extents`, `zoom_window`, `get_screenshot` |
| `system` | `status`, `health`, `get_backend`, `runtime`, `init`, `execute_lisp` |

`plot_pdf`, `undo`, `redo`, `offset`, `fillet`, `chamfer` and `execute_lisp` need the File IPC backend. `execute_lisp` runs arbitrary AutoLISP in your AutoCAD session.

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `AUTOCADSS_MCP_BACKEND` | `auto` | `auto`, `file_ipc` or `ezdxf` |
| `AUTOCADSS_MCP_IPC_DIR` | `C:/temp` | IPC file folder. If changed, also change `*autocadss-ipc-dir*` in `autocadss_dispatch.lsp` |
| `AUTOCADSS_MCP_IPC_TIMEOUT` | `10` | Seconds to wait for one AutoCAD command (1-300) |
| `AUTOCADSS_MCP_TOOL_TIMEOUT` | `60` | Seconds allowed for one whole tool call |
| `AUTOCADSS_MCP_ONLY_TEXT` | `false` | Disable screenshots |

## Changes from autocad-mcp v3.1

- Fixed a Windows hang where the first tool call never returned: native modules now load before the stdio transport starts.
- Every tool call has a time limit and returns an error instead of waiting forever.
- Fixed the `dev` dependency declaration in `pyproject.toml`, which stopped `uv sync` from installing test tools.
- Added a test that drives the real server over stdio.
- Renamed everything so both servers can be installed together.

## Development

```powershell
uv sync
uv run pytest tests -q
```

## License

MIT. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
