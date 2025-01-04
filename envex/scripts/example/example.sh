#!/bin/sh
SCRIPT_DIR=$(dirname "$0")

SOURCE_NAME=example.env
TEMPLATE_NAME=example_env_template.env

TEMPLATE="$SCRIPT_DIR/$TEMPLATE_NAME"
SOURCE="$SCRIPT_DIR/$SOURCE_NAME"

OUTPUT=test.env

$SCRIPT_DIR/../envsecrets.py -e -s "$SCRIPT_DIR" -d "$SOURCE_NAME" -t "$TEMPLATE" -k example -C "~/.certs/cacert.pem" -v "$OUTPUT"
