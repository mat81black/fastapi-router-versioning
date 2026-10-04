#!/usr/bin/env bash

set -e
set -x

mypy fastapi_router_versioning examples
ty check fastapi_router_versioning examples
ruff check fastapi_router_versioning tests examples docs_src
ruff format fastapi_router_versioning tests examples --check
