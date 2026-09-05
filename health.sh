#!/usr/bin/env bash
curl -fsS "http://127.0.0.1:${APP_PORT:-3000}/health"
