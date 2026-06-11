#!/usr/bin/python3
import argparse
import http.server
import io
import os
import socketserver
import urllib.parse
import urllib.request

import get_data
import mdb
import wue

PORT = 8000
server_args = None


class MDBServer(http.server.SimpleHTTPRequestHandler):

    def do_GET(self):
        # Custom endpoint to trigger the update pipeline
        if self.path == '/update':
            try:
                print("🔄 Syncing from Google Sheets...")
                filenames = get_data.sync_sheets(server_args.key_file, server_args.sheet_url, server_args.worksheets)
                print("🔨 Rebuilding database...")
                mdb.build_db(filenames, server_args.db_file, 'machines')

                self.send_response(200)
                self.send_header("Content-type", "text/plain")
                self.end_headers()
                self.wfile.write(b"Update successful, database rebuilt.")
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(f"Update failed: {str(e)}".encode())
                raise e

        # When serving db file, force update cache if the file changed
        elif server_args.db_file in self.path:
            full_path = self.translate_path(self.path)
            stats = os.stat(full_path)
            self.send_response(200)
            self.send_header('Content-type', 'application/x-sqlite3')
            self.send_header('Last-Modified', self.date_time_string(stats.st_mtime))
            self.end_headers()
            # Manually serve the file content
            with open(full_path, 'rb') as f:
                self.wfile.write(f.read())

        # Pass on queries to monitoring system
        elif self.path.startswith('/mon'):
            query = urllib.parse.urlparse(self.path).query
            params = urllib.parse.parse_qs(query)
            ip = params.get('ip')[0]

            target_url = f"{server_args.mon_url}?q=(host.ip:{ip})&_source=host.ip,message,code,mac,@timestamp&sort=@timestamp:desc&size=1"
            with urllib.request.urlopen(target_url) as response:
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(response.read())

        # query monitoring system and generate an image showing water use effectiveness
        elif self.path.startswith('/wue'):
            img_bytes = wue.plot(wue.get_data(server_args.mon_url))
            self.send_response(200)
            self.send_header('Content-type', 'image/png')
            self.send_header('Content-length', len(img_bytes))
            self.end_headers()
            self.wfile.write(img_bytes)

        # Otherwise, serve files normally (index.html, etc.)
        else:
            super().do_GET()


    def list_directory(self, path):
        """Parent class list_directory doesn't include file sizes"""
        try:
            list = os.listdir(path)
        except OSError as e:
            self.send_error(404, f"{e}")
            return None

        list.sort(key=lambda a: a.lower())
        r = []
        displaypath = urllib.parse.unquote(self.path)

        # Start building the HTML response
        r.append('<!DOCTYPE html><html><head><meta charset="utf-8">')
        r.append(f'<title>Directory listing for {displaypath}</title></head>')
        r.append('<body><ul>')

        for name in list:
            fullname = os.path.join(path, name)
            displayname = linkname = name
            size = ""

            # Append / for directories, get size for files
            if os.path.isdir(fullname):
                displayname = name + "/"
                linkname = name + "/"
            else:
                # Calculate size in MB
                file_size = os.path.getsize(fullname) / (1024 * 1024)
                size = f"({file_size:.1f} MB)"

            r.append('<li><a href="%s">%s</a> %s</li>'
                    % (urllib.parse.quote(linkname), displayname, size))

        r.append('</ul></body></html>')

        # Convert list to bytes
        encoded = '\n'.join(r).encode('utf-8', 'surrogateescape')
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()

        return io.BytesIO(encoded)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--key_file', type=str, default="qrb-labs-mdb.json")
    parser.add_argument('--sheet_url', type=str, help="Google spreadsheet url")
    parser.add_argument('--worksheets', nargs='+',
                        help='list of worksheet names eg --worksheets "Miners" "Other miners"',  default=["Miners"])
    parser.add_argument('--db_file', type=str, default="mdb.sqlite")
    parser.add_argument('--mon_url', type=str, default="http://localhost:9200/_search", help="Monitoring search URL")
    server_args = parser.parse_args()

    with socketserver.TCPServer(("", PORT), MDBServer) as httpd:
        print(f"🚀 Server running at http://localhost:{PORT}")
        print(f"🔗 Visit http://localhost:{PORT}/update to refresh data")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down server...")
            httpd.server_close()
