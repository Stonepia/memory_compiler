"""Dev Memory Compiler (DMC).

A local-first memory/context sidecar for coding agents.

This package is bootstrapped by module M00_BOOTSTRAP. Most submodules
(schemas, store, planner, renderer, retriever, precheck, recorder, distiller,
evals, mcp_server, adapters) are implemented by later modules. At bootstrap
time only the package metadata and a smoke-testable CLI exist.
"""

__version__ = "0.1.0"

__all__ = ["__version__"]
