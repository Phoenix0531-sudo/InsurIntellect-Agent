# -*- coding: utf-8 -*-
from setuptools import setup, find_packages

with open("README.md", encoding="utf-8") as f:
    long_description = f.read()

MAIN_REQUIREMENTS = [
    "fastapi>=0.104.0",
    "uvicorn[standard]>=0.33.0",
    "pydantic>=2.0.0",
    "pydantic-settings>=2.0.0",
    "python-dotenv>=1.0.0",
    "loguru>=0.7.0",
    "openai>=1.0.0",
    "langchain>=0.2.0",
    "langchain-openai>=0.1.0",
    "langchain-chroma>=0.1.0",
    "langchain-community>=0.2.0",
    "langchain-core>=0.2.0",
    "langchain-text-splitters>=0.2.0",
    "langchain-huggingface>=0.1.0",
    "sentence-transformers>=3.0.0",
    "chromadb>=0.5.0",
    "PyMuPDF>=1.24.0",
    "python-multipart>=0.0.20",
    "sqlalchemy>=2.0.0",
    "aiosqlite>=0.20.0",
    "numpy>=1.24.0",
    "scikit-learn>=1.3.0",
    "jieba>=0.42.0",
    "rank_bm25>=0.2.0",
    "tqdm>=4.67.0",
    "requests>=2.32.0",
    "httpx>=0.28.0",
    "aiofiles>=24.0.0",
    "PyYAML>=6.0.0",
    "psutil>=5.9.0",
    "tenacity>=8.5.0",
]

ADVANCED_REQUIREMENTS = [
    "pypdf>=5.0.0",
    "PyPDF2>=3.0.0",
    "pdfplumber>=0.11.0",
    "pytesseract>=0.3.0",
    "Pillow>=10.0.0",
    "beautifulsoup4>=4.12.0",
    "unstructured>=0.18.0",
    "asyncpg>=0.29.0",
    "pandas>=2.0.0",
]

DEV_REQUIREMENTS = [
    "pytest>=8.0.0",
    "ruff>=0.6.0",
    "httpx>=0.28.0",
]

setup(
    name="insurintellect-agent",
    version="1.0.0",
    description=(
        "Local insurance-clause RAG demo with hybrid retrieval, cited answers, "
        "and regulated-advice refusal boundaries"
    ),
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/Phoenix0531-sudo/InsurIntellect-Agent",
    packages=find_packages(),
    include_package_data=True,
    install_requires=MAIN_REQUIREMENTS,
    extras_require={
        "advanced": ADVANCED_REQUIREMENTS,
        "dev": DEV_REQUIREMENTS,
        "all": ADVANCED_REQUIREMENTS + DEV_REQUIREMENTS,
    },
    python_requires=">=3.11",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Science/Research",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Operating System :: OS Independent",
    ],
)
