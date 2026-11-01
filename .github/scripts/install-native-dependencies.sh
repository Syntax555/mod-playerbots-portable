#!/usr/bin/env bash
set -euo pipefail

# The runner's Azure HTTP mirror can stall package index downloads.
sudo bash -euc '
for mirrors in /etc/apt/apt-mirrors*.txt; do
    [[ -f "$mirrors" ]] || continue
    if [[ "$mirrors" == *security* ]]; then
        printf "%s\n" https://security.ubuntu.com/ubuntu/ > "$mirrors"
    else
        printf "%s\n" https://archive.ubuntu.com/ubuntu/ > "$mirrors"
    fi
done
'

options=(-o Acquire::Retries=3 -o Acquire::http::Timeout=30 -o Acquire::https::Timeout=30)
sudo apt-get "${options[@]}" -o APT::Update::Error-Mode=any update
sudo apt-get "${options[@]}" install --no-install-recommends -y "$@"
