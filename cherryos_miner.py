#!/usr/bin/env python3
"""Foreground Linux CPU client for the public cherryOS mining coordinator."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import multiprocessing as mp
import os
import queue
import re
import struct
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


WALLET_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")
MAX_NONCE = 1 << 64
GPU_GROUPS = 256
GPU_ITERS = 32

SHA256_K = (
    0x428A2F98, 0x71374491, 0xB5C0FBCF, 0xE9B5DBA5, 0x3956C25B, 0x59F111F1,
    0x923F82A4, 0xAB1C5ED5, 0xD807AA98, 0x12835B01, 0x243185BE, 0x550C7DC3,
    0x72BE5D74, 0x80DEB1FE, 0x9BDC06A7, 0xC19BF174, 0xE49B69C1, 0xEFBE4786,
    0x0FC19DC6, 0x240CA1CC, 0x2DE92C6F, 0x4A7484AA, 0x5CB0A9DC, 0x76F988DA,
    0x983E5152, 0xA831C66D, 0xB00327C8, 0xBF597FC7, 0xC6E00BF3, 0xD5A79147,
    0x06CA6351, 0x14292967, 0x27B70A85, 0x2E1B2138, 0x4D2C6DFC, 0x53380D13,
    0x650A7354, 0x766A0ABB, 0x81C2C92E, 0x92722C85, 0xA2BFE8A1, 0xA81A664B,
    0xC24B8B70, 0xC76C51A3, 0xD192E819, 0xD6990624, 0xF40E3585, 0x106AA070,
    0x19A4C116, 0x1E376C08, 0x2748774C, 0x34B0BCB5, 0x391C0CB3, 0x4ED8AA4A,
    0x5B9CCA4F, 0x682E6FF3, 0x748F82EE, 0x78A5636F, 0x84C87814, 0x8CC70208,
    0x90BEFFFA, 0xA4506CEB, 0xBEF9A3F7, 0xC67178F2,
)

GPU_WGSL = """
var<private> K: array<u32, 64> = array<u32, 64>(__SHA256_K__);

struct Params {
    s0: vec4<u32>,
    s1: vec4<u32>,
    hi: u32,
    base: u32,
    bits: u32,
    iters: u32,
};

@group(0) @binding(0) var<uniform> p: Params;
@group(0) @binding(1) var<storage, read_write> res: array<atomic<u32>, 65>;

fn rotr(x: u32, n: u32) -> u32 { return (x >> n) | (x << (32u - n)); }

