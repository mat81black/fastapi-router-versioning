#!/usr/bin/env bash
set -x

ruff check fastapi_router_versioning tests examples --fix
ruff format fastapi_router_versioning tests examples
