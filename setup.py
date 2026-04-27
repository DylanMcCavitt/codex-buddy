from setuptools import find_packages, setup


setup(
    name="codex-buddy-bridge",
    version="0.1.0",
    description="Repo-local Codex status bridge for Claude/Codex hardware buddies",
    author="Dylan McCavitt",
    package_dir={"": "src"},
    packages=find_packages("src"),
    python_requires=">=3.9",
    install_requires=["pyserial>=3.5"],
    extras_require={
        "ble": ["bleak>=0.22"],
        "dev": ["pytest>=8"],
    },
    entry_points={
        "console_scripts": [
            "codex-buddy=codex_buddy_bridge.cli:main",
        ],
    },
)
