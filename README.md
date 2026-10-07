# cherryOS Linux miner

This is a transparent foreground CPU/GPU client for the public cherryOS
coordinator. It uses the same public challenge and share format as the browser
miner:

```text
SHA-256(seed || nonce_as_8_byte_big_endian)
```

The client only needs a public wallet address. It does not request or store a
private key, install persistence, or hide its CPU usage.

## Requirements

- Linux
- Python 3.10 or newer
- Network access to the coordinator
- `requirements-gpu.txt` for GPU mode

## Install GPU support

The GPU backend uses Python `wgpu` and the system's Vulkan, DirectX 12, or
Metal adapter. Linux GPU drivers must already be installed.

```bash
python3 -m pip install -r requirements-gpu.txt
```

## Check the coordinator

```bash
python3 cherryos_miner.py --wallet 0xYOUR_40_HEX_ADDRESS --check
```

## Start mining

```bash
python3 cherryos_miner.py --wallet 0xYOUR_40_HEX_ADDRESS --backend gpu --intensity 0.75
```

Use `--backend auto` to prefer GPU and fall back to CPU when `wgpu` or a GPU
adapter is unavailable. Use `--backend cpu --threads 4` to force CPU mode.
Use `--bits` to pin a difficulty accepted by the current challenge. Without it,
the client adjusts difficulty from the measured hashrate and rotates expired
challenges.

This client is based on the currently public browser protocol. The coordinator
or protocol may change, so rejected shares should be treated as a compatibility
failure rather than evidence that the wallet is wrong.
