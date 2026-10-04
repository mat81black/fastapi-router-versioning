#!/usr/bin/env bash

set -e
set -x

zensical build --clean --strict ${@}
