#!/bin/sh
# stt-helper をビルドする（bin/stt-helper に出る）。
set -eu
cd "$(dirname "$0")"
mkdir -p bin
swiftc -O -parse-as-library stt_helper.swift -o bin/stt-helper