@compute @workgroup_size(256)
fn main(@builtin(global_invocation_id) gid: vec3<u32>) {
    for (var it = 0u; it < p.iters; it = it + 1u) {
        let lo = p.base + gid.x * p.iters + it;
        var w: array<u32, 64>;
        w[0] = p.s0.x; w[1] = p.s0.y; w[2] = p.s0.z; w[3] = p.s0.w;
        w[4] = p.s1.x; w[5] = p.s1.y; w[6] = p.s1.z; w[7] = p.s1.w;
        w[8] = p.hi; w[9] = lo; w[10] = 0x80000000u;
        w[11] = 0u; w[12] = 0u; w[13] = 0u; w[14] = 0u; w[15] = 320u;
        for (var i = 16u; i < 64u; i = i + 1u) {
            let x = w[i - 15u];
            let y = w[i - 2u];
            let s0 = rotr(x, 7u) ^ rotr(x, 18u) ^ (x >> 3u);
            let s1 = rotr(y, 17u) ^ rotr(y, 19u) ^ (y >> 10u);
            w[i] = w[i - 16u] + s0 + w[i - 7u] + s1;
        }
        var a = 0x6a09e667u; var b = 0xbb67ae85u; var c = 0x3c6ef372u; var d = 0xa54ff53au;
        var e = 0x510e527fu; var f = 0x9b05688cu; var g = 0x1f83d9abu; var h = 0x5be0cd19u;
        for (var i = 0u; i < 64u; i = i + 1u) {
            let s1 = rotr(e, 6u) ^ rotr(e, 11u) ^ rotr(e, 25u);
            let ch = (e & f) ^ (~e & g);
            let t1 = h + s1 + ch + K[i] + w[i];
            let s0 = rotr(a, 2u) ^ rotr(a, 13u) ^ rotr(a, 22u);
            let maj = (a & b) ^ (a & c) ^ (b & c);
            let t2 = s0 + maj;
            h = g; g = f; f = e; e = d + t1; d = c; c = b; b = a; a = t1 + t2;
        }
        let h0 = a + 0x6a09e667u;
        var z = countLeadingZeros(h0);
        if (h0 == 0u) { z = 32u + countLeadingZeros(b + 0xbb67ae85u); }
        if (z >= p.bits) {
            let slot = atomicAdd(&res[0], 1u);
            if (slot < 64u) { atomicStore(&res[slot + 1u], lo); }
        }
    }
}
""".replace(
    "__SHA256_K__", ", ".join(f"0x{value:08x}u" for value in SHA256_K)
)


def leading_zero_bits(digest: bytes) -> int:
    zeros = 0
    for byte in digest:
        if byte == 0:
            zeros += 8
            continue
        return zeros + (8 - byte.bit_length())
    return len(digest) * 8


def mine_worker(
    seed: bytes,
    bits: int,
    worker_id: int,
    worker_count: int,
    intensity: float,
    stop_event: Any,
    message_queue: Any,
) -> None:
    nonce = worker_id
    hashed = 0
    while not stop_event.is_set():
        digest = hashlib.sha256(seed + nonce.to_bytes(8, "big")).digest()
        hashed += 1
        if leading_zero_bits(digest) >= bits:
            message_queue.put(("found", nonce))
        nonce = (nonce + worker_count) % MAX_NONCE
        if hashed >= 8192:
            message_queue.put(("hashes", hashed))
            hashed = 0
            if intensity < 1.0:
                time.sleep((1.0 - intensity) * 0.004)
    if hashed:
        message_queue.put(("hashes", hashed))


def gpu_worker(
    seed: bytes,
    bits: int,
    intensity: float,
    stop_event: Any,
    message_queue: Any,
) -> None:
    try:
        import wgpu

        adapter = wgpu.gpu.request_adapter_sync(power_preference="high-performance")
        if adapter is None:
            raise RuntimeError("no WebGPU adapter found")
        device = adapter.request_device_sync()
        adapter_name = str(adapter.info.get("device") or adapter.info.get("description") or "WebGPU")
        message_queue.put(("device", adapter_name))

        layout = device.create_bind_group_layout(
            entries=[
                {
                    "binding": 0,
                    "visibility": wgpu.ShaderStage.COMPUTE,
                    "buffer": {"type": "uniform"},
                },
                {
                    "binding": 1,
                    "visibility": wgpu.ShaderStage.COMPUTE,
                    "buffer": {"type": "storage"},
                },
            ]
        )
        pipeline_layout = device.create_pipeline_layout(bind_group_layouts=[layout])
        shader = device.create_shader_module(code=GPU_WGSL)
        pipeline = device.create_compute_pipeline(
            layout=pipeline_layout,
            compute={"module": shader, "entry_point": "main"},
        )
        uniform_buffer = device.create_buffer(
            size=48,
            usage=wgpu.BufferUsage.UNIFORM | wgpu.BufferUsage.COPY_DST,
        )
        result_buffer = device.create_buffer(
            size=65 * 4,
            usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_SRC,
        )
        bind_group = device.create_bind_group(
            layout=layout,
            entries=[
                {"binding": 0, "resource": {"buffer": uniform_buffer}},
                {"binding": 1, "resource": {"buffer": result_buffer}},
            ],
        )

        seed_words = struct.unpack(">8I", seed)
        span = GPU_GROUPS * 256 * GPU_ITERS
        word_span = 1 << 32
        hi = 0
        base = 0
        while not stop_event.is_set():
            params = struct.pack(
                "<12I", *seed_words, hi, base, bits, GPU_ITERS
            )
            device.queue.write_buffer(uniform_buffer, 0, params)
            encoder = device.create_command_encoder()
            compute_pass = encoder.begin_compute_pass()
            compute_pass.set_pipeline(pipeline)
            compute_pass.set_bind_group(0, bind_group)
            compute_pass.dispatch_workgroups(GPU_GROUPS)
            compute_pass.end()
            device.queue.submit([encoder.finish()])

            raw_result = device.queue.read_buffer(result_buffer, 0, 65 * 4)
            result = struct.unpack("<65I", bytes(raw_result))
            for index in range(min(result[0], 64)):
                message_queue.put(("found", (hi << 32) | result[index + 1]))
            message_queue.put(("hashes", span))

            base += span
            if base >= word_span:
                hi = (hi + base // word_span) % word_span
                base %= word_span
            if intensity < 1.0:
                time.sleep((1.0 - intensity) * 0.004)
    except Exception as error:
        message_queue.put(("error", str(error)))
        stop_event.set()


def request_json(
    coordinator: str,
    path: str,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    body = None
    headers = {"content-type": "application/json", "user-agent": "cherryos-linux-miner/0.1"}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        coordinator.rstrip("/") + path,
        data=body,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        try:
            details = json.loads(error.read().decode("utf-8"))
            message = details.get("error", str(error))
        except (json.JSONDecodeError, UnicodeDecodeError):
            message = str(error)
        raise RuntimeError(message) from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"coordinator unavailable: {error.reason}") from error
    if not isinstance(result, dict):
        raise RuntimeError("coordinator returned a non-object response")
    return result


def get_challenge(coordinator: str, wallet: str) -> dict[str, Any]:
    query = urllib.parse.urlencode({"wallet": wallet})
    return request_json(coordinator, f"/v1/mine/challenge?{query}")


def submit_shares(
    coordinator: str,
    wallet: str,
    challenge: dict[str, Any],
    bits: int,
    nonces: list[int],
    device: str,
    backend: str,
) -> dict[str, Any]:
    payload = {
        "wallet": wallet,
        "id": challenge["id"],
        "issuedAt": challenge["issuedAt"],
        "bits": bits,
        "nonces": [f"{nonce:016x}" for nonce in nonces],
        "device": device,
        "backend": backend,
    }
    return request_json(coordinator, "/v1/mine/submit", "POST", payload)


def choose_bits(challenge: dict[str, Any], hashrate: float, requested: int | None) -> int:
    minimum = int(challenge["minBits"])
    maximum = int(challenge["maxBits"])
    if requested is not None:
        if not minimum <= requested <= maximum:
            raise ValueError(f"--bits must be between {minimum} and {maximum}")
        return requested
    if hashrate <= 0:
        return minimum
    estimate = math.floor(math.log2(max(1.0, hashrate * 2)))
    return max(minimum, min(maximum, estimate))


def start_workers(
    challenge: dict[str, Any],
    bits: int,
    worker_count: int,
    intensity: float,
    stop_event: Any,
    message_queue: Any,
    backend: str,
) -> list[mp.Process]:
    seed = bytes.fromhex(challenge["seed"])
    if backend == "gpu":
        worker = mp.Process(
            target=gpu_worker,
            args=(seed, bits, intensity, stop_event, message_queue),
            name="cherryos-miner-gpu",
        )
        worker.start()
        return [worker]

    workers = []
    for worker_id in range(worker_count):
        worker = mp.Process(
            target=mine_worker,
            args=(seed, bits, worker_id, worker_count, intensity, stop_event, message_queue),
            name=f"cherryos-miner-{worker_id}",
        )
        worker.start()
        workers.append(worker)
    return workers


def stop_workers(workers: list[mp.Process], stop_event: Any) -> None:
    stop_event.set()
    for worker in workers:
        worker.join(timeout=2)
    for worker in workers:
        if worker.is_alive():
            worker.terminate()
            worker.join()


def flush_pending(
    coordinator: str,
    wallet: str,
    challenge: dict[str, Any],
    bits: int,
    pending: list[int],
    device: str,
    backend: str,
) -> tuple[int, int, float, float]:
    accepted = rejected = 0
    credited = 0.0
    balance = 0.0
    while pending:
        batch = pending[:256]
        del pending[:256]
        result = submit_shares(
            coordinator, wallet, challenge, bits, batch, device, backend
        )
        accepted += int(result.get("accepted", 0))
        rejected += int(result.get("rejected", 0)) + int(result.get("duplicate", 0))
        credited += float(result.get("credited", 0))
        balance = float(result.get("credits", 0))
    return accepted, rejected, credited, balance


def check_coordinator(coordinator: str, wallet: str) -> None:
    health = request_json(coordinator, "/health")
    challenge = get_challenge(coordinator, wallet)
    print(json.dumps({"health": health, "challenge": challenge}, indent=2))


def select_backend(requested: str) -> tuple[str, str]:
    if requested == "cpu":
        return "cpu", "linux-cpu"
    try:
        import wgpu

        adapter = wgpu.gpu.request_adapter_sync(power_preference="high-performance")
    except ImportError as error:
        if requested == "gpu":
            raise RuntimeError("GPU backend requires: python3 -m pip install -r requirements-gpu.txt") from error
        return "cpu", "linux-cpu"
    if adapter is None:
        if requested == "gpu":
            raise RuntimeError("no WebGPU adapter found")
        return "cpu", "linux-cpu"
    return "gpu", str(adapter.info.get("device") or adapter.info.get("description") or "WebGPU")


def run(args: argparse.Namespace) -> int:
    if not WALLET_RE.fullmatch(args.wallet):
        raise ValueError("wallet must be a 40-hex-character 0x address")
    if not 0.05 <= args.intensity <= 1.0:
        raise ValueError("--intensity must be between 0.05 and 1.0")
    if args.check:
        check_coordinator(args.coordinator, args.wallet)
        return 0

    backend, device = select_backend(args.backend)
    worker_count = args.threads or max(1, (os.cpu_count() or 2) - 1)
    if worker_count < 1:
        raise ValueError("--threads must be at least 1")

    message_queue: Any = mp.Queue()
    stop_event: Any = mp.Event()
    pending: list[int] = []
    total_hashes = 0
    total_found = 0
    last_hashes = 0
    last_report = time.monotonic()
    last_flush = time.monotonic()
    challenge = get_challenge(args.coordinator, args.wallet)
    bits = choose_bits(challenge, 0, args.bits)
    workers = start_workers(
        challenge, bits, worker_count, args.intensity, stop_event, message_queue, backend
    )
    started = time.monotonic()
    print(
        f"Mining with {backend} on {device}, intensity {args.intensity:.0%}; "
        f"challenge {challenge['id']} at {bits} bits. Press Ctrl-C to stop.",
        flush=True,
    )

    try:
        while True:
            try:
                kind, value = message_queue.get(timeout=0.25)
                if kind == "hashes":
                    total_hashes += int(value)
                elif kind == "found":
                    pending.append(int(value))
                    total_found += 1
                elif kind == "device":
                    device = str(value)
                elif kind == "error":
                    raise RuntimeError(f"{backend} worker failed: {value}")
            except queue.Empty:
                pass

            now = time.monotonic()
            if now - last_flush >= 4 and pending:
                accepted, rejected, credited, balance = flush_pending(
                    args.coordinator, args.wallet, challenge, bits, pending, device, backend
                )
                print(
                    f"shares found={total_found} accepted={accepted} rejected={rejected} "
                    f"credited={credited:.4f} balance={balance:.4f}",
                    flush=True,
                )
                last_flush = now

            if now - last_report >= 5:
                elapsed = max(0.001, now - started)
                rate = (total_hashes - last_hashes) / max(0.001, now - last_report)
                print(
                    f"hashrate={rate:,.0f} H/s total={total_hashes:,} "
                    f"uptime={int(elapsed)}s bits={bits}",
                    flush=True,
                )
                last_hashes = total_hashes
                desired = choose_bits(challenge, rate, args.bits)
                expires_at = int(challenge["expiresAt"]) / 1000
                if args.bits is None and (
                    abs(desired - bits) >= 2 or time.time() >= expires_at - 60
                ):
                    if pending:
                        flush_pending(
                            args.coordinator,
                            args.wallet,
                            challenge,
                            bits,
                            pending,
                            device,
                            backend,
                        )
                    stop_workers(workers, stop_event)
                    challenge = get_challenge(args.coordinator, args.wallet)
                    bits = choose_bits(challenge, rate, args.bits)
                    stop_event = mp.Event()
                    workers = start_workers(
                        challenge,
                        bits,
                        worker_count,
                        args.intensity,
                        stop_event,
                        message_queue,
                        backend,
                    )
                    print(f"rotated to challenge {challenge['id']} at {bits} bits", flush=True)
                last_report = now
    except KeyboardInterrupt:
        print("\nStopping...", flush=True)
    finally:
        stop_workers(workers, stop_event)
        while True:
            try:
                kind, value = message_queue.get_nowait()
                if kind == "hashes":
                    total_hashes += int(value)
                elif kind == "found":
                    pending.append(int(value))
            except queue.Empty:
                break
        if pending:
            try:
                accepted, rejected, credited, balance = flush_pending(
                    args.coordinator, args.wallet, challenge, bits, pending, device, backend
                )
                print(
                    f"final shares accepted={accepted} rejected={rejected} "
                    f"credited={credited:.4f} balance={balance:.4f}",
                    flush=True,
                )
            except RuntimeError as error:
                print(f"final submit failed: {error}", file=sys.stderr)
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Foreground cherryOS Linux CPU/GPU miner")
    parser.add_argument("--wallet", required=True, help="destination public wallet address")
    parser.add_argument(
        "--coordinator",
        default="https://cherryos.fly.dev",
        help="coordinator base URL",
    )
    parser.add_argument("--threads", type=int, help="number of CPU worker processes")
    parser.add_argument(
        "--backend",
        choices=("auto", "gpu", "cpu"),
        default="auto",
        help="compute backend (default: auto; GPU uses WebGPU/Vulkan)",
    )
    parser.add_argument(
        "--intensity",
        type=float,
        default=0.75,
        help="CPU duty factor from 0.05 to 1.0 (default: 0.75)",
    )
    parser.add_argument("--bits", type=int, help="fixed difficulty; otherwise auto-tune")
    parser.add_argument(
        "--check",
        action="store_true",
        help="check coordinator and fetch one challenge without mining",
    )
    return parser.parse_args()


if __name__ == "__main__":
    try:
        raise SystemExit(run(parse_args()))
    except (RuntimeError, ValueError, KeyError) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(2)