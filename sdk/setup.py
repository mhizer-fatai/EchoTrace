from setuptools import setup, find_packages

setup(
    name="echotrace-sdk",
    version="1.0.0",
    description="Python SDK for EchoTrace: AI Agent Decision Provenance & Temporal Memory Engine",
    author="EchoTrace Team",
    packages=find_packages(),
    install_requires=[
        "requests>=2.31.0",
        "pydantic>=2.6.0",
    ],
    python_requires=">=3.9",
)
