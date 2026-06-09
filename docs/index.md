# ZDEM Archiver

<div align="center">

Data purge utility for ZDEM numerical simulations.

![Python](https://img.shields.io/badge/Python-3.8%2B-blue)
![PyQt5](https://img.shields.io/badge/PyQt-5.15-green)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)

</div>

## Overview

A native GUI purging utility for ZDEM discrete element method simulations. Safely strips redundant output data while preserving core source code and configuration files.

## Quick Start

```bash
pip install -r requirements.txt
python zdem_archiver_main.py
```

## Docker

```bash
docker build -t zdem-archiver .
docker run --rm zdem-archiver
```

*Docker is for build verification only; GUI requires a native display.*

## Repository

<https://github.com/Phoenix0531-sudo/ZDEM_Archiver>

## License

MIT License
