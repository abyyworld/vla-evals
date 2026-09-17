"""Entry point for the packaged builds.

PyInstaller needs a module to freeze; the console script in pyproject.toml is
only created by pip, which the downloaded binary never runs. Keeping this one
line here rather than generating it in CI means the packaged build and the
installed one enter through the same function.
"""

from policy_evals.cli import app

if __name__ == "__main__":
    app()
