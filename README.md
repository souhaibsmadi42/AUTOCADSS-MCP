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

Nothing to set up (since 0.2.0):

- If AutoCAD is closed, the first `drawing`, `layer`, `entity` (or `system launch`) call starts it on a blank
  metric drawing (`/t acadiso.dwt`) and waits until it answers.
- The server writes an Autoloader bundle to `%APPDATA%\Autodesk\ApplicationPlugins\AutocadssMCP.bundle`. AutoCAD
  loads `autocadss_dispatch.lsp` from it into every drawing. That folder is a trusted location, so there is no
  SECURELOAD prompt and no security setting is changed. If a drawing still lacks the dispatcher, the server loads it.
- `system(operation="status")` is read-only and never starts AutoCAD.

To do it by hand instead, set `AUTOCADSS_MCP_AUTO_LAUNCH=0`, open AutoCAD, run `APPLOAD` and load
`lisp-code/autocadss_dispatch.lsp`. Without AutoCAD installed, `auto` uses the headless ezdxf backend.

## Tools

| Tool | Operations |
|------|------------|
| `drawing` | `new`, `create`, `open`, `info`, `set_variables`, `save`, `save_as_dxf`, `plot_pdf`, `purge`, `get_variables`, `undo`, `redo` |
| `entity` | `create_line`, `create_circle`, `create_polyline`, `create_rectangle`, `create_arc`, `create_ellipse`, `create_mtext`, `create_hatch`, `list`, `count`, `get`, `copy`, `move`, `rotate`, `scale`, `mirror`, `offset`, `array`, `fillet`, `chamfer`, `erase` |
| `layer` | `list`, `create`, `set_current`, `set_properties`, `freeze`, `thaw`, `lock`, `unlock`, `on`, `off`, `delete`, `load_linetype`, `list_linetypes` |
| `block` | `list`, `insert`, `insert_with_attributes`, `get_attributes`, `update_attribute`, `define` |
| `annotation` | `create_text`, `create_dimension_linear`, `create_dimension_aligned`, `create_dimension_angular`, `create_dimension_radius`, `create_leader`, `create_text_style`, `create_dim_style` |
| `pid` | P&ID operations; symbol insertion needs the CAD Tools Online library at `C:\PIDv4-CTO\` |
| `view` | `zoom_extents`, `zoom_window`, `get_screenshot` |
| `system` | `status`, `launch`, `load_dispatcher`, `health`, `get_backend`, `runtime`, `init`, `execute_lisp` |

`execute_lisp` runs arbitrary AutoLISP in your AutoCAD session.

- `drawing new` opens a separate drawing tab from a template (optionally saved to `path`) and leaves open drawings
  alone (full AutoCAD only). `drawing create` erases the active drawing and refuses when it has objects unless
  `force: true`.
- `layer create` / `set_properties` take `plot: false` for non-plotting layers and load missing linetypes (DASHED,
  HIDDEN, CENTER, ...) from `acadiso.lin`. `layer delete` removes empty layers only.
- `drawing set_variables {values: {INSUNITS: 4, LTSCALE: 100}}` refuses security variables (SECURELOAD, TRUSTEDPATHS, ...).

### Backend limits

| Operation | File IPC (live AutoCAD) | ezdxf (headless) |
|-----------|-------------------------|------------------|
| `drawing`: `plot_pdf`, `undo`, `redo`, `new`, `set_variables` | Yes (`new` needs full AutoCAD) | No |
| `layer`: `on`, `off`, `delete`, linetypes; `annotation` styles | Yes | No |
| `entity`: `offset`, `fillet`, `chamfer` | Yes | No |
| `view`: `zoom_extents`, `zoom_window` | Yes | No |
| `system`: `execute_lisp` | Yes | No |
| `block`: `define` | No | Yes |
| `pid`: `list_symbols` | Yes | Yes |
| `pid`: every other operation | Needs `pid_tools.lsp`, see below | Yes, symbols are drawn as labelled placeholders |

### P&ID on a live AutoCAD

The dispatcher calls P&ID functions from `pid_tools.lsp`, which is not included in this repository. Until that file is loaded in AutoCAD, every `pid` operation except `list_symbols` returns `pid_tools.lsp not loaded`. The `attributes` argument of `insert_valve`, `insert_pump` and `insert_tank` is not applied on this backend.

`lisp-code/attribute_tools.lsp` is an optional set of helper commands for use at the AutoCAD command line. The server does not need it.

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `AUTOCADSS_MCP_BACKEND` | `auto` | `auto`, `file_ipc` or `ezdxf` |
| `AUTOCADSS_MCP_IPC_DIR` | `C:/temp` | IPC file folder. If changed, also change `*autocadss-ipc-dir*` in `autocadss_dispatch.lsp` |
| `AUTOCADSS_MCP_IPC_TIMEOUT` | `10` | Seconds to wait for one AutoCAD command (1-300) |
| `AUTOCADSS_MCP_TOOL_TIMEOUT` | `60` | Seconds allowed for one whole tool call |
| `AUTOCADSS_MCP_ONLY_TEXT` | `false` | Disable screenshots |
| `AUTOCADSS_MCP_AUTO_LAUNCH` | `1` | Start AutoCAD when it is closed and load the dispatcher automatically (`0` = off) |
| `AUTOCADSS_MCP_ACAD_EXE` | newest installed | Which `acad.exe` / `acadlt.exe` to start |
| `AUTOCADSS_MCP_START_WAIT` | `240` | Seconds to wait for a started AutoCAD to show a drawing (not counted in the tool timeout) |
| `AUTOCADSS_MCP_PLUGINS_DIR` | `%APPDATA%\Autodesk\ApplicationPlugins` | Where the Autoloader bundle is written |
| `AUTOCADSS_MCP_DEBUG_DETECT_FILE` | unset | Path of a file to write backend-detection details to, for troubleshooting |
| `CTO_LIBRARY_PATH` | `C:/PIDv4-CTO` | P&ID symbol library folder. Used by the ezdxf backend only; the AutoLISP files always read `C:/PIDv4-CTO/` |

## Changes in 0.2.0

- Starts AutoCAD by itself and gets the dispatcher loaded with no person involved (Autoloader bundle + fallback load);
  reconnects when AutoCAD is closed and reopened.
- New: `drawing new`, `drawing set_variables`, layer plot flag, `on`, `off`, `delete`, `load_linetype`,
  `list_linetypes`, `annotation create_text_style`, `annotation create_dim_style`; richer `layer list` and `drawing info`.
- `drawing create` refuses to erase a drawing that has objects unless `force: true`.
- Fixed: `drawing open` on full AutoCAD (opened through ActiveX; `OPEN` from LISP is ignored when several drawings
  can be open); Windows paths (the LISP JSON reader does not unescape backslashes, so paths are sent with `/`);
  `create_line` (built with `entmake`; it used to return the previous object's handle when the line failed, and it
  now also accepts its coordinates in `data`); object snaps are off while a command runs.
- The dispatcher claims a command file before running it, and a dropped trigger is re-sent once.
- Tested on AutoCAD 2027, including a cold start with AutoCAD closed.

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
