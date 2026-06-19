#!/usr/bin/env bash

set -e
set -x

bash scripts/test-cov.sh ${@}
coverage html --show-contexts --title "Coverage report"
echo "HTML report generated in htmlcov/"
