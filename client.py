import socket
import threading
import time
import struct
import time

MAGIC_COOKIE = 0xabcddcba
OFFER_MESSAGE_TYPE = 0x2
REQUEST_MESSAGE_TYPE = 0x3
PAYLOAD_MESSAGE_TYPE = 0x4


class SpeedTestClient:
    def __init__(self):
        self.file_size = 0
        self.tcp_connections = 0
        self.udp_connections = 0
        self.running = True
        self.broadcast_port = 13118
        self.server_udp_port = 13117

    def start(self):
        while True:
            self.get_user_input()
            while self.running:
                print("Client started, listening for offer requests...")
                server_info = self.wait_for_offer()
                if server_info:
                    self.run_speed_test(server_info)
                    break
                else:
                    print("No server offer received, retrying...")
                    time.sleep(1)

    def get_user_input(self):
        while True:
            try:
                self.file_size = int(input("Enter file size (bytes): "))
                self.tcp_connections = int(input("Enter number of TCP connections: "))
                self.udp_connections = int(input("Enter number of UDP connections: "))
                if self.file_size > 0 and self.tcp_connections >= 0 and self.udp_connections >= 0:
                    break
                print("Please enter positive numbers")
            except ValueError:
                print("Please enter valid numbers")

    def wait_for_offer(self):
        client_socket = None
        try:
            client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            client_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

            client_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

            client_socket.bind(('', self.broadcast_port))

            client_socket.settimeout(10)

            while self.running:
                try:
                    data, server = client_socket.recvfrom(1024)

                    if len(data) < 8:
                        continue

                    magic_cookie, msg_type, udp_port, tcp_port = struct.unpack('!IbHH', data)


                    if magic_cookie == MAGIC_COOKIE and msg_type == OFFER_MESSAGE_TYPE:
                        print(f"Received offer from server {server[0]}")
                        return {
                            'address': server[0],
                            'udp_port': udp_port,
                            'tcp_port': tcp_port
                        }
                except socket.timeout:
                    print("Timeout waiting for server offer")
                    return None

        except Exception as e:
            print(f"Error while waiting for offer: {e}")
            return None
        finally:
            if client_socket:
                client_socket.close()

    def run_speed_test(self, server_info):
        print(f"Starting speed test with server {server_info['address']}")
        print(f"TCP port: {server_info['tcp_port']}, UDP port: {server_info['udp_port']}")

        threads = []

        for i in range(self.tcp_connections):
            t = threading.Thread(target=self.tcp_transfer, args=(server_info, i + 1))
            threads.append(t)
            t.start()

        for i in range(self.udp_connections):
            t = threading.Thread(target=self.udp_transfer, args=(server_info, i + 1))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        print("\nAll transfers complete, listening to offer requests")

    def tcp_transfer(self, server_info, connection_id):
        sock = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)

            print(f"TCP Connection {connection_id}: Connecting to {server_info['address']}:{server_info['tcp_port']}")
            sock.connect((server_info['address'], server_info['tcp_port']))

            request = struct.pack('!IbQ', MAGIC_COOKIE, REQUEST_MESSAGE_TYPE, self.file_size)
            sock.send(request)
            print(f"TCP Connection {connection_id}: Established and request sent")
            self.measure_tcp_transfer_time(sock, connection_id)

            response = sock.recv(1024)
            if response:
                print(f"TCP Connection {connection_id}: Received response from server")

        except socket.timeout:
            print(f"TCP Connection {connection_id}: Connection timed out")
        except ConnectionRefusedError:
            print(f"TCP Connection {connection_id}: Connection refused by server")
        except Exception as e:
            print(f"TCP Connection {connection_id}: Error - {str(e)}")
        finally:
            if sock:
                sock.close()
                print(f"TCP Connection {connection_id}: Closed")

    def udp_transfer(self, server_info, connection_id):
        sock = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(5)

            request = struct.pack('!IbQ', MAGIC_COOKIE, REQUEST_MESSAGE_TYPE, self.file_size)
            print(f"\nUDP Connection {connection_id}: Sending request to {server_info['address']}:{server_info['udp_port']}")
            sock.sendto(request, (server_info['address'], server_info['udp_port']))
            self.measure_udp_transfer_time(sock, server_info, connection_id)

            try:
                response, addr = sock.recvfrom(1024)
                if response:
                    print(f"UDP Connection {connection_id}: Received response from server")
            except socket.timeout:
                print(f"UDP Connection {connection_id}: No response from server")

        except Exception as e:
            print(f"UDP Connection {connection_id}: Error - {str(e)}")
        finally:
            if sock:
                sock.close()
                print(f"UDP Connection {connection_id}: Closed")

    def measure_tcp_transfer_time(self, sock, connection_id):
        data_received = 0

        try:
            ack = sock.recv(1)
            if not ack:
                print(f"TCP Connection {connection_id}: No acknowledgment received, terminating.")
                return

            start_time = time.time()

            while data_received < self.file_size:
                chunk = sock.recv(1024)
                if not chunk:
                    break
                data_received += len(chunk)

            end_time = time.time()
            total_time = max(end_time - start_time, 1e-6)

        except Exception as e:
            print(f"TCP Connection {connection_id}: Error during transfer - {e}")
            total_time = 1e-6

        speed = (data_received * 8) / total_time
        print(
            f"TCP transfer #{connection_id} finished, total time: {total_time:.6f} seconds, total speed: {speed:.2f} bits/second")

    def measure_udp_transfer_time(self, sock, server_info, connection_id):
        data_received = 0
        packets_sent = 0
        packets_received = 0

        try:
            request = struct.pack('!IbQ', MAGIC_COOKIE, REQUEST_MESSAGE_TYPE, self.file_size)
            sock.sendto(request, (server_info['address'], server_info['udp_port']))
            packets_sent += 1

            ack, _ = sock.recvfrom(1)
            if not ack:
                print(f"UDP Connection {connection_id}: No acknowledgment received, terminating.")
                return

            start_time = time.time()

            while data_received < self.file_size:
                try:
                    chunk, _ = sock.recvfrom(1024)
                    data_received += len(chunk)
                    packets_received += 1
                except socket.timeout:
                    break

            end_time = time.time()
            total_time = max(end_time - start_time, 1e-6)

        except Exception as e:
            print(f"UDP Connection {connection_id}: Error during transfer - {e}")
            total_time = 1e-6

        success_rate = (packets_received / packets_sent) * 100 if packets_sent > 0 else 0
        speed = (data_received * 8) / total_time
        print(
            f"UDP transfer #{connection_id} finished, total time: {total_time:.6f} seconds, total speed: {speed:.2f} bits/second, percentage of packets received successfully: {success_rate:.2f}%")


def main():
    client = SpeedTestClient()
    client.start()



if __name__ == "__main__":
    main()
