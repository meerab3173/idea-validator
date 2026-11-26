#!/bin/sh
# API address is set at runtime, never baked into the image.
set -e
echo "window.__CONFIG__ = { API_URL: \"${API_URL:-/api}\" };" > /usr/share/nginx/html/config.js
exec nginx -g 'daemon off;'
