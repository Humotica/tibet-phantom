"""tibet-phantom CLI entry point."""

import sys


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "demo":
        from demo.hackaway_demo import main as demo_main
        demo_main()
    elif len(sys.argv) > 1 and sys.argv[1] == "info":
        print()
        print("tibet-phantom v0.1.0")
        print("Zero-Footprint AI Materialization")
        print()
        print("  Compute once on GPU. Verify everywhere.")
        print("  Materialize only with proof.")
        print()
        print("  Architecture:")
        print("    tibet-edge     → seal inference output")
        print("    tibet-overlay  → resolve identity (CGNAT-proof)")
        print("    tibet-mesh     → P2P transport (store-and-forward)")
        print("    ghost produce  → context-bound materialization")
        print("    tlex-edge      → token decode (45k tok/sec)")
        print()
        print("  Protocols:")
        print("    TIBET  — provenance chain")
        print("    JIS    — identity binding")
        print("    UPIP   — process integrity + L4 hash")
        print("    RVP    — biometric context verification")
        print()
        print("  Run demo: phantom demo")
        print()
    else:
        print("Usage: phantom [demo|info]")


if __name__ == "__main__":
    main()
