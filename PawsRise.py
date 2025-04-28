
import os
import sys
import subprocess
import requests
import re
import time
import socket
import concurrent.futures
import tempfile
from pathlib import Path

# ANSI color codes
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BOLD = "\033[1m"
RESET = "\033[0m"

def check_sudo():
    """Check if the script is running with sudo privileges"""
    return os.geteuid() == 0

def download_file(url, destination):
    """Download a file from URL to destination"""
    response = requests.get(url)
    with open(destination, 'wb') as f:
        f.write(response.content)

def extract_servers(config_file):
    """Extract server information from the config file"""
    servers = []
    with open(config_file, 'r') as f:
        content = f.read()

    # Extract all remote lines with comments
    remote_pattern = r'remote\s+(\d+\.\d+\.\d+\.\d+)\s+(\d+)\s+#\s+(vpn\d+-\w+\.riseup\.net)\s+\(([^)]+)\)'
    matches = re.findall(remote_pattern, content)

    # Group by server name to avoid duplicates
    servers_dict = {}
    for ip, port, hostname, location in matches:
        if hostname not in servers_dict:
            servers_dict[hostname] = {
                'hostname': hostname,
                'ip': ip,
                'location': location,
                'ports': []
            }
        if port not in servers_dict[hostname]['ports']:
            servers_dict[hostname]['ports'].append(port)

    # Convert to list
    return list(servers_dict.values())

def test_server_speed(server, timeout=2):
    """Test the response time of a server"""
    start_time = time.time()
    try:
        # Try connecting to port 80
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect((server['ip'], 80))
        sock.close()
        response_time = time.time() - start_time
        return server, response_time
    except (socket.timeout, socket.error):
        # If connection fails or times out, assign a high value
        return server, float('inf')

def find_fastest_server(servers):
    """Find the fastest server by testing all of them in parallel"""

    # Use ThreadPoolExecutor to test servers in parallel
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(test_server_speed, server) for server in servers]
        results = []

        for future in concurrent.futures.as_completed(futures):
            results.append(future.result())

    # Filter out unreachable servers (those with response_time = inf)
    reachable_servers = [(server, rt) for server, rt in results if rt != float('inf')]

    if not reachable_servers:
        return [(server, float('inf')) for server in servers]

    # Sort by response time (fastest first)
    reachable_servers.sort(key=lambda x: x[1])

    return reachable_servers

def create_server_specific_config(base_config_path, server, output_path):
    """Create a server-specific OpenVPN config file"""
    with open(base_config_path, 'r') as f:
        content = f.read()

    # Remove all remote lines
    content = re.sub(r'remote\s+\d+\.\d+\.\d+\.\d+\s+\d+.*\n', '', content)

    # Add specific remote lines for the selected server
    server_lines = []
    for port in server['ports']:
        server_lines.append(f"remote {server['ip']} {port} # {server['hostname']} ({server['location']})")

    # Add the remote lines at the beginning of the config
    server_specific_content = "\n".join(server_lines) + "\n\n" + content

    # Write the new config file
    with open(output_path, 'w') as f:
        f.write(server_specific_content)

    return output_path

def verify_connection(expected_location):
    """Verify the connection by checking public IP and location"""
    try:
        time.sleep(5)  # Give some time for the connection to establish

        # Get public IP information
        response = requests.get("https://ipinfo.io/json", timeout=10)
        ip_info = response.json()

        # Check if location matches expected location
        actual_location = ip_info.get('city', '').lower()
        if expected_location.lower() in actual_location or expected_location.lower() in ip_info.get('region', '').lower():
            print(f"\n{GREEN}✅ Successfully connected to {expected_location}!{RESET}")

            # Display minimal connection info
            print(f"IP: {ip_info.get('ip', 'Unknown')} | Location: {ip_info.get('city', 'Unknown')}, {ip_info.get('country', 'Unknown')}")

            # Display latency to a popular website
            try:
                start = time.time()
                requests.get("https://www.google.com", timeout=5)
                latency = (time.time() - start) * 1000
                print(f"Latency: {latency:.1f} ms")
            except:
                pass

        else:
            print(f"\n{YELLOW}⚠️ Connected, but location appears to be {ip_info.get('city', 'Unknown')} instead of {expected_location}.{RESET}")
    except Exception as e:
        print(f"\n{RED}Could not verify connection{RESET}")

def run_with_hidden_output(command, working_dir=None):
    """Run a command with hidden output"""
    devnull = open(os.devnull, 'w')
    try:
        if working_dir:
            original_dir = os.getcwd()
            os.chdir(working_dir)

        subprocess.run(command, stdout=devnull, stderr=devnull, check=True)

        if working_dir:
            os.chdir(original_dir)

        return True
    except subprocess.CalledProcessError:
        if working_dir:
            os.chdir(original_dir)
        return False
    finally:
        devnull.close()

