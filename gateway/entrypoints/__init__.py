"""
gateway/entrypoints/__init__.py

Re-export entrypoint HTTP standar dari Nameko (`nameko.web.handlers.http`)
agar bisa diimpor sebagai `from gateway.entrypoints import http`,
sesuai konvensi yang dipakai di service.py.

Nameko sudah menyediakan decorator `http` bawaan untuk membuat
endpoint REST sederhana:

    @http("GET", "/path/<int:id>")
    def handler(self, request, id):
        ...

Dokumentasi: https://www.nameko.io/
"""

from nameko.web.handlers import http  # noqa: F401
