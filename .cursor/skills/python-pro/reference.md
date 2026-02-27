# Python Pro — Reference

Detailed capabilities and knowledge for the python-pro skill. Use when you need specifics on language features, tooling, or patterns.

## Modern Python features

- Python 3.12+: better error messages, performance, type system
- Async/await: asyncio, aiohttp, trio
- Context managers and `with` for resources
- Dataclasses, Pydantic, modern validation
- Pattern matching (match statements)
- Type hints, generics, Protocol
- Descriptors, metaclasses (when justified)
- Generators, itertools, memory-efficient processing

## Tooling and environment

- **uv**: fast package manager; prefer over pip for new projects
- **ruff**: format + lint (replaces black, isort, flake8)
- **mypy / pyright**: static type checking
- **pyproject.toml**: project and tool config
- venv, pipenv, or uv for virtual envs
- Pre-commit for quality automation
- Lock files and reproducible installs

## Testing and quality

- pytest and plugins; fixtures and factories
- Hypothesis for property-based tests
- pytest-cov, coverage.py
- pytest-benchmark for performance
- Integration tests and CI (e.g. GitHub Actions)

## Performance and optimization

- Profiling: cProfile, py-spy, memory_profiler
- Async for I/O-bound; multiprocessing / concurrent.futures for CPU-bound
- Caching: functools.lru_cache, external caches
- DB: SQLAlchemy 2.0+, async ORMs
- NumPy/Pandas: vectorization and efficient patterns

## Web and APIs

- FastAPI (APIs, docs, async)
- Django, Flask when appropriate
- Pydantic for validation/serialization
- SQLAlchemy 2.0+ with async
- Celery + Redis for background work
- WebSockets: FastAPI, Django Channels
- Auth and authorization patterns

## Data and ML

- NumPy, Pandas; visualization (Matplotlib, Seaborn, Plotly)
- Scikit-learn; Jupyter/IPython
- ETL and pipelines; modern ML libs (PyTorch, TensorFlow)
- Validation and performance on large data

## DevOps and production

- Docker and multi-stage builds
- Kubernetes and cloud (AWS, GCP, Azure)
- Structured logging and APM
- Config and env vars; security and scanning
- CI/CD and performance monitoring

## Advanced patterns

- Design patterns (Singleton, Factory, Observer, etc.)
- SOLID in Python; dependency injection
- Event-driven and messaging
- Functional style; decorators and context managers
- Metaprogramming; plugin architectures

## Knowledge base (priorities)

- Python 3.12+ features and performance
- Current ecosystem: uv, ruff, pyright
- Web: FastAPI, Django 5.x
- Async and asyncio patterns
- Packaging, security, profiling, testing practices