def display_servers_and_choose(ranked_servers):
    """Display server list and get user choice"""
    # Determine speed thresholds
    fastest_speed = ranked_servers[0][1] if ranked_servers[0][1] != float('inf') else 1.0
    slow_threshold = fastest_speed * 2
    very_slow_threshold = fastest_speed * 4

    print(f"{BOLD}Available servers (fastest to slowest):{RESET}")
    for i, (server, response_time) in enumerate(ranked_servers, 1):
        # Format response time
        if response_time == float('inf'):
            speed_info = "Timeout"
            color = RED
        elif response_time < slow_threshold:
            speed_info = f"{response_time:.3f}s"
            color = GREEN
        elif response_time < very_slow_threshold:
            speed_info = f"{response_time:.3f}s"
            color = YELLOW
        else:
            speed_info = f"{response_time:.3f}s"
            color = RED

        # Print colored server info
        print(f"{i}. {color}{server['hostname']} ({server['location']}) - {speed_info}{RESET}")

    # Suggest the fastest server but allow user to choose
    if ranked_servers and ranked_servers[0][1] != float('inf'):
        fastest_server = ranked_servers[0][0]
        fastest_index = 1
    else:
        fastest_index = None

    # Ask user which server to connect to or to exit
    while True:
        if fastest_index:
            choice_input = input(f"\nEnter server number (1-{len(ranked_servers)}) [press Enter for fastest, 'E' to exit]: ")
            if choice_input.strip().upper() == 'E':
                return None
            if not choice_input.strip():
                return ranked_servers[fastest_index-1][0]
        else:
            choice_input = input(f"\nEnter server number (1-{len(ranked_servers)}) ['E' to exit]: ")
            if choice_input.strip().upper() == 'E':
                return None

        try:
            choice = int(choice_input)
            if 1 <= choice <= len(ranked_servers):
                return ranked_servers[choice-1][0]
            print(f"{RED}Invalid choice. Please enter a number between 1 and {len(ranked_servers)}.{RESET}")
        except ValueError:
            if choice_input.strip() and choice_input.strip().upper() != 'E':
                print(f"{RED}Please enter a valid number or 'E' to exit.{RESET}")

def connect_to_server(selected_server, config_path, birdrequires_dir):
    """Connect to the selected server"""
    print(f"\nConnecting to {BOLD}{selected_server['hostname']} ({selected_server['location']}){RESET}...")

    # Create a server-specific config file
    server_config_path = birdrequires_dir / f"riseup-{selected_server['hostname']}.conf"
    create_server_specific_config(config_path, selected_server, server_config_path)

    # Connect using OpenVPN with the server-specific config
    try:
        # Use the specific config file that only contains the selected server
        openvpn_command = ["openvpn", "--config", str(server_config_path)]

        # Start the OpenVPN process
        devnull = open(os.devnull, 'w')
        openvpn_process = subprocess.Popen(openvpn_command, stdout=devnull, stderr=devnull)

        # Try to verify the connection
        verify_connection(selected_server['location'])

        # Keep the script running until Ctrl+C
        print("\nVPN connection established. Press Ctrl+C to disconnect and select another server.")
        while openvpn_process.poll() is None:
            time.sleep(1)

    except KeyboardInterrupt:
        print(f"\n{YELLOW}VPN connection terminated.{RESET}")
    except Exception as e:
        print(f"\n{RED}Error connecting to VPN{RESET}")
    finally:
        # Make sure to kill the OpenVPN process
        try:
            if 'openvpn_process' in locals() and openvpn_process.poll() is None:
                openvpn_process.terminate()
                openvpn_process.wait(timeout=5)
        except:
            pass

        if devnull and not devnull.closed:
            devnull.close()

def main():
    if not check_sudo():
        # Relaunch with sudo without notification
        args = ['sudo', sys.executable] + sys.argv
        result = subprocess.call(args)
        sys.exit(result)

    script_dir = Path(os.path.dirname(os.path.abspath(__file__)))
    birdrequires_dir = script_dir / "birdrequires"

    # Create birdrequires directory if it doesn't exist
    if not birdrequires_dir.exists():
        birdrequires_dir.mkdir()

    # Initial setup
    os.system('clear')
    print(f"{BOLD}Welcome to PawsRise{RESET}")
    print("a Python script to connect to Riseup VPN (made by dorkerdotexe) \n")

    # Download required files silently
    generate_sh_url = "https://github.com/BarbossHack/RiseupVPN-OpenVPN/raw/refs/heads/master/generate.sh"
    sample_conf_url = "https://github.com/BarbossHack/RiseupVPN-OpenVPN/raw/refs/heads/master/riseup-ovpn.sample.conf"

    generate_sh_path = birdrequires_dir / "generate.sh"
    sample_conf_path = birdrequires_dir / "riseup-ovpn.sample.conf"

    download_file(generate_sh_url, generate_sh_path)
    download_file(sample_conf_url, sample_conf_path)

    # Make generate.sh executable
    if not os.access(generate_sh_path, os.X_OK):
        os.chmod(generate_sh_path, 0o755)

    # Run generate.sh silently
    print("Updating servers...")
    run_with_hidden_output(["./generate.sh"], working_dir=birdrequires_dir)

    # Check if riseup-ovpn.conf was created
    config_path = birdrequires_dir / "riseup-ovpn.conf"
    if not config_path.exists():
        print(f"{RED}Error: Could not update server list.{RESET}")
        sys.exit(1)

    # Parse server information
    servers = extract_servers(config_path)

    # Find the fastest server
    print("Testing server speeds...")
    ranked_servers = find_fastest_server(servers)

    # Main program loop
    while True:
        # Clear screen before showing servers
        os.system('clear')
        print(f"{BOLD}Welcome to PawsRise{RESET}")
        print("a Python script to connect to Riseup VPN (made by dorkerdotexe) \n")

        # Display servers and get choice
        selected_server = display_servers_and_choose(ranked_servers)

        # Exit if user chose to exit
        if selected_server is None:
            print(f"\n{GREEN}Goodbye!{RESET}")
            break

        # Connect to the selected server
        connect_to_server(selected_server, config_path, birdrequires_dir)

if __name__ == "__main__":
    main()
