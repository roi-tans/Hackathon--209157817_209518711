import socket
import threading
import struct
import time
import logging
from typing import Tuple
from colorama import Fore, Style, init

init()

MAGIC_COOKIE = 0xabcddcba
OFFER_MESSAGE_TYPE = 0x2
REQUEST_MESSAGE_TYPE = 0x3
PAYLOAD_MESSAGE_TYPE = 0x4


class SpeedTestServer:
    def __init__(self):
        self.udp_port = 13117
        self.broadcast_port = 13118
        self.tcp_port = 12345
        self.running = False
        self.clients = set()
        self.broadcast_socket = None
        self.tcp_socket = None
        self.udp_socket = None
        self.ip_address = self.get_ip()

        logging.basicConfig(
            level=logging.INFO,
            format=f'{Fore.CYAN}[%(asctime)s] %(message)s{Style.RESET_ALL}',
            datefmt='%H:%M:%S'
        )


    def setup_broadcast_socket(self):
        try:
            self.broadcast_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            self.broadcast_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            self.broadcast_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

            self.broadcast_socket.bind(('', 0))
            logging.info(f"{Fore.GREEN}Broadcast socket setup complete{Style.RESET_ALL}")

        except Exception as e:
            logging.error(f"Error setting up broadcast socket: {e}")
            raise

    def setup_tcp_listener(self):
        try:
            self.tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.tcp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

            self.tcp_socket.bind(('', self.tcp_port))
            self.tcp_socket.listen(10)

            logging.info(f"{Fore.GREEN}TCP listener setup complete on port {self.tcp_port}{Style.RESET_ALL}")

        except Exception as e:
            logging.error(f"Error setting up TCP listener: {e}")
            raise

    def setup_udp_listener(self):
        try:
            self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

            self.udp_socket.bind(('', self.udp_port))

            logging.info(f"{Fore.GREEN}UDP listener setup complete on port {self.udp_port}{Style.RESET_ALL}")

        except Exception as e:
            logging.error(f"Error setting up UDP listener: {e}")
            raise

    def get_ip(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except:
            return socket.gethostbyname(socket.gethostname())

    def _handle_tcp_connections(self):
        """Handle incoming TCP connections"""
        while self.running:
            try:
                client_socket, client_address = self.tcp_socket.accept()
                logging.info(f"{Fore.GREEN}New TCP connection from {client_address}{Style.RESET_ALL}")

                client_thread = threading.Thread(
                    target=self._handle_tcp_client,
                    args=(client_socket, client_address)
                )
                client_thread.daemon = True
                client_thread.start()

            except Exception as e:
                if self.running:
                    logging.error(f"Error accepting TCP connection: {e}")

    def _handle_tcp_client(self, client_socket: socket.socket, client_address: Tuple[str, int]):
        try:
            self.clients.add(client_address)

            request_data = client_socket.recv(1024)
            if len(request_data) >= 13:
                magic_cookie, msg_type, file_size = struct.unpack('!IbQ', request_data[:13])

                if magic_cookie == MAGIC_COOKIE and msg_type == REQUEST_MESSAGE_TYPE:
                    logging.info(f"Received request from {client_address}, file size: {file_size}")

                    client_socket.send(b'\x01')

                    bytes_sent = 0
                    while bytes_sent < file_size:
                        chunk_size = min(1024, file_size - bytes_sent)
                        client_socket.send(b'X' * chunk_size)
                        bytes_sent += chunk_size

        except Exception as e:
            logging.error(f"Error handling TCP client {client_address}: {e}")
        finally:
            self.clients.remove(client_address)
            client_socket.close()

    def _handle_udp_connections(self):
        """Handle incoming UDP messages"""
        while self.running:
            try:
                data, client_address = self.udp_socket.recvfrom(1024)
                if len(data) >= 13:
                    magic_cookie, msg_type, file_size = struct.unpack('!IbQ', data[:13])

                    if magic_cookie == MAGIC_COOKIE and msg_type == REQUEST_MESSAGE_TYPE:
                        logging.info(f"Received UDP request from {client_address}, file size: {file_size}")

                        self.udp_socket.sendto(b'\x01', client_address)

                        for _ in range(file_size // 1024 + 1):
                            self.udp_socket.sendto(b'X' * 1024, client_address)

            except Exception as e:
                if self.running:
                    logging.error(f"Error handling UDP message: {e}")

    def start(self):
        try:
            self.running = True

            self.setup_broadcast_socket()
            self.setup_tcp_listener()
            self.setup_udp_listener()

            self.broadcast_thread = threading.Thread(target=self.broadcast_offers)
            self.broadcast_thread.daemon = True
            self.broadcast_thread.start()

            self.tcp_thread = threading.Thread(target=self._handle_tcp_connections)
            self.tcp_thread.daemon = True
            self.tcp_thread.start()

            self.udp_thread = threading.Thread(target=self._handle_udp_connections)
            self.udp_thread.daemon = True
            self.udp_thread.start()

            logging.info(f"""
                {Fore.GREEN}Server started, listening on IP address {self.ip_address}{Style.RESET_ALL}
            """)

            while self.running:
                time.sleep(1)

        except KeyboardInterrupt:
            logging.info(f"{Fore.YELLOW}Server shutting down...{Style.RESET_ALL}")
            self.stop()
        except Exception as e:
            logging.error(f"Error starting server: {e}")
            self.stop()

    def stop(self):
        self.running = False
        try:
            if self.broadcast_socket:
                self.broadcast_socket.close()
            if self.tcp_socket:
                self.tcp_socket.close()
            if self.udp_socket:
                self.udp_socket.close()
        except Exception as e:
            logging.error(f"Error while shutting down: {e}")
    def broadcast_offers(self):
        while self.running:
            try:
                offer_message = struct.pack('!IbHH',
                                            MAGIC_COOKIE,
                                            OFFER_MESSAGE_TYPE,
                                            self.udp_port,
                                            self.tcp_port)

                self.broadcast_socket.sendto(offer_message, ('<broadcast>', self.broadcast_port))
                logging.info(f"{Fore.GREEN}Broadcasted offer message{Style.RESET_ALL}")

                time.sleep(1)
            except Exception as e:
                if self.running:
                    logging.error(f"Error broadcasting offer: {e}")



if __name__ == "__main__":
    server = SpeedTestServer()
    server.start()
