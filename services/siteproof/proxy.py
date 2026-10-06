"""Pin DNS at socket connect. Browser network has no direct external route.
CONNECT targets only port 443. HTTP targets port 80. Both reject every non-global resolved IP.
"""

import asyncio
import socket
from urllib.parse import urlsplit

from .security import public_address


async def relay(source, target):
    count = 0
    while data := await asyncio.wait_for(source.read(65536), 30):
        count += len(data)
        if count > 20_000_000:
            raise ValueError("Resource transfer limit exceeded")
        target.write(data)
        await target.drain()


async def handle(reader, writer):
    upstream = None
    try:
        header = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 10)
        if len(header) > 16384:
            raise ValueError("Headers too large")
        first = header.split(b"\r\n")[0].decode()
        method, target, version = first.split(" ", 2)
        if method == "CONNECT":
            host, port = target.rsplit(":", 1)
            port = int(port)
            if port != 443:
                raise ValueError("Unsupported port")
        else:
            parsed = urlsplit(target)
            host = parsed.hostname
            port = parsed.port or 80
            if parsed.scheme != "http" or port != 80 or parsed.username is not None or parsed.password is not None:
                raise ValueError("Unsupported URL")
        addresses = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
        if not addresses or any(not public_address(row[4][0]) for row in addresses):
            raise ValueError("Non-public destination")
        # Connect literal approved IP, eliminating resolve/connect rebinding gap.
        remote, upstream = await asyncio.wait_for(asyncio.open_connection(addresses[0][4][0], port), 10)
        if method == "CONNECT":
            writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            await writer.drain()
        else:
            parsed = urlsplit(target)
            path = parsed.path or "/"
            if parsed.query:
                path += "?" + parsed.query
            upstream.write((method + " " + path + " " + version + "\r\n").encode() + header.split(b"\r\n", 1)[1])
            await upstream.drain()
        await asyncio.wait_for(asyncio.gather(relay(reader, upstream), relay(remote, writer)), 60)
    except Exception:
        try:
            writer.write(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n")
            await writer.drain()
        except Exception:
            pass
    finally:
        writer.close()
        if upstream:
            upstream.close()


async def main():
    server = await asyncio.start_server(handle, "0.0.0.0", 8080, limit=16384)
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
