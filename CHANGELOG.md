# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.1] - 2026-10-11

### Added
- Installable PyPI package `aether-sim` (import name `aether`) with MIT license and typed package marker.
- Optional extras: `[ai]` (LangGraph / OpenAI helpers), `[postgres]` (Neon/Postgres store), `[all]`.
- Package `__version__` via `importlib.metadata`.
- GitHub Actions CI (pytest + wheel build) and trusted-publishing workflow for release tags.

### Changed
- Core runtime depends only on Pydantic; AI and Postgres stacks are optional.
- AI graph imports are lazy so `from aether import Aether` works without the `[ai]` extra.
- README install path documents `pip install aether-sim` / extras.

### Fixed
- Runtime fixes from the 1.0 / 1.01 development line (dialogue, interact loop, module registration).

## [0.1.0] - 2026-10-11

### Added
- Initial PyPI packaging preview for `aether-sim`.

[1.0.1]: https://github.com/c-blanding/Aether/releases/tag/v1.0.1
[0.1.0]: https://pypi.org/project/aether-sim/0.1.0/
